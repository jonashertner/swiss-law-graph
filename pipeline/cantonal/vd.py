#!/usr/bin/env python3
"""VD adapter: Base législative vaudoise (BLV) -> build/cantonal/VD.json (contract: SPEC.md).

Source: the BLV "Publication" front-end https://prestations.vd.ch/pub/blv-publication/ (Angular
SPA). No documented API; the JSON endpoints below are the ones its main bundle calls
(main.<hash>.js, BLV Publication 11.1.3):

  1. api/actes/rechercher?sortBy=COTE&textes=ABREVIATION,COTE,TITRE&statuts=EN_VIGUEUR
         &importances=MAJEUR,MINEUR&categories=CONSOLIDE
     -> every consolidated act in force (one JSON list; no paging). "Majeur" acts are what the
        systematic tree (api/recueil-systematique) shows by default; "mineur" acts (mostly décrets
        and arrêtés, e.g. arrêtés de mise en vigueur, crédits, convocations) are in the same
        collection with their own cote. Both are kept; `importance` tells them apart.
  2. api/actes/CONSOLIDE?id=<acte id>&cote=<cote>
     -> the act's versions; the one with versionType ACTUELLE is today's text (the SPA's default).
  3. api/actes/<htmlId>/html
     -> the version as Akoma-Ntoso-flavoured XHTML: div.akn-preface (docType, docNumber,
        docTitle, docAbreviation, docDate[date]), then div.akn-autorite (issuer),
        div.akn-preamble (the "vu ..." clauses), div.akn-formula (enacting word), then the body;
        footnotes are <a class="akn-commentaire" identify=ID>[A]</a> resolved in
        div.akn-commentaires > div#ID.

Public page of an act (what the SPA's openActeDetail opens):
  https://prestations.vd.ch/pub/blv-publication/actes/consolide/<cote>?id=<acte id>

Raw responses are cached under build/cantonal/raw/VD/ (HTML gzipped), so a rerun is offline.
Usage: python3 pipeline/cantonal/vd.py [--offline] [--refresh-list] [--workers N]
"""
import argparse
import concurrent.futures as cf
import gzip
import html
import json
import re
import sys
import threading
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "build" / "cantonal" / "raw" / "VD"
OUT = ROOT / "build" / "cantonal" / "VD.json"

BASE = "https://prestations.vd.ch/pub/blv-publication/"
LIST_URL = (BASE + "api/actes/rechercher?sortBy=COTE&textes=ABREVIATION,COTE,TITRE"
            "&statuts=EN_VIGUEUR&importances=MAJEUR,MINEUR&categories=CONSOLIDE")
VERSIONS_URL = BASE + "api/actes/CONSOLIDE?id={id}&cote={cote}"
HTML_URL = BASE + "api/actes/{html_id}/html"
PAGE_URL = BASE + "actes/consolide/{cote}?id={id}"
UA = "swiss-law-graph/1.0 (legal research; +https://opencaselaw.ch)"

_tls = threading.local()


def session():
    s = getattr(_tls, "s", None)
    if s is None:
        s = _tls.s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept": "application/json, text/html;q=0.9"})
    return s


def fetch(url, offline, delay=0.25, tries=6):
    if offline:
        raise RuntimeError(f"offline and not cached: {url}")
    err = None
    for i in range(tries):
        try:
            r = session().get(url, timeout=60)
            if r.status_code == 200:
                time.sleep(delay)
                return r.content
            err = f"HTTP {r.status_code}"
            if r.status_code < 500 and r.status_code != 429:
                break
        except requests.RequestException as e:  # timeouts, resets
            err = repr(e)
        time.sleep(min(60, 2 ** i))
    raise RuntimeError(f"{url}: {err}")


def cached(path, url, offline, gz=False):
    """Bytes of url, from path if present, else fetched and written there."""
    if path.exists():
        data = path.read_bytes()
        return gzip.decompress(data) if gz else data
    data = fetch(url, offline)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(data, 9) if gz else data)
    tmp.replace(path)
    return data


