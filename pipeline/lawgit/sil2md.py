"""Geneva (rs/GE) and Neuchâtel (RSN) Word-HTML pages → Markdown, in the format of akn2md.py (decision 36).

Both collections are SIL books: one Word-HTML page per act, the text in force only (no earlier versions are published),
paragraphs typed by class.

GE: p.TitreLoi, p.NoLoi, p.date, p.vigueur, p.GC/p.Vu (Ingress), p.partie/titre/chapitre/section/sousnote (headings),
p.article ("Art. 4A(15)  Droit à un acte attaquable"), p.sousmargi (marginal title inside an article), p.Texte/TexteTL
(alineas, <sup>1</sup>), p.retrait1/2/3 (letters), and at the end the change table (p.T…). The calls "(15)" stay text,
as on the page: they number the rows of the change table, which follows as a table ("Historique").

NE: p.xNom, p.xDateAdoption (day, month, year in three paragraphs), p.xEdition, p.xItalique/xVu (Ingress), p.xTitre/
xChapitre + p.xNomChapitre, p.xSection, p.xMarginale (marginal title, before its article), p.xNormal ("<b>Art. 12</b>
<sup>1</sup>…"), p.xRetrait1a/1s/2a/2s (lists), p.xCitation (quoted text of an amendment), and Word footnotes
(a[href=#_ftnN] → div#ftnN), which become footnotes of their article.
"""
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from akn2md import esc, line_safe, squash, yval

SFX = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies)"
ART = re.compile(rf"^(Art(?:icle)?\.?\s*(?:premier|unique|\d+(?:[A-Za-z](?![a-z.]))?{SFX}?|[IVXLC]+){SFX}?)(?![\w])\s*(.*)$", re.S)
MARK = re.compile(r"^(?:[a-z]{1,2}\)|[a-z]{1,2}\s?\.|\d+°|\d+[.)]|[ivx]+\)|[–\-•·])(?=\s)")
NUMLINE = re.compile(r"^\d[\d.]*[a-z]?$")

GE_HEAD = {"partie": 1, "titre": 2, "chapitre": 3, "section": 4, "sousnote": 5}
NE_HEAD = {"xTitre": 1, "xTitreCitation": 1, "xChapitre": 2, "xChapitreCitation": 2, "xSection": 3, "xSectionCitation": 3}
NE_NAME = {"xNomChapitre", "NomChapitre", "xnomchapitre0", "xNomChapitreCitation"}
NE_MARG = {"xMarginale", "Marginale", "MarginaleRetrait", "xMarginaleRetrait", "xMarginaleRetrait2", "MarginaleRetrait2",
           "CitationRetraitA1"}
LIST0 = {"retrait1", "retrait10", "xRetrait1a", "xRetrait1s", "xRetrait1", "xretrait1a0", "xRetraitCitation1a",
         "xRetraitCitation1s", "xRetraitCitation", "MsoListParagraph", "MsoListParagraphCxSpFirst",
         "MsoListParagraphCxSpMiddle", "MsoListParagraphCxSpLast"}
LIST1 = {"retrait2", "retrait20", "xRetrait2a", "xRetrait2s", "xRetrait2", "xRetraitCitation2a"}
LIST2 = {"retrait3", "retrait4"}
NE_ART_CLS = {"xNormal", "xLigneBlanche", "Normal", "Default", "MsoBodyText", "Texte", "xnormal0", "MsoCommentText", ""}


