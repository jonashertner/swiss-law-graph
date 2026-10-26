"""Step 3a — the tree the map is laid out on (position = place in the SR).

  root
  ├─ Landesrecht (SR 1–9)          official Fedlex legal taxonomy, every level
  ├─ Völkerrecht (SR 0.1–0.9)      idem
  └─ Kantonales Recht              canton -> cantonal act nodes from the corpus
Federal acts shown: every act in force (Fedlex enforcement status 0) and every
act cited at least once (including earlier acts sharing an SR number, placed
next to their successor). An act that has taxonomy children (an ordinance with
its sub-ordinances) becomes a group holding the act and its children.
Cantonal act nodes cited by fewer than MIN_CANTONAL decisions are pooled into
one node per canton. Children are ordered by SR number (Dewey order); cantonal
acts by number of citing decisions.

Leaf value = citing decisions + 1 (so an uncited act still has an area).
Output: build/hierarchy.json
"""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
MIN_CANTONAL = 5
CANTONS = "ZH BE LU UR SZ OW NW GL ZG FR SO BS BL SH AR AI SG GR AG TG TI VD VS NE GE JU".split()
GROUP_LABEL = {
    "CH": {"de": "Landesrecht", "fr": "Droit interne", "it": "Diritto interno", "en": "Domestic law"},
    "INT": {"de": "Völkerrecht", "fr": "Droit international", "it": "Diritto internazionale",
            "en": "International law"},
    "KT": {"de": "Kantonales Recht", "fr": "Droit cantonal", "it": "Diritto cantonale", "en": "Cantonal law"},
}


def dewey(n: str) -> str:
    return n.replace(".", "")


def main() -> None:
    labels: dict[str, dict] = defaultdict(dict)
    parent: dict[str, str | None] = {}
    for r in csv.DictReader(open(ROOT / "data/sr_taxonomy.csv", encoding="utf-8")):
        labels[r["notation"]][r["lang"]] = r["label"]
        parent[r["notation"]] = r["broader"] or None
    status = {}
    for r in csv.DictReader(open(ROOT / "data/sr_eli.csv", encoding="utf-8")):
        s = (r["inForce"] or "").rsplit("/", 1)[-1]
        status[r["notation"]] = min(status.get(r["notation"], "9"), s or "9")
    is_act = set(status)

    c = duckdb.connect()
    dec = dict(c.sql(f"select act_id, decisions from '{BUILD}/graph/acts.parquet'").fetchall())
    nodes = json.load(open(BUILD / "act_nodes.json"))

    # Federal acts to show.
    shown: dict[str, str] = {}          # act_id -> taxonomy notation it sits at
    for sr in is_act:
        if status[sr] == "0" and sr in parent:
            shown["SR " + sr] = sr
    for act_id, nd in nodes.items():
        if nd["sr"] in parent:
            shown[act_id] = nd["sr"]
    # Taxonomy nodes holding shown acts (and their ancestors).
    keep = set()
    for sr in shown.values():
        n = sr
        while n:
            keep.add(n)
            n = parent.get(n)
    kids: dict[str | None, list] = defaultdict(list)
    for n in keep:
        kids[parent.get(n)].append(n)

    def act_leaf(act_id: str) -> dict:
        return {"id": act_id, "kind": "act", "value": dec.get(act_id, 0) + 1, "decisions": dec.get(act_id, 0)}

    at: dict[str, list] = defaultdict(list)
    for a, sr in shown.items():
        at[sr].append(a)

    def build(n: str) -> dict:
        acts_here = sorted(at.get(n, []), key=lambda a: (a.count("@") == 0, a))
        children = [build(k) for k in sorted(kids.get(n, []), key=dewey)]
        if n in is_act or acts_here:
            leaves = [act_leaf(a) for a in acts_here]
            # earlier acts first, then the current one: they sit side by side
            if not children:
                return leaves[0] if len(leaves) == 1 else {"id": "G " + n, "kind": "group", "sr": n,
                                                            "children": leaves}
            return {"id": "G " + n, "kind": "group", "sr": n, "children": leaves + children}
        return {"id": "A " + n, "kind": "area", "sr": n, "children": children}

    roots = sorted(kids[None], key=dewey)
    ch = {"id": "CH", "kind": "domain", "children": [build(r) for r in roots if not r.startswith("0")]}
    intl = {"id": "INT", "kind": "domain", "children": [build(r) for r in roots if r.startswith("0")]}

    # Cantonal acts.
    by_canton: dict[str, list] = defaultdict(list)
    for act_id, d in dec.items():
        if not act_id.startswith("SR "):
            by_canton[act_id.split(" ", 1)[0]].append((act_id, d))
    kt = {"id": "KT", "kind": "domain", "children": []}
    for k in CANTONS + sorted(set(by_canton) - set(CANTONS)):
        items = sorted(by_canton.get(k, []), key=lambda x: (-x[1], x[0]))
        if not items:
            continue
        big = [a for a in items if a[1] >= MIN_CANTONAL]
        small = [a for a in items if a[1] < MIN_CANTONAL]
        children = [{"id": a, "kind": "act", "value": d + 1, "decisions": d} for a, d in big]
        if small:
            children.append({"id": f"{k} *", "kind": "bucket", "codes": len(small),
                             "value": sum(d for _, d in small) + 1, "decisions": sum(d for _, d in small)})
        kt["children"].append({"id": "K " + k, "kind": "canton", "canton": k, "children": children})

    tree = {"id": "root", "kind": "root", "children": [ch, intl, kt]}
    json.dump(tree, open(BUILD / "hierarchy.json", "w"), ensure_ascii=False)
    count = defaultdict(int)

    def walk(t):
        count[t["kind"]] += 1
        for x in t.get("children", []):
            walk(x)
    walk(tree)
    print(dict(count))


if __name__ == "__main__":
    main()
