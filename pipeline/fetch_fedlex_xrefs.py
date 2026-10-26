"""Legislative cross-references: which act's text refers to which other act.

Standard library only. Federal drafting gives the SR number of another act in a
footnote at the place the text names it ("… nach dem Versicherungsvertragsgesetz
vom 2. April 1908³" — ³ SR 221.229.1). Footnotes that only report an amendment
("Fassung gemäss …", "Eingefügt durch …") cite the amending act in AS, not an SR
number, and are not counted. A footnote inside an article heading (<num>) is an
amendment note and is skipped. Links to a consolidated act (eli/cc/…) are mapped
to their SR number via data/sr_eli.csv.

For every act in force (Fedlex enforcement status 0) plus every cited act, the
consolidated German XML applicable on RUN_DATE is read once.
Output: data/fedlex_xrefs.json
    {"run_date", "acts": {sr: {"date", "refs": [[article eId or "", target sr], ...]}}}
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = "2026-10-26"
SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
SR_NOTE = re.compile(r"^\s*SR\s+(0\.\d[\d.]*\d|\d[\d.]*\d|\d)\b")
SR_ANY = re.compile(r"\bSR\s+(0\.\d[\d.]*\d|\d[\d.]*\d|\d)\b")

Q = """PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?notation ?date ?url WHERE {
 VALUES ?n { %s }
 ?act a jolux:ConsolidationAbstract ; jolux:classifiedByTaxonomyEntry ?c . ?c skos:notation ?notation .
 FILTER(str(?notation) = ?n)
 ?cons jolux:isMemberOf ?act ; jolux:dateApplicability ?date ; jolux:isRealizedBy ?expr .
 ?expr jolux:language <http://publications.europa.eu/resource/authority/language/DEU> ; jolux:isEmbodiedBy ?m .
 ?m jolux:userFormat <https://fedlex.data.admin.ch/vocabulary/user-format/xml> ; jolux:isExemplifiedBy ?url .
 FILTER(?date <= "%s"^^xsd:date) }"""


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL, data=data, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": "swiss-law-graph/0.1 (research; jonashertner)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["results"]["bindings"]
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "swiss-law-graph/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def all_text(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def refs_of(blob: bytes, eli_to_sr: dict[str, str]) -> list[list[str]]:
    root = ET.fromstring(blob)
    body = next((e for e in root.iter() if local(e.tag) == "body"), root)
    out: list[list[str]] = []

    def scan(el, art: str, in_num: bool) -> None:
        t = local(el.tag)
        if t == "article":
            art = el.get("eId", "")
        if t == "num":
            in_num = True
        if t == "authorialNote" and not in_num:
            text = all_text(el)
            m = SR_NOTE.match(text)
            if m:
                for sr in SR_ANY.findall(text):
                    out.append([art, sr])
        if t == "ref" and not in_num:
            href = el.get("href", "")
            if "/eli/cc/" in href:
                base = re.sub(r"(/eli/cc/[^/#]+/[^/#]+).*", r"\1", href)
                sr = eli_to_sr.get(base)
                if sr:
                    out.append([art, sr])
        for ch in el:
            scan(ch, art, in_num)

    scan(body, "", False)
    return out


def main() -> None:
    srs, eli_to_sr = set(), {}
    for r in csv.DictReader(open(ROOT / "data/sr_eli.csv", encoding="utf-8")):
        eli_to_sr[r["act"].rstrip("/")] = r["notation"]
        if (r["inForce"] or "").endswith("/0"):
            srs.add(r["notation"])
    srs |= {l.strip() for l in open(ROOT / "pipeline/acts_to_validate.txt") if l.strip()}
    srs = sorted(srs)
    latest: dict[str, tuple[str, str]] = {}
    for i in range(0, len(srs), 40):
        chunk = srs[i:i + 40]
        for b in sparql(Q % (" ".join(json.dumps(s) for s in chunk), RUN_DATE)):
            n, d, u = b["notation"]["value"], b["date"]["value"], b["url"]["value"]
            if n not in latest or d > latest[n][0]:
                latest[n] = (d, u)
        if i % 400 == 0:
            print(f"sparql {i + len(chunk)}/{len(srs)}: {len(latest)} with XML", file=sys.stderr)

    def work(sr: str):
        d, u = latest[sr]
        try:
            refs = [r for r in refs_of(fetch(u), eli_to_sr) if r[1] != sr]
            return sr, {"date": d, "refs": refs}
        except Exception as e:  # recorded, never silently dropped
            return sr, {"date": d, "refs": None, "error": str(e)[:200]}

    result = {}
    todo = sorted(latest)
    with ThreadPoolExecutor(max_workers=6) as ex:
        for k, (sr, rec) in enumerate(ex.map(work, todo)):
            result[sr] = rec
            if k % 250 == 0:
                print(f"xml {k}/{len(todo)}", file=sys.stderr)
    json.dump({"run_date": RUN_DATE, "source": "Fedlex consolidated DE XML: SR-number footnotes and eli/cc links",
               "acts": result}, open(ROOT / "data/fedlex_xrefs.json", "w"), ensure_ascii=False, separators=(",", ":"))
    n_refs = sum(len(r["refs"] or []) for r in result.values())
    print(f"done: {len(result)} acts read, {n_refs} references", file=sys.stderr)


if __name__ == "__main__":
    main()
