"""Assemble the law repository (decision 36): every version of every act as a commit, dated on the day it applies.

main   — the law as it applied on each day from START (2021-01-01) to TODAY; one commit per act and version
         (the first commit per jurisdiction is its state on START), a deletion when an act ends.
future — main plus the versions Fedlex and the cantons already publish for a later day.
Paths: ch/<area>/<SR>/<lang>.md (area: first digit, international law 0.1 … 0.9), <ct>/<first char>/<number>/<lang>.md.
Cantons: LexWork (19) and Vaud with every version since START; Geneva and Neuchâtel with the text in force only.
Messages are computed from the texts: federal — the AS references in footnotes new in this version; cantonal — the
rows of the canton's change table that took effect on that day. Written with `git fast-import`.

Usage: python3 pipeline/lawgit/build_repo.py <target dir>      (the directory becomes a fresh repository)
"""
import datetime as dt
import gzip
import html
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "build/lawgit"
START = "2021-01-01"
TODAY = dt.date.today().isoformat()
TZ = ZoneInfo("Europe/Zurich")
WHO = "swiss-law · jonashertner.com <noreply@jonashertner.com>"
FOOT = ("\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_01MYoE3wkJdqwAeR8TTwc1B4")
MONTHS = "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split()
CANTON = {"AG": "Aargau", "AI": "Appenzell Innerrhoden", "AR": "Appenzell Ausserrhoden", "BE": "Bern", "BL": "Basel-Landschaft",
          "BS": "Basel-Stadt", "FR": "Freiburg", "GE": "Genf", "GL": "Glarus", "GR": "Graubünden", "JU": "Jura", "LU": "Luzern",
          "NE": "Neuenburg", "NW": "Nidwalden", "OW": "Obwalden", "SG": "St. Gallen", "SH": "Schaffhausen", "SO": "Solothurn",
          "SZ": "Schwyz", "TG": "Thurgau", "TI": "Tessin", "UR": "Uri", "VD": "Waadt", "VS": "Wallis", "ZG": "Zug", "ZH": "Zürich"}