def decode(b: bytes) -> str:
    for enc in ("utf-8", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("cp1252", errors="replace")


def cls_of(p) -> str:
    return (p.get("class") or [""])[0]


def is_sup_span(el) -> bool:
    st = (el.get("style") or "").replace(" ", "").lower()
    return "vertical-align:super" in st or bool(re.search(r"position:relative;top:-\d", st))


def blocks(body):
    """Paragraphs and top-level tables of the body, in document order (footnote bodies and table cells excluded)."""
    for el in body.find_all(["p", "table", "h1", "h2", "h3", "h4", "h5", "h6"]):
        if el.find_parent(["table", "h1", "h2", "h3", "h4", "h5", "h6"]) is not None:
            continue
        if el.find_parent("div", id=re.compile(r"^_?ftn\d+")) is not None:
            continue
        yield el


class SIL:
    def __init__(self, soup, ct):
        self.ct = ct
        self.lines, self.pending, self.count, self.scope, self.used = [], [], {}, "t", set()
        self.fn = {}
        if ct == "NE":                                   # Word footnotes, by id
            for d in soup.find_all("div", id=re.compile(r"^_?ftn\d+")):
                t = squash(self.children(d))
                self.fn[d["id"].lstrip("_")] = re.sub(r"^(?:\[\d+\]|\(\*+\)|\*+)\s*", "", t)

    def set_scope(self, s):
        s = re.sub(r"\W", "", s) or "a"
        base, k = s, 1
        while s in self.used:
            k += 1
            s = f"{base}_{k}"
        self.used.add(s)
        self.scope = s

    def blank(self):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def para(self, s):
        s = squash(s)
        if s:
            self.blank()
            self.lines.append(line_safe(s))

    def note(self, text):
        k = self.count.get(self.scope, 0) + 1
        self.count[self.scope] = k
        lab = f"{self.scope}-{k}"
        self.pending.append((lab, squash(text)))
        return f"[^{lab}]"

    def flush(self):
        if self.pending:
            self.blank()
            self.lines += [f"[^{a}]: {b}" for a, b in self.pending]
            self.pending = []

    def inline(self, el) -> str:
        if isinstance(el, NavigableString):
            if type(el).__name__ in ("Comment", "Declaration", "ProcessingInstruction", "Doctype"):
                return ""
            return esc(str(el).replace("\xa0", " "))
        if not isinstance(el, Tag):
            return ""
        if el.name == "a":
            m = re.search(r"#_?(ftn\d+)$", el.get("href") or "") if self.ct == "NE" else None
            if m and m.group(1) in self.fn:
                return self.note(self.fn[m.group(1)])
            href = el.get("href") or ""
            t = self.children(el)
            return f"[{squash(t)}]({href})" if href.startswith("http") and squash(t) else t
        if el.name == "br":
            return " "
        inner = self.children(el)
        core = inner.strip()
        lead, trail = inner[:len(inner) - len(inner.lstrip())], inner[len(inner.rstrip()):]
        name = "sup" if el.name == "span" and is_sup_span(el) else el.name
        if name == "sup" and (core.startswith("[^") or "<sup>" in core):
            return inner
        mark = {"b": ("**", "**"), "strong": ("**", "**"), "i": ("*", "*"), "em": ("*", "*"),
                "sup": ("<sup>", "</sup>"), "sub": ("<sub>", "</sub>")}.get(name)
        if mark and core:
            if mark[0].startswith("*") and (core.startswith("*") or core.endswith("*") or re.fullmatch(r"<sup>[^<]*</sup>", core)):
                return inner                             # nested emphasis: keep the outer one only
            return f"{lead}{mark[0]}{core}{mark[1]}{trail}"
        return inner

    def children(self, el) -> str:
        return re.sub(r"[ \t\r\n]+", " ", "".join(self.inline(c) for c in el.children))

    def item(self, txt, depth):
        txt = re.sub(r"^[–\-•·]\s+", "", txt)
        if not (self.lines and re.match(r"^\s*- ", self.lines[-1])):
            self.blank()
        self.lines.append("  " * depth + "- " + re.sub(r"^(\d+)\.(?=\s)", r"\1\\.", txt))

    def table(self, t):
        rows = []
        for tr in t.find_all("tr"):
            if tr.find_parent("table") is not t:
                continue
            cells = []
            for td in tr.find_all(["td", "th"]):
                if td.find_parent("tr") is not tr:
                    continue
                ps = td.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6"]) or [td]
                cells.append("<br>".join(x for x in (squash(self.children(p)) for p in ps) if x))
            if any(cells):
                rows.append(cells)
        if not rows:
            return
        self.blank()
        self.lines.append("<table>")
        for r in rows:
            self.lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
        self.lines.append("</table>")

    def history(self, t):
        """GE's change table: RSG/title, adoption, entry into force; one row per line of the table."""
        rows = []
        for tr in t.find_all("tr"):
            cells = [squash(self.children(td)) for td in tr.find_all("td") if td.find_parent("tr") is tr]
            if any(cells):
                rows.append([c.replace("|", "\\|") for c in cells])
        if not rows:
            return
        self.flush()
        self.blank()
        self.lines += ["## Historique", ""]
        w = max(len(r) for r in rows)
        head = rows[0] + [""] * (w - len(rows[0]))
        self.lines.append("| " + " | ".join(head) + " |")
        self.lines.append("|" + "---|" * w)
        for r in rows[1:]:
            self.lines.append("| " + " | ".join(r + [""] * (w - len(r))) + " |")


def head_md(lvl, top, txt):
    return ("##" if lvl == top else "###") + " " + txt


def convert(html_bytes: bytes, ct: str, front: dict, notice: str) -> str:
    soup = BeautifulSoup(decode(html_bytes), "lxml")
    for x in soup(["script", "style"]):
        x.decompose()
    d = SIL(soup, ct)
    body = soup.body                                     # every WordSection (annexes are in WordSection2 …)
    els = list(blocks(body))
    heads = GE_HEAD if ct == "GE" else NE_HEAD
    present = sorted({heads[cls_of(p)] for p in els if p.name == "p" and cls_of(p) in heads})
    top = present[0] if present else 0
    title, intro, marg, date_parts = "", True, [], []
    pend_head = None                                     # NE: "Chapitre premier" waits for its name

    def put_head(lvl, txt):
        d.flush()
        d.set_scope("h" + txt[:24])
        d.blank()
        d.lines.append(head_md(lvl, top, txt))

    def put_marg():
        for m in marg:
            d.para(f"**{m}**")
        marg.clear()

    def handle(p):
        nonlocal title, intro, pend_head, date_parts, last
        if p.name == "table":
            if ct == "NE" and p.find("p", class_=["xNom", "Nom"]) is not None and not title:
                for q in p.find_all("p"):                # newer NE pages: date, title, edition in a table
                    handle(q)
                return
            if ct == "GE" and p.find("p", class_="TitreLoi") is not None:
                for q in p.find_all("p"):                # newer GE pages: title and RSG number in a table
                    handle(q)
                return
            if ct == "GE" and p.find("p", class_=re.compile(r"^Ttete")):
                put_marg()
                d.history(p)
            else:
                d.table(p)
            return
        if re.fullmatch(r"h[1-6]", p.name):             # Word headings ("A) La Conférence du Concordat")
            t = squash(d.children(p))
            if t:
                put_marg()
                put_head(9, re.sub(r"^\*+|\*+$", "", t).strip() or t)
            return
        c = cls_of(p)
        txt = re.sub(r"\*\*(\s*)\*\*", r"\1", squash(d.children(p)))     # "**Art.** **2**"
        plain = squash(p.get_text(" ").replace("\xa0", " "))
        if c in ("xDateAdoption",):
            if plain:
                date_parts.append(txt)
            return
        if date_parts:
            d.para(" ".join(date_parts))
            date_parts = []
        if pend_head is not None and (c not in NE_NAME or not txt):
            if not txt:
                return
            put_head(*pend_head)
            pend_head = None
        if not txt:
            return
        if c in ("TitreLoi", "xNom", "Nom"):
            if not title:
                title, last = txt, "title"
            else:                                        # a second title (an annex, a model text)
                d.para(f"**{txt}**")
            return
        if ct == "GE" and (c in ("NoLoi", "ligne") or (c == "MsoNormal" and plain == "Texte en vigueur")):
            return
        if ct == "NE" and intro and not title and c in ("MsoNormal", "") and NUMLINE.match(plain):
            return                                       # the RSN number above the title
        if re.fullmatch(r"(?:\[\^[^\]]+\]\s*)+", txt) and last == "title":
            title += txt.replace(" ", "")
            return
        last = None
        if re.fullmatch(r"(?:\[\^[^\]]+\]\s*)+", txt) and d.lines:
            k = len(d.lines) - 1                         # a call on its own line: to the line before
            while k > 0 and d.lines[k] == "":
                k -= 1
            d.lines[k] += txt.replace(" ", "")
            return
        if ct == "NE" and c in NE_NAME and pend_head is not None:
            lvl, h = pend_head
            pend_head = None
            put_head(lvl, squash(f"{h} {txt}"))
            return
        if c in heads:
            put_marg()
            intro = False
            if ct == "NE" and c in ("xTitre", "xChapitre", "xTitreCitation", "xChapitreCitation") and len(plain) < 40:
                pend_head = (heads[c], txt)
                return
            put_head(heads[c], txt)
            return
        if ct == "NE" and c in NE_MARG:
            intro = False
            marg.append(txt)
            return
        if ct == "GE" and c in ("article", "article0"):
            m = ART.match(txt)
            if m:
                intro = False
                d.flush()
                d.set_scope(m.group(1).replace("Article", "").replace("Art.", ""))
                rest = m.group(2)
                calls = re.match(r"^((?:\s*<sup>[^<]*</sup>)*)\s*(.*)$", rest)
                d.blank()
                d.lines.append("#### " + squash(m.group(1)) + calls.group(1).replace(" ", ""))
                if calls.group(2):
                    d.lines += ["", f"**{calls.group(2)}**"]
                return
        if ct == "NE" and c in NE_ART_CLS:
            m = re.match(r"^\*\*(Art(?:icle)?\.?\s*[^*]{1,24}?)\*\*\s*((?:\[\^[^\]]+\]\s*)*)(.*)$", txt)
            if m and ART.match(m.group(1)) and not ART.match(m.group(1)).group(2):
                num, calls, rest = squash(m.group(1)), m.group(2).replace(" ", ""), m.group(3)
            else:
                m2 = ART.match(txt) if c in ("Normal", "Default", "MsoBodyText", "", "MsoCommentText") else None
                if m2 and re.match(r"^\s*(?:<sup>\d|\d+\s|[A-ZÀ-Ý])", m2.group(2)):
                    num, calls, rest = squash(m2.group(1)), "", m2.group(2)
                else:
                    num = None
            if num:
                intro = False
                d.flush()
                d.set_scope(num.replace("Article", "").replace("Art.", ""))
                d.blank()
                d.lines.append("#### " + num + calls)
                for mm in marg:
                    d.lines += ["", f"**{mm}**"]
                marg.clear()
                rest = squash(re.sub(r"^<sup>(\d+\w*)</sup>\s*", r"<sup>\1</sup> ", rest))
                rest = re.sub(r"^(\d+)\s+(?=[A-ZÀ-Ý])", r"<sup>\1</sup> ", rest) if c != "xNormal" else rest
                if rest:
                    d.para(rest)
                return
        put_marg()
        if c in ("sousmargi", "sousmargi0"):
            d.para(f"*{txt}*")
            return
        if c in LIST0 and MARK.match(plain):
            d.item(txt, 0)
            return
        if c in LIST1 and MARK.match(plain):
            d.item(txt, 1)
            return
        if c in LIST2 and MARK.match(plain):
            d.item(txt, 2)
            return
        txt = re.sub(r"^<sup>(\d+\w*)</sup>\s*", r"<sup>\1</sup> ", txt)
        d.para(txt)

    last = None
    for p in els:
        handle(p)
    if date_parts:
        d.para(" ".join(date_parts))
    if pend_head is not None:
        put_head(*pend_head)
    put_marg()
    d.flush()
    yaml = ["---"] + [f"{k}: {yval(v)}" for k, v in front.items() if v not in (None, "", [])] + ["---", "", f"> {notice}", ""]
    lines = [re.sub(r"<sup>(\d+[a-z]*)</sup>(?=[A-Za-zÀ-ÿ«])", r"<sup>\1</sup> ", x) for x in d.lines]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join([f"# {title or front.get('title', '')}"] + lines)).strip() + "\n"
    return "\n".join(yaml) + "\n" + out


