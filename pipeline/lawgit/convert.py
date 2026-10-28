"""Convert every fetched version to Markdown, with its front matter and the word check (decision 36).

Federal: build/lawgit/xml/<eli>/<date>.<lang>.xml.gz → build/lawgit/md/ch/<eli>/<date>.<lang>.md.gz
Cantonal (LexWork): build/lawgit/kt/<CT>/<nr>/<id>.json.gz → build/lawgit/md/<ct>/<nr>/<id>.<lang>.md.gz
Vaud (BLV): build/lawgit/vd/html/<htmlId>.html.gz → build/lawgit/md/vd/<cote>/<htmlId>.fr.md.gz
Geneva, Neuchâtel (SIL, text in force only): build/cantonal/raw/<CT>/htm/<page>.htm → build/lawgit/md/<ct>/<nr>/current.fr.md.gz
Each conversion is checked: the words of the source's text against the words of the Markdown (multiset); the result
of every file goes to build/lawgit/check_<jur>.json. Resumable (existing Markdown is kept unless --force).
Usage: python3 pipeline/lawgit/convert.py [ch] [kt] [vd] [sil] [pend] [pdfcur] [zh] [ktfront] [--force]
(ktfront: rewrite the heads of the converted LexWork files only, see kt_front.)
"""
import gzip
import json
import re
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import akn2md  # noqa: E402
import lexwork2md  # noqa: E402
import pdf2md  # noqa: E402
import sil2md  # noqa: E402
import vd2md  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from refresh import TODAY, digest  # noqa: E402
from build_repo import in_force_acts  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
B = ROOT / "build/lawgit"
FORCE = "--force" in sys.argv

NOTICE_CH = {
    "de": "Nicht amtliche Wiedergabe der konsolidierten Fassung (Fedlex). Massgebend ist die Veröffentlichung in der "
          "Amtlichen Sammlung (Art. 15 PublG, SR 170.512).",
    "fr": "Reproduction non officielle de la version consolidée (Fedlex). Seule la publication au Recueil officiel fait "
          "foi (art. 15 LPubl, RS 170.512).",
    "it": "Riproduzione non ufficiale della versione consolidata (Fedlex). Fa stato la pubblicazione nella Raccolta "
          "ufficiale (art. 15 LPubb, RS 170.512).",
    "rm": "Nicht amtliche Wiedergabe der konsolidierten Fassung (Fedlex). Massgebend ist die Veröffentlichung in der "
          "Amtlichen Sammlung (Art. 15 PublG, SR 170.512).",
    "en": "Unofficial reproduction of the consolidated version (Fedlex). English is not an official language of the "
          "Confederation: this translation is for information only and has no legal force. Only the publication in the "
          "Official Compilation is authoritative (Art. 15 PublA, SR 170.512).",
}
NOTICE_PDF = {
    "de": "Diese Fassung veröffentlicht der Kanton nur als PDF: Der Text ist daraus gelesen, die Gliederung aus dem Satzbild "
          "erschlossen.",
    "fr": "Le canton ne publie cette version qu’en PDF : le texte en est extrait, la structure déduite de la mise en page.",
    "it": "Il Cantone pubblica questa versione solo in PDF: il testo ne è estratto, la struttura dedotta dall’impaginazione.",
    "rm": "Diese Fassung veröffentlicht der Kanton nur als PDF: Der Text ist daraus gelesen, die Gliederung aus dem Satzbild "
          "erschlossen.",
}
NOTICE_KT = {
    "de": "Nicht amtliche Wiedergabe aus der systematischen Gesetzessammlung des Kantons {ct}. Massgebend ist die amtliche "
          "Veröffentlichung des Kantons.",
    "fr": "Reproduction non officielle du recueil systématique du canton {ct}. Seule la publication officielle du canton "
          "fait foi.",
    "it": "Riproduzione non ufficiale della raccolta sistematica del Cantone {ct}. Fa stato la pubblicazione ufficiale del "
          "Cantone.",
    "rm": "Nicht amtliche Wiedergabe aus der systematischen Gesetzessammlung des Kantons {ct}. Massgebend ist die "
          "amtliche Veröffentlichung des Kantons.",
}


