"""Jura: every act in force of the Recueil systématique de la législation jurassienne (RSJU).

Source: the official portal rsju.jura.ch (IceCube CMS, server-rendered; src "portal").
  /fr/Sommaire/Sommaire.html                                   the table of contents
  /Scripts/Modules/CustomView/List.aspx?idn=<n>&name=SubCategories
                                                               one node of the systematics: its
                                                               sub-nodes and the acts filed in it
                                                               (<li class="file_<id>"> with the
                                                               RSJU number and the title)
  /fr/viewdocument.html?idn=<n>&id=<id>                        the act's page (url of the record)
  /fr/viewdocument.html?idn=<n>&id=<id>&download=1             its text in force (PDF)
Repealed texts live in a separate list ("Textes abrogés", name=Obsolete) that is not crawled.

The préambule is read from the PDF up to the first article: "Loi … (LiLEg)", "du 17 mai 2000",
then "Le Parlement de la République et Canton du Jura, vu …1), vu …2), arrête :". Footnote markers
("1)", superscript) become "[1]"; the notes are the endnotes at the end of the PDF, located through
the PDF's internal links from each marker (else by number). Hyperlinks inside the préambule and
inside its notes (e.g. "RS 151.1" -> admin.ch, "RSJU 101" -> rsju.jura.ch) go to "links", the
latter with "note": n.

abbr: the parenthetical closing the official title when it has the shape of an abbreviation
("(LiLEg)"; "(Loi sur les auberges, LAub)" gives abbr LAub and short_title "Loi sur les
auberges"; "(Code de procédure administrative)" is a short title only). adopted: the date under
the title; for an agreement signed on two days ("des 25 février et 5 mars 2014") the later one.
Extra fields: rsju_id, header (title block as printed), short_title.

Raw responses: build/cantonal/raw/JU/ (rerun is offline). Output: build/cantonal/JU.json.
Requires: requests, pymupdf.   Usage: python3 pipeline/cantonal/ju.py   (~3 min cold, 20 s cached)
"""
import html
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
RAW = ROOT / "build" / "cantonal" / "raw" / "JU"
OUT = ROOT / "build" / "cantonal" / "JU.json"
UA = "swiss-law-graph/1.0 (legal research; +https://opencaselaw.ch)"
HOST = "https://rsju.jura.ch"
WORKERS = 3          # concurrent requests to rsju.jura.ch
DELAY = 0.3          # seconds after each request, per worker

# ---------------------------------------------------------------- fetching (cached)
_local = threading.local()


def _session():
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _local.s = s
    return _local.s


def fetch(url, path):
    """GET url (cached at path). Retries 5xx / timeouts with backoff. Returns bytes or None."""
    if fresh(path):                                     # the text in force: re-read in a weekly refresh
        return path.read_bytes()
    err = None
    for attempt in range(6):
        try:
            r = _session().get(url, timeout=60)
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


# RSJU writes the path as /Scripts/ and, in places, /scripts/ (category 144 was missed until 2026-10-27)
LIST_RE = re.compile(r'href="(/Scripts/Modules/CustomView/List\.aspx\?idn=(\d+)&(?:amp;)?name=SubCategories)"', re.I)
FILE_RE = re.compile(r'<li class="file_(\d+)"><a href="(/fr/viewdocument\.html\?idn=(\d+)&(?:amp;)?id=\d+)">'
                     r'<strong>(.*?)</strong><span>(.*?)</span></a>', re.S)


def crawl():
    """All acts listed in the systematic table of contents: {id: {...}} in TOC order."""
    som = fetch(f"{HOST}/fr/Sommaire/Sommaire.html", RAW / "sommaire.html").decode("utf-8")
    todo = list(dict.fromkeys(m.group(2) for m in LIST_RE.finditer(som)))
    seen, acts = set(todo), {}
    while todo:
        batch, todo = todo, []
        with ThreadPoolExecutor(WORKERS) as ex:
            pages = list(ex.map(lambda n: (n, fetch(
                f"{HOST}/Scripts/Modules/CustomView/List.aspx?idn={n}&name=SubCategories",
                RAW / "list" / f"{n}.html")), batch))
        for n, page in pages:
            if page is None:
                continue
            s = page.decode("utf-8")
            for m in LIST_RE.finditer(s):
                if m.group(2) not in seen:
                    seen.add(m.group(2))
                    todo.append(m.group(2))
            for m in FILE_RE.finditer(s):
                fid = m.group(1)
                if fid not in acts:
                    acts[fid] = {"id": fid, "idn": m.group(3), "href": html.unescape(m.group(2)),
                                 "sr": norm(html.unescape(re.sub(r"<[^>]+>", "", m.group(4)))),
                                 "title": norm(html.unescape(re.sub(r"<[^>]+>", "", m.group(5))))}
    return acts, len(seen)


