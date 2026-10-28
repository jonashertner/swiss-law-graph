"""Ticino: every act in force of the Raccolta delle leggi (RL), via LexFind.

The official RL (www3.ti.ch/CAN/RLeggi) cannot be reached from the build sandbox (every *.ti.ch
host: tunnel closed), so the canton's collection is read from LexFind (lexfind.ch, Institut du
Fédéralisme), which mirrors it (src "lexfind"). The record's url is the official RL page LexFind
names (dta_urls[].original_url), else the LexFind page of the act.

Endpoints (LexFind frontend API, read from its SPA bundle):
  GET /api/fe/it/entities/21/systematics?active_only=false              the RL systematic tree
  GET /api/fe/it/entities/21/systematics?...&tols_for_systematics[]=<n>  + the acts in node n
  GET /api/fe/it/texts-of-law/<id>/with-version-groups                  one act: dta_urls,
                                                                        versions, category
  GET /tol/<id>/it                                                      current text (PDF)
The Ingress is read from the PDF up to the first article: title, "(LCCit)", "(dell'8 novembre
1994)", then "IL GRAN CONSIGLIO DELLA REPUBBLICA E CANTONE TICINO visti il messaggio … d e c r e t a :".
The letter-spaced enacting word is written closed up ("decreta:"). Footnote markers (superscript
numbers) become "[n]"; their text is taken from the page's footnote zone.

Systematic numbers are LexFind's (the RL numbering since July 2018, "141.100"). abbr: the
parenthetical closing the official title when it has the shape of an abbreviation and agrees with
LexFind's short name (keywords); "(legge sanitaria, LSan)" gives abbr LSan and short_title
"legge sanitaria". Extra fields: lexfind_id, lexfind_url, category, version_active_since,
keywords (LexFind's short name), header (title block as printed), short_title.

Raw responses: build/cantonal/raw/TI/ (rerun is offline). Output: build/cantonal/TI.json.
Requires: requests, pymupdf.   Usage: python3 pipeline/cantonal/ti.py   (~4 min cold, 5 s cached)
"""
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refresh import fresh  # noqa: E402  (weekly refresh)

try:
    import pymupdf
except ImportError:  # older PyMuPDF
    import fitz as pymupdf

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "build" / "cantonal" / "raw" / "TI"
OUT = ROOT / "build" / "cantonal" / "TI.json"
UA = "swiss-law-graph/1.0 (legal research; +https://opencaselaw.ch)"
HOST = "https://www.lexfind.ch"
API = HOST + "/api/fe/it"
ENTITY = 21
WORKERS = 3          # concurrent requests to lexfind.ch
DELAY = 0.3          # seconds after each request, per worker

# ---------------------------------------------------------------- fetching (cached)
_local = threading.local()


def _session():
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _local.s = s
    return _local.s


