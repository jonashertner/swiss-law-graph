"""Cantonal acts in force and the bases their Ingresses state (data/cantonal_basis.json).

Input: build/cantonal/<CT>.json from the adapters in pipeline/cantonal/ (one per official
collection; contract in pipeline/cantonal/SPEC.md), data/sr_taxonomy.csv (dated titles of
every federal act in DE/FR/IT), data/fedlex_acts.json (earlier federal acts of cited SR
numbers), data/fedlex_structure.json.gz (articles of the 26 cantonal constitutions).

For every act: the enacting authority (issuer, verbatim) and its floor, and every basis the
Ingress names, resolved to an exact target where the text allows it:
  "SR <n>"   a federal act in force (footnote/inline SR number, or type + date + title),
  "SR <n>@<year>"  an earlier federal act (no longer in force under that number),
  "KV"       the canton's own constitution (with its articles),
  "CT:<n>"   another act of the same canton (footnote/inline number, date, abbreviation),
  "?"        named but not identified (kept verbatim, counted).
A reference is identified by, in this order: its footnote or inline collection number (the
canton's own prefix or SR/RS), the name of a constitution, a fixed federal title (ZGB, OR,
StGB …), the act's type and date matched against the federal or cantonal titles of that
date, or an abbreviation the canton itself states. Nothing is guessed: an act named only as
"die eidgenössische Asylgesetzgebung" stays "?".

Floors (Art. 49 BV: all of them below federal law): 4 = the constitution; 5 = parliament,
people, Landsgemeinde, intercantonal agreements; 6 = government and cantonal courts;
7 = directorates, departments, offices, other bodies (incl. communal bodies some cantons
publish). From the issuer; without one, from the title ("Verordnung des Regierungsrates").

Usage: python3 pipeline/cantonal_basis.py       (~20 s, offline)
"""
import csv
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cantons import CANTON_CONSTITUTION  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = "2026-10-26"
CANTONS = sorted(CANTON_CONSTITUTION)

# ---------- dates ----------
MONTHS = {
    "januar": 1, "jänner": 1, "jenner": 1, "februar": 2, "hornung": 2, "märz": 3, "merz": 3, "april": 4,
    "ostermonat": 4, "mai": 5, "wonnemonat": 5, "juni": 6, "brachmonat": 6, "juli": 7, "heumonat": 7,
    "august": 8, "augstmonat": 8, "september": 9, "herbstmonat": 9, "oktober": 10, "weinmonat": 10,
    "november": 11, "wintermonat": 11, "dezember": 12, "christmonat": 12,
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "juin": 6, "juillet": 7, "août": 8,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6, "luglio": 7,
    "agosto": 8, "settembre": 9, "ottobre": 10, "dicembre": 12,
}
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
# footnote digits are glued to the year in some collections (LU, OW: "vom 20. Oktober 19912" = 1991, note 2)
DATE = re.compile(rf"\b(\d{{1,2}})(?:\.|er|°|º)?\s*({MONTH_RE})\s+((?:1[4-9]|20)\d\d)\d{{0,2}}\b", re.I)
DATE_NUM = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")


def iso(m) -> str:
    return f"{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"


def dates_in(s: str):
    return [(m.start(), m.end(), iso(m)) for m in DATE.finditer(s)]


# ---------- vocabulary ----------
# act types, grouped so that "Gesetz" matches "loi" and "legge" (bilingual cantons, federal titles)
TYPES = [
    ("const", r"(?:Bundes|Kantons|Staats)?verfassung\w*|Verfassung\w*|[Cc]onstitution\w*|[Cc]ostituzione\w*"),
    ("law", r"\w*[Gg]esetz(?:es|e|en)?\b|BG\b|\w*[Gg]esetzbuch\w*|Obligationenrecht\w*|lois?\b|legg[ei]\b|[Cc]ode\b|[Cc]odice\b"),
    ("ord", r"\w*[Vv]erordnung\w*|ordonnances?\b|ordinanz[ae]\b"),
    ("dec", r"\w*[Bb]eschlu(?:ss|ß)\w*|\w*[Dd]ekret\w*|arrêtés?\b|décrets?\b|decret[oi]\b"),
    ("reg", r"\w*[Rr]eglement\w*|règlements?\b|regolament[oi]\b|\w*[Oo]rdnung\b|[Ss]tatut\w*|statuts?\b|statut[oi]\b"),
    ("treaty", r"\w*[Kk]onkordat\w*|\w*[Vv]ereinbarung\w*|Übereinkunft\w*|\w*[Aa]bkommen\w*|Übereinkommen\w*|\w*[Vv]ertrag\w*|"
               r"Protokoll\w*|Notenaustausch\w*|Statut\s+des|protocoles?\b|protocoll[oi]\b|échange\s+de\s+notes|"
               r"concordats?\b|conventions?\b|accords?\b|concordat[oi]\b|convenzion[ei]\b|accord[oi]\b"),
    ("dir", r"\w*[Rr]ichtlinie\w*|\w*[Ww]eisung\w*|directives?\b|direttiv[ae]\b|\w*[Tt]arif\w*|tarifs?\b|tariff[ae]\b"),
]
TYPE_RE = re.compile("|".join(f"(?P<{k}>\\b(?:{v}))" for k, v in TYPES), re.I)
FEDERAL_WORD = re.compile(r"\b(?:Bundes\w*|BG\b|eidgenössisch\w*|[Ss]chweizerisch\w*|fédéra\w*|suisses?\b|federal\w*|svizzer\w*|"
                          r"Confédération|Confederazione|Eidgenossenschaft)")
NOT_ACT = re.compile(r"\b(?:Botschaft|Bericht|Antrag|Vorlage|Gutachten|Vernehmlassung|message|rapport|préavis|projet|proposition|"
                     r"messaggio|rapporto|proposta|progetto)\b", re.I)

KV_NAME = re.compile(
    r"\b(?:Kantonsverfassung|Staatsverfassung|Verfassung\s+(?:des\s+Kantons|von|für\s+den\s+Kanton|des\s+eidgenössischen\s+Standes|"
    r"des\s+Standes|der\s+Republik)[\w\s.\-]{0,40}?|Verfassung(?=\s*\[|\s*\(|\s*vom|\s*,|\s*;|\s+beschliesst|\s*$)|KV\b|"
    r"[Cc]onstitution\s+(?:cantonale|du\s+canton|de\s+la\s+République|vaudoise|jurassienne|neuchâteloise|genevoise|"
    r"fribourgeoise|valaisanne)[\w\s\-]{0,40}?|[Cc]onstitution(?=\s*\[|\s*\(|\s*du\s+\d|\s*;|\s*,)|Cst(?:\.|\b)(?:[ -]?[A-Z]{2}\b)?|"
    r"[Cc]ostituzione\s+(?:cantonale|della\s+Repubblica|del\s+Cantone)[\w\s]{0,40}?|[Cc]ost\.(?:\s?cant\.)?)")
