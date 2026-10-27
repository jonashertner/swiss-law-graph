"""Vaud (BLV) for the law repository (decision 36): every consolidated act in force, repealed or lapsed, its versions,
and the XHTML of every version that applied on or after START or applies later.

Reuses the caches of pipeline/cantonal/vd.py (build/cantonal/raw/VD/{list.json,versions,html}); new files go to
build/lawgit/vd/. Output: build/lawgit/vd/acts.json [{act, versions: [...]}]. ~1,500 version lists and the missing
HTML, 3 workers with a pause, as vd.py.
"""
import gzip
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cantonal"))
import vd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/lawgit/vd"
RAW = vd.RAW
START = "2021-01-01"
LIST = (vd.BASE + "api/actes/rechercher?sortBy=COTE&textes=ABREVIATION,COTE,TITRE&statuts={st}"
        "&importances=MAJEUR,MINEUR&categories=CONSOLIDE")


def iso(d):
    if not d:
        return ""
    p = d.split(".")
    return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 else d


def cached(path: Path, url: str, gz=False) -> bytes:
    for p in (path, RAW / path.relative_to(OUT)):
        if p.exists():
            b = p.read_bytes()
            return gzip.decompress(b) if gz else b
    b = vd.fetch(url, False)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(gzip.compress(b, 9) if gz else b)
    tmp.replace(path)
    return b


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    acts = []
    for st in ("EN_VIGUEUR", "ABROGE", "CADUC"):
        f = OUT / f"list_{st}.json"
        if not f.exists():
            f.write_bytes(vd.fetch(LIST.format(st=st), False))
        acts += [a for a in json.load(open(f)) if a.get("categorie") == "CONSOLIDE"]
    print(f"{len(acts)} consolidated acts", file=sys.stderr)

    def work(a):
        vs = json.loads(cached(OUT / "versions" / f"{a['id']}.json",
                               vd.VERSIONS_URL.format(id=quote(a["id"]), cote=quote(a["cote"], safe="."))))
        ab = max((iso(v.get("dateAbrogation") or v.get("dateCaducite")) for v in vs), default="")
        keep = []
        for v in vs:
            start, nxt = iso(v.get("versionDateMiseEnVigueur") or v.get("dateMiseEnVigueur")), iso(v.get("nextDateMiseEnVigueur"))
            end = nxt or ab
            if end and end <= START:
                continue
            if not v.get("htmlId"):
                continue
            try:
                cached(OUT / "html" / f"{v['htmlId']}.html.gz", vd.HTML_URL.format(html_id=quote(str(v["htmlId"]))), gz=True)
                keep.append({**v, "_start": start, "_end": end})
            except Exception as e:                        # noqa: BLE001 — recorded
                keep.append({**v, "_start": start, "_end": end, "_error": str(e)[:200]})
        return {"act": a, "abrogated": ab, "versions": keep}

    t0 = time.time()
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(work, acts))
    res = [r for r in res if r["versions"]]
    json.dump(res, open(OUT / "acts.json", "w"), ensure_ascii=False)
    print(f"{len(res)} acts with a version on or after {START}, {sum(len(r['versions']) for r in res)} versions, "
          f"{sum(1 for r in res for v in r['versions'] if v.get('_error'))} errors, {time.time() - t0:.0f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
