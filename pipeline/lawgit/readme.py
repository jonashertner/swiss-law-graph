"""The repository's own files (decision 36), written in the last commit of main: the front page in four languages, a
README per part (federal areas, cantons, adopted acts, consultations), AGENTS.md for programs, LICENSE, CITATION.cff,
.gitattributes and the indexes (index.csv, index.jsonl). Every number is counted from the tree it describes."""
import csv
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "build/lawgit"
REPO = "https://github.com/jonashertner/swisslaw-git"
SITE = "https://jonashertner.github.io/swiss-law-graph/"
LANGS = ("de", "fr", "it", "en")
LNAME = {"de": "Deutsch", "fr": "Français", "it": "Italiano", "en": "English"}
FILE = {"de": "README.md", "fr": "README.fr.md", "it": "README.it.md", "en": "README.en.md"}
FMT = {"de": "'", "fr": "\u202f", "it": "'", "en": ","}                       # thousands
MONTHS = {"de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember",
          "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre",
          "it": "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre",
          "en": "January February March April May June July August September October November December"}
CT = {"AG": ("Aargau", "Argovie", "Argovia", "Aargau"), "AI": ("Appenzell Innerrhoden", "Appenzell Rhodes-Intérieures", "Appenzello Interno", "Appenzell Innerrhoden"),
      "AR": ("Appenzell Ausserrhoden", "Appenzell Rhodes-Extérieures", "Appenzello Esterno", "Appenzell Ausserrhoden"),
      "BE": ("Bern", "Berne", "Berna", "Bern"), "BL": ("Basel-Landschaft", "Bâle-Campagne", "Basilea Campagna", "Basel-Landschaft"),
      "BS": ("Basel-Stadt", "Bâle-Ville", "Basilea Città", "Basel-Stadt"), "FR": ("Freiburg", "Fribourg", "Friburgo", "Fribourg"),
      "GE": ("Genf", "Genève", "Ginevra", "Geneva"), "GL": ("Glarus", "Glaris", "Glarona", "Glarus"), "GR": ("Graubünden", "Grisons", "Grigioni", "Graubünden"),
      "JU": ("Jura", "Jura", "Giura", "Jura"), "LU": ("Luzern", "Lucerne", "Lucerna", "Lucerne"), "NE": ("Neuenburg", "Neuchâtel", "Neuchâtel", "Neuchâtel"),
      "NW": ("Nidwalden", "Nidwald", "Nidvaldo", "Nidwalden"), "OW": ("Obwalden", "Obwald", "Obvaldo", "Obwalden"),
      "SG": ("St. Gallen", "Saint-Gall", "San Gallo", "St. Gallen"), "SH": ("Schaffhausen", "Schaffhouse", "Sciaffusa", "Schaffhausen"),
      "SO": ("Solothurn", "Soleure", "Soletta", "Solothurn"), "SZ": ("Schwyz", "Schwytz", "Svitto", "Schwyz"), "TG": ("Thurgau", "Thurgovie", "Turgovia", "Thurgau"),
      "TI": ("Tessin", "Tessin", "Ticino", "Ticino"), "UR": ("Uri", "Uri", "Uri", "Uri"), "VD": ("Waadt", "Vaud", "Vaud", "Vaud"),
      "VS": ("Wallis", "Valais", "Vallese", "Valais"), "ZG": ("Zug", "Zoug", "Zugo", "Zug"), "ZH": ("Zürich", "Zurich", "Zurigo", "Zurich")}
ORDER = "ZH BE LU UR SZ OW NW GL ZG FR SO BS BL SH AR AI SG GR AG TG TI VD VS NE GE JU".split()         # Art. 1 BV
OWN = {"FR": "fr", "VS": "fr", "GE": "fr", "VD": "fr", "NE": "fr", "JU": "fr", "TI": "it"}   # the language of the canton's collection
LEXWORK = set("AG AI AR BE BL BS FR GL GR LU NW OW SG SH SO TG UR VS ZG".split())
GOOD = {"de": "Treu und Glauben", "fr": "bonne foi", "it": "buona fede", "en": "good faith"}
MOST = ["101", "210", "220", "311.0", "281.1", "272", "312.0", "173.110", "172.021", "235.1", "830.1", "142.20", "0.101"]


def area_names() -> dict:
    """The SR's own names of its areas (1 … 9, 0.1 … 0.9), in every language, from the Fedlex taxonomy."""
    out = defaultdict(dict)
    f = ROOT / "data/sr_taxonomy.csv"
    if f.exists():
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if re.fullmatch(r"\d|0\.\d", r["notation"]):
                out[r["notation"]][r["lang"]] = r["label"].replace(" - ", " – ")
    return out


