#!/usr/bin/env python3
"""Geneva: every act of the rs/GE (silgeneve.ch) -> build/cantonal/GE.json (SPEC.md).

Source: the SIL table of contents https://silgeneve.ch/legis/program/books/rsg/content.htm
("rs/GE - Textes en vigueur", windows-1252) and one Word-HTML page per act under …/rsg/htm/.
The collection carries only texts in force: a repealed act leaves the table of contents and its
page is withdrawn (e.g. rsg_d3_08p06, still in the abbreviation table abtoc.htm, answers 404).
Each page also says "Texte en vigueur" above the title; a page that does not is reported.

Page anatomy: p.TitreLoi (official title, the abbreviation in parentheses on its own line),
p.NoLoi (systematic number "E 5 10"), p.date ("du 12 septembre 1985"), p.vigueur, a rule
(p.ligne), then the preamble: p.GC (issuer, enacting clause) and p.Vu (bases); a constitution
or convention may instead carry it under an "Art." heading "Préambule". Footnote calls
"(15)" link to rows of the history table at the end of the page (a[name=FN15]).

Usage: python3 pipeline/cantonal/ge.py [--refresh]   (--refresh refetches the table of contents)
"""
from __future__ import annotations

import copy
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sil_common import (BUILD, Fetcher, adoption_date, find_enacting, issuer_of, norm_ws,  # noqa: E402
                        soup, text_of, write_json)

CT = "GE"
BASE = "https://silgeneve.ch/legis/program/books/rsg"
STOP = {"article", "article0", "titre", "chapitre", "section", "partie", "Tteteintit"}
PRE = {"GC", "Vu", "vu0", "retrait1"}          # classes a preamble is made of
SKIP = {"retour1", "retour2", "ligne", "date", "vigueur"}
FN = re.compile(r"#FN(\w+)$")


def cls(p) -> str:
    return (p.get("class") or [""])[0]


def enumerate_acts(f: Fetcher) -> list[dict]:
    s = soup(f.get(f"{BASE}/content.htm", "content.htm", refresh=f.refresh))
    out, seen = [], set()
    for a in s.find_all("a", href=re.compile(r"^htm/[^/]+\.htm$")):
        pid = a["href"][4:-4]
        if pid in seen:
            continue
        seen.add(pid)
        label = norm_ws(a.get_text())
        m = re.match(r"^([A-M]\s\d+\s\d+(?:\.\d+)?)\s+(.*)$", label)
        out.append({"id": pid, "toc_sr": m.group(1) if m else None,
                    "toc_title": m.group(2) if m else label})
    return out


def abbreviation_table(f: Fetcher) -> dict[str, str]:
    """{page id: abbreviation} from the portal's "Table des abréviations cantonales"."""
    b = f.get(f"{BASE}/abtoc.htm", "abtoc.htm", refresh=f.refresh)
    out = {}
    for tr in soup(b).find_all("tr"):
        a = tr.find("a", href=re.compile(r"^htm/"))
        tds = tr.find_all("td")
        if a and len(tds) >= 2:
            out[a["href"][4:-4]] = norm_ws(tds[0].get_text())
    return out


def clean_title(p) -> str:
    p = copy.copy(p)
    for a in p.find_all("a", href=FN):
        (a.find_parent("sup") or a).decompose()
    return text_of(p)[0]


def footnote(s, key: str) -> str | None:
    a = s.find("a", attrs={"name": f"FN{key}"})
    if not a:
        return None
    tr = a.find_parent("tr")
    if not tr:                                   # a lettered remark outside the history table
        return re.sub(rf"^\(?{key}\)?\s*\.?\s*", "", text_of(a.find_parent("p") or a)[0])
    cells = [text_of(td)[0] for td in tr.find_all("td", recursive=False)]
    head = s.find("p", class_="Tteteintit")
    labels = ([text_of(p)[0] for p in head.find_parent("tr").find_all("p")]
              if head else ["", "Date d'adoption", "Entrée en vigueur"])
    note = re.sub(rf"^{key}\s*\.\s*", "", cells[0])
    for lab, val in zip(labels[1:], cells[1:]):
        if val:
            note += f"; {lab} : {val}"
    return note


