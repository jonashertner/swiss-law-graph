"""Step 4a — the data the page loads: site/data/core.json + article packs.

core.json   every circle of the map (domain, area, group, act, canton, bucket)
            with position, exact counts, titles DE/FR/IT/EN, links, per-year
            counts of acts, act co-citation edges [a, b, n, lift], legislative
            cross-references `xedges` [from, to, provisions], search aliases and
            the numbers of the method panel.
ey.json     per co-citation edge (same order as core.edges): [first year,
            decisions per year], loaded with the time slider.
p/<n>.json  articles of a few acts each, loaded when the reader zooms in:
            grid position, citing decisions, years, headings, the act's
            structure, most-cited decisions, article co-citation edges, the acts
            each article's text names (`x`), the act's "not found in the text" bucket.

Article grid: articles keep their order in the official text (Art. 1 top
left, reading order), each top-level unit of the act (book, part, title)
starts on a new row under a blank heading row. Dot radius ~ sqrt(citing
decisions / most cited article of the act); uncited articles are drawn small.
"""
import csv
import gzip
import json
import math
import re
import urllib.parse
from collections import defaultdict
from pathlib import Path

import duckdb

from artnum import parse_eid

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
G = BUILD / "graph"
SITE = ROOT / "site" / "data"
OCL = ROOT.parent / "jonashertner/opencaselaw"
PACK_BYTES = 300_000
TOP_ART, TOP_ACT = 10, 25
LANGS = ("de", "fr", "it", "en")
FEDERAL_COURTS = {"bger": "BGer", "bge": "BGE", "bvger": "BVGer", "bstger": "BStGer", "bpatger": "BPatGer",
                  "ecthr_chamber": "EGMR", "ecthr_gc": "EGMR GC", "mkg": "MKG", "ch_vb": "VPB",
                  "hudoc_ch": "EGMR", "emark": "EMARK"}


def r6(v: float) -> float:
    return float(f"{v:.6g}") if abs(v) < 1 else round(v, 5)


def fedlex_page(eli: str | None) -> str | None:
    if not eli:
        return None
    return eli.replace("https://fedlex.data.admin.ch/eli/", "https://www.fedlex.admin.ch/eli/")


def abbr_from_title(t: str) -> str | None:
    m = re.search(r"\(([^()]*)\)\s*$", t or "")
    if not m:
        return None
    tok = re.split(r"[,;]\s*", m.group(1))[-1].strip()
    if 1 < len(tok) <= 14 and " " not in tok and any(ch.isupper() for ch in tok) and not re.search(r"\d{4}", tok):
        return tok
    return None


def decision_label(did: str, court: str, label: str) -> str:
    rest = did[len(court) + 1:] if did.startswith(court + "_") else did
    if label and "\ufffd" in label:   # corrupt OCR label in the source: show the id instead
        label = rest
    if court == "bge":
        m = re.match(r"(\d+)[ _]([IVX]+[ab]?)[ _](\d+)", rest)
        return f"BGE {int(m.group(1))} {m.group(2)} {int(m.group(3))}" if m else "BGE " + rest
    if court.startswith("ecthr") or court == "hudoc_ch":
        return "EGMR " + re.sub(r"_\d{8}$", "", label or rest)
    short = FEDERAL_COURTS.get(court)
    if short:
        return f"{short} {label or rest}"
    canton, _, name = court.partition("_")
    return f"{canton.upper()} {name.replace('_', ' ').title()} {label or rest}".strip()


