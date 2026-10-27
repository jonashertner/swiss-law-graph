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
from datetime import date, timedelta
from pathlib import Path
import inforce

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "site" / "data"
OUT = ROOT / "docs" / "data"
LANGS = ("de", "fr", "it", "en")
SITE = "https://jonashertner.github.io/swiss-law-graph/"     # where GitHub Pages serves docs/ (a custom domain: change here)
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
NO_SR = ("Nicht mehr in Kraft, ohne SR-Nummer", "Plus en vigueur, sans numéro RS", "Non più in vigore, senza numero RS",
         "No longer in force, no SR number")


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
    y_run = int((tree["method"].get("run_date") or "2026")[:4])
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
    for r in inforce.rows():                          # Fedlex status corrected by its dates (decision 33)
        eli_any.setdefault(r["notation"], r["act"])
        if inforce.in_force(r):
            eli_in[r["notation"]] = r["act"]
    hist_path = ROOT / "data/fedlex_history.json"     # every act Fedlex has carried, by ELI (decision 32)
    hist = json.load(open(hist_path)) if hist_path.exists() else {}
    day_after = lambda d: (date.fromisoformat(d) + timedelta(days=1)).isoformat()
    TYPE_FLOOR = {21: 1, 22: 1, 28: 1, 8: 1, 9: 1, 7: 1, 36: 1, 10: 1, 4: 1, 5: 1, 19: 1,   # the Federal Assembly
                  29: 2, 3: 2, 15: 2,                                                  # Federal Council, courts, contracts with cantons
                  26: 3, 27: 3, 1: 3, 2: 3, 81: 3, 14: 3,                              # departments, offices, other bodies
                  31: 8, 32: 8, 16: 4}                                                 # treaties; cantonal constitutions

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
        at = n.split("@")[1] if "@" in n else ""         # "1967", or "1986-11" when two acts of the number share a year
        cur = (eli_in.get(base) or "").rstrip("/")     # the act in force: by its ELI, not the last act of the number
        fv = (next((v for v in fa if (v.get("eli") or "").rstrip("/") == cur), None) or hist.get(cur) or fa[-1]) if not at \
            else next((v for v in fa if (v.get("date") or "")[:len(at)] == at), fa[0])
        # an earlier act takes its names from its own record only: the taxonomy describes the act now under the number
        # (BV 1874 had shown "Federal Constitution of 18 April 1999" in English)
        own = lambda d, lg: plain((d or {}).get(lg)) or plain((d or {}).get("de"))
        title = {lg: own(fv.get("title"), lg) or ("" if kind == "o" else tax[base].get(lg) or tax[base].get("de", "")) for lg in LANGS}
        ab = {lg: ((cn.get("a") or {}).get(lg) or (fv.get("abbr") or {}).get(lg) or ("" if kind == "o" else abbr_of(tax[base].get(lg)) or
                   abbr_of(tax[base].get("de"))) or "") for lg in LANGS}
        if not ab["en"]:
            ab["en"] = ab["de"]
        if kind == "o":                       # an earlier act: "BV 1874", "aOR"; a cited number with no act in force: its last act
            y = at or (fv.get("date") or fv.get("in_force") or "0000")[:4]
            # without an abbreviation of its own it is named by its title, not by a bare number ("641.71 1999")
            ab = {lg: ("" if not ab[lg] and title[lg] else "a" + (ab[lg] or base) if y == "a" else (ab[lg] or base) if y in (ab[lg] or "") else
                       f"{ab[lg] or base} {y}" if y != "0000" else (ab[lg] or base)) for lg in LANGS}
        url = ((fv.get("eli") if kind == "o" and not at else None) or cn.get("e") or eli_in.get(base) or eli_any.get(base) or ""
               ).replace("https://fedlex.data.admin.ch/", "https://www.fedlex.admin.ch/")
        hr = hist.get((fv.get("eli") or "").rstrip("/")) or (hist.get(cur, {}) if kind == "a" else {})   # its own record
        if fl == -1 and kind == "a" and hr.get("type") in TYPE_FLOOR:   # no text, so no Ingress (SR 974.4): the document type
            fl = TYPE_FLOOR[hr["type"]]
        end = None if kind != "o" or fv.get("repealed") or hr.get("repealed") else hr.get("end")
        rp = (fv.get("repealed") or hr.get("repealed") or (day_after(end) if end else None)) if kind == "o" else None
        k = add(kind, parent, base if kind == "a" else n, {lg: ab[lg] or title[lg] for lg in LANGS}, title,
                id=n, f=fl, d=cn.get("n", 0), n=art_count.get(aid), pk=cn.get("pk") if "pk" in cn else None,
                ad=tn.get("ad") or fv.get("date"), by=tn.get("by"), u=url, rp=rp, le=end,
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
            # a number courts cite whose acts are all repealed or lapsed (SR 235.3, 831.232.21) is an earlier act too
            fed_act(n, parent, kind="o" if "@" in n or base not in eli_in else "a")

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
    # ---- the federal history (decision 32): every act the federal compilations carried in the SR and repealed
    # since (Fedlex; from the cleaned-up collection of 1948 on), placed by the SR number it carried; the earlier
    # acts courts cite are among them and keep their node. Shown only in the time view (no value today).
    path = lambda u: (u or "").split("/eli/")[-1]
    have = {path(n.get("u")) for n in nodes if n["k"] in ("a", "o") and n.get("u")} | {path(u) for u in eli_in.values()}
    cited = {tuple((n["s"].split("@") + [""])[:2]) for n in nodes if n["k"] == "o"}
    kv_ct = {n["sr"]: n["ct"] for n in nodes if n["k"] == "a" and n.get("ct") and n.get("sr")}
    codes = {n["s"] for n in nodes if n["k"] == "o"}
    hstat = Counter()
    by_sy = {}
    for eli, h in hist.items():
        sr = h.get("hid") or h.get("n")
        if sr:
            by_sy.setdefault((sr, (h.get("date") or "")[:4]), h)
    by_eli = {path(eli): h for eli, h in hist.items()}
    for n in nodes:                                    # the earlier acts courts cite: who made them (for the time view)
        if n["k"] == "o" and n.get("f", -1) in (None, -1):
            h = by_eli.get(path(n.get("u"))) or by_sy.get(tuple(n["s"].split("@")))
            if h:
                n["f"] = 0 if n["s"].startswith("101@") else TYPE_FLOOR.get(h.get("type"), 8 if n["s"].startswith("0.") else -1)

    def place(sr):                                 # next to the act now under the number, else its nearest SR area
        here = act_idx.get("SR " + sr)
        if here is not None:
            return nodes[here]["p"]
        s = sr
        while s:
            if s in tax and s != sr:
                return cat(s)
            if s == sr and tax.get(s, {}).get("_b"):
                return cat(tax[s]["_b"])
            s = s[:-1].rstrip(".")
        return blk["int" if sr.startswith("0") else "fed"]
    nosr = {}                                      # ended before the SR numbered them (mostly before 1970)

    def nosr_group(b):
        if b not in nosr:
            nosr[b] = add("g", blk[b], "", NO_SR, id=f"{b}/-", hg=1)
        return nosr[b]
    run = (tree["method"].get("run_date") or f"{y_run}-12-31")[:10]
    for eli, h in hist.items():
        sr = h.get("hid") or h.get("n") or ""
        st = h.get("status")
        # the end of its force: the repeal, else the day after the end of applicability a temporary act states
        rep = h.get("repealed") or (day_after(h["end"]) if h.get("end") else None)
        y = (h.get("date") or h.get("in_force") or "")[:4]
        if path(eli) in have:
            hstat["on the map"] += 1
            continue
        if not rep or rep > run:                       # no end before the run (an act marked in force may have one: decision 33)
            hstat["in force or not yet" if st in (0, 4) else "no date of its end" if st in (1, 2, 3) else
                  "no status: draft or placeholder" if not h.get("in_force") else
                  "no status: enters into force later" if h["in_force"] > run else "no status: in force by its dates"] += 1
            continue
        if not (sr or y):
            hstat["undated"] += 1
            continue
        hstat["ended: repealed" if h.get("repealed") else "ended: lapsed (end of applicability)"] += 1
        if sr and (sr, y) in cited:                    # an earlier act courts cite: its node is there already
            hstat["cited"] += 1
            continue
        ty = h.get("type")
        treaty = sr.startswith("0.") or (not sr and ty in (31, 32))
        if sr:
            code = f"{sr}@{y}" if y else sr + "@0000"
            k2 = 2
            while code in codes:
                code = f"{sr}@{y}~{k2}"; k2 += 1
        else:                                          # "@1951~3": no number, so no "SR …" and no hash year (#de@1951/)
            k2 = 1
            while f"@{y}~{k2}" in codes:
                k2 += 1
            code = f"@{y}~{k2}"
        codes.add(code)
        ct = kv_ct.get(sr) if ty == 16 else None
        if ty == 16 and not ct:
            hstat["constitution without canton"] += 1
            continue
        title = {lg: plain(h["title"].get(lg) or h["title"].get("de") or h["title"].get("fr") or "") for lg in LANGS}
        ab = {lg: h["abbr"].get(lg) or h["abbr"].get("de") or "" for lg in LANGS}
        ab = {lg: f"{v} {y}" if v and y and y not in v else v for lg, v in ab.items()}     # "OG 1943", as the cited ones
        fl = 0 if sr == "101" else TYPE_FLOOR.get(ty, 8 if treaty else -1)
        parent = ct_idx[ct] if ct else place(sr) if sr else nosr_group("int" if treaty else "fed")
        k = add("o", parent, code, {lg: ab[lg] or title[lg] for lg in LANGS}, title,
                id=code, f=fl, ad=h.get("date"), ct=ct, rp=rep, le=None if h.get("repealed") else h.get("end"), u=eli.replace("https://fedlex.data.admin.ch/", "https://www.fedlex.admin.ch/"),
                ab={lg: ab[lg] for lg in LANGS if ab[lg]} if any(ab.values()) else None)
        start = h.get("in_force") if treaty else h.get("date")
        nodes[k]["_y"] = [int((start or h.get("date") or h.get("in_force") or "0")[:4]), int(rep[:4])]
        hstat[("treaty" if treaty else "constitution" if ty == 16 else "federal act") + ("" if sr else ", no SR number")] += 1
    print("history:", dict(hstat))

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
        elif kind == "o" and n.get("_y"):               # the federal history: from adoption (a treaty: in force) to repeal
            born[k], died[k] = n["_y"]
            how["history"] += 1
        elif kind == "o":                              # an earlier federal act: while it was in force
            base, at = (s.split("@") + [""])[:2]
            fa_ = fedacts.get(base, [])
            fv = next((v for v in fa_ if (v.get("date") or "")[:len(at)] == at), None) if at else (fa_[-1] if fa_ else None)
            if fv:
                born[k] = year(fv.get("in_force") or fv.get("date"))
                nxt = [v["in_force"] for v in fa_ if (v.get("in_force") or "") > (fv.get("in_force") or "9")]
                if year(n.get("rp")):                   # repeal, else the day after its end of applicability
                    died[k] = year(n.get("rp"))
                elif year(fv.get("repealed")):
                    died[k] = year(fv.get("repealed"))
                elif nxt:                               # no repeal date on Fedlex (VEZL 2002): until its successor started
                    died[k] = year(min(nxt))
                    how["earlier, ended by successor"] += 1
            how["earlier, in force" if fv else "earlier, undated"] += 1
        elif s.startswith("0.") and not n.get("ct"):   # a treaty: in force for Switzerland
            path = (n.get("u") or "").split("/eli/")[-1]
            recs = fdates.get(s, [])
            r = next((v for v in recs if v["eli"].split("/eli/")[-1] == path), None) or \
                hist.get("https://fedlex.data.admin.ch/eli/" + path) or \
                next((v for v in reversed(recs) if not v.get("repealed")), None)      # a treaty new to the map: its own record
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
               "how": dict(how), "noend": hstat["no date of its end"]}, open(OUT / "time.json", "w"), separators=(",", ":"))
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

    # ---- the health check (Befund) and what is new (decision 35): lists computed from the same bases as the panels
    basis_f = json.load(open(ROOT / "data/fedlex_basis.json"))["acts"]
    fed_a = lambda n: n["k"] == "a" and not n.get("ct")
    chk = {"run": run, "dangling": [], "repealed": [], "bv1874": [], "olddate": [], "note": [], "nobasis": [], "unchanged": []}
    for ti, bl in tree["bases"].items():
        a = t2a.get(int(ti), -1)
        if a < 0 or out_nodes[a]["k"] != "a":
            continue
        rec = (ing_k if tnodes[int(ti)].get("ct") else ing_f).get(ti)
        clauses = rec[2] if rec and len(rec) > 2 else []
        for j, b in enumerate(bl):
            tgt = b[0] if b[0] is not None and b[0] >= 0 else -1
            t = t2a.get(tgt, -1) if tgt >= 0 else -1
            art = tnodes[tgt].get("n") if tgt >= 0 and tnodes[tgt]["k"] in ("bvart", "kvart") else None
            arts = [art] if art else [x for x in (b[1] or []) if isinstance(x, str)]
            clause = b[2] or (clauses[j] if j < len(clauses) else "")
            via, found = (b[4] if len(b) > 4 else ""), (b[5] if len(b) > 5 else 1)
            row = [a, t, arts, clause, via]
            if tgt >= 0 and not found:                        # articles the target's text today does not contain (07: b[7])
                miss = (b[7] if len(b) > 7 else []) or [[x, "absent"] for x in arts]     # [number, "rep" | "absent"]
                chk["dangling"].append([a, t, miss, clause, via])
            if via in ("hist", "hist→today", "earlier", "absent"):
                chk["repealed"].append(row)                   # an earlier act, or a number with no act in force
            elif via in ("aBV", "aBV→BV", "kvold"):
                chk["bv1874"].append(row)                     # the Constitution of 1874 or an earlier cantonal one
            elif via == "old":
                chk["olddate"].append(row)                    # today's number, the old act's date in the text
            elif via == "note":
                chk["note"].append(row)                       # the footnote names another act than the text
    nob = next((k for k, x in enumerate(tnodes) if x["i"] == "TREE:none"), -1)
    for ti, x in enumerate(tnodes):                           # federal acts whose Ingress names no basis
        a = t2a.get(ti, -1)
        if x["k"] == "act" and not x.get("ct") and x.get("p") == nob and a >= 0 and fed_a(out_nodes[a]) \
                and not (basis_f.get(x["i"][3:]) or {}).get("bases"):
            chk["nobasis"].append(a)
    kt_nob = Counter(); kt_all = Counter()                    # cantonal acts naming no basis, per canton (drafting practice)
    for ti, x in enumerate(tnodes):
        if x["k"] == "act" and x.get("ct") and x.get("l") in (5, 6, 7):
            kt_all[x["ct"]] += 1
            if not tree["bases"].get(str(ti)):
                kt_nob[x["ct"]] += 1
    chk["nobasis_kt"] = {ct: [kt_nob[ct], kt_all[ct]] for ct in sorted(kt_all)}
    for a, n in enumerate(out_nodes):                         # federal acts whose current version dates from before 1990
        if fed_a(n) and not n["s"].startswith("0."):
            v = (basis_f.get(n["s"]) or {}).get("date") or ""
            if v and v < "1990-01-01":
                chk["unchanged"].append([a, v])
    chk["unchanged"].sort(key=lambda r: r[1])
    chk["lower"] = len(agg["low"]["items"])
    why = Counter(r["why"] for r in inforce.rows() if r["why"])
    chk["fedlex"] = {"dates": why["dates"], "ended": why["ended"]}
    json.dump(chk, open(OUT / "check.json", "w"), separators=(",", ":"), ensure_ascii=False)
    print("check:", {k: len(v) if isinstance(v, (list, dict)) else v for k, v in chk.items()})

    since = (date.fromisoformat(run) - timedelta(days=365)).isoformat()
    path_ = lambda u: (u or "").split("/eli/")[-1]
    hist_p = {path_(e): h for e, h in hist.items()}
    new_in, ended, kt_new = [], [], []
    for a, n in enumerate(out_nodes):
        if fed_a(n):
            h = hist_p.get(path_(n.get("u"))) or {}
            f = h.get("in_force") or ""
            if since < f <= run:
                new_in.append([a, f])
        elif n["k"] == "a" and n.get("ct") and since < (n.get("ad") or "") <= run:
            kt_new.append([a, n["ad"]])
        elif n["k"] == "o" and since < (n.get("rp") or "") <= run:
            ended.append([a, n["rp"]])
    for xs in (new_in, ended, kt_new):
        xs.sort(key=lambda r: (r[1], r[0]), reverse=True)
    json.dump({"run": run, "since": since, "in_force": new_in, "ended": ended, "cantonal": kt_new},
              open(OUT / "news.json", "w"), separators=(",", ":"), ensure_ascii=False)
    print(f"news: {len(new_in)} federal acts in force since {since}, {len(ended)} ended, {len(kt_new)} cantonal acts adopted")

    def idof(n):
        return f"{n['ct']}/{n['s']}" if n["k"] == "a" and n.get("ct") else n["s"]
    FEED_T = {"de": ("Atlas des Schweizer Rechts – neu", "In Kraft seit", "Beschlossen am"),
              "fr": ("Atlas du droit suisse – nouveautés", "En vigueur depuis le", "Adopté le"),
              "it": ("Atlante del diritto svizzero – novità", "In vigore dal", "Adottato il"),
              "en": ("Atlas of Swiss Law – new", "In force since", "Adopted on")}
    xe = lambda x: (x or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for lg in LANGS:
        ft, w_in, w_ad = FEED_T[lg]
        items = sorted([(f, a, w_in) for a, f in new_in] + [(d, a, w_ad) for a, d in kt_new], reverse=True)[:300]
        entries = []
        for d, a, w in items:
            n = out_nodes[a]
            lab, tit = names[lg]["l"][a], names[lg]["t"][a]
            head = (f"{n['ct']} " if n.get("ct") else "SR ") + n["s"] + " " + (lab or "")
            url = f"{SITE}#{lg}/{idof(n)}"
            entries.append(f"<entry><title>{xe(head)}</title><id>{xe(url)}</id><updated>{d}T00:00:00Z</updated>"
                           f"<link href=\"{xe(url)}\"/><summary>{xe(w + ' ' + d + (' · ' + tit if tit and tit != lab else ''))}</summary></entry>")
        feed = (f'<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="{lg}">'
                f"<title>{xe(ft)}</title><id>{SITE}feed.{lg}.xml</id><updated>{run}T00:00:00Z</updated>"
                f'<link rel="self" href="{SITE}feed.{lg}.xml"/><link href="{SITE}#{lg}/new"/>'
                f"<author><name>Jonas Hertner</name><uri>https://jonashertner.com</uri></author>" + "".join(entries) + "</feed>\n")
        open(OUT.parent / f"feed.{lg}.xml", "w").write(feed)

    # ---- division headings for search
    for lg in LANGS:
        tp = json.load(open(SRC / f"topics.{lg}.json"))
        out = [[c2a.get(ci, -1), eid, h, n, (rest[0] if rest else -1)] for ci, eid, h, n, *rest in tp]   # in order: parents by index
        json.dump(out, open(OUT / f"find.{lg}.json", "w"), separators=(",", ":"), ensure_ascii=False)

    # ---- the catalogue: every act on the site as one CSV row, for people and programs (and llms.txt to describe the data)
    catalogue(out_nodes, names, born, died, meta_run=tree["method"].get("run_date") or "")

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
    fields = ["k", "p", "s", "f", "d", "n", "pk", "ad", "by", "u", "ab", "ct", "fb", "m", "dd", "sr", "hd", "rp", "hg", "le"]
    meta = {"run": tree["method"].get("run_date"), "decisions": core["nodes"][0].get("n"), "fields": fields,
            "fedlex": FED, "kurl": kurl, "ksym": tree["method"].get("ksym") or {},
            "counts": {"fed_in_force": sum(1 for n in out_nodes if n["k"] == "a" and not n.get("ct") and not n["s"].startswith("0.")),
                       "int_in_force": sum(1 for n in out_nodes if n["k"] == "a" and n["s"].startswith("0.")),
                       "kt_in_force": sum(1 for n in out_nodes if n["k"] == "a" and n.get("ct")),
                       "earlier": sum(1 for n in out_nodes if n["k"] == "o" and not n.get("_y")),
                       "history": sum(1 for n in out_nodes if n.get("_y")),
                       "not_in_collection": sum(1 for n in out_nodes if n["k"] == "x")}}
    rows = [[n.get(f) for f in fields] for n in out_nodes]
    for r in rows:                                   # trailing empties off
        while r and r[-1] is None:
            r.pop()
    json.dump({"meta": meta, "nodes": rows}, open(OUT / "atlas.json", "w"), separators=(",", ":"), ensure_ascii=False)
    # the repealed acts only the time view shows: their names in a file of their own, loaded with it
    hidx = [k for k, n in enumerate(out_nodes) if n.get("_y")]
    for lg in LANGS:
        json.dump({"i": hidx, "l": [names[lg]["l"][k] for k in hidx], "t": [names[lg]["t"][k] for k in hidx]},
                  open(OUT / f"hnames.{lg}.json", "w"), separators=(",", ":"), ensure_ascii=False)
        for k in hidx:
            names[lg]["l"][k] = names[lg]["t"][k] = ""
        json.dump(names[lg], open(OUT / f"names.{lg}.json", "w"), separators=(",", ":"), ensure_ascii=False)
    method = dict(tree["method"])
    for k in ("tours", "plates"):
        method.pop(k, None)
    why = Counter(r["why"] for r in inforce.rows() if r["why"])     # the dates against Fedlex's status (decision 33)
    json.dump({"tree": method, "core": core.get("method", {}),
               "inforce": {"run": inforce.RUN_DATE, "dates": why["dates"], "ended": why["ended"]}},
              open(OUT / "method.json", "w"), separators=(",", ":"), ensure_ascii=False)
    size = sum(f.stat().st_size for f in OUT.rglob("*.json"))
    print(json.dumps(meta["counts"]), dict(stats), f"{size / 1e6:.1f} MB in docs/data")


LEVEL = {0: "constitution", 4: "constitution", 1: "parliament", 5: "parliament", 2: "government", 6: "government",
         3: "administration", 7: "administration", 8: "treaty"}
KINDS = {"a": "in_force", "o": "earlier", "x": "not_in_collection"}
CAT_COLS = ["id", "kind", "jurisdiction", "number", "abbreviation", "title_de", "title_fr", "title_it", "title_en", "level",
            "enacted_by", "adopted", "from_year", "until", "decisions", "source", "page"]


def catalogue(out_nodes, names, born, died, meta_run):
    """docs/data/catalog.csv: one row per act the site holds (in force; earlier federal acts courts cite or Fedlex records;
    codes courts cite that no collection holds), the columns llms.txt explains. kind "earlier" with from/until = an act
    no longer in force; until is the day it ended (repeal, or the day after a temporary act lapsed)."""
    import csv
    rows = []
    for k, n in enumerate(out_nodes):
        kind = KINDS.get(n["k"])
        if not kind:
            continue
        ct, code = n.get("ct") or "", n.get("s") or ""
        sid = (f"{ct}/{code}" if ct else code) if n["k"] == "a" else f"{ct}/-{code}" if n["k"] == "x" else code
        tit = {lg: names[lg]["t"][k] or names[lg]["l"][k] for lg in LANGS}
        if tit["en"] == tit["de"]:                       # no English title (the site falls back to German): left empty here
            tit["en"] = ""
        ab = n.get("ab") or {}
        until = n.get("rp") or ""
        rows.append({"id": sid, "kind": kind, "jurisdiction": ct or ("INT" if code.startswith("0.") or n.get("f") == 8 else "CH"),
                     "number": "" if n["k"] == "x" or code.startswith("@") else code.split("@")[0],
                     "abbreviation": " | ".join(dict.fromkeys(v for v in ab.values() if v)) if isinstance(ab, dict) else ab,
                     **{f"title_{lg}": tit[lg] for lg in LANGS}, "level": LEVEL.get(n.get("f"), ""),
                     "enacted_by": "" if n.get("by") in ("Titel", "unbekannt") else n.get("by") or "", "adopted": n.get("ad") or "", "from_year": born[k] or "",
                     "until": until or (died.get(k) and str(died[k])) or "", "decisions": n.get("d") or 0,
                     "source": n.get("u") or "", "page": f"{SITE}#de/{sid}"})
    with open(OUT / "catalog.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAT_COLS)
        w.writeheader()
        w.writerows(rows)
    c = Counter(r["kind"] for r in rows)
    (OUT.parent / "llms.txt").write_text(f"""# Atlas des Schweizer Rechts / Atlas of Swiss Law

> Every federal and cantonal act of Switzerland in force ({c['in_force']:,} acts), the earlier federal acts ({c['earlier']:,}),
> how each rests on another (the legal bases its preamble states), the cross-references between federal acts, and how often
> courts cite each act and article (decisions from OpenCaseLaw). Data as of {meta_run}. By jonashertner.com. Not official:
> Fedlex and the cantons' collections are authoritative.

## Pages
- {SITE} — the map (DE/FR/IT/EN). Links: `#<lang>/<id>` an act (`#de/220` the OR, `#de/ZH/700.1` a cantonal act,
  `#de/220:art_41` an article), `#<lang>@<year>/…` the same in a past year, `#<lang>/net`, `#<lang>/cantons/<SR>`,
  `#<lang>/check` (gaps and dead references), `#<lang>/new`, `#<lang>/method` (how every number is computed).

## Data (static files, CC0)
- {SITE}data/catalog.csv — one row per act: {", ".join(CAT_COLS)}.
  kind: in_force | earlier (no longer in force; from_year/until its period) | not_in_collection (a code courts cite that no
  collection holds). level: who enacted it (constitution, parliament, government, administration, treaty). decisions:
  distinct published decisions referring to it. source: Fedlex or the canton's page. page: the act on this site.
- {SITE}data/links.json — stated bases, co-citation and legislative cross-references between acts (indices into atlas.json).
- {SITE}data/atlas.json — the tree the map draws (meta.fields names the columns of each node).
- {SITE}feed.de.xml (also fr, it, en) — Atom feed of new federal acts in force and cantonal acts adopted.

## Full text
- https://github.com/jonashertner/swisslaw-git — the law itself as Markdown in git: every version since 2021, one commit
  per version dated on the day it applies; index.csv / index.jsonl list every file; AGENTS.md explains layout and fields.

## Code
- https://github.com/jonashertner/swiss-law-graph — the pipeline (MIT); method and every decision in its CLAUDE.md.
""", encoding="utf-8")
    print(f"catalogue: {len(rows)} rows {dict(c)}")


if __name__ == "__main__":
    main()
