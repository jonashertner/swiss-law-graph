"""BLV (Vaud) version, Akoma-Ntoso-flavoured XHTML → Markdown, in the format of akn2md.py (decision 36).

The BLV renders an act as div.akn-preface (docType, docNumber, docTitle, docAbreviation, docDate), div.akn-autorite,
div.akn-preamble, div.akn-formula, then in document order *-container tables (part, title, chapter, section,
subsection: num + heading), article containers (num + heading) followed by div.collapse with the alineas
(sup.akn-sup-num + p), lists (table.akn-list > tr.akn-point: td.akn-num + td.akn-pointContent), notes
(a.akn-commentaire [A] → div.akn-commentaires > div#id), change notes (div.akn-modification, the amending acts in
div.akn-modifiants-container) and annexes (a.akn-annex). Notes and change notes become footnotes of their article.
"""
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from akn2md import esc, line_safe, squash, yval

LEVELS = ["part", "title", "chapter", "section", "subsection"]


def has(el, cls):
    return isinstance(el, Tag) and cls in (el.get("class") or [])


class VD:
    def __init__(self, soup):
        self.lines, self.pending, self.count, self.scope = [], [], {}, "t"
        self.notes = {d.get("id"): d for c in soup.find_all(class_="akn-commentaires") for d in c.find_all("div", id=True)}
        self.mods = {m.get("unique"): m for m in soup.find_all(class_="akn-modifiants-container")}
        present = [lv for lv in LEVELS if soup.find(class_=f"akn-{lv}-container")]
        self.top = present[0] if present else None

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
            return esc(str(el))
        if not isinstance(el, Tag) or el.name in ("script", "style"):
            return ""
        if has(el, "akn-commentaire"):
            d = self.notes.get(el.get("identify"))
            return self.note(self.children(d)) if d is not None else ""
        if has(el, "akn-modifiant-number"):                 # "[3, 5, 8]": the element's amendments, as one note
            m = self.mods.get(el.get("modcontainer"))
            return self.note(self.history(m)) if m is not None else ""
        if has(el, "akn-modifiants-container") or has(el, "popper") or has(el, "akn-collapsible-icon"):
            return ""
        if el.name == "a" and has(el, "akn-commentaire-link"):
            m = re.search(r"window\.open\('([^']+)'\)", el.get("onclick") or "")
            t = squash(self.children(el))
            return f"[{t}]({m.group(1)})" if m and t and m.group(1).startswith("http") else t
        if el.name == "br":
            return " "
        inner = self.children(el)
        core = inner.strip()
        lead, trail = inner[:len(inner) - len(inner.lstrip())], inner[len(inner.rstrip()):]
        mark = {"strong": ("**", "**"), "b": ("**", "**"), "em": ("*", "*"), "i": ("*", "*"),
                "sup": ("<sup>", "</sup>"), "sub": ("<sub>", "</sub>")}.get(el.name)
        if mark and core:
            if el.name == "sup" and core.startswith("[^"):
                return inner                                  # a note's marker is already a footnote
            return f"{lead}{mark[0]}{core}{mark[1]}{trail}"
        if el.name == "a" and (el.get("href") or "").startswith("http") and core:
            return f"{lead}[{core}]({el['href']}){trail}"
        if el.name in ("p", "div", "td", "tr", "li", "table"):
            return " " + inner + " "
        return inner

    def children(self, el) -> str:
        if el is None:
            return ""
        return re.sub(r"[ \t\r\n]+", " ", "".join(self.inline(c) for c in el.children))

    def history(self, m) -> str:
        rows = []
        for tr in m.find_all("tr", attrs={"modnum": True}):
            a = tr.find(class_="akn-modification-modif")
            det = [squash(self.children(x)) for x in tr.find_all(class_="akn-modification")]
            rows.append(squash(f"{squash(self.children(a)) if a else ''}: {'; '.join(x for x in det if x)}"))
        return " · ".join(r for r in rows if r)

    def lines_note(self, txt):
        mark = self.note(txt)
        if self.lines and self.lines[-1].startswith("#### "):
            self.lines[-1] += mark                           # a change of the article as a whole
        elif self.lines and self.lines[-1]:
            self.lines[-1] += mark
        else:
            self.para(mark)

    def heading_of(self, table):
        num = table.find(class_="akn-num")
        head = table.find(class_="akn-heading")
        sub = table.find(class_="akn-subheading")
        return squash(self.children(num)), squash(self.children(head)), squash(self.children(sub))

    def walk(self, el):
        for c in el.children:
            if isinstance(c, NavigableString):
                if c.strip():
                    self.para(esc(str(c)))
                continue
            if not isinstance(c, Tag) or c.name in ("script", "style"):
                continue
            cls = c.get("class") or []
            if any(x in cls for x in ("popper", "akn-commentaires", "akn-modifiants-container", "akn-separator", "akn-collapsible-icon")):
                continue
            lv = next((lv for lv in LEVELS if f"akn-{lv}-container" in cls), None)
            if lv:
                t = c.find("table")
                num, head, sub = self.heading_of(t) if t is not None else ("", "", "")
                self.flush()
                self.scope = re.sub(r"\W", "", f"{lv}{num}") or lv
                self.blank()
                self.lines.append(("##" if lv == self.top else "###") + " " + squash(f"{num} {head}"))
                if sub:
                    self.lines += ["", f"**{sub}**"]
                self.flush()
                continue
            if "akn-article-container" in cls:
                self.flush()
                t = c.find("table")
                num, head, sub = self.heading_of(t) if t is not None else ("", "", "")
                self.scope = re.sub(r"[^\w]", "", num.replace("Art.", "").replace("Article", "")) or "a"
                self.blank()
                self.lines.append("#### " + num if num else "")
                if head:
                    self.lines += ["", f"**{head}**"]
                if sub:
                    self.lines += ["", f"*{sub}*"]
                continue
            if "akn-alinea" in cls:
                n = c.find("sup", class_="akn-sup-num")
                nt = squash(n.get_text()) if n else ""
                if n:
                    n.extract()
                first = True
                for part in c.children:
                    if isinstance(part, Tag) and part.name == "table" and has(part, "akn-list"):
                        self.list(part, 0)
                        continue
                    if isinstance(part, Tag) and has(part, "akn-modification"):
                        self.lines_note(self.children(part))
                        continue
                    s = squash(self.inline(part))
                    if not s:
                        continue
                    self.para(f"<sup>{nt}</sup> {s}" if first and nt else s)
                    first = False
                if first and nt:
                    self.para(f"<sup>{nt}</sup>")
                continue
            if c.name == "table" and "akn-list" in cls:
                self.list(c, 0)
                continue
            if "akn-modification" in cls:
                self.lines_note(self.children(c))
                continue
            if c.name == "a" and "akn-annex" in cls:
                m = re.search(r"window\.open\('([^']+)'\)", c.get("onclick") or "") or None
                t = squash(self.children(c))
                self.para(f"[{t}]({m.group(1)})" if m and t and m.group(1).startswith("http") else t)
                continue
            if c.name in ("p",) or "akn-preamble-element" in cls or "akn-subheading" in cls:
                self.para(self.children(c))
                continue
            self.walk(c)

    def list(self, table, depth):
        pad = "  " * depth
        self.blank()
        for tr in table.find_all("tr", class_="akn-point", recursive=True):
            if tr.find_parent("table", class_="akn-list") is not table:
                continue
            num = tr.find("td", class_="akn-num")
            content = tr.find("td", class_="akn-pointContent")
            nested = [t for t in (content.find_all("table", class_="akn-list") if content else []) if t.find_parent("td", class_="akn-pointContent") is content]
            for t in nested:
                t.extract()
            n_ = squash(self.children(num)) if num else ""
            txt = squash(self.children(content)) if content else ""
            self.lines.append(pad + "- " + squash(f"{re.sub(r'^(\d+)\.', r'\1\\.', n_)} {txt}"))
            for t in nested:
                self.list(t, depth + 1)
        self.blank()


