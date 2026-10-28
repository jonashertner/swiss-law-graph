# OpenCaseLaw — anomalies found while building swiss-law-graph

Snapshot examined: HF `voilaj/swiss-caselaw` 2026-10-26 (`citations.parquet`,
`statute_references.parquet`, `structure.parquet`), `cite-index-2026-10-25-42b9b98a.tsv.gz`,
`docs/data/law_codes.json` (generated 2026-08-18), `docs/api/law_aliases.json`.
Every number below is computed from those files; "not-found share" = share of references
whose article number does not exist in the act's consolidated Fedlex text (2026-10-26).
Reproduce with the swiss-law-graph pipeline (`pipeline/01_resolve.py`, `02_validate.py`).
Ordered by impact. Each item says how the map handles it meanwhile.

---

## A. Decision records (corpus)

### A1. The same judgment is held twice: BGE + BGer docket version — 5,812 pairs
`bge_*` and `bger_*` records with the same docket label are one judgment, e.g.
`bger_2C_276_2011` = `bge_137 II 393`, `bger_2C_302_2023` = `bge_151 I 187`.
5,796 of the 5,812 pairs carry statute references on **both** records, so any count of
"decisions citing article X" counts these judgments twice. Citations are split between
the two ids: the pairs receive 2,733,265 citations on the BGE side and 159,374 on the BGer side.
*Suggested fix:* expose a canonical id (or a `same_as` link) and attach statute references once.
*Map:* merged onto the BGE id; citation pairs deduplicated after the merge.
*Live service:* the MCP already collapses duplicate representations in search results (the nightly
representation manifest, ~140k rows: GE procedure/decision numbers, VD dual scrapes, SH twin courts;
and the BGE dual-id fold `bge_` / `bge_BGE_`, `tests/test_bge_twin_fold.py`). Both are link-only and
do not reach the CC0 export, which carries no `bge_BGE_` ids. Whether the manifest also links the
BGE/BGer docket pairs of A1 was not checked.

### A2. Other duplicate records — 185
Same label, same date, same canton, two ids: `be_weitere` ↔ `be_direktionen` 173
(e.g. `be_weitere_2022.GSI.1106`), `tg_obergericht` ↔ `tg_gerichte` 10
(`tg_obergericht_RBOG_2004_Nr._19` = `tg_gerichte_BR.2004.66`), `sg_publikationen` ↔
`sg_gerichte` 1, `zg_obergericht` ↔ `zg_kantonsgericht` 1.

### A3. Impossible decision dates — 14,645 decisions dated more than a year before their own docket year
| court | decisions |
|---|---|
| ge_gerichte | 3,832 |
| ch_vb | 1,468 |
| ne_gerichte | 1,389 |
| ti_gerichte | 1,304 |
| zh_verwaltungsgericht | 1,104 |
| so_gerichte | 603 |
| zh_sozialversicherungsgericht | 595 |
| ar_gerichte | 556 |
| bs_appellationsgericht | 540 |
| bl_gerichte | 390 |
| sg_versicherungsgericht | 388 |
| vd_findinfo | 345 |

Examples: `ge_gerichte_ATA_57_2002` dated 1987-02-02; `ge_gerichte_ATAS_397_2007` 1999-03-15;
`zh_verwaltungsgericht__VB.2021.00057` 2007-06-22; `ur_gerichte_2023_OG_V_22_15` 1905-01-01
(looks like a placeholder). In **2,423** cases the wrong date is frozen into the decision id itself
(`ti_gerichte_15.2023.88_d20180315`, `ne_gerichte_CPEN.2021.15_d20080905`): the date was
mis-extracted at ingestion (probably a date quoted in the text, e.g. the contested decision).
Also: 1 future date (`fr_gerichte_605 2025 140` → 2027-07-27); 2,683 decisions without a date
(ti_gerichte 831, gr_gerichte 805, mkg 542, hudoc_ch 252).
Why it matters beyond display: anything that depends on the date (which edition of a law
a citation means, time series) goes wrong.
*Map:* such dates are treated as unknown (no year shown); act assignment uses 1 January
of the docket year.

### A4. Federal decisions inside cantonal collections — 34
`ge_gerichte` 31 (e.g. `ge_gerichte_4A_427_2007`, `ge_gerichte_119 II 36`), `ag_gerichte_2P.176_2002`,
one each in `zh_gerichte` and `ag_verwaltungsgericht`; 21 of them also exist as `bger`/`bge` records.

