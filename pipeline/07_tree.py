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
import csv
import gzip
import json
import math

import duckdb
import re
from collections import Counter, defaultdict
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
    struct_all = json.load(gzip.open(ROOT / "data/fedlex_structure.json.gz"))["acts"]
    struct = struct_all["101"]

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
    # ---- cantonal law: every act in force in the 26 official collections
    # (data/cantonal_basis.json, from pipeline/cantonal/*.py and cantonal_basis.py)
    cb = json.load(open(ROOT / "data/cantonal_basis.json"))
    kv_node, kv_art, kgroup, kact, kinfo = {}, defaultdict(dict), {}, {}, {}
    kvst = {ct: {a["id"]: a for a in struct_all.get(sr, {}).get("articles", []) if not a.get("rep")}
            for ct, sr in CANTON_CONSTITUTION.items()}
    kv_order = {ct: {a["id"]: k for k, a in enumerate(struct_all.get(sr, {}).get("articles", []))}
                for ct, sr in CANTON_CONSTITUTION.items()}
    ct_order = sorted(CANTON_CONSTITUTION, key=lambda c: sort_srkey(CANTON_CONSTITUTION[c]))
    for ct in ct_order:
        sr = CANTON_CONSTITUTION[ct]
        col = cb["cantons"].get(ct, {})
        kvrec = col.get("acts", {}).get(col.get("kv") or "", {})
        kv_node[ct] = add(f"SR {sr}", "act", bvart["art_51"], cidx.get(f"SR {sr}", -1), 4,
                          {"ct": ct, **({"ksr": col["kv"], "u": kvrec.get("url")} if kvrec else {})})
        if kvrec:
            kinfo[kv_node[ct]] = kvrec
        # acts naming only federal law; a basis named that cannot be identified; only cantonal acts of a lower floor;
        # no basis named; no Ingress published; cited, not found
        for g in ("fed", "unres", "lower", "none", "noing", "cited"):
            kgroup[(ct, g)] = add(f"KG:{ct}:{g}", "tgroup", kv_node[ct], -1, "kvart", {"ct": ct})
        for ksr, rec in col.get("acts", {}).items():
            if ksr == col.get("kv"):
                continue
            fl = rec["floor"] if rec["floor"] in (5, 6, 7) else 7
            kact[(ct, ksr)] = add(f"K:{ct}:{ksr}", "act", None, -1, fl,
                                  {"ct": ct, "ksr": ksr, "t": rec.get("title"), "ab": rec.get("abbr"), "u": rec.get("url"),
                                   "fb": rec.get("floor_by"), "ad": rec.get("adopted")})
            kinfo[kact[(ct, ksr)]] = rec
    stats["cantons_read"] = sum(1 for ct in ct_order if cb["cantons"].get(ct))
    stats["cantonal_acts"] = len(kact)
    stats["k_floor_from_title"] = sum(1 for i in kact.values() if kinfo[i].get("floor_by") == "Titel")
    stats["k_floor_unknown"] = sum(1 for i in kact.values() if kinfo[i].get("floor_by") == "unbekannt")

    def abbr_keys(ab, ct):
        out = set()
        for part in re.split(r"\s*[,;]\s*", ab or ""):
            k = re.sub(r"[\s.\-/()]", "", part).lower()
            if len(k) < 2:
                continue
            out.add(k)
            for v in (k.removesuffix(ct.lower()), k.removeprefix(ct.lower())):
                if len(v) >= 2:
                    out.add(v)                       # "LPA-VD", "Cst-GE": the code without its canton
        return out
    kidx = defaultdict(lambda: defaultdict(set))
    for (ct, ksr), t in kact.items():
        rec = kinfo[t]
        for ab in [rec.get("abbr")] + [v.get("abbr") for v in (rec.get("i18n") or {}).values()]:
            for k in abbr_keys(ab, ct):
                kidx[ct][k].add(t)
    # the codes decisions cite: the act whose own collection states that abbreviation, else a group
    for k, n in enumerate(core["nodes"]):
        if n["k"] not in ("act", "bucket") or n.get("c") not in kv_node:
            continue
        ct = n["c"]
        code = n["i"].split(" ", 1)[1] if " " in n["i"] else n["i"]
        hits = set()
        if n["k"] == "act":
            for key in abbr_keys(code, ct):
                hits |= kidx[ct].get(key, set())
        if len(hits) == 1 and core_i[next(iter(hits))] < 0:
            core_i[next(iter(hits))] = k
            stats["cited_matched"] += 1
            stats["cited_matched_decisions"] += n.get("n", 0)
            continue
        if len(hits) == 1:                     # a second code for the same act (CPJA = VRG, VRPG = LPJA)
            t = next(iter(hits))
            info[t].setdefault("al", []).append(k)
            stats["cited_matched_second_code"] += 1
            continue
        stats["cited_ambiguous" if len(hits) > 1 else "cited_shared_code" if hits else "cited_unmatched"] += 1
        stats["cited_unmatched_decisions"] += n.get("n", 0)
        add(n["i"], n["k"], kgroup[(ct, "cited")], k, 7, {"ct": ct, "cited": 1})
    # an act cited under several codes: the distinct decisions citing any of them (exact, not a sum)
    multi = {t: [core["nodes"][core_i[t]]["i"]] + [core["nodes"][k]["i"] for k in info[t]["al"]]
             for t in kact.values() if info[t].get("al") and core_i[t] >= 0}
    alias_ids = dict(multi)                     # every code an act is cited under (for the overview's counts)
    if multi:
        pairs = [(t, a) for t, codes in multi.items() for a in codes]
        duckdb.sql("create or replace temp table mc(t int, act_id varchar)")
        duckdb.executemany("insert into mc values (?, ?)", pairs)
        for t, n_ in duckdb.sql(f"select mc.t, count(distinct r.decision_id) from mc join '{ROOT}/build/refs_valid.parquet' r "
                                f"using (act_id) group by 1").fetchall():
            info[t]["dn"] = n_
        for t in multi:
            info[t]["al"] = [[core["nodes"][k]["i"].split(" ", 1)[1], core["nodes"][k].get("n", 0)] for k in info[t]["al"]]
            stats["cited_matched_decisions"] += info[t].get("dn", 0) - core["nodes"][core_i[t]].get("n", 0)
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

    # ---- cantonal bases: resolve to tree nodes; the parent is the nearest higher cantonal floor
    def kv_article(ct, n):
        e = eid_of(n)
        if not e or e not in kvst[ct]:
            return None
        if e not in kv_art[ct]:
            a = kvst[ct][e]
            kv_art[ct][e] = add(f"KV:{ct}:{e}", "kvart", kv_node[ct], -1, "kvart", {"ct": ct, "n": n, "h": a.get("h") or {}})
        return kv_art[ct][e]

    def fed_eids(tgt, nums):
        alist = acts[tgt].get("arts") or []
        out = []
        for n in nums:
            block = None
            if n.startswith(("SchlT ", "ÜB ")):
                block, n = n.split(" ", 1)
            e = eid_of(n.split("–")[0])
            if block and e:
                e = next((a for a in alist if a.startswith("disp_") and a.endswith("/" + e)), e)
            if e:
                out.append(e)
        return out
    kv_nodes = set(kv_node.values())

    def kfloor(t):
        return 4 if t in kv_nodes or kind[t] == "kvart" else lv[t]

    def is_k(t):
        return t in kv_nodes or kind[t] == "kvart" or ids[t].startswith("K:")
    kresolved = {}
    for (ct, ksr), me in kact.items():
        out = []
        for b in kinfo[me]["bases"]:
            tgt, arts, clause = b[0], b[1], b[2]
            via = {"old": "old", "note": "note"}.get(b[3], "text") if len(b) > 3 else "text"
            stats["k_bases"] += 1
            if tgt == "KV":
                hit = [x for x in (kv_article(ct, n.split("–")[0]) for n in arts) if x]
                found = int(len(hit) == len(arts))
                if not found:
                    stats["k_bases_kv_article_not_found"] += 1
                stats["k_bases_kv"] += 1
                out.append([hit[0] if hit else kv_node[ct], [ids[x].split(":")[-1] for x in hit], clause, "basis", via, found])
            elif tgt.startswith("CT:"):
                t2 = kact.get((ct, tgt[3:])) or (kv_node[ct] if tgt[3:] == cb["cantons"][ct].get("kv") else None)
                if t2 is None or t2 == me:
                    stats["k_bases_unresolved"] += 1
                    out.append([-1, [], clause, "basis", "unresolved", 0])
                    continue
                stats["k_bases_cantonal"] += 1
                out.append([t2, arts, clause, "basis", via, 1])
            elif tgt == "SR 101":
                eids = [eid_of(n) for n in arts if eid_of(n) in bvart]
                stats["k_bases_federal"] += 1
                out.append([bvart[eids[0]] if eids else root, eids, clause, "basis", via, int(len(eids) == len(arts))])
            elif tgt.startswith("X:"):                 # an act of another canton (agreements name each party's law)
                stats["k_bases_other_canton"] += 1
                out.append([-1, [], clause, "basis", "other", 0])
            elif tgt == "SR ?":                       # federal law named in general ("Bundesgesetzgebung über …")
                stats["k_bases_federal_unidentified"] += 1
                out.append([-1, [], clause, "basis", "fedany", 0])
            elif tgt.startswith("SR ") and "@" not in tgt and tgt[3:] in act_node:
                stats["k_bases_federal"] += 1
                out.append([act_node[tgt[3:]], fed_eids(tgt[3:], arts), clause, "basis", via, 1])
            elif tgt.startswith("SR "):
                stats["k_bases_federal_earlier" if "@" in tgt else "k_bases_federal_not_on_tree"] += 1
                out.append([-1, [], clause, "basis", "earlier" if "@" in tgt else "absent", 0])
            else:
                stats["k_bases_unresolved"] += 1
                out.append([-1, [], clause, "basis", "unresolved", 0])
        best = None
        for order, c in enumerate(out):
            t = c[0]
            if t < 0 or not is_k(t) or kfloor(t) > lv[me]:
                continue
            key = (kfloor(t) < lv[me], kfloor(t), -order)        # a higher floor, the nearest one, text order
            if best is None or key > best[0]:
                best = (key, order)
        if best is not None:
            parent[me] = out[best[1]][0]
            stats["k_parent_same_floor"] += int(not best[0][0])
        else:
            # no cantonal basis to hang from: say why, in this order
            if any(c[4] in ("unresolved", "other") for c in out):
                g = "unres"                          # a basis named that the collection in force does not identify (or another canton's)
            elif any(c[0] >= 0 and is_k(c[0]) for c in out):
                g = "lower"                          # it names only cantonal acts of a lower floor
            elif out:
                g = "fed"                            # only federal law (in force, earlier, or in general)
            elif (kinfo[me].get("ingress") or "").strip() and not kinfo[me].get("noing"):
                g = "none"                           # the Ingress names no basis (an editorial note in its place, UR/ZG, is no Ingress)
            else:
                g = "noing"                          # the collection publishes no Ingress
            parent[me] = kgroup[(ct, g)]
            stats[{"unres": "k_basis_unidentified", "lower": "k_basis_lower_floor_only", "fed": "k_only_federal_basis",
                   "none": "k_no_basis_in_ingress", "noing": "k_no_ingress_published"}[g]] += 1
        for k_, c in enumerate(out):
            c.append(1 if best is not None and k_ == best[1] else 0)
        kresolved[me] = out
    for (ct, ksr), me in kact.items():                       # same-floor chains: a cycle goes to "names no act above it"
        seen, j = set(), me
        while j is not None and j >= 0 and j not in seen:
            seen.add(j)
            j = parent[j]
        if j == me:
            parent[me] = kgroup[(ct, "lower")]      # same-floor bases that run in a circle
            stats["k_cycle_broken"] += 1

    # ---- sizes
    def nof(t):
        if info[t].get("dn"):
            return info[t]["dn"]
        return core["nodes"][core_i[t]].get("n", 0) if core_i[t] >= 0 else 0
    radius = [0.0] * len(ids)
    for t in range(len(ids)):
        if kind[t] == "act" and lv[t] in (5, 6, 7):    # cantonal: sqrt(decisions + 120), room for 15,000 acts
            radius[t] = 0.11 * math.sqrt(nof(t) + 120)
        elif kind[t] == "act":   # sqrt(decisions + 400): an uncited ordinance stays visible
            radius[t] = 0.11 * math.sqrt(nof(t) + 400)
        elif kind[t] == "bvart":
            info[t]["dec"] = art_n.get(ids[t][3:], 0)
            radius[t] = 0.09 * math.sqrt(info[t]["dec"] + 30)
        elif kind[t] == "kvart":
            radius[t] = 1.1
        elif kind[t] in ("abv", "tgroup"):
            radius[t] = 0.9
        else:
            radius[t] = 0.8

    kids = defaultdict(list)
    for t, p in enumerate(parent):
        if p is not None and p >= 0:
            kids[p].append(t)
    for p, ch in kids.items():
        if p in kv_nodes:                                                    # KV articles in order, then the groups
            ch.sort(key=lambda t: (kind[t] == "tgroup", kv_order[info[p]["ct"]].get(ids[t].split(":")[-1], 0), t))
        elif ids[p].startswith(("K:", "KV:", "KG:")):
            ch.sort(key=lambda t: (kfloor(t), natkey(info[t].get("ksr") or ids[t])))
        elif p == root:
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
    CANT = (4, "kvart", 5, 6, 7)
    fed_kids = {p: [c for c in ch if lv[c] not in CANT] for p, ch in kids.items()}

    def calc(t):
        s = sum(calc(c) for c in fed_kids.get(t, []))
        need[t] = max(own(t), s)
        return need[t]
    total = calc(root)
    C = total / (2 * math.pi * 0.985)
    need = [x / C for x in need]          # arc lengths (in units of C) -> angles
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

    # cantons: the full circle in SR order; inside each, a radial tree from its constitution:
    #   constitution (floor 4) -> its articles named as bases and the groups (just outside) ->
    #   acts on floors 5-7, each as wide as what rests on it.
    KR = {4: 1.0, "kvart": 1.07, 5: 1.3, 6: 1.58, 7: 1.86}
    KY = {4: -0.3, "kvart": -0.34, 5: -0.62, 6: -0.94, 7: -1.26}
    ckids = {p: [c for c in ch if lv[c] in CANT] for p, ch in kids.items()}

    def karc(t):
        return 2 * radius[t] + 0.3 + 0.1 * radius[t]

    kneed = {}

    def kcalc(t):
        s_ = sum(kcalc(c) for c in ckids.get(t, []))
        kneed[t] = max(karc(t) / KR[lv[t]], s_)
        return kneed[t]
    T = sum(kcalc(kv_node[ct]) for ct in ct_order)
    gap = 0.004 * 2 * math.pi
    Rk = max(T / (2 * math.pi * 0.99 - gap * len(ct_order)), 1.22 * LV_R[3] * C)

    def kplace(t, a0):
        ch = ckids.get(t, [])
        s_ = sum(kneed[c] for c in ch) / Rk
        a = a0 + (kneed[t] / Rk - s_) / 2
        for c in ch:
            kplace(c, a)
            a += kneed[c] / Rk
        ang[t] = a0 + kneed[t] / Rk / 2
        need[t] = kneed[t] / Rk
    a = -math.pi / 2
    for ct in ct_order:
        kplace(kv_node[ct], a + gap / 2)
        a += kneed[kv_node[ct]] / Rk + gap
    ring_abs = {L: KR[L] * Rk for L in KR}

    pos = []
    for t in range(len(ids)):
        L = lv[t]
        r = ring_abs[L] if L in CANT else ring(t) * C
        y = LV_Y["apex"] if L == "apex" else LV_Y["crown"] if L in ("title", "chapter", "section", "bvart") else (
            KY[L] if L in CANT else LV_Y[L])
        pos.append([round(r * math.cos(ang[t]), 2), round(y * C, 2), round(r * math.sin(ang[t]), 2)])
    pos[root] = [0.0, round(LV_Y["apex"] * C, 2), 0.0]

    # ---- output
    # URLs of cantonal acts: one template per canton where the portal's links follow one ({} = number)
    kurl = {}
    for ct in ct_order:
        us = [(info[t]["ksr"], info[t].get("u")) for (c_, _), t in kact.items() if c_ == ct and info[t].get("u")]
        best_tpl = max({u.replace(k, "{}", 1) for k, u in us if k in u} or {""},
                       key=lambda tp: sum(1 for k, u in us if tp and tp.replace("{}", k, 1) == u))
        if best_tpl:
            kurl[ct] = best_tpl
            for (c_, _), t in kact.items():
                if c_ == ct and info[t].get("u") == best_tpl.replace("{}", info[t]["ksr"], 1):
                    del info[t]["u"]
    for t in kact.values():
        if info[t].get("fb") in ("Ingress", "interkantonal", "kommunal", "Kirche"):
            del info[t]["fb"]                    # the floor follows from the Ingress; only "Titel"/"unbekannt" shown
    method_k_urls = kurl
    # article symbol of each canton's constitution as its own Ingresses write it ("§ 41 KV" in ZG, "Art. 38 KV" in ZH)
    ksym = {}
    for ct in ct_order:
        c = Counter()
        for (c_, _), t in kact.items():
            if c_ == ct:
                for b in kinfo[t]["bases"]:
                    if b[0] == "KV" and b[1]:
                        c["§" if "§" in b[2] else "Art."] += 1
        ksym[ct] = c.most_common(1)[0][0] if c else "Art."
    # the constitutions on Fedlex (guaranteed by the Federal Assembly, published in SR 131.2)
    eli = {}
    for r in csv.DictReader(open(ROOT / "data/sr_eli.csv", encoding="utf-8")):
        if r["notation"] not in eli or (r.get("inForce") or "").endswith("/0"):
            eli[r["notation"]] = r["act"]
    for ct, t in kv_node.items():
        e = eli.get(CANTON_CONSTITUTION[ct])
        if e:
            info[t]["e"] = e.replace("http://", "https://").replace("fedlex.data.admin.ch", "www.fedlex.admin.ch")
    # adoption date of each federal act (dated title in the SR taxonomy): today's law by year of adoption
    from cantonal_basis import LABEL, MONTHS
    for r in csv.DictReader(open(ROOT / "data/sr_taxonomy.csv", encoding="utf-8")):
        t = act_node.get(r["notation"]) if r["lang"] == "de" else None
        m = LABEL.match(r["label"]) if t is not None else None
        if m:
            info[t]["ad"] = f"{int(m['y']):04d}-{MONTHS[m['m'].lower()]:02d}-{int(m['d']):02d}"
    info[root]["ad"] = "1999-04-18"
    stats["federal_acts_with_date"] = sum(1 for t in act_node.values() if info[t].get("ad"))

    # guided tours: stops chosen by rule from the data, so every number they show is computed
    rests_on = defaultdict(list)                 # target -> acts naming it as a basis
    for sr, cands in resolved.items():
        for c in cands:
            rests_on[c[0]].append(act_node[sr])
    for me, cands in kresolved.items():
        for c in cands:
            if c[0] >= 0:
                rests_on[c[0]].append(me)

    def thread(eid, sr):
        """Art. <eid> BV -> the act -> its most-cited ordinance resting on it -> the most-cited cantonal act
        resting on either: one real delegation chain, from the Constitution to the canton."""
        law = act_node[sr]
        ords = [x for x in set(rests_on[law]) if lv[x] == 2 and parent[x] == law]
        o = max(ords, key=lambda x: (nof(x), -x)) if ords else None
        cant = [x for x in set(rests_on[law] + (rests_on[o] if o is not None else [])) if lv[x] in (5, 6, 7)]
        k = max(cant, key=lambda x: (nof(x), -x)) if cant else None
        return [x for x in (bvart[eid], law, o, k) if x is not None]
    top_acts = sorted((t for t in act_node.values()), key=lambda t: -nof(t))[:3]
    tours = [
        {"id": "stufenbau", "stops": [{"k": "overview"}, {"k": "apex", "i": root}, {"k": "floor", "l": 1},
                                      {"k": "floor", "l": 2}, {"k": "floor", "l": 3}, {"k": "cantons"},
                                      {"k": "courts", "top": top_acts}]},
        {"id": "verkehr", "stops": [{"k": "node", "i": x} for x in thread("art_82", "741.01")] + [{"k": "courts", "i": act_node["741.01"]}]},
        {"id": "bauen", "stops": [{"k": "node", "i": x} for x in thread("art_75", "700")] + [{"k": "courts", "i": act_node["700"]}]},
    ]
    # ---- the overview ("Aufbau"): one block per floor and SR area (federal law) or canton. Every
    # act in force sits in exactly one block and arrives by exactly one flow, its place in the tree
    # (primary basis), so the flows into a block plus its stubs ("no basis named", "only federal
    # law named") sum to its acts. Case law between blocks: distinct decisions citing both.
    kgroup_kind = {v: k[1] for k, v in kgroup.items()}
    kv_ct = {v: k for k, v in kv_node.items()}
    act_ct = {t: ct for (ct, _), t in kact.items()}
    fed_acts = set(act_node.values())
    blocks, bidx = [], {}

    def block(key):
        if key not in bidx:
            bidx[key] = len(blocks)
            blocks.append({"r": key[0], "k": key[1]})
        return bidx[key]

    def key_of(t):                                    # the block a node belongs to
        if t in fed_acts:
            return (lv[t], ids[t][3])                 # SR area: the first digit
        if t in kv_ct:
            return (4, kv_ct[t])
        if kind[t] == "kvart":
            return (4, info[t]["ct"])
        if t in act_ct:
            return (lv[t], act_ct[t])
        if t == abv:
            return ("bv", "1874")
        if t == intl or t in treaty_set:
            return ("bv", "int")
        if t == root:
            return ("bv", root)
        if kind[t] == "bvart":                        # an article: the section (or chapter, title) it stands in
            p = parent[t]
            return ("bv", p if p is not None and p != root and kind[p] in ("title", "chapter", "section") else root)
        if kind[t] in ("title", "chapter", "section"):
            return ("bv", t)
        return None
    bmembers, bflows, bstubs = defaultdict(list), defaultdict(list), defaultdict(list)
    for t in list(act_node.values()) + list(kv_ct) + list(act_ct):
        me = block(key_of(t))
        bmembers[me].append(t)
        p = parent[t]
        g = kgroup_kind.get(p)
        if p is None or p < 0 or p == nob:
            bstubs[(me, "none")].append(t)
        elif g in ("none", "noing", "unres", "lower", "fed"):
            bstubs[(me, g)].append(t)
        else:
            bflows[(block(key_of(p)), me)].append(t)
    by_dec = lambda t: (-nof(t), t)
    for b in range(len(blocks)):
        blocks[b]["n"] = len(bmembers[b])
        blocks[b]["o"] = sum(len(v) for (s, _), v in bflows.items() if s == b)
    # decisions per block, and per pair of blocks: distinct decisions citing an act of each
    act_rows, bv_rows = [], []
    for t in list(act_node.values()) + list(kv_ct) + list(act_ct):
        codes = alias_ids.get(t) or ([core["nodes"][core_i[t]]["i"]] if core_i[t] >= 0 else [])
        act_rows += [(c, bidx[key_of(t)]) for c in codes]
    for e, t in bvart.items():
        bv_rows.append((e, bidx.get(key_of(t), bidx.get(("bv", root), -1))))
    duckdb.sql("create or replace temp table bm_act(act_id varchar, b int)")
    duckdb.executemany("insert into bm_act values (?, ?)", act_rows)
    duckdb.sql("create or replace temp table bm_bv(art varchar, b int)")
    duckdb.executemany("insert into bm_bv values (?, ?)", bv_rows)
    bv_root = block(("bv", root))
    duckdb.sql(f"""create or replace temp table db as
        select distinct r.decision_id d, m.b from '{ROOT}/build/refs_valid.parquet' r join bm_act m using (act_id)
        union
        select distinct r.decision_id d, coalesce(a.b, {bv_root}) b from '{ROOT}/build/refs_valid.parquet' r
          left join bm_bv a on a.art = r.art where r.act_id = 'SR 101'""")
    for b, n_ in duckdb.sql("select b, count(distinct d) from db group by 1").fetchall():
        blocks[b]["d"] = n_
    dec_any = duckdb.sql("select count(distinct d) from db").fetchall()[0][0]
    court = [[a, b, n_] for a, b, n_ in duckdb.sql(
        "select x.b, y.b, count(*) from db x join db y on x.d = y.d and x.b < y.b group by 1, 2 order by 3 desc").fetchall()]
    # legislation between blocks: provisions of one act naming another (the whole BV for SR 101)
    core_block = {core_i[t]: bidx[key_of(t)] for t in act_node.values()}
    core_block[cidx["SR 101"]] = bv_root
    for k, n in enumerate(core["nodes"]):
        if n["i"].startswith("SR 0.") and n["k"] == "act":
            core_block[k] = block(("bv", "int"))
    law = defaultdict(lambda: [0, 0])
    int_block = block(("bv", "int"))
    for a, b, n_ in core.get("xedges", []):              # domestic acts naming others (treaties naming treaties: out)
        if a in core_block and b in core_block and core_block[a] != int_block:
            x = law[(core_block[a], core_block[b])]
            x[0] += n_; x[1] += 1
    for b in range(len(blocks)):                      # blocks created for the legislation layer only
        blocks[b].setdefault("n", 0); blocks[b].setdefault("o", 0)
    # the matrix: every stated basis by pair of blocks (not only the one that places an act in the
    # tree): acts of block a naming a basis in block b; of them, acts whose place in the tree is there
    nb = [bidx.get(key_of(t), -1) if key_of(t) is not None else -1 for t in range(len(ids))]
    core_blk = [core_block.get(k, -1) for k in range(len(core["nodes"]))]
    floor_of = lambda t: lvl_of_node(t) if t not in kv_ct and kind[t] != "kvart" and t not in act_ct else (4 if t in kv_ct or kind[t] == "kvart" else lv[t])
    bpair = defaultdict(lambda: [set(), set()])
    rank = Counter()
    seen_pair = set()
    # bases on a lower floor, as reviewed by hand (reports/inversions_review.json): category per pair
    rev = json.load(open(ROOT / "reports/inversions_review.json"))
    rev_cats = [c["id"] for c in rev["categories"]] + ["open"]
    rev_of = {(x["a"], x["t"]): rev_cats.index(x["c"]) for x in rev["items"]}
    low = []
    for me, targets in [(act_node[sr], [c[0] for c in cands]) for sr, cands in resolved.items()] + \
            [(me, [c[0] for c in cands]) for me, cands in kresolved.items()]:
        a = nb[me]
        for t in targets:
            if t is None or t < 0 or a < 0 or nb[t] < 0 or (me, t) in seen_pair:
                continue
            seen_pair.add((me, t))
            x = bpair[(a, nb[t])]
            x[0].add(me)
            if parent[me] == t:
                x[1].add(me)
            fa, ft = floor_of(me), floor_of(t)
            rank["higher" if ft < fa else "same" if ft == fa else "lower"] += 1
            if ft > fa:
                low.append([me, t, rev_of.get((ids[me], ids[t]), len(rev_cats) - 1)])
    stats["mat_basis_pairs"] = len(seen_pair)
    stats["mat_basis_cells"] = len(bpair)
    for k_, v in rank.items():
        stats[f"mat_basis_{k_}"] = v
    for k_, c_ in enumerate(rev_cats):
        stats[f"mat_low_{c_}"] = sum(1 for x in low if x[2] == k_)
    stale = set(rev_of) - {(ids[a], ids[b]) for a, b, _ in low}
    stats["mat_low_review_stale"] = len(stale)          # reviewed pairs that no longer occur (data changed)
    agg = {"blocks": blocks, "members": [sorted(bmembers[b], key=by_dec) for b in range(len(blocks))],
           "basis": [[a, b, len(v[0]), len(v[1])] for (a, b), v in sorted(bpair.items())], "nb": nb, "cb": core_blk,
           "rank": {k_: rank[k_] for k_ in ("higher", "same", "lower")},
           "low": {"cats": rev_cats, "reviewed": rev["reviewed"], "items": sorted(low)},
           "flows": [[s, d, sorted(v, key=by_dec)] for (s, d), v in sorted(bflows.items(), key=lambda x: (-len(x[1]), x[0]))],
           "stubs": [[d, g, sorted(v, key=by_dec)] for (d, g), v in sorted(bstubs.items())],
           "law": [[a, b, v[0], v[1]] for (a, b), v in sorted(law.items(), key=lambda x: (-x[1][0], x[0]))],
           "court": court, "dec_any": dec_any, "ct_order": ct_order}
    stats["agg_blocks"] = len(blocks)
    stats["agg_flows"] = len(bflows)
    stats["agg_acts"] = sum(len(v) for v in bmembers.values())
    stats["agg_dec_any"] = dec_any
    for g_ in ("none", "noing", "unres", "lower", "fed"):
        stats[f"agg_stub_{g_}"] = sum(len(v) for (_, g), v in bstubs.items() if g == g_)
    stats["agg_no_basis"] = stats["agg_stub_none"]
    stats["agg_only_federal"] = stats["agg_stub_fed"]
    rowno = lambda r: 0 if r == "bv" else r                # the Constitution's row is floor 0
    stats["agg_skip_flows"] = sum(len(v) for (s_, d_), v in bflows.items()   # a floor skipped, within one part (the trunk aside)
                                  if rowno(blocks[d_]["r"]) - rowno(blocks[s_]["r"]) > 1 and (rowno(blocks[s_]["r"]) >= 4) == (blocks[d_]["r"] >= 4))
    assert stats["agg_acts"] == sum(len(v) for v in bflows.values()) + sum(len(v) for v in bstubs.values())

    out_nodes = []
    for t in range(len(ids)):
        o = {"i": ids[t], "k": kind[t], "p": parent[t] if parent[t] is not None else -1, "c": core_i[t],
             "x": pos[t][0], "y": pos[t][1], "z": pos[t][2], "r": round(radius[t], 4),
             "w": round(need[t] * (ring_abs[lv[t]] if lv[t] in CANT else ring(t) * C) if t != root
                        else 2 * math.pi * LV_R["bvart"] * C, 1),   # arc width of its span
             "l": lv[t] if isinstance(lv[t], int) else (4.5 if lv[t] == "kvart" else 0 if lv[t] == "apex" else -1)}
        if info[t]:
            o.update({k: v for k, v in info[t].items() if v not in (None, {}, "", False)})
        if ids[t].startswith("SR ") and ids[t][3:] in levels:
            o["by"] = levels[ids[t][3:]][1]
        out_nodes.append(o)
    bases_out = {}
    for sr, cands in resolved.items():
        if cands:
            bases_out[act_node[sr]] = [c[:6] + [c[6] if len(c) > 6 else 0] for c in cands]
    kclauses = {}
    for me, cands in kresolved.items():       # cantonal clauses travel with the Ingress (loaded on demand)
        if cands:
            bases_out[me] = [[c[0], c[1], "", *c[3:]] for c in cands]
            kclauses[me] = [c[2] for c in cands]
    by_level = defaultdict(int)
    for sr in members:
        by_level[levels[sr][0]] += 1
    by_level[4] = len(kv_node)
    for t in kact.values():
        by_level[lv[t]] += 1
    method = {"run_date": basis["run_date"], "acts": len(members), "by_level": dict(by_level),
              "issuer_from_title": sum(1 for v in levels.values() if v[1] == "Titel"),
              "acts_with_stated_basis": sum(1 for r in members.values() if r.get("bases")),
              "treaties_as_basis": len(treaty_node), "C": round(C, 3),
              "excluded_cantonal_constitutions": excluded["cantonal_constitutions"],
              "failed_texts": sum(1 for r in acts.values() if "error" in r), "Rk": round(Rk, 3), "kurl": method_k_urls, "ksym": ksym,
              "cantonal": {"run_date": cb["run_date"], **cb["stats"],
                           "by_canton": {ct: len(cb["cantons"].get(ct, {}).get("acts", {})) for ct in ct_order},
                           "src": dict(sorted(defaultdict(int, {k: sum(1 for r in kinfo.values() if r.get("src") == k)
                                                                 for k in {r.get("src") for r in kinfo.values()}}).items()))},
              **stats}
    # the floors of the Stufenbau (drawn as glass plates): [height, radius, key]
    plates = [[round(LV_Y["crown"] * C, 3), round((LV_R["bvart"] + 0.025) * C, 3), "lvBV"],
              [round(LV_Y[1] * C, 3), round((LV_R[1] + 0.03) * C, 3), "lv1"],
              [round(LV_Y[2] * C, 3), round((LV_R[2] + 0.03) * C, 3), "lv2"],
              [round(LV_Y[3] * C, 3), round((LV_R[3] + 0.03) * C, 3), "lv3"],
              [round(KY[4] * C, 3), round(ring_abs["kvart"] + 0.02 * Rk, 3), "lv4"],
              [round(KY[5] * C, 3), round(ring_abs[5] + 0.02 * Rk, 3), "lv5"],
              [round(KY[6] * C, 3), round(ring_abs[6] + 0.02 * Rk, 3), "lv6"],
              [round(KY[7] * C, 3), round(ring_abs[7] + 0.02 * Rk, 3), "lv7"]]
    json.dump({"nodes": out_nodes, "bases": bases_out, "root": root, "method": method, "plates": plates, "tours": tours},
              open(SITE / "tree.json", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(agg, open(SITE / "agg.json", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump({act_node[sr]: [issuer_of(r), r.get("ingress", "")] for sr, r in members.items()},
              open(SITE / "ingress.json", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump({t: [r.get("issuer") or "", r.get("ingress") or "", kclauses.get(t, [])] for t, r in kinfo.items() if r.get("ingress")},
              open(SITE / "ingress_k.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(method, ensure_ascii=False, indent=1))
    print(f"tree.json {(SITE / 'tree.json').stat().st_size / 1e6:.2f} MB, {len(out_nodes)} nodes; "
          f"ingress.json {(SITE / 'ingress.json').stat().st_size / 1e6:.2f} MB; "
          f"ingress_k.json {(SITE / 'ingress_k.json').stat().st_size / 1e6:.2f} MB")


def natkey(s: str):
    """Order of a cantonal systematic number of any style: 155.611, VIII B/21/5/1, E 5 10.03."""
    return tuple((0, int(x)) if x.isdigit() else (1, x) for x in re.findall(r"\d+|[A-Za-z]+", s or ""))


def sort_srkey(sr: str):
    return tuple(int(x) if x.isdigit() else 10 ** 6 for x in re.split(r"[.]", sr))


if __name__ == "__main__":
    main()
