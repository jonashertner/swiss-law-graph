# swiss-law-graph

**Atlas of Swiss Law** (`docs/`, published with GitHub Pages): every federal and cantonal act in force as
a tile of a zoomable map, sized by acts or by the court decisions that refer to them, coloured by who
enacted it; inside each cited federal act its divisions and articles. Two further views: the hierarchy
(every act hangs from the basis its preamble names, from the Federal Constitution down to cantonal
administration) and the dependencies between all parts of the law. German, French, Italian, English.
Static files only: `python3 -m http.server -d docs` and open http://localhost:8000. The data in
`docs/data/` is built by `pipeline/08_web.py` from the outputs of steps 05 and 07.

The earlier 3D map:

Interactive 3D map of Swiss law in two views. Stufenbau: the Federal Constitution at the apex and
every federal act in force under the provision its Ingress names as its basis, on the floor of the
authority that enacted it; below, the 26 cantonal constitutions (Art. 51 BV) and every act in
force of the 26 official cantonal collections, each under the cantonal provision its own Ingress names.
Systematik: the Classified Compilation (SR) as a floor plan, acts as spheres sized by the court
decisions that refer to them, articles as a skyline inside each act. In both, two layers of links
between acts: what courts cite together and what the statute text itself refers to. Built from the OpenCaseLaw CC0 dataset
(huggingface.co/datasets/voilaj/swiss-caselaw), Fedlex and the cantonal law collections (official portals;
LexFind for TI and SZ).

- `data/` — raw source files (OpenCaseLaw CC0 snapshot 2026-10-26; Fedlex exports of the same day).
- `pipeline/` — steps 01–08, from statute references to the site data. See `CLAUDE.md` for the
  run order and every data decision.
- `layout/` — circle packing (d3-hierarchy).
- `site/` — the page (`index.html` + ES modules `main.js`, `gl.js`, `i18n.js`, `method.js`; three.js
  from jsDelivr); `flat.html` + `app.js` is the earlier 2D version. `site/data/` is generated and
  not committed. Serve `site/` over HTTP (`python3 -m http.server`) — modules do not load from file://.
- `docs/` — the public site (`index.html`, `style.css`, `js/`, `fonts/` Geist under the SIL OFL, `data/`).
- `reports/opencaselaw-anomalies.md` — issues found in the source data.
