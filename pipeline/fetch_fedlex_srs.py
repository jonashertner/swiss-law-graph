"""The SR numbers: data/sr_eli.csv (SR number → act → Fedlex status) and data/sr_taxonomy.csv (the SR tree with its
titles), so a refresh (decision 39) reads them again instead of keeping the copies of 2026-10-26.

sr_eli.csv comes from data/fedlex_history.json (fetch_fedlex_history.py first): one row per act with an SR number and
per status Fedlex gives it (temporary acts carry two, "0" and "3": both rows, as the copy of 2026-10-26 had them; an act
without status, an empty one). inforce.py reads it. sr_taxonomy.csv is the legal taxonomy (skos), one row per entry and
language: entry, notation, the notation of the entry above, language, title. Checked on 2026-10-27: the taxonomy query
gives the 37,240 rows of the copy; sr_eli.csv the copy's 13,403 rows plus the acts published since.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_fedlex_history import PRE, sparql  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ST = "https://fedlex.data.admin.ch/vocabulary/enforcement-status/"
Q_TAX = PRE + """SELECT ?c ?n ?bn ?l (LANG(?l) AS ?lang) WHERE {
 ?c skos:inScheme <https://fedlex.data.admin.ch/vocabulary/legal-taxonomy> ; skos:notation ?n ; skos:prefLabel ?l .
 OPTIONAL { ?c skos:broader ?b . ?b skos:notation ?bn } }"""


def srkey(s: str):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in s.replace("@", ".").split(".")]


def write(path: Path, head: list, rows: list) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(head)
        w.writerows(rows)
    tmp.replace(path)


def main() -> None:
    H = json.load(open(ROOT / "data/fedlex_history.json"))
    eli = []
    for act, a in H.items():
        if a.get("n"):
            for st in (a.get("statuses") or ([a["status"]] if a.get("status") is not None else [None])):
                eli.append((a["n"], act.rstrip("/"), "" if st is None else ST + str(st)))
    eli.sort(key=lambda r: (srkey(r[0]), r[1], r[2]))
    write(ROOT / "data/sr_eli.csv", ["notation", "act", "inForce"], eli)
    tax = sorted(((r["c"], r["n"], r.get("bn") or "", r["lang"], " ".join(r["l"].split())) for r in sparql(Q_TAX)),
                 key=lambda r: (srkey(r[1]), r[0], r[3]))
    if len(tax) < 30000:                                 # a partial answer must not replace the tree
        sys.exit(f"taxonomy: only {len(tax)} rows, kept the copy")
    write(ROOT / "data/sr_taxonomy.csv", ["c", "notation", "broader", "lang", "label"], tax)
    print(f"sr_eli.csv: {len(eli)} rows ({len({r[1] for r in eli})} acts); sr_taxonomy.csv: {len(tax)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
