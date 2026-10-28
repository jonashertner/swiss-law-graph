"""Assemble the law repository (decision 36): every version of every act as a commit, dated on the day it applies.

main   — the law as it applied on each day from START (2021-01-01) to TODAY; one commit per act and version
         (the first commit per jurisdiction is its state on START), a deletion when an act ends.
future — main plus the versions Fedlex and the cantons already publish for a later day.
Paths: ch/<area>/<SR>/<lang>.md (area: first digit, international law 0.1 … 0.9), <ct>/<first char>/<number>/<lang>.md.
Cantons: LexWork (19) and Vaud with every version since START; Geneva, Neuchâtel, Zürich, Jura with the text in force.
Messages are computed from the texts: federal — the AS references in footnotes new in this version; cantonal — the
rows of the canton's change table that took effect on that day. Written with `git fast-import`.

Usage: python3 pipeline/lawgit/build_repo.py <target dir>      (the directory becomes a fresh repository)
       python3 pipeline/lawgit/build_repo.py --append <repo dir>   (the weekly run: extends main, rebuilds future)

--append never rewrites main. The tip must equal the state every version known today gives (replayed up to TODAY):
versions published only after the day they apply from ("late": that day is on or before the last run) are committed
first, with the day they apply from as author date and the first day of this run's window as commit date, so that
`git rev-list --before=<day>` keeps meaning "as this repository showed it on that day"; then every version of the
window (last run, TODAY], by day; then README and indexes; `future` is rebuilt on top. An act no event mentions any
more stays as it is (a source that answers partly must not delete law); more than MAX_DROP deletions stop the run.
SWISSLAW_TODAY=YYYY-MM-DD fixes the day (tests).
"""
import os
import datetime as dt
import gzip
import html
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "build/lawgit"
START = "2021-01-01"
TZ = ZoneInfo("Europe/Zurich")
TODAY = os.environ.get("SWISSLAW_TODAY") or dt.datetime.now(TZ).date().isoformat()
WHO = "swiss-law · jonashertner.com <130315719+jonashertner@users.noreply.github.com>"   # GitHub noreply address: commits link to the account
FOOT = ("\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
        "Claude-Session: https://claude.ai/code/session_01MYoE3wkJdqwAeR8TTwc1B4")
if os.environ.get("GITHUB_RUN_ID"):                      # the weekly run: its log is the commit's provenance
    FOOT = (f"\n\nAutomatisch ergänzt: {os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
            f"{os.environ.get('GITHUB_REPOSITORY', 'jonashertner/swisslaw-git')}/actions/runs/{os.environ['GITHUB_RUN_ID']}")
MAX_DROP = 0.03     # --append stops when a run would repeal more than this share of a jurisdiction's acts (ch/, cantons/)
MAX_LATE = 400      # … or change more files after the fact: a converter changed, not the law (SWISSLAW_REFORMAT=1)
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
    return clean_headings(gzip.open(p, "rt", encoding="utf-8").read())


CALL = re.compile(r"\[\^[^\]\s]+\](?!:)")
SUP_CALLS = re.compile(r"<sup>\s*((?:\[\^[^\]\s]+\]\s*)+)</sup>")


