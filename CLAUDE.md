# swiss-law-graph — working notes for Claude Code

## Goal
A zoomable, searchable, beautiful map of Swiss law for a general audience: SR areas →
acts → articles → decisions, with every node and edge traceable to its source. It must feel
like magic and be exact. Phase 2 (later): a tool to radically simplify the law and find
contradictions and lacunae. Owner: Jonas Hertner (also owner of opencaselaw.ch).

## Sources (public only — the page will be public)
- `data/citations.parquet` — OpenCaseLaw CC0, 9,474,505 decision→decision edges
  (`match_type`, `confidence_score`). HF `voilaj/swiss-caselaw`, snapshot 2026-10-26.
- `data/statute_references.parquet` — CC0, 12,707,001 rows decision × code × article × paragraph
  (`mention_count` is 1 on every row: carries no information).
- `data/structure.parquet` — CC0, per-decision court/language/structure flags.
- `data/cite-index-*.tsv.gz` — CC0: col0 label, col1 court, col2 canton, col3 date, col5 decision_id.
- `data/sr_taxonomy.csv` — Fedlex SPARQL legal taxonomy: SR tree + titles DE/FR/IT (+ some EN/RM).
- `data/sr_eli.csv` — Fedlex SR number → ELI + enforcement status (`…/0` = in force).
- `data/fedlex_acts.json` — every act that ever carried a cited SR number, with dateDocument,
  entry into force, repeal, titles and short titles per language (`fetch_fedlex_acts.py`).
- `data/fedlex_articles.json` — flat article list per cited act (`fetch_fedlex_articles.py`; fallback only).
- `data/fedlex_structure.json.gz` — structure of each cited act from the consolidated XML, DE/FR/IT:
  levels (book/part/title/…/marginal titles) and articles in order with eId, repealed flag, headings
  (`fetch_fedlex_structure.py`, ~35 min). 826/830 acts (4 have no XML).
- `data/fedlex_regime_articles.json` — article numbers of each earlier act from its earliest and last
  published text (mostly PDF/A, parsed by bold "Art." headings) (`fetch_fedlex_regimes.py`, needs
  `build/act_nodes.json` from step 1). 171/230 earlier acts have a text.
- `data/fedlex_xrefs.json` — legislative cross-references: for every act in force plus every cited
  act (5,145), the current consolidated DE XML read once; an SR-number footnote (not inside an
  article heading, not an AS amendment note) or an `eli/cc` link names another act
  (`fetch_fedlex_xrefs.py`, ~50 min). 28,075 references, 12,167 act pairs, 0 texts failed.
  Drafting rules put the footnote at the first mention only: 76 % of pairs have weight 1.
- `data/fedlex_basis.json` — the Ingress of every act in force plus every cited act (5,147, current
  consolidated DE XML): issuer, verbatim Ingress, stated bases (target SR from the footnote, article
  numbers, the clause verbatim), adoption date, editorial notes, body article eIds
  (`fetch_fedlex_basis.py`, ~6 min; SPARQL by ELI URI, cached in build/fedlex_xml_urls.json).
  Only a footnote that *is* an SR reference marks a basis ("SR …", "[BS …]"); editorial notes
  ("Der Titel wurde … PublG (SR 170.512) angepasst") let the clause run on.
- `data/cantonal_basis.json` — all 26 cantonal collections in force (16,384 acts; `cantonal_basis.py`):
  title, abbreviation, URL, adoption date, issuer, verbatim Ingress, floor, and every stated basis resolved
  to `SR <n>` / `SR <n>@<year>` / `KV` (+ articles) / `CT:<n>` / `?` with the clause verbatim. Read by the
  adapters in `pipeline/cantonal/` (contract: `SPEC.md`; raw caches in build/cantonal/raw, 705 MB):
  `lexwork.py` (19 cantons, one API; PDF fallback for unconverted acts), `zh.py` (zh.ch per LS folder +
  PDF), `ge.py`/`ne.py` (SIL), `vd.py` (BLV API; "majeur" acts only on the map), `ju.py` (RSJU), `ti.py`
  and `sz.py` via LexFind (www3.ti.ch unreachable from the sandbox; sz.ch answered 403 — not circumvented).
  Cantonal Ingress text is official (Art. 5 URG), shown verbatim with a link to the canton's page.
- Alias tables live in the opencaselaw repo: `docs/data/law_codes.json`,
  `docs/api/law_aliases.json` (public repo: clone `jonashertner/opencaselaw` next to this one).
- Do NOT use `jonashertner/opencaselaw-data` (private telemetry; its cards forbid release).

Network: the claude.ai cloud sandbox reached HuggingFace, Fedlex and the npm registry on
2026-10-26 (it did not earlier). Jonas' Mac disk is ~99 % full: keep large work off it.

## Run
```
pip install duckdb pandas pyarrow pdfplumber        # + pandoc for docx (not used today)
python3 pipeline/01_resolve.py ../jonashertner/opencaselaw   # 25 s
python3 pipeline/02_validate.py                     # 20 s
python3 pipeline/03_graph.py                        # 40 s
python3 pipeline/04_hierarchy.py && (cd layout && npm ci && node pack.mjs)
python3 pipeline/05_site.py                         # 40 s -> site/data (44 MB, not in git)
python3 pipeline/cantonal_basis.py                  # 10 s, offline: data/cantonal_basis.json
python3 pipeline/07_tree.py                         # site/data/tree.json + ingress(_k).json + agg.json (Stufenbau, Aufbau)
python3 pipeline/06_artifact.py                     # site/artifact.html for claude.ai preview (the 3D page)
python3 pipeline/08_web.py                          # 20 s -> docs/data (68 MB, committed): the public site (reads build/*.parquet too)
node layout/net.mjs                                 # 40 s -> docs/data/net.json (network layout, decision 29)
python3 -m http.server -d docs 8766                 # the public site: http://localhost:8766
python3 -m http.server -d site 8765                 # local view: http://localhost:8765
```
Fedlex fetchers (only when refreshing data): `fetch_fedlex_acts.py`, `fetch_fedlex_articles.py`,
`fetch_fedlex_structure.py` (`--missing` adds new acts only), then step 1, then `fetch_fedlex_regimes.py`;
`fetch_fedlex_xrefs.py` and `fetch_fedlex_basis.py` for the two legislative layers; `fetch_fedlex_history.py` (~10 min,
cached per segment in build/fedlex_history) for decision 32, then 08 and layout/net.mjs; `fetch_fedlex_dates.py` (~25 min,
after 08 has written atlas.json; then 08 again) for the time view: adoption, entry into force and repeal of every
federal act and treaty on the site (`data/fedlex_dates.json`, 5,111 SR numbers).
Cantonal collections (only when refreshing): `python3 pipeline/cantonal/lexwork.py` (~15 min), `zh.py`
(~15 min), `vd.py` (~30 min), `ge.py`, `ne.py`, `ju.py`, `ti.py`, `sz.py` (minutes each), then `cantonal_basis.py`.
Preview (private): the public site (decision 28) at https://claude.ai/artifact/XBRDshccV9KQwnf8qdaqo9 and,
since 2026-10-27 (Jonas: "replace the 3D preview too"), also at the former 3D preview
https://claude.ai/artifact/24YRYz7zvbowy3WEyXLhjU — republish both from `docs/index.html` without its
doctype/html/head/body wrapper (and without its charset/viewport/theme-color metas), with root `docs` and
every file under it, in two publishes each (≤ 64 MB: first all but `data/art/`, then `data/art/`). The 3D
page itself (`site/`, `06_artifact.py` → `site/artifact.html`) is kept in the repository but no longer
previewed. Licence: code MIT (`LICENSE`), data CC0, official texts Art. 5 URG, fonts OFL (README).

