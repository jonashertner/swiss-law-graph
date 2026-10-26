# swiss-law-graph

Interactive 3D map of Swiss law in two views. Stufenbau: the Federal Constitution at the apex and
every federal act in force under the provision its Ingress names as its basis, on the floor of the
authority that enacted it, with the cantonal constitutions (Art. 51 BV) and cantonal law below.
Systematik: the Classified Compilation (SR) as a floor plan, acts as spheres sized by the court
decisions that refer to them, articles as a skyline inside each act. In both, two layers of links
between acts: what courts cite together and what the statute text itself refers to. Built from the OpenCaseLaw CC0 dataset
(huggingface.co/datasets/voilaj/swiss-caselaw) and Fedlex.

- `data/` — raw source files (OpenCaseLaw CC0 snapshot 2026-10-26; Fedlex exports of the same day).
- `pipeline/` — steps 01–06, from statute references to the site data. See `CLAUDE.md` for the
  run order and every data decision.
- `layout/` — circle packing (d3-hierarchy).
- `site/` — the page (`index.html` + ES modules `main.js`, `gl.js`, `i18n.js`, `method.js`; three.js
  from jsDelivr); `flat.html` + `app.js` is the earlier 2D version. `site/data/` is generated and
  not committed. Serve `site/` over HTTP (`python3 -m http.server`) — modules do not load from file://.
- `reports/opencaselaw-anomalies.md` — issues found in the source data.