def clean_headings(md: str) -> str:
    """A heading holds the designation only. GitHub takes a heading's anchor from its rendered text, footnote numbers
    included ("#### Art. 6a[^6a-1]" → #art-6a1, the number set by the note's place in the file): the calls move to the
    article's marginal title below it, after the line below the act's title, or onto a line of their own, so
    ch/2/220/de.md#art-6a always works. A call set raised (<sup>[^…]</sup>) is written as a plain call."""
    lines = SUP_CALLS.sub(lambda m: re.sub(r"\s+", "", m.group(1)), md).split("\n")
    out, k = [], 0
    while k < len(lines):
        line = lines[k]
        if not (line.startswith("#") and re.match(r"#{1,6} ", line) and CALL.search(line)):
            out.append(line)
            k += 1
            continue
        calls = "".join(CALL.findall(line))
        head = re.sub(r"\s{2,}", " ", CALL.sub("", line)).rstrip()
        out.append(head)
        j = k + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        nxt = lines[j].strip() if j < len(lines) else ""
        if head.startswith("#### ") and re.fullmatch(r"\*\*.+?\*\*(?:\[\^[^\]\s]+\])*", nxt):    # the marginal title
            out += lines[k + 1:j] + [re.sub(r"^(\s*\*\*.+?\*\*)", lambda x: x.group(1) + calls, lines[j], count=1)]
            k = j + 1
        elif head.startswith("# ") and nxt and not re.match(r"[#|<>\-]", nxt):                  # the act's title
            out += lines[k + 1:j] + [lines[j].rstrip() + calls]
            k = j + 1
        else:
            out += ["", calls]
            k += 1
    return "\n".join(out)


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


def in_force_acts(ct: str) -> dict:
    """The acts in force ZH, GE, NE, JU list: the adapter's own output (pipeline/cantonal/<ct>.py, fresh in a weekly run),
    else data/cantonal_basis.json (the same records: checked equal for all four on 2026-10-27)."""
    f = ROOT / "build/cantonal" / f"{ct}.json"
    if f.exists():
        return {r["sr"]: r for r in json.load(open(f)) if r.get("in_force", True)}
    return json.load(open(ROOT / "data/cantonal_basis.json"))["cantons"][ct]["acts"]


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
            base = f"cantons/{ct.lower()}/{slug(nr)[:1]}/{slug(nr)}"
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
                           "src": src, "lang0": lang0, "label": label, "url": t.get("canonical_link") or "", "orig": sp["from"]})
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
        base = f"cantons/vd/{slug(nr)[:1]}/{slug(nr)}"
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
                       "src": None, "lang0": "fr", "label": label, "url": url, "orig": v["_start"]})
            stats["vd_versions"] += 1
        if end:
            ev.append({"d": end, "jur": "VD", "act": ("VD", nr), "path": base, "files": {}, "kind": "end", "label": label})
    # Geneva, Neuchâtel (SIL), Zürich, Jura (PDF): only the text in force here; it enters on the day it took effect
    # (START if earlier), so an act amended since START is absent before its current version applies
    chk = {}
    for name in ("check_sil.json", "check_pdfcur.json"):
        cf = B / name
        if cf.exists():
            chk.update(json.load(open(cf)))
    zf = B / "zh/acts.json"
    zh_hist = zf.exists()
    if zh_hist:                                          # Zürich: every version since START, from the canton's PDFs
        zc = json.load(open(B / "check_zh.json")) if (B / "check_zh.json").exists() else {}
        KZ = in_force_acts("ZH")
        for r in json.load(open(zf)):
            nr = r["sr"]
            a = KZ.get(nr) or {}
            base = f"cantons/zh/{slug(nr)[:1]}/{slug(nr)}"
            title = re.sub(r"\s+", " ", a.get("title") or "").strip()
            short = a.get("abbr") or ""
            label = f"ZH {nr} {short or (title[:60] + ('…' if len(title) > 60 else ''))}".strip()
            acts[("ZH", nr)] = {"path": base, "ct": "ZH", "nr": nr, "title": title, "short": short, "url": a.get("url") or ""}
            vs, prev_end = [], ""
            for v in r["versions"]:                      # in the order of the Nachträge
                f = B / "md/zh" / slug(nr) / f"{v['key']}.de.md.gz"
                if not f.exists():
                    stats["zh_missing"] += 1
                    continue
                own = (zc.get(str(f.relative_to(B))) or {}).get("version") or ""
                # "in Kraft bis 01.07.2024": the next version applies from that day; "bis 31.12.2002": from the day after
                after = (prev_end if prev_end.endswith("-01") else day_after(prev_end)) if prev_end else ""
                start = own if own and (not after or own >= after) else (after or own or START)
                vs.append((max(start, START), v, f))
                prev_end = v.get("end") or prev_end
            vs.sort(key=lambda x: (x[0], x[1]["nachtrag"]))
            keep = [x for k, x in enumerate(vs) if k + 1 == len(vs) or vs[k + 1][0] > x[0]]   # superseded the same day: the later one
            for d, v, f in keep:
                ev.append({"d": d, "jur": "ZH", "act": ("ZH", nr), "path": base, "files": {"de": f}, "kind": "zh", "orig": d,
                           "src": None, "lang0": "de", "label": label, "url": "https://www.zh.ch" + v["link"],
                           "msg": f"{label}: Stand {de_date(d)} (Nachtrag {v['nachtrag']:03d})\n\nText aus dem PDF des Kantons "
                                  f"gelesen.\n\nQuelle: https://www.zh.ch{v['link']}"})
                stats["zh_versions"] += 1
    for ct, lg in (("GE", "fr"), ("NE", "fr"), ("ZH", "de"), ("JU", "fr")):   # ZH, JU: read from the canton's PDF
        if ct == "ZH" and zh_hist:
            continue
        for nr, a in in_force_acts(ct).items():
            f = B / "md" / ct.lower() / slug(nr) / f"current.{lg}.md.gz"
            if not f.exists():
                stats["sil_missing"] += 1
                continue
            ver = (chk.get(str(f.relative_to(B))) or {}).get("version") or ""
            if not ver:
                stats["sil_no_date"] += 1
            d = max(ver or a.get("adopted") or START, START)
            base = f"cantons/{ct.lower()}/{slug(nr)[:1]}/{slug(nr)}"
            title = re.sub(r"\s+", " ", a.get("title") or "").strip()
            short = a.get("abbr") or ""
            label = f"{ct} {nr} {short or (title[:60] + ('…' if len(title) > 60 else ''))}".strip()
            acts[(ct, nr)] = {"path": base, "ct": ct, "nr": nr, "title": title, "short": short, "url": a.get("url") or ""}
            ev.append({"d": d, "jur": ct, "act": (ct, nr), "path": base, "files": {lg: f}, "kind": "current",
                       "src": None, "lang0": lg, "label": label, "url": a.get("url") or "", "orig": ver or a.get("adopted") or ""})
            stats[f"sil_{ct}_{'start' if d == START else 'later' if d <= TODAY else 'future'}"] += 1
    print(f"cantonal: {len(acts)} acts, {dict(stats)}", file=sys.stderr)
    return ev, acts