# ---------------------------------------------------------------- minimal DOM
VOID = {"br", "img", "hr", "meta", "input", "link", "col", "area", "base", "wbr", "source"}
BLOCK = {"p", "div", "br", "li", "td", "th", "tr", "table", "tbody", "ul", "ol", "h1", "h2",
         "h3", "h4", "h5", "h6", "blockquote", "section"}


class Node:
    __slots__ = ("tag", "attrs", "kids", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.kids, self.parent = tag, attrs, [], parent

    def cls(self):
        return (self.attrs.get("class") or "").split()

    def iter(self):
        yield self
        for k in self.kids:
            if isinstance(k, Node):
                yield from k.iter()

    def elems(self):
        return [k for k in self.kids if isinstance(k, Node)]


class DomBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        n = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.kids.append(n)
        if tag not in VOID:
            self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def parse(fragment):
    b = DomBuilder()
    b.feed(fragment)
    b.close()
    return b.root


def is_marker(n):
    return n.tag == "a" and "akn-commentaire" in n.cls()


def text_of(node, out=None, skip_markers=False):
    """Text with block elements separated by spaces, whitespace normalised."""
    top = out is None
    out = [] if top else out
    for k in node.kids:
        if isinstance(k, str):
            out.append(k)
        elif k.tag in ("script", "style") or (skip_markers and is_marker(k)):
            continue
        else:
            if k.tag in BLOCK:
                out.append(" ")
            text_of(k, out, skip_markers)
            if k.tag in BLOCK:
                out.append(" ")
    return norm("".join(out)) if top else out


def norm(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ").replace("​", "")).strip()


ONCLICK_URL = re.compile(r"""window\.open\(\s*['"]([^'"]+)['"]""")


def href_of(a):
    h = a.attrs.get("href", "")
    if h and not h.lower().startswith("javascript"):
        return html.unescape(h)
    m = ONCLICK_URL.search(a.attrs.get("onclick", ""))
    if m and not m.group(1).lower().startswith("javascript"):
        return html.unescape(m.group(1))
    return None  # a few BLV footnote links are dead: window.open('javascript:void(0);')


# ---------------------------------------------------------------- extraction
def slice_doc(doc):
    """(preface..start of body, footnote block) as strings; skips the inline jQuery etc."""
    i = doc.find('<div class="akn-preface"')
    if i < 0:
        return None, None
    k = doc.find('<div class="akn-commentaires"', i)
    notes = ""
    if k >= 0:
        # the footnote block is the last thing in akomaNtoso
        e = doc.find("</akomaNtoso>", k)
        notes = doc[k:e if e > 0 else len(doc)]
    return doc[i:], notes


def extract(doc):
    head, notes_html = slice_doc(doc)
    res = {"has_preface": head is not None}
    if head is None:
        return res
    # cut the head at the first body container to keep parsing cheap; the preamble elements
    # come before it (a container never sits inside a preamble).
    m = re.search(r'<div class="akn-(?:(?:tome|part|book|title|chapter|section|subsection|article)'
                  r'-container|annexes|commentaires)\b', head)
    root = parse(head[:m.start()] if m else head)
    pre = next((n for n in root.iter() if "akn-preface" in n.cls()), None)

    def first(cls, scope):
        return next((n for n in scope.iter() if cls in n.cls()), None) if scope else None

    for key, cls in (("docType", "akn-docType"), ("docNumber", "akn-docNumber"),
                     ("docTitle", "akn-docTitle"), ("docAbreviation", "akn-docAbreviation")):
        n = first(cls, pre)
        res[key] = text_of(n, skip_markers=True) if n is not None else None
    dv = first("akn-docDate-value", pre)
    res["docDate"] = dv.attrs.get("date") if dv is not None else None
    res["docDateText"] = text_of(first("akn-docDate", pre)) if first("akn-docDate", pre) else None

    # the preamble elements are the siblings that follow the preface
    sib = pre.parent.elems() if pre is not None else []
    parts = {"autorite": None, "preamble": None, "formula": None}
    seen = False
    for n in sib:
        if n is pre:
            seen = True
            continue
        if not seen:
            continue
        c = n.cls()
        if "akn-separator" in c:
            continue
        key = ("autorite" if "akn-autorite" in c else "preamble" if "akn-preamble" in c
               else "formula" if "akn-formula" in c else None)
        if key is None:
            break
        if parts[key] is None:
            parts[key] = n
    res["parts"] = {k: (text_of(v) if v is not None else None) for k, v in parts.items()}
    res["preamble_paras"] = ([norm(text_of(p)) for p in parts["preamble"].elems()]
                             if parts["preamble"] is not None else [])

    # footnote markers and links inside the ingress
    markers, links = [], []
    for key in ("autorite", "preamble", "formula"):
        n = parts[key]
        if n is None:
            continue
        for a in n.iter():
            if a.tag != "a":
                continue
            if "akn-commentaire" in a.cls():
                markers.append((text_of(a), a.attrs.get("identify", "")))
            else:
                links.append({"text": text_of(a), "href": href_of(a)})
    res["markers"] = markers
    res["links"] = links

    # footnote texts (only those referenced from the ingress)
    notes = {}
    want = {ident for _, ident in markers if ident}
    if want and notes_html:
        nroot = parse(notes_html)
        for n in nroot.iter():
            ident = n.attrs.get("id")
            if ident in want and ident not in notes:
                notes[ident] = (text_of(n),
                                [{"text": text_of(a), "href": href_of(a)}
                                 for a in n.iter() if a.tag == "a"])
    res["notes"] = notes
    return res


MONTHS = {m: i + 1 for i, m in enumerate(
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split())}


def iso_from_dmy(s):
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


BASIS = re.compile(r"(vu|vus)\b", re.I)


def sr_key(cote):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"[.\s]", cote)]