def de_date(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{int(dd)}. {MONTHS[int(m) - 1]} {y}"


def ts(d: str) -> str:
    t = dt.datetime.fromisoformat(d + "T00:00:00").replace(tzinfo=TZ)
    off = t.utcoffset().total_seconds() // 60
    return f"{int(t.timestamp())} {'+' if off >= 0 else '-'}{int(abs(off)) // 60:02d}{int(abs(off)) % 60:02d}"


def day_after(d: str) -> str:
    return (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()


def read_md(p: Path) -> str:
    return gzip.open(p, "rt", encoding="utf-8").read()


# ---- federal
def federal_events():
    V = json.load(open(B / "fedlex_versions.json"))
    H = json.load(open(ROOT / "data/fedlex_history.json"))
    sys.path.insert(0, str(ROOT / "pipeline"))
    import inforce
    srs = {}
    for r in inforce.rows():
        srs.setdefault(r["act"].rstrip("/"), r["notation"])
    ev, acts, stale = [], {}, 0
    occupied = defaultdict(list)                         # path -> [(from, to, act)]
    for act, vs in sorted(V.items()):
        key = act.split("/eli/", 1)[1].replace("/", "_")
        h = H.get(act) or {}
        sr = srs.get(act) or h.get("n") or ""
        vs = [v for v in vs if (v["e"] or "9999") >= START and any((B / "md/ch" / key / f"{v['d']}.{lg}.md.gz").exists() for lg in v["u"])]
        if not vs:
            continue
        end = h.get("repealed") or (day_after(h["end"]) if h.get("end") else "")
        first = max(vs[0]["d"], START)
        last_e = vs[-1]["e"]
        if not end and last_e and last_e < TODAY:
            stale += 1                                   # no later version as XML; the act is not marked as ended: kept
        grp = ("0." + sr[2]) if sr.startswith("0.") and len(sr) > 2 else (sr[:1] or "_")
        base = f"ch/{grp}/{sr or key}"
        span = (first, end or "9999")
        if any(a < span[1] and span[0] < b for a, b, _ in occupied[base]):
            base = f"{base}@{(h.get('date') or first)[:4]}"          # two acts under one number at the same time
        occupied[base].append((*span, act))
        title = (h.get("abbr") or {}).get("de") or ""
        if not title:
            full = re.sub(r"\s+", " ", (h.get("title") or {}).get("de") or "")
            title = full[:60] + ("…" if len(full) > 60 else "")
        acts[act] = {"path": base, "sr": sr, "title": (h.get("title") or {}).get("de", ""), "short": title,
                     "titles": h.get("title") or {}, "abbr": h.get("abbr") or {}}
        prev = {}
        for k, v in enumerate(vs):
            d = max(v["d"], START)
            if end and d >= end:
                break
            files = {lg: B / "md/ch" / key / f"{v['d']}.{lg}.md.gz" for lg in v["u"]}
            files = {lg: p for lg, p in files.items() if p.exists()}
            ev.append({"d": d, "jur": "ch", "act": act, "path": base, "files": files, "kind": "version",
                       "orig": v["d"], "url": act.replace("https://fedlex.data.admin.ch", "https://www.fedlex.admin.ch")
                       + f"/{v['d'].replace('-', '')}/de", "label": f"SR {sr} {title}".strip()})
        if end:
            ev.append({"d": end, "jur": "ch", "act": act, "path": base, "files": {}, "kind": "end",
                       "label": f"SR {sr} {title}".strip()})
    print(f"federal: {len(acts)} acts, {sum(1 for e in ev if e['kind'] == 'version')} versions, "
          f"{sum(1 for e in ev if e['kind'] == 'end')} ends, {stale} acts whose last XML version ended without a recorded end",
          file=sys.stderr)
    return ev, acts


AS_RE = re.compile(r"\[(?:AS|RO|RU) (\d{4}) (\d+)\]\((https://[^)]+)\)")


def notes_of(md: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in re.finditer(r"^\[\^([^\]]+)\]: (.*)$", md, re.M)}


def federal_body(prev_md: str, md: str) -> str:
    new = set(notes_of(md).values()) - set(notes_of(prev_md).values())
    seen, lines = set(), []
    for n in sorted(new):
        for m in AS_RE.finditer(n):
            ref = f"AS {m.group(1)} {m.group(2)}"
            if ref in seen:
                continue
            seen.add(ref)
            txt = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", n)
            txt = re.sub(r"<[^>]+>", "", txt)
            lines.append(f"- {ref}: {txt[:220]}{'…' if len(txt) > 220 else ''}")
    return "\n".join(lines[:25]) + (f"\n- … {len(lines) - 25} weitere" if len(lines) > 25 else "")


# ---- cantonal (LexWork)
DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def iso(m) -> str:
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


def parse_span(s: str) -> dict:
    s = s or ""
    out = {}
    m = DATE.search(s)
    if m:
        out["from"] = iso(m)
    for key, rx in (("to", r"(?:bis|jusqu'au|al)\s*:?\s*"), ("fix", r"(?:berichtigt am|sans procédure formelle le|rettificat\w* il)\s*:?\s*"),
                    ("adopted", r"(?:Beschlussdatum|Erlassdatum|Date d'adoption|Data della decisione)\s*:?\s*")):
        m = re.search(rx + r"(\d{2})\.(\d{2})\.(\d{4})", s)
        if m:
            out[key] = iso(m)
    return out


def repeal_of(s: str) -> str:
    m = re.search(r"(?:\bper|avec effet au|con effetto al)\s+(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return iso(m) if m else ""


def slug(nr: str) -> str:
    return re.sub(r"[^\w.\-]", "_", nr)


def change_rows(version: dict, lang: str, day: str) -> list[str]:
    """Rows of the canton's change table that took effect on `day` (Beschluss, Inkrafttreten, Element, Änderung, Quelle)."""
    out = []
    for t in ((version.get("json_content") or {}).get("modification_table") or []):
        h = (t.get("html_content") or {}).get(lang) or next(iter((t.get("html_content") or {}).values()), "")
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", h or "", re.S):
            cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) >= 4:
                m = DATE.search(cells[1])
                if m and iso(m) == day:
                    out.append(" · ".join(x for x in cells if x))
        if out:
            break
    return out


def cantonal_events():
    ev, acts = [], {}
    stats = defaultdict(int)
    for cdir in sorted((B / "kt").iterdir()):
        if not cdir.is_dir():
            continue
        ct = cdir.name
        lang0 = {"FR": "fr", "VS": "fr"}.get(ct, "de")
        for adir in sorted(cdir.iterdir()):
            if not adir.is_dir() or not (adir / "_act.json.gz").exists():
                continue
            t = json.load(gzip.open(adir / "_act.json.gz", "rt", encoding="utf-8"))
            nr = t.get("systematic_number") or adir.name
            end = repeal_of(t.get("abrogated_dates_str") or "")
            if end and end <= START:
                continue
            vers = [t.get("current_version") or {}] + (t.get("old_versions") or []) + (t.get("future_versions") or [])
            vlist = []
            for v in vers:
                if not v.get("id"):
                    continue
                sp = parse_span(v.get("version_dates_str"))
                if not sp.get("from") or (sp.get("to") or "9999") < START:
                    continue
                d = max(sp.get("fix") or sp["from"], sp["from"], START)
                vlist.append((d, sp, v))
            vlist.sort(key=lambda x: (x[0], x[1].get("fix") or "", x[2]["id"]))
            if not vlist:
                continue
            base = f"{ct.lower()}/{slug(nr)[:1]}/{slug(nr)}"
            short = t.get("abbreviation") or ""
            title = re.sub(r"\s+", " ", t.get("title") or "").strip()
            label = f"{ct} {nr} {short or (title[:60] + ('…' if len(title) > 60 else ''))}".strip()
            acts[(ct, nr)] = {"path": base, "ct": ct, "nr": nr, "title": t.get("title") or "", "short": short,
                              "url": t.get("canonical_link") or ""}
            for d, sp, v in vlist:
                if end and d >= end:
                    break
                mdir = B / "md" / ct.lower() / adir.name
                files = {p.name.split(".")[1]: p for p in mdir.glob(f"{v['id']}.*.md.gz")} if mdir.exists() else {}
                src = adir / f"{v['id']}.json.gz"
                if not files:
                    stats["pdf_or_missing"] += 1
                    files = {"_pdf": (t, v, lang0)}         # a stub pointing to the canton's PDF
                ev.append({"d": d, "jur": ct, "act": (ct, nr), "path": base, "files": files, "kind": "fix" if sp.get("fix") else "version",
                           "src": src, "lang0": lang0, "label": label, "url": t.get("canonical_link") or ""})
                stats["versions"] += 1
            if end:
                ev.append({"d": end, "jur": ct, "act": (ct, nr), "path": base, "files": {}, "kind": "end", "label": label})
                stats["ends"] += 1
    # Vaud (BLV): its own portal, every version since START, acts repealed since START too
    vf = B / "vd/acts.json"
    for r in (json.load(open(vf)) if vf.exists() else []):
        a = r["act"]
        nr = a["cote"]
        end = r.get("abrogated") or ""
        if end and end <= START:
            continue
        base = f"vd/{slug(nr)[:1]}/{slug(nr)}"
        short = a.get("abreviation") or ""
        title = re.sub(r"\s+", " ", a.get("titreCompletSansCote") or a.get("titre") or "").strip()
        label = f"VD {nr} {short or (title[:60] + ('…' if len(title) > 60 else ''))}".strip()
        url = f"https://prestations.vd.ch/pub/blv-publication/actes/consolide/{nr}?id={a['id']}"
        acts[("VD", nr)] = {"path": base, "ct": "VD", "nr": nr, "title": title, "short": short, "url": url}
        vs = sorted((v for v in r["versions"] if not v.get("_error") and v.get("_start")), key=lambda v: (v["_start"], v["htmlId"]))
        for v in vs:
            d = max(v["_start"], START)
            if end and d >= end:
                break
            f = B / "md/vd" / slug(nr) / f"{v['htmlId']}.fr.md.gz"
            if not f.exists():
                stats["vd_missing"] += 1
                continue
            ev.append({"d": d, "jur": "VD", "act": ("VD", nr), "path": base, "files": {"fr": f}, "kind": "version",
                       "src": None, "lang0": "fr", "label": label, "url": url})
            stats["vd_versions"] += 1
        if end:
            ev.append({"d": end, "jur": "VD", "act": ("VD", nr), "path": base, "files": {}, "kind": "end", "label": label})
    # Geneva, Neuchâtel (SIL): only the text in force is published; it enters on the day it took effect (START if
    # earlier), so an act amended since START is absent before its current version applies
    cf = B / "check_sil.json"
    chk = json.load(open(cf)) if cf.exists() else {}
    K = json.load(open(ROOT / "data/cantonal_basis.json"))["cantons"]
    for ct in ("GE", "NE"):
        for nr, a in K[ct]["acts"].items():
            f = B / "md" / ct.lower() / slug(nr) / "current.fr.md.gz"
            if not f.exists():
                stats["sil_missing"] += 1
                continue
            ver = (chk.get(str(f.relative_to(B))) or {}).get("version") or ""
            if not ver:
                stats["sil_no_date"] += 1
            d = max(ver or a.get("adopted") or START, START)
            base = f"{ct.lower()}/{slug(nr)[:1]}/{slug(nr)}"
            title = re.sub(r"\s+", " ", a.get("title") or "").strip()
            short = a.get("abbr") or ""
            label = f"{ct} {nr} {short or (title[:60] + ('…' if len(title) > 60 else ''))}".strip()
            acts[(ct, nr)] = {"path": base, "ct": ct, "nr": nr, "title": title, "short": short, "url": a.get("url") or ""}
            ev.append({"d": d, "jur": ct, "act": (ct, nr), "path": base, "files": {"fr": f}, "kind": "current",
                       "src": None, "lang0": "fr", "label": label, "url": a.get("url") or ""})
            stats[f"sil_{ct}_{'start' if d == START else 'later' if d <= TODAY else 'future'}"] += 1
    print(f"cantonal: {len(acts)} acts, {dict(stats)}", file=sys.stderr)
    return ev, acts


# ---- adopted, not yet in force; consultations (fedlex_pending.py, convert.py pend)
def pending_events():
    """beschlossen/as/<year>/<nr>: an AS act from its publication to its (last) entry into force; beschlossen/bbl/<year>/<nr>:
    a Referendumsvorlage from its publication to its AS publication or, without one, the referendum deadline;
    vernehmlassung/<year>/<nr>: the draft(s) of a consultation from its opening, its status changed when it closes."""
    P = B / "pending"
    ev, stats = [], defaultdict(int)
    if not (P / "as.json").exists():
        return ev
    chk = {}
    cf = B / "check_pend.json"
    if cf.exists():
        chk = json.load(open(cf))
    for kind, sub in (("as", "as"), ("ref", "bbl")):
        for a in json.load(open(P / f"{kind}.json")):
            fam, y, n = a["id"].split("/")[:3]
            files = {lg: B / "md/pend" / kind / (a["id"].replace("/", "_") + f".{lg}.md.gz") for lg in a["xml"]}
            files = {lg: f for lg, f in files.items() if f.exists()}
            if not files:
                stats[f"{kind}_missing"] += 1
                continue
            ref = f"{'AS' if fam == 'oc' else 'BBl'} {y} {n}"
            title = a["title"].get("de") or next(iter(a["title"].values()), "")
            label = f"{ref} {title[:90] + ('…' if len(title) > 90 else '')}"
            if kind == "as":
                end = max(a["eif"])
                why = f"in Kraft seit {de_date(end)}" + (f" (gestaffelt: {', '.join(de_date(d) for d in a['eif'])})" if len(a["eif"]) > 1 else "")
                head = f"{label}: veröffentlicht, tritt am {de_date(end)} in Kraft" if len(a["eif"]) == 1 else \
                       f"{label}: veröffentlicht, tritt gestaffelt in Kraft ({', '.join(de_date(d) for d in a['eif'])})"
            else:
                dl = (chk.get(str(files.get("de", next(iter(files.values()))).relative_to(B))) or {}).get("deadline") or ""
                end = a.get("as_pd") or (day_after(dl) if dl else "")
                why = f"in der Amtlichen Sammlung veröffentlicht ({a['as'].replace('oc/', 'AS ').replace('/', ' ')})" if a.get("as_pd") \
                    else (f"Referendumsfrist am {de_date(dl)} abgelaufen" if dl else "")
                head = f"{label}: Referendumsvorlage" + (f", Referendumsfrist bis {de_date(dl)}" if dl else "")
            if end and end <= START:
                continue
            path = f"beschlossen/{sub}/{y}/{n}"
            url = f"https://www.fedlex.admin.ch/eli/{a['id']}/de"
            ev.append({"d": max(a["pd"], START), "jur": "beschlossen", "act": (sub, a["id"]), "path": path, "files": files,
                       "kind": "pending", "msg": f"{head}\n\nQuelle: {url}", "label": label})
            stats[kind] += 1
            if end:
                ev.append({"d": end, "jur": "beschlossen", "act": (sub, a["id"]), "path": path, "files": {}, "kind": "end",
                           "msg": f"{label}: {why}\n\nQuelle: {url}", "label": label})
    for c in json.load(open(P / "cons.json")):
        if not c["docs"] or (c["end"] and c["end"] < START):
            continue
        y, n = c["id"].split("/")[2:4]
        cn = c["id"].rsplit("/", 1)[1]
        path = f"vernehmlassung/{y}/{n}" + ("" if cn == "cons_1" else f"-{cn.split('_')[1]}")
        files = {}
        for dn, d in sorted(c["docs"].items(), key=lambda kv: int(kv[0].split("_")[1])):
            for lg in d["pdf"]:
                f = B / "md/pend/cons" / (c["id"].replace("/", "_") + f"_{dn}.{lg}.md.gz")
                if f.exists():
                    files[lg if len(c["docs"]) == 1 else f"{dn.replace('_', '-')}.{lg}"] = f
        if not files:
            stats["cons_missing"] += 1
            continue
        title = c["title"].get("de") or next(iter(c["title"].values()), "")
        label = title[:110] + ("…" if len(title) > 110 else "")
        url = f"https://www.fedlex.admin.ch/eli/{c['id']}/de"
        ev.append({"d": max(c["start"], START), "jur": "vernehmlassung", "act": ("vl", c["id"]), "path": path, "files": files,
                   "kind": "pending", "label": label,
                   "msg": f"Vernehmlassung eröffnet: {label}" + (f" (bis {de_date(c['end'])})" if c["end"] else "") + f"\n\nQuelle: {url}"})
        if c["end"]:
            ev.append({"d": day_after(c["end"]), "jur": "vernehmlassung", "act": ("vl", c["id"]), "path": path, "files": files,
                       "kind": "closed", "label": label, "msg": f"Vernehmlassung abgeschlossen: {label}\n\nQuelle: {url}"})
        stats["cons"] += 1
    print(f"pending: {dict(stats)}", file=sys.stderr)
    return ev


def pdf_stub(t: dict, v: dict, lang: str) -> str:
    title = t.get("title") or ""
    pdf = v.get("pdf_link_tol") or t.get("pdf_link") or ""
    note = {"de": "Diese Fassung veröffentlicht der Kanton nur als PDF; ihr Text ist hier nicht wiedergegeben.",
            "fr": "Le canton ne publie cette version qu’en PDF ; son texte n’est pas reproduit ici.",
            "it": "Il Cantone pubblica questa versione solo in PDF; il suo testo non è riprodotto qui."}.get(lang)
    return (f"---\ncanton: {t.get('ct', '')}\nnumber: \"{t.get('systematic_number', '')}\"\ntitle: \"{title}\"\n"
            f"version: \"{v.get('version_dates_str') or ''}\"\nurl: {t.get('canonical_link') or ''}\npdf: {pdf}\ntext: pdf\n---\n\n"
            f"# {title}\n\n{note}\n\n[PDF]({pdf})\n")


# ---- the stream
def message(e, prev_text: dict) -> str:
    d = de_date(e["d"])
    if e.get("msg"):
        return e["msg"]
    if e["kind"] == "end":
        return f"{e['label']}: aufgehoben per {d}"
    if e["kind"] == "current":
        return (f"{e['label']}: Stand {d}\n\nGeltende Fassung. Frühere Fassungen veröffentlicht der Kanton nicht als Text; "
                f"die Änderungen nennt die Tabelle am Ende des Erlasses.\n\nQuelle: {e['url']}")
    if e["kind"] == "fix":
        head = f"{e['label']}: formlos berichtigt, {d}"
    else:
        head = f"{e['label']}: Stand {d}"
    body = ""
    if e["jur"] == "ch":
        de = e["files"].get("de")
        if de and prev_text.get("de"):
            body = federal_body(prev_text["de"], read_md(de))
        if not prev_text:
            body = "Neu in der Sammlung." if e["d"] > START else ""
        body = (body + "\n\n" if body else "") + f"Fedlex: {e['url']}"
    else:
        try:
            if e["jur"] == "VD":
                dd = ".".join(reversed(e["d"].split("-")))
                txt = read_md(e["files"]["fr"])
                rows = sorted({m.group(1) for m in re.finditer(r"^\[\^[^\]]+\]: (.*entrée en vigueur au " + re.escape(dd) + r".*)$", txt, re.M)})
            else:
                v = json.load(gzip.open(e["src"], "rt", encoding="utf-8"))
                rows = change_rows(v, e["lang0"], e["d"])
        except Exception:                                # noqa: BLE001
            rows = []
        body = "\n".join(f"- {r[:240]}" for r in rows[:25])
        body = (body + "\n\n" if body else "") + (f"Quelle: {e['url']}" if e.get("url") else "")
    return head + ("\n\n" + body if body else "")


def stream(out, events: list, branch: str, start_mark: int, parent: str | None, snapshots: dict):
    """Write the commits of `events` to fast-import. snapshots: path -> {lang: text} (the files now in the tree)."""
    mark = start_mark
    first = True
    by_day = defaultdict(list)
    for e in events:
        by_day[e["d"]].append(e)
    for day in sorted(by_day):
        es = by_day[day]
        groups = []
        if day == START:                                   # the state on START: one commit per jurisdiction
            per = defaultdict(list)
            for e in es:
                per[e["jur"]].append(e)
            for jur in sorted(per, key=lambda j: (j != "ch", j)):
                n = len({x["path"] for x in per[jur]})
                name = {"ch": "Bundesrecht", "beschlossen": "Beschlossen, noch nicht in Kraft",
                        "vernehmlassung": "Vernehmlassungen"}.get(jur) or f"Kanton {CANTON.get(jur, jur)}"
                unit = "Vorlagen" if jur == "vernehmlassung" else "Erlasse"
                groups.append((f"{name}: Stand {de_date(START)} ({n:,} {unit})".replace(",", "'"), per[jur], True))
        else:
            for e in sorted(es, key=lambda x: (x["jur"] != "ch", x["jur"], x["path"], x["kind"] == "end")):
                groups.append((None, [e], False))
        for head, group, snap in groups:
            changes, msg = [], head
            for e in group:
                path = e["path"]
                old = snapshots.get(path, {})
                if e["kind"] == "end":
                    for lg in old:
                        changes.append(("D", f"{path}/{lg}.md", None))
                    snapshots.pop(path, None)
                    msg = msg or message(e, old)
                    continue
                new = {}
                for lg, p in e["files"].items():
                    if e["kind"] == "closed":
                        new[lg] = read_md(p).replace("status: Vernehmlassung", "status: Vernehmlassung abgeschlossen", 1)
                        continue
                    if lg == "_pdf":
                        t, v, lang0 = p
                        t = {**t, "ct": e["jur"]}
                        new[lang0] = pdf_stub(t, v, lang0)
                    else:
                        new[lg] = read_md(p)
                if not snap and not msg:
                    msg = message(e, {lg: old[lg] for lg in old})
                for lg in set(old) - set(new):
                    changes.append(("D", f"{path}/{lg}.md", None))
                for lg, txt in new.items():
                    if old.get(lg) != txt:
                        changes.append(("M", f"{path}/{lg}.md", txt))
                snapshots[path] = new
            if not changes:
                continue
            mark += 1
            data = (msg + FOOT).encode()
            out.write(f"commit refs/heads/{branch}\nmark :{mark}\nauthor {WHO} {ts(day)}\ncommitter {WHO} {ts(day)}\n".encode())
            out.write(f"data {len(data)}\n".encode() + data + b"\n")
            if first and parent:
                out.write(f"from {parent}\n".encode())
            first = False
            for op, path, txt in changes:
                if op == "D":
                    out.write(f"D {path}\n".encode())
                else:
                    b = txt.encode()
                    out.write(f"M 100644 inline {path}\ndata {len(b)}\n".encode() + b + b"\n")
    return mark


def write_extra(out, mark: int, branch: str, files: dict, msg: str, day: str) -> int:
    mark += 1
    data = (msg + FOOT).encode()
    out.write(f"commit refs/heads/{branch}\nmark :{mark}\nauthor {WHO} {ts(day)}\ncommitter {WHO} {ts(day)}\n".encode())
    out.write(f"data {len(data)}\n".encode() + data + b"\n")
    for path, txt in files.items():
        b = txt.encode()
        out.write(f"M 100644 inline {path}\ndata {len(b)}\n".encode() + b + b"\n")
    return mark


def main() -> None:
    target = Path(sys.argv[1]).resolve()
    if target.exists() and any(target.iterdir()):
        sys.exit(f"{target} is not empty")
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(target)], check=True)
    fev, facts = federal_events()
    kev, kacts = cantonal_events()
    pev = pending_events()
    events = fev + kev + pev
    main_ev = [e for e in events if e["d"] <= TODAY]
    fut_ev = [e for e in events if e["d"] > TODAY]
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import readme
    p = subprocess.Popen(["git", "fast-import", "--quiet", "--done"], cwd=target, stdin=subprocess.PIPE)
    snaps: dict = {}
    mark = stream(p.stdin, main_ev, "main", 0, None, snaps)
    future = sorted({(e["d"], e["jur"], e["path"], e.get("label") or e["path"]) for e in fut_ev
                     if e["kind"] in ("version", "fix") and not e["path"].startswith(("beschlossen/", "vernehmlassung/"))})
    mark = write_extra(p.stdin, mark, "main", readme.files(snaps, facts, kacts, START, TODAY, future),
                       f"README und Verzeichnisse: Stand {de_date(TODAY)}", TODAY)
    main_mark = mark
    mark = stream(p.stdin, fut_ev, "future", mark, f":{main_mark}", snaps)
    p.stdin.write(b"done\n")
    p.stdin.close()
    if p.wait():
        sys.exit("fast-import failed")
    subprocess.run(["git", "checkout", "-q", "main"], cwd=target, check=True)
    n = subprocess.run(["git", "rev-list", "--count", "main"], cwd=target, capture_output=True, text=True).stdout.strip()
    nf = subprocess.run(["git", "rev-list", "--count", "main..future"], cwd=target, capture_output=True, text=True).stdout.strip()
    print(f"main: {n} commits; future: {nf} more; {len(snaps)} acts in the last tree", file=sys.stderr)


if __name__ == "__main__":
    main()