# ---- adopted, not yet in force; consultations (fedlex_pending.py, convert.py pend)
def pending_events():
    """adopted/as/<year>/<nr>: an AS act from its publication to its (last) entry into force; adopted/bbl/<year>/<nr>:
    a Referendumsvorlage from its publication to its AS publication or, without one, the referendum deadline;
    consultations/<year>/<nr>: the draft(s) of a consultation from its opening, its status changed when it closes."""
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
                end = a.get("rejected") or a.get("as_pd") or (day_after(dl) if dl else "")
                why = f"in der Volksabstimmung vom {de_date(a['rejected'])} abgelehnt" if a.get("rejected") else \
                    f"in der Amtlichen Sammlung veröffentlicht ({a['as'].replace('oc/', 'AS ').replace('/', ' ')})" if a.get("as_pd") \
                    else (f"Referendumsfrist am {de_date(dl)} abgelaufen" if dl else "")
                head = f"{label}: Referendumsvorlage" + (f", Referendumsfrist bis {de_date(dl)}" if dl else "")
            if end and end <= START:
                continue
            path = f"adopted/{sub}/{y}/{n}"
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
        path = f"consultations/{y}/{n}" + ("" if cn == "cons_1" else f"-{cn.split('_')[1]}")
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
            f"version: \"{v.get('version_dates_str') or ''}\"\nurl: {t.get('canonical_link') or ''}\npdf: {pdf}\ntext: link\n---\n\n"
            f"# {title}\n\n{note}\n\n[PDF]({pdf})\n")


