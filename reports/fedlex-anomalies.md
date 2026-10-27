# Fedlex: anomalies found while reading the Ingresses (decision 35)

For Jonas to pass on to the Federal Chancellery (Fedlex) or the drafting services. Each item was read in the
consolidated XML the pipeline uses (`build/fedlex_xml_urls.json`, latest DE version before 2026-10-26). The map
works around them as stated; nothing here is corrected silently.

## Wrong or misleading markup

1. **SR 954.195.1 UEV (version of 1 January 2016)** — the Ingress names "Artikel 126, 131, 132 Absatz 3 … des
   Finanzmarktinfrastrukturgesetzes vom 19. Juni 2015 (FinfraG)", the footnote says **SR 954.1**. SR 954.1 was the
   Börsengesetz and is today the FINIG of 15 June 2018; the FinfraG is **SR 958.1**. The map follows the text
   (flag "note", Befund → "Fussnote und Text widersprechen sich").
2. **SR 131.232 Verfassung des Kantons Wallis (version of 6 March 2023)** — Art. 3 is printed
   `<b>Art. 3</b><sup>a</sup>` (the superscript is a note marker: "In der Verfassung gilt jede Bezeichnung der Person
   … für Mann oder Frau") and carries the element id **`art_3_a`**. A link to `#art_3` finds nothing; four Valais
   acts cite "Art. 3 KV". The map maps art_3 → art_3_a for this text only (`07_tree.py`).
3. **SR 173.110.210.1 (Bundesgericht, Richtlinien für die Gerichtsgebühren)** — the whole operative text ("beschliesst:
   1. Bei Streitigkeiten …") sits inside the `preamble` element, with its footnotes. The pipeline now reads every
   preamble only up to the enacting formula.
4. **SR 446.2 JSFVG (version of 1 January 2025)** — the ranges "Art. 6–8" and "Art. 21–25" appear as elements
   (`art_6_8`, `art_21_25`) with no text and no note; a reader cannot tell whether they are repealed or not yet in
   force. The map counts them as present (the JSFVV cites Art. 8 and 25).

## Found while building the law repository (decision 36, 2026-10-27)

5. **Two consultation drafts are empty files.** `eli/dl/proj/2023/20/cons_1/doc_2` (it) and
   `eli/dl/proj/2023/103/cons_1/doc_1` (it): the filestore answers HTTP 200 with 0 bytes
   (`…/it/pdf-a/fedlex-data-admin-ch-eli-dl-proj-2023-20-cons_1-doc_2-it-pdf-a.pdf`, likewise for 2023/103). Retried
   2026-10-27, same result. The repository has these drafts in DE and FR only.
6. **A consultation in the year 6020.** `eli/dl/proj/6020/55/cons_1` (Vorlage 1) — evidently a typing error for 2020 in
   the identifier. Kept as Fedlex has it.
7. **Metadata inside the act.** Some AS texts (e.g. `eli/oc/2022/325`) carry an `rdf:RDF` block (the issuing office,
   the formats docx/html/xml) directly under `akomaNtoso`, outside `meta`; others embed SVG figures with their CSS
   (`eli/oc/2026/24`, road signs). Neither is text of the act; the word check skips both.
8. **An empty heading before the real one.** AS amending acts write `<heading/><heading>Übergangsbestimmung</heading>`
   (`eli/oc/2022/776`, EnEV annexes); a reader taking the first heading loses the title. The converter joins all
   headings of an element.

## Status lagging behind the dates

See `reports/counts-check.md` and decision 33: 265 acts in force without a status, 29 marked in force although their
repeal or the end of their applicability is recorded.

## Ingresses naming provisions that no longer exist (for the drafting services)

The Befund lists them (`docs/data/check.json`, "Grundlage zeigt ins Leere"). Federal acts in force on 2026-10-26:

| Act | Names | Status in today's text |
|---|---|---|
| SR 143.5 RDV | Art. 111 AIG | repealed |
| SR 172.220.111.331, 172.220.111.332 | Art. 34a BPV | repealed |
| SR 172.220.115 PUBLICA-Personalreglement | Art. 27c BPG | repealed (Art. 27a–27c) |
| SR 211.432.21 VAV-VBS | Art. 46b VAV | not in the text |
| SR 211.435.1 EÖBV | Art. 929a OR | not in the text |
| SR 232.112.11 HasLV-WBF | Art. 9 HasLV | repealed |
| SR 322.2 MStV | Art. 27 MStP | repealed (Art. 27–29, 2018) |
| SR 734.25 VPeA | Art. 15h EleG | repealed |
| SR 784.101.113 (BAKOM) | Art. 25 VID | not in the text |
| SR 814.81 ChemRRV | Art. 63 USG | repealed |
| SR 817.023.41 HKV | Art. 63 LGV | repealed |
| SR 831.143.15 (Schiedsgericht AHV) | Art. 54 AHVG | repealed |
| SR 913.1 SVV | Art. 107a LwG | repealed |
| SR 951.312 KKV-FINMA | Art. 128 KAG | repealed (Art. 127–129) |

Fourteen federal acts name an act by the date of the earlier act under the same number (the Ingress was not updated
after a total revision), e.g. SR 235.21 and 852.12 → "Bundesgesetz vom 24. März 2000" (SR 235.2 is today the act of
18 December 2020); SR 514.10, 520.13, 523.51, 974.03 → "BZG vom 4. Oktober 2002" (today's BZG is of 20 December 2019);
SR 742.161 → "GüTG vom 25. September 2015" (today's act of 21 March 2025). Befund → "Bezeichnung nicht nachgeführt".