BV_NAME = re.compile(r"\b(?:Bundesverfassung\w*|Constitution\s+fédérale|Costituzione\s+federale|BV\b|Cst\.?\s?féd\.?)")
FIXED = [  # federal acts named without date
    (r"Zivilgesetzbuch\w*|Code\s+civil(?:\s+suisse)?|Codice\s+civile(?:\s+svizzero)?|\bZGB\b|\bCC\b", "210"),
    (r"Obligationenrecht\w*|Code\s+des\s+obligations|Codice\s+delle\s+obbligazioni|\bOR\b|\bCO\b", "220"),
    (r"Strafgesetzbuch\w*|Code\s+pénal(?:\s+suisse)?|Codice\s+penale(?:\s+svizzero)?|\bStGB\b", "311.0"),
    (r"Schweizerische\w*\s+Zivilprozessordnung|Zivilprozessordnung\w*|Code\s+de\s+procédure\s+civile|"
     r"Codice\s+di\s+diritto\s+processuale\s+civile|\bZPO\b", "272"),
    (r"Schweizerische\w*\s+Strafprozessordnung|Strafprozessordnung\w*|Code\s+de\s+procédure\s+pénale|"
     r"Codice\s+di\s+diritto\s+processuale\s+penale|\bStPO\b", "312.0"),
    (r"Jugendstrafprozessordnung\w*|\bJStPO\b", "312.1"),
]
FIXED = [(re.compile(rf"\b(?:{p})"), sr) for p, sr in FIXED]
IMPL = re.compile(r"(?:Einführung\w*|Anwendung\w*|Ausführung\w*|Vollzieh\w*|Vollzug\w*|EG|d['’]application|d['’]introduction|"
                  r"d['’]exécution|di\s+applicazione|d['’]applicazione|di\s+esecuzione|introduttiva|cantonale|kantonal\w*)"
                  r"[\s\w\-–]{0,40}$", re.I)
AMEND = re.compile(r"(?:Fassung|Nachtrag\w*|Änderung|geändert|revidiert|Revision|teneur|modifi\w*|révis\w*|"
                   r"modific\w*|revisione|tenore)[^.;\[]{0,30}$", re.I)
SCHLT = re.compile(r"Schlusstitel\w*|Schlussbestimmung\w*|Übergangsbestimmung\w*|[Tt]itre\s+final|dispositions?\s+finales?|"
                   r"dispositions?\s+transitoires?|[Tt]itolo\s+finale|disposizioni\s+finali|disposizioni\s+transitorie")

# basis clauses and what ends them
BASIS_KW = re.compile(r"\b(?:dans\s+le\s+respect\s+d[eu]|gestützt\s+auf|gestützt(?=\s+(?:§|Art))|gesützt\s+auf|in\s+Hinsicht\s+auf|im\s+Hinblick\s+auf|"
                      r"unter\s+Bezugnahme\s+auf|auf\s+der\s+Grundlage\s+(?:von|des|der)|gemäss|en\s+vertu\s+d[ue]|sur\s+la\s+base\s+d[ue]|"
                      r"in\s+virtù|sulla\s+base|fondandosi\s+su|in\s+Ausführung|in\s+Anwendung|in\s+Vollziehung|in\s+Vollzug|in\s+Umsetzung|"
                      r"aufgrund|auf\s+Grund|vu|vus|en\s+application|en\s+exécution|conformément\s+à|"
                      r"vist[oaie]|richiamat[oaie]|in\s+applicazione|in\s+esecuzione|conformemente)\b", re.I)
STOP_KW = re.compile(r"\b(?:vereinbaren|treffen|schliessen\s+(?:folgende|nachstehende)|conviennent|concluent|convengono|auf\s+Antrag|nach\s+Einsicht\w*|nach\s+Kenntnisnahme|in\s+Erwägung|in\s+der\s+Absicht|"
                     r"beschliess\w*|verordne\w*|erlässt|erlassen|verfügt|setzt\b|sur\s+(?:la\s+)?proposition|considérant|"
                     r"après\s+avoir|décrète|arrête\b|adopte|édicte|ordonne|su\s+proposta|decreta|risolve|ordina|emana|"
                     r"considerato|ritenuto)\b", re.I)
HEAD_CUT = re.compile(r"\b(?:gestützt\s+auf|in\s+Ausführung|in\s+Anwendung|in\s+Vollziehung|in\s+Vollzug|in\s+Umsetzung|"
                      r"aufgrund|auf\s+Grund|vu|vus|en\s+application|en\s+exécution|conformément\s+à|"
                      r"vist[oaie]|richiamat[oaie]|in\s+applicazione|in\s+esecuzione|conformemente)\b", re.I)
HEAD_STOP = re.compile(r"\b(?:auf\s+Antrag|nach\s+Einsicht\w*|nach\s+Kenntnisnahme|in\s+Erwägung|in\s+der\s+Absicht|"
                       r"beschliess\w*|verordne\w*|erlässt|erlassen|verfügt|setzt\b|sur\s+(?:la\s+)?proposition|considérant|"
                       r"après\s+avoir|décrète|arrête\b|adopte|édicte|ordonne|su\s+proposta|decreta|risolve|ordina|emana|"
                       r"considerato|ritenuto)\b", re.I)
ACTION = re.compile(r"\b(?:beschliess\w*|verordne\w*|erlässt|erlassen\s+hiermit|verfügt|décrète|arrête|adopte|édicte|ordonne|"
                    r"decreta|risolve|ordina|emana|se\s+donne|gibt\s+sich)\b", re.I)

AUTH = re.compile(r"(?:Rat\b|[Rr]äte\b|Regierung|Gericht|Volk|Landsgemeinde|Stimmberechtigt|Stimmbürger|Kantone\b|Konferenz|"
                  r"Direktion|Departement|Kommission|Amt\b|Universität|Hochschul|Verwaltung|Büro|Landammann|Synode|"
                  r"Gemeinde|Conseil|Grand|Parlement|Gouvernement|peuple|Assemblée|Département|Direction|Commission|"
                  r"Conférence|cantons\b|Tribunal|Chambre|Office|Bureau|Collège|Consiglio|Gran\b|popolo|Dipartimento|"
                  r"Commissione|Conferenza|Cantoni\b|Tribunale|Ufficio|Camera|Erziehungsrat|Kirchenrat)", re.I)
PARL = re.compile(r"Kantonsrat|Gro(?:ss|ß)e[rn]?\s+Rat|Grossrat|Landrat|Landsgemeinde|Kantonsparlament|Parlament|Volk\b|Stimmberechtigt|"
                  r"Stimmbürger|Verfassungsrat|Grand\s+Conseil|GRAND\s+CONSEIL|peuple|Assemblée\s+constituante|Constituante|"
                  r"Gran\s+Consiglio|GRAN\s+CONSIGLIO|popolo|Landeskonferenz|Grosse\s+Landrat", re.I)
INTERCANT = re.compile(r"^(?:Die|Les|I|Gli)\s+(?:Regierungen\s+der\s+)?(?:Kantone|cantons|Cantoni|Vereinbarungskantone|"
                       r"Konkordatskantone)|Konferenz|Conférence|Conferenza|Vereinbarungs|Konkordats", re.I)
GOV = re.compile(r"Regierungsrat|Regierung\b|Standeskommission|Landammann|Conseil\s+d['’]\s*[ÉE]tat|CONSEIL\s+D['’]\s*[ÉE]TAT|"
                 r"Conseil-exécutif|Consiglio\s+di\s+Stato|CONSIGLIO\s+DI\s+STATO|Gouvernement|Obergericht|Kantonsgericht|"
                 r"Verwaltungsgericht|Appellationsgericht|Tribunal\s+cantonal|Tribunale\s+d['’]appello|Cour\s+(?:suprême|de\s+justice)|"
                 r"Justizleitung|Justizkommission|Gerichtsrat|Kantonsgerichtsausschuss|Plenum", re.I)