# ---- the stream
def message(e, prev_text: dict) -> str:
    d = de_date(e["d"])
    if e.get("msg"):
        return e["msg"]
    if e["kind"] == "end":
        return f"{e['label']}: aufgehoben per {d}"
    if e["kind"] == "current":
        why = {"GE": "Frühere Fassungen veröffentlicht der Kanton nicht als Text; die Änderungen nennt die Tabelle am Ende des Erlasses.",
               "NE": "Frühere Fassungen veröffentlicht der Kanton nicht als Text; die Änderungen nennen die Fussnoten.",
               "ZH": "Text aus dem PDF des Kantons gelesen; frühere Fassungen folgen.",
               "JU": "Text aus dem PDF des Kantons gelesen; die Änderungen nennen die Fussnoten."}.get(e["jur"], "")
        return f"{e['label']}: Stand {d}\n\nGeltende Fassung. {why}\n\nQuelle: {e['url']}"
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


def day_groups(day: str, es: list) -> list:
    """The commits of one day, in order: (head or None, events, one commit for all)."""
    groups = []
    if day == START:                                       # the state on START: one commit per jurisdiction
        per = defaultdict(list)
        for e in es:
            per[e["jur"]].append(e)
        for jur in sorted(per, key=lambda j: (j != "ch", j)):
            n = len({x["path"] for x in per[jur]})
            name = {"ch": "Bundesrecht", "beschlossen": "Beschlossen, noch nicht in Kraft",
                    "vernehmlassung": "Vernehmlassungen"}.get(jur) or f"Kanton {CANTON.get(jur, jur)}"
            unit = "Vorlagen" if jur == "vernehmlassung" else "Erlasse"
            groups.append((f"{name}: Stand {de_date(START)} ({n:,} {unit})".replace(",", "'"),
                           sorted(per[jur], key=lambda x: x["kind"] != "end"), True))
    else:
        # an act that ends on the day another begins under its number (a successor, SR 0.142.112.739 in 2025): the end first
        for e in sorted(es, key=lambda x: (x["jur"] != "ch", x["jur"], x["path"], x["kind"] != "end")):
            groups.append((None, [e], False))
    return groups


def by_days(events: list) -> list:
    by_day = defaultdict(list)
    for e in events:
        by_day[e["d"]].append(e)
    return [(day, by_day[day]) for day in sorted(by_day)]


def apply(e, snapshots: dict) -> tuple[list, dict]:
    """Apply one event to the tree `snapshots` (path -> {lang: text}); returns the changes and the files before."""
    path = e["path"]
    old = snapshots.get(path, {})
    changes = []
    if e["kind"] == "end":
        for lg in old:
            changes.append(("D", f"{path}/{lg}.md", None))
        snapshots.pop(path, None)
        return changes, old
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
    for lg in set(old) - set(new):
        changes.append(("D", f"{path}/{lg}.md", None))
    for lg, txt in new.items():
        if old.get(lg) != txt:
            changes.append(("M", f"{path}/{lg}.md", txt))
    snapshots[path] = new
    return changes, old


def replay(events: list, snapshots: dict) -> dict:
    """The tree the commits of `events` give, without writing them; path -> last event applied."""
    last = {}
    for day, es in by_days(events):
        for _, group, _ in day_groups(day, es):
            for e in group:
                apply(e, snapshots)
                last[e["path"]] = e
    return last


def write_commit(out, mark: int, branch: str, msg: str, day: str, changes: list, parent: str | None = None,
                 committed: str | None = None) -> int:
    mark += 1
    data = (msg + FOOT).encode()
    out.write(f"commit refs/heads/{branch}\nmark :{mark}\nauthor {WHO} {ts(day)}\ncommitter {WHO} {ts(committed or day)}\n".encode())
    out.write(f"data {len(data)}\n".encode() + data + b"\n")
    if parent:
        out.write(f"from {parent}\n".encode())
    for op, path, txt in changes:
        if op == "D":
            out.write(f"D {path}\n".encode())
        else:
            b = txt.encode()
            out.write(f"M 100644 inline {path}\ndata {len(b)}\n".encode() + b + b"\n")
    return mark


