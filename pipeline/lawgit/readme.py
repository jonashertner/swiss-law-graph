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


def yload(v: str):
    """One value of the YAML subset the converters write (akn2md.yval): a plain or double-quoted scalar, a flow list."""
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [yload(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"|[^,\[\]]+', v[1:-1]) if x.strip()]
    if len(v) >= 2 and v[0] == v[-1] == '"':
        return re.sub(r"\\(.)", r"\1", v[1:-1])
    return v


def front_of(txt: str) -> dict:
    """The YAML head of a file as a dict."""
    if not txt.startswith("---\n"):
        return {}
    out = {}
    for line in txt[4:].split("\n---\n", 1)[0].split("\n"):
        k, sep, v = line.partition(": ")
        if sep:
            out[k] = yload(v)
    return out


INDEX_COLS = ["file", "act", "jurisdiction", "kind", "number", "language", "title", "short", "version", "valid_until",
              "adopted", "in_force", "status", "text", "url", "source"]


def index_rows(snaps: dict) -> list[dict]:
    """One row per file of the last tree: what an agent needs to find a file without opening it."""
    rows = []
    for path in sorted(snaps, key=srkey):
        top = path.split("/")[0]
        kind = ("treaty" if path.split("/")[1].startswith("0.") else "federal") if top == "ch" else \
            "adopted" if path.startswith("beschlossen/as/") else "referendum" if path.startswith("beschlossen/bbl/") else \
            "consultation" if top == "vernehmlassung" else "cantonal"
        for lg in sorted(snaps[path]):
            f = front_of(snaps[path][lg])
            num = f.get("sr") or f.get("number") or f.get("reference") or f.get("consultation") or ""
            text = f.get("text") or ("pdf" if kind == "consultation" else "xml" if top in ("ch", "beschlossen") else "html")
            val = lambda x: ", ".join(x) if isinstance(x, list) else (x or "")
            rows.append({"file": f"{path}/{lg}.md", "act": path, "jurisdiction": "CH" if top in ("ch", "beschlossen", "vernehmlassung") else top.upper(),
                         "kind": kind, "number": num, "language": lg, "title": f.get("title") or "", "short": f.get("short") or "",
                         "version": f.get("version") or f.get("opened") or f.get("published") or "",
                         "valid_until": f.get("valid_until") or f.get("closes") or f.get("referendum_deadline") or "",
                         "adopted": f.get("adopted") or "", "in_force": val(f.get("in_force")), "status": f.get("status") or "in force",
                         "text": text, "url": f.get("url") or "", "source": f.get("source") or f.get("pdf") or ""})
    return rows


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
        v = front_of(txt).get(key) or ""
        return ", ".join(v) if isinstance(v, list) else v
    pend = sorted(p for p in snaps if p.startswith("beschlossen/"))
    t = ["# Beschlossen, noch nicht in Kraft", "",
         f"Stand {today}. Erlasse der Amtlichen Sammlung (AS), die veröffentlicht sind, aber erst später in Kraft treten, und "
         "Referendumsvorlagen aus dem Bundesblatt (BBl) während der Referendumsfrist bzw. bis zur Veröffentlichung in der AS. "
         "Tritt ein Erlass in Kraft, verschwindet er hier und steht in seiner konsolidierten Fassung unter [ch/](../ch/README.md).", "",
         "| Fundstelle | Titel | Inkrafttreten | Referendumsfrist |", "|---|---|---|---|"]
    for p in sorted(pend, key=lambda p: (fm(p, "in_force") or fm(p, "referendum_deadline"), p)):
        lgs = sorted(snaps[p])
        t.append(f"| {cell(fm(p, 'reference'))} | {cell(fm(p, 'title'))} | {cell(fm(p, 'in_force'))} | "
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
            if jur == "pdfcur":                          # Jura only (the current Zürich texts give way to its history)
                vj = [r for r in vals if r["f"].startswith("md/ju/")]
                chk["ju"] = (len(vj), sum(1 for r in vj if r.get("miss")), sum(r.get("miss", 0) for r in vj), sum(r.get("n", 0) for r in vj))
            if jur == "pend":                            # the consultation drafts (PDF), apart from the AS and BBl texts (XML)
                for key, vk in (("cons", [r for r in vals if r.get("pdf")]), ("pendx", [r for r in vals if not r.get("pdf")])):
                    chk[key] = (len(vk), sum(1 for r in vk if r.get("miss")), sum(r.get("miss", 0) for r in vk), sum(r.get("n", 0) for r in vk))
            if jur == "kt":                              # the LexWork versions read from the canton's PDF
                vp = [r for r in vals if r.get("pdf")]
                chk["kt_pdf"] = (len(vp), sum(1 for r in vp if r.get("miss")), sum(r.get("miss", 0) for r in vp), sum(r.get("n", 0) for r in vp))
    nfed = sum(len(v) for v in fed.values())
    nkt = {ct: len(v) for ct, v in kt.items()}
    npend = (sum(1 for p in pend if p.startswith("beschlossen/as/")), sum(1 for p in pend if p.startswith("beschlossen/bbl/")),
             len(vl), sum(1 for p in vl if "abgeschlossen" not in fm(p, "status")))
    P = B / "pending"
    nopdf = (sum(1 for a in json.load(open(P / "as.json")) if not a["xml"]) if (P / "as.json").exists() else 0,
             sum(1 for a in json.load(open(P / "ref.json")) if not a["xml"]) if (P / "ref.json").exists() else 0)
    out["README.md"] = readme(nfed, nkt, chk, start, today, npend, nopdf)
    rows = index_rows(snaps)
    import csv
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=INDEX_COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    out["index.csv"] = buf.getvalue()
    out["index.jsonl"] = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    out["AGENTS.md"] = agents(len(rows), len(snaps), start, today)
    return out


def n(x) -> str:
    return f"{x:,}".replace(",", "'")


def readme(nfed: int, nkt: dict, chk: dict, start: str, today: str, npend=(0, 0, 0, 0), nopdf=(0, 0)) -> str:
    kt_list = ", ".join(f"[{ct}]({ct.lower()}/README.md) ({n})" for ct, n in sorted(nkt.items()))
    ch = chk.get("ch", (0, 0, 0, 0))
    kc = chk.get("kt", (0, 0, 0, 0))
    kp = chk.get("kt_pdf", (0, 0, 0, 0))
    vc = chk.get("vd", (0, 0, 0, 0))
    sc = chk.get("sil", (0, 0, 0, 0))
    zc = chk.get("ju", (0, 0, 0, 0))
    zh_ = chk.get("zh", (0, 0, 0, 0))
    pc = chk.get("cons", (0, 0, 0, 0))
    px = chk.get("pendx", (0, 0, 0, 0))
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
git show "$(git rev-list -1 --before='2023-06-30 12:00 +0200' main)":ch/2/220/de.md   # das OR, wie es am 30. Juni 2023 galt
git diff "$(git rev-list -1 --before='2022-01-01 12:00 +0100' main)" main -- ch/2/220/de.md     # seit dem 1. Januar 2022
grep ',220,' index.csv                                    # Datei, Sprachen, Fassung, Quelle jedes Erlasses (auch index.jsonl)
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
  {n(kc[2])} von {n(kc[3])} Wörtern fehlen (davon aus dem PDF gelesen: {n(kp[0])} Dateien, {n(kp[2])} von {n(kp[3])} Wörtern fehlen). Waadt: {n(vc[0])} Dateien, {vc[1]} mit Abweichung, {n(vc[2])} von {n(vc[3])} Wörtern fehlen.
  Genf und Neuenburg: {n(sc[0])} Dateien, {sc[1]} mit Abweichung, {n(sc[2])} von {n(sc[3])} Wörtern fehlen. Zürich (aus dem PDF):
  {n(zh_[0])} Dateien, {n(zh_[2])} von {n(zh_[3])} Wörtern fehlen; Jura (aus dem PDF): {n(zc[0])} Dateien,
  {n(zc[2])} von {n(zc[3])} Wörtern fehlen.
- Beschlossene Erlasse und Referendumsvorlagen: XML aus AS und Bundesblatt (Fedlex; {n(px[0])} Dateien, {n(px[2])} von {n(px[3])} Wörtern
  fehlen). Vernehmlassungsvorlagen: die PDF auf Fedlex, Text daraus gelesen ({n(pc[0])} Dateien, {n(pc[2])} von {n(pc[3])} Wörtern fehlen;
  zwei italienische Vorlagen liefert Fedlex als leere Datei).
- Erzeugt mit den offenen Skripten in [`jonashertner/swiss-law-graph`](https://github.com/jonashertner/swiss-law-graph) (`pipeline/lawgit/`).

## Was fehlt

- Fassungen vor 2021 (Fedlex hat sie nur als PDF und Word) und kantonale Erlasse, die vor 2021 aufgehoben wurden.
- Frühere Fassungen in GE und NE (die Kantone veröffentlichen sie nicht als Text).
- Frühere Fassungen im Jura (RSJU veröffentlicht nur den geltenden Text) sowie Zürcher Erlasse, die seit {start} aufgehoben wurden.
- Die Kantone TI und SZ (von hier aus nur über LexFind erreichbar).
- Kantonale Fassungen, die der Kanton nur als PDF veröffentlicht, sind aus dem PDF gelesen (Kopf `text: pdf`). Geprüft ist, dass jedes Wort
  des PDF in der Datei steht (oben); die Gliederung ist aus dem Satzbild erschlossen und nicht geprüft: Überschriften, Absätze und Listen
  können anders gegliedert, Fussnoten anders zugeordnet sein als im Original, in Tarifen und Tabellen Zeilen zusammenlaufen. Im Zweifel
  gilt das PDF, dessen Link der Kopf nennt (`pdf:`). War kein PDF zu lesen, nennt die Datei nur den Link.
- Referendumsvorlagen, die vor Juli 2020 veröffentlicht wurden (etwa das CO2-Gesetz von 2020), fehlen unter `beschlossen/`. Abgelehnte
  Vorlagen erkennt das Repository an den Bundesratsbeschlüssen über das Ergebnis der Volksabstimmung; sie verschwinden am Tag der Abstimmung.
- Erlasse der AS und Referendumsvorlagen, die Fedlex nur als PDF führt ({n(nopdf[0])} bzw. {n(nopdf[1])}, fast alle 2020–2022), fehlen
  unter `beschlossen/`; die AS-Erlasse stehen ab ihrem Inkrafttreten in ihrer konsolidierten Fassung unter `ch/`.
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
`git log -p`, `git blame` and `git show "$(git rev-list -1 --before='YYYY-MM-DD 12:00 +0100' main)":PATH` to read the law as it
stood on any day (noon, so the time zone of your machine does not matter). `index.csv` / `index.jsonl` list every file with its
number, title, version and source; [AGENTS.md](AGENTS.md) documents the layout and every field for scripts and agents.
"""


def agents(nfiles: int, nacts: int, start: str, today: str) -> str:
    """AGENTS.md: the repository for scripts and agents — layout, every field, exact recipes, the limits."""
    return f"""# Using this repository from scripts and agents

Swiss federal law and the law of the cantons, as Markdown: one file per act and language, one commit per version, each
commit dated 00:00 Europe/Zurich on the day its version applies ({start} to {today}). Not official: the official
publication (AS/BBl for the Confederation, the canton's collection) is authoritative. {n(nfiles)} files, {n(nacts)} acts and
drafts in the last tree of `main`.

## Find a file without opening it: `index.csv`, `index.jsonl`

One row per file of the last tree of `main` (the same rows in both files; `future` adds the versions it holds).

| column | meaning |
|---|---|
| `file` | path of the file, e.g. `ch/2/220/de.md` |
| `act` | its directory: one act, all languages (`ch/2/220`) |
| `jurisdiction` | `CH` or the canton (`ZH`, `VD`, …) |
| `kind` | `federal`, `treaty` (SR 0.…), `cantonal`, `adopted` (published in the AS, not yet in force), `referendum` (BBl, referendum period), `consultation` (draft) |
| `number` | SR number, the canton's collection number, the AS/BBl reference, or the consultation's ELI |
| `language` | `de`, `fr`, `it`, `rm`, `en` (English: a translation without legal force) |
| `title`, `short` | title and abbreviation in that language |
| `version` | the day this version applies from (consultation: opened; AS/BBl: published) |
| `valid_until` | last day of this version if the source states it (consultation: deadline; BBl: referendum deadline) |
| `adopted`, `in_force` | adoption and first entry into force of the act (AS acts in force in stages: several dates) |
| `status` | `in force`, or the status of an adopted act, referendum bill or draft |
| `text` | where the words come from: `xml` (Fedlex), `html` (the canton's structured text), `pdf` (read from the canton's or Fedlex's PDF: words checked, structure inferred), `link` (no text, only the link) |
| `url`, `source` | the page of this version; the file it was read from (XML or PDF) |

## Layout

| path | content |
|---|---|
| `ch/<area>/<SR>/<lang>.md` | federal acts in force, area = first digit (treaties: `0.1` … `0.9`) |
| `<ct>/<first char>/<number>/<lang>.md` | cantonal acts (`zh/7/700.1/de.md`; characters outside `[A-Za-z0-9._-]` become `_`) |
| `beschlossen/as/<year>/<nr>/` | acts published in the AS whose entry into force is later; removed on the day they enter into force (they then appear consolidated under `ch/`) |
| `beschlossen/bbl/<year>/<nr>/` | bills subject to referendum, until their AS publication, the referendum deadline or a rejection at the ballot |
| `vernehmlassung/<year>/<nr>/` | federal consultation drafts from their opening; `status: Vernehmlassung abgeschlossen` once closed |
| `README.md` in each directory | human-readable lists |

Branches: `main` = the law as it applied each day up to {today}; `future` = `main` plus versions already published for a
later day.

## Inside a file

- YAML front matter (the fields above, plus per source: federal `sr`, `eli`, `source`; cantonal `canton`, `number`,
  `corrected` (a correction without formal procedure), `version_adopted` (adoption of the amendment that made this
  version), `pdf`; ZH `nachtrag`; consultations `document`, `opened`, `closes`, `affects` (SR numbers), `consultation`).
  Lists are YAML flow sequences.
- A one-line notice (`> …`) that the text is not official.
- `# Title`, then preamble, then the structure: `##`/`###` headings for parts, titles, chapters, sections;
  `#### Art. 41` (cantons: `#### § 3`, `#### Article 12`) for each article, so `ch/2/220/de.md#art-41` links to it.
- Each paragraph on one line, starting `<sup>1</sup>`; lists as `- a. …`; tables as HTML.
- Footnotes `[^<article>-<k>]`, defined right after the article that calls them (amendment notes with their AS/collection reference).
- Amending acts (`beschlossen/as/`): the amended element in bold (`**Art. 6 Abs. 2bis**`) followed by its new text.

## Recipes

```sh
# the file as it applied on a day: the last commit at or before noon of that day, Zurich time (any machine time zone)
git show "$(git rev-list -1 --before='2023-06-30 12:00 +0200' main)":ch/2/220/de.md
# every version of an act, with what changed
git log --follow -p -- ch/2/220/de.md
# what changed in a canton or an area between two days
git log --since='2025-01-01 12:00 +0100' --until='2025-12-31 12:00 +0100' --name-status -- 'zh/*' 'ch/8/*'
# find an act by number or title words
grep -i ',220,' index.csv;  grep -i 'Raumplanung' index.csv | grep ',cantonal,'
# the law of a day as a whole tree
git worktree add /tmp/law-2022 "$(git rev-list -1 --before='2022-07-01 12:00 +0200' main)"
```

Commit messages: first line `<label>: Stand <day>` (or `aufgehoben per`, `formlos berichtigt`, `veröffentlicht, tritt am …
in Kraft`, `Vernehmlassung eröffnet/abgeschlossen`); the body lists the AS references new in this version (federal) or the rows
of the canton's change table that took effect that day, then `Fedlex:`/`Quelle:` with the URL.

## Limits

- Federal versions before 2021 are not here (Fedlex publishes them as PDF/Word only); versions start on {start}.
- Geneva and Neuchâtel publish only the text in force; it enters on the day its version took effect (or {start}).
  Jura: likewise, from its PDF. Ticino and Schwyz are not included.
- `text: pdf` files: every word of the PDF is in the file (checked), but headings, paragraphs, lists and footnotes are
  inferred from the layout. When in doubt, the PDF in `source` is authoritative.
- AS acts of 2020–2022 published only as PDF are missing under `beschlossen/as/`; consultations: drafts only, not the
  explanatory reports.

Made by [jonashertner.com](https://jonashertner.com) with the scripts in `jonashertner/swiss-law-graph` (`pipeline/lawgit/`).
Texts of acts: not protected by copyright (Art. 5 URG). Front matter, indexes: CC0.
"""