TITLE_FLOOR = [
    (re.compile(r"^(?:Verfassung|Constitution|Costituzione)\b", re.I), 4),
    # agreements (intercantonal or with another state) → 5, whoever concluded them: intercantonal law prevails over
    # cantonal law (Art. 48 Abs. 5 BV), as for agreements the Ingress shows concluded by cantons or their governments
    (re.compile(r"^(?:Nachtrag\s+zu[mr]\s+)?(?:Gegenrechts\w+)\b(?!.*\b(?:Einwohnergemeinde|Bürgergemeinde|Gemeinde|commune|comune)\b)", re.I), 5),
    (re.compile(r"^(?!.*\b(?:Einwohnergemeinde|Bürgergemeinde|Gemeinde|commune|comune)\b)"      # a commune's contract: not here
                r"(?:Nachtrag\s+zu[mr]\s+)?(?:Interkantonale[rs]?\s+|Intercantonale?\s+)?(?:\w*[Vv]ereinbarung|Übereinkunft|Übereinkommen|"
                r"Vertrag|Verträge|Staatsvertrag|Konvention|Konkordat|Abkommen|Traité|Convention|Concordat|Accord|Protocole|"
                r"Convenzione|Accordo|Concordato|Trattato|Protocollo)\b", re.I), 5),
    # a contract of the canton with a commune, concluded by the government
    (re.compile(r"vertreten\s+durch\s+(?:den|die)\s+(?:hohe\s+)?(?:Regierungsrat|Regierung)\b", re.I), 6),
    (re.compile(r"^Geschäftsordnung\s+(?:des|für\s+den)\s+(?:Grossen\s+Rat|Kantonsrat|Landrat)|^Règlement\s+du\s+Grand\s+Conseil|"
                r"^Kantonale[rs]?\s+\w*[Gg]esetz\b|^[\w-]+\s+und\s+\w*gesetz\b", re.I), 5),
    (re.compile(r"\b(?:des\s+Regierungsrates|der\s+Regierung|der\s+Standeskommission|du\s+Conseil\s+d['’]\s*[ÉE]tat|"
                r"del\s+Consiglio\s+di\s+Stato|Regierungsratsbeschluss|Regierungsbeschlus\w*|Standeskommissionsbeschluss|des\s+Obergerichts|des\s+Kantonsgerichts|"
                r"du\s+Tribunal\s+cantonal)\b", re.I), 6),
    (re.compile(r"\b(?:der\s+\w*[Dd]irektion|des\s+\w*[Dd]epartement\w*|du\s+Département|de\s+la\s+Direction|"
                r"del\s+Dipartimento|Weisung|Richtlinie|Directive|Direttiva)\b", re.I), 7),
    (re.compile(r"^(?:\w*[Gg]esetz\w*|Loi|Legge|Code|Codice|\w*[Dd]ekret\w*|Décret|Decreto|Kantonsratsbeschluss|"
                r"Landratsbeschluss|Grossratsbeschluss|Gro(?:ss|ß)ratsbeschluss|Konkordat|Concordat|Concordato|"
                r"\w*[Vv]ereinbarung|Convention|Accord|Convenzione|Accordo|Beitritt|Adhésion|Adesione)\b", re.I), 5),
    (re.compile(r"^(?:\w*[Vv]erordnung|Ordonnance|Ordinanza|\w*[Rr]eglement|Règlement|Regolamento|Arrêté|Beschluss)\b", re.I), 6),
]

# the canton's own collection, as footnotes write it ("BGS 111.1"); federal law: SR (de), RS (fr/it)
OWN = {"ZH": r"LS", "BE": r"BSG|RSB", "LU": r"SRL(?:\s+Nr\.)?", "UR": r"RB", "SZ": r"SRSZ", "OW": r"GDB", "NW": r"NG",
       "GL": r"GS", "ZG": r"BGS", "FR": r"RSF", "SO": r"BGS", "BS": r"SG", "BL": r"SGS", "SH": r"SHR", "AR": r"bGS",
       "AI": r"GS", "SG": r"sGS", "GR": r"BR", "AG": r"SAR", "TG": r"RB", "TI": r"RL", "VD": r"BLV|RSV",
       "VS": r"RS/VS|RSVS|SGS/VS|GS/VS", "NE": r"RSN", "GE": r"rsGE|RSG", "JU": r"RSJU"}
NUMTOK = r"(?:[IVX]+\s?[A-Z]+/[\d/]*\d|[A-L]\s\d+(?:\s\d+(?:\.\d+)*)?|\d+(?:\.\d+)+|\d+)"   # 155.611 · VIII B/21/5/1 · E 5 10.03 · 1
LATIN = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies)"
NUM = rf"\d+(?:[a-z](?![a-zäöüéèà])|{LATIN})?(?:{LATIN})?"      # 5a, 34ter; not "65 e" (and)
ART_KW = re.compile(r"(?:\b(?:Artikeln|Artikel|Art\.?|[Aa]rticles?|art\.|[Aa]rticol[oi]|artt\.)|§§?)\s*(?=\d)")
QUAL = re.compile(r"^(?:Absätze|Absatz|Abs\.|Buchstaben|Buchstabe|Bst\.|lit\.|let\.|lettres?|lettere|lettera|lett\.|"
                  r"Ziffern|Ziffer|Ziff\.|Sätze|Satz|Unterabsatz|alinéas|alinéa|al\.|chiffres|chiffre|ch\.|"
                  r"capoversi|capoverso|cpv\.|cifre|cifra|n\.|numeri|numero|phrase|frase|para\.)\s*")
PLURAL_Q = {"Absätze", "Buchstaben", "Ziffern", "Sätze", "alinéas", "lettres", "chiffres", "capoversi", "lettere", "cifre", "numeri"}
SEP = re.compile(r"(\s*,\s*|\s+(und|sowie|bis|oder|et|ou|à|e|o|a|ed)\s+|\s*–\s*|\s+)")


def parse_list(s: str) -> tuple[list[str], int]:
    """Article numbers of 'Art. 9 Abs. 3, 21 Abs. 2 und 3 sowie 31' / 'articles 44, 86 et 89' /
    'art. 5 cpv. 2 e 7' (paragraph, letter and figure qualifiers dropped). Same rule as the
    federal parser: after a qualifier, a number stays a sub-unit unless a qualifier follows it,
    'sowie' precedes it, or the qualifier was singular ("Absatz 1 und 4" = article 4)."""
    out: list[str] = []
    s = s.replace("-", "–")
    pos, mode, qtype, last_q, sep = 0, "art", None, None, None
    while pos < len(s):
        rest = s[pos:]
        m = SEP.match(rest)
        if m and m.end() > 0:
            w = m.group(2) or ("," if "," in m.group(1) else ("–" if "–" in m.group(1) else None))
            if w:
                sep = w
            pos += m.end()
            continue
        q = QUAL.match(rest)
        if q:
            kw = q.group(0).strip()
            qtype = "plur" if kw in PLURAL_Q else ("abbr" if kw.endswith(".") else "sing")
            mode, last_q, sep = "qual0", None, None
            pos += q.end()
            continue
        m = re.match(rf"({NUM})(?:er|e)?\b", rest)
        if m:
            a = m.group(1).replace(" ", "")
            n = int(re.match(r"\d+", a).group())
            after = rest[m.end():]
            if mode == "qual0":
                mode, last_q = "qual", n
            elif mode == "qual":
                followed = bool(QUAL.match(re.sub(r"^[\s,]+", "", after)))
                if followed or sep == "sowie" or qtype == "sing" or last_q is None or (
                        qtype == "abbr" and not (last_q < n <= last_q + 3 and n <= 20)):
                    mode = "art"
                else:
                    last_q = n
            if mode == "art":
                if sep in ("–", "bis", "à") and out and out[-1].isdigit() and a.isdigit():
                    out[-1] = f"{out[-1]}–{a}"
                else:
                    out.append(a)
            pos += m.end()
            sep = None
            continue
        if mode in ("qual", "qual0") and re.match(r"[a-z](?![a-zäöüéèà])", rest):
            mode = "qual"
            pos += 1
            continue
        if re.match(r"(?:ff?\.|ss?\.|und\s+folgende|et\s+suivants|e\s+seguenti)", rest):
            pos += re.match(r"(?:ff?\.|ss?\.|und\s+folgende|et\s+suivants|e\s+seguenti)", rest).end()
            continue
        break
    return out, pos