# ---------------------------------------------------------------- text helpers
MONTHS = {m: i for i, m in enumerate(
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(), 1)}
MONTHS.update({"fevrier": 2, "aout": 8, "decembre": 12})
_MON = "|".join(MONTHS)
DATE_RE = re.compile(r"\b(\d{1,2})\s*(?:er|ER)?\s+(" + _MON + r")\s+(\d{4})", re.I)
DATE_LINE_RE = re.compile(r"^\(?\s*(?:du|des|le|les)\s+\d{1,2}\s*(?:er)?\s*(?:(?:" + _MON
                          + r")\s*(?:\d{4}\s+)?)?(?:(?:et|au|,|/)\s*\d{1,2}\s*(?:er)?\s+)*(?:" + _MON
                          + r")\s+\d{4}.{0,60}$", re.I)
ENACT_WORDS = ["arrête", "arrêtent", "décrète", "décrètent", "édicte", "édictent", "ordonne",
               "adopte", "adoptent", "décide", "décident", "conviennent", "convient", "approuve",
               "prononce", "promulgue", "statue", "édicte les dispositions suivantes",
               "arrête les dispositions suivantes", "conviennent de ce qui suit",
               "sont convenus de ce qui suit", "ont convenu de ce qui suit",
               "conviennent des dispositions suivantes", "savoir faisons"]
ENACT_RE = re.compile(r"(?<![\w’'])(?:(?:" + "|".join(sorted(map(re.escape, ENACT_WORDS), key=len,
                                                                reverse=True))
                      + r")\b[^:;]{0,80}:|dont la teneur suit\s*:|(?:arrête|décrète|ordonne|"
                        r"édicte|adopte)\s*$)\s*$", re.I)
CONST_END_RE = re.compile(r"(?:se donne|adopte|s['’]est donné)\b.{0,60}Constitution.{0,30}$", re.I)
ARTICLE_RE = re.compile(r"^\s*(?:Article\s+(?:premier|unique|1)\b|Art\.\s*(?:1(?:er)?\b|premier|"
                        r"unique)|§\s*1\b)", re.I)
STRUCT_RE = re.compile(r"^\s*(?:TITRE|Titre|CHAPITRE|Chapitre|SECTION|Section|PARTIE|Partie|"
                       r"LIVRE|Livre)\b")
BASIS_RE = re.compile(r"(?<![\w’'])(?:vu|vus|vue|considérant|sur (?:la )?proposition|en application|"
                      r"en exécution|se fondant|sur la base|conformément|après avoir|d['’]entente|"
                      r"dans le but|animé|soucieux|conscient|désireux|décidé|résolu|attendu|"
                      r"en vertu|sur préavis|en complément|afin de|en vue|constatant|"
                      r"considérant|savoir faisons|sur le rapport|après examen)(?![\w’'])", re.I)


def norm(s):
    return re.sub(r"\s+", " ", s.replace(" ", " ").replace("­", "")).strip()


def iso(d, mon, y):
    return f"{int(y):04d}-{MONTHS[mon.lower()]:02d}-{int(d):02d}"


class Line:
    __slots__ = ("page", "y0", "y1", "x0", "x1", "size", "bold", "parts", "text", "note_no")

    def __init__(self, page, bbox, size, bold, parts, note_no=None):
        self.page, self.y0, self.y1, self.x0, self.x1 = page, bbox[1], bbox[3], bbox[0], bbox[2]
        self.size, self.bold, self.parts = size, bold, parts   # parts: [(text, marker, bbox)]
        self.note_no = note_no          # endnote number if the line opens an endnote ("1) RS …")
        self.text = norm("".join(t for t, _, _ in parts))


