"""README and directory indexes of the law repository (decision 36), written in the last commit of main."""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "build/lawgit"
AREAS = {"1": "Staat – Volk – Behörden", "2": "Privatrecht – Zivilrechtspflege – Vollstreckung", "3": "Strafrecht – Strafrechtspflege – Strafvollzug",
         "4": "Schule – Wissenschaft – Kultur", "5": "Landesverteidigung", "6": "Finanzen", "7": "Öffentliche Werke – Energie – Verkehr",
         "8": "Gesundheit – Arbeit – Soziale Sicherheit", "9": "Wirtschaft – Technische Zusammenarbeit",
         "0.1": "Völkerrecht: Staat – Volk – Behörden", "0.2": "Völkerrecht: Privatrecht – Zivilrechtspflege", "0.3": "Völkerrecht: Strafrecht – Rechtshilfe",
         "0.4": "Völkerrecht: Schule – Wissenschaft – Kultur", "0.5": "Völkerrecht: Krieg und Neutralität", "0.6": "Völkerrecht: Finanzen",
         "0.7": "Völkerrecht: Öffentliche Werke – Energie – Verkehr", "0.8": "Völkerrecht: Gesundheit – Arbeit – Soziale Sicherheit",
         "0.9": "Völkerrecht: Wirtschaft – Technische Zusammenarbeit"}
CANTON = {"AG": "Aargau", "AI": "Appenzell Innerrhoden", "AR": "Appenzell Ausserrhoden", "BE": "Bern", "BL": "Basel-Landschaft",
          "BS": "Basel-Stadt", "FR": "Freiburg / Fribourg", "GE": "Genf / Genève", "GL": "Glarus", "JU": "Jura", "GR": "Graubünden / Grigioni / Grischun", "LU": "Luzern",
          "NE": "Neuenburg / Neuchâtel", "ZH": "Zürich", "NW": "Nidwalden", "OW": "Obwalden", "SG": "St. Gallen", "SH": "Schaffhausen", "SO": "Solothurn", "TG": "Thurgau",
          "UR": "Uri", "VD": "Waadt / Vaud", "VS": "Wallis / Valais", "ZG": "Zug"}