def build_record(act, versions, ext, html_id):
    cote, aid = act["cote"], act["id"]
    rec = {
        "ct": "VD",
        "sr": cote,
        "title": None,
        "abbr": None,
        "url": PAGE_URL.format(cote=quote(cote, safe="."), id=aid),
        "in_force": act["statut"] == "EN_VIGUEUR",
        "adopted": None,
        "issuer": None,
        "ingress": "",
        "notes": {},
        "links": [],
        "lang": "fr",
        "src": "portal",
        "importance": act.get("importance"),
    }
    ext = ext or {}
    # title: the header of today's text (docType + docTitle, footnote markers dropped); the
    # list's "titre" (same text, typographic apostrophes, a few stale) only as a fallback
    if ext.get("docType") and ext.get("docTitle"):
        rec["title"] = norm(ext["docType"] + " " + ext["docTitle"])
    else:
        rec["title"] = norm(html.unescape(act["titre"]))
    # abbreviation: the act header's own "(LPA-VD)" line, else the BLV's abreviation field
    ab = ext.get("docAbreviation")
    if ab:
        ab = ab[1:-1].strip() if ab.startswith("(") and ab.endswith(")") else ab
    rec["abbr"] = ab or (norm(html.unescape(act["abreviation"])) if act.get("abreviation") else None)
    rec["adopted"] = ext.get("docDate") or iso_from_dmy(act.get("dateAdoption"))

    parts = ext.get("parts") or {}
    autorite = parts.get("autorite") or ""
    pre = parts.get("preamble") or ""
    formula = parts.get("formula") or ""
    issuer = autorite or None
    if not issuer:
        # no akn-autorite (some conventions): the parties stand at the head of the preamble,
        # before the first "vu" clause. Without such a clause no issuer is claimed.
        paras = [p for p in ext.get("preamble_paras", []) if p]
        k = next((i for i, p in enumerate(paras) if BASIS.match(p)), None)
        if k:
            issuer = norm(" ".join(paras[:k]))
    rec["issuer"] = issuer
    rec["ingress"] = norm(" ".join(x for x in (autorite, pre, formula) if x))

    # footnotes: marker letters as the source prints them ("[A]" -> "A")
    letters = {}
    for mk, ident in ext.get("markers", []):
        lab = mk.strip().strip("[]").strip()
        if ident in ext.get("notes", {}) and lab not in letters:
            letters[lab] = ident
    links = list(ext.get("links", []))
    for lab, ident in letters.items():
        txt, nlinks = ext["notes"][ident]
        rec["notes"][lab] = txt
        for l in nlinks:
            links.append({"text": l["text"], "href": l["href"], "note": lab})
    rec["links"] = links
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use only the raw cache")
    ap.add_argument("--refresh-list", action="store_true", help="refetch the list of acts")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    t0 = time.time()
    RAW.mkdir(parents=True, exist_ok=True)

    lp = RAW / "list.json"
    if a.refresh_list and lp.exists() and not a.offline:
        lp.unlink()
    acts = json.loads(cached(lp, LIST_URL, a.offline))
    acts = [x for x in acts if x.get("statut") == "EN_VIGUEUR" and x.get("categorie") == "CONSOLIDE"]
    print(f"{len(acts)} acts in force (consolidated)", file=sys.stderr)

    problems = []
    done = [0]
    lock = threading.Lock()

    def work(act):
        aid, cote = act["id"], act["cote"]
        try:
            vs = json.loads(cached(RAW / "versions" / f"{aid}.json",
                                   VERSIONS_URL.format(id=quote(aid), cote=quote(cote, safe=".")),
                                   a.offline))
        except Exception as e:
            return act, None, None, None, f"versions: {e}"
        cur = next((v for v in vs if v.get("versionType") == "ACTUELLE"), None) or (vs[-1] if vs else None)
        if cur is None:
            return act, vs, None, None, "no version"
        hid = cur["htmlId"]
        try:
            doc = cached(RAW / "html" / f"{hid}.html.gz", HTML_URL.format(html_id=quote(str(hid))),
                         a.offline, gz=True).decode("utf-8")
        except Exception as e:
            return act, vs, None, hid, f"html: {e}"
        try:
            ext = extract(doc)
        except Exception as e:  # never silently: reported below
            return act, vs, None, hid, f"parse: {e!r}"
        with lock:
            done[0] += 1
            if done[0] % 200 == 0:
                print(f"  {done[0]}/{len(acts)}  {time.time() - t0:.0f}s", file=sys.stderr)
        return act, vs, ext, hid, None

    out = []
    with cf.ThreadPoolExecutor(max_workers=max(1, min(3, a.workers))) as ex:
        for act, vs, ext, hid, err in ex.map(work, acts):
            if err:
                problems.append({"sr": act["cote"], "id": act["id"], "error": err})
            out.append(build_record(act, vs, ext, hid))

    out.sort(key=lambda r: (sr_key(r["sr"]), r["adopted"] or "", r["url"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT)

    n = len(out)
    st = {
        "acts": n,
        "majeur": sum(r["importance"] == "MAJEUR" for r in out),
        "mineur": sum(r["importance"] == "MINEUR" for r in out),
        "ingress": sum(bool(r["ingress"]) for r in out),
        "issuer": sum(bool(r["issuer"]) for r in out),
        "adopted": sum(bool(r["adopted"]) for r in out),
        "abbr": sum(bool(r["abbr"]) for r in out),
        "with_notes": sum(bool(r["notes"]) for r in out),
        "with_links": sum(bool(r["links"]) for r in out),
        "problems": len(problems),
        "seconds": round(time.time() - t0, 1),
    }
    print(json.dumps(st, ensure_ascii=False), file=sys.stderr)
    for p in problems[:30]:
        print("  problem:", p, file=sys.stderr)
    (RAW / "problems.json").write_text(json.dumps(problems, ensure_ascii=False, indent=1),
                                       encoding="utf-8")


if __name__ == "__main__":
    main()