def articles_in(seg: str) -> list[str]:
    """Every article list in the words naming one basis."""
    out = []
    for m in ART_KW.finditer(seg):
        nums, _ = parse_list(seg[m.end():])
        out += [n for n in nums if n not in out]
    return out


# ---------- federal titles by date (all languages) ----------
LABEL = re.compile(rf"^(?P<type>.+?)\s+(?:vom|du|del|dell['’]|della|dello|des)\s+(?P<d>\d{{1,2}})(?:\.|er|°)?\s*(?P<m>{MONTH_RE})\s+(?P<y>\d{{4}})(?P<rest>.*)$", re.I)
STOPW = set("der die das des dem den und über zur zum vom von für mit bei auf ihre seine einer eines einem "
            "la le les du de des et sur aux au en pour par une un dans relative relatif concernant "
            "il lo la i gli le del della dei delle e sul sulla sui sugli per con un una nel nella".split()) | set(MONTHS) | {
    "bundes", "bundesgesetz", "bundesgesetzes", "bundesbeschluss", "verordnung", "gesetz", "gesetzes", "fédérale", "fédéral",
    "federale", "schweizerischen", "schweizerische", "schweizerisches", "suisse", "svizzera", "svizzero", "eidgenössischen",
    "ordonnance", "ordinanza", "legge", "arrêté", "décret", "decreto", "loi", "kantons", "canton", "cantone", "cantonale"}


SELF_NAME = re.compile(r"\b(?:(?:de\s+la\s+)?République\s+et\s+(?:C|c)anton|(?:des|dem|den)\s+Kantons?|für\s+den\s+Kanton|"
                       r"(?:du|de\s+l['’]|le)\s+canton|(?:del|nel)\s+Cantone|Repubblica\s+e\s+Cantone)\s+(?:du\s+|de\s+|d['’]|di\s+|del\s+)?"
                       r"[A-ZÄÖÜ][\w.\-]*(?:\s+[A-ZÄÖÜ][\w.\-]*)?", re.I)


def words(s: str) -> set:
    s = SELF_NAME.sub(" ", s)          # "des Kantons Solothurn" says which canton, not which act
    return {w for w in re.findall(r"[a-zäöüàâçéèêëîïôûùü]{4,}", s.lower()) if w not in STOPW}


COMPOUND = re.compile(r"s?(?:gesetz|verordnung|reglement|beschluss|dekret|ordnung)(?:es|s|en|e)?$")


def compound(x: str, y: str) -> bool:
    """"strassenverkehr" ~ "strassenverkehrsgesetz", "landwirtschaftsgesetzes" ~ "landwirtschaftsgesetz"."""
    if len(x) > len(y):
        x, y = y, x
    if len(x) < 6 or not y.startswith(x):
        return False
    rest = y[len(x):]
    return bool(COMPOUND.fullmatch(rest)) or rest in ("es", "s", "en", "e", "n")


def type_of(s: str):
    m = TYPE_RE.search(s)
    return m.lastgroup if m else None


def federal_index():
    in_force = set(json.load(open(ROOT / "data/fedlex_basis.json"))["acts"])
    by_date = defaultdict(list)
    for r in csv.DictReader(open(ROOT / "data/sr_taxonomy.csv", encoding="utf-8")):
        m = LABEL.match(re.sub(r"<[^>]+>", "", r["label"]))      # "1<sup>er</sup> juillet"
        if not m or r["lang"] not in ("de", "fr", "it") or re.match(r"(?:BG|LF|BB|AF|DF|V|O)\s", m["type"]):
            continue                                              # "BG über …": a cross-reference node of the taxonomy
        d = f"{int(m['y']):04d}-{MONTHS[m['m'].lower()]:02d}-{int(m['d']):02d}"
        by_date[d].append({"sr": r["notation"], "type": type_of(m["type"]), "w": words(m["type"] + " " + m["rest"]),
                           "abbr": set(re.findall(r"[(,]\s*([A-ZÄÖÜ][\w./\-]{1,14})\)?\s*$", m["rest"])), "now": r["notation"] in in_force})
    # earlier acts of cited SR numbers (repealed or replaced): "SR <n>@<year>"
    old = json.load(open(ROOT / "data/fedlex_acts.json"))["acts"]
    for sr, versions in old.items():
        if len(versions) < 2:
            continue
        for v in versions[:-1]:
            if not v.get("date"):
                continue
            for t in (v.get("title") or {}).values():          # one entry per language, as for the taxonomy
                by_date[v["date"]].append({"sr": f"{sr}@{v['date'][:4]}", "type": type_of(t), "w": words(t),
                                           "abbr": set((v.get("abbr") or {}).values()), "now": False})
    return by_date


ARTICLES_W = {"der", "die", "das", "des", "dem", "den", "la", "le", "les", "du", "de", "l", "il", "lo", "gli", "del", "della",
              "dello", "dell", "dei", "delle"}
BARE = {"gesetz", "verordnung", "reglement", "dekret", "beschluss", "konkordat", "vereinbarung", "vertrag", "verfassung", "statut",
        "ordnung", "bundesgesetz", "bundesbeschluss", "bundesverfassung", "einführungsgesetz", "ausführungsgesetz",
        "vollziehungsverordnung", "geschäftsordnung", "kantonsverfassung", "staatsverfassung", "ordonnance", "règlement",
        "regolamento", "ordinanza", "convention", "concordat", "convenzione", "concordato"}


def tkey(s: str) -> tuple:
    """A title compared without date, case, articles in front, case endings, glued footnote digits or
    the old spelling of tripled consonants: "des Bundesgesetzes über die Binnenschiffahrt1" =
    "Bundesgesetz über die Binnenschifffahrt"."""
    s = DATE.sub(" ", s.lower().replace("ß", "ss"))
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"(?<=[a-zäöüàâçéèêëîïôûùü])\d+", "", s)
    s = re.sub(r"(.)\1\1", r"\1\1", s)
    toks = re.findall(r"[a-zäöüàâçéèêëîïôûùü]+", s)
    while toks and toks[0] in ARTICLES_W:
        toks.pop(0)
    out = []
    for t in toks:
        for suf in ("es", "en", "em", "er", "e", "s", "n"):
            if t.endswith(suf) and len(t) - len(suf) >= 4:
                t = t[:-len(suf)]
                break
        out.append({"zgb": "zivilgesetzbuch", "stgb": "strafgesetzbuch", "zur": "zu", "zum": "zu"}.get(t, t))
    out = [t for t in out if t not in ("schweizerisch", "eidgenössisch", "kantonal", "cantonal", "cantonal")]
    # "Gesetz über die Einführung des ZGB" = "Einführungsgesetz zum ZGB"
    if len(out) > 4 and out[0] == "gesetz" and out[1] in ("über", "betreffend") and out[2] == "die" and \
            out[3] in ("einführung", "ausführung", "vollziehung") and out[4] in ("des", "der", "zu"):
        out = [out[3] + "sgesetz", "zu"] + out[5:]
    return tuple(out)


def key_ok(k: tuple) -> bool:
    return len(k) >= 2 or (len(k) == 1 and len(k[0]) >= 8 and k[0] not in {tkey(b)[0] for b in BARE})


def federal_titles():
    """Titles of the federal acts in force, without date (DE/FR/IT): key → SR numbers."""
    in_force = set(json.load(open(ROOT / "data/fedlex_basis.json"))["acts"])
    out = defaultdict(set)
    for r in csv.DictReader(open(ROOT / "data/sr_taxonomy.csv", encoding="utf-8")):
        m = LABEL.match(re.sub(r"<[^>]+>", "", r["label"]))      # "1<sup>er</sup> juillet"
        if not m or r["lang"] not in ("de", "fr", "it") or r["notation"] not in in_force or re.match(r"(?:BG|LF|BB|AF|DF|V|O)\s", m["type"]):
            continue
        k = tkey(m["type"] + " " + m["rest"])
        if key_ok(k):
            out[k].add(r["notation"])
    return out