def parse(pid: str, b: bytes, stub: dict, abtoc: dict, odd: list) -> dict | None:
    url = f"{BASE}/htm/{pid}.htm"
    s = soup(b)
    body = s.body
    ps = body.find_all("p")
    t_p = body.find("p", class_="TitreLoi")
    n_p = body.find("p", class_="NoLoi")
    if not t_p:
        odd.append(f"{pid}: no TitreLoi, skipped")
        return None
    title = clean_title(t_p)
    sr = norm_ws(n_p.get_text()) if n_p else stub["toc_sr"]
    if stub["toc_sr"] and sr != stub["toc_sr"]:
        odd.append(f"{pid}: number on page {sr!r} != table of contents {stub['toc_sr']!r}")

    # status line above the title
    status = text_of(ps[:ps.index(t_p)])[0]
    if "en vigueur" not in status.lower() or "abrog" in status.lower():
        odd.append(f"{pid}: status line {status[:80]!r}")

    # abbreviation: the last "(…)" of the official title, as the portal writes it
    m = re.search(r"\(([^()]+)\)\s*$", title)
    abbr = m.group(1).strip() if m else None
    if abbr and abtoc.get(pid) and abtoc[pid] != abbr:
        odd.append(f"{pid}: title abbreviation {abbr!r} != abbreviation table {abtoc[pid]!r}")

    # adoption date: p.date, else the history table's first row ("Date d'adoption")
    d_ps = body.find_all("p", class_="date")
    d_txt = text_of(d_ps)[0] if d_ps else ""
    adopted = adoption_date(d_txt)
    if not adopted:
        row = body.find("p", class_="TIntit")
        ta = row.find_parent("tr").find("p", class_="Tadopt") if row else None
        mm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", ta.get_text()) if ta else None
        if mm:
            adopted = f"{mm.group(3)}-{mm.group(2)}-{mm.group(1)}"
            odd.append(f"{pid}: adoption date from the history table ({adopted}); "
                       f"header: {d_txt!r}")
        else:
            odd.append(f"{pid}: no adoption date "
                       f"(header: {d_txt!r})")

    # preamble candidates: after the rule, up to the first structural heading
    start = next((i for i, p in enumerate(ps) if cls(p) == "ligne"), ps.index(t_p))
    cands, used_pre = [], False
    for p in ps[start + 1:]:
        c = cls(p)
        if c in STOP:
            if not used_pre and not cands and re.match(r"^pr[ée]ambule\b", norm_ws(p.get_text()), re.I):
                used_pre = True                  # the text under a "Préambule" heading
                continue
            break
        if c in SKIP:
            continue
        if norm_ws(p.get_text()):
            cands.append(p)

    def mk(a):
        mm = FN.search(a.get("href", ""))
        return mm.group(1) if mm else None

    texts = [text_of(p, mk, url)[0] for p in cands]
    k, strict = find_enacting(texts)
    if k is not None:
        chosen = cands[:k + 1]
        if not strict:
            odd.append(f"{pid}: enacting clause taken from a paragraph with an enacting verb: "
                       f"{texts[k][-70:]!r}")
    elif used_pre:                               # everything under a "Préambule" heading
        chosen = cands
    else:
        chosen = []
        for p in cands:
            if cls(p) not in PRE:
                break
            chosen.append(p)
        if cands:
            odd.append(f"{pid}: no enacting clause; " + (
                f"kept {len(chosen)} preamble paragraph(s)" if chosen else
                f"text before the first article not a preamble: {texts[0][:70]!r}"))
    ingress, keys, links = text_of(chosen, mk, url) if chosen else ("", [], [])
    notes = {}
    for key in keys:
        if key not in notes:
            n = footnote(s, key)
            if n is None:
                odd.append(f"{pid}: footnote {key} of the preamble not found")
            else:
                notes[key] = n
    return {
        "ct": CT, "sr": sr, "title": title, "abbr": abbr, "url": url, "in_force": True,
        "adopted": adopted, "issuer": issuer_of(ingress) if ingress else None,
        "ingress": ingress, "notes": notes, "links": links, "lang": "fr", "src": "portal",
    }


def sort_key(sr: str):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[\s.]+", sr)]


def main():
    t0 = time.time()
    f = Fetcher(BUILD / "raw" / CT, refresh="--refresh" in sys.argv)
    stubs = enumerate_acts(f)
    abtoc = abbreviation_table(f)
    f.refresh = False
    print(f"{CT}: {len(stubs)} acts in content.htm, {len(abtoc)} in abtoc.htm", file=sys.stderr)
    pages = f.get_many([(f"{BASE}/htm/{x['id']}.htm", f"htm/{x['id']}.htm") for x in stubs], CT)
    odd: list[str] = []
    for pid in sorted(set(abtoc) - {x["id"] for x in stubs}):
        odd.append(f"{pid}: in abtoc.htm ({abtoc[pid]}) but not in the table of contents (not in force)")
    recs = []
    for x in stubs:
        b = pages[f"htm/{x['id']}.htm"]
        if b is None:
            odd.append(f"{x['id']}: 404")
            continue
        r = parse(x["id"], b, x, abtoc, odd)
        if r:
            recs.append(r)
    recs.sort(key=lambda r: sort_key(r["sr"]))
    out = write_json(recs, CT)
    (BUILD / "raw" / CT / "_oddities.txt").write_text("\n".join(odd) + "\n", encoding="utf-8")
    n = len(recs)
    print(f"{CT}: {n} acts -> {out} ({time.time() - t0:.0f} s, {f.n_net} requests); "
          f"ingress {sum(bool(r['ingress']) for r in recs)}, adopted "
          f"{sum(bool(r['adopted']) for r in recs)}, abbr {sum(bool(r['abbr']) for r in recs)}, "
          f"oddities {len(odd)} (build/cantonal/raw/{CT}/_oddities.txt)", file=sys.stderr)


if __name__ == "__main__":
    main()
