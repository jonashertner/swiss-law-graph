"""Zürich (zh.ch, Loseblattsammlung LS) for the law repository (decision 36): every version of every act in force that
applied on or after START, as the canton's PDF (zh.ch publishes no other text).

The detail page of an act lists its versions ("Historie": "121 (in Kraft bis 01.07.2024)", the current one "(aktuell)"),
each a page of its own with its PDF. A version is kept when it ended on or after START, or is current. Its first day is
read later from its own text (the latest "in Kraft seit" of its change notes, see convert.py), its last day is the
"in Kraft bis" of the list. Reuses pipeline/cantonal/zh.py (requests, delay, 3 workers per host; caches in
build/cantonal/raw/ZH/{detail,pdf}). Output: build/lawgit/zh/acts.json.
Usage: python3 pipeline/lawgit/zh_fetch.py
"""
import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cantonal"))
import zh  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/lawgit/zh"
START = "2021-01-01"
ITEM = re.compile(r'<a href="([^"]+\.html)">\s*<input[^>]*placeholder="(\d+)\s*\(([^)]*)\)"')


def iso(s: str) -> str:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def page_of(link: str) -> str:
    return zh.cached(zh.RAW / "detail" / f"{zh.key_of(link)}.html", lambda: zh.get("https://www.zh.ch" + link).content).decode("utf-8")


def versions(m: dict) -> list[dict]:
    link = m["page"].replace("https://www.zh.ch", "")
    page = page_of(link)
    out = []
    for href, nr, st in ITEM.findall(page):
        cur = "aktuell" in st
        end = "" if cur else iso(st)
        if cur or end >= START:
            out.append({"key": zh.key_of(href), "link": href, "nachtrag": int(nr), "end": end, "current": cur})
    if not out:                                          # a page without a list: the version shown is the current one
        out.append({"key": zh.key_of(link), "link": link, "nachtrag": 0, "end": "", "current": True})
    return out


def pdf_of(v: dict) -> str:
    page = page_of(v["link"])
    p = re.search(r'href="(https://www\.notes\.zh\.ch/[^"]+\.pdf)"', page)
    if not p:
        raise RuntimeError("no PDF link")
    zh.fetch_pdf(v["key"], html.unescape(p.group(1)))
    return str(zh.RAW / "pdf" / f"{v['key']}.pdf")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    meta = json.load(open(zh.RAW / "meta.json"))
    with ThreadPoolExecutor(3) as ex:
        lists = list(ex.map(versions, meta))
    jobs = [(m, v) for m, vs in zip(meta, lists) for v in vs]
    print(f"{len(meta)} acts, {len(jobs)} versions on or after {START}", file=sys.stderr)

    def work(j):
        m, v = j
        try:
            v["pdf"] = pdf_of(v)
        except Exception as e:                            # noqa: BLE001 — recorded
            v["error"] = str(e)[:200]
        return j
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(work, jobs))
    out = [{"sr": m["sr"], "page": m["page"], "versions": sorted(vs, key=lambda v: v["nachtrag"])} for m, vs in zip(meta, lists)]
    json.dump(out, open(OUT / "acts.json", "w"), ensure_ascii=False)
    print(f"{sum(1 for _, v in jobs if v.get('pdf'))} PDFs, {sum(1 for _, v in jobs if v.get('error'))} errors", file=sys.stderr)


if __name__ == "__main__":
    main()
