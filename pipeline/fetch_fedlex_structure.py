"""Fetch the internal structure of every cited federal act from Fedlex (DE/FR/IT).

Standard library only. For each SR number in pipeline/acts_to_validate.txt it
downloads the consolidated Akoma Ntoso XML applicable on RUN_DATE in German,
French and Italian and keeps, per act:
  levels    the structural units (book, part, title, chapter, marginal-title
            level, transitional block) with their number and heading, and parent
  articles  every article in document order: number, eId, enclosing level,
            own heading (if any), and whether the current text holds only a
            "repealed" note (rep)
The eId is identical across the three languages, so French and Italian headings
are joined onto the German skeleton by eId. The XML is discarded.

Output: data/fedlex_structure.json.gz
    {"run_date", "acts": {sr: {"date", "url", "levels": [...], "articles": [...]}}}
    level   = {"id": eId, "p": parent level index or -1, "num": {lang: ...}, "h": {lang: ...}}
    article = {"n": "41", "id": "art_41", "l": level index or -1, "rep": bool, "h": {lang: ...}}
"""
import gzip
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from inforce import RUN_DATE  # noqa: E402  (one run date: decision 39)
SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
LANGS = {"de": "DEU", "fr": "FRA", "it": "ITA"}

Q = """PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?notation ?date ?url WHERE {
 VALUES ?n { %s }
 ?act a jolux:ConsolidationAbstract ; jolux:classifiedByTaxonomyEntry ?c . ?c skos:notation ?notation .
 FILTER(str(?notation) = ?n)
 ?cons jolux:isMemberOf ?act ; jolux:dateApplicability ?date ; jolux:isRealizedBy ?expr .
 ?expr jolux:language <http://publications.europa.eu/resource/authority/language/%s> ; jolux:isEmbodiedBy ?m .
 ?m jolux:userFormat <https://fedlex.data.admin.ch/vocabulary/user-format/xml> ; jolux:isExemplifiedBy ?url .
 FILTER(?date <= "%s"^^xsd:date) }"""

CONTAINERS = {"book", "part", "title", "subtitle", "chapter", "subchapter", "section", "subsection",
              "level", "transitional", "division", "subdivision", "hcontainer", "conclusions"}
LATIN = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies)"


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL, data=data, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": "swiss-law-graph/0.1 (research; jonashertner)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["results"]["bindings"]


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


def text(el) -> str:
    """Text of an element without its footnotes (authorialNote)."""
    if el is None:
        return ""
    out = [el.text or ""]
    for ch in el:
        if local(ch.tag) != "authorialNote":
            out.append(text(ch))
        out.append(ch.tail or "")
    return re.sub(r"\s+", " ", "".join(out).replace("\xa0", " ")).strip()


def child(el, name: str):
    return next((c for c in el if local(c.tag) == name), None)


def art_number(num: str) -> str | None:
    m = re.match(r"(?:Art\.?|Artikel|Article|Articolo)?\s*(\d+)\s*([a-z]?\s*" + LATIN + r"|[a-z]|)(?![a-z])", num, re.I)
    return (m.group(1) + re.sub(r"\s+", "", m.group(2))).lower() if m else None


def parse(blob: bytes) -> tuple[list, list]:
    root = ET.fromstring(blob)
    body = next((e for e in root.iter() if local(e.tag) == "body"), None)
    levels, articles = [], []

    def walk(el, parent: int) -> None:
        for ch in el:
            t = local(ch.tag)
            if t in CONTAINERS:
                levels.append({"id": ch.get("eId", ""), "p": parent,
                               "num": text(child(ch, "num")), "h": text(child(ch, "heading"))})
                walk(ch, len(levels) - 1)
            elif t == "article":
                n = art_number(text(child(ch, "num")))
                body_parts = [c for c in ch if local(c.tag) not in ("num", "heading")]
                articles.append({"n": n, "id": ch.get("eId", ""), "l": parent,
                                 "rep": not body_parts, "h": text(child(ch, "heading"))})
            elif t not in ("num", "heading", "authorialNote"):
                walk(ch, parent)  # transparent wrappers (proviso, act, body)

    if body is not None:
        walk(body, -1)
    return levels, articles


def main() -> None:
    srs = [l.strip() for l in open(ROOT / "pipeline/acts_to_validate.txt") if l.strip()]
    out = ROOT / "data/fedlex_structure.json.gz"
    known = {}
    if "--missing" in sys.argv and out.exists():           # fetch only acts not yet in the file
        known = json.load(gzip.open(out))["acts"]
        srs = [s for s in srs if s not in known]
        print(f"{len(srs)} acts missing", file=sys.stderr)
    latest: dict[tuple[str, str], tuple[str, str]] = {}
    for lang, code in LANGS.items():
        for i in range(0, len(srs), 40):
            chunk = srs[i:i + 40]
            for b in sparql(Q % (" ".join(json.dumps(s) for s in chunk), code, RUN_DATE)):
                n, d, u = b["notation"]["value"], b["date"]["value"], b["url"]["value"]
                if (n, lang) not in latest or d > latest[(n, lang)][0]:
                    latest[(n, lang)] = (d, u)
        print(f"sparql {lang}: {sum(1 for k in latest if k[1] == lang)} acts with XML", file=sys.stderr)

    def work(sr: str):
        rec = {"levels": None, "articles": None}
        try:
            d, u = latest[(sr, "de")]
            levels, arts = parse(fetch(u))
            rec.update(date=d, url=u)
            for lv in levels:
                lv["num"], lv["h"] = {"de": lv["num"]}, {"de": lv["h"]}
            for a in arts:
                a["h"] = {"de": a["h"]} if a["h"] else {}
            by_id = {lv["id"]: lv for lv in levels} | {a["id"]: a for a in arts}
            for lang in ("fr", "it"):
                if (sr, lang) not in latest:
                    continue
                lv2, ar2 = parse(fetch(latest[(sr, lang)][1]))
                for x in lv2:
                    if x["id"] in by_id:
                        by_id[x["id"]]["num"][lang] = x["num"]
                        by_id[x["id"]]["h"][lang] = x["h"]
                for x in ar2:
                    if x["id"] in by_id and x["h"]:
                        by_id[x["id"]]["h"][lang] = x["h"]
            rec["levels"], rec["articles"] = levels, arts
        except Exception as e:  # recorded, never silently dropped
            rec["error"] = str(e)[:200]
        return sr, rec

    result = {**known, **{s: {"levels": None, "articles": None} for s in srs}}
    todo = sorted({sr for sr, lang in latest if lang == "de"})
    with ThreadPoolExecutor(max_workers=6) as ex:
        for k, (sr, rec) in enumerate(ex.map(work, todo)):
            result[sr] = rec
            if k % 50 == 0:
                print(f"xml {k}/{len(todo)}", file=sys.stderr)
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump({"run_date": RUN_DATE, "source": "Fedlex SPARQL + filestore, consolidated XML DE/FR/IT",
                   "acts": result}, f, ensure_ascii=False, separators=(",", ":"))
    ok = sum(1 for r in result.values() if r.get("articles"))
    print(f"done: {ok}/{len(result)} acts with structure -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
