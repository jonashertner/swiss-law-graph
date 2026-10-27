"""Download the XML of every federal version the law repository holds (decision 36): every version applying on or
after START (2021-01-01) and every version Fedlex already publishes for a later date, in every language it has.

Input: build/lawgit/fedlex_versions.json (fedlex_versions.py). Output: build/lawgit/xml/<eli path>/<date>.<lang>.xml.gz
(resumable: files already there are kept). ~38,000 files, ~35 min with 6 workers.
"""
import gzip
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/lawgit"
XML = OUT / "xml"
START = "2021-01-01"
UA = {"User-Agent": "swiss-law (law repository; +https://jonashertner.com)"}


def eli_path(act: str) -> str:
    return act.split("/eli/", 1)[1].replace("/", "_")


def wanted() -> list[tuple[Path, str]]:
    V = json.load(open(OUT / "fedlex_versions.json"))
    jobs = []
    for act, vs in V.items():
        for v in vs:
            if (v["e"] or "9999") < START:
                continue
            for lang, url in v["u"].items():
                jobs.append((XML / eli_path(act) / f"{v['d']}.{lang}.xml.gz", url))
    return jobs


def get(job):
    path, url = job
    if path.exists():
        return 0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                data = r.read()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with gzip.open(tmp, "wb", compresslevel=6) as f:
                f.write(data)
            tmp.rename(path)
            return len(data)
        except Exception as e:                       # noqa: BLE001 — retried, then reported
            if attempt == 4:
                print(f"failed {url}: {e}", file=sys.stderr)
                return -1
            time.sleep(3 * (attempt + 1))


def main() -> None:
    jobs = wanted()
    todo = [j for j in jobs if not j[0].exists()]
    print(f"{len(jobs)} files wanted, {len(todo)} to fetch", file=sys.stderr)
    t0, done, size, failed = time.time(), 0, 0, 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for n in ex.map(get, todo):
            done += 1
            size += max(n, 0)
            failed += n < 0
            if done % 1000 == 0:
                print(f"{done}/{len(todo)} {size / 1e9:.2f} GB raw, {failed} failed, {time.time() - t0:.0f} s", file=sys.stderr)
    print(f"done: {done} fetched, {failed} failed, {size / 1e9:.2f} GB raw", file=sys.stderr)


if __name__ == "__main__":
    main()
