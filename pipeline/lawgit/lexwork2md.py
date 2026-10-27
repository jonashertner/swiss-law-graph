"""LexWork version (JSON tree of HTML fragments) → Markdown, in the format of akn2md.py (decision 36).

Titles `##`/`###` (their number says the depth), articles `#### § 1` / `#### Art. 1` with the Sachüberschrift in bold
on the next line, paragraphs `<sup>1</sup> …`, enumerations `- a) …` (nested by two spaces), tables as HTML,
footnotes labelled by the article (`[^12-1]`) and defined after it, links kept. LexWork's change marker (a bold
"*" after a number, which links to the change table on the portal) is dropped: it is not part of the text; so are the
outline numbers SG and AR print greyed before a title ("(1.1)", class number_discrete). Footnotes the portal lists
but no element of the version calls (old change notes, mostly BS) follow at the end ("Weitere Fussnoten").
"""
import html
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from akn2md import esc, line_safe, squash, yval


def soup(h: str):
    return BeautifulSoup(h or "", "lxml")


class Lex:
    def __init__(self, lang: str, footnotes_html: str):
        self.lang = lang
        self.notes, self.order, self.used = {}, [], set()
        fs = soup(footnotes_html)
        for li in fs.find_all("li"):
            a = li.find("a", class_="footnote")
            txt = li.find(class_="footnote_text")
            if a and a.get("id"):
                self.notes[a["id"]] = txt if txt is not None else li
                self.order.append((a["id"], squash(a.get_text()).strip("[]")))
        self.lines: list[str] = []
        self.scope = "t"
        self.count: dict[str, int] = {}
        self.pending: list[tuple[str, str]] = []

    def inline(self, el) -> str:
        if isinstance(el, NavigableString):
            return esc(str(el))
        if not isinstance(el, Tag):
            return ""
        name, cls = el.name, " ".join(el.get("class") or [])
        if name == "a" and "footnote" in cls:
            href = (el.get("href") or "").lstrip("#")
            note = self.notes.get(href)
            if note is None:
                return ""
            self.used.add(href)
            k = self.count.get(self.scope, 0) + 1
            self.count[self.scope] = k
            lab = f"{self.scope}-{k}"
            self.pending.append((lab, squash(self.children(note))))
            return f"[^{lab}]"
        if name == "strong" and squash(el.get_text()) == "*":
            return ""                                       # LexWork's change marker
        if name == "br":
            return " "
        inner = self.children(el)
        core = inner.strip()
        lead, trail = inner[:len(inner) - len(inner.lstrip())], inner[len(inner.rstrip()):]
        mark = {"strong": ("**", "**"), "b": ("**", "**"), "em": ("*", "*"), "i": ("*", "*"),
                "sup": ("<sup>", "</sup>"), "sub": ("<sub>", "</sub>")}.get(name)
        if mark:
            return f"{lead}{mark[0]}{core}{mark[1]}{trail}" if core else inner
        if name == "a" and el.get("href", "").startswith("http") and core:
            return f"{lead}[{core}]({el['href']}){trail}"
        if name in ("p", "div", "li", "td", "th", "tr"):
            return " " + inner + " "
        return inner

    def children(self, el) -> str:
        return re.sub(r"[ \t\r\n]+", " ", "".join(self.inline(c) for c in el.children))

    def blank(self):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def flush(self):
        if self.pending:
            self.blank()
            for lab, body in self.pending:
                self.lines.append(f"[^{lab}]: {body}")
            self.pending = []

    def para(self, s: str):
        s = squash(s)
        if s:
            self.blank()
            self.lines.append(line_safe(s))

    def node(self, n: dict, depth: int, enum: int = 0):
        t = n.get("type")
        h = (n.get("html_content") or {}).get(self.lang) or ""
        s = soup(h)
        if t == "title":
            num = s.find(class_="number")
            tt = s.find(class_="title_text")
            title = squash(f"{self.children(num) if num else ''} {self.children(tt) if tt else ''}")
            if title:
                self.blank()
                self.lines.append(("##" if depth <= 1 else "###") + " " + title)
                self.flush()
            for c in n.get("children") or []:
                self.node(c, depth + 1)
        elif t == "article":
            num = s.find(class_="article_number")
            sym = num.find(class_="article_symbol") if num else None
            nn = num.find(class_="number") if num else None
            raw = squash(f"{sym.get_text('') if sym else ''} {nn.get_text('') if nn else (num.get_text('') if num else '')}")
            raw = squash(re.sub(r"\*", "", raw))
            self.scope = re.sub(r"[^\w]", "", raw.replace("Art.", "").replace("§", "").replace("Article", "").replace("Articolo", "")) or "a"
            tt = s.find(class_="article_title")
            self.blank()
            self.lines.append("#### " + squash(html.unescape(raw)))
            head = squash(self.children(tt)) if tt else ""
            if head:
                self.lines.append("")
                self.lines.append(f"**{head}**")
            for c in n.get("children") or []:
                self.node(c, depth + 1)
            self.flush()
        elif t == "paragraph":
            num = s.find(class_="number")
            n_ = squash(self.children(num)) if num else ""
            if num:
                num.decompose()
            ps = s.find_all("p") or [s]
            lines = [squash(self.children(p)) for p in ps]
            lines = [x for x in lines if x]
            if not lines:
                if n_:
                    self.para(f"<sup>{n_}</sup>")
            for k, txt in enumerate(lines):                 # a paragraph of several sentences on lines of their own
                self.para(f"<sup>{n_}</sup> {txt}" if k == 0 and n_ else txt)
            for c in n.get("children") or []:
                self.node(c, depth + 1, enum)
        elif t == "enumeration":
            nums = [squash(self.children(td)) for td in s.find_all("td", class_="number")]
            n_ = next((x for x in reversed(nums) if x), "")               # nested items: the number is in a later cell
            left = [td for td in s.find_all("td") if "left_col" in " ".join(td.get("class") or [])]
            right = [td for td in s.find_all("td") if "right_col" in " ".join(td.get("class") or []) and squash(td.get_text())]
            txt = squash(" ".join(self.children(td) for td in left))
            if right:                                                       # a tariff's value column
                txt = squash(txt + " — " + " ".join(self.children(td) for td in right))
            if self.lines and self.lines[-1] != "" and not self.lines[-1].lstrip().startswith("- "):
                self.blank()
            item = squash(f"{re.sub(r'^(\d+)\.', r'\1\\.', n_)} {txt}")
            self.lines.append("  " * enum + "- " + item)
            for c in n.get("children") or []:
                self.node(c, depth + 1, enum + 1)
        elif t == "table":
            self.table(s)
            for c in n.get("children") or []:
                self.node(c, depth + 1)
        else:
            txt = squash(self.children(s))
            if txt:
                self.para(txt)
            for c in n.get("children") or []:
                self.node(c, depth + 1, enum)

    def table(self, s):
        rows = []
        for tr in s.find_all("tr"):
            cells = []
            for c in tr.find_all(["td", "th"]):
                attrs = "".join(f' {a}="{c.get(a)}"' for a in ("colspan", "rowspan") if c.get(a))
                cells.append(f"<{c.name}{attrs}>{squash(self.children(c))}</{c.name}>")
            if any(re.sub(r"<[^>]+>", "", x).strip() for x in cells):
                rows.append("<tr>" + "".join(cells) + "</tr>")
        if rows:
            self.blank()
            self.lines += ["<table>", *rows, "</table>"]
            self.blank()


