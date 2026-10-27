# Are the counts right? (2026-10-27)

Jonas: "are we sure about the number of laws, federal and cantonal? must be accurate". Two independent checks.

## Federal law: Fedlex's own pages and LexFind

Fedlex's status lags behind its own dates (decision 33, `pipeline/inforce.py`): 265 acts in force have no status yet
(nearly all since 2024), 29 marked in force carry a repeal date or an end of applicability in the past. The rule: in
force if entered into force on or before the run date, not repealed, not expired, and marked in force or without status.

- **Fedlex's web pages** ("Dieser Text ist in Kraft" / "nicht in Kraft", read in headless Chromium): all 29 "ended" acts
  show "nicht in Kraft"; 6 of 25 sampled "in force by dates" acts rendered a status in time, all "in Kraft"; 35 of 35
  agree, 0 disagree (34 pages showed no status within 25 s).
- **LexFind** (lexfind.ch, Institut du Fédéralisme; entity "Bund"): 5,339 acts active, under 5,338 SR numbers — the
  same 5,338 numbers our rule gives, none more, none less (LexFind lists SR 0.672.957.31 twice). Fedlex's raw status
  would have given 5,102.
- On the map: 2,125 federal acts and 3,187 treaties in force (5,312 SR numbers = the rule's 5,338 less the 26 cantonal
  constitutions, which sit in their cantons). Before: 2,013 + 3,098 = 5,111, of which 49 were not in force — 28 numbers
  Fedlex still marked in force after their repeal or expiry, and 21 numbers courts cite whose acts are all repealed or
  lapsed (SR 235.3 SDSG, 831.232.21 GgV, 832.103 VEZL …) — while 250 acts in force were missing (265 without status, 15
  of them already on the map because courts cite them). 5,111 − 49 + 250 = 5,312.

## Cantonal law: LexFind per canton

Active acts in LexFind's systematic trees (all 26 cantons read 2026-10-27) against ours (`data/cantonal_basis.json`).
LexFind is not independent for TI and SZ: we read them from LexFind (their own portals were unreachable / 403).

| Canton | Ours | LexFind | Diff | Explanation |
|---|---:|---:|---:|---|
| AG | 463 | 463 | 0 |  |
| AI | 421 | 421 | 0 |  |
| AR | 332 | 332 | 0 |  |
| BE | 711 | 711 | 0 |  |
| BL | 860 | 860 | 0 |  |
| BS | 982 | 982 | 0 |  |
| FR | 812 | 814 | -2 | LexFind +2: 743.0.1 Gesetz über den Wasserbau (not in the official index bdlf.fr.ch today: stale) and "18.1 Ombudsgesetz --> 181.1" (a pointer to the renumbered act, not an act). Official index: 812 = ours. |
| GE | 865 | 865 | 0 |  |
| GL | 489 | 489 | 0 |  |
| GR | 419 | 419 | 0 |  |
| JU | 855 | 855 | 0 | Was 854: RSJU links category 144 as /scripts/ (lower case), which our crawler did not follow; fixed 2026-10-27, 144.1 Ordonnance concernant l'intégration des étrangers et la lutte contre le racisme added. |
| LU | 630 | 630 | 0 |  |
| NE | 822 | 822 | 0 |  |
| NW | 401 | 401 | 0 |  |
| OW | 516 | 516 | 0 |  |
| SG | 731 | 731 | 0 |  |
| SH | 432 | 432 | 0 |  |
| SO | 539 | 539 | 0 |  |
| SZ | 426 | 430 | -4 | LexFind +4: "Gebührentarif" (a link), "Abkürzungsverzeichnis", "Alphabetisches Register", "Benützungshinweise" — no acts. |
| TG | 461 | 461 | 0 |  |
| TI | 623 | 623 | 0 |  |
| UR | 379 | 379 | 0 |  |
| VD | 895 | 900 | -5 | LexFind +5: 935.51 (2001, replaced by the LVLJAr of 2021), 221.317.1 (2014, replaced 3 June 2026) and 832.05.1 ALAM (no longer in the BLV) are stale; 931.151 (2015, 2019) are décrets the BLV classes "mineur". BLV: 895 "majeur" acts in force = ours; with its 1,852 "mineur" acts 2,747. |
| VS | 691 | 691 | 0 |  |
| ZG | 686 | 686 | 0 |  |
| ZH | 944 | 944 | 0 |  |
| **Total** | **16,385** | **16,396** | | |

22 cantons agree exactly (JU since the fix); FR, SZ, VD differ only where LexFind lists stale entries, non-acts, or VD's
"mineur" decrees. One real miss of ours (JU 144.1), fixed. Open choice: VD's 1,852 "mineur" acts (décrets and arrêtés of
the BLV, e.g. arrêtés de mise en vigueur, crédits, convocations) are not on the map; other collections hold no such class,
and LexFind does not count them either.
