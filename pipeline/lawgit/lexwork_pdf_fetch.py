"""The PDFs of the LexWork versions that have no structured text (decision 36), for pdf2md.py.

A version applies in the repository when it was in force on or after START (as build_repo.cantonal_events reads it); if
convert.py made no Markdown of it (empty json_content), its PDF is fetched in every language the version names:
https://<host>/api/<lang>/versions/<id>/pdf_file → build/lawgit/kt_pdf/<CT>/<nr>/<id>.<lang>.pdf (resumable).
Usage: python3 pipeline/lawgit/lexwork_pdf_fetch.py [CT ...]
"""
import gzip
import json
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_repo as br  # noqa: E402
from lexwork_fetch import UA  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "build/lawgit"
OUT = B / "kt_pdf"
PER_HOST = 2
_local = threading.local()


def jobs(only):
    out = []
    for cdir in sorted((B / "kt").iterdir()):
        if not cdir.is_dir() or (only and cdir.name not in only):
            continue
        for adir in sorted(cdir.iterdir()):
            if not (adir / "_act.json.gz").exists():
                continue
            t = json.load(gzip.open(adir / "_act.json.gz", "rt", encoding="utf-8"))
            end = br.repeal_of(t.get("abrogated_dates_str") or "")
            if end and end <= br.START:
                continue
            md = B / "md" / cdir.name.lower() / adir.name
            for v in [t.get("current_version") or {}] + (t.get("old_versions") or []) + (t.get("future_versions") or []):
                if not v.get("id"):
                    continue
                sp = br.parse_span(v.get("version_dates_str"))
                if not sp.get("from") or (sp.get("to") or "9999") < br.START:
                    continue
                if md.exists() and list(md.glob(f"{v['id']}.*.md.gz")):
                    continue
                src = adir / f"{v['id']}.json.gz"
                if not src.exists():
                    continue
                vj = json.load(gzip.open(src, "rt", encoding="utf-8"))
                url = vj.get("pdf_link_tol") or ""
                if not url:
                    continue
                langs = [x["language"]["iso639_1_code"] for x in (vj.get("available_languages") or [])] or [url.split("/api/")[1][:2]]
                for lg in langs:
                    u = url.replace(f"/api/{url.split('/api/')[1][:2]}/", f"/api/{lg}/", 1)
                    out.append((cdir.name, u, OUT / cdir.name / adir.name / f"{v['id']}.{lg}.pdf"))
    return out


def get(url: str) -> bytes | None:
    s = getattr(_local, "s", None)
    if s is None:
        s = _local.s = requests.Session()
        s.headers.update({"User-Agent": UA})
        s.mount("https://", requests.adapters.HTTPAdapter(max_retries=requests.adapters.Retry(
            total=5, backoff_factor=3, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET"}))))
    r = s.get(url, timeout=180)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


def main() -> None:
    only = set(sys.argv[1:])
    todo = [j for j in jobs(only) if not j[2].exists()]
    print(f"{len(todo)} PDFs to fetch", file=sys.stderr)
    by_ct = defaultdict(list)
    for j in todo:
        by_ct[j[0]].append(j)
    done, failed, t0 = [0], [], time.time()
    lock = threading.Lock()

    def work(j):
        ct, url, path = j
        try:
            b = get(url)
            if b is None or not b.startswith(b"%PDF"):
                raise ValueError("not a PDF" if b else "404")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(b)
            tmp.rename(path)
        except Exception as e:                            # noqa: BLE001 — listed at the end
            with lock:
                failed.append((url, str(e)[:120]))
        with lock:
            done[0] += 1
            if done[0] % 250 == 0:
                print(f"  {done[0]}/{len(todo)} {time.time() - t0:.0f} s", file=sys.stderr)

    pools = {ct: ThreadPoolExecutor(PER_HOST) for ct in by_ct}    # one pool per host: at most PER_HOST at a time
    futs = [pools[ct].submit(work, j) for ct, js in by_ct.items() for j in js]
    for f in futs:
        f.result()
    for p in pools.values():
        p.shutdown()
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(failed, open(OUT / "_failed.json", "w"), ensure_ascii=False, indent=0)
    print(f"done: {done[0] - len(failed)} fetched, {len(failed)} failed, {time.time() - t0:.0f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
