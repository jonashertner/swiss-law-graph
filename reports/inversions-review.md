# The 109 inversions, read (2026-10-27)

**What was checked.** The matrix (decision 25) listed 109 stated bases whose target sits on a *lower*
floor of the Stufenbau than the act naming it. I read each one in its Ingress, together with the
footnotes and the issuer of the target.

**Result.**

| | pairs |
|---|---:|
| Listed before the review | 109 |
| … our errors, now fixed: floor of the act or target wrong | 45 |
| … our errors, now fixed: basis misread | 17 |
| … genuine readings, kept | 47 |
| Newly exposed by the floor fixes (agreements now on floor 5) | 8 |
| **Lower-floor bases after the review** | **55** |
| … after decision 27 (acts of intercantonal bodies on floor 5; UR 20.2715 → ZBSA rules no longer lower) | **54** |

Of the 55, **one** inverts the delegation (ZG 413.123). The other 54 are structural. They are preamble
lists, agreements naming each party's norm, approvals and successor numbers, plus 12 whose floor is
only a default.

## Fixes (pipeline/cantonal_basis.py)

**Floors (45 pairs).**

- Agreements take their floor from their parties (`agreement_floor`): title before the topic plus the
  Ingress head.
  - Two or more cantons, the Confederation, a foreign state or the Holy See → 5.
  - Church bodies only → 7.
  - Communes or companies only → 7.
  - The canton with communes, a church or a private party → 6 (5 if its parliament is the party, 7 if a
    department is).
- Before, "Zentralschweizer Fachhochschul-Vereinbarung", "Geldspielkonkordat", VD's "CONVENTION", the
  NE–JU data-protection convention, the Vierwaldstättersee and Zürichsee agreements and the
  Franco-Swiss airport treaty sat on floor 7.
- A "Konferenz" is intercantonal only with a cantonal word. "Mittelschulkonferenz des Kantons
  Solothurn", "Präsidialkonferenz der Regionalgerichte" (GR) and "Conférence des préfets" (FR) had
  been on 5.
- Acts of church bodies by title → 7. The Thurgau synod's and church council's ordinances had been on 6.
- Parliaments not recognised before: "LE CONSEIL REPRÉSENTATIF" (GE), "I CONSIGLI DEL CANTONE" and
  "GRAN CONSGLIO" (TI). "Landsgemeindebeschluss" → 5. "Präambel" is no issuer.

**Readings (17 pairs).**

- UR prints "durch Verweis veröffentlicht" where the Ingress would be. That is an editorial note,
  not a basis: 6 intercantonal agreements had "rested" on UR's Publikationsreglement.
- VD's "Note :" inside an Ingress.
- Text after the enacting formula is not read: SG prints its footnote apparatus there, BS its recitals.
- A footnote with another canton's collection number, or a designation naming another canton, is
  "another canton's act" (new target kind `X:`, 184 bases), never the own canton's act.
  - Example: SH 817.002 had read the AI and AR footnotes as SH's lottery-fund ordinance.
- The only act of a date needs an agreeing title word.
  - Example: BL 915.111 had matched a BS ordinance to BL's language-promotion ordinance of the same date.
- A footnote of another type than the text's act of that date yields to the text.

**Found on the way.**

- LU numbers with a letter suffix ("SRL Nr. 539c") were cut to "539". Every such footnote had pointed
  at a different act (58 LU acts).
- ZH footnotes without prefix ("414.11.") were not read.

**Checks.**

- Diff against the run before: 147 changed cantonal targets, sample 40/40 corrections.
- 37 former matches became "?". I read all 37: 34 had been wrong; the other 3 are restored.
- 329 floor changes, all read by group.
- Unresolved bases went from 1,893 to 1,979. Most of the rise is the 184 bases now marked as
  another canton's act.

## Errors in the official collections (for the cantons)