def text_tokens(html_bytes: bytes, ct: str) -> list[str]:
    """The page's words (the counterpart of akn2md.text_tokens_md on the Markdown): footnote calls and the furniture
    left out of the Markdown removed, each footnote's text once per call."""
    soup = BeautifulSoup(decode(html_bytes), "lxml")
    for x in soup(["script", "style"]):
        x.decompose()
    calls = {}
    if ct == "NE":
        for a in soup.find_all("a", href=re.compile(r"#_?ftn\d+$")):
            k = re.search(r"(ftn\d+)$", a["href"]).group(1)
            calls[k] = calls.get(k, 0) + 1
            a.decompose()
    for x in soup.find_all(["sup", "span"]):            # a paragraph number glued to its first word
        if (x.name == "sup" or is_sup_span(x)) and re.fullmatch(r"\d+[a-z]*", x.get_text().strip()):
            nx = next((t for t in x.next_elements if isinstance(t, NavigableString) and x not in t.parents), None)
            if nx is not None and re.match(r"[A-Za-zÀ-ÿ«]", str(nx)):
                x.insert_after(" ")
    for x in soup.find_all(["sup", "sub", "b", "i", "strong", "em", "span", "a", "u", "font"]):
        x.unwrap()
    soup = BeautifulSoup(str(soup), "lxml")
    notes = []
    for dv in soup.find_all("div", id=re.compile(r"^_?ftn\d+")):
        t = re.sub(r"^(?:\[\d+\]|\(\*+\)|\*+)\s*", "", squash(dv.get_text(" ").replace("\xa0", " ")))
        notes += [t] * calls.get(dv["id"].lstrip("_"), 0)
        dv.decompose()
    body = soup.body                                     # every WordSection (annexes are in WordSection2 …)
    if ct == "GE":
        for p in body.find_all("p", class_=["NoLoi", "ligne"]):
            p.decompose()
        for p in body.find_all("p", class_="MsoNormal"):
            if squash(p.get_text(" ").replace("\xa0", " ")) == "Texte en vigueur":
                p.decompose()
    else:
        for p in body.find_all("p"):                    # the RSN number above the title
            if cls_of(p) in ("MsoNormal", "") and p.find_previous("p", class_=["xNom", "Nom"]) is None and NUMLINE.match(squash(p.get_text(" ").replace("\xa0", " "))):
                p.decompose()
    words = re.findall(r"[0-9A-Za-zÀ-ÿĀ-ž]+", body.get_text(" ").replace("\xa0", " "))
    for n in notes:
        words += re.findall(r"[0-9A-Za-zÀ-ÿĀ-ž]+", n)
    return words