def convert(version: dict, lang: str, front: dict, notice: str) -> str | None:
    jc = version.get("json_content") or {}
    doc = jc.get("document") or {}
    if not doc.get("content"):
        return None
    L = Lex(lang, (jc.get("footnotes") or {}).get(lang, ""))
    hs = soup((doc.get("header") or {}).get(lang, ""))
    top = hs.body.find_all(recursive=False) if hs.body else []
    title = hs.find(class_="title")
    L.lines.append("# " + (squash(L.children(title)) if title else (front.get("title") or "")))
    L.scope = "ingress"
    for x in top:                                        # every header element in order: abbreviation, dates, notes, Ingress
        cls = " ".join(x.get("class") or [])
        if "systematic_number" in cls or x is title:
            continue
        for p in (x.find_all("p") or [x]):
            L.para(L.children(p))
    L.flush()
    L.scope = "t"
    L.node(doc["content"], 0)
    L.flush()
    fs = soup((doc.get("footer") or {}).get(lang, "") if isinstance(doc.get("footer"), dict) else "")
    if squash(fs.get_text()):
        L.scope = "footer"
        for p in fs.find_all(["p", "div"]) or [fs]:
            if p.find(["p", "div"]):
                continue
            L.para(L.children(p))
        L.flush()
    rest = [(i, n) for i, n in L.order if i not in L.used]
    if rest:                                             # notes the portal lists but no element of this version calls
        L.blank()
        L.lines += ["## " + {"fr": "Autres notes", "it": "Altre note"}.get(lang, "Weitere Fussnoten"), ""]
        L.lines += [f"- [{n}] {squash(L.children(L.notes[i]))}" for i, n in rest]
    yaml = ["---"] + [f"{k}: {yval(v)}" for k, v in front.items() if v not in (None, "", [])] + ["---", "", f"> {notice}", ""]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(L.lines)).strip() + "\n"
    return "\n".join(yaml) + "\n" + body


def text_tokens_json(version: dict, lang: str) -> list[str]:
    """Words of a version's text (header, nodes, footnotes, footer) for the check, the change marker left out."""
    jc = version.get("json_content") or {}
    doc = jc.get("document") or {}
    parts = [(doc.get("header") or {}).get(lang, ""), (jc.get("footnotes") or {}).get(lang, "")]
    if isinstance(doc.get("footer"), dict):
        parts.append(doc["footer"].get(lang, ""))

    def walk(n):
        parts.append((n.get("html_content") or {}).get(lang, ""))
        for c in n.get("children") or []:
            walk(c)
    if doc.get("content"):
        walk(doc["content"])
    words = []
    for h in parts:
        s = soup(h)
        for x in s.find_all("h1", class_="systematic_number"):
            x.decompose()
        for x in s.find_all(class_="number_discrete"):        # SG/AR outline numbers "(1.1)", shown greyed: editorial
            x.decompose()
        for x in s.find_all("strong"):
            if squash(x.get_text()) == "*":
                x.decompose()
        for a in s.find_all("a", class_="footnote"):
            a.decompose()
        for x in s.find_all(["sup", "sub", "strong", "em", "b", "i", "span", "a"]):
            x.unwrap()                                       # inline: no gap, as in the Markdown
        s = soup(str(s))
        words += re.findall(r"[0-9A-Za-zÀ-ÿĀ-ž]+", s.get_text(" "))
    return words
