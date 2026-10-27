"""Federal texts that are adopted but not yet in force, and consultation drafts, for the law repository (decision 36).

1. AS (Amtliche Sammlung, eli/oc): every act published since FROM whose entry into force lies after its publication.
   It applies from its entry into force; until then the repository shows it under beschlossen/as/. Several dates
   (staggered entry into force): the last one ends the wait, all are named.
2. Referendumsvorlagen (Bundesblatt, eli/fga, resource type 84): acts the Federal Assembly adopted, published with
   the referendum deadline. Shown from publication until the AS publication of the same act (same date of adoption,
   same title) or, without one, until the referendum deadline the text states. Federal decrees on popular initiatives
   (recommendations to the vote) are left out: they are not legislation.
3. Vernehmlassungen (eli/dl/proj/…/cons_N): consultations opened since FROM; their Vernehmlassungsvorlage(n) (draft
   document type 11) as PDF per language, the opening and closing day, the department, the acts they would change.

Output: build/lawgit/pending/{as,ref,cons}.json and the files under build/lawgit/pending/{xml,pdf}/ (resumable).
4. Ballots: the Federal Council's decrees on each vote's result (BBl) give the bills the people rejected (`votes`).

Usage: python3 pipeline/lawgit/fedlex_pending.py [votes]
"""
import gzip
import json
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch_fedlex_history import PRE, sparql  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build/lawgit/pending"
FROM = "2020-07-01"                                     # an act published then can still wait for 2021-01-01
DATE = "^^<http://www.w3.org/2001/XMLSchema#date>"
LANG = {"DEU": "de", "FRA": "fr", "ITA": "it", "ROH": "rm", "ENG": "en"}
UA = "swiss-law (law repository; +https://jonashertner.com)"

Q_AS = PRE + """SELECT ?a ?eif ?pd ?dd ?td ?l ?t ?url WHERE {
 ?a a jolux:Act ; jolux:publicationDate ?pd ; jolux:dateEntryInForce ?eif ; jolux:isRealizedBy ?e .
 FILTER(STRSTARTS(STR(?a), "https://fedlex.data.admin.ch/eli/oc/%s/"))
 FILTER(?eif > ?pd)
 OPTIONAL { ?a jolux:dateDocument ?dd } OPTIONAL { ?a jolux:typeDocument ?td }
 ?e jolux:language ?l . OPTIONAL { ?e jolux:title ?t }
 OPTIONAL { ?e jolux:isEmbodiedBy ?m . ?m jolux:userFormat <https://fedlex.data.admin.ch/vocabulary/user-format/xml> ; jolux:isExemplifiedBy ?url } }"""
Q_REF = PRE + """SELECT ?a ?pd ?dd ?l ?t ?url WHERE {
 ?a a jolux:Act ; jolux:typeDocument <https://fedlex.data.admin.ch/vocabulary/resource-type/84> ; jolux:publicationDate ?pd ;
    jolux:isRealizedBy ?e . OPTIONAL { ?a jolux:dateDocument ?dd }
 FILTER(STRSTARTS(STR(?a), "https://fedlex.data.admin.ch/eli/fga/%s/"))
 ?e jolux:language ?l . OPTIONAL { ?e jolux:title ?t }
 OPTIONAL { ?e jolux:isEmbodiedBy ?m . ?m jolux:userFormat <https://fedlex.data.admin.ch/vocabulary/user-format/xml> ; jolux:isExemplifiedBy ?url } }"""
Q_OC_BY_DATE = PRE + """SELECT ?a ?dd ?pd ?t WHERE { VALUES ?dd { %s } ?a a jolux:Act ; jolux:dateDocument ?dd ; jolux:publicationDate ?pd ;
 jolux:isRealizedBy ?e . ?e jolux:language <http://publications.europa.eu/resource/authority/language/DEU> ; jolux:title ?t .
 FILTER(STRSTARTS(STR(?a), "https://fedlex.data.admin.ch/eli/oc/")) }"""
