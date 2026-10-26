#!/usr/bin/env python3
"""Neuchâtel: every act of the RSN (rsn.ne.ch) -> build/cantonal/NE.json (SPEC.md).

Source: the SIL table of contents https://rsn.ne.ch/DATA/program/books/rsne/content.htm
("RSN - État au …", windows-1252) and one Word-HTML page per act under …/rsne/htm/. The RSN
carries the texts in force only; an entry "<n> Voir <m>" is a pointer to another number, not an
act, and is skipped. The portal's table of abbreviations (ta.pdf) is read to tell an act's own
abbreviation from an institution's abbreviation at the end of a title.

Page anatomy: a header table, left cell the adoption date (p.xDateAdoption "24" / "septembre" /
"2000"), right cell the official title (p.xNom) with a footnote call "(*)" (publication in the
FO); then p.xEdition ("Etat au …"), the preamble — p.xItalique (issuer, enacting clause), p.xVu
(bases), sometimes p.xNormal ("sur la proposition du Conseil d'Etat, …") — and the articles
(a[name^=LVMPART], p.xMarginale, p.xChapitre …). Footnotes are Word footnotes at the end of the
page (div#ftnN, a[name=_ftnN]); calls show "[1]" or "(*)".

Usage: python3 pipeline/cantonal/ne.py [--refresh]   (--refresh refetches the table of contents)
"""
from __future__ import annotations

import copy
import re
import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sil_common import (BUILD, Fetcher, adoption_date, find_enacting, fr_dates, issuer_of,  # noqa: E402
                        norm_ws, soup, text_of, write_json)

CT = "NE"
BASE = "https://rsn.ne.ch/DATA/program/books/rsne"
STOP = {"xTitre", "xNomChapitre", "xMarginale", "xMarginaleRetrait", "xChapitre", "xSection",
        "MsoFootnoteText", "xTitreCitation"}
PRE = {"xItalique", "xVu"}
HEADING = re.compile(r"^(article\s+(premier|unique|1(er)?\b)|art\.\s*(1(er)?|premier)\b|"
                     r"chapitre\s+(premier|1|i)\b|titre\s+(premier|1|i)\b|section\s+(1|i|première)\b)",
                     re.I)
FTN = re.compile(r"#_ftn(\d+)$")


def cls(p) -> str:
    return (p.get("class") or [""])[0]


def enumerate_acts(f: Fetcher) -> tuple[list[dict], list[str]]:
    s = soup(f.get(f"{BASE}/content.htm", "content.htm", refresh=f.refresh))
    out, pointers, seen = [], [], set()
    for a in s.find_all("a", href=re.compile(r"^htm/[^/]+\.htm$")):
        fn = a["href"][4:-4]
        if fn in seen:
            continue
        seen.add(fn)
        label = norm_ws(a.get_text())
        m = re.match(r"^(\d[\d.]*[a-z]?)\s+(.*)$", label)
        if m and re.match(r"^voir\s+[\d.]+\s*$", m.group(2), re.I):
            pointers.append(f"{fn}: table-of-contents entry {label!r} is a pointer, skipped")
            continue
        out.append({"id": fn, "toc_sr": m.group(1) if m else None,
                    "toc_title": m.group(2) if m else label})
    return out, pointers


