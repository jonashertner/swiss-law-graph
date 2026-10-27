"""Fetch the federal history (Fedlex SPARQL): every act the federal compilations have carried in the SR.

Standard library only. For each consolidation abstract (17,319 on 2026-10-27): the SR number it was classified
under and the one it carried (historicalLegalId), adoption (dateDocument), entry into force, repeal
(dateNoLongerInForce), in-force status (0 in force, 1 no longer published in the SR, 2 obsolete, 3 no longer in
force, 4 not yet in force), document type (Bundesgesetz, Verordnung des Bundesrates, Departementsverordnung, …,
treaty), and title and short title per language. The record reaches back to the cleaned-up collection of 1948
(acts repealed from the 1940s on). A temporary act that lapsed has no repeal date but an end of applicability
(dateEndApplicability, the last day it applied; on the abstract or on its act in the AS).

Output: data/fedlex_history.json  {eli: {"n", "hid", "date", "in_force", "repealed", "end", "status", "type",
                                         "title": {lang}, "abbr": {lang}}}
Run when refreshing data (~10 min); then 08_web.py and layout/net.mjs.
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from refresh import fresh

ROOT = Path(__file__).resolve().parents[1]
SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
PRE = """PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
"""
# one ELI segment at a time ("eli/cc/1950/…"): paging with OFFSET over all 17,319 answers HTTP 500 beyond ~9,000
PAGE = '?a a jolux:ConsolidationAbstract . FILTER(STRSTARTS(STR(?a), "https://fedlex.data.admin.ch/eli/cc/%s/"))'
Q_SEG = PRE + """SELECT ?seg (COUNT(DISTINCT ?a) AS ?n) WHERE { ?a a jolux:ConsolidationAbstract .
 BIND(STRBEFORE(STRAFTER(STR(?a), "/eli/cc/"), "/") AS ?seg) } GROUP BY ?seg"""
CACHE = ROOT / "build/fedlex_history"
Q_META = PRE + """SELECT DISTINCT ?a ?n ?hid ?doc ?eif ?enlif ?st ?ty WHERE { %s
 OPTIONAL { ?a jolux:classifiedByTaxonomyEntry ?c . ?c skos:notation ?n }
 OPTIONAL { ?a jolux:historicalLegalId ?hid }
 OPTIONAL { ?a jolux:dateDocument ?doc }
 OPTIONAL { ?a jolux:dateEntryInForce ?eif }
 OPTIONAL { ?a jolux:dateNoLongerInForce ?enlif }
 OPTIONAL { ?a jolux:inForceStatus ?st }
 OPTIONAL { ?a jolux:typeDocument ?ty } }"""
# the end of applicability a temporary act states ("gilt bis 31. Dezember 1974"): on the abstract, else on its AS act
Q_END = PRE + """SELECT DISTINCT ?a ?e ?oe WHERE { %s
 OPTIONAL { ?a jolux:dateEndApplicability ?e }
 OPTIONAL { ?a jolux:basicAct ?b . ?b jolux:dateEndApplicability ?oe }
 FILTER(BOUND(?e) || BOUND(?oe)) }"""
Q_TITLE = PRE + """SELECT DISTINCT ?a ?lang ?t ?s WHERE { %s
 ?a jolux:isRealizedBy ?e . ?e jolux:language ?l ; jolux:title ?t .
 OPTIONAL { ?e jolux:titleShort ?s }
 BIND(replace(str(?l), "^.*/", "") AS ?lang) }"""
LANG = {"DEU": "de", "FRA": "fr", "ITA": "it", "ROH": "rm", "ENG": "en"}


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL, data=data, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": "swiss-law-graph/0.1 (research; jonashertner)"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return [{k: v["value"] for k, v in b.items()} for b in json.load(r)["results"]["bindings"]]
        except Exception:                                  # noqa: BLE001 — retry on any network error
            if attempt == 4:
                raise
            time.sleep(2 ** (attempt + 1))
    return []


def segment(seg: str) -> dict[str, dict]:
    f = CACHE / f"{seg}.json"
    if fresh(f):
        return json.load(open(f))
    acts: dict[str, dict] = {}
    for v in sparql(Q_META % (PAGE % seg)):
        a = acts.setdefault(v["a"], {"title": {}, "abbr": {}})
        for k, key in (("n", "n"), ("hid", "hid"), ("doc", "date"), ("eif", "in_force"), ("enlif", "repealed")):
            if v.get(k) and not a.get(key):
                a[key] = v[k][:10] if key in ("date", "in_force", "repealed") else v[k]
        if v.get("st"):
            a["status"] = int(v["st"].rsplit("/", 1)[1])
        if v.get("ty"):
            a["type"] = int(v["ty"].rsplit("/", 1)[1])
    for v in sparql(Q_TITLE % (PAGE % seg)):
        a = acts.setdefault(v["a"], {"title": {}, "abbr": {}})
        lg = LANG.get(v.get("lang", ""), v.get("lang", ""))
        a["title"].setdefault(lg, " ".join(v["t"].split()))
        if v.get("s"):
            a["abbr"].setdefault(lg, " ".join(v["s"].split()))
    CACHE.mkdir(parents=True, exist_ok=True)
    json.dump(acts, open(f, "w"), ensure_ascii=False)
    return acts


def ends(seg: str) -> dict[str, str]:
    f = CACHE / f"{seg}.end.json"
    if fresh(f):
        return json.load(open(f))
    out: dict[str, str] = {}
    for v in sparql(Q_END % (PAGE % seg)):
        if v.get("e"):
            out[v["a"]] = v["e"][:10]
        elif v.get("oe"):
            out.setdefault(v["a"], v["oe"][:10])
    CACHE.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(f, "w"))
    return out


def main() -> None:
    segs = sorted((r["seg"], int(r["n"])) for r in sparql(Q_SEG))
    acts: dict[str, dict] = {}
    for k, (seg, n) in enumerate(segs):
        got = segment(seg)
        for a, e in ends(seg).items():
            if a in got:
                got[a]["end"] = e
        acts.update(got)
        if len(got) != n:
            print(f"segment {seg}: {len(got)} of {n}", flush=True)
        if k % 20 == 0:
            print(f"{k + 1}/{len(segs)} segments, {len(acts)} acts", flush=True)
    json.dump(dict(sorted(acts.items())), open(ROOT / "data/fedlex_history.json", "w"), ensure_ascii=False, indent=0)
    rep = sum(1 for a in acts.values() if a.get("repealed"))
    end = sum(1 for a in acts.values() if a.get("end") and not a.get("repealed"))
    print(f"{len(acts)} acts, {rep} with a repeal date, {end} more with an end of applicability, "
          f"{sum(1 for a in acts.values() if a.get('n') or a.get('hid'))} with an SR number")


if __name__ == "__main__":
    main()