def srkey(s: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def files(snaps: dict, facts: dict, kacts: dict, start: str, today: str, future=()) -> dict:
    out = {}
    fed = defaultdict(list)
    by_path = {a["path"]: a for a in facts.values()}
    for path, langs in snaps.items():
        if path.startswith("ch/"):
            a = by_path.get(path) or {}
            fed[path.split("/")[1]].append((a.get("sr") or path.split("/")[2], a.get("short") or "", a.get("title") or "", path, sorted(langs)))
    kt = defaultdict(list)
    kby = {a["path"]: a for a in kacts.values()}
    for path, langs in snaps.items():
        if not path.startswith("ch/") and not path.startswith(("beschlossen/", "vernehmlassung/")):
            a = kby.get(path) or {}
            kt[path.split("/")[0].upper()].append((a.get("nr") or path.split("/")[2], a.get("short") or "", a.get("title") or "", path, sorted(langs),
                                                    "pdf" if any("\ntext: pdf\n" in snaps[path][lg] for lg in langs)
                                                    else "link" if any("\ntext: link\n" in snaps[path][lg] for lg in langs) else ""))
    # per area
    for grp, rows in fed.items():
        rows.sort(key=lambda r: srkey(r[0]))
        t = [f"# {AREAS.get(grp, grp)}", "", f"{len(rows)} Erlasse in Kraft am {today} · [alle Bereiche](../README.md)", "",
             "| SR | Kurztitel | Titel | Sprachen |", "|---|---|---|---|"]
        t += [f"| {cell(sr)} | {cell(sh)} | {cell(ti)} | " + " ".join(f"[{lg}](../../{p}/{lg}.md)" for lg in ls) + " |"
              for sr, sh, ti, p, ls in rows]
        out[f"ch/{grp}/README.md"] = "\n".join(t) + "\n"
    order = sorted(fed, key=lambda g: (g.startswith("0."), srkey(g)))
    out["ch/README.md"] = "\n".join(["# Bundesrecht", "", "| Bereich | | Erlasse |", "|---|---|---:|"] +
                                    [f"| [{g}]({g}/README.md) | {AREAS.get(g, '')} | {len(fed[g])} |" for g in order]) + "\n"
    for ct, rows in kt.items():
        rows.sort(key=lambda r: srkey(r[0]))
        npdf = sum(1 for r in rows if r[5] == "pdf")
        nlink = sum(1 for r in rows if r[5] == "link")
        t = [f"# Kanton {CANTON.get(ct, ct)}", "", f"{len(rows)} Erlasse in Kraft am {today}"
             + (f"; {npdf} davon veröffentlicht der Kanton nur als PDF, ihr Text ist daraus gelesen (PDF)" if npdf else "")
             + (f"; {nlink} nur als Link auf das PDF" if nlink else ""), "",
             "| Nummer | Kurztitel | Titel | Sprachen |", "|---|---|---|---|"]
        t += [f"| {cell(nr)} | {cell(sh)} | {cell(ti)}{' (PDF)' if pdf == 'pdf' else ' (nur Link)' if pdf == 'link' else ''} | " + " ".join(f"[{lg}](../{p.split('/', 1)[1]}/{lg}.md)" for lg in ls) + " |"
              for nr, sh, ti, p, ls, pdf in rows]
        out[f"{ct.lower()}/README.md"] = "\n".join(t) + "\n"
    # adopted, not yet in force; consultations
    def fm(path, key):
        txt = next((snaps[path][lg] for lg in ("de", "fr", "it") if lg in snaps[path]), next(iter(snaps[path].values()), ""))
        m = re.search(rf"^{key}: (.*)$", txt.split("\n---\n", 1)[0], re.M)
        return (m.group(1).strip().strip('"') if m else "")
    pend = sorted(p for p in snaps if p.startswith("beschlossen/"))
    t = ["# Beschlossen, noch nicht in Kraft", "",
         f"Stand {today}. Erlasse der Amtlichen Sammlung (AS), die veröffentlicht sind, aber erst später in Kraft treten, und "
         "Referendumsvorlagen aus dem Bundesblatt (BBl) während der Referendumsfrist bzw. bis zur Veröffentlichung in der AS. "
         "Tritt ein Erlass in Kraft, verschwindet er hier und steht in seiner konsolidierten Fassung unter [ch/](../ch/README.md).", "",
         "| Fundstelle | Titel | Inkrafttreten | Referendumsfrist |", "|---|---|---|---|"]
    for p in sorted(pend, key=lambda p: (fm(p, "in_force") or fm(p, "referendum_deadline"), p)):
        lgs = sorted(snaps[p])
        t.append(f"| {cell(fm(p, 'reference'))} | {cell(fm(p, 'title'))} | {cell(fm(p, 'in_force').strip('[]'))} | "
                 f"{cell(fm(p, 'referendum_deadline'))} | " + " ".join(f"[{lg}](../{p}/{lg}.md)" for lg in lgs))
    t[4], t[5] = "| Fundstelle | Titel | Inkrafttreten | Referendumsfrist | Sprachen |", "|---|---|---|---|---|"
    if future:
        byj = defaultdict(int)
        for d, jur, p, lab in future:
            byj[jur] += 1
        t += ["", "## Künftige konsolidierte Fassungen (Branch `future`)", "",
              "Fassungen, die Bund und Kantone bereits konsolidiert veröffentlichen, die aber erst später gelten: "
              + ", ".join(f"{'Bund' if j == 'ch' else j} {n}" for j, n in sorted(byj.items(), key=lambda kv: (kv[0] != "ch", kv[0])))
              + f". `git checkout future` zeigt sie im Text; hier jede mit dem Tag, ab dem sie gilt.", "",
              "| Gilt ab | Erlass | Datei (future) |", "|---|---|---|"]
        for d, jur, p, lab in future:
            t.append(f"| {d} | {cell(lab)} | [{p}](../../../tree/future/{p}) |")
    out["beschlossen/README.md"] = "\n".join(t) + "\n"
    vl = sorted(p for p in snaps if p.startswith("vernehmlassung/"))
    t = ["# Vernehmlassungen", "",
         f"Stand {today}. Die Vernehmlassungsvorlagen des Bundes seit {start[:4]} (Entwürfe, kein geltendes Recht), aus den PDF auf "
         "Fedlex gelesen. Offen zuerst, dann nach Eröffnung.", "",
         "| Eröffnet | Frist | Status | Vorlage | Dateien |", "|---|---|---|---|---|"]
    for p in sorted(vl, key=lambda p: ("abgeschlossen" in fm(p, "status"), "" if "abgeschlossen" in fm(p, "status") else fm(p, "closes"),
                                       "".join(chr(255 - ord(ch)) for ch in fm(p, "opened")))):
        t.append(f"| {fm(p, 'opened')} | {fm(p, 'closes')} | {'abgeschlossen' if 'abgeschlossen' in fm(p, 'status') else 'offen'} | "
                 f"{cell(fm(p, 'title'))} | " + " ".join(f"[{lg}](../{p}/{lg}.md)" for lg in sorted(snaps[p])) + " |")
    out["vernehmlassung/README.md"] = "\n".join(t) + "\n"
    chk = {}
    for jur in ("ch", "kt", "vd", "sil", "pend", "pdfcur", "zh"):
        f = B / f"check_{jur}.json"
        if f.exists():
            vals = list(json.load(open(f)).values())
            chk[jur] = (len(vals), sum(1 for r in vals if r.get("miss")), sum(r.get("miss", 0) for r in vals), sum(r.get("n", 0) for r in vals))
    nfed = sum(len(v) for v in fed.values())
    nkt = {ct: len(v) for ct, v in kt.items()}
    npend = (sum(1 for p in pend if p.startswith("beschlossen/as/")), sum(1 for p in pend if p.startswith("beschlossen/bbl/")),
             len(vl), sum(1 for p in vl if "abgeschlossen" not in fm(p, "status")))
    out["README.md"] = readme(nfed, nkt, chk, start, today, npend)
    return out


def n(x) -> str:
    return f"{x:,}".replace(",", "'")


def readme(nfed: int, nkt: dict, chk: dict, start: str, today: str, npend=(0, 0, 0, 0)) -> str:
    kt_list = ", ".join(f"[{ct}]({ct.lower()}/README.md) ({n})" for ct, n in sorted(nkt.items()))
    ch = chk.get("ch", (0, 0, 0, 0))
    kc = chk.get("kt", (0, 0, 0, 0))
    vc = chk.get("vd", (0, 0, 0, 0))
    sc = chk.get("sil", (0, 0, 0, 0))
    zc = chk.get("pdfcur", (0, 0, 0, 0))
    zh_ = chk.get("zh", (0, 0, 0, 0))
    pc = chk.get("pend", (0, 0, 0, 0))
    return f"""# Schweizer Recht

Das Recht des Bundes und von {len(nkt)} Kantonen als Git-Repository: eine Datei pro Erlass und Sprache, ein Commit pro Fassung,
datiert auf den Tag, an dem sie gilt – vom {start} bis heute ({today}), dazu die bereits veröffentlichten künftigen Fassungen.
Ein Projekt von [jonashertner.com](https://jonashertner.com); die Karte dazu: [Atlas des Schweizer Rechts](https://jonashertner.github.io/swiss-law-graph/).

> **Nicht amtlich.** Massgebend ist die Veröffentlichung in der Amtlichen Sammlung des Bundesrechts (Art. 15 PublG, SR 170.512)
> bzw. die amtliche Veröffentlichung des Kantons. Englische Fassungen sind Übersetzungen ohne Rechtskraft.

- **Bundesrecht** ([ch/](ch/README.md)): {n(nfed)} Erlasse in Kraft, Landesrecht und Völkerrecht, deutsch, französisch, italienisch, wo vorhanden rätoromanisch und englisch.
- **Kantonales Recht**: {kt_list}.
- **Beschlossen, noch nicht in Kraft** ([beschlossen/](beschlossen/README.md)): {n(npend[0])} Erlasse der Amtlichen Sammlung, die erst
  später in Kraft treten, {n(npend[1])} Referendumsvorlagen aus dem Bundesblatt. Jeder steht dort vom Tag seiner Veröffentlichung bis zum
  Inkrafttreten bzw. zur Veröffentlichung in der AS (dann ab dem Tag seines Inkrafttretens unter `ch/`).
- **Vernehmlassungen** ([vernehmlassung/](vernehmlassung/README.md)): {n(npend[2])} Vernehmlassungsvorlagen des Bundes seit {start[:4]},
  davon {n(npend[3])} offen. Entwürfe, kein geltendes Recht.

## Benutzen

```sh
cat ch/2/220/de.md                                        # das Obligationenrecht, heute
git log --follow -p -- ch/2/220/de.md                     # jede Fassung seit {start[:4]}, mit Änderungen
git blame ch/2/220/de.md                                  # welche Fassung jede Zeile geschrieben hat
git show "$(git rev-list -1 --before=2023-07-01 main)":ch/2/220/de.md     # das OR, wie es am 30. Juni 2023 galt
git diff "$(git rev-list -1 --before=2022-01-01 main)" main -- ch/2/220/de.md
git log --since=2025-01-01 --oneline -- 'zh/*' 'be/*'     # was sich in einem Kanton geändert hat
git grep -n "Treu und Glauben" -- 'ch/*/de.md'
git checkout future                                       # mit den Fassungen, die erst später gelten
```

Jeder Artikel ist eine Überschrift (`#### Art. 41`), also verlinkbar: `ch/2/220/de.md#art-41`. Absätze stehen je auf einer Zeile, damit
Diffs und `blame` genau sind. Fussnoten (Änderungsvermerke mit der Fundstelle in der AS) folgen dem Artikel, zu dem sie gehören.
Der Kopf jeder Datei (YAML) nennt SR-Nummer bzw. Nummer der kantonalen Sammlung, Titel, Kurztitel, Sprache, die Fassung (gültig ab),
Beschluss und Inkrafttreten und die Quelle.

Die Commit-Nachricht nennt, was sich geändert hat: beim Bund die Fundstellen in der AS aus den in dieser Fassung neuen Fussnoten,
bei den Kantonen die Zeilen der Änderungstabelle, die an diesem Tag in Kraft traten. Zeitpunkt jedes Commits: 00:00 Uhr (Zürich) des
Tages, ab dem die Fassung gilt. Ein aufgehobener Erlass wird an seinem letzten Tag + 1 gelöscht.

## Quellen und Prüfung

- Bund: die konsolidierten Fassungen von [Fedlex](https://www.fedlex.admin.ch) als XML (Akoma Ntoso), über den SPARQL-Endpunkt der Bundeskanzlei.
  Fedlex führt XML ab 2021 und die damals geltende Fassung: Für {start} liegt von 5'105 der 5'106 damals geltenden Erlasse die Fassung vor.
- Kantone: die systematischen Gesetzessammlungen der Kantone auf LexWork (AG, AI, AR, BE, BL, BS, FR, GL, GR, LU, NW, OW, SG, SH, SO, TG, UR,
  VS, ZG), jede Fassung seit {start}, auch formlose Berichtigungen; die Base législative vaudoise (BLV) mit allen konsolidierten Erlassen
  (auch den «mineurs»), ebenfalls jede Fassung seit {start}. Erlasse, die seit {start} aufgehoben wurden, sind bis zu ihrer Aufhebung enthalten.
- Zürich (zh.ch, Loseblattsammlung): jede Fassung seit {start} der heute geltenden Erlasse, aus den PDF des Kantons gelesen (Kopf
  `text: pdf`); eine Fassung gilt ab der letzten «in Kraft seit»-Angabe ihrer Fussnoten, sonst ab dem Ende der vorigen laut «Historie».
  Jura (RSJU): der geltende Text aus dem PDF, ab dem Tag seiner Fassung (letzte «en vigueur depuis le»), bei älteren ab {start}.
- Genf (rs/GE) und Neuenburg (RSN) veröffentlichen nur den geltenden Text (Word-HTML der SIL). Er steht ab dem Tag im Repository, an dem
  er gilt (GE: das letzte Inkrafttreten der Änderungstabelle, NE: «État au»), bei älteren Fassungen ab {start}. Ein Erlass, der seit
  {start} geändert wurde, fehlt deshalb vor seiner geltenden Fassung; die Änderungen nennt die Tabelle am Ende des Erlasses (GE) bzw. die Fussnoten (NE).
- Geprüft wird jede Datei: Jedes Wort des Quelltextes muss im Markdown stehen. Bund: {n(ch[0])} Dateien, {ch[1]} mit Abweichung,
  {n(ch[2])} von {n(ch[3])} Wörtern fehlen (meist Abstände in Fundstellen). Kantone: {n(kc[0])} Dateien, {kc[1]} mit Abweichung,
  {n(kc[2])} von {n(kc[3])} Wörtern fehlen. Waadt: {n(vc[0])} Dateien, {vc[1]} mit Abweichung, {n(vc[2])} von {n(vc[3])} Wörtern fehlen.
  Genf und Neuenburg: {n(sc[0])} Dateien, {sc[1]} mit Abweichung, {n(sc[2])} von {n(sc[3])} Wörtern fehlen. Zürich (aus dem PDF):
  {n(zh_[0])} Dateien, {n(zh_[2])} von {n(zh_[3])} Wörtern fehlen; Jura: {n(zc[0])} Dateien (mit den geltenden Zürcher Texten),
  {n(zc[2])} von {n(zc[3])} Wörtern fehlen.
- Beschlossene Erlasse und Referendumsvorlagen: XML aus AS und Bundesblatt (Fedlex). Vernehmlassungsvorlagen: die PDF auf Fedlex,
  Text daraus gelesen ({n(pc[0])} Dateien, {n(pc[2])} von {n(pc[3])} Wörtern fehlen).
- Erzeugt mit den offenen Skripten in [`jonashertner/swiss-law-graph`](https://github.com/jonashertner/swiss-law-graph) (`pipeline/lawgit/`).

## Was fehlt

- Fassungen vor 2021 (Fedlex hat sie nur als PDF und Word) und kantonale Erlasse, die vor 2021 aufgehoben wurden.
- Frühere Fassungen in GE und NE (die Kantone veröffentlichen sie nicht als Text).
- Frühere Fassungen im Jura (RSJU veröffentlicht nur den geltenden Text) sowie Zürcher Erlasse, die seit {start} aufgehoben wurden.
- Die Kantone TI und SZ (von hier aus nur über LexFind erreichbar).
- Kantonale Fassungen, die der Kanton nur als PDF veröffentlicht, sind aus dem PDF gelesen (Kopf `text: pdf`): der Wortlaut ist exakt, die
  Gliederung aus dem Satzbild erschlossen; in Tarifen und Tabellen können Zeilen zusammenlaufen. War kein PDF zu lesen, nennt die Datei den Link.
- Referendumsvorlagen, die vor Juli 2020 veröffentlicht wurden (etwa das CO2-Gesetz von 2020), fehlen unter `beschlossen/`. Abgelehnte
  Vorlagen erkennt das Repository an den Bundesratsbeschlüssen über das Ergebnis der Volksabstimmung; sie verschwinden am Tag der Abstimmung.
- Von den Vernehmlassungen nur die Vorlagen, nicht die erläuternden Berichte und Stellungnahmen.
- Aufzählungen kantonaler Tarife mit einer Betragsspalte: Betrag nach « — ».

## Lizenz

Erlasse und ihre Übersetzungen sind urheberrechtlich nicht geschützt (Art. 5 Abs. 1 Bst. a und Abs. 2 URG). Aufbereitung, Kopfdaten
und Verzeichnisse: [CC0](https://creativecommons.org/publicdomain/zero/1.0/deed.de). Skripte: MIT.

---

## Droit suisse

Le droit fédéral et celui de {len(nkt)} cantons sous forme de dépôt Git : un fichier par acte et par langue, un commit par version, daté du jour
où elle s’applique, du {start} à aujourd’hui ; la branche `future` contient les versions déjà publiées qui s’appliqueront plus tard.
**Non officiel** : seule la publication au Recueil officiel fait foi (art. 15 LPubl, RS 170.512), resp. la publication officielle du canton.
Chaque article est un titre (`#### Art. 41`) ; chaque alinéa tient sur une ligne. Sources : Fedlex (XML), les recueils cantonaux sur LexWork,
la BLV (Vaud) et la SIL (Genève, Neuchâtel : texte en vigueur seulement).

## Diritto svizzero

Il diritto federale e quello di {len(nkt)} Cantoni come repository Git: un file per atto e lingua, un commit per versione, datato al giorno
in cui si applica, dal {start} a oggi; il ramo `future` contiene le versioni già pubblicate che si applicheranno più tardi.
**Non ufficiale**: fa stato la pubblicazione nella Raccolta ufficiale (art. 15 LPubb, RS 170.512), risp. la pubblicazione ufficiale del Cantone.

## Swiss law

Federal law and the law of {len(nkt)} cantons as a Git repository: one file per act and language, one commit per version, dated on the day
it applies, from {start} to today; the `future` branch holds versions already published for a later day. **Not official**: only the
publication in the Official Compilation is authoritative (Art. 15 PublA, SR 170.512), or the canton's official publication. Use
`git log -p`, `git blame` and `git show "$(git rev-list -1 --before=DATE main)":PATH` to read the law as it stood on any day.
"""