def stream(out, events: list, branch: str, start_mark: int, parent: str | None, snapshots: dict, days: list | None = None):
    """Write the commits of `events` to fast-import. snapshots: path -> {lang: text} (the files now in the tree).
    days: if given, receives (day, mark of the last commit of that day) for the tags."""
    mark = start_mark
    for day, es in by_days(events):
        for head, group, snap in day_groups(day, es):
            changes, msg = [], head
            for e in group:
                ch, old = apply(e, snapshots)
                changes += ch
                if not msg and (e["kind"] == "end" or not snap):
                    msg = message(e, old)
            if not changes:
                continue
            mark = write_commit(out, mark, branch, msg, day, changes, parent if mark == start_mark else None)
        if days is not None and mark > start_mark:
            days.append((day, mark))
    return mark


def month_tags(out, days: list) -> int:
    """stand/<YYYY-MM-01>: the law as it applied on the first of every month (the last commit of that day or before)."""
    n, k = 0, 0
    y, m = int(START[:4]), int(START[5:7])
    while f"{y:04d}-{m:02d}-01" <= TODAY:
        d = f"{y:04d}-{m:02d}-01"
        while k + 1 < len(days) and days[k + 1][0] <= d:
            k += 1
        if days and days[k][0] <= d:
            out.write(f"reset refs/tags/stand/{d}\nfrom :{days[k][1]}\n\n".encode())
            n += 1
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return n


def write_extra(out, mark: int, branch: str, files: dict, msg: str, day: str) -> int:
    mark += 1
    data = (msg + FOOT).encode()
    out.write(f"commit refs/heads/{branch}\nmark :{mark}\nauthor {WHO} {ts(day)}\ncommitter {WHO} {ts(day)}\n".encode())
    out.write(f"data {len(data)}\n".encode() + data + b"\n")
    for path, txt in files.items():
        b = txt.encode()
        out.write(f"M 100644 inline {path}\ndata {len(b)}\n".encode() + b + b"\n")
    return mark


LAW = ("ch/", "cantons/", "adopted/", "consultations/")
IN_FORCE_ONLY = ("zh", "ge", "ne", "ju")              # cantons whose lists hold the acts in force only


def tree_of(repo: Path) -> dict:
    """The law files of main's tip: act path -> {lang: text} (README.md of the folders are not law)."""
    files = subprocess.run(["git", "ls-files", "-z"], cwd=repo, capture_output=True, text=True, check=True).stdout.split("\0")
    t: dict = {}
    for f in files:
        if f.startswith(LAW) and f.endswith(".md") and not f.endswith("/README.md"):
            path, name = f.rsplit("/", 1)
            t.setdefault(path, {})[name[:-3]] = (repo / f).read_text(encoding="utf-8")
    return t


def git(repo: Path, *a) -> str:
    return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def readme_counts(main_ev: list) -> Counter:
    VK = ("version", "fix", "zh", "current", "pending")
    nver = Counter(("ch" if e["jur"] == "ch" else "adopted" if e["jur"] == "beschlossen" else
                    "consultations" if e["jur"] == "vernehmlassung" else "cantons") for e in main_ev if e["kind"] in VK)
    nver.update(f"ct:{e['jur']}" for e in main_ev if e["kind"] in VK and e["jur"] not in ("ch", "beschlossen", "vernehmlassung"))
    return nver


def future_list(fut_ev: list) -> list:
    return sorted({(e["d"], e["jur"], e["path"], e.get("label") or e["path"]) for e in fut_ev
                   if e["kind"] in ("version", "fix") and not e["path"].startswith(("adopted/", "consultations/"))})


