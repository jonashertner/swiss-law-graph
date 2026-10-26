# swiss-law-graph

Interactive map of Swiss law: SR areas, acts and articles, sized by the court decisions that
refer to them, with the decisions themselves one click away. Built from the OpenCaseLaw CC0
dataset (huggingface.co/datasets/voilaj/swiss-caselaw) and Fedlex.

- `data/` — raw source files (OpenCaseLaw CC0 snapshot 2026-10-26; Fedlex exports of the same day).
- `pipeline/` — steps 01–06, from statute references to the site data. See `CLAUDE.md` for the
  run order and every data decision.
- `layout/` — circle packing (d3-hierarchy).
- `site/` — the page (`index.html`, `app.js`); `site/data/` is generated and not committed.
- `reports/opencaselaw-anomalies.md` — issues found in the source data.