MONTHS = {m: i + 1 for i, m in enumerate(["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                                          "septembre", "octobre", "novembre", "décembre"])}


def fr_date(s: str) -> str:
    m = re.search(r"(\d{1,2})\s*(?:er)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})", s.replace("\xa0", " "), re.I)
    return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}" if m else ""


def version_date(html_bytes: bytes, ct: str, today: str) -> str:
    """The day the text on the page took effect. GE: the latest entry into force in the change table up to today (else
    the act's own); NE: "État au …" (else the adoption date, left to the caller)."""
    soup = BeautifulSoup(decode(html_bytes), "lxml")
    if ct == "GE":
        ds = []
        for p in soup.find_all("p", class_="Tvigueur"):
            m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", p.get_text())
            if m:
                ds.append(f"{m.group(3)}-{m.group(2)}-{m.group(1)}")
        ds = [x for x in ds if x <= today]
        if ds:
            return max(ds)
        p = soup.find("p", class_="vigueur")
        return fr_date(p.get_text(" ")) if p else ""
    p = soup.find("p", class_="xEdition")
    if p is None:                                        # older pages: "Etat au 24 mai 2006" in the header table
        p = next((q for q in soup.find_all("p")[:80] if re.match(r"\s*[ÉE]tat au", q.get_text(" ").replace("\xa0", " "))), None)
    return fr_date(p.get_text(" ")) if p else ""
