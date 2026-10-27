"""Full texts and versions of the 19 LexWork collections for the law repository (decision 36).

Per canton: the index with repealed acts (`lightweight_index?show_abrogated=true`); per act `show_as_json` (the
version in force or the last one, its old and future versions, the repeal); then every old version that still
applied on or after START (`texts_of_law/<nr>/versions/<id>/show_as_json`) and every future version. A response
carries every language the canton publishes. Acts repealed before START are kept as metadata only.

Output: build/lawgit/kt/<CT>/_index.json, build/lawgit/kt/<CT>/<nr>/<version id>.json.gz (resumable).
Usage: python3 pipeline/lawgit/lexwork_fetch.py [CT ...]
"""
import gzip
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cantonal"))
from lexwork import HOSTS, LANG  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/lawgit/kt"
START = "2021-01-01"
UA = "swiss-law (law repository; +https://jonashertner.com)"
PER_HOST = 2
_local = threading.local()


def get(url):
    s = getattr(_local, "s", None)
    if s is None:
        s = _local.s = requests.Session()
        s.headers.update({"User-Agent": UA, "Accept": "application/json"})
        s.mount("https://", requests.adapters.HTTPAdapter(max_retries=requests.adapters.Retry(
            total=5, backoff_factor=3, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET"}))))
    r = s.get(url, timeout=120)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def iso(d: str) -> str:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", d)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def span(s: str) -> tuple[str, str]:
    """('from', 'to') of "Version in Kraft von: 01.05.2024 bis: 29.06.2024", "… seit: 20.04.1803", "… ab: 01.01.2027"."""
    s = s or ""
    a = re.search(r"(?:von|seit|ab|dal|du|depuis|dès|da|from|since)\s*:?\s*(\d{2}\.\d{2}\.\d{4})", s, re.I)
    b = re.search(r"(?:bis|au|al|until|to)\s*:?\s*(\d{2}\.\d{2}\.\d{4})", s, re.I)
    return (iso(a.group(1)) if a else ""), (iso(b.group(1)) if b else "")


def slug(nr: str) -> str:
    return re.sub(r"[^\w.\-]", "_", nr)


def save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    tmp.rename(path)


def act(ct: str, host: str, lang: str, stub: dict) -> dict:
    nr = stub["systematic_number"]
    d = OUT / ct / slug(nr)
    head = d / "_act.json.gz"
    if head.exists():
        t = json.load(gzip.open(head, "rt", encoding="utf-8"))
    else:
        j = get(f"https://{host}/api/{lang}/texts_of_law/{quote(nr, safe='')}/show_as_json")
        if not j:
            return {"nr": nr, "missing": True}
        t = j["text_of_law"]
        sel = t.get("selected_version") or {}
        if sel.get("id"):
            save(d / f"{sel['id']}.json.gz", sel)
        t = {k: v for k, v in t.items() if k != "selected_version"}
        t["selected_id"] = sel.get("id")
        save(head, t)
    rep = re.search(r"per\s+(\d{2}\.\d{2}\.\d{4})", t.get("abrogated_dates_str") or "")
    repealed = iso(rep.group(1)) if rep else ""
    if repealed and repealed < START:
        return {"nr": nr, "repealed": repealed, "versions": 0}
    n = 0
    for v in (t.get("old_versions") or []) + (t.get("future_versions") or []):
        a, b = span(v.get("version_dates_str"))
        if b and b < START:
            continue
        f = d / f"{v['id']}.json.gz"
        if not f.exists():
            j = get(f"https://{host}/api/{lang}/texts_of_law/{quote(nr, safe='')}/versions/{v['id']}/show_as_json")
            if j:
                save(f, j["text_of_law"].get("selected_version") or {})
        n += 1
    return {"nr": nr, "repealed": repealed, "versions": n}


def canton(ct: str) -> str:
    host, lang = HOSTS[ct], LANG.get(ct, "de")
    ip = OUT / ct / "_index.json"
    if ip.exists():
        idx = json.load(open(ip))
    else:
        idx = get(f"https://{host}/api/{lang}/texts_of_law/lightweight_index?show_abrogated=true")
        ip.parent.mkdir(parents=True, exist_ok=True)
        json.dump(idx, open(ip, "w"), ensure_ascii=False)
    stubs = sorted({s["systematic_number"]: s for v in (idx.values() if isinstance(idx, dict) else [idx]) for s in v}.values(),
                   key=lambda s: s["systematic_number"])
    with ThreadPoolExecutor(PER_HOST) as ex:
        res = list(ex.map(lambda s: act(ct, host, lang, s), stubs))
    ab = sum(1 for s in stubs if s.get("abrogated"))
    old = sum(1 for r in res if r.get("repealed") and r["repealed"] < START)
    return (f"{ct}: {len(stubs)} acts ({ab} repealed, {old} before {START}), "
            f"{sum(r.get('versions', 0) for r in res)} further versions, {sum(1 for r in res if r.get('missing'))} missing")


def main() -> None:
    cts = sys.argv[1:] or sorted(HOSTS)
    with ThreadPoolExecutor(len(cts)) as ex:
        for line in ex.map(canton, cts):
            print(line, flush=True)


if __name__ == "__main__":
    main()