def article_grid(cx, cy, R, n_items, breaks):
    """Positions in reading order inside the circle; a blank row precedes each break."""
    Ri, top = R * 0.9, cy - R * 0.9 * 0.74

    def fill(p):
        rows, y = [], top + p / 2
        while y <= cy + Ri - p / 2 + 1e-12:
            half = math.sqrt(max(Ri * Ri - (y - cy) ** 2, 0)) - p / 2
            k = int((2 * half) // p) + 1 if half >= 0 else 0
            rows.append((y, k, cx - (k - 1) * p / 2))
            y += p
        pos, heads, ri, col = [], [], 0, 0
        for i in range(n_items):
            if i in breaks:
                if col:
                    ri, col = ri + 1, 0
                while ri < len(rows) and rows[ri][1] < 3:
                    ri += 1
                if ri >= len(rows):
                    return None
                heads.append((i, rows[ri][2] - p / 2, rows[ri][0]))
                ri += 1
            while ri < len(rows) and rows[ri][1] == 0:
                ri += 1
            if ri >= len(rows):
                return None
            y, k, x0 = rows[ri]
            pos.append((x0 + col * p, y))
            col += 1
            if col >= k:
                ri, col = ri + 1, 0
        return pos, heads

    lo, hi = R * 1e-4, R
    best = None
    for _ in range(40):
        mid = (lo + hi) / 2
        got = fill(mid)
        if got:
            best, lo = (mid, got), mid
        else:
            hi = mid
    if best is None:
        best = (lo, fill(lo))
    p, (pos, heads) = best
    return p, pos, heads


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "p").mkdir(exist_ok=True)
    for f in (SITE / "p").glob("*.json"):
        f.unlink()
    layout = json.load(open(BUILD / "layout.json"))
    tree = json.load(open(BUILD / "hierarchy.json"))
    nodes_meta = json.load(open(BUILD / "act_nodes.json"))
    struct = json.load(gzip.open(ROOT / "data/fedlex_structure.json.gz", "rt"))["acts"]
    lc = json.load(open(OCL / "docs/data/law_codes.json"))

    tax = defaultdict(dict)
    for r in csv.DictReader(open(ROOT / "data/sr_taxonomy.csv", encoding="utf-8")):
        tax[r["notation"]][r["lang"]] = r["label"]
    eli = {}
    for r in csv.DictReader(open(ROOT / "data/sr_eli.csv", encoding="utf-8")):
        if r["notation"] not in eli or (r["inForce"] or "").endswith("/0"):
            eli[r["notation"]] = r["act"]
    fed_abbr = {e["sr_number"]: {k: e.get("abbr_" + k) for k in ("de", "fr", "it") if e.get("abbr_" + k)}
                for e in lc["federal"]}

    # Cantonal titles: only where the official title carries the code and names one law.
    norm = lambda s: re.sub(r"[.\s\-_/]+", "", s or "").upper()
    kidx = defaultdict(list)
    for e in lc["cantonal"]:
        for lang, t in (e.get("titles") or {}).items():
            for m in re.finditer(r"\(([^()]*)\)", t or ""):
                tok = re.split(r"[,;]\s*", m.group(1))[-1].strip()
                if re.fullmatch(r"[A-Za-zÀ-ÿ][\w./\-]{1,14}", tok) and not re.search(r"\d{4}", tok):
                    kidx[(e["canton"], norm(tok))].append((e["systematic_number"], lang, t, e.get("url")))
    ktitle = {k: v[0] for k, v in kidx.items() if len({x[0] for x in v}) == 1}

    c = duckdb.connect()
    acts = {r[0]: r for r in c.sql(f"select * from '{G}/acts.parquet'").fetchall()}
    acols = [d[0] for d in c.sql(f"select * from '{G}/acts.parquet' limit 0").description]
    act_years = defaultdict(list)
    for a, y, n in c.sql(f"select act_id, y, n from '{G}/act_years.parquet' order by act_id, y").fetchall():
        act_years[a].append((y, n))

    # --- Circles. ---
    nodes, index, parent_of = [], {}, {}

    def walk(t, parent):
        index[t["id"]] = len(nodes)
        nodes.append(t)
        parent_of[t["id"]] = parent
        for ch in t.get("children", []):
            walk(ch, t["id"])
    walk(tree, None)

    # Distinct decisions per area (a decision citing two acts of an area counts once).
    anc_rows = []
    for t in nodes:
        if t["kind"] in ("act", "bucket"):
            p = parent_of[t["id"]]
            while p is not None:
                anc_rows.append((t["id"], p))
                p = parent_of[p]
    c.sql("create table anc (act_id varchar, area varchar)")
    c.executemany("insert into anc values (?, ?)", anc_rows)
    bucket_rows = [(f"{a.split(' ', 1)[0]} *", a) for a in acts if not a.startswith("SR ")
                   and f"{a.split(' ', 1)[0]} *" in index and a not in index]
    c.sql("create table bucket (bucket varchar, act_id varchar)")
    c.executemany("insert into bucket values (?, ?)", bucket_rows)
    c.sql(f"""create table ad as select distinct coalesce(b.bucket, r.act_id) act_id, r.decision_id
              from '{BUILD}/refs_valid.parquet' r left join bucket b on b.act_id = r.act_id""")
    area_dec = dict(c.sql("select a.area, count(distinct ad.decision_id) from ad join anc a using (act_id) group by 1").fetchall())
    total_dec = c.sql("select count(distinct decision_id) from ad").fetchall()[0][0]

    out_nodes = []
    for t in nodes:
        x, y, r, depth = layout[t["id"]]
        o = {"i": t["id"], "p": index[parent_of[t["id"]]] if parent_of[t["id"]] else -1,
             "k": t["kind"], "x": r6(x), "y": r6(y), "r": r6(r)}
        kind = t["kind"]
        if kind == "root":
            o["n"] = total_dec
        elif kind in ("domain", "area", "group", "canton"):
            o["n"] = area_dec.get(t["id"], 0)
            if kind in ("area", "group"):
                o["sr"] = t["sr"]
                o["t"] = {k: v for k, v in tax.get(t["sr"], {}).items() if k in LANGS}
            if kind == "canton":
                o["c"] = t["canton"]
        elif kind == "bucket":
            o["n"] = t["decisions"]
            o["codes"] = t["codes"]
        elif kind == "act":
            aid = t["id"]
            o["n"] = t["decisions"]
            row = dict(zip(acols, acts[aid])) if aid in acts else {}
            if row:
                o["f"] = row["decisions_federal"]
                o["nf"] = row["refs_not_in_text"]
                o["nfd"] = row["decisions_not_in_text"]
                o["nt"] = row["refs_no_text"]
            if act_years.get(aid):
                ys = act_years[aid]
                o["y0"] = ys[0][0]
                dense = [0] * (ys[-1][0] - ys[0][0] + 1)
                for yy, n in ys:
                    dense[yy - ys[0][0]] = n
                o["ys"] = dense
            if aid.startswith("SR "):
                sr, _, reg = aid[3:].partition("@")
                o["sr"] = sr
                meta = nodes_meta.get(aid, {})
                if reg:
                    o["reg"] = reg
                    o["t"] = {k: v for k, v in (meta.get("title") or {}).items() if k in LANGS}
                    o["e"] = fedlex_page(meta.get("eli"))
                    if meta.get("in_force"):
                        o["from"] = meta["in_force"]
                    if meta.get("valid_until"):
                        o["to"] = meta["valid_until"]
                else:
                    o["t"] = {k: v for k, v in tax.get(sr, {}).items() if k in LANGS}
                    o["e"] = fedlex_page(eli.get(sr) or meta.get("eli"))
                ab = dict(meta.get("abbr") or {}) or dict(fed_abbr.get(sr, {}))
                if not ab:
                    for lang in ("de", "fr", "it"):
                        a = abbr_from_title(o["t"].get(lang, ""))
                        if a:
                            ab[lang] = a
                ab = {k: v for k, v in ab.items() if k in ("de", "fr", "it", "en")}
                if ab:
                    o["a"] = ab
            else:
                canton, code = aid.split(" ", 1)
                o["c"] = canton
                o["a"] = {"de": code}
                kt = ktitle.get((canton, norm(code)))
                if kt:
                    o["t"] = {kt[1]: kt[2]}
                    o["e"] = kt[3]
        out_nodes.append(o)

    # Act co-citation edges, and per edge the decisions citing both acts by year
    # (ey.json, aligned with core.edges, loaded only when the time slider opens).
    pair_years = defaultdict(list)
    for x, y, yr, n in c.sql(f"select x, y, yr, n from '{G}/act_edge_years.parquet' order by x, y, yr").fetchall():
        pair_years[(x, y)].append((yr, n))
    act_edges, edge_years = [], []
    for x, y, n, l in c.sql(f"select x, y, n, lift from '{G}/act_edges.parquet' order by x, y").fetchall():
        if x not in index or y not in index:
            continue
        act_edges.append([index[x], index[y], n, round(l, 2)])
        ys = pair_years.get((x, y))
        if ys:
            dense = [0] * (ys[-1][0] - ys[0][0] + 1)
            for yy, nn in ys:
                dense[yy - ys[0][0]] = nn
            edge_years.append([ys[0][0], dense])
        else:
            edge_years.append(None)

    # Legislative cross-references (pipeline/fetch_fedlex_xrefs.py): act A's current
    # text names act B's SR number in a footnote or links to it. Weight = number of
    # A's provisions that do so. Only pairs whose two acts are on the map are drawn.
    xedges, art_x, xstats = [], defaultdict(set), None
    xpath = ROOT / "data" / "fedlex_xrefs.json"
    if xpath.exists():
        xr = json.load(open(xpath))
        prov = defaultdict(set)
        xstats = {"run_date": xr["run_date"], "acts_read": 0, "acts_failed": 0, "references": 0,
                  "act_pairs": 0, "act_pairs_on_map": 0, "acts_on_map_with_refs": 0}
        all_pairs = set()
        for sr, rec in xr["acts"].items():
            if rec.get("refs") is None:
                xstats["acts_failed"] += 1
                continue
            xstats["acts_read"] += 1
            xstats["references"] += len(rec["refs"])
            src = f"SR {sr}"
            for eid, tgt in rec["refs"]:
                if tgt == sr:
                    continue
                all_pairs.add((sr, tgt))
                dst = f"SR {tgt}"
                if src in index and dst in index:
                    prov[(src, dst)].add(eid)
                    if eid.startswith("art_"):
                        art_x[(src, eid)].add(index[dst])
        xstats["act_pairs"] = len(all_pairs)
        xstats["act_pairs_on_map"] = len(prov)
        xstats["acts_on_map_with_refs"] = len({s for s, _ in prov})
        xedges = sorted([index[s], index[d], len(e)] for (s, d), e in prov.items())

    # --- Articles. ---
    arts = defaultdict(list)
    for row in c.sql(f"select act_id, art, num, ord, level, rep, h from '{BUILD}/articles.parquet' order by act_id, ord").fetchall():
        arts[row[0]].append(row)
    art_n = {(a, k): n for a, k, n in c.sql(f"select act_id, art, decisions from '{G}/articles.parquet'").fetchall()}
    art_years = defaultdict(list)
    for a, k, y, n in c.sql(f"select act_id, art, y, n from '{G}/art_years.parquet' order by act_id, art, y").fetchall():
        art_years[(a, k)].append((y, n))
    levels = defaultdict(list)
    for a, i, eid, p, num, h in c.sql(f"select act_id, idx, eid, parent, num, h from '{BUILD}/levels.parquet' order by act_id, idx").fetchall():
        levels[a].append((eid, p, json.loads(num), json.loads(h)))

    positions, grids = {}, {}
    for aid, rows in arts.items():
        if aid not in index:
            continue
        x, y, r, _ = layout[aid]
        lv = levels.get(aid, [])

        def chain(li):
            out = []
            while li is not None and li >= 0:
                out.append(li)
                li = lv[li][1]
            return out[::-1]
        chains = [chain(row[4]) if lv else [] for row in rows]
        depth_used, breaks, heads_lv = None, set(), []
        for d in range(0, 3):
            keys = [ch[d] if len(ch) > d else None for ch in chains]
            distinct = {k for k in keys if k is not None}
            if len(distinct) >= 2:
                if len(distinct) <= 40:
                    depth_used = d
                break
        if depth_used is not None:
            prev = object()
            for i, ch in enumerate(chains):
                k = ch[depth_used] if len(ch) > depth_used else None
                if k != prev:
                    breaks.add(i)
                    heads_lv.append(k)
                    prev = k
        p, pos, heads = article_grid(x, y, r, len(rows), breaks)
        nmax = max((art_n.get((aid, row[1]), 0) for row in rows), default=0) or 1
        g = []
        for row, (ax, ay) in zip(rows, pos):
            key = row[1]
            n = art_n.get((aid, key), 0)
            ar = 0.5 * p * (0.3 + 0.66 * math.sqrt(n / nmax)) if n else 0.14 * p
            positions[(aid, key)] = (ax, ay)
            g.append((key, row[2], ax, ay, ar, n, row[4], row[5], json.loads(row[6]) if row[6] else None))
        grids[aid] = (p, g, [(lv[k][2], lv[k][3], hx, hy) if k is not None else ({}, {}, hx, hy)
                             for k, (_, hx, hy) in zip(heads_lv, heads)])

    # Most-cited decisions, decision catalog, article edges.
    tops = defaultdict(list)
    for a, k, did, cb, rk in c.sql(f"select act_id, art, decision_id, cited_by, rk from '{G}/top_decisions.parquet' order by act_id, art, rk").fetchall():
        if k is None or rk <= TOP_ART:
            tops[(a, k)].append(did)
    dec = {}
    for did, court, canton, label, dt, cb in c.sql(
            f"select decision_id, court, canton, label, dt, cited_by from '{G}/decisions.parquet'").fetchall():
        dec[did] = [did, decision_label(did, court, label), str(dt) if dt else None, cb, canton]
    aedges = defaultdict(list)
    for x, y, n, l in c.sql(f"select x, y, n, lift from '{G}/art_edges.parquet'").fetchall():
        ax, ak = x.split("|", 1)
        bx, bk = y.split("|", 1)
        if (ax, ak) in positions and (bx, bk) in positions:
            pa, pb = positions[(ax, ak)], positions[(bx, bk)]
            aedges[(ax, ak)].append([bx, bk, r6(pb[0]), r6(pb[1]), n, round(l, 1)])
            aedges[(bx, bk)].append([ax, ak, r6(pa[0]), r6(pa[1]), n, round(l, 1)])
    nf = defaultdict(list)
    for a, num, n in c.sql(f"select act_id, num, n from '{G}/act_nf.parquet' order by act_id, n desc").fetchall():
        if len(nf[a]) < 30:
            nf[a].append([num, n])

    # --- Packs, in SR order. ---
    order = [n["id"] for n in nodes if n["id"] in grids or (n["kind"] == "act" and (n["id"], None) in tops)]
    packs, cur, cur_size, pack_of = [], {}, 0, {}
    for aid in order:
        g = grids.get(aid)
        rec = {"top": [], "nf": nf.get(aid, [])}
        dids = set(tops.get((aid, None), []))
        rec["top"] = tops.get((aid, None), [])
        if g:
            p, items, heads = g
            rec["p"] = r6(p)
            rec["arts"] = []
            for key, label, ax, ay, ar, n, lvl, rep, h in items:
                a = [key, label, r6(ax), r6(ay), r6(ar), n]
                extra = {}
                if rep:
                    extra["rep"] = 1
                if h:
                    extra["h"] = h
                if lvl is not None and lvl >= 0:
                    extra["l"] = lvl
                ys = art_years.get((aid, key))
                if ys:
                    dense = [0] * (ys[-1][0] - ys[0][0] + 1)
                    for yy, nn in ys:
                        dense[yy - ys[0][0]] = nn
                    extra["y0"], extra["ys"] = ys[0][0], dense
                t = tops.get((aid, key))
                if t:
                    extra["top"] = t
                    dids.update(t)
                e = aedges.get((aid, key))
                if e:
                    extra["e"] = sorted(e, key=lambda z: -z[4] * math.log(z[5]))[:12]
                x = art_x.get((aid, key))
                if x:
                    extra["x"] = sorted(x)
                if extra:
                    a.append(extra)
                rec["arts"].append(a)
            rec["heads"] = [[num, h, r6(hx), r6(hy)] for num, h, hx, hy in heads]
            rec["levels"] = [[e, p_, num, h] for e, p_, num, h in levels.get(aid, [])]
        size = len(json.dumps(rec, ensure_ascii=False)) + 120 * len(dids)
        if cur and cur_size + size > PACK_BYTES:
            packs.append(cur)
            cur, cur_size = {}, 0
        cur[aid] = (rec, dids)
        cur_size += size
    if cur:
        packs.append(cur)
    for i, pk in enumerate(packs):
        alld = sorted({d for _, ds in pk.values() for d in ds if d in dec})
        body = {"acts": {aid: rec for aid, (rec, _) in pk.items()}, "dec": {d: dec[d][1:] for d in alld}}
        json.dump(body, open(SITE / "p" / f"{i}.json", "w"), ensure_ascii=False, separators=(",", ":"))
        for aid in pk:
            pack_of[aid] = i
    for o in out_nodes:
        if o["i"] in pack_of:
            o["pk"] = pack_of[o["i"]]

    # Topic index for search ("Miete", "Ehescheidung"): every structural heading and
    # article heading of the acts, with the first article under it and the number of
    # distinct decisions referring to any article under it. One file per language,
    # loaded at the first search.
    mem = []
    first_art = {}
    for aid, rows in arts.items():
        lv = levels.get(aid)
        if not lv or aid not in index:
            continue
        for row in rows:
            li = row[4]
            while li is not None and li >= 0:
                mem.append((aid, row[1], li))
                first_art.setdefault((aid, li), row[1])
                li = lv[li][1]
    c.sql("create table mem (act_id varchar, art varchar, lvl int)")
    c.executemany("insert into mem values (?, ?, ?)", mem)
    lvl_dec = {(a, l): n for a, l, n in c.sql(f"""select m.act_id, m.lvl, count(distinct r.decision_id)
        from mem m join (select distinct act_id, art, decision_id from '{BUILD}/refs_valid.parquet' where status = 'valid') r
        on r.act_id = m.act_id and r.art = m.art group by 1, 2""").fetchall()}
    for lang in ("de", "fr", "it", "en"):
        pick = lambda d: (d or {}).get(lang) or (d or {}).get("de") or (d or {}).get("fr") or (d or {}).get("it") or ""
        # entry: [node, first article, heading, decisions, parent entry or -1]; search matches
        # a query against the heading and its parents ("Kündigung Arbeitsvertrag").
        topics, pos = [], {}
        for aid, lv in levels.items():
            if aid not in index:
                continue
            for li, (eid, p_, num, h) in enumerate(lv):
                text = " ".join(x for x in (pick(num).strip(), pick(h).strip()) if x)
                if text and (aid, li) in first_art:
                    pos[(aid, li)] = len(topics)
                    topics.append([index[aid], first_art[(aid, li)], text, lvl_dec.get((aid, li), 0),
                                   pos.get((aid, p_), -1)])
        for aid, rows in arts.items():
            if aid not in index:
                continue
            for row in rows:
                h = json.loads(row[6]) if row[6] else None
                n = art_n.get((aid, row[1]), 0)
                if h and pick(h) and n:   # article headings only where decisions cite the article
                    topics.append([index[aid], row[1], f"{row[2]} · {pick(h)}", n, pos.get((aid, row[4]), -1)])
        json.dump(topics, open(SITE / f"topics.{lang}.json", "w"), ensure_ascii=False, separators=(",", ":"))

    # Search aliases: every code the corpus uses for a federal act.
    alias = {}
    for k, v in lc["alias_to_sr"].items():
        if isinstance(v, str) and "SR " + v in index:
            alias[norm(k)] = index["SR " + v]
    for o in out_nodes:
        for a in (o.get("a") or {}).values():
            alias.setdefault(norm(a), index[o["i"]])

    rep = {k: json.load(open(p)) for k, p in (("resolution", BUILD / "resolution_report.json"),
                                              ("validation", BUILD / "validation_report.json"),
                                              ("citations", G / "citations_report.json"))}
    method = {
        "snapshot": "2026-10-26",
        "resolution": rep["resolution"]["by_resolution"],
        "total_references": rep["resolution"]["total_references"],
        "duplicates": rep["resolution"]["duplicate_decisions"],
        "dates": rep["resolution"]["decision_dates"],
        "alias_overrides": rep["resolution"]["alias_overrides"],
        "aliases_added_from_fedlex": len(rep["resolution"]["aliases_added_from_fedlex"]),
        "cantonal_homonyms": rep["resolution"]["cantonal_homonyms"],
        "unverified_homonyms": rep["resolution"]["unverified_homonyms"],
        "not_cantonal": rep["resolution"]["not_cantonal"],
        "glued_codes": rep["resolution"].get("glued_codes", 0),
        "regimes": len(rep["resolution"]["regimes"]),
        "validation": rep["validation"]["by_status"],
        "article_nodes": rep["validation"]["article_nodes"],
        "citations": {k: v for k, v in rep["citations"].items() if k != "co_citation"},
        "co_citation": rep["citations"]["co_citation"],
        "act_edges": len(act_edges),
        "xrefs": xstats,
        "xedges": len(xedges),
    }
    # Titles go to one file per language (a phone loads one): the title in that
    # language, else [title, language] from the first of de/fr/it that has one.
    for lang in LANGS:
        col = []
        for o in out_nodes:
            t = o.get("t") or {}
            if t.get(lang):
                col.append(t[lang])
            else:
                fb = next((l for l in ("de", "fr", "it") if t.get(l)), None)
                col.append([t[fb], fb] if fb else None)
        json.dump(col, open(SITE / f"titles.{lang}.json", "w"), ensure_ascii=False, separators=(",", ":"))
    for o in out_nodes:
        o.pop("t", None)
    core = {"nodes": out_nodes, "edges": act_edges, "xedges": xedges, "alias": alias, "method": method,
            "packs": len(packs)}
    json.dump(core, open(SITE / "core.json", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump(edge_years, open(SITE / "ey.json", "w"), separators=(",", ":"))
    sizes = sorted((f.stat().st_size for f in (SITE / "p").glob("*.json")), reverse=True)
    print(f"core.json {(SITE / 'core.json').stat().st_size / 1e6:.2f} MB, {len(out_nodes)} nodes, "
          f"{len(act_edges)} act edges; {len(packs)} packs, largest {sizes[0] / 1e6:.2f} MB, "
          f"total {sum(sizes) / 1e6:.1f} MB; {sum(len(g[1]) for g in grids.values())} article dots")


if __name__ == "__main__":
    main()
