"""Cantonal acts in force from the 19 LexWork portals (official cantonal collections).

LexWork (Sitrox/Ronorp) serves the same JSON API on every canton's own host:
  /api/<lang>/texts_of_law/lightweight_index      every act (systematic number, title, abrogated)
  /api/<lang>/texts_of_law/<sr>/show_as_json       one act; json_content.document.header holds the
                                                   Ingress per language (ingress_author,
                                                   ingress_foundation, ingress_action), and
                                                   json_content.footnotes the notes it points to.
Only the header, the footnotes the header references and the act's scalar metadata are kept
(build/cantonal/raw/<CT>/<sr>.json), so a rerun is offline. Output: build/cantonal/<CT>.json in
the contract of SPEC.md, plus "i18n" with the other languages the canton publishes.

Acts the portal holds only as a PDF (older texts never converted; no json_content): the
Ingress is read from the PDF's first two pages, between the date line and the first article.

Usage: python3 pipeline/cantonal/lexwork.py [CT ...]     (~15 min for all 19, network bound)
"""
import html
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refresh import fresh  # noqa: E402  (weekly refresh)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "cantonal"
UA = "swiss-law-graph/1.0 (legal research; +https://opencaselaw.ch)"

HOSTS = {
    "AG": "gesetzessammlungen.ag.ch", "AI": "ai.clex.ch", "AR": "ar.clex.ch",
    "BE": "www.belex.sites.be.ch", "BL": "bl.clex.ch", "BS": "www.gesetzessammlung.bs.ch",
    "FR": "bdlf.fr.ch", "GL": "gesetze.gl.ch",   # not gl.clex.ch: its redirect drops the %2F in "VII C/12/1"
    "GR": "www.gr-lex.gr.ch", "LU": "srl.lu.ch",
    "NW": "nw.clex.ch", "OW": "ow.clex.ch", "SG": "www.gesetzessammlung.sg.ch",
    "SH": "sh.clex.ch", "SO": "bgs.so.ch", "TG": "www.rechtsbuch.tg.ch",
    "UR": "rechtsbuch.ur.ch", "VS": "lex.vs.ch", "ZG": "bgs.zg.ch",
}
LANG = {"FR": "fr", "VS": "fr"}          # primary language where it is not German
PER_HOST = 2


def session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    a = requests.adapters.HTTPAdapter(max_retries=requests.adapters.Retry(
        total=4, backoff_factor=3, status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"})))
    s.mount("https://", a)
    return s


_local = threading.local()


def get(url):
    if not hasattr(_local, "s"):
        _local.s = session()
    for attempt in range(4):
        try:
            r = _local.s.get(url, timeout=90)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))


def text(h):
    """HTML fragment -> plain text; footnote anchors become [n]."""
    h = re.sub(r"<br\s*/?>", " ", h or "")
    h = re.sub(r"</(p|div|li|h\d)>", " ", h)
    h = re.sub(r"<[^>]+>", "", h)
    h = re.sub(r"\s+", " ", html.unescape(h)).strip()
    return re.sub(r"(?<=[\s\],;:])\*(?=\s|$)|^\*\s*", "", h).replace(" ,", ",").strip()


def block(header, cls):
    m = re.search(r"<(h\d|div) class='%s'>(.*?)</\1>" % cls, header, re.S)
    return m.group(2) if m else ""