def write_paths(snaps: dict, facts: dict, kacts: dict) -> None:
    """For the atlas (08_web.py): where each act in force lives at the end of main, and in which languages."""
    where = {"ch": {a["sr"]: [a["path"], sorted(snaps[a["path"]])] for a in facts.values() if a.get("sr") and a["path"] in snaps},
             "kt": {f"{a['ct']}/{a['nr']}": [a["path"], sorted(snaps[a["path"]])] for a in kacts.values() if a["path"] in snaps}}
    json.dump(where, open(B / "repo_paths.json", "w"), ensure_ascii=False)


def append(repo: Path) -> None:
    """The weekly run (see the module's docstring)."""
    import readme
    if git(repo, "rev-parse", "--abbrev-ref", "HEAD") != "main" or git(repo, "status", "--porcelain"):
        sys.exit(f"{repo}: main must be checked out and clean")
    tip = git(repo, "rev-parse", "main")
    last = subprocess.run(["git", "log", "-1", "--format=%cd", "--date=format-local:%Y-%m-%d", "main"], cwd=repo,
                          capture_output=True, text=True, check=True, env={**os.environ, "TZ": "Europe/Zurich"}).stdout.strip()
    if TODAY < last:
        sys.exit(f"TODAY {TODAY} is before the last run {last}")
    window = min(day_after(last), TODAY)                 # the commit date of late versions: the first day of this window
    fev, facts = federal_events()
    kev, kacts = cantonal_events()
    events = fev + kev + pending_events()
    known = {e["path"] for e in events}
    T = tree_of(repo)
    # the state the versions known today give on the last run's day, against what main shows
    S: dict = {}
    last_ev = replay([e for e in events if e["d"] <= last], S)
    kinds = defaultdict(set)
    first_day = {}
    for e in events:
        kinds[e["path"]].add(e["kind"])
        first_day[e["path"]] = min(first_day.get(e["path"], "9999"), e["d"])
    for p in T:
        if p not in known:                               # no source mentions it this time: kept as it is
            S[p] = T[p]
        elif p not in S and kinds[p] == {"current"} and first_day[p] > last:
            S[p] = T[p]                                  # GE, NE, JU give the text in force only: the one main shows stood until now
    # Zürich, Geneva, Neuchâtel and Jura list the acts in force only: an act that left the list was repealed (the day is
    # not given: the first day of this window). Only a few at a time (≤ 5 or 3 % of the canton's acts): more means the
    # list came back incomplete — then nothing of that canton is removed and the run says so.
    vanished = []
    for ct in IN_FORCE_ONLY:
        mine = [q for q in T if q.startswith(f"cantons/{ct}/")]
        gone = [q for q in mine if q not in known]
        if mine and len(gone) <= max(5, 0.03 * len(mine)):
            vanished += gone
        elif gone:
            print(f"::warning::{ct.upper()}: {len(gone)} of {len(mine)} acts not in the canton's list this time — taken as "
                  f"an incomplete list, all kept", file=sys.stderr)
    for q in vanished:
        f = (T[q].get("de") or T[q].get("fr") or next(iter(T[q].values())))
        fm = dict(re.findall(r'^(number|short|title): "?(.*?)"?$', f.split("\n---", 1)[0], re.M))
        ct = q.split("/")[1].upper()
        label = f"{ct} {fm.get('number', '')} {fm.get('short') or fm.get('title', '')[:60]}".strip()
        events.append({"d": window, "jur": ct, "act": (ct, fm.get("number", q)), "path": q, "files": {}, "kind": "end",
                       "label": label, "msg": f"{label}: nicht mehr in der Sammlung des Kantons (aufgehoben)\n\n"
                                              f"Der Kanton nennt das Datum der Aufhebung nicht; festgestellt am {de_date(window)}."})
        known.add(q)
        kinds[q].add("end")
        first_day[q] = min(first_day.get(q, "9999"), window)
        S[q] = T[q]                                      # it stood until this window
    unknown = sum(1 for p in T if p not in known)
    late = sorted((p for p in set(S) | set(T) if S.get(p) != T.get(p)), key=lambda p: (last_ev[p]["d"] if p in last_ev else "", p))
    drops = [p for p in late if p not in S]
    print(f"append: last run {last}, today {TODAY}; {len(T)} acts in main, {unknown} not in any source this time (kept); "
          f"{len(late)} late ({len(drops)} of them ended)", file=sys.stderr)
    window_ev = [e for e in events if last < e["d"] <= TODAY]
    # guards: repeals are normal (1 January), a share of a jurisdiction gone at once is not; nor are hundreds of
    # files changed after the fact (that is a converter changed: rerun with SWISSLAW_REFORMAT=1, one commit)
    jur_of = lambda q: q.split("/")[1] if q.startswith("cantons/") else "ch" if q.startswith("ch/") else ""
    size = Counter(jur_of(q) for q in T)
    gone = Counter(jur_of(q) for q in drops + [e["path"] for e in window_ev if e["kind"] == "end" and e["path"] in T])
    over = {j: n for j, n in gone.items() if j and n > max(25, MAX_DROP * size[j])}
    if over and not os.environ.get("SWISSLAW_ALLOW_DROPS"):
        sys.exit(f"repeals above {MAX_DROP:.0%} of a jurisdiction in one run: {over}; a source may be wrong. "
                 f"Check them, then rerun with SWISSLAW_ALLOW_DROPS=1.")
    reformat = bool(os.environ.get("SWISSLAW_REFORMAT"))
    if len(late) > MAX_LATE and not reformat:
        sys.exit(f"{len(late)} acts differ from what main shows for days already covered (more than {MAX_LATE}): most likely "
                 f"a converter changed. Check a sample, then rerun with SWISSLAW_REFORMAT=1 (one commit).")
    p = subprocess.Popen(["git", "fast-import", "--quiet", "--done", "--force"], cwd=repo, stdin=subprocess.PIPE)
    mark, parent, snaps = 0, tip, {k: dict(v) for k, v in T.items()}
    if reformat and late:                                # the texts as the converters write them now: one commit
        changes = []
        for path in late:
            old, new = snaps.get(path, {}), S.get(path)
            changes += [("D", f"{path}/{lg}.md", None) for lg in old if not new or lg not in new]
            changes += [("M", f"{path}/{lg}.md", txt) for lg, txt in (new or {}).items() if old.get(lg) != txt]
            if new is None:
                snaps.pop(path, None)
            else:
                snaps[path] = new
        mark = write_commit(p.stdin, mark, "main", f"Neu umgesetzt: {len(late):,} Erlasse".replace(",", "'") +
                            "\n\nDie Texte, wie die Umsetzung in Markdown sie heute schreibt; der Wortlaut ist unverändert.",
                            window, changes, parent)
        parent, late = None, []
    for path in late:                                    # 1. late: published after the day they apply from
        e = last_ev.get(path)
        old = snaps.get(path, {})
        new = S.get(path)
        changes = [("D", f"{path}/{lg}.md", None) for lg in old if not new or lg not in new]
        changes += [("M", f"{path}/{lg}.md", txt) for lg, txt in (new or {}).items() if old.get(lg) != txt]
        if new is None:
            snaps.pop(path, None)
        else:
            snaps[path] = new
        if not changes:
            continue
        day = e["d"] if e else window
        msg = message(e, old) if e else f"{path}: Stand {de_date(window)}"
        head, _, rest = msg.partition("\n\n")
        since = (e or {}).get("orig") or day                # the version's own first day (START caps the history only)
        if path not in T and new is not None:            # an act the source has only now: new in the collection
            head = f"{e['label'] if e else path}: neu in der Sammlung"
            note = f"Gilt seit {de_date(since)}; hier aufgenommen am {de_date(window)}."
        else:
            note = (f"Nachträglich veröffentlicht: {'aufgehoben' if new is None else 'gilt'} seit "
                    f"{de_date(since if new is not None and since > day else day)}, hier ergänzt am {de_date(window)}.")
        mark = write_commit(p.stdin, mark, "main", f"{head}\n\n{note}" + (f"\n\n{rest}" if rest else ""), day, changes,
                            parent, committed=max(day, window))
        parent = None
    mark = stream(p.stdin, window_ev, "main", mark, parent, snaps)  # 2. the window, by day
    if mark:
        parent = None
    main_ev = [e for e in events if e["d"] <= TODAY]
    fut_ev = [e for e in events if e["d"] > TODAY]
    root = readme.files(snaps, facts, kacts, START, TODAY, future_list(fut_ev), readme_counts(main_ev))
    changed = {f: txt for f, txt in root.items() if not (repo / f).exists() or (repo / f).read_text(encoding="utf-8") != txt}
    for f in [f for f in changed if f.startswith(".github/")]:   # the workflow's token may not change workflows: by hand
        print(f"::notice::{f} differs from readme.py; push it by hand (a full build or a commit of its own)", file=sys.stderr)
        del changed[f]
    if changed:                                          # 3. README and indexes
        mark = write_commit(p.stdin, mark, "main", f"README und Verzeichnisse: Stand {de_date(TODAY)}", TODAY,
                            [("M", f, txt) for f, txt in changed.items()], tip if not mark else None)
    write_paths(snaps, facts, kacts)
    head_ref = f":{mark}" if mark else tip
    p.stdin.write(f"reset refs/heads/future\nfrom {head_ref}\n\n".encode())     # 4. future, rebuilt on the new tip
    stream(p.stdin, fut_ev, "future", mark, None, {k: dict(v) for k, v in snaps.items()})
    p.stdin.write(b"done\n")
    p.stdin.close()
    if p.wait():
        sys.exit("fast-import failed")
    subprocess.run(["git", "reset", "-q", "--hard", "main"], cwd=repo, check=True)
    # the tip must be what every version known today gives
    want = {k: dict(v) for k, v in S.items()}            # the last run's day as known today, then the window
    replay(window_ev, want)
    got = tree_of(repo)
    bad = sorted(q for q in set(want) | set(got) if want.get(q) != got.get(q))
    n = git(repo, "rev-list", "--count", f"{tip}..main")
    nf = git(repo, "rev-list", "--count", "main..future")
    print(f"append: {n} new commits on main ({len(late)} late, {len(window_ev)} events in the window); future {nf} commits; "
          f"{len(got)} acts in the tree; {len(bad)} differ from the replay", file=sys.stderr)
    if bad:
        sys.exit(f"the tip differs from the replay of all known versions: {bad[:10]}")


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    if sys.argv[1] == "--append":
        return append(Path(sys.argv[2]).resolve())
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
    import readme
    p = subprocess.Popen(["git", "fast-import", "--quiet", "--done"], cwd=target, stdin=subprocess.PIPE)
    snaps: dict = {}
    days: list = []
    mark = stream(p.stdin, main_ev, "main", 0, None, snaps, days)
    ntags = month_tags(p.stdin, days)
    mark = write_extra(p.stdin, mark, "main", readme.files(snaps, facts, kacts, START, TODAY, future_list(fut_ev),
                                                         readme_counts(main_ev)),
                       f"README und Verzeichnisse: Stand {de_date(TODAY)}", TODAY)
    write_paths(snaps, facts, kacts)
    main_mark = mark
    mark = stream(p.stdin, fut_ev, "future", mark, f":{main_mark}", snaps)
    p.stdin.write(b"done\n")
    p.stdin.close()
    if p.wait():
        sys.exit("fast-import failed")
    subprocess.run(["git", "checkout", "-q", "main"], cwd=target, check=True)
    n = subprocess.run(["git", "rev-list", "--count", "main"], cwd=target, capture_output=True, text=True).stdout.strip()
    nf = subprocess.run(["git", "rev-list", "--count", "main..future"], cwd=target, capture_output=True, text=True).stdout.strip()
    print(f"main: {n} commits; future: {nf} more; {len(snaps)} acts in the last tree; {ntags} tags stand/<day>", file=sys.stderr)


if __name__ == "__main__":
    main()
