#!/usr/bin/env python3
"""ZH adapter: acts in force in the Zürcher Loseblattsammlung (LS) -> build/cantonal/ZH.json.

Source (official portal, src "portal"):
  listing  https://www.zh.ch/de/politik-staat/gesetze-beschluesse/gesetzessammlung/_jcr_content/
           main/lawcollectionsearch_312548694.zhweb-zhlex-ls.zhweb-cache.json?fileNumber=<1..14>&page=<n>
           The unfiltered listing stops at 150 hits ("moreSearchResultsThanAllowed"), so it is read
           per Ordner (fileNumber 1-14, each < 150 acts). page is 1-based (page=0 repeats page 1).
           Without includeRepealedEnactments the listing carries acts in force only.
  detail   https://www.zh.ch/de/.../zhlex-ls/erlass-<nr>-<date>-<date>-<nachtrag>.html: PDF link,
           Kurztitel, "Link auf aktuelle Version" (the stable permalink used as "url").
  text     https://www.notes.zh.ch/appl/zhlex_r.nsf/OpenAttachment?...pdf (answers with a JS redirect
           to /appl/zhlex_r.nsf/WebView/<docid>/$File/<name>.pdf). zh.ch offers no HTML text.
           The Ingress is read from the first page(s) of the PDF (between the "(vom ...)" line and the
           first heading/article); footnotes are endnotes at the end of the PDF ("4 LS 171.1.").

Raw responses are cached under build/cantonal/raw/ZH/ (list/, detail/, pdf/); a rerun is offline.
Usage: python3 pipeline/cantonal/zh.py [--limit N] [--only 700.1,131.1]
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

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "build" / "cantonal" / "raw" / "ZH"
OUT = ROOT / "build" / "cantonal" / "ZH.json"

UA = "swiss-law-graph/1.0 (legal research; +https://opencaselaw.ch)"
LIST_URL = ("https://www.zh.ch/de/politik-staat/gesetze-beschluesse/gesetzessammlung/_jcr_content/"
            "main/lawcollectionsearch_312548694.zhweb-zhlex-ls.zhweb-cache.json")
FOLDERS = range(1, 15)          # "Ordner" 1-14 of the LS search form (101-176 ... 861-954)
DELAY = 0.25                    # seconds after each request, per worker
WORKERS = 3                     # <= 3 concurrent requests per host

ENACT = (r"beschliesst|beschliessen|verfügt|verfügen|verordnet|verordnen|erlässt|erlassen|"
         r"vereinbaren|vereinbart|bestimmt|bestimmen|setzt\s+fest|setzen\s+fest|ordnet\s+an|"
         r"schliessen|schliesst|geben\s+uns\s+die\s+folgende\s+Verfassung|beschlossen|"
         r"genehmigt|erklärt|erklären|stellt\s+fest")
BASIS_KW = re.compile(
    r",?\s*\b(gestützt|in\s+Betracht|in\s+Hinsicht|auf\s+Gesuch|mit\s+dem\s+Ziel|nach\s+Einsicht|in\s+Anbetracht|in\s+Ausführung|in\s+Anwendung|in\s+Vollziehung|"
    r"in\s+Vollzug|auf\s+Antrag|auf\s+den\s+Antrag|nach\s+Kenntnisnahme|in\s+Kenntnis|"
    r"in\s+Erwägung|im\s+Bestreben|in\s+der\s+Absicht|mit\s+Rücksicht|aufgrund|auf\s+Grund|"
    r"nach\s+Prüfung|in\s+Revision|in\s+Verantwortung|im\s+Hinblick|in\s+Ergänzung|"
    r"in\s+Abänderung|unter\s+Hinweis|nach\s+Anhörung|in\s+Berücksichtigung|"
    r"vorbehältlich|unter\s+Vorbehalt|im\s+Sinne|im\s+Rahmen)\b")
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
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return data


# ---------------------------------------------------------------- enumeration

def enumerate_acts() -> list[dict]:
    acts: dict[str, dict] = {}
    for f in FOLDERS:
        page, pages = 1, 1
        while page <= pages:
            p = RAW / "list" / f"folder{f:02d}_p{page:02d}.json"
            d = json.loads(cached(p, lambda: get(LIST_URL, params={"fileNumber": f, "page": page}).content))
            if d.get("moreSearchResultsThanAllowed"):
                raise SystemExit(f"folder {f}: listing truncated by the portal")
            pages = d.get("numberOfResultPages") or 1
            for x in d.get("data", []):
                x["folder"] = f
                acts.setdefault(x["link"], x)
            page += 1
        n = sum(1 for a in acts.values() if a["folder"] == f)
        if n != d.get("numberOfResults"):
            print(f"  folder {f}: {n} unique acts vs numberOfResults {d.get('numberOfResults')}",
                  file=sys.stderr)
    return list(acts.values())


# ---------------------------------------------------------------- detail + pdf

def key_of(link: str) -> str:
    return link.rsplit("/", 1)[-1].removesuffix(".html")


def dd(page: str, label: str) -> str | None:
    m = re.search(r"<dt>\s*" + re.escape(label) + r"\s*</dt>\s*<dd>(.*?)</dd>", page, re.S)
    if not m:
        return None
    v = re.sub(r"<[^>]+>", " ", m.group(1))
    v = re.sub(r"\s+", " ", html.unescape(v)).strip()
    return v or None


def permalink(page: str) -> str | None:
    m = re.search(r"<dt>\s*Link auf aktuelle Version\s*</dt>\s*<dd>\s*<span>([^<]+)</span>", page)
    return html.unescape(m.group(1)).strip() if m else None


def fetch_detail(act: dict) -> dict:
    link = act["link"]
    page = cached(RAW / "detail" / f"{key_of(link)}.html",
                  lambda: get("https://www.zh.ch" + link).content).decode("utf-8")
    # the cached listing can lag behind: follow the history entry marked "(aktuell)"
    m = re.search(r'<a href="([^"]+\.html)">\s*<input checked="true"[^>]*placeholder="[^"]*\(aktuell\)"',
                  page)
    cur = re.search(r'<a href="([^"]+\.html)">\s*<input[^>]*placeholder="[^"]*\(aktuell\)"', page)
    if not m and cur and cur.group(1) != link:
        link = cur.group(1)
        page = cached(RAW / "detail" / f"{key_of(link)}.html",
                      lambda: get("https://www.zh.ch" + link).content).decode("utf-8")
    pdf = re.search(r'href="(https://www\.notes\.zh\.ch/[^"]+\.pdf)"', page)
    return {
        "link": link,
        "pdf_url": html.unescape(pdf.group(1)) if pdf else None,
        "kurztitel": dd(page, "Kurztitel"),
        "erlassdatum": dd(page, "Erlassdatum"),
        "inkraft": dd(page, "Inkraftsetzungsdatum"),
        "aufhebung": dd(page, "Aufhebungsdatum"),
        "title": dd(page, "Erlasstitel"),
        "permalink": permalink(page),
    }


def fetch_pdf(key: str, url: str) -> bytes:
    def go() -> bytes:
        r = get(url)
        body = r.content
        if len(body) < 2000 and b"window.location" in body:
            loc = re.search(rb'window\.location="([^"]+)"', body).group(1).decode()
            if loc.startswith("/"):
                loc = "https://www.notes.zh.ch" + loc
            body = get(loc).content
        if not body.startswith(b"%PDF"):
            raise RuntimeError(f"not a PDF: {url}")
        return body
    return cached(RAW / "pdf" / f"{key}.pdf", go)


# ---------------------------------------------------------------- PDF parsing

def _lines(doc, pages) -> list[dict]:
    """Text lines of the given pages, header/footer removed, in reading order."""
    out = []
    for pno in pages:
        if pno >= doc.page_count:
            break
        pg = doc[pno]
        h = pg.rect.height
        for b in pg.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                spans = [s for s in ln["spans"] if s["text"] != "\n"]
                if not spans or not "".join(s["text"] for s in spans).strip():
                    continue
                y0 = ln["bbox"][1]
                if y0 < 0.10 * h or y0 > 0.89 * h:      # running head, Nachtragsstand, page no.
                    continue
                out.append({"p": pno, "x": ln["bbox"][0], "y": y0, "y1": ln["bbox"][3], "spans": spans})
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


def _clean(t: str) -> str:
    return re.sub(r"[\u00a0\u202f\u2009\u2007\t]", " ", re.sub(r"[\ufeff\u200b]", "", t))


def _is_sup(s, body_size) -> bool:
    return bool(s["flags"] & 1) or (s["size"] < 0.75 * body_size and _clean(s["text"]).strip()[:1].isdigit())


def _line_text(ln, body_size=9.2) -> str:
    parts = []
    for s in ln["spans"]:
        t = _clean(s["text"])
        if _is_sup(s, body_size):
            nums = [n for n in re.split(r"[,\s]+", t) if n]
            t = "".join(f"[{n}]" for n in nums)
        parts.append(t)
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
                text += t                               # "GebV-" + "AIG"
        else:
            text += " " + t
    text = text.replace("­", "")
    return re.sub(r"\s+", " ", text).strip()


def _footnotes(doc) -> dict[str, str]:
    """Endnotes at the end of an LS PDF: a small number span followed by ~8pt text.
    Later occurrences win (the endnote block closes the document)."""
    entries: list[tuple[str, list[str]]] = []
    cur = None
    for pno in range(doc.page_count):
        pg = doc[pno]
        h = pg.rect.height
        for b in pg.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                spans = [s for s in ln["spans"] if s["text"].strip()]
                if not spans:
                    continue
                y0 = ln["bbox"][1]
                if y0 < 0.10 * h or y0 > 0.89 * h:
                    continue
                first, rest = spans[0], spans[1:]
                if (re.fullmatch(r"\d{1,3}", _clean(first["text"]).strip()) and first["size"] < 6.5
                        and rest and all(6.8 <= s["size"] <= 8.6 for s in rest)):
                    cur = ["".join(s["text"] for s in ln["spans"][ln["spans"].index(first) + 1:])]
                    entries.append((_clean(first["text"]).strip(), cur))
                elif cur is not None and all(6.8 <= s["size"] <= 8.6 or (s["flags"] & 1) for s in spans) \
                        and not any(s["flags"] & 16 for s in spans):
                    cur.append("".join(s["text"] for s in ln["spans"]))
                else:
                    cur = None
    notes: dict[str, str] = {}
    for k, v in entries:
        notes[k] = _join([_clean(t) for t in v])
    return notes


VOM = re.compile(r"^\(?\s*(vom|von)\s+\d", re.I)
# article lines are "§ 1.    text" / "Art. 1    text"; an Ingress line may start "§ 40 Abs. 1 ...",
# "§§ 60 ff. ..."
HEADING = re.compile(r"^(§\s*\d+(\s?[a-z])?\.(\s*\[\d+\])*(\s|$)|(Art\.|Artikel)\s*\d+\s*[a-z]*\.?(\s*\[\d+\])*(\s{2,}|$)|"
                     r"[IVXLC]+\.(\s|$)|\d+\.\s*(Teil|Titel|Abschnitt|Kapitel|Unterabschnitt)\b|\d+\.(\s*\[\d+\])*\s*$|"
                     r"\d+\.\s{2,}|\d+\.\s+\[\d+\]|"
                     r"[A-Z]\.\s|Präambel\b|Einleitung\b|Inhaltsverzeichnis)")
ENACT_END = re.compile(r"\b(" + ENACT + r"|folgende[nrs]?\s+\w+|nachstehende[nrs]?\s+\w+|"
                       r"nachfolgende[nrs]?\s+\w+|wie\s+folgt|was\s+folgt|überein|übereingekommen)\b[^:]{0,80}$",
                       re.I)
ISSUER_CUT = re.compile(r"\s(" + ENACT + r"|erteilt|erteilen|verleiht|verleihen|verabschiedet|"
                        r"verabschieden|treffen|trifft|haben|hat|kommen|kommt|zieht|ziehen|räumt|"
                        r"räumen|gibt|geben|sind\s+übereingekommen)\b")
ISSUER_START = re.compile(r"^(Der|Die|Das|Wir)\b")


def _body_size(doc) -> float:
    """Body text size: character-weighted mode, endnote/marginal-note sizes (< 8.6 pt) left out."""
    big, allc = Counter(), Counter()
    for pg in doc:
        for b in pg.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln["spans"]:
                    n = len(_clean(sp["text"]).strip())
                    allc[round(sp["size"], 1)] += n
                    if sp["size"] >= 8.6:
                        big[round(sp["size"], 1)] += n
    c = big if sum(big.values()) >= 100 else allc
    return c.most_common(1)[0][0] if c else 9.2


def issuer_of(ingress: str) -> str | None:
    """Verbatim issuer: the text before the first basis clause, the enacting verb, or the first
    comma that opens a lower-case clause."""
    cuts = [len(ingress)]
    for m in (BASIS_KW.search(ingress), ISSUER_CUT.search(ingress),
              re.search(r",(\s*\[\d+\])*\s+(?=[a-zäöü])", ingress)):
        if m:
            cuts.append(m.start())
    issuer = re.sub(r"[\s,]*(\[\d+\][\s,]*)*$", "", ingress[:min(cuts)]).strip()
    if ISSUER_START.match(issuer):
        return issuer
    m2 = re.search(r"\b(?:" + ENACT + r")\s+((?:die|der|das)\s+[^,:]+?)\s*(\[\d+\])*\s*[,:]", ingress)
    return m2.group(1) if m2 else None


def parse_pdf(data: bytes) -> dict:
    import pymupdf
    doc = pymupdf.open(stream=data, filetype="pdf")
    res = {"ingress": "", "issuer": None, "notes": {}, "vom": None, "pages": doc.page_count,
           "flag": None}
    lines = _lines(doc, range(min(3, doc.page_count)))
    if not lines:
        res["flag"] = "no text layer"
        return res
    body = _body_size(doc)
    # title block = leading large bold lines; then "(vom ...)"
    i = 0
    while i < len(lines) and all(s["size"] > body + 1.5 or _is_sup(s, body) or not _clean(s["text"]).strip()
                                 for s in lines[i]["spans"]):
        i += 1
    if i < len(lines) and VOM.match(_line_text(lines[i], body).strip()):
        res["vom"] = re.sub(r"\[[^\]]*\]", "", _line_text(lines[i], body)).strip()
        i += 1
    else:
        res["flag"] = "no (vom ...) line"
    x_body = lines[i]["x"] if i < len(lines) else 54
    preamble = False
    if i < len(lines) and _line_text(lines[i], body).strip() == "Präambel":
        preamble = True
        i += 1
    cand = []
    for ln in lines[i:]:
        t = _line_text(ln, body).strip()
        words = [s for s in ln["spans"] if _clean(s["text"]).strip() and not _is_sup(s, body)]
        if not words:
            if cand:
                cand.append(ln)
            continue
        bold = all(s["flags"] & 16 for s in words)
        small = all(s["size"] < body - 1 for s in words)
        if bold or small or HEADING.match(t):
            break
        if abs(ln["x"] - x_body) > 40:                  # marginal note column
            break
        cand.append(ln)
        if len(cand) > 80:
            break
    if not cand:
        return res
    texts = [_line_text(l, body) for l in cand]
    # the Ingress ends at the first line closing with ":" after an enacting word ("beschliesst:",
    # "verfügt die Direktion der Finanzen:", "vereinbaren, was folgt:"); a colon without one does not
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
        joined = _join(texts)
        if not re.search(r"[.:](\s*\[\d+\])*$", joined) or not ENACT_END.search(joined[:-1]):
            res["flag"] = "text before the first article is not an Ingress: " + joined[:100]
            return res
        end = len(cand) - 1
        res["flag"] = "Ingress closes with '.': " + joined[-60:]
    ingress = _join(texts[: end + 1])
    res["ingress"] = ingress
    res["preamble"] = preamble
    # issuer: the leading italic run (ZH sets issuer and enacting word in italics), else issuer_of()
    ital = []
    for l in cand:
        for sp in l["spans"]:
            if not _clean(sp["text"]).strip():
                continue
            if sp["flags"] & 2:
                ital.append(_clean(sp["text"]))
            else:
                break
        else:
            continue
        break
    issuer = _join(ital) if ital else ""
    issuer = re.sub(r"\s+(" + ENACT + r")\s*(\[\d+\])*\s*:\s*$", "", issuer)
    issuer = re.sub(r"[\s,]*(\[\d+\][\s,]*)*$", "", issuer).strip()
    if not ISSUER_START.match(issuer) or len(issuer) > 200:
        issuer = issuer_of(ingress)
    res["issuer"] = issuer or None
    markers = list(dict.fromkeys(re.findall(r"\[(\d+)\]", ingress)))
    if markers:
        allnotes = _footnotes(doc)
        res["notes"] = {n: allnotes[n] for n in markers if n in allnotes}
        missing = [n for n in markers if n not in allnotes]
        if missing:
            res["flag"] = f"footnote(s) {missing} not found"
    return res


# ---------------------------------------------------------------- record

def abbr_like(a: str) -> bool:
    """An abbreviation, not a short title: "PBG", "OG RR", "KBüG", "GeschO SyR", "IKV 2020" -
    not "Notariatsverordnung", "rpg-Verordnung", "HarmoS-Konkordat"."""
    a = a.strip()
    toks = a.split()
    if not (2 <= len(a) <= 20) or len(toks) > 3 or not a[0].isalnum():
        return False
    if re.search(r"[a-zäöüß]{6,}", a) or not all(re.search(r"[A-ZÄÖÜ0-9]", t) for t in toks):
        return False
    return sum(c.isupper() for c in a) >= 2 or (len(a) <= 4 and a[0].isupper())


def abbr_of(title: str, kurztitel: str | None) -> str | None:
    """The abbreviation the portal states: its Kurztitel field ("Entschädigungsreglement, ER") or a
    parenthesis closing the official title ("Planungs- und Baugesetz (PBG)")."""
    groups = []
    if kurztitel and kurztitel.strip() not in ("-", ""):
        groups.append(kurztitel.strip().strip("()"))
    t = title
    while True:
        m = re.search(r"\(([^()]+)\)\s*$", t)
        if not m:
            break
        groups.append(m.group(1))
        t = t[:m.start()].rstrip()
    for g in groups:
        for part in reversed(re.split(r"[;,]", g)):
            if abbr_like(part):
                return part.strip()
    return None


def iso(d: str | None) -> str | None:
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", (d or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def build(act: dict) -> dict:
    det = fetch_detail(act)
    key = key_of(det["link"])
    parsed = {"ingress": "", "issuer": None, "notes": {}, "flag": "no PDF link"}
    if det["pdf_url"]:
        try:
            parsed = parse_pdf(fetch_pdf(key, det["pdf_url"]))
        except Exception as e:                          # keep the act, report the failure
            parsed = {"ingress": "", "issuer": None, "notes": {}, "flag": f"pdf: {e}"}
    sr = act["referenceNumber"].strip()
    title = re.sub(r"\s+", " ", html.unescape(act["enactmentTitle"])).strip()
    perma = det["permalink"] or f"http://www.zhlex.zh.ch/Erlass.html?Open&Ordnr={sr}"
    rec = {
        "ct": "ZH",
        "sr": sr,
        "title": title,
        "abbr": abbr_of(title, det["kurztitel"]),
        "url": perma.replace("http://", "https://", 1),
        "in_force": not (act.get("withdrawalDate") or "").strip(),
        "adopted": iso(act.get("enactmentDate")) or iso(det["erlassdatum"]),
        "issuer": parsed.get("issuer"),
        "ingress": parsed.get("ingress", ""),
        "notes": parsed.get("notes", {}),
        "links": [],
        "lang": "de",
        "src": "portal",
    }
    meta = {"page": "https://www.zh.ch" + det["link"], "pdf": det["pdf_url"], "vom": parsed.get("vom"),
            "flag": parsed.get("flag"), "kurztitel": det["kurztitel"], "folder": act["folder"],
            "inkraft": iso(det["inkraft"]), "preamble": parsed.get("preamble", False)}
    return rec, meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only", help="comma-separated LS numbers")
    args = ap.parse_args()
    t0 = time.time()
    acts = enumerate_acts()
    print(f"ZH: {len(acts)} acts listed in folders 1-14", file=sys.stderr)
    if args.only:
        want = set(args.only.split(","))
        acts = [a for a in acts if a["referenceNumber"].strip() in want]
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
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not args.only and not args.limit:
        OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        (RAW / "meta.json").write_text(json.dumps([dict(sr=r["sr"], **m) for r, m in results],
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        for r, m in results:
            print(json.dumps(r, ensure_ascii=False), json.dumps(m, ensure_ascii=False))
    n = len(recs)
    print(f"ZH: {n} acts, ingress {sum(1 for r in recs if r['ingress'])}, adopted "
          f"{sum(1 for r in recs if r['adopted'])}, abbr {sum(1 for r in recs if r['abbr'])}, "
          f"flags {sum(1 for _, m in results if m['flag'])}, {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
