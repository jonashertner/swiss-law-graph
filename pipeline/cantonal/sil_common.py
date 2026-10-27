"""Shared helpers for the SIL portals (GE silgeneve.ch, NE rsn.ne.ch).

SIL ("Système d'Information Législatif") serves each collection as Word-generated HTML in
windows-1252: a table of contents `content.htm` and one page per act under `htm/`. This module
holds what both adapters need: a polite cached fetcher, windows-1252 decoding, plain-text
extraction with footnote markers kept as "[n]", preamble segmentation (issuer, enacting clause)
and the output writer. Record shape: pipeline/cantonal/SPEC.md.
"""
from __future__ import annotations

import datetime
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refresh import fresh  # noqa: E402  (weekly refresh)

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build" / "cantonal"
USER_AGENT = "swiss-law-graph/1.0 (legal research; +https://opencaselaw.ch)"
MAX_PER_HOST = 3


# ---------------------------------------------------------------------------------------------
# fetching

class Fetcher:
    """GET with an on-disk cache, at most MAX_PER_HOST requests in flight, retries on 5xx,
    429 and timeouts with exponential backoff. A 404 is cached as an empty `<name>.404`."""

    def __init__(self, raw_dir: Path, refresh: bool = False):
        self.raw_dir = raw_dir
        self.refresh = refresh
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.sem = threading.Semaphore(MAX_PER_HOST)
        self.lock = threading.Lock()
        self.n_net = 0

    def get(self, url: str, name: str, refresh: bool | None = None) -> bytes | None:
        p = self.raw_dir / name
        miss = p.with_name(p.name + ".404")
        if not (self.refresh if refresh is None else refresh):
            if fresh(p):                                 # GE, NE publish the text in force: re-read in a refresh
                return p.read_bytes()
            if fresh(miss):
                return None
        p.parent.mkdir(parents=True, exist_ok=True)
        delay, err = 2.0, None
        for _ in range(6):
            try:
                with self.sem:
                    r = self.session.get(url, timeout=60)
                with self.lock:
                    self.n_net += 1
            except (requests.ConnectionError, requests.Timeout) as e:
                err = e
            else:
                if r.status_code == 200:
                    tmp = p.with_name(p.name + ".part")
                    tmp.write_bytes(r.content)
                    tmp.replace(p)
                    miss.unlink(missing_ok=True)
                    return r.content
                if r.status_code == 404:
                    miss.write_bytes(b"")
                    p.unlink(missing_ok=True)
                    return None
                if r.status_code < 500 and r.status_code != 429:
                    raise RuntimeError(f"HTTP {r.status_code} {url}")
                err = f"HTTP {r.status_code}"
            time.sleep(delay)
            delay *= 2
        raise RuntimeError(f"giving up on {url}: {err}")

    def get_many(self, jobs: list[tuple[str, str]], label: str = "") -> dict[str, bytes | None]:
        """{name: bytes | None} for [(url, name)], MAX_PER_HOST at a time."""
        done = [0]

        def one(job):
            b = self.get(*job)
            with self.lock:
                done[0] += 1
                if done[0] % 200 == 0 or done[0] == len(jobs):
                    print(f"  {label} {done[0]}/{len(jobs)} ({self.n_net} from network)",
                          file=sys.stderr)
            return job[1], b

        with ThreadPoolExecutor(MAX_PER_HOST) as ex:
            return dict(ex.map(one, jobs))


def decode(b: bytes) -> str:
    """SIL pages declare windows-1252 (bytes undefined there are replaced)."""
    return b.decode("cp1252", errors="replace")


def soup(b: bytes) -> BeautifulSoup:
    return BeautifulSoup(decode(b), "lxml")


# ---------------------------------------------------------------------------------------------
# text

def norm_ws(s: str) -> str:
    s = s.replace("­", "")  # soft hyphen
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


MONTHS = {"janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
          "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
          "décembre": 12, "decembre": 12}
DATE_FR = re.compile(r"(\d{1,2})\s*(?:er|re)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", re.I)


def fr_dates(s: str) -> list[str]:
    """ISO dates of every complete "12 septembre 1985" / "1er janvier 1986" in s, in order."""
    out = []
    for m in DATE_FR.finditer(norm_ws(s)):
        try:
            out.append(datetime.date(int(m.group(3)), MONTHS[m.group(2).lower()],
                                     int(m.group(1))).isoformat())
        except ValueError:
            pass
    return out


def adoption_date(s: str) -> str | None:
    """Adoption date of a header such as "du 12 septembre 1985". When the header names several
    dates ("des 31 mai et 27 septembre 2001", signatures of a concordat), the latest complete
    one: the act exists from then on."""
    ds = fr_dates(s)
    return max(ds) if ds else None