def write_gz(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
        f.write(text)
    tmp.rename(path)


# ---- federal
_meta = None


def fed_meta():
    global _meta
    if _meta is None:
        H = json.load(open(ROOT / "data/fedlex_history.json"))
        sys.path.insert(0, str(ROOT / "pipeline"))
        import inforce
        sr = {}
        for r in inforce.rows():
            sr.setdefault(r["act"].rstrip("/"), r["notation"])
        _meta = (H, sr)
    return _meta


def fed_convert(args):
    src, out, date, lang, act, url = args
    H, SR = fed_meta()
    h = H.get(act) or {}
    xml = gzip.open(src).read()
    front = {
        "sr": SR.get(act) or h.get("n") or "",
        "title": (h.get("title") or {}).get(lang) or "",
        "short": (h.get("abbr") or {}).get(lang) or "",
        "eli": act,
        "language": lang,
        "version": date,
        "adopted": h.get("date") or "",
        "in_force": h.get("in_force") or "",
        "source": url,
        "url": act.replace("https://fedlex.data.admin.ch", "https://www.fedlex.admin.ch") + f"/{date.replace('-', '')}/{lang}",
    }
    try:
        md = akn2md.convert(xml, front, NOTICE_CH.get(lang, NOTICE_CH["de"]))
    except Exception as e:                                      # recorded in the check file, never silently dropped
        return {"f": str(out), "error": str(e)[:300]}
    a, b = Counter(akn2md.text_tokens_xml(xml)), Counter(akn2md.text_tokens_md(md))
    write_gz(out, md)
    miss, extra = a - b, b - a
    return {"f": str(out.relative_to(B)), "n": sum(a.values()), "miss": sum(miss.values()), "extra": sum(extra.values()),
            "ex": [w for w, _ in (miss + extra).most_common(6)]}


def federal():
    V = json.load(open(B / "fedlex_versions.json"))
    jobs = []
    for act, vs in V.items():
        key = act.split("/eli/", 1)[1].replace("/", "_")
        for v in vs:
            for lang, url in v["u"].items():
                src = B / "xml" / key / f"{v['d']}.{lang}.xml.gz"
                out = B / "md/ch" / key / f"{v['d']}.{lang}.md.gz"
                if src.exists() and (FORCE or not out.exists()):
                    jobs.append((src, out, v["d"], lang, act, url))
    print(f"federal: {len(jobs)} to convert", file=sys.stderr)
    res = run(fed_convert, jobs)
    merge_check("ch", res)


# ---- cantonal (LexWork)
SPAN = None


def header_names(v: dict, lang: str) -> tuple[str, str]:
    """Title and abbreviation of a version in one language, from its header (empty for a version without structured text)."""
    hs = lexwork2md.soup((((v.get("json_content") or {}).get("document") or {}).get("header") or {}).get(lang, ""))
    for x in hs.find_all(["sup", "a"]):                  # footnote calls
        x.decompose()
    t, a = hs.find(class_="title"), hs.find(class_="abbreviation")
    return (akn2md.squash(t.get_text(" ")) if t else "", akn2md.squash(a.get_text(" ")).strip("() ") if a else "")


def kt_front(ct: str, act: dict, v: dict, lang: str, adir: Path, md: str = "") -> dict:
    """The head of a LexWork file in its own language. The portal answers in the collection's first language (FR: French,
    BE: German): in another language the title and abbreviation come from the version's header in that language, for a
    version read from its PDF from the heading the PDF gives ("Verordnung über den Rebbau und den Wein (VRW)"), else from
    another version's header; never the other language's. Dates as days; the portal's links in that language."""
    global SPAN
    if SPAN is None:
        import build_repo
        SPAN = build_repo.parse_span
    link = act.get("canonical_link") or ""
    m = re.search(r"/(?:app|api)/(\w\w)/", link or v.get("pdf_link_tol") or "")
    first = m.group(1) if m else lang
    title, short = (v.get("title") or act.get("title") or ""), (v.get("abbreviation") or act.get("abbreviation") or "")
    if lang != first:
        title, short = header_names(v, lang)
        h1 = re.search(r"^# (.+)$", md, re.M)
        if not title and h1:
            h = re.sub(r"\[\^[^\]]+\]|\*+", "", h1.group(1)).strip()
            m = re.fullmatch(r"(.+?)\s*\(([^()]{1,25})\)", h)
            title, short = (m.group(1), m.group(2)) if m else (h, "")
        if not title or not short:                       # another version of the act, the current one first
            ids = [str((act.get("current_version") or {}).get("id") or "")]
            for f in [adir / f"{i}.json.gz" for i in ids if i] + sorted(adir.glob("[0-9]*.json.gz"), reverse=True):
                if f.exists():
                    t2, s2 = header_names(json.load(gzip.open(f, "rt", encoding="utf-8")), lang)
                    if t2:
                        title, short = title or t2, short or s2
                        break
    sp = SPAN(v.get("version_dates_str") or "")
    ln = (lambda u: re.sub(r"/(app|api)/\w\w/", rf"/\1/{lang}/", u, count=1) if u else "")
    return {"canton": ct, "number": act.get("systematic_number"), "title": title, "short": short, "language": lang,
            "version": sp.get("from", ""), "valid_until": sp.get("to", ""), "corrected": sp.get("fix", ""),
            "version_adopted": sp.get("adopted", ""), "adopted": act.get("date_of_decision") or "",
            "in_force": act.get("enactment") or "", "url": ln(link), "pdf": ln(v.get("pdf_link_tol") or "")}


def set_front(md: str, front: dict) -> str:
    """Replace the YAML head of a file (the keys of the old head that the new one lacks, such as text: pdf, are kept)."""
    head, body = md[4:].split("\n---\n", 1)
    old = dict(x.split(": ", 1) for x in head.split("\n") if ": " in x)
    new = {k: akn2md.yval(v) for k, v in front.items() if v not in (None, "", [])}
    keep = {k: x for k, x in old.items() if k not in front and k not in ("original",)}
    return "---\n" + "\n".join(f"{k}: {x}" for k, x in {**new, **keep}.items()) + "\n---\n" + body


def ktfront_one(args):
    """ktfront: rewrite the head of one converted LexWork file (no new reading of the text; the word check is unchanged)."""
    o, src = args
    v = json.load(gzip.open(src, "rt", encoding="utf-8"))
    act = json.load(gzip.open(src.parent / "_act.json.gz", "rt", encoding="utf-8"))
    md = gzip.open(o, "rt", encoding="utf-8").read()
    lang = o.name.split(".")[1]
    new = set_front(md, kt_front(src.parent.parent.name, act, v, lang, src.parent, md))
    if new != md:
        write_gz(o, new)
        return 1
    return 0


def ktfront():
    jobs = []
    for d in sorted((B / "kt").iterdir()):
        if d.is_dir():
            for src in d.glob("*/[0-9]*.json.gz"):
                for o in (B / "md" / d.name.lower() / src.parent.name).glob(f"{src.name.split('.')[0]}.*.md.gz"):
                    jobs.append((o, src))
    print(f"ktfront: {len(jobs)} files", file=sys.stderr)
    with Pool(4) as p:
        n = sum(p.imap_unordered(ktfront_one, jobs, chunksize=16))
    print(f"ktfront: {n} heads rewritten", file=sys.stderr)


def kt_convert(args):
    ct, src, outdir = args
    v = json.load(gzip.open(src, "rt", encoding="utf-8"))
    act = json.load(gzip.open(src.parent / "_act.json.gz", "rt", encoding="utf-8"))
    langs = [x["language"]["iso639_1_code"] for x in (v.get("available_languages") or [])] or ["de"]
    out = []
    for lang in langs:
        o = outdir / f"{src.name.split('.')[0]}.{lang}.md.gz"
        if o.exists() and not FORCE:
            continue
        front = kt_front(ct, act, v, lang, src.parent)
        md = lexwork2md.convert(v, lang, front, NOTICE_KT.get(lang, NOTICE_KT["de"]).format(ct=ct))
        if md is None:                                   # no structured text: read the canton's PDF (lexwork_pdf_fetch.py)
            pdf = B / "kt_pdf" / ct / src.parent.name / f"{src.name.split('.')[0]}.{lang}.pdf"
            if not pdf.exists():
                out.append({"f": str(o.relative_to(B)), "pdf_only": 1})
                continue
            try:
                md, want = pdf2md.convert_checked(pdf, {**front, "text": "pdf"},
                                                  NOTICE_KT.get(lang, NOTICE_KT["de"]).format(ct=ct) + " " + NOTICE_PDF.get(lang, NOTICE_PDF["de"]),
                                                  lang, act.get("systematic_number") or "")
            except Exception as e:                       # noqa: BLE001 — recorded, the version stays a stub
                out.append({"f": str(o.relative_to(B)), "pdf_only": 1, "error": str(e)[:200]})
                continue
            md = set_front(md, kt_front(ct, act, v, lang, src.parent, md))      # the title the PDF gives in its language
            got = Counter(akn2md.text_tokens_md(md))
            write_gz(o, md)
            miss, extra = want - got, got - want
            out.append({"f": str(o.relative_to(B)), "pdf": 1, "n": sum(want.values()), "miss": sum(miss.values()),
                        "extra": sum(extra.values()), "ex": [w for w, _ in (miss + extra).most_common(6)],
                        "cid": md.count("(cid:")})
            continue
        a, b = Counter(lexwork2md.text_tokens_json(v, lang)), Counter(akn2md.text_tokens_md(md))
        write_gz(o, md)
        miss, extra = a - b, b - a
        out.append({"f": str(o.relative_to(B)), "n": sum(a.values()), "miss": sum(miss.values()), "extra": sum(extra.values()),
                    "ex": [w for w, _ in (miss + extra).most_common(6)]})
    return out


def cantonal():
    jobs = []
    for d in sorted((B / "kt").iterdir()):
        if not d.is_dir():
            continue
        for src in d.glob("*/*.json.gz"):
            if src.name.startswith("_"):
                continue
            jobs.append((d.name, src, B / "md" / d.name.lower() / src.parent.name))
    print(f"cantonal: {len(jobs)} versions", file=sys.stderr)
    res = [x for r in run(kt_convert, jobs) if r for x in r]
    merge_check("kt", res)


# ---- Vaud (BLV)
def vd_convert(args):
    act, v, src, out = args
    h = gzip.open(src).read().decode("utf-8")
    front = {"canton": "VD", "number": act["cote"], "title": act.get("titreCompletSansCote") or act.get("titre") or "",
             "short": act.get("abreviation") or "", "language": "fr", "version": v.get("_start") or "",
             "url": f"https://prestations.vd.ch/pub/blv-publication/actes/consolide/{act['cote']}?id={act['id']}"}
    md = vd2md.convert(h, front, NOTICE_KT["fr"].format(ct="VD"))
    a, b = Counter(vd2md.text_tokens(h)), Counter(vd2md.md_tokens(md))
    write_gz(out, md)
    miss, extra = a - b, b - a
    return {"f": str(out.relative_to(B)), "n": sum(a.values()), "miss": sum(miss.values()), "extra": sum(extra.values()),
            "ex": [w for w, _ in (miss + extra).most_common(6)]}


def vaud():
    jobs = []
    for r in json.load(open(B / "vd/acts.json")):
        a = r["act"]
        for v in r["versions"]:
            if v.get("_error"):
                continue
            hid = v["htmlId"]
            src = next((p for p in (B / "vd/html" / f"{hid}.html.gz", ROOT / "build/cantonal/raw/VD/html" / f"{hid}.html.gz") if p.exists()), None)
            out = B / "md/vd" / re.sub(r"[^\w.\-]", "_", a["cote"]) / f"{hid}.fr.md.gz"
            if src and (FORCE or not out.exists()):
                jobs.append((a, v, src, out))
    print(f"vd: {len(jobs)} versions", file=sys.stderr)
    merge_check("vd", run(vd_convert, jobs))


# ---- Geneva, Neuchâtel (SIL)
RUN_DATE = TODAY                                         # the day of the run (refresh.py)


def stale(src: Path, out: Path, chk: dict) -> bool:
    """A text in force (GE, NE, JU, ZH): convert again when its source differs from the one converted last."""
    return FORCE or not out.exists() or (chk.get(str(out.relative_to(B))) or {}).get("src") != digest(src)


def sil_convert(args):
    ct, nr, a, src, out = args
    b = src.read_bytes()
    ver = sil2md.version_date(b, ct, RUN_DATE)
    front = {"canton": ct, "number": nr, "title": a.get("title") or "", "short": a.get("abbr") or "", "language": "fr",
             "version": ver, "adopted": a.get("adopted") or "", "url": a.get("url") or ""}
    try:
        md = sil2md.convert(b, ct, front, NOTICE_KT["fr"].format(ct=ct))
    except Exception as e:                                      # recorded in the check file, never silently dropped
        return {"f": str(out.relative_to(B)), "error": str(e)[:300]}
    a_, b_ = Counter(sil2md.text_tokens(b, ct)), Counter(akn2md.text_tokens_md(md))
    write_gz(out, md)
    miss, extra = a_ - b_, b_ - a_
    return {"f": str(out.relative_to(B)), "n": sum(a_.values()), "miss": sum(miss.values()), "extra": sum(extra.values()),
            "ex": [w for w, _ in (miss + extra).most_common(6)], "version": ver, "src": digest(src)}


def sil():
    chk = json.load(open(B / "check_sil.json")) if (B / "check_sil.json").exists() else {}
    jobs = []
    for ct in ("GE", "NE"):
        for nr, a in in_force_acts(ct).items():
            src = ROOT / "build/cantonal/raw" / ct / "htm" / a["url"].rsplit("/", 1)[1]
            out = B / "md" / ct.lower() / re.sub(r"[^\w.\-]", "_", nr) / "current.fr.md.gz"
            if src.exists() and stale(src, out, chk):
                jobs.append((ct, nr, a, src, out))
    print(f"sil: {len(jobs)} acts", file=sys.stderr)
    merge_check("sil", run(sil_convert, jobs))


# ---- adopted, not yet in force; consultation drafts (fedlex_pending.py)
NOTICE_AS = {
    "de": "Nicht amtliche Wiedergabe aus der Amtlichen Sammlung (AS). Der Erlass ist veröffentlicht, aber noch nicht in Kraft; "
          "massgebend ist die Veröffentlichung in der AS (Art. 15 PublG, SR 170.512).",
    "fr": "Reproduction non officielle du Recueil officiel (RO). L’acte est publié mais n’est pas encore en vigueur ; seule la "
          "publication au RO fait foi (art. 15 LPubl, RS 170.512).",
    "it": "Riproduzione non ufficiale della Raccolta ufficiale (RU). L’atto è pubblicato ma non ancora in vigore; fa stato la "
          "pubblicazione nella RU (art. 15 LPubb, RS 170.512).",
}
NOTICE_REF = {
    "de": "Nicht amtliche Wiedergabe aus dem Bundesblatt (BBl). Von der Bundesversammlung beschlossen, dem fakultativen "
          "Referendum unterstellt, nicht in Kraft.",
    "fr": "Reproduction non officielle de la Feuille fédérale (FF). Adopté par l’Assemblée fédérale, sujet au référendum "
          "facultatif, pas en vigueur.",
    "it": "Riproduzione non ufficiale del Foglio federale (FF). Adottato dall’Assemblea federale, sottoposto a referendum "
          "facoltativo, non in vigore.",
}
NOTICE_VL = {
    "de": "Entwurf in der Vernehmlassung, kein geltendes Recht. Nicht amtliche Wiedergabe aus dem PDF auf Fedlex; der Text ist "
          "daraus gelesen, die Gliederung aus dem Satzbild erschlossen.",
    "fr": "Projet mis en consultation, pas du droit en vigueur. Reproduction non officielle du PDF publié sur Fedlex ; le texte "
          "en est extrait, la structure déduite de la mise en page.",
    "it": "Progetto posto in consultazione, non diritto in vigore. Riproduzione non ufficiale del PDF pubblicato su Fedlex; il "
          "testo ne è estratto, la struttura dedotta dall’impaginazione.",
}
PEND = B / "pending"


def ref_label(i: str) -> str:                           # "oc/2026/510" → "AS 2026 510", "fga/2026/2718" → "BBl 2026 2718"
    fam, y, n = i.split("/")[:3]
    return f"{'AS' if fam == 'oc' else 'BBl'} {y} {n}"


def pend_convert(args):
    kind, a, lg, src, out = args
    if kind in ("as", "ref"):
        xml = gzip.open(src).read()
        front = {"status": "beschlossen, noch nicht in Kraft" if kind == "as" else "Referendumsvorlage",
                 "reference": ref_label(a["id"]), "title": a["title"].get(lg) or a["title"].get("de", ""), "language": lg,
                 "adopted": a.get("dd") or "", "published": a["pd"],
                 "in_force": a.get("eif") or "",                   # a list: several dates when it enters into force in stages
                 "url": f"https://www.fedlex.admin.ch/eli/{a['id']}/{lg}"}
        if kind == "ref":
            m = re.search(rb"Ablauf der Referendumsfrist:?\s*([^<]+)<", gzip.open(PEND / "xml" / (a["id"].replace("/", "_") + ".de.xml.gz")).read()) \
                if (PEND / "xml" / (a["id"].replace("/", "_") + ".de.xml.gz")).exists() else None
            front["referendum_deadline"] = de_iso(m.group(1).decode()) if m else ""
            front["as"] = ref_label(a["as"]) if a.get("as") else ""
        notice = (NOTICE_AS if kind == "as" else NOTICE_REF).get(lg, NOTICE_AS["de"] if kind == "as" else NOTICE_REF["de"])
        try:
            md = akn2md.convert(xml, front, notice)
        except Exception as e:                            # noqa: BLE001
            return {"f": str(out.relative_to(B)), "error": str(e)[:200]}
        a_, b_ = Counter(akn2md.text_tokens_xml(xml)), Counter(akn2md.text_tokens_md(md))
        write_gz(out, md)
        miss = a_ - b_
        return {"f": str(out.relative_to(B)), "n": sum(a_.values()), "miss": sum(miss.values()),
                "extra": sum((b_ - a_).values()), "ex": [w for w, _ in miss.most_common(6)],
                "deadline": front.get("referendum_deadline", "")}
    c, dn = a
    H, SR = fed_meta()
    front = {"status": "Vernehmlassung", "title": c["title"].get(lg) or c["title"].get("de", ""),
             "document": (c["docs"][dn]["title"].get(lg) or ""), "language": lg, "opened": c["start"], "closes": c["end"],
             "affects": [SR.get(x.rstrip("/")) or x for x in c["impacts"]], "consultation": c["id"],
             "url": f"https://www.fedlex.admin.ch/eli/{c['id']}/{lg}", "text": "pdf"}
    try:
        md, want = pdf2md.convert_checked(src, front, NOTICE_VL.get(lg, NOTICE_VL["de"]), lg, "")
    except Exception as e:                                # noqa: BLE001
        return {"f": str(out.relative_to(B)), "error": str(e)[:200]}
    got = Counter(akn2md.text_tokens_md(md))
    write_gz(out, md)
    miss = want - got
    return {"f": str(out.relative_to(B)), "pdf": 1, "n": sum(want.values()), "miss": sum(miss.values()),
            "extra": sum((got - want).values()), "ex": [w for w, _ in miss.most_common(6)]}


MONTHS_DE = {m: i + 1 for i, m in enumerate("Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split())}


def de_iso(s: str) -> str:
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zä]+)\s+(\d{4})", s)
    return f"{m.group(3)}-{MONTHS_DE.get(m.group(2), 0):02d}-{int(m.group(1)):02d}" if m and m.group(2) in MONTHS_DE else ""


def pending():
    jobs = []
    for kind in ("as", "ref"):
        for a in json.load(open(PEND / f"{kind}.json")):
            for lg in a["xml"]:
                src = PEND / "xml" / (a["id"].replace("/", "_") + f".{lg}.xml.gz")
                out = B / "md/pend" / kind / (a["id"].replace("/", "_") + f".{lg}.md.gz")
                if src.exists() and (FORCE or not out.exists()):
                    jobs.append((kind, a, lg, src, out))
    for c in json.load(open(PEND / "cons.json")):
        for dn, d in c["docs"].items():
            for lg in d["pdf"]:
                src = PEND / "pdf" / (c["id"].replace("/", "_") + f"_{dn}.{lg}.pdf")
                out = B / "md/pend/cons" / (c["id"].replace("/", "_") + f"_{dn}.{lg}.md.gz")
                if src.exists() and (FORCE or not out.exists()):
                    jobs.append(("cons", (c, dn), lg, src, out))
    print(f"pending: {len(jobs)} files", file=sys.stderr)
    merge_check("pend", run(pend_convert, jobs))


# ---- Zürich, Jura: the text in force, read from the canton's PDF (cached by pipeline/cantonal/zh.py, ju.py)
RAWK = ROOT / "build/cantonal/raw"


def zh_since(key: str) -> str:
    """ZH: the current version applies from the day its predecessor ended ("Historie: 121 (in Kraft bis 01.07.2024)")."""
    f = RAWK / "ZH/detail" / f"{key}.html"
    if not f.exists():
        return ""
    ends = [f"{y}-{m}-{d}" for d, m, y in re.findall(r"\(in Kraft bis (\d{2})\.(\d{2})\.(\d{4})\)", f.read_text("utf-8", "replace"))]
    ends = [e for e in ends if e <= RUN_DATE]
    return max(ends) if ends else ""


def pdfcur_convert(args):
    ct, nr, a, src, out, lg, hint = args
    front = {"canton": ct, "number": nr, "title": a.get("title") or "", "short": a.get("abbr") or "", "language": lg,
             "version": "", "adopted": a.get("adopted") or "", "url": a.get("url") or "", "text": "pdf"}
    try:
        md, want = pdf2md.convert_checked(src, front, NOTICE_KT[lg].format(ct=ct) + " " + NOTICE_PDF[lg], lg, nr)
    except Exception as e:                                # noqa: BLE001
        return {"f": str(out.relative_to(B)), "error": str(e)[:200]}
    ver = hint or pdf2md.latest_in_force(md, RUN_DATE)
    if ver:                                              # the version's day, known only once the text is read
        md = re.sub(r"^(language: .*)$", lambda m: f'{m.group(1)}\nversion: "{ver}"', md, count=1, flags=re.M)
    got = Counter(akn2md.text_tokens_md(md))
    write_gz(out, md)
    miss = want - got
    return {"f": str(out.relative_to(B)), "pdf": 1, "n": sum(want.values()), "miss": sum(miss.values()),
            "extra": sum((got - want).values()), "ex": [w for w, _ in miss.most_common(6)], "version": ver, "src": digest(src)}


def pdfcur():
    KZ = in_force_acts("ZH")
    chk = json.load(open(B / "check_pdfcur.json")) if (B / "check_pdfcur.json").exists() else {}
    jobs = []
    for m in json.load(open(RAWK / "ZH/meta.json")):
        key = m["page"].rsplit("/", 1)[1].replace(".html", "")
        src, nr = RAWK / "ZH/pdf" / f"{key}.pdf", m["sr"]
        out = B / "md/zh" / re.sub(r"[^\w.\-]", "_", nr) / "current.de.md.gz"
        a = KZ.get(nr) or {"title": "", "url": m.get("page") or ""}
        if src.exists() and stale(src, out, chk):
            jobs.append(("ZH", nr, a, src, out, "de", zh_since(key) or ""))
    for nr, a in in_force_acts("JU").items():
        m = re.search(r"[?&]id=(\d+)", a.get("url") or "")
        src = RAWK / "JU/pdf" / f"{m.group(1)}.pdf" if m else None
        out = B / "md/ju" / re.sub(r"[^\w.\-]", "_", nr) / "current.fr.md.gz"
        if src and src.exists() and stale(src, out, chk):
            jobs.append(("JU", nr, a, src, out, "fr", ""))
    print(f"pdfcur: {len(jobs)} acts", file=sys.stderr)
    merge_check("pdfcur", run(pdfcur_convert, jobs))


def zh_convert(args):
    nr, a, v, src, out = args
    front = {"canton": "ZH", "number": nr, "title": a.get("title") or "", "short": a.get("abbr") or "", "language": "de",
             "nachtrag": v["nachtrag"], "valid_until": v.get("end") or "", "adopted": a.get("adopted") or "",
             "url": "https://www.zh.ch" + v["link"], "text": "pdf"}
    try:
        md, want = pdf2md.convert_checked(src, front, NOTICE_KT["de"].format(ct="ZH") + " " + NOTICE_PDF["de"], "de", nr)
    except Exception as e:                                # noqa: BLE001
        return {"f": str(out.relative_to(B)), "error": str(e)[:200]}
    ver = pdf2md.latest_in_force(md, v.get("end") or RUN_DATE)
    if ver:
        md = re.sub(r"^(language: .*)$", lambda m: f'{m.group(1)}\nversion: "{ver}"', md, count=1, flags=re.M)
    got = Counter(akn2md.text_tokens_md(md))
    write_gz(out, md)
    miss = want - got
    return {"f": str(out.relative_to(B)), "pdf": 1, "n": sum(want.values()), "miss": sum(miss.values()),
            "extra": sum((got - want).values()), "ex": [w for w, _ in miss.most_common(6)], "version": ver}


def zhhist():
    K = in_force_acts("ZH")
    jobs = []
    for r in json.load(open(B / "zh/acts.json")):
        nr = r["sr"]
        for v in r["versions"]:
            if not v.get("pdf"):
                continue
            out = B / "md/zh" / re.sub(r"[^\w.\-]", "_", nr) / f"{v['key']}.de.md.gz"
            if FORCE or not out.exists():
                jobs.append((nr, K.get(nr) or {}, v, RAWK / "ZH/pdf" / f"{v['key']}.pdf", out))   # not v["pdf"]: an absolute path
    print(f"zh: {len(jobs)} versions", file=sys.stderr)
    merge_check("zh", run(zh_convert, jobs))


def run(fn, jobs):
    out = []
    with Pool(4) as p:
        for k, r in enumerate(p.imap_unordered(fn, jobs, chunksize=8)):
            if r:
                out.append(r)
            if k % 2000 == 0:
                print(f"  {k}/{len(jobs)}", file=sys.stderr)
    return out


def merge_check(jur: str, res: list) -> None:
    f = B / f"check_{jur}.json"
    old = json.load(open(f)) if f.exists() else {}
    for r in res:
        old[r["f"]] = r
    json.dump(old, open(f, "w"), ensure_ascii=False)
    vals = list(old.values())
    print(f"{jur}: {len(vals)} files, {sum(1 for r in vals if r.get('error'))} errors, "
          f"{sum(1 for r in vals if r.get('pdf_only'))} PDF only, {sum(1 for r in vals if r.get('pdf'))} read from PDF, "
          f"{sum(1 for r in vals if r.get('miss') or r.get('extra'))} with a word difference, "
          f"{sum(r.get('miss', 0) for r in vals)} words missing of {sum(r.get('n', 0) for r in vals)}", file=sys.stderr)


if __name__ == "__main__":
    which = [a for a in sys.argv[1:] if not a.startswith("--")] or ["ch", "kt", "vd", "sil", "pend", "pdfcur", "zh"]
    if "ch" in which:
        federal()
    if "kt" in which:
        cantonal()
    if "vd" in which:
        vaud()
    if "sil" in which:
        sil()
    if "pend" in which:
        pending()
    if "pdfcur" in which:
        pdfcur()
    if "zh" in which:
        zhhist()
    if "ktfront" in which:
        ktfront()