Q_CONS = PRE + """SELECT ?c ?st ?en ?status ?inst WHERE {
 ?c a jolux:Consultation ; jolux:hasSubTask ?o . ?o a jolux:ConsultationPhase ; jolux:eventStartDate ?st .
 OPTIONAL { ?o jolux:eventEndDate ?en } OPTIONAL { ?c jolux:consultationStatus ?status }
 OPTIONAL { ?o jolux:institutionInChargeOfTheEventLevel2 ?inst }
 FILTER(?st >= "%s"%s) }"""
Q_CONS_META = PRE + """SELECT ?c ?p ?o (LANG(?o) AS ?lg) WHERE { VALUES ?c { %s } VALUES ?p { jolux:eventTitle jolux:foreseenImpactToLegalResource jolux:eventId }
 ?c ?p ?o }"""
Q_CONS_DOCS = PRE + """SELECT ?d ?ty ?l ?t ?url WHERE { VALUES ?d { %s }
 ?d jolux:draftProcessDocumentType ?ty ; jolux:isRealizedBy ?e .
 ?e jolux:language ?l . OPTIONAL { ?e jolux:title ?t }
 ?e jolux:isEmbodiedBy ?m . ?m jolux:isExemplifiedBy ?url . }"""


def lang(l: str) -> str:
    return LANG.get(l.rsplit("/", 1)[1], "")


def years():
    return [str(y) for y in range(int(FROM[:4]), time.gmtime().tm_year + 2)]


def get(url: str) -> bytes | None:
    for k in range(5):
        try:
            r = requests.get(url, timeout=120, headers={"User-Agent": UA})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except Exception:                                 # noqa: BLE001 — retried, then raised
            if k == 4:
                raise
            time.sleep(3 * (k + 1))


def fetch_all(jobs):
    """[(url, path)] → files; gzip for XML."""
    todo = [(u, p) for u, p in jobs if not p.exists()]
    failed = []

    def work(j):
        u, p = j
        try:
            b = get(u)
            if b is None:
                raise ValueError("404")
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(gzip.compress(b, 6) if p.suffix == ".gz" else b)
            tmp.rename(p)
        except Exception as e:                            # noqa: BLE001 — listed
            failed.append((u, str(e)[:120]))
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(work, todo))
    return len(todo), failed