FED_GENERIC = re.compile(r"Bundesgesetzgebung|bundesrechtlich\w*|Bundesrecht\w*|(?:Bestimmungen|Vorschriften)\s+des\s+Bundes|"
                         r"eidgenössische\w*\s+(?:Gesetzgebung|Recht\w*|Bestimmungen|Vorschriften)|législation\s+fédérale|"
                         r"droit\s+fédéral|dispositions?\s+fédérales?|prescriptions?\s+fédérales?|legislazione\s+federale|"
                         r"diritto\s+federale|disposizioni\s+federali", re.I)
WEAK_KW = re.compile(r"gemäss|im\s+Hinblick|in\s+Hinsicht|unter\s+Bezugnahme|auf\s+der\s+Grundlage", re.I)


CONJ_REF = re.compile(r"(?:\b(?:sowie|und|et|e|nonché)\s+|,\s*)(?:auf\s+)?(?:das|die|den|dem|der|des|la|le|les|l['’]|il|lo|gli|i|son|sa|ses|seine[nmr]?|ihre[nmr]?)\b"
                      r"(?=\s*(?:\S+\s+){0,2}?\S*?(?:" + TYPE_RE.pattern + r"))")


def ref_cut(left: str) -> int:
    """Where the reference ending at the end of `left` begins: after the last article keyword,
    semicolon, footnote mark, date, or "und die/et la" that introduces another act. A date with no
    act named after it is part of the title ("… de Crans-Montana du 1er janvier 2026 du 20 mars 2026")."""
    base = [0] + [x.end() for x in ART_KW.finditer(left)] + [x.end() for x in re.finditer(r";|\[(?:\d+|[A-Z]{1,2})\]", left)] + \
        [x.start() for x in CONJ_REF.finditer(left)]
    dates = []
    for x in DATE.finditer(left):               # a date, and the "(Kurztitel, Abk.)" that follows it, close a reference
        e = x.end() + len(re.match(r"(?:\s*\[\w+\])?\s*(?:\([^()]*\))?\)?", left[x.end():]).group(0))
        if TYPE_RE.search(left[e:]):
            dates.append(e)
    return max(base + dates)


# ---------- one Ingress ----------
def split_clauses(ing: str):
    """[(start, end)] of the basis clauses: from a basis keyword to the next basis or stop keyword.
    The weaker keywords ("gemäss", "im Hinblick auf" …) count only before the enacting formula and
    never after "Fassung"/"Nachtrag" (an amendment, not a basis)."""
    act = ACTION.search(ing)
    marks = sorted([(m.start(), m.end(), "b") for m in BASIS_KW.finditer(ing)
                    if not (WEAK_KW.match(m.group(0)) and (act and m.start() > act.start() or
                            re.search(r"(?:Fassung|Nachtr\w*|Änderung|geändert|revidiert)\s*$", ing[max(0, m.start() - 30):m.start()])))] +
                   [(m.start(), m.end(), "s") for m in STOP_KW.finditer(ing)])
    out = []
    for k, (a, b, kind) in enumerate(marks):
        if kind != "b":
            continue
        end = next((x[0] for x in marks[k + 1:]), len(ing))
        out.append((b, end))
    return out


KV_TITLE = re.compile(r"^(?:Verfassung|Constitution|Costituzione)\s+(?:des\s+Kantons|für\s+den\s+Eidgenössischen\s+Stand|"
                      r"du\s+canton|de\s+la\s+République|della\s+Repubblica|del\s+Cantone)", re.I)
CHURCH = re.compile(r"Kirche|Landeskirche|Kantonalkirche|Konfessionsteil|ecclésiastique|Eglise|Église|Chiesa|Verband\s+der", re.I)


def issuer_and_floor(rec):
    ing = (rec.get("ingress") or "").strip()
    iss = (rec.get("issuer") or "").strip(" ,;:")
    head = ing
    m = HEAD_CUT.search(ing) or HEAD_STOP.search(ing)
    if m:
        head = ing[:m.start()]
    head = re.sub(r"\[\d+\]", "", head).strip(" ,;:")
    if not iss and head and AUTH.search(head) and len(head) < 240:
        iss = head
    if not iss:                       # "Erlassen vom Obergericht …", "… von der Regierung erlassen am …"
        m = re.search(r"Erlassen\s+vo[mn]\s+(?:der\s+|dem\s+)?([^,.;]{3,80}?)(?:\s+gestützt|\s+am\b|[.,;]|$)", ing) or \
            re.search(r"\bvo[mn]\s+(?:der\s+|dem\s+)?([A-ZÄÖÜ][^,.;]{2,60}?)\s+erlassen\b", ing)
        if m:
            iss = m.group(1).strip()
    iss = re.sub(r"\s+(?:erlässt|beschliesst|verordnet)\s*$", "", iss)
    title = rec.get("title") or ""
    if KV_TITLE.match(title) and not CHURCH.search(title):
        return iss, 4, "Titel"
    if CHURCH.search(title) and re.match(r"^(?:Verfassung|Constitution|Costituzione)\b", title):
        return iss, 7, "Kirche"              # constitution of a recognised church: a body of public law
    if iss:
        if INTERCANT.search(iss) and not GOV.search(iss.split(",")[0]) or re.search(r"\bund\s+(?:der|die|das)\s+Regierung|et\s+le\s+Gouvernement|"
                                                                                 r"\bund\s+der\s+Regierungsrat\s+des\s+Kantons", iss):
            return iss, 5, "interkantonal"
        if PARL.search(iss) and not re.search(r"Büro|Bureau|Ufficio|Kommission|Commission|Verwaltungskommission", iss):
            return iss, 5, "Ingress"
        if GOV.search(iss):
            return iss, 6, "Ingress"
        if re.search(r"\bGemeinde|Einwohner|commune|comune|Stadtrat|Gemeinderat", iss):
            return iss, 7, "kommunal"
        return iss, 7, "Ingress"
    for rx, fl in TITLE_FLOOR:
        if rx.search(title):
            return "", fl, "Titel"
    return "", 7, "unbekannt"


