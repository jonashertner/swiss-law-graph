"""The legal basis of every federal act, from its Ingress (preamble) on Fedlex.

Standard library only. Federal drafting states, at the head of each act, who enacts
it and on what basis: "Die Bundesversammlung der Schweizerischen Eidgenossenschaft,
gestützt auf Artikel 122 Absatz 1 der Bundesverfassung¹, … beschliesst:" — ¹ SR 101.
An ordinance names the articles of the act(s) delegating to it: "Der Schweizerische
Bundesrat, gestützt auf Artikel 96 des Bundesgesetzes vom 18. März 1994² über die
Krankenversicherung (KVG), … verordnet:". Each footnote carries the SR number of the
act named (Fedlex marks it as an attribute, rs="101", or as an eli/cc link).

For every act in force plus every cited act (the list of fetch_fedlex_xrefs.py), the
consolidated German XML applicable on RUN_DATE is read once and this is kept:
  title, short   the preface: title and abbreviation
  issuer         the first line of the Ingress ("Der Schweizerische Bundesrat")
  ingress        the Ingress text without footnotes, verbatim (for the reader)
  bases          in order of the text: [target SR, [article numbers], clause, note, via, how]
                 clause = the words naming the basis ("Artikel 122 Absatz 1 der
                 Bundesverfassung"); for an act based on the 1874 Constitution, the
                 Fedlex footnote gives today's equivalent ("Dieser Bestimmung
                 entspricht Artikel 122 der Bundesverfassung vom 18. April 1999"):
                 then the target is 101 and the articles are the equivalent ones,
                 and `note` keeps the footnote text. via: text | aBV→BV | aBV (no
                 equivalent given); how: basis ("gestützt auf") | exec ("in Ausführung von").
  arts           article eIds of the act's body (to check bases against).
  adopted        the date in the preface ("vom 19. Dezember 2008")
  notes          the Ingress's editorial footnotes ("Fassung gemäss …"): an Ingress revised
                 since 2000 cites today's Constitution, an older one may cite that of 1874
                 even where the footnote only gives "SR 101".
Paragraph, letter and number qualifiers ("Absatz 1", "Bst. a") are dropped: the map
works at article level. The XML is discarded. The URL list is cached in
build/fedlex_xml_urls.json (rerun reuses it).

Output: data/fedlex_basis.json {"run_date", "source", "acts": {sr: {...}}}
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = "2026-10-26"
SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
FX = "{http://fedlex.admin.ch/}"
LATIN = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies|undecies|duodecies)"
NUM = rf"\d+(?:\s?[a-z](?![a-z])|{LATIN})?(?:{LATIN})?"
ART_KW = re.compile(r"\b(?:Artikeln|Artikel|Art\.?)\s+(?=\d)")
QUAL = re.compile(r"^(?:Absätze|Absatz|Abs\.|Buchstaben|Buchstabe|Bst\.|lit\.|Ziffern|Ziffer|Ziff\.|Sätze|Satz|Unterabsatz)\s*")
SR_TEXT = re.compile(r"\bSR\s+(0\.\d[\d.]*\d|\d[\d.]*\d|\d)\b")
EQUIV = re.compile(r"entspr\w*\s+(?:heute\s+)?(?:(?:dem|den|der|die)\s+)?(?:Art(?:ikeln|ikel|\.)?\s+)(.+?)\s+(?:der|des)\s+(?:Bundesverfassung|BV)\b")

# Consolidations of given acts (ELI URIs from data/sr_eli.csv): looking acts up by URI is
# some 20 times faster than matching SR notations as strings.
Q = """PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?act ?date ?url WHERE {
 VALUES ?act { %s }
 ?cons jolux:isMemberOf ?act ; jolux:dateApplicability ?date ; jolux:isRealizedBy ?expr .
 FILTER(?date <= "%s"^^xsd:date)
 ?expr jolux:language <http://publications.europa.eu/resource/authority/language/DEU> ; jolux:isEmbodiedBy ?m .
 ?m jolux:userFormat <https://fedlex.data.admin.ch/vocabulary/user-format/xml> ; jolux:isExemplifiedBy ?url . }"""


def http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 180) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "swiss-law-graph/0.1 (research; jonashertner)",
                                                          **(headers or {})})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(4 * (attempt + 1))