## Decisions taken (each disclosed on the page's method panel)
1. Language variants collapse onto one SR number (OR = CO, BGG = LTF, EMRK = CEDH).
2. Regimes, now generic (`01_resolve.py::act_intervals`): 412 of the 830 cited SR numbers carried
   more than one act (Fedlex). Earlier acts get `SR <n>@<year of the act>` (232 receive references).
   A code borne only by the earlier act (OG, ANAG, BStP, SGG, BEHG, GestG) means it; a code shared
   by old and new act (ELG, AsylG, MWSTG, BüG, BV) means the act in force on the decision date; a
   code only the current act bears (BGG, AIG) means the current act whatever the date. Short titles
   of repealed acts from Fedlex are added as aliases (223 added; 9 rejected because they collide with other usage
   — `REJECTED_FEDLEX`: LAG, LAJ, OASI, TVA, ALV, OOA, OGF, OAJ, BCO). 300 act nodes carry a regime
   suffix (305 until decision 32: an act that never entered into force governs nothing — CO2-Gesetz 2020, rejected
   on 13 June 2021, and Fedlex placeholders without entry into force, `…_cc` for GwG, TabPG, StADG, StReG, had taken the
   references dated before the first act); 303 earlier acts were looked up on Fedlex, 211 have a text. Editions of acts still in force
   (aStGB, aZGB, aOR) get `@a`; StGB in decisions before 2007-01-01 → 311.0@a.
3. ZPO/CPC/StPO/CPP before 2011-01-01: cantonal procedure codes (cantonal decision →
   `<canton> <code>`; federal decision → excluded). Cantonal decisions 2011–2013 citing an article
   absent from the federal ZPO/StPO → the canton's former code (6,616 refs, VD above all).
4. Cantonal homonyms (`CANTONAL_HOMONYMS`): cantonal decision → cantonal act; federal → excluded.
   Added 2026-10-26 on evidence of article-not-found rates per canton: StG, PBG, LAF, LC, LPers, PG,
   LAS. Unverified / a-prefix collisions (`UNVERIFIED_HOMONYMS`, incl. AZG = aZG Customs Act 1925,
   AWG, ASTG, ASTV) are excluded everywhere — never guessed.
5. Unknown codes in cantonal decisions → cantonal act `<canton> <code>`, except `NOT_CANTONAL`
   (federal acts missing from the alias tables, typos, generic words, SIA/CCT/CGA) and 2,113 codes
   with an article number glued on (BV8, ZGB8): 71,453 refs excluded.
   Cantonal act nodes with < 5 citing decisions are pooled per canton. Cantonal titles only where an
   official title in law_codes.json contains the code and names exactly one law (639 acts, mostly GE/TI).
6. Citation edges: `confidence_score` is NOT a probability. Keep all match types, drop < 0.5
   (33,369), merge duplicate decisions, dedupe pairs (543,190), drop self-citations (6,210) and
   targets outside the corpus (15,012) → 8,876,525 edges; 712,251 rest on a `bge_pincite` only.
7. Article validation (`02_validate.py`): an article node exists only if the article exists in the
   applicable Fedlex text — current act: main body of today's XML (transitional blocks restart
   numbering and are separate; SchlT ZGB is its own section); repealed blocks ("Art. 274–274g") are
   expanded; earlier acts: union of their earliest and last published text; aZGB/aOR: today's
   numbering. Results: 9,054,590 valid / 30,590 not in text (bucket per act) / 12,038 no text;
   63,559 article nodes.
8. Every number shown is computed, not estimated; every node links to its source
   (decisions: `https://mcp.opencaselaw.ch/entscheid/<urlencoded id>`; acts: Fedlex ELI page,
   articles with `#<eId>` anchor).
9. Co-citation: min 20 (acts) / 10 (articles) shared decisions, lift ≥ 2, top-8 per node ranked by
   n·ln(lift) (lift alone surfaces obscure pairs). 7,376 act edges, 102,195 article edges.
10. Labels say exactly what is measured: "Decisions referring to this article", "Most-cited decisions
    referring to this article" (ranked by citing decisions), never "leading case".
11. One judgment, one node: 5,812 BGE/BGer docket twins and 185 same label/date/canton duplicates
    are merged onto one id (BGE preferred).
12. Impossible source dates (14,645 decisions dated > 1 year before their own docket year; 1 future
    date) are treated as unknown: no year shown; act assignment uses 1 January of the docket year.
13. Alias fixes: OPC → 831.301 (not 281.41; not-found 69 % → 0.4 %); KLV → 832.112.31 for decisions
    before 2025-01-01 (KlV climate ordinance from then on: ambiguous, excluded).
14. Counting unit on the map: a decision counts once per act / article; areas count distinct
    decisions citing any act inside (not the sum of their acts).
15. Two layers of links between acts, never mixed: case law (co-citation, decision 9) arcs above the
    SR plane, blue; legislation (`fedlex_xrefs.json`, directed, weight = provisions of the referring
    act that name the other) arcs below it, gold; a pair in both is white. 11,693 legislative pairs
    join two acts on the map (474 name an SR number without a node); 507 pairs are in both layers.
    Lines follow the SR tree (Holten bundling, β = 0.75) and merge into the visible areas from afar.
    Legislation is today's text only (no time series); case law has per-year counts (`ey.json`).
16. Stufenbau (default view, `07_tree.py`): federal law in force as the tree its own Ingresses state.
    Apex: the BV with its titles/chapters/sections/articles (all 232). Floors = enacting authority
    named in the Ingress (Bundesversammlung 426; Bundesrat + federal courts 916; departments, offices,
    other bodies 669; 37 from the title). Parent = a stated basis: nearest higher floor, then longest
    common SR prefix, then Ingress order; every other basis kept (dashed). BV 1874 citations: the
    article Fedlex gives as today's equivalent; with a plain "SR 101" footnote the 1874 text is meant
    if the act predates 2000 and its Ingress was not revised since, or the number is old-style
    (34ter) → node "BV 1874". 3,014 bases; 13 name an article missing from the target's current
    text (real dangling bases, e.g. Art. 19/21 BWIS in SR 120.4, Art. 929a OR in SR 211.435.1).
    Treaties appear only as the basis of a federal act (96); 79 acts have no basis in the tree.
