#!/usr/bin/env python3
"""SZ adapter: acts in force in the Systematische Gesetzsammlung des Kantons Schwyz (SRSZ)
-> build/cantonal/SZ.json, read through LexFind (src "lexfind").

The official portal (www.sz.ch/kanton/gesetze/systematische-gesetzsammlung.html) answered HTTP 403
to a plain request; it is not contacted. LexFind (Institut du Fédéralisme) mirrors the collection:
  listing  https://www.lexfind.ch/api/fe/de/entities/19/systematics?active_only=true
           &tols_for_systematics[]=<every systematic id>   (the SRSZ tree with its texts of law;
           the same 430 ids as a fulltext search for "der" over entity 19)
  detail   https://www.lexfind.ch/api/fe/de/texts-of-law/<id>/with-version-groups
           (dta_urls[].original_url = the sz.ch PDF, used as "url")
  text     https://www.lexfind.ch/tol/<id>/de  (LexFind's copy of the sz.ch PDF)
The Ingress is read from the PDF between the "(Vom ...)" line and the enacting word; footnotes are
page-bottom notes or endnotes ("2 SRSZ 100.100.").

Raw responses are cached under build/cantonal/raw/SZ/ (list/, tol/, pdf/); a rerun is offline.
Usage: python3 pipeline/cantonal/sz.py [--limit N] [--only 231.110,100.100]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refresh import fresh  # noqa: E402  (weekly refresh)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "build" / "cantonal" / "raw" / "SZ"
OUT = ROOT / "build" / "cantonal" / "SZ.json"

UA = "swiss-law-graph/1.0 (legal research; +https://opencaselaw.ch)"
API = "https://www.lexfind.ch/api/fe/de"
ENTITY = 19
DELAY = 0.3
WORKERS = 3

MONTHS = {m: i + 1 for i, m in enumerate(
    ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september",
     "oktober", "november", "dezember"])}
ENACT = (r"beschliesst|beschliessen|verfügt|verfügen|verordnet|verordnen|erlässt|erlassen|"
         r"vereinbaren|vereinbart|bestimmt|bestimmen|setzt\s+fest|setzen\s+fest|ordnet\s+an|"
         r"schliessen|schliesst|geben\s+uns\s+folgende\s+Verfassung|geben\s+uns\s+die\s+folgende\s+Verfassung|"
         r"folgende\s+Vereinbarung|folgendes\s+Konkordat|folgenden\s+Vertrag|beschlossen|genehmigt|"
         r"erklärt|erklären|stellt\s+fest|treffen\s+folgende\s+Vereinbarung")
BASIS_KW = re.compile(
    r",?\s*\b(gestützt|in\s+Betracht|in\s+Hinsicht|nach\s+zustimmender|auf\s+Gesuch|mit\s+dem\s+Ziel|nach\s+Einsicht|in\s+Ausführung|in\s+Anwendung|in\s+Vollziehung|"
    r"in\s+Vollzug|auf\s+Antrag|auf\s+den\s+Antrag|auf\s+das\s+Gesuch|nach\s+Kenntnisnahme|"
    r"in\s+Kenntnis|in\s+Erwägung|im\s+Bestreben|in\s+der\s+Absicht|mit\s+Rücksicht|aufgrund|"
    r"auf\s+Grund|nach\s+Prüfung|in\s+Revision|in\s+Verantwortung|im\s+Hinblick|in\s+Ergänzung|"
    r"in\s+Abänderung|unter\s+Hinweis|nach\s+Anhörung|in\s+Berücksichtigung|in\s+Anbetracht|"
    r"vorbehältlich|unter\s+Vorbehalt|im\s+Sinne|im\s+Rahmen|zur\s+Ausführung|zum\s+Vollzug|"
    r"in\s+Nachachtung|in\s+Ausübung)\b")
ISSUER_START = re.compile(r"^(Der|Die|Das|Wir)\b")
CONJ = {"und", "oder", "bis", "sowie", "bzw", "bzw.", "resp.", "noch", "als", "wie"}

_host_sem: dict[str, threading.Semaphore] = {}
_host_lock = threading.Lock()
_tls = threading.local()


def session() -> requests.Session:
    s = getattr(_tls, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = UA
        retry = Retry(total=6, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",), respect_retry_after_header=True)
        s.mount("https://", HTTPAdapter(max_retries=retry))
        _tls.s = s
    return s


def get(url: str, **kw) -> requests.Response:
    host = urlparse(url).netloc
    if host.endswith("sz.ch"):
        raise RuntimeError("sz.ch refused access (HTTP 403); not contacted")
    with _host_lock:
        sem = _host_sem.setdefault(host, threading.Semaphore(WORKERS))
    with sem:
        r = session().get(url, timeout=90, **kw)
        time.sleep(DELAY)
    if r.status_code in (401, 403):
        raise SystemExit(f"{host} refused access (HTTP {r.status_code}) for {url}: stopping")
    r.raise_for_status()
    return r


def cached(path: Path, fetch) -> bytes:
    if fresh(path) and path.stat().st_size > 0:          # lists and texts in force: re-read in a weekly refresh
        return path.read_bytes()
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return data


# ---------------------------------------------------------------- enumeration

def enumerate_acts() -> list[dict]:
    tree = json.loads(cached(RAW / "list" / "systematics.json",
                             lambda: get(f"{API}/entities/{ENTITY}/systematics",
                                         params={"active_only": "true"}).content))
    ids = sorted(int(k) for k in tree if k)
    full = json.loads(cached(RAW / "list" / "systematics_tols.json",
                             lambda: get(f"{API}/entities/{ENTITY}/systematics",
                                         params=[("active_only", "true")] +
                                                [("tols_for_systematics[]", str(i)) for i in ids]).content))
    acts: dict[int, dict] = {}
    for k, node in full.items():
        if not k:
            continue
        for t in node.get("tols") or []:
            if not t.get("is_active"):
                continue
            t = dict(t, systematic=node.get("identifier"), systematic_title=node.get("title"))
            acts.setdefault(t["id"], t)
    return list(acts.values())


def is_act(t: dict) -> bool:
    """The SRSZ also lists its Register, Abkürzungsverzeichnis and Benützungshinweise."""
    return bool(re.match(r"^\d", (t.get("systematic_number") or "").strip()))


# ---------------------------------------------------------------- PDF parsing

def _clean(t: str) -> str:
    return re.sub(r"[    \t]", " ", re.sub(r"[﻿​]", "", t))


def _lines(doc, pages, sr: str) -> list[dict]:
    out = []
    for pno in pages:
        if pno >= doc.page_count:
            break
        for b in doc[pno].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                spans = [s for s in ln["spans"] if s["text"]]
                if not any(_clean(s["text"]).strip() for s in spans):
                    continue
                out.append({"p": pno, "x": ln["bbox"][0], "y": ln["bbox"][1], "y1": ln["bbox"][3],
                            "spans": spans})
    return _rows(out)


def _rows(lines: list[dict]) -> list[dict]:
    """Reading order: group lines that share a visual row (a superscript marker printed as its own
    line sits slightly higher than the text it follows), then sort each row by x."""
    lines.sort(key=lambda l: (l["p"], (l["y"] + l["y1"]) / 2))
    rows: list[list[dict]] = []
    for l in lines:
        if rows and rows[-1][0]["p"] == l["p"]:
            r = rows[-1]
            top, bot = min(x["y"] for x in r), max(x["y1"] for x in r)
            ov = min(bot, l["y1"]) - max(top, l["y"])
            h = min(bot - top, l["y1"] - l["y"])
            if h > 0 and ov > 0.4 * h:
                r.append(l)
                continue
        rows.append([l])
    return [l for r in rows for l in sorted(r, key=lambda l: l["x"])]


def _merged_rows(lines: list[dict]) -> list[dict]:
    """Lines of one visual row merged (footnote number and text are set as separate lines)."""
    out: list[dict] = []
    for l in lines:
        if out and out[-1]["p"] == l["p"] and min(out[-1]["y1"], l["y1"]) - max(out[-1]["y"], l["y"]) > \
                0.4 * min(out[-1]["y1"] - out[-1]["y"], l["y1"] - l["y"]) and l["x"] > out[-1]["x"]:
            prev = out[-1]
            out[-1] = dict(prev, spans=prev["spans"] + [{"text": " ", "size": l["spans"][0]["size"],
                                                          "flags": 0, "bbox": l["spans"][0]["bbox"]}]
                           + l["spans"], y=min(prev["y"], l["y"]), y1=max(prev["y1"], l["y1"]))
        else:
            out.append(dict(l))
    return out


def _body_size(doc) -> float:
    """Body text size: character-weighted mode over the document, footnote-sized text (< 7.8 pt)
    left out (short acts with long endnotes otherwise come out at the note size)."""
    big, allc = Counter(), Counter()
    for pg in doc:
        for b in pg.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    n = len(_clean(s["text"]).strip())
                    allc[round(s["size"], 1)] += n
                    if s["size"] >= 7.8:
                        big[round(s["size"], 1)] += n
    c = big if sum(big.values()) >= 100 else allc
    return c.most_common(1)[0][0] if c else 8.5


def _is_sup(s, body) -> bool:
    t = _clean(s["text"]).strip()
    return bool(t) and (bool(s["flags"] & 1) or s["size"] < 0.75 * body) and \
        bool(re.fullmatch(r"[\d,\s)]+", t))


def _is_furniture(ln, sr, body) -> bool:
    t = _clean(" ".join(s["text"] for s in ln["spans"])).strip()
    if re.fullmatch(r"SRSZ\s+\d{1,2}\.\d{1,2}\.\d{4}", t) or t == sr:
        return True
    if re.fullmatch(r"\d{1,3}", t) and all(s["size"] >= 0.8 * body for s in ln["spans"]):
        return True                                  # page number
    return False


def _line_text(ln, body) -> str:
    parts, prev = [], None
    for s in ln["spans"]:
        t = _clean(s["text"])
        if _is_sup(s, body):
            nums = [n for n in re.split(r"[,\s)]+", t) if n]
            t = "".join(f"[{n}]" for n in nums)
        elif prev is not None and parts and not parts[-1][-1:].isspace() and not t[:1].isspace() \
                and s["bbox"][0] - prev["bbox"][2] > 0.2 * s["size"]:
            t = " " + t                                  # spans set apart without a space char
        parts.append(t)
        prev = s
    return "".join(parts)


def _join(lines: list[str]) -> str:
    text = ""
    for t in lines:
        t = t.strip()
        if not t:
            continue
        if not text:
            text = t
        elif text.endswith("­"):
            text = text[:-1] + t
        elif re.search(r"[A-Za-zÄÖÜäöüß]-$", text):
            first = t.split(" ", 1)[0]
            if first in CONJ:
                text += " " + t
            elif re.search(r"isch-$", text):
                text += t                               # "römisch-" + "katholischen"
            elif first[:1].islower():
                text = text[:-1] + t                    # hyphenation at the line end
            else:
                text += t                               # "Basel-" + "Stadt"
        elif t[:1] in ",.;:)" or t.startswith("["):
            text += t
        else:
            text += " " + t
    text = re.sub(r"­", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+(\[\d+\])", r"\1", text)           # "(StPO), [2]" -> "(StPO),[2]"
    return text


def _footnotes(doc, sr, body) -> dict[str, str]:
    """Footnotes (page bottom or endnotes): a small number then text smaller than the body.
    Later occurrences win (endnotes close the document)."""
    entries: list[tuple[str, list[str]]] = []
    for pno in range(doc.page_count):
        cur = None
        for ln in _merged_rows(_lines(doc, [pno], sr)):
            if _is_furniture(ln, sr, body):
                continue
            spans = [s for s in ln["spans"] if _clean(s["text"]).strip()]
            first, rest = spans[0], spans[1:]
            if (re.fullmatch(r"\d{1,3}", _clean(first["text"]).strip()) and first["size"] < 0.8 * body
                    and rest and all(s["size"] < body - 0.6 for s in rest)
                    and all(s["size"] > 0.65 * body for s in rest if not _is_sup(s, body))):
                allsp = ln["spans"]
                cur = ["".join(s["text"] for s in allsp[allsp.index(first) + 1:])]
                entries.append((_clean(first["text"]).strip(), cur))
            elif cur is not None and all(s["size"] < body - 0.6 for s in spans) \
                    and not (len(spans) == 1 and _is_sup(spans[0], body)):
                cur.append("".join(s["text"] for s in ln["spans"]))
            else:
                cur = None
    notes: dict[str, str] = {}
    for k, v in entries:
        notes[k] = _join([_clean(t) for t in v])
    return notes


VOM = re.compile(r"^\(?\s*(vom|von)\s+\d", re.I)
HEADING = re.compile(r"^((§+|Art\.|Artikel)\s*\d+\s*[a-z]*\s*(\[\d+\])*\s*$|[IVXLC]+\.\s*$|\d+\.\s*$|"
                     r"[IVXLC]+\.\s+[A-ZÄÖÜ][a-zäöü]+(\s+[A-ZÄÖÜa-zäöü]+){0,6}$|Ziffer\s+\d|"
                     r"\d+\.\s*(Teil|Titel|Abschnitt|Kapitel)\b|Einleitung\b|Inhaltsverzeichnis)")
ENACT_END = re.compile(r"\b(" + ENACT + r"|folgende[nrs]?\s+\w+|nachstehende[nrs]?\s+\w+|"
                       r"nachfolgende[nrs]?\s+\w+|wie\s+folgt|was\s+folgt|überein)\b[^:]{0,80}$", re.I)
ISSUER_CUT = re.compile(r"\s(" + ENACT + r"|erteilt|erteilen|verleiht|verleihen|verabschiedet|"
                        r"verabschieden|treffen|trifft|haben|hat|kommen|kommt|zieht|ziehen|räumt|"
                        r"räumen|schliessen|schliesst|geben|gibt)\b")


def issuer_of(ingress: str) -> str | None:
    """Verbatim issuer: the text before the first basis clause, the enacting verb, or the first
    comma that opens a lower-case clause ("Der Regierungsrat des Kantons Schwyz, in Betracht ...")."""
    cuts = [len(ingress)]
    k = BASIS_KW.search(ingress)
    if k:
        cuts.append(k.start())
    v = ISSUER_CUT.search(ingress)
    if v:
        cuts.append(v.start())
    c = re.search(r",(\s*\[\d+\])*\s+(?=[a-zäöü])", ingress)
    if c:
        cuts.append(c.start())
    issuer = ingress[:min(cuts)]
    issuer = re.sub(r"[\s,]*(\[\d+\][\s,]*)*$", "", issuer).strip()
    if ISSUER_START.match(issuer):
        return issuer
    m2 = re.search(r"\b(?:beschliessen|vereinbaren|erlassen)\s+((?:die|der)\s+[^,:]+?)\s*[,:]", ingress)
    return m2.group(1) if m2 else None


def parse_date(vom: str | None) -> str | None:
    """First date of the "(Vom ...)" line: "7./18. November 1849" -> 1849-11-07,
    "28. April 1927 / 14. Juni 1928" -> 1927-04-28, "13. Dezember 2002/14. September 2007"."""
    if not vom:
        return None
    d = re.search(r"(\d{1,2})\.", vom)
    if not d:
        return None
    mo = next((m for m in re.finditer(r"[A-Za-zäÄ]+", vom[d.end():]) if m.group().lower() in MONTHS), None)
    if not mo:
        return None
    y = re.search(r"\b(\d{4})\b", vom[d.end() + mo.end():])
    if not y:
        return None
    return f"{y.group(1)}-{MONTHS[mo.group().lower()]:02d}-{int(d.group(1)):02d}"


def parse_pdf(data: bytes, sr: str) -> dict:
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    res = {"ingress": "", "issuer": None, "notes": {}, "vom": None, "title_pdf": None, "flag": None,
           "pages": doc.page_count}
    lines = _lines(doc, range(min(3, doc.page_count)), sr)
    if not lines:
        res["flag"] = "no text layer"
        return res
    body = _body_size(doc)
    lines = [l for l in lines if not _is_furniture(l, sr, body)]
    # title = lines before the "(Vom ...)" line; without one, the leading bold lines
    vi = next((i for i, l in enumerate(lines[:12]) if VOM.match(_line_text(l, body).strip())), None)
    if vi is not None:
        res["title_pdf"] = _join([_line_text(l, body) for l in lines[:vi]])
        res["vom"] = re.sub(r"\[[^\]]*\]", "", _line_text(lines[vi], body)).strip()
        i = vi + 1
    else:
        i = 0
        while i < len(lines) and all((s["flags"] & 16) or _is_sup(s, body) or not _clean(s["text"]).strip()
                                     for s in lines[i]["spans"]):
            i += 1
        if i == 0:
            res["flag"] = "no (Vom ...) line and no title"
            return res
        res["title_pdf"] = _join([_line_text(l, body) for l in lines[:i]])
        res["flag"] = "no (Vom ...) line"
    preamble = False
    if i < len(lines) and _line_text(lines[i], body).strip() == "Präambel":
        preamble = True
        i += 1
    # candidate lines up to the first heading
    cand = []
    for ln in lines[i:]:
        t = _line_text(ln, body).strip()
        words = [s for s in ln["spans"] if _clean(s["text"]).strip() and not _is_sup(s, body)]
        if not words:
            if cand:
                cand.append(ln)                         # a marker on its own line
            continue
        bold = all(s["flags"] & 16 for s in words)
        small = all(s["size"] < body - 0.6 for s in words)
        if bold or small or HEADING.match(t):
            break
        cand.append(ln)
        if len(cand) > 80:
            break
    if not cand:
        return res
    texts = [_line_text(l, body) for l in cand]
    # the Ingress ends at the first line closing with ":" after an enacting word ("beschliesst:",
    # "folgende Vereinbarung:"); a colon without one ("zieht in Betracht:") does not end it
    end, first_colon = None, None
    for j in range(len(cand)):
        sofar = _join(texts[: j + 1])
        if re.search(r":(\s*\[\d+\])*$", sofar):
            if first_colon is None:
                first_colon = j
            head = re.sub(r"(\s*\[\d+\])*\s*:(\s*\[\d+\])*$", "", sofar)
            seg = head.rsplit(":", 1)[-1]                # since the previous colon
            if ENACT_END.search(head) or re.search(r"\b(" + ENACT + r")\b", seg):
                end = j
                break
    if end is None and first_colon is not None and \
            not re.search(r"[a-zäöüß]{3,}\.\s+[A-ZÄÖÜ]", _join(texts[: first_colon + 1])):
        end = first_colon                               # one sentence, unknown enacting word
        res["flag"] = "unknown enacting word: " + _join(texts[: end + 1])[-70:]
    if end is None:
        # no colon before the first heading: a preamble closed by "." ("beschliesst.",
        # "folgende Vereinbarung.", "... zusammen.")
        joined = _join(texts)
        if not re.search(r"[.:](\s*\[\d+\])*$", joined) or \
                not (ENACT_END.search(joined[:-1]) or re.search(r"\b(" + ENACT + r")\b", joined)) or \
                re.search(r"[a-zäöüß]{3,}\.\s+[A-ZÄÖÜ]", joined):
            res["flag"] = "text before the first article is not an Ingress: " + joined[:100]
            return res
        end = len(cand) - 1
        res["flag"] = "Ingress closes with '.': " + joined[-60:]
    ingress = _join(texts[: end + 1])
    res["ingress"] = ingress
    res["preamble"] = preamble
    res["issuer"] = issuer_of(ingress)
    markers = re.findall(r"\[(\d+)\]", ingress)
    if markers:
        alln = _footnotes(doc, sr, body)
        res["notes"] = {n: alln[n] for n in dict.fromkeys(markers) if n in alln}
        missing = [n for n in dict.fromkeys(markers) if n not in alln]
        if missing:
            res["flag"] = f"footnote(s) {missing} not found"
    return res


# ---------------------------------------------------------------- record

def abbr_like(a: str) -> bool:
    """An abbreviation, not a short title: "JG", "StHG", "VO RPG 2", "IKV 2020" - not
    "Staatshaftungsgesetz", "Psychiatriekonkordat", "ViCLAS-Konkordat"."""
    a = a.strip()
    toks = a.split()
    if not (2 <= len(a) <= 20) or len(toks) > 3 or not a[0].isalnum():
        return False
    if re.search(r"[a-zäöüß]{6,}", a) or not all(re.search(r"[A-ZÄÖÜ0-9]", t) for t in toks):
        return False
    return sum(c.isupper() for c in a) >= 2 or (len(a) <= 4 and a[0].isupper())


def abbr_of(title_pdf: str | None, keywords: str | None) -> tuple[str | None, str | None]:
    """Abbreviation as the text header states it ("(JG)", "(Denkmalschutzverordnung, DSV)"),
    else LexFind's keywords field when it holds one ("KV", "Staatshaftungsgesetz, StHG")."""
    if title_pdf:
        t = re.sub(r"(\[\d+\])+\s*$", "", title_pdf).strip()
        while True:
            m = re.search(r"\(([^()]+)\)$", t)
            if not m:
                break
            for part in reversed(re.split(r"[;,]", m.group(1))):
                if abbr_like(part):
                    return part.strip(), "pdf"
            t = t[:m.start()].rstrip()
    if keywords:
        for part in reversed(re.split(r"[;,]", keywords)):
            if abbr_like(part):
                return part.strip(), "lexfind_keywords"
    return None, None