def fetch(url, path, params=None, accept="application/json"):
    """GET url (cached at path; re-read in a weekly refresh). Retries 5xx / timeouts with backoff. Returns bytes or None."""
    if fresh(path):
        return path.read_bytes()
    err = None
    for attempt in range(6):
        try:
            r = _session().get(url, params=params, headers={"Accept": accept}, timeout=60)
            time.sleep(DELAY)
            if r.status_code == 200:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(path.suffix + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(path)
                return r.content
            if r.status_code in (404, 410):
                return None
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            err = repr(e)
        time.sleep(2 * 2 ** attempt)
    print(f"  ! giving up on {url}: {err}", file=sys.stderr)
    return None


def systematics():
    """The RL tree with the acts hanging in each node (active and repealed)."""
    base = f"{API}/entities/{ENTITY}/systematics"
    tree = json.loads(fetch(base, RAW / "systematics.json", {"active_only": "false"}))
    ids = sorted((k for k in tree if k), key=int)
    for i in range(0, len(ids), 40):             # long query strings get HTTP 414
        batch = ids[i:i + 40]
        params = [("active_only", "false")] + [("tols_for_systematics[]", x) for x in batch]
        part = json.loads(fetch(base, RAW / "systematics" / f"tols_{i // 40:03d}.json", params))
        for x in batch:
            tree[x]["tols"] = part[x]["tols"]
    return tree


# ---------------------------------------------------------------- text helpers
MONTHS = {m: i for i, m in enumerate(
    "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre "
    "dicembre".split(), 1)}
_MON = "|".join(MONTHS)
DATE_RE = re.compile(r"\b(\d{1,2})\s*(?:°|º)?\s*(" + _MON + r")\s+(\d{4})", re.I)
# "(dell'8 novembre 1994)", "del 22 giugno 1994 (stato 15 marzo 2026)", "(25 novembre 1994)"
DATE_LINE_RE = re.compile(r"^\(?\s*(?:(?:del|dell[’'`]|dal|dei|delli)\s*)?\d{1,2}\s*[°º]?\s*(?:"
                          + _MON + r")\s+\d{4}\s*\)?\s*(?:\((?:stato\b|\d)[^)]*\)?)?\s*$", re.I)
# notes under the title that precede the issuer: "Approvato dal Consiglio federale il …"
HEAD_NOTE_RE = re.compile(r"^(?:\(?stato\b|approvat[oa]\b|modifica approvata|data dell[’']entrata|"
                          r"entrat[oa] in vigore|ratificat[oa]|adottat[oa]\b|\(?in vigore)", re.I)
ADOPT_RE = re.compile(r"(?:\b(?:del|dell[’'`]|dal|dei)\s*|\(\s*)(\d{1,2})\s*[°º]?\s*(" + _MON
                      + r")\s+(\d{4})", re.I)
# enacting words, closed up (the RL letter-spaces them: "d e c r e t a :", "riso lv e:")
ENACT = {"decreta": "decreta", "decretano": "decretano", "risolve": "risolve", "pronuncia": "pronuncia",
         "risolvono": "risolvono", "hannorisoluto": "hanno risoluto", "harisoluto": "ha risoluto",
         "ordina": "ordina", "emana": "emana", "emanano": "emanano", "adotta": "adotta",
         "adottano": "adottano", "stabilisce": "stabilisce", "dispone": "dispone",
         "convengono": "convengono", "conviene": "conviene", "decide": "decide",
         "delibera": "delibera", "deliberano": "deliberano", "statuisce": "statuisce",
         "approva": "approva", "hannoconvenutoquantosegue": "hanno convenuto quanto segue",
         "convengonoquantosegue": "convengono quanto segue",
         "hannodecretato": "hanno decretato", "hadecretato": "ha decretato",
         "decretaedordina": "decreta ed ordina", "decretaeordina": "decreta e ordina",
         "risolveedecreta": "risolve e decreta", "decretaerisolve": "decreta e risolve"}
_ENACT_TAIL = [(re.compile(r"(?<![\w’'])" + r"\s*".join(map(re.escape, k)) + r"\s*:\s*$", re.I), v)
               for k, v in sorted(ENACT.items(), key=lambda kv: -len(kv[0]))]
ARTICLE_RE = re.compile(r"^\s*(?:§\s*1\b|Art(?:icolo|\.)\s*(?:1\s*[a-z]?\b|1$|unico|primo)|"
                        r"Articolo\s+unico|Art\.\s*unico|Art\.\s*1\d*$)", re.I)
STRUCT_RE = re.compile(r"^\s*(?:TITOLO|Titolo|CAPITOLO|Capitolo|PARTE|Parte|Sezione|SEZIONE|"
                       r"Libro|LIBRO)\b|^\s*[IVX]+\.\s+\S")
BASIS_RE = re.compile(r"(?<!\w)(?:visti|visto|vista|viste|richiamat[aoie]|considerat[aoie]|"
                      r"preso atto|in applicazione|in esecuzione|su proposta|sentit[aoie]|"
                      r"ritenut[aoie]|in base|fondandosi|giusta|conformemente|nell[’']intento|"
                      r"allo scopo|in virtù|esaminat[aoie]|letto|letti|dopo aver|"
                      r"richiamandosi|riferendosi|tenuto conto|in conformità|in ossequio|"
                      r"vist[oaie]|vedut[oaie]|a norma|sulla base|in attuazione|secondo|ai sensi|"
                      r"sulla proposta|dietro proposta|in aggiunta|a complemento|d[’']intesa|"
                      r"previo|udit[oaie]|accertat[oaie]|constatat[oaie]|"
                      r"dopo aver(?:e)?|nell[’']intento|riservat[oaie]|desideros[oaie]|consapevol[ei]|"
                      r"convint[oaie]|animat[oaie]|intenzionat[oaie]|considerando|"
                      r"richiamandosi|tenendo conto)(?!\w)", re.I)
# basis words the RL letter-spaces ("c o n s i d e ra t o :") are closed up like the enacting word
SPACED_WORDS = ["considerato", "considerati", "richiamato", "richiamati", "richiamata",
                "richiamate", "visto", "visti", "vista", "viste", "ritenuto"]
_SPACED_RE = [(re.compile(r"(?<![\w’'])" + r"\s*".join(w) + r"(?![\w’'])", re.I), w)
              for w in SPACED_WORDS]


def close_up(s):
    for rx, w in _SPACED_RE:
        s = rx.sub(lambda m: m.group(0) if " " not in m.group(0) else
                   (w.capitalize() if m.group(0)[0].isupper() else w), s)
    return s


ACT_WORD_RE = re.compile(r"(?:legge|regolamento|decreto|concordato|convenzione|accordo|direttiva|"
                         r"ordinanza|codice|tariffa|statuto|statuti|concordat|loi)\b", re.I)


def abbr_shape(s, confirmed=False):
    """An abbreviation, not a word: "LCCit", "Reg. Laf", "HarmoS"; not "Zugo", "Basilea-Città".
    With LexFind's confirmation (keywords) a single capitalised token passes ("Lcan", "Lorform")."""
    toks = s.split()
    if not toks or len(toks) > 3 or re.fullmatch(r"[\d\s.\-–/]+", s):
        return False
    if len(toks) == 1:
        t = toks[0]
        if confirmed:
            return bool(re.match(r"[A-ZÀ-Ý]", t))
        return sum(ch.isupper() for ch in t) >= 2 and not re.match(r"[A-ZÀ-Ý][a-zà-ÿ]{4,}", t)
    return sum(ch.isupper() for ch in s) >= 2 and all(
        re.search(r"[A-ZÀ-Ý\d]", t) or len(t) <= 3 for t in toks) and \
        not any(re.fullmatch(r"[A-ZÀ-Ý][a-zà-ÿ’']{4,}", t) for t in toks)


def abbr_of(paren, keywords):
    """(abbr, short title) the RL states in the parenthetical closing the official title:
    "(LCCit)" -> LCCit; "(legge sanitaria, LSan)" -> LSan + short title "legge sanitaria";
    "(Legge autoambulanze)" -> short title only. Where LexFind files a short name (keywords),
    the parenthetical counts only if it is that name; "(Zugo)" is neither."""
    if not paren:
        return None, None
    confirmed = bool(keywords)
    if confirmed and norm(keywords) != paren:
        return None, None
    parts = [p.strip() for p in paren.split(",")]
    if abbr_shape(parts[-1], confirmed):
        return parts[-1], (", ".join(parts[:-1]) or None)
    return None, (paren if ACT_WORD_RE.match(paren) else None)


def norm(s):
    return re.sub(r"\s+", " ", s.replace(" ", " ").replace("­", "")).strip()


def iso(d, mon, y):
    return f"{int(y):04d}-{MONTHS[mon.lower()]:02d}-{int(d):02d}"


ENACT_PHRASE_RE = re.compile(
    r"(?<![\w’'])(?:emana|emanano|adotta|adottano|decreta|decretano|risolve|ordina|stabilisce|"
    r"dispone|convengono|si conviene|conviene|hanno convenuto|decide|delibera|pronuncia|"
    r"approva|statuisce|hanno stipulato|stipulano|provvede)\b[^:;]{0,80}"
    r"(?::|quanto segue\s*[,.:]?)\s*$", re.I)


def enact_tail(text):
    """(start, enacting words) if the line ends with the enacting word + colon. Letter-spaced
    single words come back closed up; written-out phrases verbatim (None)."""
    for rx, word in _ENACT_TAIL:
        m = rx.search(text)
        if m:
            return m.start(), word
    m = ENACT_PHRASE_RE.search(text)
    if m:
        return m.start(), None
    return None


class Line:
    __slots__ = ("page", "y0", "y1", "x0", "size", "bold", "parts", "text", "note_no")

    @property
    def plain(self):
        """The text without footnote markers."""
        return norm("".join(t for t, m in self.parts if not m))

    def __init__(self, page, bbox, size, bold, parts, note_no=None):
        self.page, self.y0, self.y1, self.x0 = page, bbox[1], bbox[3], bbox[0]
        self.size, self.bold, self.parts = size, bold, parts   # parts: [(text, is_marker)]
        self.note_no = note_no          # footnote number if the line starts a footnote
        self.text = norm("".join(t for t, _ in parts))


def page_lines(doc, pno):
    """Lines of a page in reading order. A small raised number after text is a footnote marker;
    a small number opening a line is the start of a footnote."""
    page = doc[pno]
    d = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    sizes = {}
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                k = round(sp["size"], 1)
                sizes[k] = sizes.get(k, 0) + len(sp["text"].strip())
    body = max(sizes, key=sizes.get) if sizes else 10
    raw = []
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            spans = [sp for sp in ln["spans"] if sp["text"]]
            if not spans:
                continue
            base = max(sp["origin"][1] for sp in spans if sp["size"] >= 0.85 * body) \
                if any(sp["size"] >= 0.85 * body for sp in spans) else spans[0]["origin"][1]
            parts, size, bold = [], 0, False
            for sp in spans:
                t = sp["text"]
                small = sp["size"] < 0.85 * body
                sup = bool(sp["flags"] & 1) or (small and sp["origin"][1] < base - 1)
                is_marker = small and sup and bool(re.fullmatch(r"\s*\d{1,3}\)?\s*", t)) \
                    and any(p.strip() for p, _ in parts)
                parts.append((t, is_marker))
                if t.strip() and not is_marker and not small:
                    size = max(size, sp["size"])
                    bold = bold or bool(sp["flags"] & 16)
            note_no = None
            first = spans[0]
            if first["size"] < 0.85 * body and re.fullmatch(r"\s*\d{1,3}\)?\s*", first["text"]) \
                    and len(spans) > 1:
                note_no = re.sub(r"\D", "", first["text"])
            raw.append(Line(pno, ln["bbox"], size or body, bold, parts, note_no))
    # merge pieces that PyMuPDF split into separate lines on the same baseline
    raw.sort(key=lambda l: (round(l.y1), l.x0))
    lines = []
    for l in raw:
        if lines and abs(lines[-1].y1 - l.y1) < 2.5 and l.x0 >= lines[-1].x0 and not l.note_no:
            p = lines[-1]
            p.parts = p.parts + [(" ", False)] + l.parts
            p.text = norm("".join(t for t, _ in p.parts))
            p.size = max(p.size, l.size)
            p.bold = p.bold or l.bold
            p.y0 = min(p.y0, l.y0)
            continue
        lines.append(l)
    return [l for l in lines if l.text], body


def render(lines):
    """Plain text with footnote markers as [n]; returns (text, [marker numbers])."""
    out, marks = [], []
    for l in lines:
        for t, is_m in l.parts:
            if is_m:
                n = re.sub(r"\D", "", t)
                out.append(f"[{n}]")
                marks.append(n)
            else:
                out.append(t)
        out.append(" ")
    s = norm("".join(out))
    s = re.sub(r"\s+(\[\d+\])", r"\1", s)
    return s, marks


def foot_zone(lines):
    """The footnote block at the foot of a page: the run of lines from the bottom (page number
    dropped) with no vertical gap, opening with a footnote number. Returns its lines."""
    body = [l for l in lines if not re.fullmatch(r"\d{1,4}", l.text)]
    zone = []
    for l in reversed(body):
        if zone and zone[-1].y0 - l.y1 > 4:
            break
        zone.append(l)
    zone.reverse()
    while zone and not zone[0].note_no:
        zone.pop(0)
    return zone


def page_footnotes(lines):
    """{n: text} of a page's footnotes: a line opening with a small number starts note n, the
    lines after it continue it."""
    notes, cur = {}, None
    for l in foot_zone(lines):
        if l.note_no:
            cur = l.note_no
            notes[cur] = norm("".join(t for t, _ in l.parts[1:]))
        elif cur is not None:
            notes[cur] = norm(notes[cur] + " " + l.text)
    return notes


def link_text(page, r):
    """The words of a link: those whose centre lies inside its rectangle."""
    ws = [w for w in page.get_text("words")
          if r.x0 - 1 <= (w[0] + w[2]) / 2 <= r.x1 + 1 and r.y0 - 1 <= (w[1] + w[3]) / 2 <= r.y1 + 1]
    return norm(" ".join(w[4] for w in ws))


def parse_pdf(data):
    """Header, Ingress and its footnotes from the act's PDF (pages before the first article)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    seq, pages = [], {}
    for pno in range(min(len(doc), 4)):
        ls, _ = page_lines(doc, pno)
        pages[pno] = ls
        fz = {id(l) for l in foot_zone(ls)}
        seq.extend(l for l in ls if id(l) not in fz)
        if any(ARTICLE_RE.match(l.plain) for l in ls):
            break
    end = next((i for i, l in enumerate(seq) if ARTICLE_RE.match(l.plain)), len(seq))
    # running header (systematic number) and page numbers are bare numbers
    pre = [l for l in seq[:end] if not re.fullmatch(r"[\d.]+", l.text)]
    res = {"adopted": None, "paren": None, "issuer": "", "ingress": "", "notes": {},
           "links": [], "header": ""}
    if not pre:
        return res
    # header = bold title lines, then "(ABBR)", the date line, "(stato …)", approval notes
    i = 0
    while i < len(pre) and pre[i].bold:
        i += 1
    while i < len(pre) and not pre[i].bold and (
            DATE_LINE_RE.match(pre[i].text) or re.fullmatch(r"\([^()]{1,30}\)(?:\d+)?", pre[i].text)
            or HEAD_NOTE_RE.match(pre[i].text)):
        i += 1
        if HEAD_NOTE_RE.match(pre[i - 1].text):     # a note under the title may run on
            while i < len(pre) and re.match(r"[a-zà-ÿ]", pre[i].text):
                i += 1
    start = i
    # the enacting word closes the Ingress
    enact = None
    for j in range(start, len(pre)):
        if enact_tail(pre[j].text):
            enact = j
            break
    pre_text = norm(" ".join(l.text for l in pre))
    if enact is None and re.search(r"\bPREAMBOLO\b", pre_text, re.I):
        # the Constitution: "PREAMBOLO Il popolo ticinese - … si dà la seguente COSTITUZIONE"
        k = next(j for j, l in enumerate(pre) if re.fullmatch(r"PREAMBOLO", l.text, re.I))
        last = next((j for j in range(k, len(pre)) if re.search(r"si d[àa]\b.*COSTITUZIONE",
                                                                pre[j].text, re.I)), None)
        if last is not None:
            start, enact = k + 1, last
    if enact is None and start < len(pre) and pre[start].text.isupper() and \
            re.search(r"CONSIGLIO|DIPARTIMENTO|CONFERENZA|COMMISSIONE|TRIBUNALE", pre[start].text):
        # issuer and bases with no enacting word: the preamble ends before the first heading
        j = start + 1
        while j < len(pre) and not pre[j].bold and not STRUCT_RE.match(pre[j].text):
            j += 1
        if any(BASIS_RE.match(re.sub(r"^[-–—•]\s*", "", l.text)) for l in pre[start + 1:j]):
            enact = j - 1
    header_lines = pre[:start] if enact is not None else pre[:i]
    res["header"] = render(header_lines)[0]
    head_plain = re.sub(r"\(stato\b[^)]*\)|(?<=\d{4})\s*\(\d[^)]*\)", "", " ".join(
        "".join(t for t, m in l.parts if not m) for l in header_lines))
    date_lines = [re.sub(r"\(stato\b[^)]*\)|(?<=\d{4})\s*\(\d[^)]*\)", "", l.text)
                  for l in header_lines if DATE_LINE_RE.match(l.text)]
    dates = [m for s in date_lines for m in DATE_RE.finditer(s)][:1] or \
        list(ADOPT_RE.finditer(head_plain))[-1:]
    if dates:
        res["adopted"] = iso(*dates[0].groups())
    # "(LCCit)" on its own line or closing the title (an abbreviation: short, with a capital)
    k = next((j for j in range(i) if DATE_LINE_RE.match(pre[j].text)
              or HEAD_NOTE_RE.match(pre[j].text)), i)
    title_plain = norm(" ".join(l.plain for l in pre[:k]))
    m = re.search(r"\(([^()]{1,120})\)$", title_plain)
    if m:
        res["paren"] = norm(m.group(1))
    if enact is None:
        return res
    ing_lines = [l for l in pre[start:enact + 1] if not (l.bold and l.text == "Ingresso")]
    ingress, marks = render(ing_lines)
    ingress = close_up(ingress)
    t = enact_tail(ingress)
    if t and t[1]:
        ingress = (ingress[:t[0]].rstrip() + " " + t[1] + ":").strip()
    res["ingress"] = ingress
    m = BASIS_RE.search(ingress)
    cut = m.start() if m else (t[0] if t else len(ingress))
    if t:
        cut = min(cut, t[0])
    res["issuer"] = re.sub(r"\[\d+\]", "", ingress[:cut]).strip().rstrip(",;:-–— ").strip()
    if marks:
        notes = {}
        for pno in sorted({l.page for l in ing_lines}):
            for pn in (pno, pno + 1):
                if pn in pages or pn < len(doc):
                    ls = pages.get(pn) or page_lines(doc, pn)[0]
                    for k, v in page_footnotes(ls).items():
                        notes.setdefault(k, v)
                if all(n in notes for n in marks):
                    break
        res["notes"] = {n: notes[n] for n in dict.fromkeys(marks) if n in notes}
    links = []
    for pno in sorted({l.page for l in ing_lines}):
        for lk in doc[pno].get_links():
            if lk.get("kind") != pymupdf.LINK_URI:
                continue
            r = lk["from"]
            if any(l.page == pno and l.y0 - 1 <= (r.y0 + r.y1) / 2 <= l.y1 + 1 for l in ing_lines):
                links.append({"text": link_text(doc[pno], r), "href": lk["uri"]})
    res["links"] = links
    return res


# ---------------------------------------------------------------- main
def act(tol):
    tid = tol["id"]
    meta = json.loads(fetch(f"{API}/texts-of-law/{tid}/with-version-groups",
                            RAW / "tol" / f"{tid}.json"))
    dta = [d for d in meta.get("dta_urls") or [] if d.get("language") == "it"] or \
        (meta.get("dta_urls") or [])
    url = next((d["original_url"] for d in dta if d.get("original_url")), None)
    rec = {"ct": "TI", "sr": tol["systematic_number"], "title": norm(tol["title"]),
           "abbr": None, "url": url or f"{HOST}/fe/it/tol/{tid}/it", "in_force": True,
           "adopted": None, "issuer": "", "ingress": "", "notes": {}, "links": [],
           "lang": "it", "src": "lexfind", "lexfind_id": tid,
           "lexfind_url": f"{HOST}/fe/it/tol/{tid}/it"}
    cur = [v for fam in meta.get("families") or [] for grp in fam for v in grp
           if v.get("info_badge") == "current" or (v.get("is_active") and v.get("type") == "version")]
    if cur:
        rec["category"] = (cur[0].get("category") or {}).get("name")
        rec["version_active_since"] = cur[0].get("version_active_since")
        rec["keywords"] = cur[0].get("keywords")
    else:
        rec["keywords"] = tol.get("keywords")
    if not dta:
        rec["text_error"] = "no text on LexFind"
        return rec
    data = fetch(HOST + dta[0]["url"], RAW / "text" / f"{tid}.pdf", accept="application/pdf,*/*")
    if not data:
        rec["text_error"] = "text not served"
        return rec
    if not data.startswith(b"%PDF"):
        rec["text_error"] = "text is not a PDF"
        return rec
    try:
        p = parse_pdf(data)
    except Exception as e:  # a broken PDF must not stop the run
        rec["text_error"] = f"PDF parse failed: {e!r}"
        return rec
    rec.update({k: p[k] for k in ("adopted", "issuer", "ingress", "notes", "links")})
    rec["abbr"], short = abbr_of(p["paren"], rec.get("keywords"))
    if short:
        rec["short_title"] = short
    rec["header"] = p["header"]
    return rec


def main():
    t0 = time.time()
    tree = systematics()
    tols, seen = [], set()
    for k, node in tree.items():
        for t in node.get("tols") or []:
            if t["is_active"] and t["id"] not in seen:
                seen.add(t["id"])
                tols.append(t)
    n_all = len({t["id"] for n in tree.values() for t in n.get("tols") or []})
    print(f"TI: {len(tols)} acts in force ({n_all} on LexFind incl. repealed)")
    with ThreadPoolExecutor(WORKERS) as ex:
        recs = list(ex.map(act, tols))
    recs.sort(key=lambda r: ([int(x) if x.isdigit() else x for x in re.split(r"[.]", r["sr"])],
                             r["lexfind_id"]))
    OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1))
    n = len(recs)
    print(f"wrote {OUT} ({n} acts): ingress {sum(bool(r['ingress']) for r in recs)}, "
          f"adopted {sum(bool(r['adopted']) for r in recs)}, abbr {sum(bool(r['abbr']) for r in recs)}, "
          f"official url {sum('ti.ch' in r['url'] for r in recs)}, "
          f"errors {sum('text_error' in r for r in recs)}; {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