### A5. OCR-garbage labels in `ch_vb` — 2,658
e.g. `'11U16,,,,,LLLIY`, `( IIIIILL@0`, `(ART. 11 2` (with ids derived from them).

### A6. `statute_references.mention_count` is 1 on all 12,707,001 rows
The field carries no information (one row per decision × code × article × paragraph).

---

## B. Law-code alias tables

### B1. Wrong alias: `OPC` → SR 281.41; it is the OPC-AVS/AI, SR 831.301
8,002 references. Not-found share against 281.41: **69.1 %**; against 831.301: **0.4 %**.

### B2. Cantonal homonyms mapped unconditionally to a federal act
In cantonal decisions these codes name the canton's own act; `alias_to_sr` sends them to a
federal act. Not-found share of the cited articles in the federal act, by deciding canton:

| code | federal act | cantonal decisions (not-found share) | federal courts |
|---|---|---|---|
| StG | 641.10 Stamp Duty Act | BE 4,197 (81.9 %), SG 3,387 (69.6 %), GR 1,685 (56.9 %), AR 969 (66.2 %), OW 732 (62.6 %), NW 566 (76.3 %) | 1,998 (42.7 %) |
| PBG | 745.1 Personenbeförderungsgesetz | SG 2,464 (80.5 %), NW 311 (44.4 %) | 472 (17.4 %) |
| LAF | 836.1 | VD 1,204 (90.0 %), TI 1,892 (75.6 %), GE 2,479 (47.1 %) | — |
| LC | 823.11 | BE 444 (61.3 %), VD 927 (47.0 %), VS 581 (45.3 %) | 437 (37.3 %) |
| LPers | 172.220.1 | FR 482 (57.5 %), VD 1,883 (25.7 %) | 3,181 (3.5 %) |
| PG | 783.0 Postgesetz | BE 658 (48.3 %) | 1,330 (7.2 %) |
| LAS | 851.1 | TI 3,566 (20.9 %) | — |

The federal-court share shows the same codes are partly cantonal there too (StG 42.7 %).
*Map:* added to the cantonal-homonym list (cantonal decision → `<canton> <code>`, federal → excluded).

### B3. `KLV` listed as shared between 814.310.1 and 832.112.31 — a case collision, resolvable by date
KLV = Krankenpflege-Leistungsverordnung (832.112.31, since 1996); KlV = Klimaschutzverordnung
(814.310.1, in force 2025-01-01). 4,806 references; not-found share 0.3 % against 832.112.31,
30.5 % against 814.310.1. Every decision before 2025 can only mean 832.112.31.
*Map:* KLV → 832.112.31 for decisions before 2025-01-01, excluded after.

### B4. One SR number, several acts — 412 of the 830 cited SR numbers
Fedlex lists more than one act (total revision or replacement) under 412 cited SR numbers.
`alias_to_sr` resolves to the SR number only, so references to the earlier act land on the
current one wherever both share the abbreviation. Largest cases by references dated before
the current act's entry into force: ELG 1965/2006 (831.30), MWSTV 1994/2009, MWSTG 1999/2009,
VEV 2008/2018 (142.204), OHG 1991/2007, BüG 1952/2014, RTVG 1991/2006, BöB 1994/2019,
VGKE 2006/2008, AsylG 1979/1998, ZG 1925/2005, HRegV 1937/2007, GRN 1990/2003.
`law_aliases.json` already models this for 9 acts (`former`, `as_of_hint`).
*Suggested fix:* key the alias tables to the Fedlex act (ELI) with its validity dates; mark codes
borne by both editions (ELG, AsylG, MWSTG, BüG) so consumers resolve them by date.
*Map:* generic rule from Fedlex dates and short titles (code borne only by the earlier act →
that act; shared code → act in force on the decision date; code only the current act bears →
current act).

### B5. Missing aliases for repealed acts (Fedlex has the short title) — 232 found
Examples, with distinct decision–article references (elsewhere "refs" = rows of
`statute_references.parquet`): `SGG`/`LTPF` (Strafgerichtsgesetz 2002, 173.71; 1,980 refs),
`GestG`/`LFors`/`LForo` (Gerichtsstandsgesetz 2000, now under 272; 1,643), `BEHG`/`LBVM`
(Börsengesetz 1995, 954.1; 1,171), `ANAV`/`RSEE`/`ODDS` (1949, 142.201; 1,521), `LMV` 1995,
`VEP` 2001, `VDSG`/`OLPD` 1993, `AFG` 1994, `BEHV`/`OBVM` 1996, `MWSTGV`/`OLTVA`/`OLIVA` 2000.
Former-edition codes missing like `aMWSTG`: `aLTVA` (806 refs), `aLIVA`.
Nine Fedlex short titles collide with established usage and must **not** be added:
`LAG`, `LAJ` (cantonal legal-aid acts in TI / VD-VS-NE), `OASI` (Italian AsylV), `TVA` (VAT in
French), `ALV` (unemployment insurance), `OOA`, `OGF`, `OAJ`, `BCO`.