def norm_title(t: str) -> str:
    t = re.sub(r"\s*\((?:Entwurf|Referendumsvorlage)\)\s*$", "", t or "")
    return re.sub(r"\W+", " ", t).strip().lower()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    # 1. AS acts that wait for their entry into force
    acts = {}
    for y in years():
        for r in sparql(Q_AS % y):
            if r["pd"][:10] < FROM:
                continue
            a = acts.setdefault(r["a"], {"id": r["a"].split("/eli/")[1], "pd": r["pd"][:10], "dd": (r.get("dd") or "")[:10],
                                         "type": (r.get("td") or "").rsplit("/", 1)[-1], "eif": set(), "title": {}, "xml": {}})
            a["eif"].add(r["eif"][:10])
            lg = lang(r["l"])
            if lg and r.get("t"):
                a["title"][lg] = re.sub(r"\s+", " ", r["t"]).strip()
            if lg and r.get("url"):
                a["xml"][lg] = r["url"]
    for a in acts.values():
        a["eif"] = sorted(a["eif"])
        for lg, u in a["xml"].items():
            jobs.append((u, OUT / "xml" / (a["id"].replace("/", "_") + f".{lg}.xml.gz")))
    json.dump(sorted(acts.values(), key=lambda a: (a["pd"], a["id"])), open(OUT / "as.json", "w"), ensure_ascii=False)
    print(f"AS: {len(acts)} acts published since {FROM} with a later entry into force", file=sys.stderr)

    # 2. Referendumsvorlagen
    refs = {}
    for y in years():
        for r in sparql(Q_REF % y):
            if r["pd"][:10] < FROM:
                continue
            a = refs.setdefault(r["a"], {"id": r["a"].split("/eli/")[1], "pd": r["pd"][:10], "dd": (r.get("dd") or "")[:10],
                                         "title": {}, "xml": {}})
            lg = lang(r["l"])
            if lg and r.get("t"):
                a["title"][lg] = re.sub(r"\s+", " ", r["t"]).strip()
            if lg and r.get("url"):
                a["xml"][lg] = r["url"]
    refs = {k: v for k, v in refs.items() if not re.match(r"Bundesbeschluss über die Volksinitiative", v["title"].get("de", ""))}
    dds = sorted({v["dd"] for v in refs.values() if v["dd"]})
    by = defaultdict(list)
    for i in range(0, len(dds), 40):
        vals = " ".join(f'"{d}"{DATE}' for d in dds[i:i + 40])
        for r in sparql(Q_OC_BY_DATE % vals):
            by[(r["dd"][:10], norm_title(r["t"]))].append((r["pd"][:10], r["a"].split("/eli/")[1]))
    for v in refs.values():
        hit = sorted(by.get((v["dd"], norm_title(v["title"].get("de", ""))), []))
        v["as"] = hit[0][1] if hit else ""
        v["as_pd"] = hit[0][0] if hit else ""
        for lg, u in v["xml"].items():
            jobs.append((u, OUT / "xml" / (v["id"].replace("/", "_") + f".{lg}.xml.gz")))
    print(f"Referendumsvorlagen: {len(refs)} since {FROM}, {sum(1 for v in refs.values() if v['as'])} found in the AS",
          file=sys.stderr)

    # 3. Vernehmlassungen
    cons = {}
    for r in sparql(Q_CONS % ("2020-10-01", DATE)):
        c = cons.setdefault(r["c"], {"id": r["c"].split("/eli/")[1], "start": r["st"][:10], "end": (r.get("en") or "")[:10],
                                     "status": (r.get("status") or "").rsplit("/", 1)[-1],
                                     "inst": (r.get("inst") or "").rsplit("/", 1)[-1], "title": {}, "impacts": [], "docs": {}})
        c["start"] = min(c["start"], r["st"][:10])
    keys = list(cons)
    for i in range(0, len(keys), 60):
        vals = " ".join(f"<{k}>" for k in keys[i:i + 60])
        for r in sparql(Q_CONS_META % vals):
            c = cons[r["c"]]
            p = r["p"].rsplit("#", 1)[1]
            if p == "eventTitle":
                c["title"].setdefault(r.get("lg") or "de", re.sub(r"\s+", " ", r["o"]).strip())
            elif p == "foreseenImpactToLegalResource":
                c["impacts"].append(r["o"])
    for i in range(0, len(keys), 8):                     # documents are not linked from the consultation: doc_1 … doc_25
        vals = " ".join(f"<{k}/doc_{n}>" for k in keys[i:i + 8] for n in range(1, 26))
        for r in sparql(Q_CONS_DOCS % vals):
            if not r["ty"].endswith("/11"):                # 11 = Vernehmlassungsvorlage
                continue
            lg = lang(r["l"])
            if not lg or "pdf" not in r["url"].lower():
                continue
            d = cons[r["d"].rsplit("/", 1)[0]]["docs"].setdefault(r["d"].rsplit("/", 1)[1], {"title": {}, "pdf": {}})
            if r.get("t"):
                d["title"][lg] = r["t"]
            d["pdf"][lg] = r["url"]
    for c in cons.values():
        for dn, d in c["docs"].items():
            for lg, u in d["pdf"].items():
                jobs.append((u, OUT / "pdf" / (c["id"].replace("/", "_") + f"_{dn}.{lg}.pdf")))
    print(f"Vernehmlassungen: {len(cons)} opened since 2020-10-01, {sum(1 for c in cons.values() if c['docs'])} with a draft "
          f"document", file=sys.stderr)
    json.dump(sorted(refs.values(), key=lambda a: (a["pd"], a["id"])), open(OUT / "ref.json", "w"), ensure_ascii=False)
    json.dump(sorted(cons.values(), key=lambda a: (a["start"], a["id"])), open(OUT / "cons.json", "w"), ensure_ascii=False)
    n, failed = fetch_all(jobs)
    json.dump(failed, open(OUT / "_failed.json", "w"), ensure_ascii=False)
    print(f"files: {len(jobs)} ({n} fetched now), {len(failed)} failed", file=sys.stderr)


