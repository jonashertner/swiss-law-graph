"""Fetch the article list of each former act (regime) from its last Fedlex text.

Needs `pdfplumber` (pip) and `pandoc`. A regime is an earlier act that shared
its successor's SR number (decision 2 in CLAUDE.md). Its articles are validated
against the text in force on the day before the cut-over, not against today's
act. Fedlex publishes most of these only as PDF/A: there an article heading is
a bold "Art." followed by a bold number on the same line; footnote markers are
set in a smaller size and dropped (otherwise "Art. 1" + footnote 24 reads "124").

Input: build/act_nodes.json (written by step 1): every earlier act that receives
references, with `valid_until`, the last day its text applied.
Output: data/fedlex_regime_articles.json
    {act_id: {"act": eli, "as_of": ..., "date": ..., "format": ..., "url": ..., "articles": [...]}}
Articles are the union of the earliest and the latest text published for the
act (an article repealed during the act's life is absent from its last text).
A regime without any published text gets {"articles": null} and its article
references stay unvalidated (counted, never shown as article nodes).
"""
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import artnum

ROOT = Path(__file__).resolve().parents[1]
SPARQL = "https://fedlex.data.admin.ch/sparqlendpoint"
FORMAT_RANK = ["xml", "html", "pdf-a"]

Q = """PREFIX jolux: <http://data.legilux.public.lu/resource/ontology/jolux#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?date ?fmt ?url WHERE {
 ?cons jolux:isMemberOf <%s> ; jolux:dateApplicability ?date ; jolux:isRealizedBy ?expr .
 ?expr jolux:language <http://publications.europa.eu/resource/authority/language/DEU> ; jolux:isEmbodiedBy ?m .
 ?m jolux:userFormat ?f ; jolux:isExemplifiedBy ?url .
 BIND(replace(str(?f), "^.*/", "") AS ?fmt)
 FILTER(?date <= "%s"^^xsd:date) }"""

SUFFIX = r"(?:[a-z]|bis|ter|quater|quinquies|sexies|septies|octies|novies|decies)?"
XML_ART = re.compile(r"<article\b[^>]*>\s*<num\b[^>]*>(.*?)</num>", re.S)
TAG = re.compile(r"<[^>]+>")
NUM = re.compile(r"^(\d+)(" + SUFFIX + r")$")