def links(h):
    out = []
    for m in re.finditer(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', h, re.S):
        if 'class="footnote"' in m.group(0):
            continue
        out.append({"text": text(m.group(2)), "href": m.group(1)})
    return out


def footnotes(fn_html):
    """{anchor name: (marker, plain text, [links])} for every footnote of the act."""
    out = {}
    for li in re.findall(r"<li>(.*?)</li>", fn_html or "", re.S):
        m = re.search(r"href='#([^']+)'[^>]*>\[(\d+)\]</a>", li)
        if not m:
            continue
        body = re.sub(r"^.*?\[\d+\]</a>", "", li, count=1, flags=re.S)
        out[m.group(1)] = (m.group(2), text(body), links(body))
    return out


def parse_lang(header, fns):
    found = block(header, "ingress_foundation")
    author = text(block(header, "ingress_author"))
    action = text(block(header, "ingress_action"))
    notes, ls = {}, []
    for name in re.findall(r'class="footnote" name="([^"]+)"', found + block(header, "ingress_author")):
        if name in fns:
            mk, t, l = fns[name]
            notes[mk] = t
            ls += l
    ls = links(found) + ls
    ingress = " ".join(x for x in (author, text(found), action) if x)
    abbr = text(block(header, "abbreviation")).strip("() ") or None
    return {"title": text(block(header, "title")), "abbr": abbr, "issuer": author,
            "ingress": ingress, "notes": notes, "links": ls,
            "enactment": text(block(header, "enactment"))}


def fetch_act(ct, host, lang, stub):
    sr = stub["systematic_number"]
    raw = OUT / "raw" / ct / (re.sub(r"[^\w.\-]", "_", sr) + ".json")
    if fresh(raw):                                       # the act's header changes: re-read in a weekly refresh
        return json.loads(raw.read_text())
    try:
        d = get(f"https://{host}/api/{lang}/texts_of_law/{quote(sr, safe='')}/show_as_json")
    except (requests.RequestException, ValueError) as e:
        return {"sr": sr, "missing": True, "error": str(e)[:200]}      # not cached: a rerun retries it
    if not d:
        rec = {"sr": sr, "missing": True}
    else:
        t = d["text_of_law"]
        sv = t.get("selected_version") or t.get("current_version") or {}
        jc = sv.get("json_content") or {}
        doc = jc.get("document") or {}
        header = doc.get("header") or {}
        fn_all = jc.get("footnotes") or {}
        names = {n for h in header.values() if h
                 for n in re.findall(r'class="footnote" name="([^"]+)"', h)}
        fn_keep = {}
        for lg, h in fn_all.items():
            keep = [li for li in re.findall(r"<li>.*?</li>", h or "", re.S)
                    if any(f"#{n}'" in li for n in names)]
            fn_keep[lg] = "".join(keep)
        rec = {"sr": sr, "meta": {k: v for k, v in t.items() if not isinstance(v, (dict, list))},
               "header": header, "footnotes": fn_keep}
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps(rec, ensure_ascii=False))
    return rec


PDF_END = re.compile(r"^\s*(?:§\s*1\b|Art(?:\.|ikel)\s*1\b|Article\s+(?:premier|1(?:er)?)\b|Articolo\s+1\b|I\.\s|1\.\s+(?:Abschnitt|Kapitel|Titel|Teil)|Chapitre|Titre\s+premier|Capitolo)", re.M)
PDF_DATE = re.compile(r"^\s*(?:Vom|vom|Du|du|Del|del)\s+\d{1,2}\.?\s*\S+\s+\d{4}.*$", re.M)
PDF_NOTE = re.compile(r"^\s*(\d{1,2})\)?\s+((?:SR|RS|BGS|BSG|SGS|GS|SG|sGS|SRL|GDB|NG|SHR|bGS|RB|BR|SAR|RSF|RS/VS|SRSZ|LS)\b.*)$", re.M)


def pdf_text(url):
    import pymupdf
    if not hasattr(_local, "s"):
        _local.s = session()
    r = _local.s.get(url, timeout=120)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return ""
    doc = pymupdf.open(stream=r.content, filetype="pdf")
    return "\n".join(doc[k].get_text() for k in range(min(2, len(doc))))


def pdf_ingress(txt):
    """(ingress, notes) from the first pages of a PDF: after the date line, before article 1."""
    m = PDF_DATE.search(txt)
    if not m:
        return "", {}
    end = PDF_END.search(txt, m.end())
    body = txt[m.end(): end.start() if end else m.end() + 1500]
    notes = {n: t.strip() for n, t in PDF_NOTE.findall(txt)}
    body = re.sub(r"(?<=[A-Za-zäöüéèà,])\s*(\d{1,2})\)", r"[\1]", body)       # "Kantonsverfassung 1)" -> [1]
    body = re.sub(r"-\n(?=[a-zäöü])", "", body)
    return re.sub(r"\s+", " ", body).strip(), notes