def srkey(s: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def cell(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def n(x, lg="de") -> str:
    return f"{x:,}".replace(",", FMT[lg])


def day(d: str, lg: str) -> str:
    y, m, dd = d.split("-")
    mo = MONTHS[lg].split()[int(m) - 1]
    return {"de": f"{int(dd)}. {mo} {y}", "fr": f"{'1er' if dd == '01' else int(dd)} {mo} {y}", "it": f"{'1°' if dd == '01' else int(dd)} {mo} {y}",
            "en": f"{int(dd)} {mo} {y}"}[lg]


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


def kind_of(path: str) -> str:
    top = path.split("/")[0]
    if top == "ch":
        return "treaty" if path.split("/")[1].startswith("0.") else "federal"
    return {"cantons": "cantonal", "consultations": "consultation"}.get(top) or ("adopted" if path.startswith("adopted/as/") else "referendum")


def index_rows(snaps: dict) -> list[dict]:
    """One row per file of the last tree: what an agent needs to find a file without opening it."""
    rows = []
    val = lambda x: ", ".join(x) if isinstance(x, list) else (x or "")
    for path in sorted(snaps, key=srkey):
        kind = kind_of(path)
        for lg in sorted(snaps[path]):
            f = front_of(snaps[path][lg])
            num = f.get("sr") or f.get("number") or f.get("reference") or f.get("consultation") or ""
            text = f.get("text") or ("pdf" if kind == "consultation" else "html" if kind == "cantonal" else "xml")
            rows.append({"file": f"{path}/{lg}.md", "act": path, "jurisdiction": path.split("/")[1].upper() if kind == "cantonal" else "CH",
                         "kind": kind, "number": num, "language": lg, "title": f.get("title") or "", "short": f.get("short") or "",
                         "version": f.get("version") or f.get("opened") or f.get("published") or "",
                         "valid_until": f.get("valid_until") or f.get("closes") or f.get("referendum_deadline") or "",
                         "adopted": f.get("adopted") or "", "in_force": val(f.get("in_force")), "status": f.get("status") or "in force",
                         "text": text, "url": f.get("url") or "", "source": f.get("source") or f.get("pdf") or ""})
    return rows


def checks() -> dict:
    """The word check per source (convert.py, build/lawgit/check_*.json): files, words of the source, words missing."""
    out = {}
    for jur in ("ch", "kt", "vd", "sil", "pend", "pdfcur", "zh"):
        f = B / f"check_{jur}.json"
        if not f.exists():
            continue
        vals = list(json.load(open(f)).values())
        parts = {"ch": [("ch", vals)], "kt": [("lexwork", [r for r in vals if not r.get("pdf")]), ("lexwork_pdf", [r for r in vals if r.get("pdf")])],
                 "vd": [("vd", vals)], "sil": [("sil", vals)], "zh": [("zh", vals)],
                 "pdfcur": [("ju", [r for r in vals if r["f"].startswith("md/ju/")])],
                 "pend": [("asbbl", [r for r in vals if not r.get("pdf")]), ("cons", [r for r in vals if r.get("pdf")])]}[jur]
        for key, vs in parts:
            vs = [r for r in vs if not r.get("pdf_only") and not r.get("error")]
            out[key] = (len(vs), sum(r.get("n", 0) for r in vs), sum(r.get("miss", 0) for r in vs))
    return out


# ---------------------------------------------------------------- texts
T = {
    "title": ("Schweizer Recht", "Droit suisse", "Diritto svizzero", "Swiss law"),
    "lede": ("Das Recht des Bundes und der Kantone als Git-Repository: jeder Erlass eine Datei je Sprache, jede Fassung ein Commit, "
             "datiert auf den Tag, an dem sie gilt – seit dem {start}.",
             "Le droit de la Confédération et des cantons en dépôt Git : chaque acte un fichier par langue, chaque version un commit, "
             "daté du jour où elle s’applique – depuis le {start}.",
             "Il diritto della Confederazione e dei Cantoni come repository Git: ogni atto un file per lingua, ogni versione un commit, "
             "datato al giorno in cui si applica – dal {start}.",
             "The law of the Confederation and the cantons as a git repository: one file per act and language, one commit per version, "
             "dated on the day it applies – since {start}."),
    "notice": ("**Nicht amtlich.** Massgebend ist die Veröffentlichung in der Amtlichen Sammlung des Bundesrechts (Art. 15 PublG, SR 170.512) "
               "und in den amtlichen Sammlungen der Kantone. Englische Fassungen sind Übersetzungen ohne Rechtskraft.",
               "**Non officiel.** Seule fait foi la publication au Recueil officiel du droit fédéral (art. 15 LPubl, RS 170.512) "
               "et dans les recueils officiels des cantons. Les versions anglaises sont des traductions sans force juridique.",
               "**Non ufficiale.** Fa stato la pubblicazione nella Raccolta ufficiale del diritto federale (art. 15 LPubb, RS 170.512) "
               "e nelle raccolte ufficiali dei Cantoni. Le versioni inglesi sono traduzioni senza forza giuridica.",
               "**Not official.** Only the publication in the Official Compilation of Federal Legislation (Art. 15 PublA, SR 170.512) "
               "and in the cantons' official collections is authoritative. English versions are translations without legal force."),
    "th": (("", "Erlasse", "Fassungen seit {y}"), ("", "Actes", "Versions depuis {y}"), ("", "Atti", "Versioni dal {y}"), ("", "Acts", "Versions since {y}")),
    "fed": ("Bundesrecht", "Droit fédéral", "Diritto federale", "Federal law"),
    "fed2": ("Landesrecht und Staatsverträge", "droit interne et traités", "diritto interno e trattati", "domestic law and treaties"),
    "kt": ("Kantonales Recht", "Droit cantonal", "Diritto cantonale", "Cantonal law"),
    "kt2": ("{k} Kantone", "{k} cantons", "{k} Cantoni", "{k} cantons"),
    "ad": ("Beschlossen, noch nicht in Kraft", "Adopté, pas encore en vigueur", "Adottato, non ancora in vigore", "Adopted, not yet in force"),
    "ad2": ("AS und Referendumsvorlagen", "RO et projets soumis au référendum", "RU e progetti soggetti a referendum", "Official Compilation and bills subject to referendum"),
    "vl": ("Vernehmlassungen", "Consultations", "Consultazioni", "Consultations"),
    "vl2": ("Entwürfe des Bundes, {o} offen", "projets de la Confédération, {o} ouvertes", "progetti della Confederazione, {o} aperte", "federal drafts, {o} open"),
    "stand": ("Stand {d}. Die Karte dazu – wie die Erlasse aufeinander aufbauen und wie Gerichte sie zitieren: [Atlas des Schweizer Rechts]({site}).",
              "État au {d}. La carte qui l’accompagne – comment les actes reposent les uns sur les autres et comment les tribunaux les citent : [Atlas du droit suisse]({site}).",
              "Stato al {d}. La carta che lo accompagna – come gli atti poggiano gli uni sugli altri e come i tribunali li citano: [Atlante del diritto svizzero]({site}).",
              "As of {d}. The map that goes with it – how the acts rest on one another and how courts cite them: [Atlas of Swiss Law]({site})."),
    "most": ("Häufig gebraucht", "Souvent consultés", "Spesso consultati", "Often used"),
    "use": ("Benutzen", "Utiliser", "Usare", "Use"),
    "cmd": (("das Obligationenrecht, heute", "jede Fassung seit {y}, mit den Änderungen", "das OR am 1. Juli 2023 (ein Git-Tag für jeden Monatsersten)",
             "an einem beliebigen Tag: der letzte Commit bis dahin, Mittag Zürcher Zeit", "was sich 2025 in Zürich und im Sozialversicherungsrecht änderte",
             "welche Fassung jede Zeile geschrieben hat", "suchen", "jede Datei mit Nummer, Titel, Fassung und Quelle", "mit den Fassungen, die erst später gelten"),
            ("le Code des obligations, aujourd’hui", "chaque version depuis {y}, avec les modifications", "le CO au 1er juillet 2023 (une étiquette par premier du mois)",
             "à n’importe quel jour : le dernier commit jusque-là, midi heure de Zurich", "ce qui a changé en 2025 à Zurich et en droit des assurances sociales",
             "quelle version a écrit chaque ligne", "chercher", "chaque fichier avec numéro, titre, version et source", "avec les versions qui ne s’appliquent que plus tard"),
            ("il Codice delle obbligazioni, oggi", "ogni versione dal {y}, con le modifiche", "il CO al 1° luglio 2023 (un tag per ogni primo del mese)",
             "a un giorno qualsiasi: l’ultimo commit fino ad allora, mezzogiorno ora di Zurigo", "che cosa è cambiato nel 2025 a Zurigo e nelle assicurazioni sociali",
             "quale versione ha scritto ogni riga", "cercare", "ogni file con numero, titolo, versione e fonte", "con le versioni che si applicano solo più tardi"),
            ("the Code of Obligations, today", "every version since {y}, with what changed", "the CO on 1 July 2023 (a tag for the first of every month)",
             "on any day: the last commit up to it, noon Zurich time", "what changed in 2025 in Zurich and in social insurance law",
             "which version wrote each line", "search", "every file with number, title, version and source", "with the versions that apply only later")),
    "anchor": ("Jeder Artikel ist eine Überschrift und damit verlinkbar: [`ch/2/220/{l}.md#art-41`](ch/2/220/{l}.md#art-41). [AGENTS.md](AGENTS.md) "
               "beschreibt Aufbau und jedes Feld für Programme und KI-Agenten.",
               "Chaque article est un titre, donc un lien : [`ch/2/220/{l}.md#art-41`](ch/2/220/{l}.md#art-41). [AGENTS.md](AGENTS.md) "
               "décrit la structure et chaque champ pour les programmes et les agents d’IA.",
               "Ogni articolo è un titolo, quindi un link: [`ch/2/220/{l}.md#art-41`](ch/2/220/{l}.md#art-41). [AGENTS.md](AGENTS.md) "
               "descrive la struttura e ogni campo per programmi e agenti di IA.",
               "Every article is a heading, so it can be linked: [`ch/2/220/{l}.md#art-41`](ch/2/220/{l}.md#art-41). [AGENTS.md](AGENTS.md) "
               "documents the layout and every field for programs and AI agents."),
    "layout": ("Aufbau", "Structure", "Struttura", "Layout"),
    "lay": (("Pfad", "Inhalt", "Bundesrecht in Kraft; Bereich = erste Ziffer der SR-Nummer, Staatsverträge 0.1 – 0.9",
             "kantonales Recht; Ordner nach dem ersten Zeichen der Nummer der kantonalen Sammlung",
             "in der AS veröffentlicht, noch nicht in Kraft (bis zum Inkrafttreten); Referendumsvorlagen aus dem BBl (bis zur AS, zum Ablauf der Frist oder zur Ablehnung)",
             "Vernehmlassungsvorlagen des Bundes, ab Eröffnung; nach dem Ende der Frist «abgeschlossen»",
             "`main` gilt bis heute; `future` enthält zusätzlich die bereits veröffentlichten künftigen Fassungen; Tags `stand/JJJJ-MM-01` den Stand jedes Monatsersten."),
            ("Chemin", "Contenu", "droit fédéral en vigueur ; domaine = premier chiffre du numéro RS, traités 0.1 – 0.9",
             "droit cantonal ; dossiers selon le premier caractère du numéro du recueil cantonal",
             "publié au RO, pas encore en vigueur (jusqu’à l’entrée en vigueur) ; projets soumis au référendum (FF) jusqu’au RO, à l’échéance du délai ou au rejet",
             "projets mis en consultation par la Confédération, dès l’ouverture ; « clos » après le délai",
             "`main` vaut jusqu’à aujourd’hui ; `future` contient en plus les versions futures déjà publiées ; les tags `stand/AAAA-MM-01` l’état au premier de chaque mois."),
            ("Percorso", "Contenuto", "diritto federale in vigore; settore = prima cifra del numero RS, trattati 0.1 – 0.9",
             "diritto cantonale; cartelle secondo il primo carattere del numero della raccolta cantonale",
             "pubblicato nella RU, non ancora in vigore (fino all’entrata in vigore); progetti soggetti a referendum (FF) fino alla RU, alla scadenza del termine o al rifiuto",
             "progetti posti in consultazione dalla Confederazione, dall’apertura; «chiusa» dopo il termine",
             "`main` vale fino a oggi; `future` contiene in più le versioni future già pubblicate; i tag `stand/AAAA-MM-01` lo stato al primo di ogni mese."),
            ("Path", "Content", "federal law in force; area = first digit of the SR number, treaties 0.1 – 0.9",
             "cantonal law; folders by the first character of the number in the cantonal collection",
             "published in the Official Compilation, not yet in force (until it enters into force); bills subject to referendum (Federal Gazette) until the Official Compilation, the deadline or a rejection",
             "federal consultation drafts, from their opening; “closed” after the deadline",
             "`main` applies up to today; `future` adds the versions already published for a later day; tags `stand/YYYY-MM-01` the state on the first of every month.")),
    "file": (("Eine Datei", "Kopf (YAML): Nummer, Titel, Kurztitel, Sprache, Fassung (gilt ab), Beschluss, Inkrafttreten, Quelle",
              "Titel, Ingress, Gliederung als Überschriften, jeder Artikel `#### Art. N`", "jeder Absatz eine Zeile (`<sup>1</sup> …`), damit Diffs und `blame` genau sind",
              "Fussnoten (Änderungen mit Fundstelle) gleich nach ihrem Artikel; Tabellen als HTML"),
             ("Un fichier", "en-tête (YAML) : numéro, titre, titre abrégé, langue, version (dès le), adoption, entrée en vigueur, source",
              "titre, préambule, structure en titres, chaque article `#### Art. N`", "chaque alinéa sur une ligne (`<sup>1</sup> …`), pour des diffs et un `blame` exacts",
              "notes (modifications avec leur référence) juste après leur article ; tableaux en HTML"),
             ("Un file", "intestazione (YAML): numero, titolo, titolo breve, lingua, versione (dal), adozione, entrata in vigore, fonte",
              "titolo, ingresso, struttura in titoli, ogni articolo `#### Art. N`", "ogni capoverso su una riga (`<sup>1</sup> …`), per diff e `blame` esatti",
              "note (modifiche con riferimento) subito dopo il loro articolo; tabelle in HTML"),
             ("A file", "front matter (YAML): number, title, short title, language, version (applies from), adoption, entry into force, source",
              "title, preamble, the structure as headings, each article `#### Art. N`", "each paragraph on one line (`<sup>1</sup> …`), so diffs and `blame` are exact",
              "footnotes (amendments with their reference) right after their article; tables as HTML")),
    "src": ("Quellen und Prüfung", "Sources et contrôle", "Fonti e controllo", "Sources and checks"),
    "srcs": (("Bund: die konsolidierten Fassungen auf [Fedlex](https://www.fedlex.admin.ch) als XML (Akoma Ntoso), jede Fassung seit {start}; AS, BBl und Vernehmlassungen ebenfalls von Fedlex.",
              "Kantone: die systematischen Sammlungen – 19 auf LexWork, die Waadt (BLV) und Zürich (zh.ch) mit jeder Fassung seit {start}; Genf und Neuenburg (SIL) und der Jura (RSJU) mit dem geltenden Text. Erlasse, die seit {start} aufgehoben wurden, stehen bis zu ihrer Aufhebung im Repository.",
              "Geprüft wird jede Datei: Jedes Wort der Quelle muss im Markdown stehen."),
             ("Confédération : les versions consolidées sur [Fedlex](https://www.fedlex.admin.ch) en XML (Akoma Ntoso), chaque version depuis le {start} ; RO, FF et consultations également de Fedlex.",
              "Cantons : les recueils systématiques – 19 sur LexWork, Vaud (BLV) et Zurich (zh.ch) avec chaque version depuis le {start} ; Genève et Neuchâtel (SIL) et le Jura (RSJU) avec le texte en vigueur. Les actes abrogés depuis le {start} y figurent jusqu’à leur abrogation.",
              "Chaque fichier est contrôlé : chaque mot de la source doit figurer dans le Markdown."),
             ("Confederazione: le versioni consolidate su [Fedlex](https://www.fedlex.admin.ch) in XML (Akoma Ntoso), ogni versione dal {start}; RU, FF e consultazioni pure da Fedlex.",
              "Cantoni: le raccolte sistematiche – 19 su LexWork, Vaud (BLV) e Zurigo (zh.ch) con ogni versione dal {start}; Ginevra e Neuchâtel (SIL) e il Giura (RSJU) con il testo in vigore. Gli atti abrogati dal {start} vi figurano fino alla loro abrogazione.",
              "Ogni file è controllato: ogni parola della fonte deve figurare nel Markdown."),
             ("Confederation: the consolidated versions on [Fedlex](https://www.fedlex.admin.ch) as XML (Akoma Ntoso), every version since {start}; the Official Compilation, the Federal Gazette and consultations from Fedlex too.",
              "Cantons: the classified collections – 19 on LexWork, Vaud (BLV) and Zurich (zh.ch) with every version since {start}; Geneva and Neuchâtel (SIL) and Jura (RSJU) with the text in force. Acts repealed since {start} are included up to their repeal.",
              "Every file is checked: every word of the source must be in the Markdown.")),
    "chk": (("Quelle", "Dateien", "Wörter der Quelle", "fehlen"), ("Source", "Fichiers", "Mots de la source", "manquent"),
            ("Fonte", "File", "Parole della fonte", "mancano"), ("Source", "Files", "Words of the source", "missing")),
    "chkrow": ({"ch": "Bund (Fedlex, XML)", "lexwork": "Kantone, LexWork (strukturiert)", "lexwork_pdf": "Kantone, LexWork (aus dem PDF gelesen)",
                "vd": "Waadt (BLV)", "sil": "Genf, Neuenburg (SIL)", "zh": "Zürich (aus dem PDF gelesen)", "ju": "Jura (aus dem PDF gelesen)",
                "asbbl": "AS und BBl (XML)", "cons": "Vernehmlassungen (aus dem PDF gelesen)"},
               {"ch": "Confédération (Fedlex, XML)", "lexwork": "Cantons, LexWork (structuré)", "lexwork_pdf": "Cantons, LexWork (lu dans le PDF)",
                "vd": "Vaud (BLV)", "sil": "Genève, Neuchâtel (SIL)", "zh": "Zurich (lu dans le PDF)", "ju": "Jura (lu dans le PDF)",
                "asbbl": "RO et FF (XML)", "cons": "Consultations (lu dans le PDF)"},
               {"ch": "Confederazione (Fedlex, XML)", "lexwork": "Cantoni, LexWork (strutturato)", "lexwork_pdf": "Cantoni, LexWork (letto dal PDF)",
                "vd": "Vaud (BLV)", "sil": "Ginevra, Neuchâtel (SIL)", "zh": "Zurigo (letto dal PDF)", "ju": "Giura (letto dal PDF)",
                "asbbl": "RU e FF (XML)", "cons": "Consultazioni (letto dal PDF)"},
               {"ch": "Confederation (Fedlex, XML)", "lexwork": "Cantons, LexWork (structured)", "lexwork_pdf": "Cantons, LexWork (read from the PDF)",
                "vd": "Vaud (BLV)", "sil": "Geneva, Neuchâtel (SIL)", "zh": "Zurich (read from the PDF)", "ju": "Jura (read from the PDF)",
                "asbbl": "Official Compilation and Gazette (XML)", "cons": "Consultations (read from the PDF)"}),
    "pdfnote": ("Aus dem PDF gelesene Texte tragen `text: pdf` im Kopf: Ihre Wörter sind geprüft, ihre Gliederung ist aus dem Satzbild erschlossen und nicht geprüft. Im Zweifel gilt das PDF, das der Kopf nennt.",
                "Les textes lus dans le PDF portent `text: pdf` dans l’en-tête : leurs mots sont contrôlés, leur structure est déduite de la mise en page et non contrôlée. En cas de doute, le PDF indiqué fait foi.",
                "I testi letti dal PDF recano `text: pdf` nell’intestazione: le loro parole sono controllate, la struttura è dedotta dall’impaginazione e non controllata. In caso di dubbio fa stato il PDF indicato.",
                "Texts read from a PDF carry `text: pdf` in their front matter: their words are checked, their structure is inferred from the layout and not checked. When in doubt, the PDF named there is authoritative."),
    "lim": ("Grenzen", "Limites", "Limiti", "Limits"),
    "lims": (("Fassungen vor 2021 (Fedlex führt sie nur als PDF und Word) und Erlasse, die vor 2021 aufgehoben wurden.",
              "Frühere Fassungen in Genf, Neuenburg und im Jura (die Kantone veröffentlichen nur den geltenden Text); die Kantone Tessin und Schwyz.",
              "Erlasse der AS und Referendumsvorlagen, die Fedlex nur als PDF führt ({a} bzw. {b}, fast alle 2020–2022).",
              "Von den Vernehmlassungen nur die Vorlagen, nicht die erläuternden Berichte."),
             ("Les versions antérieures à 2021 (Fedlex ne les offre qu’en PDF et Word) et les actes abrogés avant 2021.",
              "Les versions antérieures à Genève, Neuchâtel et dans le Jura (les cantons ne publient que le texte en vigueur) ; les cantons du Tessin et de Schwyz.",
              "Les actes du RO et projets soumis au référendum que Fedlex n’offre qu’en PDF ({a} et {b}, presque tous 2020–2022).",
              "Des consultations, seuls les projets, pas les rapports explicatifs."),
             ("Le versioni anteriori al 2021 (Fedlex le offre solo in PDF e Word) e gli atti abrogati prima del 2021.",
              "Le versioni anteriori a Ginevra, Neuchâtel e nel Giura (i Cantoni pubblicano solo il testo in vigore); i Cantoni Ticino e Svitto.",
              "Gli atti della RU e i progetti soggetti a referendum che Fedlex offre solo in PDF ({a} e {b}, quasi tutti 2020–2022).",
              "Delle consultazioni, solo i progetti, non i rapporti esplicativi."),
             ("Versions before 2021 (Fedlex offers them as PDF and Word only) and acts repealed before 2021.",
              "Earlier versions in Geneva, Neuchâtel and Jura (the cantons publish only the text in force); the cantons of Ticino and Schwyz.",
              "Acts of the Official Compilation and bills subject to referendum that Fedlex offers as PDF only ({a} and {b}, nearly all 2020–2022).",
              "Of the consultations, the drafts only, not the explanatory reports.")),
    "lic": ("Lizenz und Zitieren", "Licence et citation", "Licenza e citazione", "Licence and citation"),
    "lics": ("Erlasse und ihre Übersetzungen sind urheberrechtlich nicht geschützt (Art. 5 Abs. 1 Bst. a URG). Die Aufbereitung – Kopfdaten, Verzeichnisse, Gliederung – steht unter [CC0](LICENSE). "
             "Zitiert wird das Recht nach der amtlichen Veröffentlichung; dieses Repository nach [CITATION.cff](CITATION.cff). Erzeugt mit den Skripten in "
             "[`jonashertner/swiss-law-graph`](https://github.com/jonashertner/swiss-law-graph) (`pipeline/lawgit/`). Ein Projekt von [Jonas Hertner](https://jonashertner.com).",
             "Les actes et leurs traductions ne sont pas protégés par le droit d’auteur (art. 5, al. 1, let. a LDA). La mise en forme – en-têtes, répertoires, structure – est sous [CC0](LICENSE). "
             "Le droit se cite d’après la publication officielle ; ce dépôt d’après [CITATION.cff](CITATION.cff). Produit avec les scripts de "
             "[`jonashertner/swiss-law-graph`](https://github.com/jonashertner/swiss-law-graph) (`pipeline/lawgit/`). Un projet de [Jonas Hertner](https://jonashertner.com).",
             "Gli atti e le loro traduzioni non sono protetti dal diritto d’autore (art. 5 cpv. 1 lett. a LDA). La preparazione – intestazioni, indici, struttura – è sotto [CC0](LICENSE). "
             "Il diritto si cita secondo la pubblicazione ufficiale; questo repository secondo [CITATION.cff](CITATION.cff). Prodotto con gli script di "
             "[`jonashertner/swiss-law-graph`](https://github.com/jonashertner/swiss-law-graph) (`pipeline/lawgit/`). Un progetto di [Jonas Hertner](https://jonashertner.com).",
             "Acts and their translations are not protected by copyright (Art. 5 para. 1 let. a CopA). The preparation – front matter, indexes, structure – is [CC0](LICENSE). "
             "Cite the law by its official publication; this repository by [CITATION.cff](CITATION.cff). Made with the scripts in "
             "[`jonashertner/swiss-law-graph`](https://github.com/jonashertner/swiss-law-graph) (`pipeline/lawgit/`). A project by [Jonas Hertner](https://jonashertner.com)."),
}


def tr(key, lg):
    return T[key][LANGS.index(lg)]


def langbar(lg: str) -> str:
    return " · ".join(f"**{LNAME[x]}**" if x == lg else f"[{LNAME[x]}]({FILE[x]})" for x in LANGS)


# ---------------------------------------------------------------- the front page
def front(lg, start, today, snaps, facts, cnt, nver, chk, nopdf, nopen):
    by_sr = {a["sr"]: a for a in facts.values() if a.get("sr") and a["path"] in snaps}
    most = []
    for sr in MOST:
        a = by_sr.get(sr)
        if not a:
            continue
        files = snaps[a["path"]]
        f = lg if lg in files else "de"
        short = front_of(files[f]).get("short") or a.get("short") or sr
        most.append(f"[{short}]({a['path']}/{f}.md)")
    th = tr("th", lg)
    y = start[:4]
    rows = [f"| [{tr('fed', lg)}](ch/README.md) · {tr('fed2', lg)} | {n(cnt['ch'], lg)} | {n(nver.get('ch', 0), lg)} |",
            f"| [{tr('kt', lg)}](cantons/README.md) · {tr('kt2', lg).format(k=cnt['nkt'])} | {n(cnt['cantons'], lg)} | {n(nver.get('cantons', 0), lg)} |",
            f"| [{tr('ad', lg)}](adopted/README.md) · {tr('ad2', lg)} | {n(cnt['adopted'], lg)} | |",
            f"| [{tr('vl', lg)}](consultations/README.md) · {tr('vl2', lg).format(o=n(nopen, lg))} | {n(cnt['consultations'], lg)} | |"]
    c = tr("cmd", lg)
    cl = lg
    cmds = [f"cat ch/2/220/{cl}.md", f"git log --follow -p -- ch/2/220/{cl}.md", f"git show stand/2023-07-01:ch/2/220/{cl}.md",
            f"git show \"$(git rev-list -1 --before='2023-06-30 12:00 +0200' main)\":ch/2/220/{cl}.md",
            "git log --since=2025-01-01 --until=2026-01-01 --stat -- cantons/zh ch/8", f"git blame ch/2/220/{cl}.md",
            f"git grep -n \"{GOOD[lg]}\" -- 'ch/*/{cl}.md'", "grep ',220,' index.csv", "git checkout future"]
    code = [x for k, cmd in enumerate(cmds) for x in (("" if k else None), f"# {c[k].format(y=y)}", cmd) if x is not None]
    lay = tr("lay", lg)
    fl = tr("file", lg)
    ck = tr("chk", lg)
    cr = tr("chkrow", lg)
    chk_rows = []
    for key in ("ch", "lexwork", "lexwork_pdf", "vd", "sil", "zh", "ju", "asbbl", "cons"):
        if key in chk and chk[key][0]:
            files_, words, miss = chk[key]
            chk_rows.append(f"| {cr[key]} | {n(files_, lg)} | {n(words, lg)} | {n(miss, lg)} |")
    s = tr("srcs", lg)
    out = [f"# {tr('title', lg)}", "", langbar(lg), "", tr("lede", lg).format(start=day(start, lg)), "", f"> {tr('notice', lg)}", "",
           f"| {th[0]} | {th[1]} | {th[2].format(y=y)} |", "|:---|---:|---:|", *rows, "",
           tr("stand", lg).format(d=day(today, lg), site=SITE), "",
           f"**{tr('most', lg)}**{' :' if lg == 'fr' else ':'} " + " · ".join(most), "",
           f"## {tr('use', lg)}", "", "```sh", *code, "```", "", tr("anchor", lg).format(l=cl), "",
           f"## {tr('layout', lg)}", "", f"| {lay[0]} | {lay[1]} |", "|:---|:---|",
           f"| `ch/<1–9 \\| 0.1–0.9>/<SR>/<lang>.md` | {lay[2]} |", f"| `cantons/<ct>/<x>/<nr>/<lang>.md` | {lay[3]} |",
           f"| `adopted/as/…`, `adopted/bbl/…` | {lay[4]} |", f"| `consultations/<year>/<nr>/` | {lay[5]} |",
           f"| `index.csv`, `index.jsonl` | {c[7]} |", "", lay[6], "",
           f"**{fl[0]}**{' :' if lg == 'fr' else ':'} " + (" ; " if lg == "fr" else "; ").join(fl[1:]) + ".", "",
           f"## {tr('src', lg)}", "", *[f"- {x.format(start=day(start, lg))}" for x in s], "",
           f"| {ck[0]} | {ck[1]} | {ck[2]} | {ck[3]} |", "|:---|---:|---:|---:|", *chk_rows, "", tr("pdfnote", lg), "",
           f"## {tr('lim', lg)}", "", *[f"- {x.format(a=n(nopdf[0], lg), b=n(nopdf[1], lg))}" for x in tr("lims", lg)], "",
           f"## {tr('lic', lg)}", "", tr("lics", lg), ""]
    return "\n".join(out)


# ---------------------------------------------------------------- the parts
HDR = {"de": ("Nummer", "Abkürzung", "Titel", "Sprachen", "Erlasse in Kraft am {d}", "zurück", "aus dem PDF gelesen"),
       "fr": ("Numéro", "Abréviation", "Titre", "Langues", "actes en vigueur au {d}", "retour", "lu dans le PDF")}


def area_readme(grp, rows, today, names):
    nm = names.get(grp, {})
    head = " · ".join(dict.fromkeys(x for x in (nm.get("de"), nm.get("fr"), nm.get("it")) if x)) or grp
    t = [f"# {grp} · {head}", "", f"{n(len(rows))} Erlasse in Kraft am {day(today, 'de')} · [Bundesrecht](../README.md) · [Schweizer Recht](../../README.md)", "",
         "| SR | Abkürzung | Titel | Sprachen |", "|:---|:---|:---|:---|"]
    t += [f"| {cell(sr)} | {cell(sh)} | {cell(ti)} | " + " ".join(f"[{lg}]({p.split('/', 2)[2]}/{lg}.md)" for lg in ls) + " |" for sr, sh, ti, p, ls in rows]
    return "\n".join(t) + "\n"


def canton_readme(ct, rows, today):
    lg = OWN.get(ct, "de") if OWN.get(ct, "de") in HDR else "de"
    h = HDR[lg]
    name = CT[ct][1] if lg == "fr" else CT[ct][0]
    other = CT[ct][0] if lg == "fr" else CT[ct][1]
    npdf = sum(1 for r in rows if r[5] == "pdf")
    title = {"VS": "Canton du Valais", "JU": "Canton du Jura"}.get(ct) or (f"Canton de {name}" if lg == "fr" else f"Kanton {name}")
    sub = f"{n(len(rows), lg)} {h[4].format(d=day(today, lg))}" + (f" · {n(npdf, lg)} {h[6]}" if npdf else "")
    t = [f"# {title}" + (f" · {other}" if other != name else ""), "", sub + f" · [{('Kantone' if lg == 'de' else 'Cantons')}](../README.md)", "",
         f"| {h[0]} | {h[1]} | {h[2]} | {h[3]} |", "|:---|:---|:---|:---|"]
    t += [f"| {cell(nr)} | {cell(sh)} | {cell(ti)}{' ¹' if pdf == 'pdf' else ''} | " + " ".join(f"[{x}]({p.split('/', 2)[2]}/{x}.md)" for x in ls) + " |"
          for nr, sh, ti, p, ls, pdf in rows]
    if npdf:
        t += ["", "¹ " + ("Der Kanton veröffentlicht diese Fassung nur als PDF; der Text ist daraus gelesen (`text: pdf`)." if lg == "de" else
                          "Le canton ne publie cette version qu’en PDF ; le texte en est extrait (`text: pdf`).")]
    return "\n".join(t) + "\n"


def cantons_readme(kt, today, nver):
    src = {**{c: "LexWork" for c in LEXWORK}, "VD": "BLV", "ZH": "zh.ch (PDF)", "GE": "SIL", "NE": "SIL", "JU": "RSJU (PDF)"}
    hist = {**{c: "jede Fassung seit 2021" for c in LEXWORK | {"VD", "ZH"}}, "GE": "geltender Text", "NE": "geltender Text", "JU": "geltender Text"}
    t = ["# Kantonales Recht · Droit cantonal · Diritto cantonale", "",
         f"{n(sum(len(v) for v in kt.values()))} Erlasse in Kraft am {day(today, 'de')}, {len(kt)} Kantone in der Reihenfolge der Bundesverfassung (Art. 1 BV). "
         "[Schweizer Recht](../README.md)", "",
         "| Kanton | Erlasse | Fassungen seit 2021 | Quelle | Geschichte |", "|:---|---:|---:|:---|:---|"]
    for ct in ORDER:
        if ct in kt:
            t.append(f"| [{ct} · {CT[ct][1] if OWN.get(ct) == 'fr' else CT[ct][2] if OWN.get(ct) == 'it' else CT[ct][0]}]({ct.lower()}/README.md) | "
                     f"{n(len(kt[ct]))} | {n(nver.get('ct:' + ct, 0))} | {src.get(ct, '')} | {hist.get(ct, '')} |")
        else:
            t.append(f"| {ct} · {CT[ct][2] if OWN.get(ct) == 'it' else CT[ct][0]} | – | – | – | nicht enthalten |")
    return "\n".join(t) + "\n"


# ---------------------------------------------------------------- every file of the repository's own
# The tags stand/YYYY-MM-01 are written on GitHub's side: the build's own tags cannot be pushed from where it runs.
# Same rule as build_repo.month_tags (checked: identical for all 70 months of the run of 2026-10-27).
STAND_WORKFLOW = """\
# stand/YYYY-MM-01: the law as it applied on the first of every month –
# the last commit of main dated on or before that day, 00:00 Zurich time
# (every commit is dated on the day its version applies).
name: stand
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: write
jobs:
  tags:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          filter: blob:none
          sparse-checkout: .github
      - name: tag the first of every month
        env:
          TZ: Europe/Zurich
        run: |
          root=$(git rev-list --max-parents=0 HEAD)
          first=$(git log -1 --format=%cd --date=format-local:%Y-%m "$root")
          y=${first%-*}; m=$((10#${first#*-})); now=$(date +%Y-%m-%d)
          while :; do
            d=$(printf '%04d-%02d-01' "$y" "$m"); [[ "$d" > "$now" ]] && break
            c=$(git rev-list -1 --before="$d 00:00:00" HEAD || true)
            [[ -n "$c" ]] && git tag -f "stand/$d" "$c" >/dev/null
            if (( m == 12 )); then y=$((y + 1)); m=1; else m=$((m + 1)); fi
          done
          git push -f origin 'refs/tags/stand/*:refs/tags/stand/*'
"""


def files(snaps: dict, facts: dict, kacts: dict, start: str, today: str, future=(), nver=None) -> dict:
    nver = nver or {}
    out = {}
    names = area_names()
    by_path = {a["path"]: a for a in facts.values()}
    fed = defaultdict(list)
    kt = defaultdict(list)
    kby = {a["path"]: a for a in kacts.values()}
    for path, langs in snaps.items():
        k = kind_of(path)
        if k in ("federal", "treaty"):
            a = by_path.get(path) or {}
            fed[path.split("/")[1]].append((a.get("sr") or path.split("/")[2], a.get("short") or "", a.get("title") or "", path, sorted(langs)))
        elif k == "cantonal":
            a = kby.get(path) or {}
            kt[path.split("/")[1].upper()].append((a.get("nr") or path.split("/")[3], a.get("short") or "", a.get("title") or "", path, sorted(langs),
                                                    "pdf" if any("\ntext: pdf\n" in snaps[path][lg] for lg in langs) else ""))
    for grp, rows in fed.items():
        rows.sort(key=lambda r: srkey(r[0]))
        out[f"ch/{grp}/README.md"] = area_readme(grp, rows, today, names)
    order = sorted(fed, key=lambda g: (g.startswith("0."), srkey(g)))
    t = ["# Bundesrecht · Droit fédéral · Diritto federale", "",
         f"{n(sum(len(v) for v in fed.values()))} Erlasse in Kraft am {day(today, 'de')}, in den Bereichen der Systematischen Rechtssammlung (SR). "
         "[Schweizer Recht](../README.md)", "", "| SR | Bereich · domaine · settore | Erlasse |", "|:---|:---|---:|"]
    for g in order:
        nm = names.get(g, {})
        t.append(f"| [{g}]({g}/README.md) | {' · '.join(dict.fromkeys(x for x in (nm.get('de'), nm.get('fr'), nm.get('it')) if x))} | {n(len(fed[g]))} |")
    out["ch/README.md"] = "\n".join(t) + "\n"
    for ct, rows in kt.items():
        rows.sort(key=lambda r: srkey(r[0]))
        out[f"cantons/{ct.lower()}/README.md"] = canton_readme(ct, rows, today)
    out["cantons/README.md"] = cantons_readme(kt, today, nver)

    # adopted, not yet in force; consultations
    def fm(path, key):
        txt = next((snaps[path][lg] for lg in ("de", "fr", "it") if lg in snaps[path]), next(iter(snaps[path].values()), ""))
        v = front_of(txt).get(key) or ""
        return ", ".join(v) if isinstance(v, list) else v
    pend = sorted(p for p in snaps if p.startswith("adopted/"))
    t = ["# Beschlossen, noch nicht in Kraft · Adopté, pas encore en vigueur · Adottato, non ancora in vigore", "",
         f"Stand {day(today, 'de')}. Erlasse der Amtlichen Sammlung (AS), die veröffentlicht sind, aber erst später in Kraft treten, und "
         "Referendumsvorlagen aus dem Bundesblatt (BBl) während der Referendumsfrist bzw. bis zur Veröffentlichung in der AS. "
         "Tritt ein Erlass in Kraft, verschwindet er hier und steht in seiner konsolidierten Fassung unter [ch/](../ch/README.md). "
         "[Schweizer Recht](../README.md)", "",
         "| Fundstelle | Titel | Inkrafttreten | Referendumsfrist | Sprachen |", "|:---|:---|:---|:---|:---|"]
    for p in sorted(pend, key=lambda p: (fm(p, "in_force") or fm(p, "referendum_deadline"), p)):
        t.append(f"| {cell(fm(p, 'reference'))} | {cell(fm(p, 'title'))} | {cell(fm(p, 'in_force'))} | {cell(fm(p, 'referendum_deadline'))} | "
                 + " ".join(f"[{lg}]({p.split('/', 1)[1]}/{lg}.md)" for lg in sorted(snaps[p])) + " |")
    if future:
        byj = Counter(jur for d, jur, p, lab in future)
        t += ["", "## Künftige konsolidierte Fassungen (Branch `future`)", "",
              "Fassungen, die Bund und Kantone bereits konsolidiert veröffentlichen, die aber erst später gelten: "
              + ", ".join(f"{'Bund' if j == 'ch' else j} {n(c)}" for j, c in sorted(byj.items(), key=lambda kv: (kv[0] != "ch", kv[0])))
              + ". `git checkout future` zeigt sie im Text.", "", "| Gilt ab | Erlass | Datei (future) |", "|:---|:---|:---|"]
        t += [f"| {d} | {cell(lab)} | [{p}](../../../tree/future/{p}) |" for d, jur, p, lab in future]
    out["adopted/README.md"] = "\n".join(t) + "\n"
    vl = sorted(p for p in snaps if p.startswith("consultations/"))
    closed = lambda p: "abgeschlossen" in fm(p, "status")
    t = ["# Vernehmlassungen · Consultations · Consultazioni", "",
         f"Stand {day(today, 'de')}. Die Vernehmlassungsvorlagen des Bundes seit {start[:4]} – Entwürfe, kein geltendes Recht –, aus den PDF auf "
         "Fedlex gelesen. Offene zuerst (nach Frist), dann die abgeschlossenen (neueste zuerst). [Schweizer Recht](../README.md)", "",
         "| Eröffnet | Frist | Status | Vorlage | Dateien |", "|:---|:---|:---|:---|:---|"]
    for p in sorted(vl, key=lambda p: (closed(p), "" if closed(p) else fm(p, "closes"), "".join(chr(255 - ord(ch)) for ch in fm(p, "opened")))):
        t.append(f"| {fm(p, 'opened')} | {fm(p, 'closes')} | {'abgeschlossen' if closed(p) else '**offen**'} | {cell(fm(p, 'title'))} | "
                 + " ".join(f"[{lg}]({p.split('/', 1)[1]}/{lg}.md)" for lg in sorted(snaps[p])) + " |")
    out["consultations/README.md"] = "\n".join(t) + "\n"

    # the front page in four languages
    cnt = {"ch": sum(len(v) for v in fed.values()), "cantons": sum(len(v) for v in kt.values()), "nkt": len(kt),
           "adopted": len(pend), "consultations": len(vl)}
    P = B / "pending"
    nopdf = (sum(1 for a in json.load(open(P / "as.json")) if not a["xml"]) if (P / "as.json").exists() else 0,
             sum(1 for a in json.load(open(P / "ref.json")) if not a["xml"]) if (P / "ref.json").exists() else 0)
    chk = checks()
    nopen = sum(1 for p in vl if not closed(p))
    for lg in LANGS:
        out[FILE[lg]] = front(lg, start, today, snaps, facts, cnt, nver, chk, nopdf, nopen)

    # for programs: the indexes, the guide; the licence, how to cite, line endings
    rows = index_rows(snaps)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=INDEX_COLS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    out["index.csv"] = buf.getvalue()
    out["index.jsonl"] = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    out["AGENTS.md"] = agents(len(rows), len(snaps), start, today)
    out["LICENSE"] = (Path(__file__).resolve().parent / "CC0-1.0.txt").read_text(encoding="utf-8")
    out["CITATION.cff"] = citation(today)
    out[".gitattributes"] = "* text=auto eol=lf\nindex.csv linguist-generated=true\nindex.jsonl linguist-generated=true\n"
    out[".github/workflows/stand.yml"] = STAND_WORKFLOW
    return out


def citation(today: str) -> str:
    return f"""cff-version: 1.2.0
message: "Not official: cite the law by its official publication (AS/BBl, the cantons' collections). Cite this repository as below."
type: dataset
title: "Schweizer Recht – Swiss federal and cantonal law as a git repository"
abstract: "Every federal act in force and the law of 24 cantons as Markdown, one file per act and language, one commit per version dated on the day it applies, since 2021."
authors:
  - family-names: Hertner
    given-names: Jonas
    website: "https://jonashertner.com"
repository-code: "{REPO}"
url: "{SITE}"
license: CC0-1.0
version: "{today}"
date-released: "{today}"
keywords:
  - Swiss law
  - legislation
  - Fedlex
  - cantonal law
  - git
"""


def agents(nfiles: int, nacts: int, start: str, today: str) -> str:
    """AGENTS.md: the repository for scripts and agents — layout, every field, exact recipes, the limits."""
    return f"""# Using this repository from scripts and agents

Swiss federal law and the law of the cantons, as Markdown: one file per act and language, one commit per version, each
commit dated 00:00 Europe/Zurich on the day its version applies ({start} to {today}). Not official: the official
publication (AS/BBl for the Confederation, the canton's collection) is authoritative. {n(nfiles, 'en')} files, {n(nacts, 'en')} acts and
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
| `text` | where the words come from: `xml` (Fedlex), `html` (the canton's structured text), `pdf` (read from the canton's or Fedlex's PDF: words checked, structure inferred) |
| `url`, `source` | the page of this version; the file it was read from (XML or PDF) |

## Layout

| path | content |
|---|---|
| `ch/<area>/<SR>/<lang>.md` | federal acts in force, area = first digit (treaties: `0.1` … `0.9`) |
| `cantons/<ct>/<first char>/<number>/<lang>.md` | cantonal acts (`cantons/zh/7/700.1/de.md`; characters outside `[A-Za-z0-9._-]` become `_`) |
| `adopted/as/<year>/<nr>/` | acts published in the AS whose entry into force is later; removed on the day they enter into force (they then appear consolidated under `ch/`) |
| `adopted/bbl/<year>/<nr>/` | bills subject to referendum, until their AS publication, the referendum deadline or a rejection at the ballot |
| `consultations/<year>/<nr>/` | federal consultation drafts from their opening; `status: Vernehmlassung abgeschlossen` once closed |
| `README.md` in each directory | human-readable lists |

Branches and tags: `main` = the law as it applied each day up to {today}; `future` = `main` plus versions already
published for a later day; `stand/YYYY-MM-01` = the law on the first of every month (the law only: README and indexes
are in the last commit).

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
- Amending acts (`adopted/as/`): the amended element in bold (`**Art. 6 Abs. 2bis**`) followed by its new text.

## Recipes

```sh
# the law on the first of a month
git show stand/2023-07-01:ch/2/220/de.md;  git worktree add /tmp/law-2023-07 stand/2023-07-01
# the file as it applied on any day: the last commit at or before noon of that day, Zurich time (any machine time zone)
git show "$(git rev-list -1 --before='2023-06-30 12:00 +0200' main)":ch/2/220/de.md
# every version of an act, with what changed
git log --follow -p -- ch/2/220/de.md
# what changed in a canton or an area between two days
git log --since='2025-01-01 12:00 +0100' --until='2025-12-31 12:00 +0100' --name-status -- cantons/zh ch/8
# find an act by number or title words
grep -i ',220,' index.csv;  grep -i 'Raumplanung' index.csv | grep ',cantonal,'
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
- AS acts of 2020–2022 published only as PDF are missing under `adopted/as/`; consultations: drafts only, not the
  explanatory reports.

Made by [Jonas Hertner](https://jonashertner.com) with the scripts in `jonashertner/swiss-law-graph` (`pipeline/lawgit/`).
Texts of acts: not protected by copyright (Art. 5 URG). Front matter, indexes: CC0.
"""
