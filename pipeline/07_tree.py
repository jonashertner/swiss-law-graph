"""Step 7 — the Stufenbau: federal law in force as a tree rooted in the Constitution.

Every federal act names, in its Ingress, who enacts it and on what basis
(data/fedlex_basis.json, from fetch_fedlex_basis.py). That gives a directed graph
"act → the provisions it rests on". This step turns it into a tree a reader can see:

  Bundesverfassung (SR 101)
    its titles, chapters, sections, articles (data/fedlex_structure.json.gz)
      acts of the Federal Assembly resting on an article     (level 1)
        ordinances of the Federal Council or a federal court  (level 2)
          ordinances of a department, office or other body    (level 3)

The level is the enacting authority named in the Ingress, not the depth in the tree:
an ordinance resting directly on the Constitution sits on level 2 under a BV article.

Below the federal floors, because federal law takes precedence over cantonal law
(Art. 49 BV), two cantonal floors:
          the 26 cantonal constitutions under Art. 51 BV          (level 4)
            each canton's acts under its constitution              (level 5)
Art. 51 BV obliges each canton to give itself a constitution, which the Federal
Assembly guarantees: that is the constitutional link, not an Ingress. The cantonal
acts are those cited by decisions (cantonal texts were not read): their place under
their canton is exact, the article they rest on is not known. The cantons share the
full circle, in SR order, each by the room its acts need.

Parent of an act (its place in the tree) = one of its stated bases, chosen as:
  1. bases on a higher level than the act itself (an ordinance under its act), the
     nearest such level first (an ordinance under its act rather than under the BV);
  2. then the longest common SR prefix (KVV 832.102 under KVG 832.10, not ATSG 830.1);
  3. then the order of the Ingress.
A basis on the Constitution attaches to the first article named. Every other stated
basis is kept as a secondary link. Acts based on the 1874 Constitution attach to the
article Fedlex names as today's equivalent; without one, to the node "BV 1874".
Bases on an international treaty hang under that treaty (a sector of its own); acts
whose Ingress names no basis in the tree form the sector "no basis stated".
Nothing is inferred beyond the text.

Layout: radial. Each node gets an angle span large enough for its own sphere and for
its children's spans; the radius of a ring and its height follow the level. Sphere
radius ~ sqrt(citing decisions + 400), so that an act no decision cites stays visible.

Output: site/data/tree.json (nodes, positions, bases) and site/data/ingress.json
(the verbatim Ingress of each act, loaded when the reader opens one).
"""
import gzip
import json
import math

import duckdb
import re
from collections import defaultdict
from pathlib import Path

from artnum import LATIN, expand_range, sort_key, split
from cantons import CANTON_CONSTITUTION

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site" / "data"
LV_R = {"apex": 0.0, "title": 0.055, "chapter": 0.095, "section": 0.135, "bvart": 0.18,
        1: 0.42, 2: 0.71, 3: 1.0, 4: 1.18, 5: 1.45}
LV_Y = {"apex": 0.95, "crown": 0.86, 1: 0.58, 2: 0.29, 3: 0.0, 4: -0.24, 5: -0.52}
COURTS = re.compile(r"^(Das|Die|Der)\s+(Schweizerische\s+)?(Bundesgericht|Bundesverwaltungsgericht|Bundesstrafgericht|"
                    r"Bundespatentgericht|Verwaltungskommission|Militärkassationsgericht|Präsidentenkonferenz)")


MARK = re.compile(r",?\s*(gestützt auf|in Ausführung|in Anwendung|in Vollzug|nach Einsicht|verordnet:|beschliesst:|erlässt\b)")


def issuer_of(rec: dict) -> str:
    """The enacting authority: the words before the first 'gestützt auf' / 'verordnet:' of
    the Ingress, from their last capitalised article ('Das Staatssekretariat …'), since
    some Ingresses open with other matter (a profession code, an entry-into-force note)."""
    ing = rec.get("ingress", "")
    m = MARK.search(ing)
    head = ing[:m.start()] if m else rec.get("issuer", "")
    starts = [x.start() for x in re.finditer(r"\b(?:Die|Der|Das)\s+(?=\w)", head)]
    return head[starts[-1]:].strip(" ,") if starts else ""


