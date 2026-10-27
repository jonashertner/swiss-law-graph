"""Every consolidated version of every federal act that Fedlex publishes as XML (the law repository, decision 36).

Fedlex SPARQL, one ELI segment at a time (as fetch_fedlex_history.py): for each consolidation (jolux:Consolidation,
"Stand" of an act) its act, the day it applies from and the last day it applied (dateApplicability,
dateEndApplicability), and per language (de, fr, it, rm, en) the URL of its XML file. Consolidations without an XML
file in any language are left out (Fedlex has XML from 2021 on, plus the version then in force).

Output: build/lawgit/fedlex_versions.json  {act ELI: [{"d": from, "e": to or None, "u": {lang: xml url}}, ...]}
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch_fedlex_history import PRE, Q_SEG, sparql  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/lawgit"
CACHE = OUT / "versions"
LANG = {"DEU": "de", "FRA": "fr", "ITA": "it", "ROH": "rm", "ENG": "en"}
Q = PRE + """SELECT ?act ?cons ?d ?e ?l ?url WHERE {
 ?cons a jolux:Consolidation ; jolux:isMemberOf ?act ; jolux:dateApplicability ?d ; jolux:isRealizedBy ?x .
 FILTER(STRSTARTS(STR(?act), "https://fedlex.data.admin.ch/eli/cc/%s/"))
 OPTIONAL { ?cons jolux:dateEndApplicability ?e }
 ?x jolux:language ?l ; jolux:isEmbodiedBy ?m .
 ?m jolux:userFormat <https://fedlex.data.admin.ch/vocabulary/user-format/xml> ; jolux:isExemplifiedBy ?url . }"""


def segment(seg: str) -> list[dict]:
    f = CACHE / f"{seg}.json"
    if f.exists():
        return json.load(open(f))
    rows = sparql(Q % seg)
    json.dump(rows, open(f, "w"))
    return rows


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    segs = sorted(r["seg"] for r in sparql(Q_SEG))
    acts: dict[str, dict[str, dict]] = {}
    for k, seg in enumerate(segs):
        for r in segment(seg):
            v = acts.setdefault(r["act"], {}).setdefault(r["cons"], {"d": r["d"][:10], "e": (r.get("e") or "")[:10] or None, "u": {}})
            lang = LANG.get(r["l"].rsplit("/", 1)[1])
            if lang:
                v["u"].setdefault(lang, r["url"])
        if k % 25 == 0:
            print(f"segment {k + 1}/{len(segs)} {seg}: {len(acts)} acts", file=sys.stderr)
    out = {a: sorted(vs.values(), key=lambda v: v["d"]) for a, vs in sorted(acts.items())}
    json.dump(out, open(OUT / "fedlex_versions.json", "w"), separators=(",", ":"))
    n = sum(len(v) for v in out.values())
    print(f"{len(out)} acts, {n} versions with XML, "
          + ", ".join(f"{lg} {sum(1 for vs in out.values() for v in vs if lg in v['u'])}" for lg in LANG.values()), file=sys.stderr)


if __name__ == "__main__":
    main()