17. Cantonal floors (Art. 49 BV: federal law prevails, so they lie below every federal floor): the 26
    constitutions (SR 131.2, `pipeline/cantons.py`) hang from Art. 51 BV (a constitutional link, not
    an Ingress; drawn down the central axis). Below, every act in force of the 26 official collections
    (16,358 + 26 constitutions) on floors by the issuer its Ingress names: 5 parliament/people/
    Landsgemeinde/intercantonal incl. acts of intercantonal bodies (6,977), 6 government + cantonal courts (7,709), 7 directorates,
    offices, other bodies incl. communal bodies some cantons publish and church law (1,672);
    no issuer → from the title (1,435, marked; every agreement, intercantonal or with a foreign state,
    → 5 whoever concluded it: intercantonal law prevails over cantonal law, Art. 48 Abs. 5 BV — until
    2026-10-26 agreements between governments went to 6 by title but to 5 by Ingress, 131 acts moved;
    a contract of the canton "vertreten durch den Regierungsrat" with a commune → 6; 187 with no
    telling title → 7, marked "unknown"; parties of agreements since decision 26). Found through the matrix (decision 25): "Le Parlement de la
    République et Canton du Jura" and GR's "Vom Volke angenommen" were not read as parliament/people
    (287 acts were on floor 7); agreements whose Ingress lists the cantons one by one or says "die dieser
    Vereinbarung beigetretenen Kantone", or whose title names the agreement later ("Zentralschweizer
    Fachhochschul-Vereinbarung"), → 5 (117); "Plenarausschuss/Geschäftsleitung der Gerichte" → 6.
    Acts of an intercantonal body (its Verwaltungsrat, departments of several cantons) → 5 since decision 27. Parent = the nearest higher cantonal basis the Ingress names
    (a KV article node `KV:<ct>:art_N`, or a cantonal act), then text order. No parent → one of five
    groups, in this order (decision 24): "basis named, not identifiable" (469; incl. acts of another
    canton), "names only acts not above it" (lower floor or a same-floor circle, 4), "only federal law
    named" (1,264, incl. earlier federal acts and federal law in general), "no basis named" (2,595), "no
    preamble published" (1,227: TG above all; ZG's "published only on Intlex" and UR's "durch Verweis
    veröffentlicht" notes count here). A basis is identified by its footnote/inline collection
    number, the name of a constitution, a fixed federal title (not inside "Einführungsgesetz zum …"),
    type + date matched against the SR taxonomy titles (DE/FR/IT) or the canton's own acts (same type
    and agreeing title words required; a federal act only when the text says "Bundes-/fédéral/
    federale" or, without a cantonal act of that date, on ≥ 2 agreeing title words; ties → "?"), or an
    abbreviation the canton states. Amendment dates ("Fassung gemäss Nachtrag vom …") are skipped.
    Since decision 24 also: a title without date that equals exactly one act's title ("des
    Bundesgesetzes über die Binnenschiffahrt", "Einführungsgesetz zum ZGB" = "Gesetz über die
    Einführung des ZGB"), an abbreviation with a date ("Art. 11 GSchG vom 8. Oktober 1971" → the
    earlier act), "son ordonnance d'exécution" after a federal act, and "Bundesgesetzgebung über …"
    as federal law in general ("SR ?"). 24,382 bases (decision 26): 3,527 KV, 11,826 cantonal, 6,886
    federal in force, 164 earlier federal, 369 federal law in general, 184 acts of another canton
    ("X:", by its collection number or its name), 1,426 not identifiable (1,979 unresolved incl. the
    general ones and other cantons' acts, 8.1 %); 534 cite a federal law by its old date while the
    footnote gives today's SR number (flag "old"; the number may since carry another act, e.g. SR
    832.102.2), 684 a cantonal act likewise (a later year under the same number); 53 footnotes give
    another act than the text names by type and date (flag "note"; the text prevails). 18 name a KV
    article that does not exist. Spot checks (3 × 40 random bases; 2026-10-26 another
    3 × 40 of the new matches): no wrong target after the fixes. Decision codes → the act whose collection states that
    abbreviation (any official language; a second code for the same act is merged, decisions counted
    as the exact union): 1,207 codes, 497,161 decisions; 2,599 codes (142,706 decisions) have no act
    in force (mostly repealed: pre-2011 procedure codes; communal BZO) → group "cited, not in the
    collection". VD files law + arrêtés de mise en vigueur under one number: the main act keeps it
    (`~1`, `~2` for the others). Cantonal spheres √(decisions + 120) (federal + 400) to fit.
    Step 1: "KV/ZH", "Cst/VD" → that canton's constitution in any court; "KV", "ConstC", "CstC" →
    the deciding canton's, excluded in federal courts (was: all "KV" → Bern; report B9).
18. Tree layout fix (2026-10-26): `place()` added arc lengths (in units of C) as angles, so every
    subtree wrapped around the circle ~C times: siblings were scattered. Angles = need / C now; each
    child lies inside its parent's span (checked: 0 of 2,370 outside). Branches are drawn as a radial
    elbow tree on the cone's surface (one trunk + arc per parent and floor, a drop per child; Bézier
    in polar coordinates), not as chords through the cone.
19. Light theme by default ("paper atlas": ink on #f3f1ec, premultiplied alpha, no bloom; colours
    via `ink(c) = c^1.6·0.8`); the night-sky look stays one click away (☾). Tree overview: the
    delegation tree alone; case-law/legislation arcs for the selected act, or all via a toggle.
    Depth fade (atmospheric perspective) behind the point looked at.
20. Narrative layer ("martini glass": author-driven opening, then free exploration). Every sentence
    of the opening and the tours carries computed numbers only (`facts()` in main.js, from tree.json),
    with the BV article it paraphrases (Art. 3/42, 49, 51 BV). Wording rules found by checking:
    decisions "refer to at least one federal act (treaties included) or cantonal act, in force or
    earlier" (979,726 counts every act on the map, not only law in force); federal counts exclude
    treaties (2,011); floor 1 = enactments of the Federal Assembly (incl. its 19 ordinances), floors
    2–3 "nearly all / mostly ordinances"; parents that are treaties are not counted as "an act of the
    Assembly". Cantonal nodes carry the floor, not the issuer → the card says "floor: …", federal acts
    with a stated issuer "enacted by: …". FR/IT use gender-neutral forms ("autorité :", "base :").
    Time-lapse = today's law by adoption year (survivorship: repealed acts absent; 133 undated acts
    appear only in the current year).

21. Connections are brought to the act, not drawn across the map ("bring & go", Moscovich et al.,
    CHI 2009): in the cone an act's partners sit on other floors and in other cantons, so lines to
    them ran off-screen to 2–3 px dots. Selecting an act (default on, toggle "Verbindungen", key C)
    gathers them around it in an overlay (#web buttons + #wedges SVG, crisp text, keyboard- and
    screen-reader-reachable): above = stated bases (dashed = further bases), below = acts resting
    on it (most cited first, with the articles they name; for BV/KV the articles most acts rest on),
    left = legislation (→ provisions of this act naming the other, ← the reverse), right = case law
    (co-citation pairs of decision 9, so "7 of 70" counts partners in that pruned network) and the
    4 most-cited decisions. Headings say "shown of total"; "+ n" opens the panel list. Each partner
    flies in from its projected real position; hover = its 3D link + a dotted thread to its place
    (or to the screen edge towards it); click = go (the constellation re-forms around it). While it
    is shown, 3D partner labels, edge chips, the 3D link fan, spine and legend step aside and a
    spotlight veil dims the scene except the act. Tours show it at node stops (no decisions; the
    courts stop keeps the 3D decisions); the descent and the opening do not.
22. Fedlex titles carry markup (CO<sub>2</sub>, 1<sup>er</sup>, <p>, <em>, a stray <BD>): `05_site.py::plain`
    writes text only (CO₂, 1er).