def sparql(query: str) -> list[dict]:
    data = urllib.parse.urlencode({"query": query}).encode()
    req = urllib.request.Request(SPARQL, data=data, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": "swiss-law-graph/0.1 (research; jonashertner)"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)["results"]["bindings"]


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "swiss-law-graph/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def pdf_headings(blob: bytes) -> list[tuple[str, str]]:
    import pdfplumber
    out = []
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        for page in pdf.pages:
            ws = page.extract_words(extra_attrs=["size", "fontname"])
            for i, w in enumerate(ws):
                if w["text"] != "Art." or "Bold" not in w["fontname"]:
                    continue
                num = ws[i + 1] if i + 1 < len(ws) else None
                if not (num and abs(num["top"] - w["top"]) < 2 and "Bold" in num["fontname"]
                        and num["size"] >= 0.9 * w["size"] and num["text"].isdigit()):
                    continue
                txt = num["text"]
                # The suffix ("a" in italics, "bis" in a smaller size) touches the number.
                # Footnote markers also touch it but are digits, so they never match.
                nxt = ws[i + 2] if i + 2 < len(ws) else None
                if (nxt and abs(nxt["top"] - w["top"]) < 3 and nxt["x0"] - num["x1"] < 1.0
                        and re.fullmatch(SUFFIX, nxt["text"]) and nxt["text"]):
                    txt += nxt["text"]
                m = NUM.match(txt)
                if not m:
                    continue
                out.append((m.group(1), m.group(2)))
                # "Art. 268–278" / "Art. 3 und 4": a block of repealed articles under one heading.
                rest = [x for x in ws[i + 2:i + 6] if abs(x["top"] - w["top"]) < 3 and "Bold" in x["fontname"]]
                if rest and rest[0]["text"] in ("–", "-", "und", "bis") and len(rest) > 1:
                    b = rest[1]["text"]
                    nxt2 = rest[2]["text"] if len(rest) > 2 and re.fullmatch(SUFFIX, rest[2]["text"]) else ""
                    if NUM.match(b + nxt2):
                        blk = (artnum.expand_range(txt.lower(), (b + nxt2).lower()) if rest[0]["text"] != "und"
                               else [txt.lower(), (b + nxt2).lower()])
                        out.extend((x, "") for x in blk[1:])
    return out


def to_text(blob: bytes, fmt: str) -> str:
    if fmt in ("xml", "html"):
        return blob.decode("utf-8", "replace")
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / ("in." + fmt)
        src.write_bytes(blob)
        cmd = ["pandoc", str(src), "-t", "plain", "--wrap=none"]
        return subprocess.run(cmd, capture_output=True, check=True).stdout.decode("utf-8", "replace")


def articles(text: str, fmt: str) -> list[str]:
    out, seen = [], set()

    def add(n: str, s: str) -> None:
        a = (n + s).lower()
        if a not in seen:
            seen.add(a)
            out.append(a)

    if fmt == "xml":
        for m in XML_ART.finditer(text):
            num = re.sub(r"<authorialNote.*?</authorialNote>", "", m.group(1), flags=re.S)
            for a in artnum.parse_num(TAG.sub("", num)):
                add(a, "")
        return out
    if fmt == "html":
        text = TAG.sub("\n", text)
    for line in text.replace("\xa0", " ").splitlines():
        m = re.match(r"^\s*\**Art\.\s*(\d+)\s*(" + SUFFIX + r")(?![a-z0-9])\**\s*$", line)
        if m:
            add(m.group(1), m.group(2))
    return out


def work(item: tuple[str, str, str]) -> tuple[str, dict]:
    act_id, act, as_of = item
    rec = {"act": act, "as_of": as_of, "articles": None}
    try:
        rows = sparql(Q % (act, as_of))
        if not rows:
            return act_id, {**rec, "note": "no German text published"}
        # Articles repealed during the act's life are missing from its last text
        # (BStP Art. 268-278, repealed 2007): take the union of the earliest and
        # the latest published text.
        dates = sorted({r["date"]["value"] for r in rows})
        arts, used = [], []
        for day in dict.fromkeys([dates[-1], dates[0]]):
            cands = {r["fmt"]["value"]: r["url"]["value"] for r in rows if r["date"]["value"] == day}
            fmt = next((f for f in FORMAT_RANK if f in cands), None)
            if fmt is None:
                continue
            blob = download(cands[fmt])
            if fmt.startswith("pdf"):
                got = [(n + x).lower() for n, x in pdf_headings(blob)]
            else:
                got = articles(to_text(blob, fmt), fmt)
            arts.extend(got)
            used.append({"date": day, "format": fmt, "url": cands[fmt], "articles": len(set(got))})
        if not used:
            return act_id, {**rec, "date": dates[-1], "note": "no xml/html/pdf text"}
        return act_id, {**rec, "date": used[0]["date"], "format": used[0]["format"], "url": used[0]["url"],
                        "texts": used, "articles": list(dict.fromkeys(arts))}
    except Exception as e:  # recorded, never silently dropped
        return act_id, {**rec, "error": str(e)[:200]}


def main() -> None:
    nodes = json.load(open(ROOT / "build/act_nodes.json"))
    todo = sorted((k, v["eli"], v["valid_until"]) for k, v in nodes.items()
                  if v.get("regime") and v.get("valid_until") and v.get("eli"))
    result = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        for k, (act_id, rec) in enumerate(ex.map(work, todo)):
            result[act_id] = rec
            print(f"{k + 1}/{len(todo)} {act_id}: {rec.get('format')} "
                  f"{len(rec['articles']) if rec.get('articles') else rec.get('note') or rec.get('error')}",
                  file=sys.stderr)
    out = ROOT / "data/fedlex_regime_articles.json"
    json.dump({"source": "Fedlex SPARQL + filestore, German text in force on `as_of`",
               "regimes": result}, open(out, "w"), ensure_ascii=False, indent=1)
    ok = sum(1 for r in result.values() if r.get("articles"))
    print(f"done: {ok}/{len(todo)} earlier acts with article lists -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