def convert(html_text: str, front: dict, notice: str) -> str:
    soup = BeautifulSoup(html_text, "lxml")
    for x in soup(["script", "style"]):
        x.decompose()
    root = soup.find("akomantoso") or soup.body
    d = VD(soup)
    pre = root.find(class_="akn-preface")
    title = squash(d.children(pre.find(class_="akn-docTitle"))) if pre else ""
    dtype = squash(d.children(pre.find(class_="akn-docType"))) if pre else ""
    d.lines.append("# " + squash(f"{dtype} {title}" if dtype and not title.upper().startswith(dtype.upper()) else title or front.get("title", "")))
    if pre:
        for cls in ("akn-docAbreviation", "akn-docDate"):
            x = pre.find(class_=cls)
            if x is not None:
                d.para(d.children(x))
        pre.extract()
    d.scope = "ingress"
    for cls in ("akn-autorite", "akn-preamble", "akn-formula"):
        x = root.find(class_=cls)
        if x is not None:
            for p in (x.find_all("p") or [x]):
                d.para(d.children(p))
            x.extract()
    d.flush()
    d.scope = "t"
    d.walk(root)
    d.flush()
    yaml = ["---"] + [f"{k}: {yval(v)}" for k, v in front.items() if v not in (None, "", [])] + ["---", "", f"> {notice}", ""]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(x for x in d.lines if x is not None)).strip() + "\n"
    return "\n".join(yaml) + "\n" + body


def text_tokens(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text, "lxml")
    for x in soup(["script", "style"]):
        x.decompose()
    root = soup.find("akomantoso") or soup.body
    for x in root.find_all(class_=["popper", "akn-collapsible-icon", "akn-docNumber", "akn-modifiants-title", "akn-popover-close",
                                   "akn-modifiant-number"]):
        x.decompose()
    refs = {a.get("identify") for a in root.find_all("a", class_="akn-commentaire")}
    for c in root.find_all(class_="akn-commentaires"):          # notes no element of this version points to
        for d in c.find_all("div", id=True):
            if d.get("id") not in refs:
                d.decompose()
    for a in root.find_all("a", class_="akn-commentaire"):
        a.decompose()
    notes = []
    for c in root.find_all(class_="akn-commentaires"):              # each note once (cited from several places)
        for d in c.find_all("div", id=True):
            notes.append(d.get_text(" "))
        c.decompose()
    for x in root.find_all(class_="akn-modifiants-container"):
        notes.append(x.get_text(" "))
        x.decompose()
    for x in root.find_all(["sup", "sub", "strong", "em", "b", "i", "span", "a"]):
        x.unwrap()
    root = BeautifulSoup(str(root), "lxml")
    words = re.findall(r"[0-9A-Za-zÀ-ÿĀ-ž]+", root.get_text(" "))
    for n in dict.fromkeys(re.sub(r"\s+", " ", x).strip() for x in notes):
        words += re.findall(r"[0-9A-Za-zÀ-ÿĀ-ž]+", n)
    return words


def md_tokens(md: str) -> list[str]:
    """The Markdown's words with each distinct footnote text once (the counterpart of text_tokens)."""
    import akn2md
    defs = re.findall(r"^\[\^[^\]]+\]: (.*)$", md, re.M)
    body = re.sub(r"^\[\^[^\]]+\]: .*$", "", md, flags=re.M)
    words = akn2md.text_tokens_md(body)
    for d in dict.fromkeys(defs):
        words += akn2md.text_tokens_md("---\n---\n" + d)
    return words