def build(t: dict) -> tuple[dict, dict]:
    tid = t["id"]
    sr = t["systematic_number"].strip()
    det = json.loads(cached(RAW / "tol" / f"{tid}.json",
                            lambda: get(f"{API}/texts-of-law/{tid}/with-version-groups").content))
    dta = [d for d in det.get("dta_urls") or [] if d.get("language") == "de"] or det.get("dta_urls") or []
    original = next((d["original_url"] for d in dta if d.get("original_url")), None)
    cur = None
    for fam in det.get("families") or []:
        for grp in fam:
            for v in grp:
                if v.get("info_badge") == "current" and cur is None:
                    cur = v
    parsed = {"ingress": "", "issuer": None, "notes": {}, "flag": "no PDF"}
    if dta:
        try:
            pdf = cached(RAW / "pdf" / f"{tid}.pdf",
                         lambda: get("https://www.lexfind.ch" + dta[0]["url"]).content)
            if pdf.startswith(b"%PDF"):
                parsed = parse_pdf(pdf, sr)
            else:
                parsed["flag"] = "LexFind text is not a PDF"
        except Exception as e:
            parsed = {"ingress": "", "issuer": None, "notes": {}, "flag": f"pdf: {e}"}
    abbr, abbr_src = abbr_of(parsed.get("title_pdf"), t.get("keywords"))
    rec = {
        "ct": "SZ",
        "sr": sr,
        "title": re.sub(r"\s+", " ", html.unescape(t["title"])).strip(),
        "abbr": abbr,
        "url": original or f"https://www.lexfind.ch/fe/de/tol/{tid}/de",
        "in_force": bool(t.get("is_active")),
        "adopted": parse_date(parsed.get("vom")),
        "issuer": parsed.get("issuer"),
        "ingress": parsed.get("ingress", ""),
        "notes": parsed.get("notes", {}),
        "links": [],
        "lang": "de",
        "src": "lexfind",
    }
    meta = {"lexfind_id": tid, "lexfind": f"https://www.lexfind.ch/fe/de/tol/{tid}/de",
            "category_id": t.get("category_id"),
            "category": (cur or {}).get("category", {}).get("name"),
            "keywords": t.get("keywords"), "abbr_src": abbr_src, "title_pdf": parsed.get("title_pdf"),
            "vom": parsed.get("vom"), "version_active_since": (cur or {}).get("version_active_since"),
            "flag": parsed.get("flag")}
    return rec, meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="comma-separated SRSZ numbers")
    args = ap.parse_args()
    t0 = time.time()
    tols = enumerate_acts()
    acts = [t for t in tols if is_act(t)]
    print(f"SZ: {len(tols)} active LexFind texts, {len(acts)} acts "
          f"(skipped: {[t['systematic_number'] for t in tols if not is_act(t)]})", file=sys.stderr)
    if args.only:
        want = set(args.only.split(","))
        acts = [a for a in acts if a["systematic_number"].strip() in want]
    if args.limit:
        acts = acts[: args.limit]
    done = [0]

    def work(a):
        r = build(a)
        done[0] += 1
        if done[0] % 50 == 0:
            print(f"  {done[0]}/{len(acts)}  {time.time() - t0:.0f}s", file=sys.stderr)
        return r

    with ThreadPoolExecutor(WORKERS) as ex:
        results = list(ex.map(work, acts))
    results.sort(key=lambda rm: [(0, int(p), "") if p.isdigit() else (1, 0, p)
                                 for p in re.split(r"[.\s]", rm[0]["sr"])])
    recs = [r for r, _ in results]
    if not args.only and not args.limit:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (RAW / "meta.json").write_text(json.dumps([dict(sr=r["sr"], **m) for r, m in results],
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        for r, m in results:
            print(json.dumps(r, ensure_ascii=False), json.dumps(m, ensure_ascii=False))
    print(f"SZ: {len(recs)} acts, ingress {sum(1 for r in recs if r['ingress'])}, adopted "
          f"{sum(1 for r in recs if r['adopted'])}, abbr {sum(1 for r in recs if r['abbr'])}, "
          f"flags {sum(1 for _, m in results if m['flag'])}, {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