def level_of(rec: dict) -> tuple[int, str]:
    """Level (1–3) from the enacting authority named in the Ingress; title as fallback."""
    iss = issuer_of(rec)
    if re.match(r"^Die Bundesversammlung\b", iss):
        return 1, "Bundesversammlung"
    if re.match(r"^Der (Schweizerische )?Bundesrat\b", iss):
        return 2, "Bundesrat"
    if COURTS.match(iss):
        return 2, "Gericht"
    if iss and re.match(r"^(Das|Die|Der)\s", iss) and not re.match(r"^(Die Unterzeichner|Die Vertragsparteien|Die Hohen)", iss):
        return 3, "Departement, Amt oder andere Behörde"
    t = rec.get("title", "")
    if re.match(r"^(Bundesgesetz|Bundesbeschluss|Verordnung der Bundesversammlung|Geschäftsreglement)", t):
        return 1, "Titel"
    if re.match(r"^(Verordnung|Reglement|Weisung)\w*\s+(des|der)\s+(?!Bundesrates)", t):   # "Verordnung des SBFI …"
        return 3, "Titel"
    if re.match(r"^Verordnung\b", t):
        return 2, "Titel"
    return 3, "Titel"


LATIN_NUM = re.compile(r"\d+[a-z]?(?:" + "|".join(LATIN) + r")$")


def cites_1874(rec: dict, nums: list[str]) -> bool:
    """A clause citing the Constitution with a plain 'SR 101' footnote means the text of
    1874 when the act was adopted before 2000 and its Ingress has not been revised since,
    or when it names an article numbered the 1874 way (34ter, 64bis: today's Constitution
    has no such numbers)."""
    if any(LATIN_NUM.match(n.split("–")[0]) for n in nums):
        return True
    m = re.search(r"(\d{4})$", rec.get("adopted", ""))
    if not m or int(m.group(1)) >= 2000:
        return False
    for n in rec.get("notes", []):
        if re.match(r"(Fassung|Eingefügt)", n) and any(int(y) >= 2000 for y in re.findall(r"\b(?:19|20)\d\d\b", n)):
            return False                  # Ingress revised since 2000: today's numbering
    return True


def eid_of(num: str) -> str | None:
    p = split(num)
    if not p:
        return None
    return "art_" + "_".join([str(p[0])] + ([p[1]] if p[1] else []) + ([p[2]] if p[2] else []))