class Canton:
    def __init__(self, ct, acts, fed, kv_struct, fed_date, fed_titles=None):
        self.ct, self.acts, self.fed, self.fed_date = ct, acts, fed, fed_date
        self.own = re.compile(rf"(?<![\w/])(?:{OWN[ct]})\s*({NUMTOK})")
        self.fed_ref = re.compile(rf"(?<![\w/])(?:SR|RS)(?!\s*/)\s*(0\.\d[\d.]*\d|\d[\d.]*\d|\d)\b")
        self.by_date = defaultdict(list)
        self.by_abbr = defaultdict(set)
        self.by_sr = {}
        for a in acts:
            self.by_sr[norm_sr(a["sr"])] = a["sr"]
            if a.get("adopted"):
                self.by_date[a["adopted"]].append(a)
            for ab in abbrs_of(a):
                self.by_abbr[ab.lower()].add(a["sr"])
        self.kv_sr = next((a["sr"] for a in acts if a["_floor"] == 4), None)
        self.kv_arts = kv_struct
        self.fed_titles = fed_titles or {}
        self.fed_abbr = defaultdict(set)
        for cs in fed.values():
            for c in cs:
                if c["now"]:
                    for ab in c["abbr"]:
                        self.fed_abbr[ab].add(c["sr"])
        self.by_title = defaultdict(set)          # title or short title without date → acts
        for a in acts:
            for t in [a.get("title")] + [v.get("title") for v in (a.get("i18n") or {}).values()]:
                if not t:
                    continue
                # the title, and a one-word short title in brackets ("(Beurkundungsgesetz)"; not "(loi sur les épidémies)",
                # which names the law a règlement executes)
                for k in [tkey(t)] + [tkey(x) for x in re.findall(r"\(([^)\s,;]{8,40})[),;]", t) if not re.search(r"[A-Z]{2}", x)]:
                    if key_ok(k):
                        self.by_title[k].add(a["sr"])

    def target_of_note(self, note: str):
        """The act a footnote gives the number of: "SR 281.1", "BGS 111.1", or, as VD writes them,
        "Code de droit privé judiciaire vaudois du 12.01.2010 (BLV 211.02)" (first number in the note).
        Editorial notes (amendments, renamed titles) give none."""
        note = note.strip()
        if re.match(r"^(?:Fassung|Eingefügt|Aufgehoben|Geändert|Ingress|Nouvelle\s+teneur|Ingresso|Introdotto|Abrogé|n\.t\.)", note, re.I):
            return None
        fm, om = self.fed_ref.search(note), self.own.search(note)
        if fm and (not om or fm.start() < om.start()) and not re.match(rf"(?:{OWN[self.ct]})", note[fm.start():]):
            return "SR " + fm.group(1).rstrip(".")
        if om:
            return self.cantonal(om.group(1))
        return None

    def cantonal(self, num: str):
        n = norm_sr(num)
        if n in self.by_sr:
            sr = self.by_sr[n]
            return "KV" if sr == self.kv_sr else "CT:" + sr
        return "CT?:" + num.strip()            # a number of this canton's collection not in force today

    def by_name_date(self, desig: str, date: str, federal_hint: bool):
        """The act of this type and date: federal (taxonomy titles) or of this canton."""
        """Same type required; title words must agree where the designation has any; a federal
        act is taken only when the text says so (Bundes-, fédéral, federale …) or, failing a
        cantonal act of that date, when type and at least two title words agree."""
        ty, w = type_of(desig), words(desig)
        fed = [c for c in self.fed.get(date, []) if ty and c["type"] == ty]
        can = [a for a in self.by_date.get(date, []) if ty is None or type_of(a["title"]) in (ty, None)]

        def agree(a, b):
            return sum(1 for x in a if x in b or any(compound(x, y) for y in b))

        def best(cands, title_words, need):
            sc = sorted(((agree(w, title_words(c)), k) for k, c in enumerate(cands)), reverse=True)
            sc = [x for x in sc if x[0] >= need]
            if not sc:
                return None
            top = [cands[k] for n, k in sc if n == sc[0][0]]
            if len({c["sr"] for c in top}) > 1:      # the titles of one act in DE/FR/IT are no rivals
                live = {c["sr"]: c for c in top if c.get("now", True)}
                if len(live) != 1:
                    return None                # a tie that neither the words nor "in force" break
                return next(iter(live.values()))
            return top[0]
        if federal_hint:
            c = best(fed, lambda c: c["w"], 1 if w else 0)
            if c:
                return "SR " + c["sr"]
        c = best(can, lambda a: words(a["title"]), 1 if (w and len(can) > 1) else 0)
        if c:
            return "KV" if c["sr"] == self.kv_sr else "CT:" + c["sr"]
        if not federal_hint and not can:
            c = best(fed, lambda c: c["w"], 2)
            if c:
                return "SR " + c["sr"]
        return None

    def by_title_only(self, desig: str, me: str):
        """An act named without date or number ("des Bundesgesetzes über die Binnenschiffahrt",
        "des Gesundheitsgesetzes"): its title must equal exactly one act's title. A federal act is
        taken when the words say so ("Bundes-", "eidgenössisch") and the designation is not an
        Einführungs-/Ausführungsgesetz, or when no act of the canton has that title."""
        k = tkey(desig)
        if not key_ok(k):
            return None
        can = self.by_title.get(k, set()) - {me}
        fed = self.fed_titles.get(k, set())
        hint = bool(FEDERAL_WORD.search(desig)) and not IMPL.match(desig) and not re.match(r"(?:Einführung|Ausführung|Vollzieh)", desig)
        if hint and len(fed) == 1:
            return "SR " + next(iter(fed))
        if len(can) == 1:
            sr = next(iter(can))
            return "KV" if sr == self.kv_sr else "CT:" + sr
        if not can and len(fed) == 1 and len(k) >= 3:
            return "SR " + next(iter(fed))
        return None

    def parse(self, rec):
        ing = rec.get("ingress") or ""
        notes = rec.get("notes") or {}
        bases, unresolved = [], 0
        for a, b in split_clauses(ing):
            seg = ing[a:b]
            anchors = []                     # (start, end, target, priority)
            for m in re.finditer(r"\[(\d+|[A-Z]{1,2})\]", seg):
                t = self.target_of_note(notes.get(m.group(1), ""))
                if t:
                    anchors.append((m.start(), m.end(), t, 0))
            for m in self.fed_ref.finditer(seg):
                if not re.match(rf"(?:{OWN[self.ct]})", seg[m.start():]):
                    anchors.append((m.start(), m.end(), "SR " + m.group(1).rstrip("."), 0))
            for m in self.own.finditer(seg):
                anchors.append((m.start(), m.end(), self.cantonal(m.group(1)), 0))
            for m in BV_NAME.finditer(seg):
                anchors.append((m.start(), m.end(), "SR 101", 1))
            for m in KV_NAME.finditer(seg):
                if BV_NAME.match(seg, m.start()) or re.match(r"(?:Bundes|fédérale|federale)", seg[m.end():m.end() + 12].strip()):
                    continue
                if re.search(r"(?:fédérale|federale|der\s+Schweiz|der\s+Schweizerischen)", seg[m.start():m.end() + 30]):
                    continue
                anchors.append((m.start(), m.end(), "KV", 1))
            for rx, sr in FIXED:
                for m in rx.finditer(seg):
                    if IMPL.search(seg[max(0, m.start() - 70):m.start()]):
                        continue                 # "Einführungsgesetz zum ZGB", "loi d'application du code civil": cantonal
                    anchors.append((m.start(), m.end(), "SR " + sr, 1))
            for ds, de, d in dates_in(seg):
                if AMEND.search(seg[max(0, ds - 45):ds]):
                    continue                     # the date of an amendment, not of the act
                # the designation: back to the type word in the same reference
                left = seg[max(0, ds - 170):ds]
                cut = ref_cut(left)
                desig_l = left[cut:]
                tm = list(TYPE_RE.finditer(desig_l))
                tm = tm[:1]                      # the head of the designation: "l'ordonnance relative au code pénal …"
                right = re.match(r"[^,;\[\(]{0,150}", seg[de:]).group(0)
                if not tm and not TYPE_RE.match(right.strip()):
                    am = re.search(r"\b([A-ZÄÖÜ][a-zäöü]{0,6}[A-Z][A-Za-zäöü]{0,6})\s*(?:vom|du|del)?\s*$", desig_l)
                    if am:
                        hit = {c["sr"] for c in self.fed.get(d, []) if am.group(1) in c["abbr"] or
                               c["sr"].split("@")[0] in self.fed_abbr.get(am.group(1), ())}     # earlier act: today's abbreviation
                        hit_k = {sr for sr in self.by_abbr.get(am.group(1).lower(), set())
                                 if any(a["sr"] == sr for a in self.by_date.get(d, []))}
                        if len(hit) + len(hit_k) == 1:
                            t = ("SR " + next(iter(hit))) if hit else ("KV" if next(iter(hit_k)) == self.kv_sr else "CT:" + next(iter(hit_k)))
                            anchors.append((max(0, ds - 170) + cut + am.start(1), de, t, 2))
                    continue
                desig = (desig_l[tm[-1].start():] if tm else "") + " " + right
                if NOT_ACT.search(desig_l[-60:]) and not tm:
                    continue
                hint = bool(FEDERAL_WORD.search(desig))
                if re.search(r"\b(?:son|sa|ses|seine[nmr]?|ihre[nmr]?|sua|suo|i\s+suoi|le\s+sue)\s+\S*\s*$", desig_l[:tm[-1].start()] if tm else desig_l):
                    prev = [x for x in anchors if x[1] <= ds]
                    if prev and max(prev, key=lambda x: x[1])[2].startswith("SR "):
                        hint = True              # "la loi fédérale … et son ordonnance d'exécution du …"
                t = None
                pa = re.match(r"\s*\(([A-ZÄÖÜ][\w./\-]{1,14})\)", seg[de:])
                if pa:
                    hit = {c["sr"] for c in self.fed.get(d, []) if pa.group(1) in c["abbr"]}
                    hit_k = {sr for sr in self.by_abbr.get(pa.group(1).lower(), set()) if any(a["sr"] == sr for a in self.by_date.get(d, []))}
                    if len(hit) + len(hit_k) == 1:
                        t = ("SR " + next(iter(hit))) if hit else ("KV" if next(iter(hit_k)) == self.kv_sr else "CT:" + next(iter(hit_k)))
                if not t:
                    t = self.by_name_date(desig, d, hint)
                pm = re.search(r"\b(\d{1,2})(?:er|\.)?\s*(?:et|und|e|/)\s*$", seg[max(0, ds - 12):ds])
                if not t and pm:
                    t = self.by_name_date(desig, f"{d[:8]}{int(pm.group(1)):02d}", hint)
                if t:
                    st = max(0, ds - 170) + cut + (tm[-1].start() if tm else 0)
                    anchors.append((st, de, t, 2))
                elif tm:
                    st = max(0, ds - 170) + cut + tm[-1].start()
                    anchors.append((st, de, "SR ?" if FEDERAL_WORD.search(desig) and not IMPL.search(desig_l[:tm[-1].start()][-70:]) else "?", 3))
            for m in TYPE_RE.finditer(seg):
                rest = seg[m.end():]
                if re.match(rf"\s*(?:vom|du|del|dell['’]|della|dello|des)?\s*\d{{1,2}}(?:\.|er|°)?\s*(?:{MONTH_RE})", rest, re.I):
                    continue                     # dated: the date rule above
                head = seg[max(0, m.start() - 170):m.start()]
                if TYPE_RE.search(head[ref_cut(head):]):
                    continue                     # named inside another act's designation ("Verordnung zum Baugesetz")
                stop = re.search(r"[,;\[\(:]|(?<=[^\W\d_])\d{1,2}\b|\s(?:vom|du|del)\s+\d|\s(?:und|sowie|et|e|ed)\s+(?:auf|Art|§|des|der|du|de|della|del)\b|"
                                 r"(?:\b(?:Artikeln|Artikel|Art\.?|articles?|art\.)|§)\s*\d|$", rest)
                if re.match(r"[,\s]*\s(?:vom|du|del|dell['’]|della)\s*\d", rest[stop.start():]):
                    continue                     # "loi fédérale sur … du 23 janvier 1987": dated, the date rule decides
                desig = seg[m.start():m.end() + stop.start()]
                if IMPL.search(seg[max(0, m.start() - 70):m.start()]) and FEDERAL_WORD.search(desig) or \
                        re.match(r"(?:Code|Codice)\b", desig) and IMPL.search(seg[max(0, m.start() - 70):m.start()]):
                    continue                     # "loi d'application du Code civil suisse": the cantonal act, below
                t = self.by_title_only(desig, rec["sr"])
                if t:
                    anchors.append((m.start(), m.end() + stop.start(), t, 2.5))
            if not anchors:
                # nothing identifiable: federal law in general, or an act named that cannot be pinned down
                fm = FED_GENERIC.search(seg)
                tm = TYPE_RE.search(seg)
                if fm:
                    anchors.append((fm.start(), fm.end(), "SR ?", 3))
                elif tm and (ART_KW.search(seg[:tm.start()]) or tm.start() < 25) and not NOT_ACT.search(seg[max(0, tm.start() - 40):tm.start()]):
                    e = re.search(r"[,;\[:]|(?<=[^\W\d_])\d{1,2}\b|$", seg[tm.end():tm.end() + 150])
                    d_ = seg[tm.start():tm.end() + (e.start() if e else 0)]
                    fed_ = FEDERAL_WORD.search(d_) and not re.match(r"\w*(?:Einführung|Ausführung|Vollzieh)|loi\s+(?:cantonale\s+)?d['’]", d_, re.I)
                    anchors.append((tm.start(), tm.end() + (e.start() if e else 0), "SR ?" if fed_ else "?", 3))
            for m in re.finditer(r"\(([A-ZÄÖÜ][\w./\-]{1,14}(?:\s[\w./\-]{1,8})?)\)", seg):
                ab = m.group(1)
                hit = self.by_abbr.get(ab.lower())
                if hit and len(hit) == 1:
                    sr = next(iter(hit))
                    anchors.append((m.start(), m.end(), "KV" if sr == self.kv_sr else "CT:" + sr, 2))
            # group anchors into references: a new reference starts after an article keyword
            anchors.sort()
            refs, cur = [], None
            def new_ref(a, b):
                """Does the text between two anchors start another reference? ";", a dash bullet, ", das …",
                or "und das/et la …" when an act or an article follows ("et des communes" stays in a title)."""
                btw = seg[a:b]
                if re.search(r";|,\s*[–-]\s|^(?:\[\w+\])?,\s*(?:das|die|den|dem|der|des|la|le|les|l['’]|il|lo|gli)\s", btw):
                    return True
                btw = seg[a:b + 1]
                for m in re.finditer(r"(?:\b(?:sowie|und|et|e|nonché)\s+|,\s*)(?:auf\s+)?(?:das|die|den|dem|der|des|la|le|les|l['’]|il|lo|gli|i|"
                                     r"son|sa|ses|seine[nmr]?|ihre[nmr]?|il\s+suo|la\s+sua|i\s+suoi)\b", btw):
                    nxt = seg[a + m.end():a + m.end() + 60]
                    if re.match(r"\s*(?:\S+\s+){0,3}?\S*?(?:" + TYPE_RE.pattern + r")", nxt) or ART_KW.match(nxt.strip()) or \
                            KV_NAME.match(nxt.strip()) or BV_NAME.match(nxt.strip()) or FED_GENERIC.match(nxt.strip()):
                        return True
                return False
            for an in anchors:
                # two footnotes giving different acts are two references (a footnote marks each act named)
                two_notes = cur and an[3] == 0 and an[2] != "?" and any(x[3] == 0 and x[2] != an[2] for x in cur["an"])   # footnotes, "(SR …)"
                if cur and not two_notes and (an[0] <= cur["end"] + 2 or not ART_KW.search(seg[cur["end"]:an[0]])) and not new_ref(cur["end"], an[0]):
                    cur["end"] = max(cur["end"], an[1])
                    cur["an"].append(an)
                else:
                    cur = {"start": an[0], "end": an[1], "an": [an]}
                    refs.append(cur)
            for k, r in enumerate(refs):            # a reference ends after its "(Kurztitel, Abk.)", "(SR 910.1)" and footnote mark
                nxt = refs[k + 1]["start"] if k + 1 < len(refs) else len(seg)
                btw = seg[r["end"]:nxt]
                if re.match(r"\s+(?:sur|concernant|relative?s?\s+(?:à|au|aux)|régissant|portant|instituant|encourageant|"
                            r"sul|sulla|sui|sugli|sulle|concernente|relativa|relativo|über|betreffend)\b", btw):
                    # "la loi fédérale du 25 juin 1982 sur l'assurance-chômage … (LACI)": the title follows the date
                    co = re.search(r"(?:,|\s+(?:et|e|ed|und|sowie|nonché))\s*(?:l['’]|la|le|les|il|lo|i|gli|die|das|der|den|son|sa|ses)?\s*$", btw)
                    r["end"] += co.start() if co else len(btw)
                tail = re.match(r"(?:\s*\[\w+\])?(?:\s*\((?:[^()]|\([^()]*\))*\))?\)?(?:\s*\[\w+\])?", seg[r["end"]:nxt]).group(0)
                r["end"] += len(tail)
            prev_end = 0
            for r in refs:
                cand = [x for x in r["an"] if x[2] != "CT:" + rec["sr"]] or r["an"]     # a footnote giving the act's own number
                best = min(cand, key=lambda x: (x[3] if x[2] not in ("?", "SR ?") and not x[2].startswith("CT?") else 9, x[0]))
                tgt = best[2]
                flag = ""
                if tgt.startswith("CT?") and any(x[2] == "KV" for x in r["an"]):
                    tgt, flag = "KV", "old"          # "Kantonsverfassung" with the number of the former one
                if tgt.startswith("SR ") and "@" not in tgt and tgt != "SR ?":
                    said = [d for ds, de, d in dates_in(seg[r["start"]:r["end"]])]
                    if said and self.fed_date.get(tgt[3:]) and self.fed_date[tgt[3:]] not in said:
                        flag = "old"                 # footnote gives today's number of a law the text cites by its old date
                words_ = seg[prev_end:r["start"]]
                arts = articles_in(words_)
                schlt = bool(SCHLT.search(seg[prev_end:r["end"]]))
                clause = re.sub(r"\s+", " ", seg[prev_end:r["end"]]).strip(" ,;")
                clause = re.sub(r"^(?:und|sowie|et|e|auf)\s+", "", clause)
                clause = re.sub(r"\s+(?:was\s+folgt|folgendes|Folgendes|ce\s+qui\s+suit)\s*$", "", clause)
                prev_end = r["end"]
                if tgt == "CT:" + rec["sr"]:
                    continue                     # the act naming itself (amendment notes, titles)
                if tgt in ("?", "SR ?") or tgt.startswith("CT?"):
                    unresolved += 1
                fin = schlt and tgt.startswith("SR ") and tgt != "SR 101"      # SchlT ZGB, Schlussbestimmungen SchKG …
                bases.append([tgt, [("SchlT " if fin else "") + x for x in arts], clause[:400]] + ([flag] if flag else []))
        return bases, unresolved