def sparql(query: str) -> list[dict]:
    body = urllib.parse.urlencode({"query": query}).encode()
    return json.loads(http(SPARQL, body, {"Accept": "application/sparql-results+json"}, 300))["results"]["bindings"]


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def note_target(note, eli_to_sr: dict[str, str]) -> str | None:
    """SR number a footnote names: rs attribute, eli/cc link, or 'SR n' in its text."""
    for ref in note.iter():
        if local(ref.tag) != "ref":
            continue
        if ref.get(FX + "rs"):
            return ref.get(FX + "rs").strip()
        href = ref.get("href", "")
        if "/eli/cc/" in href:
            base = re.sub(r"(/eli/cc/[^/#]+/[^/#]+).*", r"\1", href).replace("https://www.fedlex", "https://fedlex.data")
            if base in eli_to_sr:
                return eli_to_sr[base]
    m = SR_TEXT.search(squash("".join(note.itertext())))
    return m.group(1) if m else None


def parse_articles(s: str) -> list[str]:
    return parse_list(s)[0]


def parse_list(s: str) -> tuple[list[str], int]:
    """Article numbers in 'Artikel 95 Absatz 1, 97 Absatz 1 und 122 Absatz 1' (qualifiers dropped).

    After a qualifier keyword its first number is a paragraph (letter, figure). A later
    number is an article when a qualifier follows it or 'sowie' precedes it; otherwise
    after a plural keyword ("Absätze 1 und 3") it stays a paragraph, after a singular
    one ("Absatz 1 und 4") it is an article, and after an abbreviation ("Abs. 2 und 3")
    it stays a paragraph while it continues a short series.
    """
    out: list[str] = []
    s = s.replace("\u2013", "–").replace("-", "–")
    pos, mode, qtype, last_q, sep = 0, "art", None, None, None
    while pos < len(s):
        rest = s[pos:]
        m = re.match(r"(\s*,\s*|\s+(und|sowie|bis|oder)\s+|\s+)", rest)
        if m:
            w = (m.group(2) or ("," if "," in m.group(1) else None))
            if w:
                sep = w
            pos += m.end()
            continue
        q = QUAL.match(rest)
        if q:
            kw = q.group(0).strip()
            qtype = "plur" if kw in ("Absätze", "Buchstaben", "Ziffern", "Sätze") else (
                "abbr" if kw.endswith(".") else "sing")
            mode, last_q, sep = "qual0", None, None
            pos += q.end()
            continue
        m = re.match(rf"({NUM})(?:\s*–\s*({NUM}))?", rest)
        if m:
            a, b = (x.replace(" ", "") if x else x for x in m.groups())
            n = int(re.match(r"\d+", a).group())
            after = rest[m.end():]
            if mode == "qual0":                          # the value of the keyword just read
                mode, last_q = "qual", n
            elif mode == "qual":
                followed = bool(QUAL.match(re.sub(r"^[\s,]+", "", after)))
                if followed or sep == "sowie" or qtype == "sing" or last_q is None or (
                        qtype == "abbr" and not (last_q < n <= last_q + 3 and n <= 20)):
                    mode = "art"
                else:
                    last_q = n
            if mode == "art":
                out.append(f"{a}–{b}" if b else a)
            pos += m.end()
            sep = None
            continue
        if mode in ("qual", "qual0") and re.match(r"[a-z](?![a-zäöü])", rest):   # Bst. a, b
            mode = "qual"
            pos += 1
            continue
        break                                     # the act's name begins: done
    return out, pos


HIST_EQUIV = re.compile(r"(?:entspr\w*|[Hh]eute:?)\s+(?:heute\s+)?(?:(?:dem|den|der|die)\s+)?Art(?:ikeln|ikel|\.)?\s+(.+?)\s+(?:der|des|dieses)\b")
TAIL_SAME = re.compile(r"^[\s,]*(?:(?:sowie|und|und\s+auf|sowie\s+auf)\s+)?(?:des\s+)?(Schlusstitels?|Übergangsbestimmungen)?\s*$")