def abbreviation_table(f: Fetcher) -> dict[str, list[str]]:
    """{abbreviation: [expansions]} from the portal's "Table des abréviations" (ta.pdf): two
    columns, the abbreviation at the left margin, the expansion indented (continuation lines
    carry no abbreviation)."""
    import io

    import pdfplumber
    b = f.get(f"{BASE}/ta.pdf", "ta.pdf", refresh=f.refresh)
    out: dict[str, list[str]] = {}
    cur = None
    with pdfplumber.open(io.BytesIO(b)) as pdf:
        for pg in pdf.pages:
            rows: dict[int, list] = {}
            for w in pg.extract_words(use_text_flow=True):
                rows.setdefault(round(w["top"]), []).append(w)
            for top in sorted(rows):
                ws = sorted(rows[top], key=lambda w: w["x0"])
                left = [w["text"] for w in ws if w["x0"] < 120]
                right = " ".join(w["text"] for w in ws if w["x0"] >= 120)
                if left and right:
                    cur = [" ".join(left), right]
                    out.setdefault(cur[0], []).append(cur)
                elif right and cur:
                    cur[1] += " " + right
    return {k: [norm_ws(e[1]) for e in v] for k, v in out.items()}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.replace("’", "'"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{4,}", _fold(s)))


def similarity(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    return len(wa & wb) / len(wa | wb) if wa | wb else 0.0


ACT_WORDS = {"loi", "arrêté", "arrete", "règlement", "reglement", "décret", "decret", "concordat",
             "accord", "convention", "ordonnance", "directive", "tarif", "statuts"}
STOPWORDS = {"de", "la", "le", "les", "des", "du", "d", "l", "à", "a", "et", "en", "sur", "pour",
             "aux", "au", "dans", "par", "un", "une"}


def ta_verdict(cand: str, before: str, whole: str, ta: dict) -> str:
    """How ta.pdf's entry for `cand` relates to the act whose title ends "<before> (<whole>)"."""
    exps = ta.get(cand)
    if not exps:
        return "absent"
    fb = _fold(before).strip(" ,:;")
    tail = re.split(r"[:]", before)[-1]                       # "… (LGéo): loi cantonale sur … (LCGéo)"
    if any(_fold(tail).strip(" ,:;") == _fold(e) for e in exps):
        return "match"
    for e in exps:
        fe = _fold(e)
        if fb.endswith(fe) and len(fb) > len(fe) + 5:
            return f"reject: ta.pdf gives {cand} = {e!r}, an act or body the title refers to"
    lead = whole[: -len(cand)].strip(" ,") if whole != cand else ""   # "(Convention sur …, CoParl)"
    if any(max(similarity(e, before), similarity(e, tail), similarity(e, lead) if lead else 0) >= 0.34
           for e in exps):
        return "match"
    kind = _fold(before.split()[0])[:1].upper() if before.split() else ""
    if cand[:1].upper() == kind and not any(_fold(e)[:1].upper() == "L" and kind != "L" for e in exps):
        return f"ta.pdf gives {cand} = {exps[0]!r} (an earlier act?)"
    return f"reject: ta.pdf gives {cand} = {exps[0]!r}"


def abbreviation_shaped(c: str) -> bool:
    """"LPA", "Cst. NE", "LSport", "Concordat HEP-BEJUNE", "Asimap" — not a qualifier such as
    "bail à loyer", "Règlement sur le TIG" (a short title) or "et partiellement du Tessin"."""
    toks = c.split()
    if not toks or len(toks) > 3 or len(c) > 40:
        return False

    def acro(t):
        return (sum(ch.isupper() for ch in t) >= 2
                or (len(toks) == 1 and t[0].isupper() and len(t) <= 15)
                or bool(re.fullmatch(r"[A-Z][a-zé]{0,3}\.?", t)))
    return (all(acro(t) or t.lower() in ACT_WORDS for t in toks) and any(acro(t) for t in toks))


def names_embedded_phrase(abbr: str, before: str) -> bool:
    """True if `abbr` spells the initials of the words right before it and that phrase does
    not start the title: "… relatives à la Haute école neuchâteloise (HEN)" abbreviates the
    school, not the act."""
    letters = re.sub(r"[^A-Z]", "", _fold(abbr).upper())
    words = [w for w in re.split(r"[\s'’\-]+", before) if w and w.lower() not in STOPWORDS]
    words = [w for w in words if re.match(r"\w", w)]
    for k in range(1, len(words) + 1):
        if "".join(_fold(w)[0].upper() for w in words[-k:]) == letters:
            return k < len(words)
    return False


def strip_calls(node):
    node = copy.copy(node)
    for a in node.find_all("a", href=FTN):
        a.decompose()
    return node


def footnote(s, key_href: str) -> str | None:
    n = FTN.search(key_href).group(1)
    a = s.find("a", attrs={"name": f"_ftn{n}"})
    if not a:
        return None
    box = a.find_parent("div") or a.find_parent("p")
    txt = text_of(strip_calls(box))[0] if box else ""
    return re.sub(r"^\s*(\(\*\)|\[\w+\]|\*)\s*", "", txt)


def parse(fn: str, b: bytes, stub: dict, ta: dict, odd: list) -> dict | None:
    url = f"{BASE}/htm/{fn}.htm"
    s = soup(b)
    body = s.body
    ps = body.find_all("p")
    head = next((t for t in body.find_all("table") if t.find("p", class_="xDateAdoption")), None)
    if head is None:
        odd.append(f"{fn}: no header table, skipped")
        return None
    cells = head.find("tr").find_all("td", recursive=False)
    date_cell, title_cell = cells[0], (cells[1] if len(cells) > 1 else None)
    if title_cell is None:
        odd.append(f"{fn}: no title cell, skipped")
        return None

    sr = stub["toc_sr"]
    first = norm_ws(ps[0].get_text()) if ps else ""
    if re.match(r"^\d[\d.]*[a-z]?$", first) and first != sr:
        odd.append(f"{fn}: number on page {first!r} != table of contents {sr!r}")

    title = text_of(strip_calls(title_cell))[0]
    title = re.sub(r"\s*\(\*\)\s*$", "", title)          # a call left as plain text
    if not title:
        odd.append(f"{fn}: empty title on page; table of contents title used")
        title = re.sub(r",?\s+(du|des|le)\s+\d.*$", "", stub["toc_title"])

    # abbreviation: the last "(…)" of the official title, when it is the act's abbreviation
    abbr = None
    m = re.search(r"\(([^()]+)\)\s*$", title)
    if m:
        whole = m.group(1).strip()
        cand = whole.rsplit(", ", 1)[-1] if ", " in whole else whole   # "(…, CoParl)"
        before = title[:m.start()]
        if abbreviation_shaped(cand):
            verdict = ta_verdict(cand, before, whole, ta)
            if verdict.startswith("reject"):
                odd.append(f"{fn}: '({whole})' ends the title; {verdict}")
            elif verdict == "absent" and names_embedded_phrase(cand, before):
                odd.append(f"{fn}: '({whole})' abbreviates the words before it, not the act")
            else:
                abbr = cand
                if verdict != "match":
                    odd.append(f"{fn}: abbreviation {cand!r} kept (stated in the title); "
                               + ("not in ta.pdf" if verdict == "absent" else verdict))
        elif cand != whole and abbreviation_shaped(whole):
            abbr = whole

    adopted = adoption_date(text_of(date_cell)[0])
    toc_dates = fr_dates(stub["toc_title"])
    if adopted and toc_dates and adopted not in toc_dates:
        odd.append(f"{fn}: adoption date on page {adopted} != table of contents {stub['toc_title'][-30:]!r}")
    if not adopted:
        odd.append(f"{fn}: no adoption date (header: {text_of(date_cell)[0]!r}, "
                   f"table of contents: {stub['toc_title'][-40:]!r})")

    # preamble candidates: after the header table up to the first article / heading
    in_head = [i for i, p in enumerate(ps) if p.find_parent("table") is head]
    cands, used_pre = [], False
    for p in ps[in_head[-1] + 1:]:
        c = cls(p)
        t = norm_ws(p.get_text())
        if c in STOP or p.find("a", attrs={"name": re.compile(r"^LVMP")}) or (t and HEADING.match(t)):
            if not used_pre and not cands and re.match(r"^pr[ée]ambule\b", t, re.I):
                used_pre = True                  # the text under a "Préambule" heading
                continue
            break
        if c in ("xEdition", "xLigneBlanche") or not t:
            continue
        if re.match(r"^(e\s*)?[ée]\s*tat\s+au\b", t, re.I):     # "Etat au 1er janvier 2026"
            continue
        cands.append(p)

    def mk(a):
        mm = FTN.search(a.get("href", ""))
        if not mm:
            return None
        k = norm_ws(a.get_text()).strip("[]()")
        return k or mm.group(1)

    texts = [text_of(p, mk, url)[0] for p in cands]
    k, strict = find_enacting(texts)
    if k is not None:
        chosen = cands[:k + 1]
        if not strict:
            odd.append(f"{fn}: enacting clause taken from a paragraph with an enacting verb: "
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
            odd.append(f"{fn}: no enacting clause; " + (
                f"kept {len(chosen)} preamble paragraph(s)" if chosen else
                f"text before the first article not a preamble: {texts[0][:70]!r}"))
    ingress, keys, links = text_of(chosen, mk, url) if chosen else ("", [], [])
    notes = {}
    hrefs = [a["href"] for p in chosen for a in p.find_all("a", href=FTN)]
    for key, href in zip(keys, hrefs):
        if key not in notes:
            n = footnote(s, href)
            if n is None:
                odd.append(f"{fn}: footnote {key} of the preamble not found")
            else:
                notes[key] = n
                if not n:
                    odd.append(f"{fn}: footnote {key} of the preamble is empty in the source")
    return {
        "ct": CT, "sr": sr, "title": title, "abbr": abbr, "url": url, "in_force": True,
        "adopted": adopted, "issuer": issuer_of(ingress) if ingress else None,
        "ingress": ingress, "notes": notes, "links": links, "lang": "fr", "src": "portal",
    }


def sort_key(sr: str):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.split(r"[.]", sr)]


def main():
    t0 = time.time()
    f = Fetcher(BUILD / "raw" / CT, refresh="--refresh" in sys.argv)
    stubs, odd = enumerate_acts(f)
    ta = abbreviation_table(f)
    f.refresh = False
    print(f"{CT}: {len(stubs)} acts in content.htm ({len(odd)} pointers skipped)", file=sys.stderr)
    pages = f.get_many([(f"{BASE}/htm/{x['id']}.htm", f"htm/{x['id']}.htm") for x in stubs], CT)
    recs = []
    for x in stubs:
        b = pages[f"htm/{x['id']}.htm"]
        if b is None:
            odd.append(f"{x['id']}: 404")
            continue
        r = parse(x["id"], b, x, ta, odd)
        if r:
            recs.append(r)
    recs.sort(key=lambda r: sort_key(r["sr"]))
    out = write_json(recs, CT)
    (BUILD / "raw" / CT / "_oddities.txt").write_text("\n".join(odd) + "\n", encoding="utf-8")
    print(f"{CT}: {len(recs)} acts -> {out} ({time.time() - t0:.0f} s, {f.n_net} requests); "
          f"ingress {sum(bool(r['ingress']) for r in recs)}, adopted "
          f"{sum(bool(r['adopted']) for r in recs)}, abbr {sum(bool(r['abbr']) for r in recs)}, "
          f"oddities {len(odd)} (build/cantonal/raw/{CT}/_oddities.txt)", file=sys.stderr)


if __name__ == "__main__":
    main()