23. Aggregated overview "Aufbau" (`07_tree.py` → `site/data/agg.json`, 0.25 MB; view in `main.js`, deep link
    `#aufbau`): rows = floors (BV parts, Bundesversammlung, Bundesrat + courts, departments; the 26
    constitutions, cantonal floors 5–7), blocks = SR area (first digit) for federal law, canton for
    cantonal law (156 blocks). Every act in force (18,395) counts once in its block and arrives by one
    flow from its primary parent (358 flows), so a block's inflows + stubs = its acts (asserted in 07).
    Stubs instead of flows, five kinds (decision 24): only federal law named (1,264, blue), basis named
    but not identifiable (469) and only acts not above it (4; both ochre), no basis named (2,675 incl.
    80 federal, grey), no preamble published (1,227, hatched); a key below the cantons lists them and
    opens each kind across all blocks. Widths = acts on three disclosed scales (BV parts by what rests on them; federal; cantonal);
    a flow is exact at its lower end and a share of the source's outflow at its upper end (parallel-sets
    style). 1,248 acts skip a floor (1,261 before the floor fixes of decisions 26/27): their flows run in a lane beside the target column instead of
    through the floor between. Art. 51 BV → 26 constitutions as a trunk on the left (not an Ingress).
    Layers: legislation = provisions of federal acts naming an act of another block (treaties naming
    treaties dropped); case law = distinct decisions citing acts of both blocks (refs_valid, BV by
    article → part), ranked by n·ln(lift), lift ≥ 1.5 (raw counts are dominated by BGG/BV/ZPO, cited
    everywhere); 90 strongest pairs drawn, all of a block's on pointing. Decisions per block exact
    (distinct); 936,927 decisions refer to at least one act in force (979,726 incl. earlier acts).