COMPANION = re.compile(r"mise\s+en\s+vigueur|Inkraftsetzung|Inkrafttreten|entrata\s+in\s+vigore|^ARRÊTÉ\s+(?:d['’]application|"
                       r"d['’]exécution)", re.I)


def norm_sr(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().rstrip(".")).replace(" .", ".")


def abbrs_of(a):
    out = set()
    for ab in [a.get("abbr")] + [v.get("abbr") for v in (a.get("i18n") or {}).values()]:
        if not ab:
            continue
        for part in re.split(r"\s*[,;]\s*", ab):
            part = part.strip("() ")
            if part and len(part) <= 16 and re.match(r"^[A-ZÄÖÜa-zäöü]", part) and " " not in part.strip() or re.match(r"^[A-Z]{1,4}\s[A-Za-z]{1,6}$", part or ""):
                out.add(part)
    return out


def kv_structure():
    s = json.load(gzip.open(ROOT / "data/fedlex_structure.json.gz"))["acts"]
    out = {}
    for ct, sr in CANTON_CONSTITUTION.items():
        st = s.get(sr)
        if not st:
            continue
        arts = {}
        for a in st.get("articles", []):
            m = re.match(r"^art_(\d+)(?:_([a-z]+))?$", a.get("id") or "")     # art_41, art_41_a, art_41_bis
            if m and not a.get("rep"):
                arts[m.group(1) + (m.group(2) or "")] = {"id": a["id"], "h": a.get("h") or {}}
        out[ct] = {"sr": sr, "arts": arts}
    return out