def text_of(node, marker_of=lambda a: None, base_url: str = "") -> tuple[str, list[str], list[dict]]:
    """Plain text of a node (or list of nodes), whitespace normalised.

    `marker_of(a)` gives the footnote key of an <a> that is a footnote reference; its visible
    "(n)" / "[n]" is then written "[n]". Every other <a href> is an ordinary hyperlink.
    Returns (text, footnote keys in order, [{text, href}] in order)."""
    parts: list[str] = []
    keys: list[str] = []
    links: list[dict] = []

    def walk(n):
        if isinstance(n, Comment):
            return
        if isinstance(n, NavigableString):
            parts.append(str(n))
            return
        if not isinstance(n, Tag) or n.name in ("script", "style"):
            return
        if n.name == "br":
            parts.append(" ")
            return
        if n.name == "a" and n.get("href"):
            k = marker_of(n)
            if k is not None:
                keys.append(k)
                parts.append(f" [{k}]")
                return
            t = norm_ws(n.get_text())
            if t:
                href = n["href"]
                if href.startswith("silwebext:"):
                    href = href[len("silwebext:"):]
                links.append({"text": t, "href": urljoin(base_url, href) if base_url else href})
        for c in n.children:
            walk(c)
        if n.name in ("p", "div", "td", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            parts.append(" ")

    for n in (node if isinstance(node, list) else [node]):
        walk(n)
    txt = norm_ws("".join(parts))
    txt = re.sub(r"\s+(\[[^\]]+\])", r"\1", txt)        # "Constitution fédérale [1]" -> "...fédérale[1]"
    return txt, keys, links


# ---------------------------------------------------------------------------------------------
# preamble segmentation

# The enacting clause: the verb by which the issuer enacts ("décrète", "arrête", ...), or the
# formula of a treaty ("sont convenus des articles suivants", "conviennent de ce qui suit").
ENACT_VERB = (r"d[ée]cr[èe]te(?:nt)?|arr[êe]te(?:nt)?|[ée]dicte(?:nt)?|adopte(?:nt)?|ordonne(?:nt)?|"
              r"d[ée]cide(?:nt)?|conviennent|sont\s+convenu(?:e)?s|ont\s+convenu|se\s+donne(?:nt)?|"
              r"promulgue(?:nt)?|statue(?:nt)?|prescrivent|prescrit|approuve(?:nt)?|ratifie(?:nt)?|"
              r"savoir\s+faisons|(?:ont|avons)\s+arr[êe]t[ée]|r[èe]gle(?:nt)?|"
              r"(?:est|sont)\s+conclu(?:e|s|es)?")
_ENACT_START = re.compile(rf"^(?:et\s+|puis\s+|il\s+|le\s+pr[ée]sent\s+\w+\s+)?(?:{ENACT_VERB})\b", re.I)
_ENACT_END = re.compile(rf"(?:^|[\s,;])(?:{ENACT_VERB})\b[^;]{{0,200}}:\s*(?:\[[^\]]+\]\s*)?$", re.I)
_ENACT_ONLY = re.compile(rf"\b(?:{ENACT_VERB})(?:\s+ce\s+qui\s+suit)?\s*[:.]?\s*(?:\[[^\]]+\]\s*)?$", re.I)


# Treaty formulas without one of those verbs: "… les articles suivants.", "… dont la teneur suit :",
# "… ont fait la Convention suivante :".
_FORMULA = re.compile(r"(?:ce\s+qui\s+suit|suivante?s?|suivans|la\s+teneur(?:\s+suit)?)\s*[:.]?\s*"
                      r"(?:\[[^\]]+\]\s*)?$", re.I)


_ENACT_ANY = re.compile(rf"\b(?:{ENACT_VERB})\b", re.I)


def find_enacting(texts: list[str]) -> tuple[int | None, bool]:
    """(index of the paragraph that closes the preamble, strict?): the first paragraph that reads
    as an enacting clause; failing that (strict = False), the last one that contains an enacting
    verb at all ("les cantons … décident de poursuivre la collaboration …")."""
    k = next((i for i, t in enumerate(texts) if is_enacting(t)), None)
    if k is not None:
        return k, True
    loose = [i for i, t in enumerate(texts) if _ENACT_ANY.search(t)
             and not re.match(r"^(vu|vus|considérant|attendu)\b", t.strip(), re.I)
             and not _NUMBERED.match(t)]
    return (loose[-1], False) if loose else (None, False)


_NUMBERED = re.compile(r"^\s*(?:\(?\d+[.)]|[a-z]\))\s")      # "1. Le Conseil d'Etat …" is body text


def is_enacting(text: str) -> bool:
    t = text.strip()
    if not t or re.match(r"^(vu|vus|considérant|attendu)\b", t, re.I) or _NUMBERED.match(t):
        return False
    return bool(_ENACT_START.match(t) or _ENACT_END.search(t) or _ENACT_ONLY.search(t)
                or _FORMULA.search(t))


# Words that open the bases, recitals or the enacting clause: the issuer is what precedes them.
_BASIS = re.compile(
    r"[,;:]?\s*\b(vu|vus|considérant|considerant|attendu|sur\s+(?:la|le|les)\s+(?:proposition|"
    r"préavis|rapport|propositions|demande)|après\s+(?:avoir|examen|consultation)|en\s+application|"
    r"en\s+exécution|en\s+vertu|conformément|dans\s+le\s+but|en\s+vue|désireu(?:x|se|ses)|"
    r"soucieu(?:x|se|ses)|animé(?:e|s|es)?|conscient(?:e|s|es)?|reconnaissant(?:e|s|es)?|"
    r"convaincu(?:e|s|es)?|résolu(?:e|s|es)?|attaché(?:e|s|es)?|déterminé(?:e|s|es)?|"
    r"respectueu(?:x|se|ses)|lesquels|ayant|à\s+savoir|dans\s+le\s+cadre|tenant|désirant|voulant|"
    rf"{ENACT_VERB})\b", re.I)


def issuer_of(ingress: str) -> str | None:
    """Text before the first basis keyword (or the enacting verb), trailing punctuation off."""
    m = _BASIS.search(ingress)
    s = ingress[:m.start()] if m else ingress
    s = re.sub(r"(?:[\s,;:]|\[[^\]]*\])+$", "", s)   # trailing punctuation and footnote calls
    if re.search(r"\.\s+\S", re.sub(r"\b(?:[A-Z]|S\. M|LL\. EE|art|al|ch|let|No|N°)\.", "", s)) \
            or len(s) > 400:
        return None                                    # recitals, not an issuer
    return s or None


def write_json(records: list[dict], ct: str) -> Path:
    out = BUILD / f"{ct}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.part")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out)
    return out
