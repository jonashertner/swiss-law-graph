"""Fetch every act that has ever carried a cited SR number (Fedlex SPARQL).

Standard library only. An SR number is reused when an act is totally revised
or replaced (OG 1943 -> BGG 2005 under 173.110, ELG 1965 -> ELG 2006 under
831.30): 412 of the 830 cited SR numbers have carried more than one act.
Step 1 needs, for each SR number, every act with its dates and abbreviations
to decide which act a reference means.

Output: data/fedlex_acts.json
    {sr: [{"eli", "date" (dateDocument), "in_force" (dateEntryInForce),
           "repealed" (dateNoLongerInForce), "title": {lang}, "abbr": {lang}}, ...]}
"""
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
LANG = {"DEU": "de", "FRA": "fr", "ITA": "it", "ENG": "en", "ROH": "rm"}

Q = """PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?n ?act ?doc ?eif ?enlif ?lang ?title ?short WHERE {
 VALUES ?n { %s }
 ?act a jolux:ConsolidationAbstract ; jolux:classifiedByTaxonomyEntry ?c . ?c skos:notation ?notation .
 FILTER(str(?notation) = ?n)
 OPTIONAL { ?act jolux:dateDocument ?doc }
 OPTIONAL { ?act jolux:dateEntryInForce ?eif }
 OPTIONAL { ?act jolux:dateNoLongerInForce ?enlif }
 OPTIONAL { ?act jolux:isRealizedBy ?e . ?e jolux:language ?l ; jolux:title ?title .
            OPTIONAL { ?e jolux:titleShort ?short }
            BIND(replace(str(?l), "^.*/", "") AS ?lang) }
}"""


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL, data=data, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": "swiss-law-graph/0.1 (research; jonashertner)"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["results"]["bindings"]


def main() -> None:
    srs = sorted({l.strip() for l in open(ROOT / "pipeline/acts_to_validate.txt") if l.strip()}
                 | set(sys.argv[1:]))
    acts: dict[str, dict] = defaultdict(lambda: {"title": {}, "abbr": {}})
    owner: dict[str, set] = defaultdict(set)
    for i in range(0, len(srs), 50):
        for b in sparql(Q % " ".join(json.dumps(s) for s in srs[i:i + 50])):
            v = {k: x["value"] for k, x in b.items()}
            a = acts[v["act"]]
            owner[v["n"]].add(v["act"])
            a["eli"] = v["act"]
            for k, key in (("doc", "date"), ("eif", "in_force"), ("enlif", "repealed")):
                if v.get(k):
                    a[key] = v[k][:10]
            lang = LANG.get(v.get("lang", ""))
            if lang:
                a["title"][lang] = v["title"]
                if v.get("short"):
                    a["abbr"][lang] = v["short"]
        print(f"{min(i + 50, len(srs))}/{len(srs)}", file=sys.stderr)
    out = {sr: sorted((acts[e] for e in owner[sr]), key=lambda a: (a.get("in_force") or "", a["eli"]))
           for sr in srs if sr in owner}
    json.dump({"source": "Fedlex SPARQL (jolux:ConsolidationAbstract by legal-taxonomy notation)",
               "acts": out}, open(ROOT / "data/fedlex_acts.json", "w"), ensure_ascii=False, indent=0)
    multi = sum(1 for v in out.values() if len(v) > 1)
    print(f"done: {len(out)} SR numbers, {multi} carried by more than one act", file=sys.stderr)


if __name__ == "__main__":
    main()