24. The 54 % check (2026-10-26). Floor 5 first showed 54 % of its acts hanging from no cantonal
    basis; after the fixes below and the floor fixes of decisions 17, 26, 27: 3,676 of 6,977 (52.7 %). The
    share is real, but "no cantonal basis" was one grey group mixing five cases. Now: 1,963 the Ingress
    names no basis (28.1 %; sample 25/25 genuine: "Der Grosse Rat … beschliesst:", "Le Grand Conseil …
    décrète"; drafting practice differs: JU 2 %, UR 5 %, ZG 8 %, VS 8 % vs LU 58 %, GL 55 %, TI 55 %,
    GE 51 %; agreements that moved to floor 5 in decision 26 often name none), 755 no preamble
    published (10.8 %), 784 only federal law (11.2 %), 171 a basis named but not identifiable (2.5 %),
    3 only acts not above them.
    Parser fixes found on the way (each checked by diff against the previous run; 29 targets changed,
    all corrections): footnote digits glued to the year ("19912"); "gestützt §", "in Hinsicht auf",
    "im Hinblick auf", "gemäss", "dans le respect de" (weak keywords only before the enacting formula);
    a footnote giving the act's own number no longer hides the KV beside it; the head of a designation
    decides its type ("l'ordonnance … relative au code pénal militaire" is not the MStG); two footnotes
    or "(SR …)" naming different acts are two references; "et des communes" no longer splits a title;
    the DE/FR/IT titles of one federal act are no rivals in a tie; Fedlex FR/IT titles write
    "1<sup>er</sup>", so every federal act adopted on the 1st was missing from the FR/IT index (FR "loi
    fédérale du 1er juillet 1966 sur les épizooties" had gone to the cantonal finance act); taxonomy
    cross-reference nodes ("BG über …") are not acts. A canton's stub panel compares its share with the
    same floor in all cantons (computed; cantons with ≥ 20 acts on the floor). Aufbau is the first view:
    no hash → overview unless the visitor last chose the cone (`slm-view`); the opening plays the first
    time the visitor enters the cone; act links (`#SR_220--art_41`) open the act as before.

25. Matrix (`main.js` "the matrix", deep link `#matrix`; data in `agg.json`: `basis` = every stated
    basis by block pair [row, column, acts, acts whose place in the tree it is], `nb`/`cb` = tree/core
    node → block, `rank`). A dependency structure matrix of the overview's blocks in Stufenbau order:
    BV parts, treaties, floors 1–3 by SR area, then per canton KV, 5, 6, 7 (canton-major, so each canton
    is a 4 × 4 module on the diagonal). Cell = acts of the row naming a basis in the column (all stated
    bases, 24,537 act → target pairs in 1,457 cells), provisions (federal acts only), or case-law lift
    (≥ 20 shared decisions; diagonal empty, not computable from pair counts). Log colour up to the
    strongest cell shown. Grey fields = same floor; below = a higher floor (21,666 bases), same floor
    2,817, a lower floor 54 (each read by hand, decision 26; it was 571 before the floor fixes the
    matrix exposed, 109 before decision 26). Sections: all (156 × 156), federal (with labels), cantons (104 rows × federal
    columns + the canton's own four). In the basis layer BV parts and treaties are columns only (they
    rest on nothing). Hover = row/column cross + tooltip; click = the acts behind the cell (basis: acts
    and their targets; legislation: act pairs by provisions; case law: pairs of the pruned co-citation
    network); the strongest 12 cells beside it; arrow keys + Enter. Panel counts checked against the
    cells (18 of 18) and the lower-floor list against the pipeline (54).

26. The 109 inversions read (2026-10-27, `reports/inversions-review.md`, data `reports/inversions_review.json`).
    Every stated basis on a lower floor than the act naming it was read in its Ingress. 62 of the 109
    were our errors. 45 were floors. Agreements now take their floor from their parties (title before
    the topic + Ingress head, `agreement_floor`): two or more cantons, the Confederation, a foreign
    state or the Holy See → 5; church bodies only → 7; communes only → 7; the canton with communes, a
    church or a private party → 6 (5 if its parliament is the party, 7 if a department is); companies
    only → 7. Also "Fachhochschul-Vereinbarung" and "Geldspielkonkordat" are agreements; VD writes
    "CONVENTION"; "Präambel" is no issuer; "Conseil représentatif", "I Consigli del Cantone", "Gran
    Consglio" are parliaments; "Landsgemeindebeschluss" → 5; acts of church bodies by title → 7; a
    conference is intercantonal only with a cantonal word ("Konferenz der kantonalen …", "Conférence
    latine", EDK/GDK/SDK …), not "Mittelschulkonferenz des Kantons", "Conférence des préfets",
    "Präsidialkonferenz der Regionalgerichte"; the issuer is tested without "unter
    Genehmigungsvorbehalt der SDK" or "gestützt auf …"; "Interkantonales Organ", "échange de notes" →
    5. The other 17 were readings. UR prints "durch Verweis veröffentlicht" where the Ingress would be:
    an editorial note, not a basis (`noing`). VD's "Note :" inside an Ingress. Text after the enacting
    formula ("beschliesst:", "erlässt … als Tarif:", "schliessen nachstehende Vereinbarung ab:";
    colons in brackets do not count) is the act's text or the collection's footnote apparatus. A
    footnote with another canton's collection number ("GS 817.010", "bGS 815.11", "RSJU 101" — a bare
    "GS" is everyone's chronological series) or a designation naming another canton ("der bernischen
    Fischereiverordnung", "Verfassung des Kantons Basel-Stadt"; an adjective only next to an act word;
    not an agreement "mit dem Kanton NW", which the collection holds) → "X:", never the own canton's
    act. The only act of a date needs an agreeing title word (type words, "d'exécution" and
    "kantonal" do not count; "son ordonnance"/"la loi précitée" borrow the words of the act just named;
    treaties of that exact date are specific enough). A footnote whose act has another type than the
    text's act of that date yields to the text (NE 991: note "RSN 601.80" = RELSub, text "la loi sur
    les subventions, du 1er février 1999" = LSub; flag "note", 53). Found on the way: LU numbers with a
    letter ("SRL Nr. 539c") were cut to "539", so those footnotes pointed at another act (58 acts); ZH footnotes
    without prefix ("414.11."). Diff against the run before: 147 changed cantonal targets
    (sample 40/40 corrections), 37 former matches now "?" (34 had been wrong), 329 floors (all read
    by group). The 55 that remain (47 of the 109, 8 newly exposed by the floor fixes) are genuine
    readings, in six groups shown in the matrix's lower-floor panel: 21 the preamble lists a lower act as
    context ("vu"/"visto" lists: the law and its executing ordinance — VS, FR, GE, TI, VD, NE practice);
    15 an agreement names a party's own competence norm (Bernese Fischereiverordnung; the communes'
    Gemeindeordnungen; the Konfessionsteil's constitution); 12 the target's floor is a default (no
    issuer: FR Tarif 1968, ZG Richtplan, SO Volksbeschluss 1898 — floor 5 by the citing act's own
    words, ZBSA rules published by reference); 3 the number now carries a successor (JU); 3 federal
    approvals name the contract approved; 1 genuine upward delegation (ZG 413.123 "gestützt auf § 20 der
    Ausführungsbestimmungen 2" of the Amt für Berufsbildung: Phase 2). 07 reports `mat_low_open`
    (pairs not yet reviewed; 0) and `mat_low_review_stale` (reviewed pairs gone; 0): after a data
    refresh, read the open ones and add them to the JSON.
27. Acts of intercantonal bodies → floor 5 (2026-10-27, Jonas): law-making by intercantonal bodies is
    intercantonal law and prevails over cantonal law (Art. 48 Abs. 4/5 BV). An issuer naming several
    cantons or an intercantonal institution ("Verwaltungsrat der BVG- und Stiftungsaufsicht der Kantone
    …", "BSABB … beider Basel", "Hochschulrat der OST – Ostschweizer Fachhochschule", "les départements
    … des cantons universitaires romands", "CONFERENCE LATINE", "Fondation romande") → 5; with no issuer,
    a title naming such a body in the genitive ("Actes adoptés par les organes du Gymnase intercantonal
    de la Broye", "Statuten des Universitäts-Kinderspitals beider Basel") → 5, not a canton's approval or
    executing act about one, not a foundation unless called intercantonal; acts UR and ZG publish only
    by reference (all 27 point to an intercantonal body's site or to Intlex) → 5 ("Verweis"); a copy
    with no issuer takes floor 5 when another collection's copy (same title, same date) names its
    intercantonal issuer (4). 40 acts moved; the SRK's rules (a private body acting for the cantons)
    stay on 7. The lower-floor list: 54 (UR 20.2715 → ZBSA rules no longer lower).

28. The public site (`docs/`, 2026-10-27; GitHub Pages from `/docs`; the 3D page in `site/` stays as it was).
    Jonas: "redo the UI from scratch … world class … a better representation than blobs … clear white
    background … each label super clear, no secondary labels … all screen sizes … DE/FR/IT/EN".
    Form: a nested squarified treemap on canvas (Bruls et al.; d3's ratio φ), every act a tile — text fits
    rectangles, circles waste a third of the plane. Hierarchy: root → federal / international / cantonal
    law → SR areas (taxonomy) or cantons (Art. 1 BV order) → acts → (cited federal acts) divisions →
    articles. "Fläche: Erlasse" = every act in force the same size (groups first, then acts by level, so a
    canton shows its own Stufenbau as a staircase); "Fläche: Entscheide" = decisions referring to the act
    (largest first; earlier acts and codes not in the collection appear, hatched). Colour = who enacted it
    (Ingress floor): one blue ramp Verfassung → Parlament → Regierung → Verwaltung, treaties ochre (#d8b679,
    checked with the dataviz validator: CVD ΔE ≥ 15 against the ramp), the one federal act without a
    recorded level (SR 173.110.3) grey; inside an act, articles by decisions (log ramp). The 26 cantonal
    constitutions sit in their canton only (no longer twice: SR 131.2 is skipped in the federal block),
    so federal law in force = 2,013 (= decision 16's floors), total 21,495. An act heading its own SR
    group (412.10 BBG with BBV and the 190 EFZ/EBA ordinances) is moved into that group, which takes its
    abbreviation as name. Labels: abbreviation; an abbreviation three siblings share ("EFZ") is no name;
    without one, the title without its date, without the words it shares with ≥ 2 siblings (prefix and
    suffix) and without its type phrase ("Verordnung über die …", "Loi sur la …", "Ordinanza concernente
    …"); VD's capitalised first word ("LOI sur …") is written "Loi"; a part filling > 80 % of its parent
    does not repeat its header; a label is drawn only whole or with ≥ 8 characters. Zoom animates every
    tile from its old to its new rectangle (exits fly out with the camera). Panel: act (facts, decisions
    per year, most-cited articles, bases with clause verbatim, dependents, co-citation, references, most-
    cited decisions, Ingress), article, area (acts by level, distinct decisions from core's containers,
    most-cited acts). Views: Karte, Hierarchie (decision 23, restyled), Abhängigkeiten (decision 25; cell
    panels from `docs/data/pairs.json`, every act → basis pair 07 counts: 24,537 in 1,457 cells, checked
    against `basis`, 0 mismatches), Methode (the 3D page's method text with its 3D parts rewritten).
    Search: abbreviations in every language, SR numbers, title words (short words must start a word),
    "Art. 41 OR" (exact abbreviation first), division headings with parent headings and 4-letter stems
    ("Mietrecht" → OR Achter Titel: Die Miete). Hash routes `#<lang>/<id>[:<eid>]` (`:` alone = inside the
    act); old `#SR_220--art_41` links still work. Light only, by Jonas' wish. Geist / Geist Mono (OFL) self-
    hosted. Phone: compact header with a language select, the panel as a bottom sheet above which the map
    shrinks, hierarchy and matrix scroll sideways. 60 fps in headless Chromium (median frame 16.7 ms).

29. Network view "Netz" (2026-10-27, Jonas: "an exceptional graph also showing the complexities and
    interdependencies"; `layout/net.mjs` → `docs/data/net.json`, view `docs/js/net.js`, deep link
    `#<lang>/net[/<id>]`). Nodes = every act with at least one link (18,051: federal 2,083 incl. earlier
    acts, treaties 2,059, cantonal 13,909); 4,273 acts in force have none and are counted, not drawn.
    Three layers, never merged, each its own colour (dataviz validator, all pairs: CVD ΔE ≥ 13.5, normal
    ≥ 18.8; the ink of the bases is a deliberate neutral, so it fails the categorical lightness/chroma band):
    stated bases (ink, 24,497 act → basis pairs from `links.json`; primary basis weighted 2), legislation
    (vermilion, 11,693 act pairs, decision 15) and case law (purple, 7,396 co-citation pairs, decision 9).
    Layout in two levels — a plain force layout of 18,000 nodes was a hairball whose positions meant
    nothing: (1) the place of each cluster is fixed by rule, not by force: federal law in the centre (the
    BV at 0,0), treaties above it, the 26 cantons on a ring in the order of Art. 1 BV, clockwise from the
    top; a cluster of n acts is a disc of radius 10·√n (area ∝ acts). (2) inside a disc, ForceAtlas2
    (LinLog, Barnes-Hut, gravity 1.2, scaling 4, outbound attraction distribution) gives each act its
    angle; the radius is its level: rings from the centre outwards constitution → parliament →
    government → administration → not in the collection (earlier acts, codes), each ring's area ∝ its
    acts; federal law and treaties in sectors by first SR digit. Acts are spread on their ring segment by
    Halton points (no overlap, no clumps). A canton's disc is turned so that its acts with links to
    federal law face the centre. So distance from a disc's centre = level of enactment (exact), sector =
    SR area (exact), angle inside a ring = closeness in the force layout (designed, not measured).
    Links between clusters are bundled (cubic Bézier through each disc's facing rim, β 0.92); links
    inside a disc are straight. Rendering: one bitmap cache, transformed while panning, redrawn after
    140 ms (38 ms per redraw at 1440×900); click = the act's ego network over a white veil, its
    partners labelled, the panel opens; search jumps into the network while it is shown. Counts by
    pair of clusters: bases 15,159 inside a canton, 6,340 canton → federal, 2,867 federal → federal,
    131 federal → treaty; legislation 7,446 federal ↔ federal, 3,304 treaty ↔ treaty, 921 federal ↔
    treaty, 22 cantonal constitution → BV (the constitutions are in Fedlex as SR 131.2); case law 2,734 canton ↔ federal, 2,463 inside a
    canton, 1,978 federal ↔ federal. Bridges (federal acts most cantons rest on, BV aside): OR, WaG,
    GSchG, SVG, BGS, AIG, ArG — 25 cantons each (TG publishes mostly no preamble); ZGB 24 cantons with
    261 cantonal acts, KVG 24/181, StGB 24/159. The panel of every act in the network offers "Im Netz zeigen".
30. Navigating the network (2026-10-27, Jonas: "pretty but navigation not yet intuitive. must be magical"). Three
    steps, each a route: the whole network (`#de/net`), one jurisdiction (`#de/net/ZH`, `fed`, `int`), one act
    (`#de/net/ZH/700.1`). The camera flies between views on the van Wijk–Nuij path (2003; d3's interpolateZoom,
    ρ = √2): out, across, in, so the eye keeps its place; the destination is rendered before the flight starts and
    re-framed if the panel opens on the way. The pointer finds what can be told apart: on the whole network a
    jurisdiction (and the largest acts), inside a jurisdiction shown ≥ 130 px wide its acts; with an act open its
    partners and chain first (12 px, touch 22 px). Pointing rests 140 ms before a preview (an act's links, a
    jurisdiction's links to the rest), so sweeping the pointer does not flicker. A jurisdiction opens with the rest
    veiled, its links to the rest kept, its levels named on the rings and its acts labelled; the panel gives acts
    in force with a link of all in force, links outside by layer, by level, the jurisdictions most linked with and,
    for a canton, the federal acts its acts name most. An act opens with its links growing out of it (650 ms), its
    chain of primary bases up to the Constitution as one cased line (KV → BV dashed: Art. 51 BV, not an Ingress), and
    for 14 s points moving from the act that names to the act named (bases and legislation; co-citation has no
    direction; 320 strongest links); the chain is also the breadcrumb ("Netz › BV › KV ZH › PBG ZH"; without a
    chain to a constitution the jurisdiction stands first). Following a partner keeps the link travelled lit
    during the flight. Pointing at a partner, a panel row or a crumb lights it and its links; the tooltip says
    what links them in words, with the articles named ("PBG ZH stützt sich darauf (Art. 25)", "Nennt RPG in 4
    Bestimmungen", "Mit RPG zusammen zitiert in 390 Entscheiden"). A click elsewhere goes one step up (an act →
    its jurisdiction, without moving the camera); Esc goes up with a flight; arrows move to the nearest item that
    way, Enter opens. A hint per step until the visitor has done it once (`slm-net-learnt`), an overview map in
    the corner once the view is closer than 1.8× the whole. Found on the way: while dragging, the cached picture
    moved against the hand until it was redrawn (sign of the pan term in the blit).
31. Time view "Zeit" (2026-10-27, Jonas: "a historical development view for Karte, Netz and Abhängigkeiten so we can
    understand how this evolved over time"; `docs/js/time.js`, data `docs/data/time.json` from 08). One year for the
    three views, in the hash (`#de@1975/net` since decision 32; internal links keep it). When an act exists: a federal or cantonal act
    from its year of adoption (18,389; 8 undated → only the last year); a treaty from its entry into force for
    Switzerland (Fedlex, all 3,098; EMRK 1974, not 1950); an earlier federal act courts cite while it was in force
    (297 + 3 editions since decision 32; BV 1874 1874 to end 1999, OG 1945 to end 2006; none undated); a cited code no collection holds from its first
    citation (2,726); before 1848 → 1848. Bases: both acts exist (as today's Ingress names them — it may have been
    amended; RPG names today's BV, so in 1985 it has no chain). Co-citation pair: from the year of its 20th shared
    dated decision (7,283 of 7,396; 113 only in the last year). Legislation: today's text only (chip "nur heutiger
    Stand"). Decisions by date: 966,313 dated, 13,413 undated; series from 1895, federal + European courts
    (canton CH/CE) and cantonal courts. The bar under the view is the history: today's acts existing per year, stacked
    by level, and decisions per year below (no shared axis); drag, ←/→ (±1), PageUp/Down (±10), Home/End, play at 13
    years/s (from 1848); the note under it states both limits (survivorship; the rise since 2000 is mostly courts
    publishing more). Map: today's layout kept, an act not yet there is an empty plot (labels faint); with
    "Entscheide" a plot fills by the share of its decisions handed down; groups too small to subdivide by their
    share; tooltip "seit 1979" / "erst 2003". Network: an act not yet there a 1 px trace; sizes by decisions so far;
    the chain stops at an act not yet there. Matrix: the basis layer recounted from `pairs.json` (an act counts once
    in a cell when it and its basis exist), today's colour scale kept so cells darken over time; provisions and case
    law today only; the rank shares hidden. 60 fps in headless Chromium while playing (map, matrix; network p95
    33 ms after 1995). Uncomfortable truths, said on the page: earlier periods look emptier than they were (repealed
    law is missing except the 305 earlier federal acts), and the growth of case law is largely publication.
32. The federal history (2026-10-27, Jonas: "yes, fetch the full federal history"; `pipeline/fetch_fedlex_history.py` →
    `data/fedlex_history.json`: every consolidation abstract on Fedlex, 17,319 acts, queried per ELI segment because
    OFFSET paging answers HTTP 500 beyond ~9,000). Status: 0 in force, 1 no longer published in the SR, 2 obsolete, 3 no
    longer in force, 4 not yet in force. The end of an act's force: its repeal (dateNoLongerInForce), else the day
    after the end of applicability a temporary act states (dateEndApplicability, on the abstract or on its act in
    the AS; where both exist the repeal is never later: 89 repealed early, 26 on the day). An act enters the time
    view if it ended before the run, is not in force (0/4) and is not one of the map's acts (by ELI): 11,413 acts
    (9,356 repealed, 2,058 temporary acts that lapsed — the panel says "Befristet, galt bis 31. Dezember 1974").
    7,594 carried an SR number (6,629 federal acts, 952 treaties, 13 cantonal constitutions, in their canton): id
    "<SR>@<year of adoption>" ("~2" for a second act of that number and year), placed next to the act now under
    that number, else in the nearest SR area. 3,819 have none (3,568 ended before 1970): their own group "Nicht
    mehr in Kraft, ohne SR-Nummer" in federal and in international law (kind g, `hg`, id `fed/-`, `int/-`), id
    "@<year>~k". Level from the document type: Bundesgesetz, dringliches BG, Bundesbeschluss,
    Verordnung der Bundesversammlung, Erlass eines Rates → 1; Verordnung des Bundesrates, Erlass eines eidg.
    Gerichts, Vertrag Bund–Kantone → 2; Departements-, Amtsverordnung, Erlass einer Anstalt, Kommission → 3;
    international texts → treaty; Kantonsverfassung → 0. Shown from adoption (treaty: entry into force) to repeal.
    Every act Fedlex marks no longer in force (1–3) now has a date of its end (`noend` in time.json: 0; the page
    names the number only if a refresh brings one). Acts without any status on Fedlex are not history: 163 drafts and
    placeholders (`…_cc`, "*wird später veröffentlicht*", no entry into force), 16 enter into force later, and 276
    are in force by their own dates but have no status — see Next. Before 1948 the record holds almost only what was still in force in 1948 (21 acts repealed
    earlier): said on the page. No value today, so the map, search and their counts are unchanged; the time view's
    map holds every act ever in force (`M.val.hist`, earlier acts in their level's colour `M.hcls`) and re-lays out
    when it opens; the header counts what exists in the year ("916 Erlasse 1955"), the editions aZGB/aOR/aStGB
    ("@a") are shown but not counted twice. Names in `hnames.<lang>.json` (loaded with the time view). Not in the
    network or matrix (no Ingress or cross-references of repealed acts were read). The panel of an earlier act says
    "Heute unter dieser Nummer" (not "Heute gilt": a number can carry an unrelated act). Federal acts / treaties in
    force by year (data): 1900 132/150; 1914 276/235; 1930 560/376; 1939 1,049/511; 1945 1,618/545; 1948 1,884/630;
    1950 1,824/664; 1960 1,659/920; 1970 1,779/1,250; 1980 2,008/1,582; 1990 2,152/1,788; 2000 2,157/2,210; 2010
    1,947/2,635; 2020 2,181/2,980; 2026 2,016/3,098 (2,013 in force + 3 earlier acts in force until 2027). The rise
    1939–1948 and the fall to 1960 are consistent with the wartime full-powers law and its winding-down (574 temporary
    acts lapsed in the 1950s; not checked against the AS). Found on the way: `#de/101@1874` (BV 1874) was read as "time view, year 1874" — the year now stands
    next to the language (`#de@1975/net`; the first links `#de/net@1975` still work); six earlier acts labelled with a
    month ("916.310@1958-08", two acts of one year) were matched to the wrong Fedlex record (title and adoption of
    the first act, shown only in the last year): matched by date prefix and ELI now; an earlier act without a repeal
    date on Fedlex ends when its successor starts (VEZL 2002 → 2013).

## Pipeline status
- [x] Step 1 `01_resolve.py`: 97.75 % of references resolve to an act; rest counted by category.
      Deterministic (ties broken explicitly); two runs give identical reports.
- [x] Step 2a `02_validate.py`: article validation (decision 7).
- [x] Step 2b `03_graph.py`: per-act/article counts and years, authority (in-degree), co-citation.
- [x] Step 3 `04_hierarchy.py` + `layout/pack.mjs`: d3-hierarchy circle packing of the SR tree
      (siblings in SR order, padding ∝ parent size), cantonal region by canton; article grid in
      reading order inside each act, a blank heading row before each top-level unit (`05_site.py`).
- [x] Step 4 `site/` (index.html + app.js, no dependencies): Canvas 2D in double precision instead
      of WebGL (exact multilingual text, zoom to 10^5× without float32 jitter, no CDN dependency;
      2–26 ms per frame in headless software rendering). Semantic zoom, instant search (acts by any
      language's code, "Art. 41 OR", SR numbers, titles, and topics from the acts' own headings —
      "Mietrecht" → OR Achter Titel: Die Miete; lazily loaded `topics.<lang>.json`), DE/FR/IT/EN, method panel, period filter,
      dark mode, phone layout (bottom sheet), deep links `#SR_220--art_41`. Articles loaded per
      shard (168 shards, ≤ 1.8 MB raw).
- [x] Step 4′ 3D (`site/index.html` + `main.js`, `gl.js`, `i18n.js`, `method.js`; three.js 0.160.0 from
      jsDelivr via import map). The SR plan is the floor: containers are flat glowing discs, acts are
      ray-traced sphere impostors standing on it (11,000 spheres = 11,000 quads; floating origin for
      float32 depth). Display-referred colours: `renderer.outputColorSpace = Linear` (sRGB output
      lifted every dark tone). Ribbons are screen-space strips (double-sided: their winding is
      arbitrary). Zooming into an act dissolves its sphere into its articles, which rise as a skyline
      (height ∝ √ citing decisions). Selection = focus + context; pointing at a partner in the panel
      lights that link; off-screen partners get edge chips. Views: top / tilted / side (side shows
      both hemispheres). Rebuilds of the bundles are skipped unless the set of open containers
      changes. The 2D Canvas version survives as `site/flat.html` + `app.js`.
      `06_artifact.py` inlines the modules (each its own scope) for the claude.ai Artifact.
- [x] Step 7 `07_tree.py` + tree view in `main.js` (`setMode("tree"|"sr")`): per-view layouts (X, Z,
      CY = centre height, R, P, kids, SPAN); radial cone, floors as glass plates, delegation lines
      weighted by what hangs below, pulses running down; links bundled through the tree (attach to the
      deepest ancestor whose span on screen ≥ 12 px); panel: verbatim Ingress, bases with clauses,
      "provisions other acts rest on", dependents by floor; crumbs = delegation chain; search
      "Art. 117 BV" opens the article in the tree; articles switch to the SR view's skyline.
- [x] Step 7′ cantonal law (`pipeline/cantonal/*.py`, `cantonal_basis.py`, decision 17): the panel of a
      cantonal act shows issuer, floor, adoption date, every basis with its clause verbatim (lazily
      loaded `ingress_k.json`, 7.7 MB), acts resting on it by floor with the delegation norm; KV panel:
      Art. 51 BV, acts by floor, KV articles other acts rest on (§/Art. as the canton writes it), the
      groups; search "PBG ZH" / "ZH PBG" / title words; deep links `#K.ZH_c700.1` (escape `_u _s _l _c`).
      Canton codes ring the outer rim; floor names right of the cone (left when the panel is open).
- [x] Step 8 immersive layer (`main.js` story block, `07_tree.py::tours`): opening sequence (once per
      browser, `slm-opening`; replay in the tour menu), three tours (Stufenbau in 7 stops; traffic:
      Art. 82 BV → SVG → VRV → SG BE → courts; building: Art. 75 BV → RPG → RPV → LaLAT GE → courts),
      descent from the Constitution along the chain of delegation, spine (left: what the selection
      rests on), scale HUD (acts in view), lenses (legend: an SR area across all floors), growth
      time-lapse ("Zeit" in the tree), the courts below the selected act (its 10 most-cited decisions,
      from the pack's `top`), focus mode (f), idle orbit, vignette. While a tour or descent runs, the
      card's free area frames the subject (`freeRect`), legend and HUD step aside (phone: toolbar too),
      and the courts appear only at their own stop. Bugs found by screenshot runs: an edge-chip
      collision loop that oscillated forever (page hang), court layers without viewport uniforms
      (screen-filling ribbons), the apex selection highlighting all 18,000 acts.
- [x] Step 9 connections (decision 21): constellation per selected act, desktop + phone (phone: smaller
      caps, toolbar steps aside while it is shown; the sheet's × brings it back). Small spheres on
      paper get more ink and a darker outline (gl.js) so uncited acts no longer vanish into the page.
- [x] Step 10 overview (decision 23): SVG view with hover (a block's flows light up), panel per block/flow
      (counts, where they rest, what rests on them, legislation/case-law partners, the acts → Stufenbau
      with constellation; "highlight in the hierarchy" = focus set in the cone); offered in the opening
      and the tour menu; phone: 920 px wide canvas that scrolls, sheet panel. The 3D loop rests while
      it is shown.
- [x] Step 5 partly: counts cross-checked with the opencaselaw MCP (BGE 143 IV 241 in-degree;
      Art. 41 OR — the MCP undercounts, see report D1); desktop + phone screenshots via Playwright.

- [x] Step 11 public site (decision 28): `pipeline/08_web.py` → `docs/data` (atlas.json, names.<lang>.json,
      links.json, hier.json, pairs.json, years.json, art/<n>.json, law/<x>.json, find.<lang>.json,
      method.json); `docs/index.html`, `style.css`, `js/` (app, data, treemap, dossier, search, hierarchy,
      matrix, method, methodtext, i18n, util). Tested at 1440×900, 1024×768 and 390×844 in DE/FR/IT/EN.
- [x] Step 12 network view (decision 29): `layout/net.mjs` (graphology 0.25.4 + graphology-layout-forceatlas2
      0.10.1) → `docs/data/net.json` (0.3 MB); `docs/js/net.js` (canvas, layer chips, ego network, labels
      with collision, pinch/wheel/keys). MIT `LICENSE`. Both previews show the public site.
- [x] Step 12′ network navigation (decision 30): routes per step, van Wijk flights, previews after a dwell, growth,
      chain as breadcrumb, moving points, brushing from panel and crumbs, keyboard, overview map; walk-throughs
      in headless Chromium at 1440×900 (DE, IT) and 390×844 (FR), no console errors.
- [x] Step 13 time view (decision 31): `pipeline/fetch_fedlex_dates.py`, `08_web.py` → `docs/data/time.json` (0.16 MB);
      `docs/js/time.js` (state, bar, chart) with hooks in treemap.js, net.js, matrix.js, app.js (hash `@year`).
- [x] Step 13′ federal history (decision 32): `pipeline/fetch_fedlex_history.py` → `data/fedlex_history.json` (11 MB);
      08 adds 11,413 acts no longer in force (repealed or lapsed; kind o, `_y`), `hnames.<lang>.json`; step 1 fix
      for acts never in force.

## Reports
- `reports/opencaselaw-anomalies.md` — anomalies in OpenCaseLaw for Jonas to fix there (duplicates,
  impossible dates, alias errors, unflagged homonyms, SR reuse, extractor issues, MCP pairing). Keep
  adding to it rather than silently working around new ones.

## Next
- Jonas: make the repository public (Settings → General → Danger Zone) and enable Pages (Settings → Pages →
  Deploy from a branch → this branch or main after merging, folder `/docs`). Pages on a private repository
  needs a paid plan and publishes the site publicly anyway.
- Time view: cantonal history (repealed cantonal acts) is not published as data by the cantons; the network and
  matrix show repealed federal acts only where courts cite them (fetching the consolidated texts of repealed acts
  would add their bases and references).
- In force without a status (found 2026-10-27, decision 32): 276 acts on Fedlex have no inForceStatus although their
  dates say in force — 252 entered into force 2024–2026 (147 federal acts, e.g. SR 122.1 Hamas-Gesetz in force
  2025-05-15, SR 745.13 FPV 2024 whose predecessor is marked repealed on 2025-02-01; 114 treaties), 21 acts of
  1875–1897 without SR number (end unknown). The map takes "in force" from status 0 (`sr_eli.csv`), so the recent ones
  are missing (unless courts cite them), and 8 numbers show the older act with status 0 beside a newer one without
  status. Fix: in force = status 0, or no status with entry into force before the run and no end, for acts since
  2000; then fetch their Ingress (basis), cross-references and structure and rerun the pipeline.
- Network: the angle inside a ring is a force-layout position (designed); a measured alternative would be
  community detection (Leiden) per canton with communities as sectors. Treaties are a dense legislative
  cluster of their own (3,304 pairs) with few links to the rest; a "law in force only" filter and a time
  slider (legislation has no time series, decision 15) are open.
- New site: row names of the hierarchy are not sticky when a phone scrolls sideways; the treemap has a
  keyboard path through the top-level tiles but not inside nested parts; cantonal acts have no subject
  grouping below the canton (their collections' numbering is not uniform: GE uses letters).
- Decision search (by docket / BGE citation) and a decision panel with its own cites/cited-by.
- PageRank as an optional authority measure (in-degree today).
- EN titles exist for 471 SR entries only (fallback DE).
- WebGL content is not screen-reader accessible; the panel, search, method dialog and the connections
  overlay (decision 21) are.
- Real-device check of the 3D page (GPU phones): headless software rendering is all that was tested.
- Legislation layer: article-level refs exist in the packs (`x`) for the article panel; the reverse
  ("which provisions of other acts name this article") needs article-precise targets, which the
  footnotes do not give (they name the act).
- Cantonal law: article-level targets for bases naming a cantonal act's article (today the act);
  read the 1,500 not identifiable mentions by hand per canton; TI/SZ from their own portals when reachable;
  communal law (BZO …) is out of scope of the cantonal collections.
- The 13 dangling bases and 79 acts without a basis are Phase-2 material (lacunae, outdated Ingress);
  so is the one genuine upward delegation of decision 26 (ZG 413.123 → § 20 of the Amt's provisions).
- The 11 inversions with a default floor (decision 26) need the issuer read in the official gazette:
  FR Tarif des émoluments administratifs 1968, ZG Richtplan 1988, SO Volksbeschluss 1898.
- Phase 2 (simplification, contradictions, lacunae) builds on `fedlex_structure.json.gz` and the
  article co-citation graph.

## Open questions for Jonas
- Public at launch, or private preview first? (Preview above is private.)
- TI and SZ come via LexFind (Institute of Federalism, academic service): only Ingress text (official,
  Art. 5 URG) and metadata are republished, links go to ti.ch / sz.ch. Acceptable for the public page?
- VD shows only the BLV's "majeur" acts (895 of 2,747); the 1,852 "mineur" decrees are left out.