def main() -> None:
    basis = json.load(open(ROOT / "data/fedlex_basis.json"))
    acts = basis["acts"]
    core = json.load(open(SITE / "core.json"))
    cidx = {n["i"]: k for k, n in enumerate(core["nodes"])}
    art_n = {a: n for a, n in duckdb.sql(
        f"select art, decisions from '{ROOT}/build/graph/articles.parquet' where act_id = 'SR 101'").fetchall()}
    struct = json.load(gzip.open(ROOT / "data/fedlex_structure.json.gz"))["acts"]["101"]

    # ---- members: federal acts in force (SR not 0.x), on the map, with a readable text
    members, excluded = {}, defaultdict(int)
    for sr, rec in acts.items():
        if sr == "101" or sr.startswith("0.") or "error" in rec:
            continue
        if sr.startswith("131.2"):          # cantonal constitutions (guaranteed, Art. 51 BV): cantonal law
            excluded["cantonal_constitutions"] += 1
            continue
        if f"SR {sr}" not in cidx:
            continue
        members[sr] = rec
    levels = {sr: level_of(r) for sr, r in members.items()}

    # ---- tree nodes
    ids, kind, parent, core_i, lv, info = [], [], [], [], [], []

    def add(id_, k, p, ci=-1, level=None, extra=None):
        ids.append(id_); kind.append(k); parent.append(p); core_i.append(ci); lv.append(level); info.append(extra or {})
        return len(ids) - 1

    root = add("SR 101", "act", -1, cidx["SR 101"], "apex")
    # the Constitution's own structure
    lvl_node = {}
    for k, L in enumerate(struct["levels"]):
        depth = L["id"].count("/")
        k_ = ("title", "chapter", "section")[min(depth, 2)]
        p = root if L["p"] < 0 else lvl_node[L["p"]]
        lvl_node[k] = add("BV:" + L["id"], k_, p, -1, k_, {"num": L["num"], "h": L["h"]})
    bvart = {}
    for a in struct["articles"]:
        p = lvl_node[a["l"]] if a["l"] is not None and a["l"] >= 0 else root
        bvart[a["id"]] = add("BV:" + a["id"], "bvart", p, -1, "bvart", {"n": a["n"], "h": a.get("h") or {}, "rep": a.get("rep", False)})
    bv_order = [a["id"] for a in struct["articles"]]
    abv = add("BV:1874", "abv", root, -1, "bvart", {})                    # 1874 Constitution, no equivalent given
    intl = add("TREE:int", "tgroup", root, -1, "bvart", {})               # bases in international treaties
    nob = add("TREE:none", "tgroup", root, -1, "bvart", {})               # no basis stated in the Ingress

    stats = defaultdict(int)
    act_node = {sr: add(f"SR {sr}", "act", None, cidx[f"SR {sr}"], levels[sr][0]) for sr in sorted(members, key=sort_srkey)}
    # cantonal floors
    kv_node = {}
    for ct, sr in CANTON_CONSTITUTION.items():
        if f"SR {sr}" in cidx:
            kv_node[ct] = add(f"SR {sr}", "act", bvart["art_51"], cidx[f"SR {sr}"], 4, {"ct": ct})
    cantonal = defaultdict(list)
    for k, n in enumerate(core["nodes"]):
        if n["k"] in ("act", "bucket") and n.get("c") in kv_node:
            cantonal[n["c"]].append(add(n["i"], n["k"], kv_node[n["c"]], k, 5, {"ct": n["c"]}))
    stats["cantonal_acts"] = sum(len(v) for v in cantonal.values())
    tde = json.load(open(SITE / "titles.de.json"))
    stats["cantonal_acts_with_title"] = sum(1 for v in cantonal.values() for t in v if tde[core_i[t]])
    treaty_node = {}

    # ---- bases: resolve targets and articles
    resolved = {}      # sr -> list of [target node, [eIds], clause, how, via, found]
    for sr, rec in members.items():
        out = []
        for b in rec.get("bases", []):
            tgt, nums, clause, note, via, how = (b + [None, None])[:6]
            stats["bases"] += 1
            if tgt == sr:
                continue
            if tgt == "101":
                stats["bases_bv"] += 1
                if via == "text" and cites_1874(rec, nums):
                    via = "aBV"
                    stats["bases_abv_plain_footnote"] += 1
                if via == "aBV":
                    out.append([abv, [], clause, how, via, 1]); stats["bases_abv_no_equivalent"] += 1
                    continue
                if via == "aBV→BV":
                    stats["bases_abv_mapped"] += 1
                eids, found = [], 1
                for n in nums:
                    if "–" in n:
                        a_, b_ = n.split("–")
                        e1, e2 = eid_of(a_), eid_of(b_)
                        if e1 in bv_order and e2 in bv_order:
                            eids += bv_order[bv_order.index(e1):bv_order.index(e2) + 1]
                        else:
                            found = 0
                    else:
                        e = eid_of(n)
                        if e in bvart:
                            eids.append(e)
                        else:
                            found = 0
                if not nums:
                    stats["bases_bv_no_article"] += 1
                if not found:
                    stats["bases_bv_article_not_found"] += 1
                out.append([bvart[eids[0]] if eids else root, eids, clause, how, via, found])
            elif tgt in members:
                alist = acts[tgt].get("arts") or []
                tarts = set(alist)
                eids, found = [], 1
                for n in nums:
                    block = None
                    if n.startswith(("SchlT ", "ÜB ")):              # final / transitional provisions
                        block, n = n.split(" ", 1)
                    parts = n.split("–")
                    es = [eid_of(x) for x in parts]
                    if block:
                        es = [next((a for a in alist if a.startswith("disp_") and a.endswith("/" + e)), e) if e else e for e in es]
                    if len(parts) == 2 and all(es):
                        rng = [eid_of(x) for x in expand_range(*parts)]
                        eids += [e for e in rng if e in tarts]
                        found &= int(es[0] in tarts and es[1] in tarts)
                    elif es[0]:
                        eids.append(es[0])
                        found &= int(es[0] in tarts)
                if nums and not found:
                    stats["bases_article_not_in_current_text"] += 1
                out.append([act_node[tgt], eids, clause, how, via, found])
            elif tgt.startswith("0."):
                stats["bases_treaty"] += 1
                if f"SR {tgt}" in cidx:
                    if tgt not in treaty_node:
                        treaty_node[tgt] = add(f"SR {tgt}", "act", intl, cidx[f"SR {tgt}"], 1)
                    out.append([treaty_node[tgt], [eid_of(n) for n in nums if eid_of(n)], clause, how, via, 1])
                else:
                    stats["bases_treaty_not_on_map"] += 1
            else:
                stats["bases_target_not_in_force_or_absent"] += 1
        resolved[sr] = out

    # ---- primary parent
    treaty_set = set()

    def lvl_of_node(t):
        L = lv[t]
        if t in treaty_set:
            return -0.5                                   # a treaty is chosen only without a domestic basis
        return 0 if L in ("apex", "title", "chapter", "section", "bvart") else L

    def common_prefix(a, b):
        n = 0
        for x, y in zip(a, b):
            if x != y:
                break
            n += 1
        return n

    treaty_set.update(treaty_node.values())
    for sr in members:
        me, my_l = act_node[sr], levels[sr][0]
        cands = resolved[sr]
        best = None
        for order, (t, eids, clause, how, via, found) in enumerate(cands):
            tl = lvl_of_node(t)
            if tl >= my_l:
                continue                                  # not a higher norm: secondary only
            tsr = ids[t][3:] if ids[t].startswith("SR ") else "101"
            key = (tl, common_prefix(sr, tsr), -order)    # nearest higher level, SR prefix, text order
            if best is None or key > best[0]:
                best = (key, order)
        if best is None and cands:                        # only same-level bases: the first one, if acyclic
            best = ((0, 0, 0), 0)
            stats["parent_same_level"] += 1
        if best is None:
            parent[me] = nob
            stats["acts_no_basis_in_tree"] += 1
            if not members[sr].get("bases"):
                stats["acts_ingress_names_no_basis"] += 1
        else:
            parent[me] = cands[best[1]][0]
            for k_, c in enumerate(cands):
                c.append(1 if k_ == best[1] else 0)
    # break cycles (same-level chains): walk up; a node meeting itself goes to "no basis"
    for sr in members:
        me, seen, j = act_node[sr], set(), act_node[sr]
        while j is not None and j >= 0 and j not in seen:
            seen.add(j)
            j = parent[j]
        if j is not None and j >= 0 and j in seen and j == me:
            parent[me] = nob
            stats["cycle_broken"] += 1

    # ---- sizes
    def nof(t):
        return core["nodes"][core_i[t]].get("n", 0) if core_i[t] >= 0 else 0
    radius = [0.0] * len(ids)
    for t in range(len(ids)):
        if kind[t] == "act":     # sqrt(decisions + 400): an uncited ordinance stays visible
            radius[t] = 0.11 * math.sqrt(nof(t) + 400)
        elif kind[t] == "bvart":
            info[t]["dec"] = art_n.get(ids[t][3:], 0)
            radius[t] = 0.09 * math.sqrt(info[t]["dec"] + 30)
        elif kind[t] in ("abv", "tgroup"):
            radius[t] = 0.9
        else:
            radius[t] = 0.8

    kids = defaultdict(list)
    for t, p in enumerate(parent):
        if p is not None and p >= 0:
            kids[p].append(t)
    for p, ch in kids.items():
        if p == root:
            ch.sort(key=lambda t: (kind[t] in ("abv", "tgroup"), t))            # BV order, then the sectors
        elif kind[p] in ("title", "chapter", "section"):
            ch.sort()                                                            # document order
        else:
            ch.sort(key=lambda t: (lvl_of_node(t), sort_srkey(ids[t][3:]) if ids[t].startswith("SR ") else (9e9,)))

    # BV articles that are no basis still get a small slot (the whole Constitution is shown)
    def ring(t):
        return LV_R[lv[t]]

    def own(t):
        if t == root:
            return 0.0
        return (2 * radius[t] + 0.5 + 0.12 * radius[t]) / max(ring(t), 1e-6)

    need = [0.0] * len(ids)
    fed_kids = {p: [c for c in ch if lv[c] not in (4, 5)] for p, ch in kids.items()}

    def calc(t):
        s = sum(calc(c) for c in fed_kids.get(t, []))
        need[t] = max(own(t), s)
        return need[t]
    total = calc(root)
    C = total / (2 * math.pi * 0.985)
    ang = [0.0] * len(ids)

    def place(t, a0):
        ch = fed_kids.get(t, [])
        s = sum(need[c] for c in ch)
        a = a0 + (need[t] - s) / 2
        for c in ch:
            place(c, a)
            a += need[c]
        ang[t] = a0 + need[t] / 2
    place(root, -math.pi / 2)

    # cantons: the full circle in SR order, each as wide as its acts need on the lowest ring
    def arc(t):
        return 2 * radius[t] + 0.5 + 0.12 * radius[t]
    width = {ct: max(sum(arc(t) for t in cantonal[ct]), arc(kv_node[ct]) * LV_R[5] / LV_R[4], 30.0) for ct in kv_node}
    r5 = max(LV_R[5] * C, sum(width.values()) / (2 * math.pi * 0.97))
    ring_abs = {4: r5 * LV_R[4] / LV_R[5], 5: r5}
    a = -math.pi / 2
    for ct in kv_node:
        span = width[ct] / r5 + 0.03 * 2 * math.pi / len(kv_node)
        ang[kv_node[ct]] = a + span / 2
        need[kv_node[ct]] = span
        acts_ = sorted(cantonal[ct], key=lambda t: ids[t])
        b = a + (span - sum(arc(t) for t in acts_) / r5) / 2
        for t in acts_:
            ang[t] = b + arc(t) / r5 / 2
            need[t] = arc(t) / r5
            b += arc(t) / r5
        a += span
    scale = 2 * math.pi / (a + math.pi / 2)                     # close the circle exactly
    for ct in kv_node:
        for t in [kv_node[ct], *cantonal[ct]]:
            ang[t] = -math.pi / 2 + (ang[t] + math.pi / 2) * scale
            need[t] *= scale

    pos = []
    for t in range(len(ids)):
        L = lv[t]
        r = ring_abs[L] if L in (4, 5) else ring(t) * C
        y = LV_Y["apex"] if L == "apex" else LV_Y["crown"] if L in ("title", "chapter", "section", "bvart") else LV_Y[L]
        pos.append([round(r * math.cos(ang[t]), 4), round(y * C, 4), round(r * math.sin(ang[t]), 4)])
    pos[root] = [0.0, round(LV_Y["apex"] * C, 4), 0.0]

    # ---- output
    out_nodes = []
    for t in range(len(ids)):
        o = {"i": ids[t], "k": kind[t], "p": parent[t] if parent[t] is not None else -1, "c": core_i[t],
             "x": pos[t][0], "y": pos[t][1], "z": pos[t][2], "r": round(radius[t], 4),
             "w": round(need[t] * (ring_abs[lv[t]] if lv[t] in (4, 5) else ring(t) * C) if t != root
                        else 2 * math.pi * LV_R["bvart"] * C, 3),   # arc width of its span
             "l": lv[t] if isinstance(lv[t], int) else (0 if lv[t] == "apex" else -1)}
        if info[t]:
            o.update({k: v for k, v in info[t].items() if v not in (None, {}, "", False)})
        if ids[t].startswith("SR ") and ids[t][3:] in levels:
            o["by"] = levels[ids[t][3:]][1]
        out_nodes.append(o)
    bases_out = {}
    for sr, cands in resolved.items():
        if cands:
            bases_out[act_node[sr]] = [c[:6] + [c[6] if len(c) > 6 else 0] for c in cands]
    by_level = defaultdict(int)
    for sr in members:
        by_level[levels[sr][0]] += 1
    by_level[4] = len(kv_node)
    by_level[5] = stats["cantonal_acts"]
    method = {"run_date": basis["run_date"], "acts": len(members), "by_level": dict(by_level),
              "issuer_from_title": sum(1 for v in levels.values() if v[1] == "Titel"),
              "acts_with_stated_basis": sum(1 for r in members.values() if r.get("bases")),
              "treaties_as_basis": len(treaty_node), "C": round(C, 3),
              "excluded_cantonal_constitutions": excluded["cantonal_constitutions"],
              "failed_texts": sum(1 for r in acts.values() if "error" in r), **stats}
    # the floors of the Stufenbau (drawn as glass plates): [height, radius, key]
    plates = [[round(LV_Y["crown"] * C, 3), round((LV_R["bvart"] + 0.025) * C, 3), "lvBV"],
              [round(LV_Y[1] * C, 3), round((LV_R[1] + 0.03) * C, 3), "lv1"],
              [round(LV_Y[2] * C, 3), round((LV_R[2] + 0.03) * C, 3), "lv2"],
              [round(LV_Y[3] * C, 3), round((LV_R[3] + 0.03) * C, 3), "lv3"],
              [round(LV_Y[4] * C, 3), round(ring_abs[4] + 0.03 * C, 3), "lv4"],
              [round(LV_Y[5] * C, 3), round(ring_abs[5] + 0.03 * C, 3), "lv5"]]
    json.dump({"nodes": out_nodes, "bases": bases_out, "root": root, "method": method, "plates": plates},
              open(SITE / "tree.json", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump({act_node[sr]: [issuer_of(r), r.get("ingress", "")] for sr, r in members.items()},
              open(SITE / "ingress.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(method, ensure_ascii=False, indent=1))
    print(f"tree.json {(SITE / 'tree.json').stat().st_size / 1e6:.2f} MB, {len(out_nodes)} nodes; "
          f"ingress.json {(SITE / 'ingress.json').stat().st_size / 1e6:.2f} MB")


def sort_srkey(sr: str):
    return tuple(int(x) if x.isdigit() else 10 ** 6 for x in re.split(r"[.]", sr))


if __name__ == "__main__":
    main()