def page_lines(doc, pno):
    """Lines of a page in reading order. "1)" small and raised after text is a note marker; a
    small "1)" opening a line starts endnote 1. Superscript ordinals ("1er") stay text."""
    d = doc[pno].get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    sizes = {}
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                k = round(sp["size"], 1)
                sizes[k] = sizes.get(k, 0) + len(sp["text"].strip())
    body = max(sizes, key=sizes.get) if sizes else 12
    raw = []
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            spans = []
            for sp in ln["spans"]:
                if not sp["text"]:
                    continue
                if spans and sp["size"] < 0.8 * body and spans[-1]["size"] < 0.8 * body and \
                        re.fullmatch(r"[\d)]+\s*", sp["text"]) and re.fullmatch(r"\s*\d+", spans[-1]["text"]):
                    prev = dict(spans[-1])
                    prev["text"] += sp["text"]
                    prev["bbox"] = tuple(pymupdf.Rect(prev["bbox"]) | pymupdf.Rect(sp["bbox"]))
                    spans[-1] = prev
                    continue
                spans.append(sp)
            if not spans:
                continue
            parts, size, bold = [], 0, False
            for sp in spans:
                t = sp["text"]
                small = sp["size"] < 0.8 * body
                is_marker = small and bool(re.fullmatch(r"\s*\d{1,3}\)\s*", t)) and \
                    any(p[0].strip() for p in parts)
                parts.append((t, is_marker, tuple(sp["bbox"])))
                if t.strip() and not small:
                    size = max(size, sp["size"])
                    bold = bold or bool(sp["flags"] & 16)
            note_no = None
            if spans[0]["size"] < 0.8 * body and re.fullmatch(r"\s*\d{1,3}\)\s*", spans[0]["text"]):
                note_no = re.sub(r"\D", "", spans[0]["text"])
            raw.append(Line(pno, ln["bbox"], size or body, bold, parts, note_no))
    raw.sort(key=lambda l: (round((l.y0 + l.y1) / 2), l.x0))
    lines = []

    def same_row(p, l):      # vertical overlap of at least half the smaller line
        ov = min(p.y1, l.y1) - max(p.y0, l.y0)
        return ov >= 0.5 * min(p.y1 - p.y0, l.y1 - l.y0)

    for l in raw:
        if lines and same_row(lines[-1], l) and l.x0 >= lines[-1].x1 - 1 and not l.note_no:
            p = lines[-1]
            p.parts = p.parts + [(" ", False, None)] + l.parts
            p.text = norm("".join(t for t, _, _ in p.parts))
            p.size, p.bold, p.y0, p.x1 = max(p.size, l.size), p.bold or l.bold, min(p.y0, l.y0), l.x1
            continue
        lines.append(l)
    return [l for l in lines if l.text], body


def render(lines):
    """Plain text with note markers as [n]; returns (text, [(n, page, bbox)])."""
    out, marks = [], []
    for l in lines:
        for t, is_m, bb in l.parts:
            if is_m:
                n = re.sub(r"\D", "", t)
                out.append(f"[{n}]")
                marks.append((n, l.page, bb))
            else:
                out.append(t)
        out.append(" ")
    s = norm("".join(out))
    s = re.sub(r"\s+(\[\d+\])", r"\1", s)
    return s, marks


