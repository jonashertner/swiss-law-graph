"""Fetch the article list of every cited federal act from Fedlex.

Standard library only (runs anywhere with python3). For each SR number in
pipeline/acts_to_validate.txt it asks the Fedlex SPARQL endpoint for the
consolidated German XML applicable on RUN_DATE, downloads it, extracts the
article numbers (Akoma Ntoso <article> elements, <num> text) and discards the
XML. Output: data/fedlex_articles.json
    {sr: {"date": "YYYY-MM-DD", "url": ..., "articles": ["1", "2", "6a", "6bis", ...]}}
Acts with no XML consolidation (PDF-only, older treaties) get {"articles": null}.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import artnum

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from inforce import RUN_DATE  # noqa: E402  (one run date: decision 39)
SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"

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

ART_RE = re.compile(r"<article\b[^>]*>\s*<num\b[^>]*>(.*?)</num>", re.S)
TAG_RE = re.compile(r"<[^>]+>")


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL, data=data, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": "swiss-law-graph/0.1 (research; jonashertner)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["results"]["bindings"]


NOTE_RE = re.compile(r"<authorialNote\b.*?</authorialNote>", re.S)


def norm_article(num_html: str) -> list[str]:
    """Numbers named by an article's <num>. Footnotes are dropped first ("Art. 4" +
    note "Aufgehoben ..." must not read "4aufgehoben"); tags are then removed
    without a space, because Fedlex splits digits ("<b>Art. 25</b><b>7</b>" = 257)
    as well as suffixes ("6<sup>bis</sup>"). Blocks ("Art. 274–274g") are expanded."""
    return artnum.parse_num(TAG_RE.sub("", NOTE_RE.sub("", num_html)))


def fetch_articles(url: str) -> list[str]:
    req = urllib.request.Request(url, headers={"User-Agent": "swiss-law-graph/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                xml = r.read().decode("utf-8", "replace")
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)
    out, seen = [], set()
    for m in ART_RE.finditer(xml):
        for a in norm_article(m.group(1)):
            if a not in seen:
                seen.add(a)
                out.append(a)
    return out


def main() -> None:
    srs = [l.strip() for l in open(ROOT / "pipeline/acts_to_validate.txt") if l.strip()]
    latest: dict[str, tuple[str, str]] = {}
    for i in range(0, len(srs), 40):
        chunk = srs[i:i + 40]
        rows = sparql(Q % (" ".join(json.dumps(s) for s in chunk), RUN_DATE))
        for b in rows:
            n, d, u = b["notation"]["value"], b["date"]["value"], b["url"]["value"]
            if n not in latest or d > latest[n][0]:
                latest[n] = (d, u)
        print(f"sparql {i + len(chunk)}/{len(srs)}: {len(latest)} with XML", file=sys.stderr)

    result: dict[str, dict] = {s: {"articles": None} for s in srs}

    def work(sr: str):
        d, u = latest[sr]
        try:
            return sr, {"date": d, "url": u, "articles": fetch_articles(u)}
        except Exception as e:  # recorded, never silently dropped
            return sr, {"date": d, "url": u, "articles": None, "error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=6) as ex:
        for k, (sr, rec) in enumerate(ex.map(work, sorted(latest))):
            result[sr] = rec
            if k % 50 == 0:
                print(f"xml {k}/{len(latest)}", file=sys.stderr)
    out = ROOT / "data/fedlex_articles.json"
    json.dump({"run_date": RUN_DATE, "source": "Fedlex SPARQL + filestore, consolidated DE XML",
               "acts": result}, open(out, "w"), ensure_ascii=False)
    ok = sum(1 for r in result.values() if r.get("articles"))
    print(f"done: {ok}/{len(srs)} acts with article lists -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