- **NE 991** (Loi sur l'aide humanitaire): note 2 gives RSN 601.80 (RELSub). The text cites "la loi
  sur les subventions, du 1er février 1999", which is RSN 601.8.
- **SH 500.102**: note 2 gives SHR 500.101 (the Verordnung). The text cites the
  Bevölkerungsschutzgesetz of 22 August 2016, which is SHR 500.100.
- **SO 625.711** (fishing agreement BE–SO): notes 4 and 5 give "BGS 923.11" and "BGS 923.111" for
  the Bernese Fischereigesetz and Fischereiverordnung. Those are BSG numbers; SO's own prefix was used.
- 53 footnotes in all give another act than the text names (flag "note"; the text prevails). Most are
  BE footnotes that give the approval decree's number for the agreement itself. That is BE's filing
  convention, not an error.

## The 55, by group


### Lower act expressly stated as basis (1)

A lower act stated as the basis ("gestützt auf"): the delegation chain runs upwards. Phase-2 material.

- **ZG 413.123 — Verordnung betreffend die Entschädigung für Experten- und Referententätigkeit in der Berufsbildung** → ZG 413.112 — Ausführungsbestimmungen 2 zum Einführungsgesetz Berufsbildung (Regelung des Qualifikationsverfahrens).
  The Regierungsrat's ordinance on fees for examiners rests "gestützt auf" § 20 of the Ausführungsbestimmungen 2 zum EG Berufsbildung, issued by the Amt für Berufsbildung. A government ordinance resting on an office's provisions inverts the chain, unless § 20 only refers back to the government. Read § 20.

### Floor of the act named unknown (11)

The target's floor is not stated: the collection gives no issuer and the title says nothing, so floor 7 is a default, not a finding. Read by hand, the inversion may disappear.

- **SR 414.110.12** → SR 414.110.1.
  Agreement of the Federal Council and the Zurich government executing Art. 6 Ziff. III of the 1905 Aussonderungsvertrag; that contract was approved by the Federal Assembly (SR 414.110.11) and sits on floor 3 by its title only.
- **ZG 1021.018 — Kantonsratsbeschluss betreffend einen Objektkredit Kostenbeteiligung Erdverkabelung auf dem Trassee zwischen den Unterwerken Sins und Langacher** → ZG 711.31 — Kantonaler Richtplan, Richtplantext.
  Names chapter E 15.2.1 of the cantonal Richtplan of 1 September 1988. The collection states no issuer for the Richtplan; floor 7 is the default.
- **ZG 1021.020 — Kantonsratsbeschluss betreffend Objektkredit für Soft-Massnahmen zur Förderung des Velofahrens** → ZG 711.31 — Kantonaler Richtplan, Richtplantext.
  Names the cantonal Richtplan of 1 September 1988. The collection states no issuer for it; floor 7 is the default.
- **FR 122.28.16 — Ordonnance fixant les émoluments du Service de la mobilité** → FR 126.21 — Tarif des émoluments administratifs.
  Names the Tarif des émoluments administratifs of 9 January 1968. The collection publishes no Ingress and no issuer; floor 7 is the default. If the Conseil d'Etat issued it, it shares the floor of the ordinances citing it.
- **FR 122.28.56 — Ordonnance fixant les émoluments du Service des ponts et chaussées** → FR 126.21 — Tarif des émoluments administratifs.
  As above (Tarif of 9 January 1968, issuer not stated).
- **FR 482.13 — Ordonnance fixant le tarif des émoluments dans les domaines de la protection des biens culturels et de l'archéologie** → FR 126.21 — Tarif des émoluments administratifs.
  As above (Tarif of 9 January 1968, issuer not stated).
- **FR 710.16 — Ordonnance fixant le tarif des émoluments et des frais de procédure dans le domaine de l'aménagement du territoire et des constructions** → FR 126.21 — Tarif des émoluments administratifs.
  As above ("l'article 5 du tarif du 9 janvier 1968").
- **FR 721.0.16 — Ordonnance fixant les émoluments du Service des forêts et de la nature** → FR 126.21 — Tarif des émoluments administratifs.
  As above (Tarif of 9 January 1968, issuer not stated).
- **FR 864.1.16 — Arrêté fixant les émoluments administratifs pour les autorisations et approbations données en application de la législation sur le travail dans l'industrie, l'artisanat et le commerce** → FR 126.21 — Tarif des émoluments administratifs.
  As above (Tarif of 9 January 1968, issuer not stated).
- **SO 735.441 — Staatliche Beteiligung an der Strassenbahn Niederbipp-Solothurn** → SO 735.421 — Staatliche Beteiligung an der Eisenbahnunternehmung Solothurn- Münster (Weissenstein-Bahn).
  The citing clause calls the target a "Volksbeschluss" of 13 November 1898, a decision of the people (floor 5). The collection publishes no Ingress for it, so the pipeline cannot see that; on floor 5 the inversion disappears.
- **SO 735.451 — Staatliche Beteiligung an der Weiterführung der Birsigtalbahn von Flüh bis Rodersdorf** → SO 735.421 — Staatliche Beteiligung an der Eisenbahnunternehmung Solothurn- Münster (Weissenstein-Bahn).
  As above (Volksbeschluss of 13 November 1898).

### Agreement names a party's own norm (15)

An agreement names a party's own norm: agreements sit on floor 5 (or 6 for the canton with communes) whoever concluded them (decision 17), while the norm that empowers a concluding government or commune lies lower. Not an inversion of validity.

- **BE 923.919.1 — Vereinbarung zwischen den Kantonen Bern und Freiburg betreffend die Fischerei in den Grenzgewässern der Sense und Saane** → BE 923.111 — Verordnung über die Fischerei.
  BE–FR fishing agreement; names the Bernese Fischereiverordnung, which empowers the Bernese authority to conclude it.
- **BE 923.921.1 — Vereinbarung zwischen den Kantonen Bern und Solothurn betreffend die Fischerei in den Grenzgewässern der Aare** → BE 923.111 — Verordnung über die Fischerei.
  BE–SO fishing agreement; names Art. 3 Abs. 2 of the Bernese Fischereiverordnung (competence to conclude).
- **BE 923.933.1 — Vereinbarung zwischen den Kantonen Bern und Neuenburg betreffend die Fischerei im Grenzgewässer des Zihlkanals** → BE 923.111 — Verordnung über die Fischerei.
  BE–NE fishing agreement; names Art. 3 Abs. 2 of the Bernese Fischereiverordnung (competence to conclude).
- **BE 923.941.1-1 — Vereinbarung zwischen den Kantonen Bern und Jura über die Fischerei im interkantonalen Abschnitt der Birs** → BE 923.111 — Verordnung über die Fischerei.
  BE–JU agreement on the Birs; names Art. 8 Abs. 1 lit. d of the Bernese Fischereiverordnung (competence to conclude).
- **BS 890.800 — Vertrag zwischen dem Kanton Basel-Stadt und den Gemeinden Bettingen und Riehen betreffend die Aufgabenteilung im Bereich Asyl** → BS RiE 111.100 — Gemeindeordnung der Einwohnergemeinde Riehen.
  Contract canton–communes on asylum; names § 21 Abs. 3 lit. i of the Gemeindeordnung of Riehen, which empowers the communal council to conclude it.
- **BS 890.800 — Vertrag zwischen dem Kanton Basel-Stadt und den Gemeinden Bettingen und Riehen betreffend die Aufgabenteilung im Bereich Asyl** → BS BeE 111.100 — Gemeindeordnung der Einwohnergemeinde Bettingen.
  As above; names § 12 Abs. 1 Ziff. 5 of the Gemeindeordnung of Bettingen.
- **BS BeE 890.800 — Vertrag zwischen dem Kanton Basel-Stadt und den Gemeinden Bettingen und Riehen betreffend die Aufgabenteilung im Bereich Asyl** → BS RiE 111.100 — Gemeindeordnung der Einwohnergemeinde Riehen.
  The same contract in Bettingen's collection.
- **BS BeE 890.800 — Vertrag zwischen dem Kanton Basel-Stadt und den Gemeinden Bettingen und Riehen betreffend die Aufgabenteilung im Bereich Asyl** → BS BeE 111.100 — Gemeindeordnung der Einwohnergemeinde Bettingen.
  The same contract in Bettingen's collection.
- **BS RiE 890.800 — Vertrag zwischen dem Kanton Basel-Stadt und den Gemeinden Bettingen und Riehen betreffend die Aufgabenteilung im Bereich Asyl** → BS RiE 111.100 — Gemeindeordnung der Einwohnergemeinde Riehen.
  The same contract in Riehen's collection.
- **BS RiE 890.800 — Vertrag zwischen dem Kanton Basel-Stadt und den Gemeinden Bettingen und Riehen betreffend die Aufgabenteilung im Bereich Asyl** → BS BeE 111.100 — Gemeindeordnung der Einwohnergemeinde Bettingen.
  The same contract in Riehen's collection.
- **BS 952.570 — Vereinbarung zwischen den Kantonen Basel-Landschaft und Basel-Stadt über die gemeinsame Ausgabe von Gewerbeparkkarten** → BS 952.560 — Verordnung über die Parkraumbewirtschaftung.
  BS–BL agreement concluded by the governments; names § 16 of the BS ordinance on parking management, the governments' own rule on the subject they agree on.
- **BS 952.570 — Vereinbarung zwischen den Kantonen Basel-Landschaft und Basel-Stadt über die gemeinsame Ausgabe von Gewerbeparkkarten** → BS 952.300 — Verordnung betreffend die ausnahmsweise Zufahrt in die Innenstadt.
  As above; names the BS ordinance on exceptional access to the city centre.
- **BL 252.111 — Vertrag über die Opferberatungsstellen beider Basel** → BL 252.11 — Verordnung zum Bundesgesetz über die Hilfe an Opfer von Straftaten.
  Contract on the victim counselling centres of both Basel; names § 1 Abs. 2 of the BL ordinance to the Victim Support Act (the BL government's competence).
- **SG 277.3 — Vereinbarung über den Schutz und die Pflege des Weltkulturerbes Stiftsbezirk St.Gallen** → SG 173.5 — Verfassung des Katholischen Konfessionsteils des Kantons St.Gallen.
  Agreement of the government, the Catholic Konfessionsteil and the city of St. Gallen on the Abbey precinct; each party names its own constitution (KV, the Konfessionsteil's constitution, the city's Gemeindeordnung).
- **NE 923.512 — Convention entre les cantons de Berne et de Neuchâtel concernant l'exercice de la pêche dans les eaux frontières du canal de la Thielle** → NE 923.101 — Règlement d'exécution de la loi sur la faune aquatique (RLFAq) ).
  NE–BE fishing convention; names art. 1 of Neuchâtel's executing regulation of its fishing law (the footnote adds: "actuellement R du 5 novembre 1997").

### Preamble lists a lower act as context (21)

The preamble lists a lower act as context, not as a delegation: "vu"/"visto" lists name the executing ordinance next to the law, or an act whose terms the new act presupposes.

- **ZH 413.227 — Vereinbarung zwischen dem Schweizerischen Bundesrat, im Namen der Regierung des Kantons Zürich, und der Regierung der Italienischen Republik betreffend den Betrieb des schweizerisch-italienischen Liceo Artistico Zürich** → ZH 413.228 — Reglement über das schweizerisch-italienische Liceo artistico (Kunstgymnasium) Zürich.
  The agreement of the Federal Council (for Zurich) with Italy on the Liceo artistico recites the local arrangements the school was founded on, among them its Reglement of 21 June 1988.
- **FR 420.82 — Règlement sur les subventions pour les infrastructures de la formation initiale en entreprise et de la formation continue financées par l'Association du Centre professionnel cantonal** → FR 420.81 — Statuts de l'Association du Centre professionnel cantonal (ACPC).
  The subsidy regulation names art. 2 of the statutes of the Association du Centre professionnel cantonal to define who receives the subsidies.
- **FR 480.1 — Loi sur l'encouragement des activités culturelles** → FR 616.11 — Règlement sur les subventions.
  "Vu la loi du 17 novembre 1999 sur les subventions (LSub) et son règlement d'exécution (RSub)": the executing regulation listed next to the law.
- **FR 710.2 — Décret fixant les principes généraux et les objectifs en matière d'aménagement du territoire** → FR 710.11 — Règlement d'exécution de la loi sur l'aménagement du territoire et les constructions.
  "Vu le règlement du 1er décembre 2009 d'exécution de la loi sur l'aménagement du territoire et les constructions", listed next to the law.
- **TI 874.500 — Legge sulle misure restrittive della libertà dei minorenni nei centri educativi** → TI 874.110 — Regolamento della legge per le famiglie.
  "Richiamati … la legge per le famiglie … e il regolamento della legge per le famiglie": the regulation listed next to the law.
- **VD 818.211 — DÉCRET sur les essais pilotes de remise contrôlée de cannabis au sens de l'article 8a de la loi fédérale sur les stupéfiants et les substances psychotropes (LStup)** → VD 818.21.4 — RÈGLEMENT sur le Groupe d'experts en matière d'addictions.
  The decree on cannabis pilot trials lists the regulation on the experts' group on addictions (RGEA) that it relies on.
- **VS 175.101 — Loi sur la fusion des communes municipales et bourgeoisiales de Sion et des Agettes** → VS 175.100 — Ordonnance sur les fusions de communes.
  The merger law lists the Conseil d'Etat's ordinance on mergers of communes (OFus) among its "vu".
- **VS 175.102 — Loi concernant la fusion des communes municipales de Baltschieder, Eggerberg et Viège** → VS 175.100 — Ordonnance sur les fusions de communes.
  As above (merger law, OFus among the "vu").
- **VS 501.20 — Décret pour la gestion des conséquences des événements naturels ayant touché le Lötschental** → VS 726.100 — Ordonnance sur les marchés publics.
  The decree on the Lötschental events lists 14 acts, among them the ordinance on public procurement.
- **VS 501.20 — Décret pour la gestion des conséquences des événements naturels ayant touché le Lötschental** → VS 705.100 — Ordonnance sur les constructions.
  As above; the ordinance on constructions.
- **VS 501.20 — Décret pour la gestion des conséquences des événements naturels ayant touché le Lötschental** → VS 611.101 — Ordonnance concernant la délégation de compétences financières du Conseil d'Etat aux départements et aux services.
  As above; the ordinance on the delegation of financial powers.
- **VS 501.30 — Décret pour le soutien aux victimes de l'incendie de Crans-Montana du 1er janvier 2026 et l'octroi d'un crédit supplémentaire** → VS 172.010 — Ordonnance sur les attributions de la présidence et des départements.
  The decree for the victims of the Crans-Montana fire lists the ordinance on the attributions of the presidency and the departments.
- **VS 813.10 — Loi d'application de la loi fédérale sur la protection contre les substances et les préparations dangereuses** → VS 451.100 — Ordonnance sur la protection de la nature, du paysage et des sites.
  "La loi cantonale sur la protection de la nature … (LcPN) et son ordonnance d'exécution (OcPN)": law and executing ordinance listed together.
- **VS 813.10 — Loi d'application de la loi fédérale sur la protection contre les substances et les préparations dangereuses** → VS 921.100 — Ordonnance sur les forêts.
  "La loi cantonale sur les forêts et les dangers naturels (LcFDN) et son ordonnance d'exécution (OcFDN)": law and executing ordinance listed together.
- **VS 900.110 — Décret concernant l’octroi de mesures exceptionnelles à des acteurs économiques touchés par des événements majeurs et imprévisibles, exogènes** → VS 900.101 — Ordonnance sur la politique économique cantonale.
  The Grand Conseil's decree lists the Conseil d'Etat's ordinance on economic policy next to the law.
- **VS 916.120 — Décret sur le blocage-financement des vins du Valais** → VS 916.142 — Ordonnance sur la vigne et le vin.
  The decree on wine stock financing lists the ordinance on vine and wine.
- **NE 411.126.0 — Règlement intercantonal des domaines professionnels BEJUNE du certificat d’école de culture générale** → NE 414.110.16 — Règlement concernant la filière menant au certificat d’école de culture générale et à la maturité spécialisée.
  The intercantonal BEJUNE regulation lists each canton's own rules on the same course, among them Neuchâtel's departmental regulation.
- **NE 821.121.34 — Arrêté fixant les tarifs de soins de longue durée au sens de l’article 25a LAMal, dispensés en établissement médico-social** → NE 832.35 — Règlement sur la reconnaissance des conditions générales de travail des établissements médico-sociaux (art. 24 LFinEMS) (RRCGT).
  The Conseil d'Etat's tariff decree lists the department's regulation on recognised working conditions (RRCGT), which the tariffs presuppose.
- **NE 832.36 — Arrêté fixant la liste et les tarifs des prestations pour les établissements médico-sociaux (EMS) et pensions au bénéfice d’un contrat de prestations au sens de la LFinEMS** → NE 832.35 — Règlement sur la reconnaissance des conditions générales de travail des établissements médico-sociaux (art. 24 LFinEMS) (RRCGT).
  As above (RRCGT listed among the "vu").
- **GE H 2 10 — Loi sur la Compagnie générale de navigation sur le Lac Léman (LCGN)** → GE H 2 05.01 — Règlement d’application de la loi sur la navigation dans les eaux genevoises (RNav).
  The law on the CGN lists federal and cantonal navigation law, among them the Conseil d'Etat's règlement d'application.
- **GE L 2 45 — Loi sur le financement de projets d’assainissement énergétique des bâtiments et sur l’ouverture de crédits d’investissement (LFAEB)** → GE L 2 30.01 — Règlement d’application de la loi sur l’énergie (REn).
  "Vu la loi sur l'énergie, du 18 septembre 1986, et son règlement d'application": listed next to the law.

### Number now carries a later act (3)

The cited act was replaced: the Ingress cites it by its date, the footnote's number now carries a later act of a lower authority.

- **JU 559.170 — Arrêté portant approbation de la convention entre la République et Canton du Jura et la République et Canton de Genève relative au traitement électronique des données de police** → JU 551.11 — Ordonnance sur l'organisation de la police cantonale (OPol).
  The 1992 approval decree cites "l'ordonnance du 19 février 1980 sur la police cantonale"; the footnote's number RSJU 551.11 now carries the Gouvernement's later OPol.
- **JU 701.251 — Ordonnance concernant la réclame extérieure et sur la voie publique** → JU 701.11 — Ordonnance sur l’aménagement du territoire et les constructions (OATC).
  An act of the Constituent Assembly (1978) cites "l'ordonnance du 6 décembre 1978 sur les constructions", its own act; RSJU 701.11 now carries the Gouvernement's OATC.
- **JU 701.511 — Décision portant délégation de compétences du Service de l'aménagement du territoire en vertu de l'article 47 de la loi sur les constructions** → JU 701.11 — Ordonnance sur l’aménagement du territoire et les constructions (OATC).
  As above (act of the Constituent Assembly, the 1978 ordinance's number now carries the OATC).

### Approval names the approved contract (3)

An approval decree names the contract it approves; the contract sits on a lower floor by its title only.

- **SR 112.1** → SR 112.
  The Federal Assembly approves the contract of 22 June 1875 between the Federal Council and the municipal council of Bern on the city's contributions to the federal seat.
- **SR 414.110.11** → SR 414.110.1.
  Approval of the Aussonderungsvertrag of 28 December 1905 (ETH) between the Confederation, the Canton and the City of Zurich.
- **SR 725.151** → SR 725.151.1.
  Approval of the agreement of 23 May 1958 with Vaud and Valais on the Great St Bernard road tunnel ("in Anbetracht des Abkommens").


## Decided (2026-10-27, decision 27)

Acts of intercantonal bodies are on floor 5 throughout: law-making by intercantonal bodies is
intercantonal law and prevails over cantonal law (Art. 48 Abs. 4/5 BV). 40 acts moved: the
Verwaltungsrat of the Ostschweizer and beider Basel BVG-Aufsicht, the OST's Hochschulrat, the CLDJP's
concordat rules, the HES-SO's and the Gymnase de la Broye's acts, the fishing commissions' rules,
UR's and ZG's acts published only by reference to an intercantonal body. Not moved: a canton's
approval or executing act for an agreement, private bodies acting for the cantons (the SRK's
rules), foundations not called intercantonal.