def endnotes(doc, marks):
    """{n: (text, [links])} for the markers. The note is where the marker's internal link points
    (some PDFs print no number in front of their notes), else the endnote numbered n, searched
    from the last page backwards. A note runs until the next note start, the next link target
    or a gap."""
    cache = {}

    def lines_of(pno):
        if pno not in cache:
            cache[pno] = page_lines(doc, pno)[0]
        return cache[pno]

    targets = {}                       # page -> y of every internal link target
    for pno in range(len(doc)):
        for lk in doc[pno].get_links():
            if lk.get("kind") == pymupdf.LINK_GOTO and lk.get("to") is not None and \
                    lk.get("page") is not None and 0 <= lk["page"] < len(doc):
                targets.setdefault(lk["page"], []).append(lk["to"].y)

    def note_at(pno, i):
        ls = lines_of(pno)
        body = [ls[i]]
        tys = targets.get(pno, [])
        for l in ls[i + 1:]:
            prev = body[-1]
            if l.note_no or re.fullmatch(r"[\d.]+", l.text) or l.y0 - prev.y1 > 6 or \
                    any(l.y0 - 2 <= ty <= l.y0 + 3 for ty in tys):
                break
            body.append(l)
        first = body[0]
        lead = first.parts
        if first.note_no:      # drop the number
            k = next(j for j, p in enumerate(lead) if re.fullmatch(r"\s*\d{1,3}\)\s*", p[0]))
            lead = lead[k + 1:]
        txt = norm(" ".join(["".join(t for t, _, _ in lead)] + [l.text for l in body[1:]]))
        txt = re.sub(r"^\d{1,3}\)\s*", "", txt)
        links = []
        for lk in doc[pno].get_links():
            if lk.get("kind") == pymupdf.LINK_URI:
                r = lk["from"]
                cy = (r.y0 + r.y1) / 2
                if any(l.y0 - 1 <= cy <= l.y1 + 1 for l in body):
                    links.append({"text": re.sub(r"^\d{1,3}\)\s*", "", link_text(doc[pno], r)),
                                  "href": lk["uri"]})
        return txt, links

    out = {}
    for n, pno, bb in marks:
        if n in out:
            continue
        found = None
        if bb:
            for lk in doc[pno].get_links():
                if lk.get("kind") != pymupdf.LINK_GOTO or not lk["from"].intersects(pymupdf.Rect(bb)):
                    continue
                tp, to = lk.get("page"), lk.get("to")
                if tp is None or to is None or not 0 <= tp < len(doc):
                    continue
                ls = lines_of(tp)
                cands = [i for i, l in enumerate(ls) if l.y0 - 3 <= to.y <= l.y1 + 1]
                cands.sort(key=lambda i: (ls[i].note_no != n, abs(ls[i].y0 - to.y)))
                if cands and (ls[cands[0]].note_no in (n, None)):
                    found = (tp, cands[0])
                    break
        if not found:
            for pno2 in range(len(doc) - 1, -1, -1):
                ls = lines_of(pno2)
                hit = next((i for i, l in enumerate(ls) if l.note_no == n), None)
                if hit is not None:
                    found = (pno2, hit)
                    break
        if found:
            out[n] = note_at(*found)
    return out


def link_text(page, r):
    """The words of a link: those whose centre lies inside its rectangle."""
    ws = [w for w in page.get_text("words")
          if r.x0 - 1 <= (w[0] + w[2]) / 2 <= r.x1 + 1 and r.y0 - 1 <= (w[1] + w[3]) / 2 <= r.y1 + 1]
    return norm(" ".join(w[4] for w in ws))