def main():
    fed = federal_index()
    fed_date = {c["sr"]: d for d, cs in fed.items() for c in cs if c["now"]}
    fed_titles = federal_titles()
    kvs = kv_structure()
    out, stats = {}, Counter()
    for ct in CANTONS:
        p = ROOT / "build" / "cantonal" / f"{ct}.json"
        if not p.exists():
            stats["cantons_missing"] += 1
            print(f"{ct}: no collection read", flush=True)
            continue
        acts = [a for a in json.load(open(p)) if a.get("in_force", True)]
        minor = [a for a in acts if a.get("importance") == "MINEUR"]
        if minor:                      # VD: individual decrees (credits, mergers, convocations), not systematic law
            stats[f"{ct}_minor_left_out"] = len(minor)
            acts = [a for a in acts if a.get("importance") != "MINEUR"]
        # one number, several acts (VD files a law's "Arrêté de mise en vigueur" under the law's number):
        # the main act keeps the number, the others get "~1", "~2" …
        by = defaultdict(list)
        for a in acts:
            by[a["sr"]].append(a)
        for sr_, group in by.items():
            if len(group) > 1:
                group.sort(key=lambda a: (bool(COMPANION.search(a.get("title") or "")), a.get("adopted") or "9999"))
                for k, a in enumerate(group[1:], 1):
                    a["sr"] = f"{sr_}~{k}"
                stats["numbers_shared"] += 1
        for a in acts:
            a["_issuer"], a["_floor"], a["_floor_by"] = issuer_and_floor(a)
        cx = Canton(ct, acts, fed, kvs.get(ct, {}).get("arts", {}), fed_date, fed_titles)
        recs = {}
        for a in acts:
            bases, unres = cx.parse(a)
            kv_art_missing = []
            for b in bases:
                if b[0] == "KV":
                    for n in b[1]:
                        if cx.kv_arts and n.split("–")[0] not in cx.kv_arts:
                            kv_art_missing.append(n)
            recs[a["sr"]] = {"title": a.get("title"), "abbr": a.get("abbr"), "url": a.get("url"), "adopted": a.get("adopted"),
                             "issuer": a["_issuer"], "floor": a["_floor"], "floor_by": a["_floor_by"],
                             "ingress": a.get("ingress") or "", "bases": bases, "src": a.get("src"), "lang": a.get("lang"),
                             **({"i18n": {lg: {"title": v.get("title"), "abbr": v.get("abbr")} for lg, v in a["i18n"].items()}} if a.get("i18n") else {}),
                             **({"kv_missing": kv_art_missing} if kv_art_missing else {})}
            stats["acts"] += 1
            stats[f"floor_{a['_floor']}"] += 1
            stats["with_ingress"] += bool(a.get("ingress"))
            stats["with_bases"] += bool(bases)
            stats["bases"] += len(bases)
            stats["bases_unresolved"] += unres
            stats["bases_outdated"] += sum(1 for b in bases if len(b) > 3 and b[3] == "old")
            for b in bases:
                k = b[0].split(":")[0].split(" ")[0]
                stats[f"target_{'SR_earlier' if '@' in b[0] else 'SR_generic' if b[0] == 'SR ?' else k}"] += 1
            stats["kv_article_not_in_text"] += len(kv_art_missing)
        out[ct] = {"kv": cx.kv_sr, "kv_sr": CANTON_CONSTITUTION[ct], "acts": recs}
        print(f"{ct}: {len(recs)} acts, {sum(1 for r in recs.values() if r['bases'])} with bases, "
              f"floors {dict(Counter(r['floor'] for r in recs.values()))}", flush=True)
    res = {"run_date": RUN_DATE, "source": "official cantonal collections (pipeline/cantonal/*.py)", "stats": dict(stats), "cantons": out}
    json.dump(res, open(ROOT / "data/cantonal_basis.json", "w"), ensure_ascii=False, separators=(",", ":"))
    print(json.dumps(dict(stats), indent=1))


if __name__ == "__main__":
    main()