def is_basis_note(note: str) -> bool:
    """A footnote that gives the SR number of the act just named ("SR 830.1"), or its
    historical publication ("[BS 1 3]. Dieser Bestimmung entspricht …"). Editorial notes
    (amendments, renamed titles, publication) are not bases: the text runs on."""
    return bool(re.match(r"^(SR\s|\[(BS|AS|BBl)\b)", note))


def clause_articles(seg: str) -> tuple[str, list[str]]:
    """The words naming the basis and its article numbers, from the text since the last
    basis footnote: every article list up to the act's name ('Artikel 40, …, 103 sowie
    Schlusstitel Artikel 6a …'); a list followed by another act's name belongs to that act."""
    keys = list(ART_KW.finditer(seg))
    if not keys:
        return "", []
    pieces = []
    for k, m in enumerate(keys):
        stop = keys[k + 1].start() if k + 1 < len(keys) else len(seg)
        nums, end = parse_list(seg[m.end():stop])
        prefix = "SchlT " if re.search(r"Schlusstitels?\s*$", seg[:m.start()]) else (
            "ÜB " if re.search(r"Übergangsbestimmungen\s*$", seg[:m.start()]) else "")
        tail = seg[m.end() + end:stop]
        pieces.append((m.start(), [prefix + n for n in nums], tail))
    # the last list names the act of this footnote; earlier ones join it while nothing but
    # "sowie" / "Schlusstitel" separates them
    first = len(pieces) - 1
    while first > 0 and TAIL_SAME.match(pieces[first - 1][2].replace("des Schlusstitels", "")):
        first -= 1
    arts = [n for _, ns, _ in pieces[first:] for n in ns]
    return seg[pieces[first][0]:], arts


def preamble_bases(pre, eli_to_sr: dict[str, str]) -> tuple[str, str, list]:
    """Issuer, Ingress text and the bases, walking the Ingress in document order."""
    buf: list[str] = []          # text since the previous basis footnote
    plain: list[str] = []        # Ingress without footnotes
    bases, notes = [], []        # notes: editorial footnotes of the Ingress ("Fassung gemäss …")

    def walk(el):
        if local(el.tag) == "authorialNote":
            target = note_target(el, eli_to_sr)
            note = squash("".join(el.itertext()))
            if target and is_basis_note(note):
                seg = squash("".join(buf))
                buf.clear()
                clause, arts = clause_articles(seg)
                k = None
                for mm in ART_KW.finditer(seg):
                    k = k or mm
                lead = seg[:k.start()] if k else seg
                how = "exec" if re.search(r"(in Ausführung|in Vollzug)\s+(von|des|der|dieses)?\s*$", lead) else "basis"
                hist = note.startswith("[")
                eq = (EQUIV if target == "101" else HIST_EQUIV).search(note) if hist else None
                if hist and target == "101":
                    bases.append([target, parse_articles(eq.group(1)) if eq else [], clause, note,
                                  "aBV→BV" if eq else "aBV", how])
                elif hist and eq:
                    bases.append([target, parse_articles(eq.group(1)), clause, note, "hist→today", how])
                elif hist:
                    bases.append([target, [], clause, note, "hist", how])
                else:
                    bases.append([target, arts, clause, None, "text", how])
            elif not is_basis_note(note):
                notes.append(note[:240])
            # an editorial note: skip it, the clause continues after it
            if el.tail:
                buf.append(el.tail); plain.append(el.tail)
            return
        if el.text:
            buf.append(el.text); plain.append(el.text)
        for ch in el:
            if local(ch.tag) in ("p", "br"):
                buf.append(" "); plain.append(" ")
            walk(ch)
        if el.tail and el is not pre:
            buf.append(el.tail); plain.append(el.tail)

    walk(pre)
    text = squash("".join(plain)).replace(" ,", ",")
    issuer = text.split(",", 1)[0] if text else ""
    return issuer, text, bases, notes


