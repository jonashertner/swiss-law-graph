"""Fetch the dates of every federal act and treaty on the site (Fedlex SPARQL), for the time view.

Standard library only. For each SR number of a federal act or treaty in docs/data/atlas.json, every
consolidation abstract that has carried it, with dateDocument (adoption; for a treaty its conclusion),
dateEntryInForce (for a treaty: in force for Switzerland) and dateNoLongerInForce. 08_web.py picks the
abstract whose ELI the site links to.

Output: data/fedlex_dates.json  {sr: [{"eli", "date", "in_force", "repealed"}, ...]}
Run after 08_web.py has written atlas.json (~3 min); then run 08_web.py again.
"""
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
Q = """PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?n ?act ?doc ?eif ?enlif WHERE {
 VALUES ?n { %s }
 ?act a jolux:ConsolidationAbstract ; jolux:classifiedByTaxonomyEntry ?c . ?c skos:notation ?notation .
 FILTER(str(?notation) = ?n)
 OPTIONAL { ?act jolux:dateDocument ?doc }
 OPTIONAL { ?act jolux:dateEntryInForce ?eif }
 OPTIONAL { ?act jolux:dateNoLongerInForce ?enlif }
}"""


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL, data=data, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": "swiss-law-graph/0.1 (research; jonashertner)"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.load(r)["results"]["bindings"]
        except Exception:                                  # noqa: BLE001 — retry on any network error
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    return []


def main() -> None:
    atlas = json.load(open(ROOT / "docs/data/atlas.json"))
    at = {k: j for j, k in enumerate(atlas["meta"]["fields"])}
    srs = sorted({r[2] for r in atlas["nodes"] if r[0] == "a" and not (r[at["ct"]] if at["ct"] < len(r) else None) and r[2]})
    out: dict[str, dict] = defaultdict(dict)
    for i in range(0, len(srs), 60):
        for b in sparql(Q % " ".join(json.dumps(s) for s in srs[i:i + 60])):
            v = {k: x["value"] for k, x in b.items()}
            a = out[v["n"]].setdefault(v["act"], {"eli": v["act"]})
            for k, key in (("doc", "date"), ("eif", "in_force"), ("enlif", "repealed")):
                if v.get(k):
                    a[key] = v[k][:10]
        print(f"{min(i + 60, len(srs))}/{len(srs)}", flush=True)
    res = {sr: sorted(d.values(), key=lambda a: a.get("in_force") or a.get("date") or "") for sr, d in sorted(out.items())}
    json.dump(res, open(ROOT / "data/fedlex_dates.json", "w"), ensure_ascii=False, indent=0)
    print(f"{len(res)} of {len(srs)} SR numbers with dates")


if __name__ == "__main__":
    main()
