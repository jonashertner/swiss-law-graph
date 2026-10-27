"""The data of the public site (docs/), from the pipeline's outputs.

One index of every act, language-independent (docs/data/atlas.json), names per language
(names.<lang>.json), and detail files loaded when an act is opened:

  atlas.json         nodes of one tree: root → blocks (federal law, international law, cantonal
                     law) → SR categories / cantons → acts. Every act in force (Fedlex: SR number
                     in force; the 26 cantonal collections), and the acts courts cite that are no
                     longer in force (earlier regimes "SR 101@1874"; cantonal codes not in the
                     collection in force). Per node: kind, parent, number, floor of the hierarchy,
                     distinct decisions referring to it, articles, detail shard.
  names.<lang>.json  label (abbreviation, else title) and full title per node, in de/fr/it/en
                     (federal titles: Fedlex; a missing English title falls back to German).
  links.json         stated bases (act → act it rests on), co-citation (decision 9) and
                     legislative references (decision 15), in atlas indices.
  hier.json          the hierarchy overview (decision 23) and the matrix (decision 25), in atlas
                     indices.
  art/<n>.json       articles of cited federal acts: structure, decisions per article and year,
                     most-cited decisions, co-cited articles (from site/data/p).
  law/<x>.json       Ingress, issuer and every stated basis with its clause verbatim (F = federal,
                     else canton).
  find.<lang>.json   headings of divisions, for search ("Mietrecht" → OR, Achter Titel).

Usage: python3 pipeline/08_web.py      (after 05_site.py and 07_tree.py; ~20 s)
"""
import csv
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site" / "data"
OUT = ROOT / "docs" / "data"
LANGS = ("de", "fr", "it", "en")
CANTON_NAMES = {
    "ZH": ("Zürich", "Zurich", "Zurigo", "Zurich"), "BE": ("Bern", "Berne", "Berna", "Bern"),
    "LU": ("Luzern", "Lucerne", "Lucerna", "Lucerne"), "UR": ("Uri", "Uri", "Uri", "Uri"),
    "SZ": ("Schwyz", "Schwytz", "Svitto", "Schwyz"), "OW": ("Obwalden", "Obwald", "Obvaldo", "Obwalden"),
    "NW": ("Nidwalden", "Nidwald", "Nidvaldo", "Nidwalden"), "GL": ("Glarus", "Glaris", "Glarona", "Glarus"),
    "ZG": ("Zug", "Zoug", "Zugo", "Zug"), "FR": ("Freiburg", "Fribourg", "Friburgo", "Fribourg"),
    "SO": ("Solothurn", "Soleure", "Soletta", "Solothurn"), "BS": ("Basel-Stadt", "Bâle-Ville", "Basilea Città", "Basel-Stadt"),
    "BL": ("Basel-Landschaft", "Bâle-Campagne", "Basilea Campagna", "Basel-Landschaft"),
    "SH": ("Schaffhausen", "Schaffhouse", "Sciaffusa", "Schaffhausen"),
    "AR": ("Appenzell Ausserrhoden", "Appenzell Rhodes-Extérieures", "Appenzello Esterno", "Appenzell Ausserrhoden"),
    "AI": ("Appenzell Innerrhoden", "Appenzell Rhodes-Intérieures", "Appenzello Interno", "Appenzell Innerrhoden"),
    "SG": ("St. Gallen", "Saint-Gall", "San Gallo", "St. Gallen"), "GR": ("Graubünden", "Grisons", "Grigioni", "Grisons"),
    "AG": ("Aargau", "Argovie", "Argovia", "Aargau"), "TG": ("Thurgau", "Thurgovie", "Turgovia", "Thurgau"),
    "TI": ("Tessin", "Tessin", "Ticino", "Ticino"), "VD": ("Waadt", "Vaud", "Vaud", "Vaud"),
    "VS": ("Wallis", "Valais", "Vallese", "Valais"), "NE": ("Neuenburg", "Neuchâtel", "Neuchâtel", "Neuchâtel"),
    "GE": ("Genf", "Genève", "Ginevra", "Geneva"), "JU": ("Jura", "Jura", "Giura", "Jura")}