def parse_pdf(data):
    """Header, préambule and its notes from the act's PDF (pages before the first article)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    seq = []
    for pno in range(min(len(doc), 4)):
        ls, _ = page_lines(doc, pno)
        seq.extend(l for l in ls if not l.note_no)
        if any(ARTICLE_RE.match(l.text) for l in ls):
            break
    end = next((i for i, l in enumerate(seq) if ARTICLE_RE.match(l.text)), len(seq))
    # running header (RSJU number) and page number are bare numbers
    pre = [l for l in seq[:end] if not re.fullmatch(r"[\d.]+", l.text)]
    res = {"adopted": None, "paren": None, "issuer": "", "ingress": "", "notes": {}, "links": [],
           "header": ""}
    if not pre:
        return res
    # header: the bold title, then "du 17 mai 2000" (and notes such as "(état …)")
    i = 0
    while i < len(pre) and pre[i].bold and not STRUCT_RE.match(pre[i].text):
        i += 1
    title_end = i
    while i < len(pre) and not pre[i].bold and (DATE_LINE_RE.match(pre[i].text) or
                                                re.fullmatch(r"\([^()]{1,60}\)", pre[i].text)):
        i += 1
    start = i
    enact = None
    for j in range(start, min(len(pre), start + 60)):
        if STRUCT_RE.match(pre[j].text) and j > start:
            break
        if ENACT_RE.search(pre[j].text) or CONST_END_RE.search(pre[j].text):
            enact = j
            break
    header_lines = pre[:start]
    res["header"] = render(header_lines)[0]
    plain = [norm("".join(t for t, m, _ in l.parts if not m)) for l in header_lines]
    for s in plain[title_end:] + plain[:title_end]:
        m = DATE_RE.search(s.replace("1er", "1"))
        if m and (DATE_LINE_RE.match(s) or re.search(r"\b(?:du|des)\s+" + re.escape(m.group(0)), s)):
            res["adopted"] = iso(*m.groups())
            break
    title_plain = norm(" ".join(plain[:title_end]))
    m = re.search(r"\(([^()]{1,120})\)$", title_plain)
    if m:
        res["paren"] = norm(m.group(1))
    if enact is None:
        return res
    ing_lines = pre[start:enact + 1]
    ingress, marks = render(ing_lines)
    res["ingress"] = ingress
    m = BASIS_RE.search(ingress)
    e = ENACT_RE.search(ingress) or CONST_END_RE.search(ingress)
    cut = min([x.start() for x in (m, e) if x] or [len(ingress)])
    res["issuer"] = re.sub(r"\[\d+\]", "", ingress[:cut]).strip().rstrip(",;:-–— ").strip()
    links = []
    for pno in sorted({l.page for l in ing_lines}):
        for lk in doc[pno].get_links():
            if lk.get("kind") == pymupdf.LINK_URI:
                r = lk["from"]
                if any(l.page == pno and l.y0 - 1 <= (r.y0 + r.y1) / 2 <= l.y1 + 1 for l in ing_lines):
                    links.append({"text": link_text(doc[pno], r), "href": lk["uri"]})
    if marks:
        notes = endnotes(doc, marks)
        res["notes"] = {n: notes[n][0] for n, _, _ in marks if n in notes}
        for n in dict.fromkeys(n for n, _, _ in marks):
            for lk in notes.get(n, ("", []))[1]:
                links.append({**lk, "note": n})
    res["links"] = links
    return res


ACT_WORD_RE = re.compile(r"(?:loi|ordonnance|code|règlement|arrêté|décret|concordat|convention|"
                         r"accord|tarif|statuts?|directive)\b", re.I)


def abbr_shape(s):
    """An abbreviation, not a word: "LiLEg", "CPDT-JUNE", "HES-SO"; not "Cameroun", "2007-2011"."""
    toks = s.split()
    if not toks or len(toks) > 3 or re.fullmatch(r"[\d\s.\-–/]+", s):
        return False
    if len(toks) == 1:
        t = toks[0]
        return sum(ch.isupper() for ch in t) >= 2 and not re.match(r"[A-ZÀ-Ý][a-zà-ÿ]{4,}", t)
    return sum(ch.isupper() for ch in s) >= 2 and all(
        re.search(r"[A-ZÀ-Ý\d]", t) or len(t) <= 3 for t in toks) and \
        not any(re.fullmatch(r"[A-ZÀ-Ý][a-zà-ÿ’']{4,}", t) for t in toks)


def abbr_of(title, paren):
    """(abbr, short title) the RSJU states in the parenthetical closing the official title (portal
    title, else the PDF's): "(LiLEg)" -> LiLEg; "(Loi sur les auberges, LAub)" -> LAub + short title;
    "(Code de procédure administrative)" -> short title only; "(Cameroun)" -> neither."""
    m = re.search(r"\(([^()]{1,120})\)$", title)
    cand = norm(m.group(1)) if m else paren
    if not cand:
        return None, None
    parts = [p.strip() for p in cand.split(",")]
    if abbr_shape(parts[-1]):
        return parts[-1], (", ".join(parts[:-1]) or None)
    return None, (cand if ACT_WORD_RE.match(cand) else None)


# ---------------------------------------------------------------- main
def act(a):
    url = f"{HOST}/fr/viewdocument.html?idn={a['idn']}&id={a['id']}"
    rec = {"ct": "JU", "sr": a["sr"], "title": a["title"], "abbr": None, "url": url,
           "in_force": True, "adopted": None, "issuer": "", "ingress": "", "notes": {},
           "links": [], "lang": "fr", "src": "portal", "rsju_id": int(a["id"])}
    data = fetch(url + "&download=1", RAW / "pdf" / f"{a['id']}.pdf")
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
    rec["abbr"], short = abbr_of(a["title"], p["paren"])
    if short:
        rec["short_title"] = short
    rec["header"] = p["header"]
    return rec


def sr_key(sr):
    return [int(x) if x.isdigit() else x for x in re.split(r"[.]", sr)]


def main():
    t0 = time.time()
    acts, n_nodes = crawl()
    print(f"JU: {len(acts)} acts in force in {n_nodes} systematic nodes")
    with ThreadPoolExecutor(WORKERS) as ex:
        recs = list(ex.map(act, acts.values()))
    recs.sort(key=lambda r: (sr_key(r["sr"]), r["rsju_id"]))
    OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1))
    print(f"wrote {OUT} ({len(recs)} acts): ingress {sum(bool(r['ingress']) for r in recs)}, "
          f"adopted {sum(bool(r['adopted']) for r in recs)}, abbr {sum(bool(r['abbr']) for r in recs)}, "
          f"notes {sum(bool(r['notes']) for r in recs)}, "
          f"errors {sum('text_error' in r for r in recs)}; {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