def canton(ct):
    host, lang = HOSTS[ct], LANG.get(ct, "de")
    idx_path = OUT / "raw" / ct / "_index.json"
    if fresh(idx_path):
        idx = json.loads(idx_path.read_text())
    else:
        idx = get(f"https://{host}/api/{lang}/texts_of_law/lightweight_index")
        idx_path.parent.mkdir(parents=True, exist_ok=True)
        idx_path.write_text(json.dumps(idx, ensure_ascii=False))
    stubs = [x for v in (idx.values() if isinstance(idx, dict) else [idx]) for x in v]
    stubs = sorted({s["systematic_number"]: s for s in stubs if not s.get("abrogated")}.values(),
                   key=lambda s: s["systematic_number"])
    with ThreadPoolExecutor(PER_HOST) as ex:
        raws = list(ex.map(lambda s: fetch_act(ct, host, lang, s), stubs))
    out = []
    for stub, r in zip(stubs, raws):
        if r.get("missing"):
            continue
        if not any((r.get("header") or {}).values()) and "pdf" not in r and (r["meta"].get("pdf_link")):
            try:
                r["pdf"] = pdf_text(r["meta"]["pdf_link"])[:6000]
            except Exception as e:                           # a PDF that fails stays without Ingress
                r["pdf"] = ""
                r["pdf_error"] = str(e)[:200]
            (OUT / "raw" / ct / (re.sub(r"[^\w.\-]", "_", r["sr"]) + ".json")).write_text(json.dumps(r, ensure_ascii=False))
        m = r["meta"]
        fns = {lg: footnotes(h) for lg, h in r["footnotes"].items()}
        per = {lg: parse_lang(h, fns.get(lg, {})) for lg, h in r["header"].items() if h}
        p = per.get(lang) or next(iter(per.values()), None) or {}
        src = "portal"
        if not p.get("ingress") and r.get("pdf"):
            ing, nts = pdf_ingress(r["pdf"])
            if ing:
                p = {**p, "ingress": ing, "notes": {k: v for k, v in nts.items() if f"[{k}]" in ing}, "links": []}
                src = "portal_pdf"
        rec = {"ct": ct, "sr": r["sr"], "title": m.get("title") or p.get("title") or stub["title"],
               "abbr": m.get("abbreviation") or p.get("abbr") or None,
               "url": m.get("canonical_link") or f"https://{host}/app/{lang}/texts_of_law/{r['sr']}",
               "in_force": not m.get("abrogated"), "adopted": m.get("date_of_decision"),
               "issuer": p.get("issuer", ""), "ingress": p.get("ingress", ""),
               "notes": p.get("notes", {}), "links": p.get("links", []), "lang": lang,
               "src": src, "enactment": p.get("enactment", "")}
        alt = {lg: {k: v[k] for k in ("title", "abbr", "issuer", "ingress", "notes")}
               for lg, v in per.items() if lg != lang and (v["title"] or v["ingress"])}
        if alt:
            rec["i18n"] = alt
        out.append(rec)
    (OUT / f"{ct}.json").write_text(json.dumps(out, ensure_ascii=False, indent=0))
    n_in = sum(1 for x in out if x["ingress"])
    n_ab = sum(1 for x in out if x["abbr"])
    print(f"{ct}: {len(stubs)} in index, {len(out)} acts, ingress {n_in}, abbr {n_ab}", flush=True)
    return ct, len(out)


if __name__ == "__main__":
    cts = [c.upper() for c in sys.argv[1:]] or sorted(HOSTS)
    with ThreadPoolExecutor(len(cts)) as ex:
        list(ex.map(canton, cts))