def read_act(blob: bytes, eli_to_sr: dict[str, str]) -> dict:
    root = ET.fromstring(blob)
    out = {"title": "", "short": "", "date": "", "issuer": "", "ingress": "", "bases": [], "notes": [], "arts": []}
    pre = face = None
    for e in root.iter():
        t = local(e.tag)
        if t == "preface" and face is None:
            face = e
        elif t == "preamble" and pre is None:
            pre = e
    if face is not None:
        def plain(el):
            return squash("".join(x for x in _text_no_notes(el)))
        for e in face.iter():
            if local(e.tag) == "docTitle" and not out["title"]:
                out["title"] = plain(e)
        m = re.search(r"\(([^()]*?)\)\s*vom\b", plain(face))
        if m:
            out["short"] = m.group(1)
        m = re.search(r"\bvom\s+(\d{1,2}\.\s*\w+\s+\d{4})", plain(face))   # adoption date ("vom 19. Dezember 2008")
        if m:
            out["adopted"] = m.group(1)
    if pre is not None:
        out["issuer"], out["ingress"], out["bases"], out["notes"] = preamble_bases(pre, eli_to_sr)
    body = next((e for e in root.iter() if local(e.tag) == "body"), None)
    if body is not None:
        out["arts"] = [e.get("eId") for e in body.iter() if local(e.tag) == "article" and e.get("eId")]
    return out


def _text_no_notes(el):
    if local(el.tag) == "authorialNote":
        return
    if el.text:
        yield el.text
    for ch in el:
        if local(ch.tag) == "br":
            yield " "
        yield from _text_no_notes(ch)
        if ch.tail:
            yield ch.tail


def main() -> None:
    srs, eli_to_sr, uris = set(), {}, defaultdict(list)     # uris: SR -> [(in force, act URI)]
    for r in csv.DictReader(open(ROOT / "data/sr_eli.csv", encoding="utf-8")):
        a = r["act"].rstrip("/")
        eli_to_sr[a] = r["notation"]
        force = (r["inForce"] or "").endswith("/0")
        uris[r["notation"]].append((force, a))
        if force:
            srs.add(r["notation"])
    srs |= {l.strip() for l in open(ROOT / "pipeline/acts_to_validate.txt") if l.strip()}
    srs = sorted(srs)
    cache = ROOT / "build/fedlex_xml_urls.json"
    latest: dict[str, list[str]] = json.load(open(cache)) if cache.exists() else {}
    todo = [s for s in srs if s not in latest]
    # the act in force under that SR number; otherwise (a cited act no longer in force) all of them
    pick = {s: [a for f, a in uris[s] if f] or [a for _, a in uris[s]] for s in todo}
    flat = [(s, a) for s in todo for a in pick[s]]
    chunks = [flat[i:i + 40] for i in range(0, len(flat), 40)]

    def ask(chunk):
        return sparql(Q % (" ".join(f"<{a}>" for _, a in chunk), RUN_DATE))
    with ThreadPoolExecutor(max_workers=3) as ex:
        for k, rows in enumerate(ex.map(ask, chunks)):
            for b in rows:
                n, d, u = eli_to_sr[b["act"]["value"]], b["date"]["value"], b["url"]["value"]
                if n not in latest or d > latest[n][0]:
                    latest[n] = [d, u]
            if k % 10 == 0:
                print(f"sparql {k + 1}/{len(chunks)}", file=sys.stderr)
    cache.parent.mkdir(exist_ok=True)
    json.dump(latest, open(cache, "w"))

    def work(sr: str):
        d, u = latest[sr]
        try:
            rec = read_act(http(u), eli_to_sr)
            rec["date"] = d
            return sr, rec
        except Exception as e:  # recorded, never silently dropped
            return sr, {"date": d, "error": str(e)[:200]}

    result = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for k, (sr, rec) in enumerate(ex.map(work, sorted(latest))):
            result[sr] = rec
            if k % 500 == 0:
                print(f"xml {k}/{len(latest)}", file=sys.stderr)
    json.dump({"run_date": RUN_DATE, "source": "Fedlex consolidated DE XML: preface and Ingress (preamble)",
               "acts": result}, open(ROOT / "data/fedlex_basis.json", "w"), ensure_ascii=False, separators=(",", ":"))
    ok = [r for r in result.values() if "error" not in r]
    print(f"done: {len(result)} acts, {len(result) - len(ok)} failed, "
          f"{sum(1 for r in ok if r['bases'])} with a stated basis", file=sys.stderr)


if __name__ == "__main__":
    main()