### B6. High-volume unresolved codes — identity to verify
| code | refs | evidence | likely |
|---|---|---|---|
| `ASYLV` / `OA` / `OASI` | 10,355 / 9,301 / 1,414 | top articles 29a, 32, 1a, 10 | AsylV 1/2/3 (OA 1, OAsi 1) — **the extractor drops the ordinance number** |
| `BVV`, `OPP` | 3,390 / — | articles 1j, 27h | BVV 2 / OPP 2 (number dropped) |
| `GEBV` | 11,325 | articles 61, 62, 48 | GebV SchKG ("SchKG" dropped) — but ZH also has a GebV des Obergerichts: ambiguous |
| `OLE` | 5,122 | articles 13, 8, 36 | Ordonnance limitant le nombre des étrangers (BVO, repealed 2008) |
| `SBG` | 1,348 | articles 3, 56, 57 | Spielbankengesetz 1998 (935.52)? |
| `TESTV` | 972 | BVGer only | ? |
| `TS`, `VO`, `BG`, `EG` | 3,193 / 4,253 / … | generic | not identifiable |
| `BGE` | 997 | — | a decision citation emitted as a law code |

### B7. Upper-casing destroys the "a" edition prefix
The extractor upper-cases codes, so `aZG` (Zollgesetz 1925) becomes `AZG` = Arbeitszeitgesetz.
`AZG`: 1,128 refs, not-found share 43.4 % against 822.21, 1.1 % against the customs act; BVGer
2007–2013 customs cases. Same pattern: `AWG` (47.1 % vs 1.7 % against the Waffengesetz), `ASTG`, `ASTV`.
*Suggested fix:* keep the original case of the code or emit an `edition` flag.
*Map:* excluded as ambiguous.

### B7b. Article numbers glued onto the code — 2,113 distinct codes
`BV8`, `ZGB8`, `LPGA1`, `RPG1`, `ZPO1`, `KV9`: a known code followed directly by an article number,
emitted as the law code (the article column then holds something else). In cantonal decisions such
a code looks like an unknown cantonal act. *Map:* excluded as extraction artifacts.

### B8. Codes cantonal courts use that are not cantonal acts
A consumer that reads "unknown code in a cantonal decision" as a cantonal act creates fake
acts in up to 24 cantons: `GEBV` (20 cantons), `BVV` (21), `VO` (21), `EG` (22), `SIA` (24),
`BG` (13), `OPP`, `AI`, `CF`, `PP`, `ALAI`/`ALAVS` (former editions), `ALPC` (typo for ALCP),
`TIT` (from "tit. fin. CC"), `CLAH` (Hague conventions), `CCT` (collective labour agreements),
`CGA` (insurance terms), `VOSTRA`, `SIS`, `DNA` (federal ordinances/acts).
*Map:* excluded as "not a cantonal act" (66,780 references).

---

