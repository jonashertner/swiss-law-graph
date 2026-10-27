"""The OpenCaseLaw snapshot (CC0) the atlas reads, from the public dataset voilaj/swiss-caselaw on Hugging Face
(decision 39: the weekly refresh reads it again):

  graph/citations.parquet            → data/citations.parquet          decision → decision
  graph/statute_references.parquet   → data/statute_references.parquet decision × code × article × paragraph
  structure/structure.parquet        → data/structure.parquet          court, language, structure flags
  artifacts/cite_index/index.json    → data/index.json                 names the cite index of the night, with its SHA-256
  artifacts/cite_index/<that file>   → data/cite-index-<day>-<hash>.tsv.gz (the one before is removed: 01_resolve.py
                                       reads the only one there)

A file replaces the copy only when it is whole: the cite index by its SHA-256, a parquet file when it reads and holds
at least 95 % of the rows the copy holds (a truncated or emptied export must not shrink the atlas). Never the
private dataset jonashertner/opencaselaw-data (CLAUDE.md).
"""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
HF = "https://huggingface.co/datasets/voilaj/swiss-caselaw/resolve/main/"
UA = {"User-Agent": "swiss-law-graph (atlas; +https://jonashertner.com)"}
PARQUET = {"graph/citations.parquet": "citations.parquet", "graph/statute_references.parquet": "statute_references.parquet",
           "structure/structure.parquet": "structure.parquet"}


def get(path: str, out: Path) -> None:
    tmp = out.with_suffix(out.suffix + ".part")
    with urllib.request.urlopen(urllib.request.Request(HF + path, headers=UA), timeout=600) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(out)


def rows(p: Path) -> int:
    return duckdb.sql(f"select count(*) from read_parquet('{p}')").fetchall()[0][0] if p.exists() else 0


def main() -> None:
    bad = []
    for src, name in PARQUET.items():
        new = DATA / (name + ".new")
        get(src, new)
        n, before = rows(new), rows(DATA / name)
        if n < 0.95 * before:
            bad.append(f"{src}: {n:,} rows against {before:,}")
            new.unlink()
            continue
        new.replace(DATA / name)
        print(f"{name}: {n:,} rows (before {before:,})", file=sys.stderr)
    idx_new = DATA / "index.json.new"
    get("artifacts/cite_index/index.json", idx_new)
    idx = json.load(open(idx_new))
    target = DATA / idx["file"]
    if not target.exists():
        get(f"artifacts/cite_index/{idx['file']}", target)
    if hashlib.sha256(target.read_bytes()).hexdigest() != idx["sha256"]:
        bad.append(f"{idx['file']}: SHA-256 does not match index.json")
        target.unlink()
        idx_new.unlink()
    else:
        for old in DATA.glob("cite-index-*.tsv.gz"):
            if old != target:
                old.unlink()
        idx_new.replace(DATA / "index.json")
        print(f"{idx['file']}: {idx.get('decisions', 0):,} decisions, generated {idx.get('generated')}", file=sys.stderr)
    if bad:
        sys.exit("kept the copies of: " + "; ".join(bad))


if __name__ == "__main__":
    main()