Q_VOTES = PRE + """SELECT ?a ?t ?f ?u WHERE { ?a a jolux:Act ; jolux:publicationDate ?pd ; jolux:isRealizedBy ?e .
 ?e jolux:language <http://publications.europa.eu/resource/authority/language/DEU> ; jolux:title ?t ; jolux:isEmbodiedBy ?m .
 ?m jolux:userFormat ?f ; jolux:isExemplifiedBy ?u .
 FILTER(STRSTARTS(STR(?a), "https://fedlex.data.admin.ch/eli/fga/")) FILTER(?pd >= "%s"%s)
 FILTER(CONTAINS(?t, "Ergebnis der Volksabstimmung")) }"""
MONTHS = {m: i + 1 for i, m in enumerate("Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split())}
STOP = {"bundesgesetz", "bundesgesetzes", "über", "die", "den", "das", "der", "des", "und", "vom", "änderung", "bundesbeschluss", "zum",
        "zur", "im", "in", "für", "auf", "mit", "von", "eine", "einen", "ein"}


def votes() -> None:
    """Which Referendumsvorlagen the people rejected: the Federal Council's decrees on the result of each ballot list the
    rejected bills (Art. "Abgelehnte Vorlage(n)") with their date of adoption; a bill matches when that date and the words
    of its title are in the same item. Adds "rejected": <vote date> to ref.json."""
    import io
    import pdfplumber
    refs = json.load(open(OUT / "ref.json"))
    rows = sparql(Q_VOTES % (FROM, DATE))
    by = defaultdict(dict)
    for r in rows:
        by[r["a"]]["t"] = r["t"]
        by[r["a"]][r["f"].rsplit("/", 1)[1]] = r["u"]
    out = []
    for a, d in sorted(by.items()):
        m = re.search(r"Volksabstimmung\s+vom\s+(\d{1,2})\.\s*([A-Za-zä]+)\s+(\d{4})", d["t"])
        if not m:
            continue
        day = f"{m.group(3)}-{MONTHS.get(m.group(2), 0):02d}-{int(m.group(1)):02d}"
        inline = bool(d.get("xml"))                    # XML cites each bill inline; a PDF prints the citations as footnotes
        if d.get("xml"):
            txt = re.sub(r"<[^>]+>", " ", get(d["xml"]).decode("utf-8", "replace"))
        elif d.get("pdf-a"):
            with pdfplumber.open(io.BytesIO(get(d["pdf-a"]))) as pdf:
                txt = "\n".join(p.extract_text() or "" for p in pdf.pages)
        else:
            continue
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = txt.split("Im Namen des", 1)[0]
        # each item ends with its result: "… ist vom Volk … abgelehnt worden" / "… angenommen worden"
        items, last = [], 0
        for mm in re.finditer(r"(abgelehnt|angenommen)\s+worden", txt):
            items.append((mm.group(1), txt[last:mm.end()]))
            last = mm.end()
        hits = []
        for res, it in items:
            if res != "abgelehnt":
                continue
            flat = re.sub(r"-\s*\n\s*", "", it).replace("\n", " ")
            cited = {f"fga/{y}/{n}" for y, n in re.findall(r"BBl (\d{4}) (\d+)", flat)} if inline else set()
            for v in refs:
                dd = v.get("dd") or ""
                if v["id"] in cited:
                    v["rejected"] = day
                    hits.append(v["id"])
                    continue
                if not dd or dd > day or cited:
                    continue
                y, mo, dy = dd.split("-")
                ds = f"{int(dy)}. {list(MONTHS)[int(mo) - 1]} {y}"
                words = [w for w in re.findall(r"\w+", v["title"].get("de", "").lower()) if w not in STOP and len(w) > 2]
                if ds in flat and words and sum(w in flat.lower() for w in words) >= 0.8 * len(words):
                    v["rejected"] = day
                    hits.append(v["id"])
        out.append({"decree": a.split("/eli/")[1], "vote": day, "rejected": hits})
        print(f"{day}: {len(hits)} rejected bills matched ({', '.join(hits)})", file=sys.stderr)
    json.dump(out, open(OUT / "votes.json", "w"), ensure_ascii=False, indent=0)
    json.dump(refs, open(OUT / "ref.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    votes() if sys.argv[1:] == ["votes"] else main()