### B9. `KV` → SR 131.212 (Constitution of Bern) for every canton
`docs/data/law_codes.json` has `alias_to_sr["KV"] = "131.212"` and lists `KV` among the federal
abbreviations. "KV" is the generic abbreviation of *any* cantonal constitution (Bern's and
Aargau's official short titles both use it). In the snapshot, 2,959 decisions cite "KV" and were
all attributed to Bern; only 464 come from Bern. ZH 608, OW 350, GR 189, SG 156, SH 95, AR 70,
SO 61, UR 54, GL 42, NW 31, … and 746 federal decisions (ambiguous). The same holds for Bern's
French and Italian abbreviations: "ConstC" and "CostC" (5 GR decisions).
Codes naming the canton are not mapped at all: "KV/ZH" (248 decisions), "KV/BE" (145), "KV/GR",
"KV/SO", "KV/SG", "KV/SH", "KV/GL", "KV/OW", "KV/FR", "KV/AR", "Cst/VD" (48), "Cst/GE" (17), ….
*Suggested fix:* treat `KV`, `ConstC`, `CstC`, `CostC` as cantonal-constitution homonyms (a
cantonal decision → its own canton's constitution, SR 131.2xx; a federal decision → ambiguous)
and map `KV/<canton>`, `Cst/<canton>` to that canton's SR number. The MCP language pairing
(D1 fix) inherits the error: `KV` expands to Bern's `ConstC`/`CostC`.
*Map:* done as above (2,924 decisions now resolve to the right constitution: ZH 831, BE 628,
OW 364, GR 242, SG 188, …).

## D. MCP tools (checked live on 2026-10-26)

### D1. `analyze_legal_trend` does not pair language variants of a law code
`analyze_legal_trend(law_code="OR", article="41")` returns **3,734** decisions; the snapshot has
3,737 decisions citing "OR 41" — and another **6,837** citing "CO 41" (French and Italian: VD 2,087,
BGer 1,994, GE 1,721, TI 338, …). `law_code="CO"` counts those separately (728 since 2025, matching the
snapshot's 724). Asked for Art. 41 OR, a German-speaking user gets about a third of the answer;
the union is 10,503 decisions (10,424 after merging BGE/BGer duplicates and adding the other
alias spellings). This is the pairing problem `law_codes.json` itself warns about ("_why").
Worth checking `find_leading_cases(law_code=…)` and every other tool that filters by `law_code`.
*Status:* fixed on opencaselaw branch `claude/law-code-language-pairing` (commit e178afe; not merged,
not deployed). `_law_code_variants` expands a code to its language variants from `law_codes.json`
(federal entries only; cantonal homonyms such as LPA, StG, VRP stay alone) and is applied in
`analyze_legal_trend` (which now also reports `law_codes_counted`), `find_leading_cases`, its statute
fallback and the graph statute search. A decision citing both OR and CO counts once.
Tests: `tests/test_law_code_language_pairing.py` (5).

### D2. The future-dated decision shows in `get_statistics`
`by_year` contains `"2027": 1` — the `fr_gerichte_605 2025 140` record of A3.

### D3. Citation counts agree
`find_citations("bge_143 IV 241", incoming, min_confidence 0.5)`: 9,086 live; the snapshot gives
8,925 direct + 48 via the BGer twin (A1) → 8,949 after merging. The difference is the live graph's growth.

## E. Cantonal law collections (found while reading all 26 collections, 2026-10-26)

### E1. `scrapers/cantonal_laws/zh.py` enumerates at most 150 ZH acts, page 1 twice — ZH has 944 in force
The zh.ch listing endpoint (`…/lawcollectionsearch_312548694.zhweb-zhlex-ls.zhweb-cache.json`) answers
`"numberOfResults": 150` without a filter: it caps the result, it does not count the collection. The scraper
starts at `page=0`, sends no `page` parameter for it, and the endpoint treats that as page 1 (checked live:
identical 15 numbers `101, 111.1, 111.2 …`); it then stops when 150 rows were seen. So one run yields at most
~135 distinct acts of 944. Fix (what `swiss-law-graph/pipeline/cantonal/zh.py` does): query each LS folder
with `fileNumber=1..14` (each below 150), start at `page=1`. LexFind's active ZH set has the same 944 numbers.
Whether the LexFind fallback in `cantonal_laws.db` covers the gap is not checked here.

### E2. Cantonal language variants are not paired — 119 code pairs
Same problem as D1, for cantonal acts: bilingual cantons' acts are cited under two codes, counted apart.
`FR CPJA` (3,179 decisions) = `FR VRG` (865) = BDLF 150.1; `BE VRPG` (11,801) = `BE LPJA` (810) = BSG 155.21;
`VS LPJA` = `VS VVRG` = RS/VS 172.6; also variant spellings (`VD LPA` 56,664, `LPA/VD` 10, `LPAVD` 8).
The LexWork header of each act carries the abbreviation in every published language (`<h2 class='abbreviation'>`
per language in `show_as_json`), which gives the pairs exactly. On the map the union is counted (distinct
decisions: FR 150.1 → 4,035, not 4,044).

### E3. 2,599 cantonal codes in decisions have no act in force in the canton's collection — 142,706 decisions
Mostly repealed acts: the cantonal procedure codes before 2011 (`TI CPC` 8,255, `VD CPC` 7,361, `TI CPP`
6,681, `VD CPP`, `GR ZPO`, `NE CPP` …), `VD LJPA` (2009), `TI PAMM`, `NE LPJA` (replaced by the LPA of 18 March
2025), `GE LIASI` (replaced 2025); communal regulations (`ZH BZO` 845); codes the canton itself never states.
A lookup by abbreviation against today's collection must not resolve these to a current act; like federal
law (B4), cantonal codes need the decision date. Full list: `site/data/tree.json`, nodes with `"cited": 1`.

### E4. VD: one systematic number, several acts — 176 numbers
The BLV files a law's "Arrêté de mise en vigueur", convocation and credit decrees under the law's own number:
173.36 = LPA-VD + 2 arrêtés de mise en vigueur; 101.01 = the Constitution + 5 decrees. A table keyed on
(canton, sr_number) keeps one of them — in our first run, the arrêté instead of the LPA-VD. Key on the act
id (BLV `id`), or keep the "majeur" act (the BLV's own `importance` field) under the number.

### E5. Federal footnotes in cantonal Ingresses that point past a repealed law — 459 bases
A cantonal Ingress cites a federal law by its old date while the footnote gives today's SR number of its
successor ("Bundesgesetz über Lebensmittel … vom 9. Oktober 1992", footnote SR 817.0 = LMG of 20 June 2014).
The canton's text is outdated, not opencaselaw; listed here because a citation resolver that trusts the
footnote alone lands on the successor. Flagged `"old"` in `data/cantonal_basis.json`.

## F. Snapshots on Hugging Face (found by the weekly refresh, 2026-10-28)

### F1. Obwalden: three published series missing from the export of 2026-10-26
`structure/structure.parquet` and `graph/statute_references.parquet` of `voilaj/swiss-caselaw` (night of 2026-10-26)
hold 2,192 Obwalden decisions against 3,460 the night before. Whole series are gone (decision id prefix
`ow_gerichte_<series>_`; structure / decisions with a statute reference, before → after):

| Series | structure | statute references |
|---|---|---|
| VVGE (Verwaltungs- und Verwaltungsgerichtsentscheide) | 732 → 0 | 598 → 0 |
| AbR (Amtsbericht über die Rechtspflege) | 441 → 0 | 398 → 0 |
| OGVE | 32 → 1 | 25 → 1 |
| without a series prefix | 2,255 → 2,191 | 2,205 → 2,141 |

The cite index of the same night still lists all 3,473 Obwalden decisions, so the export is partial, not the corpus.
In the atlas, 1,081 Obwalden decisions would have lost every reference (the canton's tile 1,946 → 1,495 decisions).
`pipeline/fetch_opencaselaw.py` now refuses a snapshot in which a court with ≥ 200 decisions loses more than 10 % and
keeps the previous one whole.

### F2. New court groups carry canton codes that are not cantons
Since 2026-10-26 the cite index has `EU` (`cjeu`, 5,618 decisions) and `UN` (`icj`, `untb_*`, `unwgad`, 10,786) in the
canton column, beside `CH` and `CE`. A consumer that reads every value other than CH and CE as a canton (as this atlas
did: CJEU "AEUV" became a cantonal act "EU AEUV") breaks. The dataset card should list the values of the column.

### F3. The statute extractor runs on CJEU texts in translation
In CJEU judgments (German and French versions) the extractor emits Swiss abbreviations for the law of the state
concerned and German words as codes. Read from the codes and articles, not from the texts:
- **Swiss abbreviations, foreign law:** `CPC` (C-354/15 Art. 188–230; C-70/15), `ZPO` (C-467/16), `AO` (C-396/98,
  C-151/94), `MWSTG` (C-203/10, C-16/14, C-108/17), `ASYLG` (62023CJ0123), `ZGB` (C-604/19 Art. 233–238), `ZSV`
  (62023CJ0313), `LEC` (C-413/12), `WFV`, `ENG`, `LNM`, `WAV`, `OM`, `ON`. They resolve to SR 272, 210, 641.20 … in a
  Swiss reading. The ECtHR set has the same problem in two judgments (`CPC` in 27756/05, `CST` Art. 10a in 68537/13).
  The atlas now counts international courts for treaties (SR 0.…) only.
- **Words as codes:** `NR` 1,112 references in 814 decisions ("Nr."), `BUCHSTABE` 141, `DIESER` 60, `DIESES`,
  `UNTERABSATZ`, `GENANNTEN`, `TEIL`, `AUF`, `BESTIMMT`.
Treaties the CJEU applies are cited correctly (EMRK 62 decisions, CMR 6, FZA 3, CISG 1).

---

## C. Not an error, but worth documenting in the dataset card
- `confidence_score` (citations) rewards same court/canton and recency; it is not a probability
  of correctness. Filtering on it removes old and cross-jurisdiction citations.
- Fedlex XML splits digits across tags (`<b>Art. 25</b><b>7</b>` = Art. 257): any parser that
  replaces tags with spaces loses articles. (Relevant if opencaselaw parses Fedlex XML.)
