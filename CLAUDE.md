# swiss-law-graph — working notes for Claude Code

## Goal
A zoomable, searchable, beautiful map of Swiss law for a general audience: SR areas →
acts → articles → decisions, with every node and edge traceable to its source. It must feel
like magic and be exact. Phase 2 (later): a tool to radically simplify the law and find
contradictions and lacunae. Owner: Jonas Hertner (also owner of opencaselaw.ch).

## Sources (public only — the page will be public)
- `data/citations.parquet` — OpenCaseLaw CC0, 9,474,505 decision→decision edges
  (`match_type`, `confidence_score`). HF `voilaj/swiss-caselaw`, snapshot 2026-10-26.
- `data/statute_references.parquet` — CC0, 12,707,001 decision→(law_code, article, paragraph).
- `data/structure.parquet` — CC0, per-decision court/language/structure flags.
- `data/cite-index-*.tsv.gz` — CC0, decision → court, canton, date (col5 = decision_id).
- `data/sr_taxonomy.csv` — Fedlex SPARQL legal taxonomy: SR tree + titles DE/FR/IT (+ some EN/RM).
- `data/sr_eli.csv` — Fedlex SR number → ELI (for links to official text).
- `data/fedlex_articles.json` — article list of each cited federal act from the current
  consolidated XML (written by `pipeline/fetch_fedlex_articles.py`).
- Alias tables live in the opencaselaw repo: `docs/data/law_codes.json`,
  `docs/api/law_aliases.json` (clone `jonashertner/opencaselaw`, pass its path to step 1).
- Do NOT use `jonashertner/opencaselaw-data` (private telemetry; its cards forbid release).

Network: HuggingFace and Fedlex were blocked from the claude.ai cloud sandbox and were
fetched from Jonas' Mac. The Mac disk is ~99 % full (12 GB free): keep large work off it.

## Decisions taken (each must be disclosed on the page's method panel)
1. Language variants collapse onto one SR number (OR = CO, BGG = LTF, EMRK = CEDH).
   The extractor emits language-specific codes; without pairing, French references vanish.
2. Regimes: one SR number can carry different acts over time; earlier acts get their own
   node `SR <n>@<regime>` because article numbering differs:
   101@1874 (aBV, cut-over 2000-01-01), 173.110@1943 (OG), 312.0@1934 (BStP),
   142.20@1931 (ANAG), 832.10@1911 (KUVG, cut 1996), 235.1@1992 (aDSG, cut 2023-09-01),
   311.0@a (StGB before the 2007 general-part revision, cut 2007-01-01), 210@a, 220@a.
   AuG/LEtr → AIG is a pure rename and is merged.
3. ZPO/CPC/StPO/CPP before 2011-01-01: cantonal procedure codes (cantonal decision →
   `<canton> <code>`; federal decision → excluded as ambiguous).
4. Cantonal homonyms (`CANTONAL_HOMONYMS` in step 1, e.g. LPA = GE procedure act, not the
   federal Animal Welfare Act): cantonal decision → cantonal act; federal → excluded.
   Unverified homonyms are excluded everywhere they are ambiguous — never guessed.
5. Unknown codes in cantonal decisions → cantonal act node `<canton> <code>` (no title yet:
   the cantonal tables carry no abbreviations).
6. Citation edges: `confidence_score` is NOT a probability — it rewards same court/canton
   and recency (see opencaselaw `search_stack/build_reference_graph.py::_citation_confidence`).
   Filtering on it would delete old and cross-jurisdiction citations. Rule: keep all match
   types, drop score < 0.5 (0.35 %, resolver-detected conflicts), dedupe (source,target)
   pairs (370,207 duplicates), flag `bge_pincite` edges as inferred.
7. Article validation: an article node exists only if the article exists in the act's
   current Fedlex text; others go to a per-act "not found in current text" bucket
   (catches extraction noise like "Art. 429 CP", and VD's transitional old CPC 2011–2013:
   cantonal decision + article absent from federal ZPO → cantonal code).
8. Every number shown is computed, not estimated; every node links to its source
   (decisions: `https://mcp.opencaselaw.ch/entscheid/<urlencoded id>`; acts: Fedlex ELI).
9. Co-citation edges between acts/articles must be significance-filtered (lift, minimum
   count, top-k per node) — raw counts make BGG/ZPO connect to everything.
10. Labels must say exactly what is measured: "most-cited decisions referring to this
    article", never "leading case on this article".

## Pipeline status
- [x] `pipeline/01_resolve.py <opencaselaw path>` → build/refs.parquet, build/meta.parquet,
      build/resolution_report.json. 97.9 % of references resolve to an act; rest counted.
- [x] `pipeline/fetch_fedlex_articles.py` (stdlib only, ~12 min, needs Fedlex access):
      826/830 acts have article lists. NOTE: the committed data/fedlex_articles.json was made
      before a parser fix and has glued suffixes ("4aufgehoben", "197angenommen"). Rerun the
      fetcher (fixed), or normalise with `^(\d+)([a-z]?(bis|ter|quater|…)?)` before use.
      Acts carry transitional/final-provision articles that restart numbering (OR, ZGB):
      treat the list as a set of valid numbers, not as order.
- [ ] Apply article validation (decision 7).
- [ ] Step 2: graph layers — areas (SR tree), acts, articles, decisions; per-year counts
      for a time slider; co-citation edges; decision citation edges.
- [ ] Step 3: layout — circle packing following the official SR tree (position = place in
      the SR, not a force layout); articles ordered by number inside each act; curved arcs
      for connections. Authority = incoming citations (PageRank optional).
- [ ] Step 4: WebGL page (sigma.js/graphology or deck.gl), semantic zoom, instant search,
      DE/FR/IT/EN, method panel with every exclusion count, works at phone width.
      Decision layer loaded on demand in shards.
- [ ] Step 5: verify counts against the opencaselaw MCP, view on desktop and phone.

## Open questions for Jonas
- Public at launch, or private preview first?
- Cantonal acts: titles need a cantonal abbreviation table (does not exist yet; opencaselaw
  issue #74 notes cantonal abbreviations collide across cantons → key as `ZH_PBG`).
