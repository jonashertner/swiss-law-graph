"""The OpenCaseLaw snapshot (CC0) the atlas reads, from the public dataset voilaj/swiss-caselaw on Hugging Face
(decision 39: the weekly refresh reads it again):

  graph/citations.parquet            → data/citations.parquet          decision → decision
  graph/statute_references.parquet   → data/statute_references.parquet decision × code × article × paragraph
  structure/structure.parquet        → data/structure.parquet          court, language, structure flags
  artifacts/cite_index/index.json    → data/index.json                 names the cite index of the night, with its SHA-256
  artifacts/cite_index/<that file>   → data/cite-index-<day>-<hash>.tsv.gz (the one before is removed: 01_resolve.py
                                       reads the only one there)

The snapshot is taken whole or not at all, so the files always belong together. It is taken when the cite index
matches its SHA-256, every parquet file reads and holds at least 95 % of the rows of the copy, and no court lost
part of its decisions: a court with at least 200 decisions in the copy must keep 90 % of them in structure.parquet
and 90 % of its decisions with a statute reference (court from each snapshot's own cite index). The snapshot of
2026-10-26 failed the last test (Obwalden: structure 3,460 → 2,192 decisions, statute references of 1,081 decisions
gone; reports/opencaselaw-anomalies.md): a partial export must not shrink the atlas. Otherwise the copy stays and
the run says why (exit 1). ATLAS_ALLOW_DROPS=1 takes it all the same (after checking; never against a wrong
SHA-256). Never the private dataset jonashertner/opencaselaw-data (CLAUDE.md).
"""
import hashlib
import json
import os
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
MIN_ROWS, MIN_COURT, COURT_FLOOR = 0.95, 0.90, 200


def get(path: str, out: Path) -> None:
    tmp = out.with_suffix(out.suffix + ".part")
    with urllib.request.urlopen(urllib.request.Request(HF + path, headers=UA), timeout=600) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.replace(out)


def rows(p: Path) -> int:
    return duckdb.sql(f"select count(*) from read_parquet('{p}')").fetchall()[0][0] if p.exists() else 0


def per_court(structure: Path, refs: Path, cite: Path) -> dict:
    """{court: (decisions in structure.parquet, decisions with a statute reference)}"""
    c = duckdb.connect()
    s = dict(c.sql(f"select court, count(distinct decision_id) from read_parquet('{structure}') group by 1").fetchall())
    r = dict(c.sql(f"""select ci.column1, count(distinct s.decision_id)
                       from read_parquet('{refs}') s
                       join read_csv('{cite}', delim='\t', header=false, quote='', compression='gzip') ci
                         on ci.column5 = s.decision_id group by 1""").fetchall())
    return {k: (s.get(k, 0), r.get(k, 0)) for k in s.keys() | r.keys()}


def main() -> None:
    bad, new = [], {}
    for src, name in PARQUET.items():
        p = DATA / (name + ".new")
        get(src, p)
        new[name] = p
        n, before = rows(p), rows(DATA / name)
        print(f"{name}: {n:,} rows (copy {before:,})", file=sys.stderr)
        if n < MIN_ROWS * before:
            bad.append(f"{src}: {n:,} rows against {before:,}")
    idx_new = DATA / "index.json.new"
    get("artifacts/cite_index/index.json", idx_new)
    idx = json.load(open(idx_new))
    cite_new = DATA / (idx["file"] + ".new")             # ".new": not yet matched by 01_resolve.py's glob
    get(f"artifacts/cite_index/{idx['file']}", cite_new)
    corrupt = hashlib.sha256(cite_new.read_bytes()).hexdigest() != idx["sha256"]
    if corrupt:
        bad.append(f"{idx['file']}: SHA-256 does not match index.json")
    old_cite = sorted(DATA.glob("cite-index-*.tsv.gz"))
    if not bad and old_cite and (DATA / "structure.parquet").exists():
        was = per_court(DATA / "structure.parquet", DATA / "statute_references.parquet", old_cite[0])
        now = per_court(new["structure.parquet"], new["statute_references.parquet"], cite_new)
        for court in sorted(was):
            for i, what in enumerate(("decisions", "decisions with statute references")):
                a, b = was[court][i], now.get(court, (0, 0))[i]
                if a >= COURT_FLOOR and b < MIN_COURT * a:
                    bad.append(f"{court}: {what} {a:,} → {b:,}")
    if bad and (corrupt or not os.environ.get("ATLAS_ALLOW_DROPS")):
        for p in [*new.values(), idx_new, cite_new]:
            p.unlink(missing_ok=True)
        sys.exit("kept the whole copy of the snapshot: " + "; ".join(bad))
    if bad:
        print("::warning::taken although (ATLAS_ALLOW_DROPS): " + "; ".join(bad), file=sys.stderr)
    for name, p in new.items():
        p.replace(DATA / name)
    for old in old_cite:
        old.unlink()
    cite_new.replace(DATA / idx["file"])
    idx_new.replace(DATA / "index.json")
    print(f"{idx['file']}: {idx.get('decisions', 0):,} decisions, generated {idx.get('generated')}", file=sys.stderr)


if __name__ == "__main__":
    main()