BLOCKS = {"fed": ("Bundesrecht", "Droit fédéral", "Diritto federale", "Federal law"),
          "int": ("Völkerrecht", "Droit international", "Diritto internazionale", "International law"),
          "kt": ("Kantonales Recht", "Droit cantonal", "Diritto cantonale", "Cantonal law")}
NOT_IN_FORCE = ("Nicht in der geltenden Sammlung", "Hors du recueil en vigueur", "Fuori dalla raccolta in vigore",
                "Not in the collection in force")
OTHER_CODES = ("Weitere", "Autres", "Altri", "Others")


def plain(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).replace(" - ", " – ").strip()


def srkey(s):
    """Sort SR numbers the way the collection does: 0.101 < 0.101.1 < 0.102; 9 < 10."""
    out = []
    for p in re.split(r"[.\s/]", s or ""):
        out.append((0, int(p), "") if p.isdigit() else (1, 0, p))
    return out


def abbr_of(label):
    m = re.search(r"\(([A-ZÄÖÜ][\w./\-]{1,15}(?:\s[\w./\-]{1,8})?)\)\s*$", label or "")
    return m.group(1) if m and not re.fullmatch(r"[IVX]+", m.group(1)) else ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    core = json.load(open(SRC / "core.json"))
    tree = json.load(open(SRC / "tree.json"))
    cnodes, tnodes = core["nodes"], tree["nodes"]
    ctitles = {lg: json.load(open(SRC / f"titles.{lg}.json")) for lg in LANGS}
    fedacts = json.load(open(ROOT / "data/fedlex_acts.json"))["acts"]
    cb = json.load(open(ROOT / "data/cantonal_basis.json"))["cantons"]

    # ---- the SR (federal) in force: taxonomy tree, titles, ELI
    tax = defaultdict(dict)
    for r in csv.DictReader(open(ROOT / "data/sr_taxonomy.csv", encoding="utf-8")):
        tax[r["notation"]][r["lang"]] = plain(r["label"])
        tax[r["notation"]]["_b"] = r["broader"]
    eli_in, eli_any = {}, {}
    for r in csv.DictReader(open(ROOT / "data/sr_eli.csv", encoding="utf-8")):
        eli_any.setdefault(r["notation"], r["act"])
        if r["inForce"].endswith("/0"):
            eli_in[r["notation"]] = r["act"]

    nodes, names = [], {lg: {"l": [], "t": []} for lg in LANGS}

    def add(kind, parent, code="", label=None, title=None, **kw):
        nodes.append({"k": kind, "p": parent, "s": code, **{k: v for k, v in kw.items() if v not in (None, "") and not (v == 0 and k in ("d", "n", "m"))}})
        for i, lg in enumerate(LANGS):
            lab = label[i] if isinstance(label, (list, tuple)) else (label or {}).get(lg) if isinstance(label, dict) else label
            tit = title[i] if isinstance(title, (list, tuple)) else (title or {}).get(lg) if isinstance(title, dict) else title
            names[lg]["l"].append(lab or "")
            names[lg]["t"].append(tit if tit and tit != lab else "")
        return len(nodes) - 1

    root = add("r", -1, "", ("Schweizer Recht", "Droit suisse", "Diritto svizzero", "Swiss law"))
    blk = {k: add("b", root, k, v, id=k) for k, v in BLOCKS.items()}

    def tlabel(n):
        d = tax[n]
        return {lg: d.get(lg) or d.get("de") for lg in LANGS}

    # categories: every taxonomy node above an act in force
    need = set()
    for n in eli_in:
        b = tax[n].get("_b")
        while b:
            if b in need:
                break
            need.add(b)
            b = tax[b].get("_b")
    cat_idx = {}

    def cat(n):
        if n in cat_idx:
            return cat_idx[n]
        b = tax[n].get("_b")
        parent = cat(b) if b else blk["int" if n.startswith("0") else "fed"]
        cat_idx[n] = add("c", parent, n, tlabel(n), id="c" + n)
        return cat_idx[n]
    for n in sorted(need, key=srkey):
        cat(n)

    # decisions and articles per federal act (core), floors and issuers (tree)
    core_by_id = {n["i"]: k for k, n in enumerate(cnodes)}
    tree_by_id = {n["i"]: k for k, n in enumerate(tnodes)}
    act_idx = {}                    # "SR 220" / "K:ZH:700.1" / core id → atlas index
    art_count = {}
    for f in sorted((SRC / "p").glob("*.json")):
        for aid, a in json.load(open(f))["acts"].items():
            art_count[aid] = sum(1 for x in a.get("arts", []) if not (len(x) > 6 and isinstance(x[6], dict) and x[6].get("rep")))

    def fed_act(n, parent, kind="a"):
        aid = "SR " + n
        ci, ti = core_by_id.get(aid, -1), tree_by_id.get(aid, -1)
        cn = cnodes[ci] if ci >= 0 else {}
        tn = tnodes[ti] if ti >= 0 else {}
        fl = 8 if n.startswith("0.") else tn.get("l", -1) if tn.get("l", -1) is not None and tn.get("l", -1) >= 0 else -1
        base = n.split("@")[0]
        fa = (fedacts.get(base) or [{}])
        fv = fa[-1] if "@" not in n else next((v for v in fa if (v.get("date") or "")[:4] == n.split("@")[1]), fa[0])
        title = {lg: plain((fv.get("title") or {}).get(lg)) or tax[base].get(lg) or tax[base].get("de", "") for lg in LANGS}
        ab = {lg: ((cn.get("a") or {}).get(lg) or (fv.get("abbr") or {}).get(lg) or abbr_of(tax[base].get(lg)) or
                   abbr_of(tax[base].get("de")) or "") for lg in LANGS}
        if not ab["en"]:
            ab["en"] = ab["de"]
        if kind == "o":                       # an earlier act: "BV 1874", "aOR"
            y = n.split("@")[1]
            ab = {lg: ("a" + (ab[lg] or base) if y == "a" else (ab[lg] or base) if y in (ab[lg] or "") else
                       f"{ab[lg] or base} {y}" if y != "0000" else (ab[lg] or base)) for lg in LANGS}
        url = (cn.get("e") or eli_in.get(base) or eli_any.get(base) or "").replace("https://fedlex.data.admin.ch/", "https://www.fedlex.admin.ch/")
        k = add(kind, parent, base if kind == "a" else n, {lg: ab[lg] or title[lg] for lg in LANGS}, title,
                id=n, f=fl, d=cn.get("n", 0), n=art_count.get(aid), pk=cn.get("pk") if "pk" in cn else None,
                ad=tn.get("ad") or fv.get("date"), by=tn.get("by"), u=url,
                ab={lg: ab[lg] for lg in LANGS if ab[lg]} if any(ab.values()) else None)
        act_idx[aid] = k
        return k
    heads = set()
    for n in sorted(eli_in, key=srkey):
        ti = tree_by_id.get("SR " + n, -1)
        if ti >= 0 and tnodes[ti].get("ct"):       # the 26 cantonal constitutions (SR 131.2): cantonal law (decision 17)
            continue
        if n in need:                              # an act heading its own group in the SR (412.10 BBG and what executes it)
            parent = cat(n)
            heads.add(n)
        else:
            parent = cat(tax[n]["_b"]) if tax[n].get("_b") else blk["int" if n.startswith("0") else "fed"]
        fed_act(n, parent)
    # earlier federal acts courts cite ("SR 101@1874"), next to today's act
    for k, cn in enumerate(cnodes):
        i = cn["i"]
        if cn["k"] == "act" and i.startswith("SR ") and i not in act_idx and not \
                (i in tree_by_id and tnodes[tree_by_id[i]].get("ct")):
            n = i[3:]
            base = n.split("@")[0]
            here = act_idx.get("SR " + base)
            parent = nodes[here]["p"] if here is not None else cat(tax[base]["_b"]) if tax.get(base, {}).get("_b") else \
                blk["int" if base.startswith("0") else "fed"]
            fed_act(n, parent, kind="o" if "@" in n else "a")

    # ---- cantonal law: the 26 collections in force, then codes courts cite that no act in force carries
    ct_order = tree["method"].get("ct_order") or sorted(cb)
    agg = json.load(open(SRC / "agg.json"))
    ct_order = agg.get("ct_order") or ct_order
    kurl = tree["method"].get("kurl") or {}
    ct_idx = {}
    for ct in ct_order:
        ct_idx[ct] = add("t", blk["kt"], ct, CANTON_NAMES[ct], id=ct)
    for ti, tn in enumerate(tnodes):
        if tn["k"] != "act" or not tn.get("ct") or tn.get("cited"):
            continue
        ct, ksr = tn["ct"], tn.get("ksr")
        rec = cb[ct]["acts"].get(ksr or "", {}) if ksr else {}
        if tn["l"] == 4:                      # the constitution: its SR number in the federal collection
            rec = cb[ct]["acts"].get(cb[ct].get("kv") or "", {})
            ksr = cb[ct].get("kv") or tn["i"][3:]
        i18n = rec.get("i18n") or {}
        title = {lg: (i18n.get(lg) or {}).get("title") or rec.get("title") or tn.get("t") or "" for lg in LANGS}
        ab = {lg: (i18n.get(lg) or {}).get("abbr") or rec.get("abbr") or tn.get("ab") or "" for lg in LANGS}
        ci = tn.get("c", -1)
        if tn["l"] == 4 and ci is not None and ci >= 0 and cnodes[ci].get("a"):     # "KV ZH", "Cst. VD"
            ab = {lg: cnodes[ci]["a"].get(lg) or cnodes[ci]["a"].get("de") or ab[lg] for lg in LANGS}
        d = tn.get("dn") or (cnodes[ci].get("n", 0) if ci is not None and ci >= 0 else 0)
        url = tn.get("u") or rec.get("url") or (kurl.get(ct, "").format(ksr) if kurl.get(ct) else "")
        k = add("a", ct_idx[ct], ksr, {lg: ab[lg] or title[lg] for lg in LANGS}, title, id=f"{ct}/{ksr}", ct=ct,
                f=tn["l"], d=d, ad=tn.get("ad") or rec.get("adopted"), u=url,
                pk=cnodes[ci].get("pk") if ci is not None and ci >= 0 else None,
                ab={lg: ab[lg] for lg in LANGS if ab[lg]} if any(ab.values()) else None,
                fb=rec.get("floor_by") if rec.get("floor_by") in ("Titel", "unbekannt") else None,
                sr=tn["i"][3:] if tn["l"] == 4 else None)
        act_idx[tn["i"]] = k
        if ci is not None and ci >= 0:
            act_idx.setdefault(cnodes[ci]["i"], k)
    for n in heads:
        k, a = cat_idx[n], act_idx["SR " + n]
        for lg in LANGS:
            names[lg]["l"][k] = names[lg]["l"][a]
            names[lg]["t"][k] = names[lg]["t"][a] or names[lg]["t"][k]
        nodes[k]["hd"] = 1
    # cited codes without an act in force, and the pooled small codes ("ZH *")
    nic = {}
    for k, cn in enumerate(cnodes):
        if cn["k"] not in ("act", "bucket") or not cn.get("c") or cn["i"] in act_idx:
            continue
        ct = cn["c"]
        if ct not in nic:
            nic[ct] = add("g", ct_idx[ct], "", NOT_IN_FORCE, id=f"{ct}/-")
        code = cn["i"].split(" ", 1)[1] if " " in cn["i"] else cn["i"]
        lab = OTHER_CODES if cn["k"] == "bucket" else code
        act_idx[cn["i"]] = add("x", nic[ct], code if cn["k"] != "bucket" else "*", lab, None, id=f"{ct}/-{code}", ct=ct,
                               d=cn.get("n", 0), pk=cn.get("pk"), m=cn.get("codes") if cn["k"] == "bucket" else None)

    # distinct decisions per group (decision 14: a decision counts once per area), from core's containers
    dd = {}
    for cn in cnodes:
        if cn["k"] == "root":
            dd["r"] = cn["n"]
        elif cn["k"] == "domain":
            dd[{"CH": "fed", "INT": "int", "KT": "kt"}[cn["i"]]] = cn["n"]
        elif cn["k"] in ("area", "group") and cn.get("sr"):
            dd["c" + cn["sr"]] = cn["n"]
        elif cn["k"] == "canton":
            dd[cn["c"]] = cn["n"]
    for n in nodes:
        key = "r" if n["k"] == "r" else n.get("id")
        if n["k"] in ("r", "b", "c", "t") and dd.get(key):
            n["dd"] = dd[key]

    # ---- children in order: categories and acts by number, cantonal acts by number
    kids = defaultdict(list)
    for k, n in enumerate(nodes):
        if n["p"] >= 0:
            kids[n["p"]].append(k)
    order = {"c": 0, "a": 1, "o": 1, "t": 0, "g": 2, "x": 1}
    for p, ks in kids.items():
        ks.sort(key=lambda k: (order.get(nodes[k]["k"], 0), ct_order.index(nodes[k]["s"]) if nodes[k]["k"] == "t" else 0,
                               srkey(nodes[k]["s"]), nodes[k]["k"] == "o", nodes[k]["s"]))
    # prune categories with nothing below
    alive = set()

    def live(k):
        n = nodes[k]
        below = [live(c) for c in kids.get(k, [])]
        ok = n["k"] in ("a", "o", "x", "t") or any(below)
        if ok:
            alive.add(k)
        return ok
    live(root)
    # renumber in depth-first order (children contiguous)
    newi, seq = {}, []

    def walk(k):
        newi[k] = len(seq)
        seq.append(k)
        for c in kids.get(k, []):
            if c in alive:
                walk(c)
    walk(root)
    out_nodes = []
    for k in seq:
        n = dict(nodes[k])
        n["p"] = newi.get(n["p"], -1)
        out_nodes.append(n)
    remap = lambda k: newi.get(k, -1)
    act_idx = {i: remap(k) for i, k in act_idx.items() if k in newi}
    for lg in LANGS:
        names[lg] = {"l": [names[lg]["l"][k] for k in seq], "t": [names[lg]["t"][k] for k in seq]}
    # in-force counts and decisions for categories (distinct decisions are on the acts; a category shows its acts)
    stats = Counter(n["k"] for n in out_nodes)

    # ---- links: stated bases, co-citation, legislation (atlas indices)
    t2a = {ti: act_idx.get(tn["i"], -1) for ti, tn in enumerate(tnodes) if tn["k"] == "act"}
    for ti, tn in enumerate(tnodes):               # BV articles and KV articles point at their constitution
        if tn["k"] == "bvart":
            t2a[ti] = act_idx.get("SR 101", -1)
        elif tn["k"] == "abv":                       # the 1874 Constitution, where no article of today's is given
            t2a[ti] = act_idx.get("SR 101@1874", act_idx.get("SR 101", -1))
        elif tn["k"] == "kvart":
            t2a[ti] = act_idx.get(next((x["i"] for x in tnodes if x["k"] == "act" and x.get("ct") == tn.get("ct") and x["l"] == 4), ""), -1)
    c2a = {ci: act_idx.get(cn["i"], -1) for ci, cn in enumerate(cnodes)}
    bases = []
    for ti, bl in tree["bases"].items():
        a = t2a.get(int(ti), -1)
        if a < 0:
            continue
        seen = set()
        for b in bl:
            t = t2a.get(b[0], -1) if b[0] is not None and b[0] >= 0 else -1
            if t < 0 or t == a or t in seen:
                continue
            seen.add(t)
            art = tnodes[b[0]].get("n") if tnodes[b[0]]["k"] in ("bvart", "kvart") else None
            arts = [art] if art else [x for x in (b[1] or []) if isinstance(x, str)][:8]
            bases.append([a, t, 1 if (len(b) > 6 and b[6]) else 0, arts])
    cocite = [[c2a[a], c2a[b], n, round(l, 1)] for a, b, n, l in core["edges"] if c2a.get(a, -1) >= 0 and c2a.get(b, -1) >= 0]
    legis = [[c2a[a], c2a[b], w] for a, b, w in core["xedges"] if c2a.get(a, -1) >= 0 and c2a.get(b, -1) >= 0]
    json.dump({"bases": bases, "cocite": cocite, "legis": legis}, open(OUT / "links.json", "w"), separators=(",", ":"), ensure_ascii=False)

    # ---- the hierarchy overview and the matrix, in atlas indices
    hier = {k: agg[k] for k in ("blocks", "basis", "rank", "law", "court", "dec_any", "ct_order")}
    hier["members"] = [[t2a.get(t, -1) for t in m if t2a.get(t, -1) >= 0] for m in agg["members"]]
    hier["flows"] = [[s, d, [t2a.get(t, -1) for t in v if t2a.get(t, -1) >= 0]] for s, d, v in agg["flows"]]
    hier["stubs"] = [[b, g, [t2a.get(t, -1) for t in v if t2a.get(t, -1) >= 0]] for b, g, v in agg["stubs"]]
    hier["low"] = {**agg["low"], "items": [[t2a.get(a, -1), t2a.get(b, -1), c] for a, b, c in agg["low"]["items"]]}
    hier["nb"] = {str(t2a[t]): b for t, b in enumerate(agg["nb"]) if b >= 0 and t2a.get(t, -1) >= 0}
    # the Constitution's parts (title / chapter / section of the BV) by name, in de/fr/it
    hier["bvparts"] = {str(B["k"]): {"num": tnodes[B["k"]].get("num"), "h": tnodes[B["k"]].get("h")}
                       for B in agg["blocks"] if B["r"] == "bv" and isinstance(B["k"], int) and tnodes[B["k"]].get("num")}
    hier["cb"] = {str(c2a[k]): b for k, b in enumerate(agg["cb"]) if b >= 0 and c2a.get(k, -1) >= 0 and str(c2a[k]) not in hier["nb"]}
    json.dump(hier, open(OUT / "hier.json", "w"), separators=(",", ":"), ensure_ascii=False)
    # the matrix's cells, act by act: [row block, column block, act, basis, article of the BV / KV]
    nbt = agg["nb"]
    pairs = [[nbt[me], nbt[tg], t2a.get(me, -1), t2a.get(tg, -1), tnodes[tg].get("n") if tnodes[tg]["k"] in ("bvart", "kvart") else ""]
             for me, tg in agg["pairs"]]
    json.dump(pairs, open(OUT / "pairs.json", "w"), separators=(",", ":"), ensure_ascii=False)

    # ---- articles of cited federal acts
    (OUT / "art").mkdir(exist_ok=True)
    for f in sorted((SRC / "p").glob("*.json")):
        p = json.load(open(f))
        out = {"acts": {}, "dec": p.get("dec", {})}
        for aid, a in p["acts"].items():
            k = act_idx.get(aid, -1)
            if k < 0:
                continue
            arts = []
            for x in a.get("arts", []):
                d = x[6] if len(x) > 6 and isinstance(x[6], dict) else {}
                e = [[act_idx.get(y[0], -1), y[1], y[4], y[5]] for y in d.get("e", []) if act_idx.get(y[0], -1) >= 0]
                arts.append([x[0], x[1], x[5], d.get("l", -1), 1 if d.get("rep") else 0, d.get("y0"), d.get("ys"), d.get("top"), e,
                             d.get("h")])
            out["acts"][str(k)] = {"lv": [[lv[0], lv[1], lv[2], lv[3]] for lv in a.get("levels", [])], "arts": arts,
                                   "top": a.get("top", []), "nf": a.get("nf", [])}
        json.dump(out, open(OUT / "art" / f.name, "w"), separators=(",", ":"), ensure_ascii=False)

    # ---- decisions per year and act
    ys = {}
    for ci, cn in enumerate(cnodes):
        k = c2a.get(ci, -1)
        if k >= 0 and cn.get("ys") and str(k) not in ys:
            ys[str(k)] = [cn["y0"], cn["ys"]]
    json.dump(ys, open(OUT / "years.json", "w"), separators=(",", ":"))

    # ---- the time view (decision 31): the year each act appears (and an earlier act goes), the year each
    # co-citation pair reaches the 20 shared decisions it is drawn from, and decisions per year
    import duckdb
    fd_path = ROOT / "data/fedlex_dates.json"
    fdates = json.load(open(fd_path)) if fd_path.exists() else {}
    year = lambda s: int(s[:4]) if s and str(s)[:4].isdigit() else 0
    born, died, how = [0] * len(out_nodes), {}, Counter()
    for k, n in enumerate(out_nodes):
        kind, s = n["k"], n.get("s") or ""
        if kind not in ("a", "o", "x"):
            continue
        if kind == "x" or s.endswith("@a"):           # codes not in the collection, editions: from their first citation
            y = ys.get(str(k))
            born[k] = y[0] if y else 0
            how["first cited"] += 1
        elif kind == "o":                              # an earlier federal act: while it was in force
            base, at = s.split("@")
            fv = next((v for v in fedacts.get(base, []) if (v.get("date") or "")[:4] == at), None)
            if fv:
                born[k] = year(fv.get("in_force") or fv.get("date"))
                if year(fv.get("repealed")):
                    died[k] = year(fv.get("repealed"))
            how["earlier, in force" if fv else "earlier, undated"] += 1
        elif s.startswith("0.") and not n.get("ct"):   # a treaty: in force for Switzerland
            path = (n.get("u") or "").split("/eli/")[-1]
            recs = fdates.get(s, [])
            r = next((v for v in recs if v["eli"].split("/eli/")[-1] == path), None) or \
                next((v for v in reversed(recs) if not v.get("repealed")), None)
            born[k] = year((r or {}).get("in_force")) or year((r or {}).get("date")) or year(n.get("ad"))
            how["treaty in force" if r and r.get("in_force") else "treaty adopted" if born[k] else "treaty undated"] += 1
        else:                                          # federal and cantonal acts: adopted
            born[k] = year(n.get("ad"))
            how["adopted" if born[k] else "undated"] += 1
    ey = json.load(open(SRC / "ey.json"))
    assert len(ey) == len(core["edges"])
    cy = []
    for e, (a, b, _, _) in zip(ey, core["edges"]):    # aligned with links.cocite
        if c2a.get(a, -1) < 0 or c2a.get(b, -1) < 0:
            continue
        y, cum = 0, 0
        for j, v in enumerate((e or [0, []])[1]):
            cum += v
            if cum >= 20:
                y = e[0] + j
                break
        cy.append(y)
    con = duckdb.connect()
    dec = con.sql(f"""select year(m.dt) y, count(distinct r.decision_id) filter (where m.canton in ('CH', 'CE')) f,
                        count(distinct r.decision_id) filter (where m.canton not in ('CH', 'CE')) k
                      from '{ROOT}/build/refs_valid.parquet' r join '{ROOT}/build/meta.parquet' m using (decision_id)
                      where m.dt is not null group by 1 order by 1""").fetchall()
    undated = con.sql(f"""select count(distinct decision_id) from '{ROOT}/build/refs_valid.parquet' r
                          join '{ROOT}/build/meta.parquet' m using (decision_id) where m.dt is null""").fetchall()[0][0]
    y1 = int((tree["method"].get("run_date") or "2026")[:4])
    dy = {r[0]: r[1:] for r in dec}
    d0 = min(dy)
    json.dump({"y0": 1848, "y1": y1, "born": born, "died": died, "cy": cy,
               "dec": {"y0": d0, "fed": [dy.get(y, (0, 0))[0] for y in range(d0, y1 + 1)],
                       "kt": [dy.get(y, (0, 0))[1] for y in range(d0, y1 + 1)], "undated": undated},
               "how": dict(how)}, open(OUT / "time.json", "w"), separators=(",", ":"))
    print("time:", dict(how), f"{sum(1 for y in cy if y)} of {len(cy)} pairs reach 20 with dated decisions;",
          f"{sum(r[1] + r[2] for r in dec)} dated decisions, {undated} undated")

    # ---- Ingress, issuer, bases with clauses: federal in one file, cantonal per canton
    (OUT / "law").mkdir(exist_ok=True)
    ing_f = json.load(open(SRC / "ingress.json"))
    ing_k = json.load(open(SRC / "ingress_k.json"))
    law = defaultdict(dict)
    for ti, tn in enumerate(tnodes):
        if tn["k"] != "act":
            continue
        a = t2a.get(ti, -1)
        if a < 0:
            continue
        rec = ing_k.get(str(ti)) if tn.get("ct") else ing_f.get(str(ti))
        bl = tree["bases"].get(str(ti), [])
        clauses = rec[2] if rec and len(rec) > 2 else []
        bb = []
        for j, b in enumerate(bl):
            t = t2a.get(b[0], -1) if b[0] is not None and b[0] >= 0 else -1
            art = tnodes[b[0]].get("n") if b[0] is not None and b[0] >= 0 and tnodes[b[0]]["k"] in ("bvart", "kvart") else None
            clause = b[2] or (clauses[j] if j < len(clauses) else "")
            bb.append([t, [art] if art else [x for x in (b[1] or []) if isinstance(x, str)], clause, b[4] if len(b) > 4 else "",
                       1 if len(b) > 6 and b[6] else 0])
        if not rec and not bb:
            continue
        law["F" if not tn.get("ct") else tn["ct"]][str(a)] = [rec[0] if rec else "", rec[1] if rec else "", bb]
    for x, d in law.items():
        json.dump(d, open(OUT / "law" / f"{x}.json", "w"), separators=(",", ":"), ensure_ascii=False)

    # ---- division headings for search
    for lg in LANGS:
        tp = json.load(open(SRC / f"topics.{lg}.json"))
        out = [[c2a.get(ci, -1), eid, h, n, (rest[0] if rest else -1)] for ci, eid, h, n, *rest in tp]   # in order: parents by index
        json.dump(out, open(OUT / f"find.{lg}.json", "w"), separators=(",", ":"), ensure_ascii=False)

    # ---- the index and the names
    FED = "https://www.fedlex.admin.ch/eli/"
    for n in out_nodes:
        u = n.get("u") or ""
        if u.startswith(FED):
            n["u"] = u[len(FED):]
        elif n.get("ct") and kurl.get(n["ct"]) and u == kurl[n["ct"]].format(n["s"]):
            n["u"] = None                              # = the canton's template with the act's number
        if n.get("ab"):
            v = list(dict.fromkeys(n["ab"][lg] for lg in LANGS if n["ab"].get(lg)))
            n["ab"] = "|".join(v)
    fields = ["k", "p", "s", "f", "d", "n", "pk", "ad", "by", "u", "ab", "ct", "fb", "m", "dd", "sr", "hd"]
    meta = {"run": tree["method"].get("run_date"), "decisions": core["nodes"][0].get("n"), "fields": fields,
            "fedlex": FED, "kurl": kurl, "ksym": tree["method"].get("ksym") or {},
            "counts": {"fed_in_force": sum(1 for n in out_nodes if n["k"] == "a" and not n.get("ct") and not n["s"].startswith("0.")),
                       "int_in_force": sum(1 for n in out_nodes if n["k"] == "a" and n["s"].startswith("0.")),
                       "kt_in_force": sum(1 for n in out_nodes if n["k"] == "a" and n.get("ct")),
                       "earlier": sum(1 for n in out_nodes if n["k"] == "o"),
                       "not_in_collection": sum(1 for n in out_nodes if n["k"] == "x")}}
    rows = [[n.get(f) for f in fields] for n in out_nodes]
    for r in rows:                                   # trailing empties off
        while r and r[-1] is None:
            r.pop()
    json.dump({"meta": meta, "nodes": rows}, open(OUT / "atlas.json", "w"), separators=(",", ":"), ensure_ascii=False)
    for lg in LANGS:
        json.dump(names[lg], open(OUT / f"names.{lg}.json", "w"), separators=(",", ":"), ensure_ascii=False)
    method = dict(tree["method"])
    for k in ("tours", "plates"):
        method.pop(k, None)
    json.dump({"tree": method, "core": core.get("method", {})}, open(OUT / "method.json", "w"), separators=(",", ":"), ensure_ascii=False)
    size = sum(f.stat().st_size for f in OUT.rglob("*.json"))
    print(json.dumps(meta["counts"]), dict(stats), f"{size / 1e6:.1f} MB in docs/data")


if __name__ == "__main__":
    main()
