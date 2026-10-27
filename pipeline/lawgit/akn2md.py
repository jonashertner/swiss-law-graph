"""Fedlex consolidated XML (Akoma Ntoso 3.0) → Markdown, one file per act, version and language (decision 36).

Made for line diffs and `git blame`:
- the title as `#`, containers (Teil, Titel, Kapitel, Abschnitt, Randtitel A./I./1.) as `##` (top level) and `###`
  (deeper; their number says the depth), every article as `#### Art. 41`, so GitHub's anchors are stable (`#art-41`);
  an article's own heading (Sachüberschrift) on the line after, in bold;
- one line per paragraph (`<sup>1</sup> Wer einem andern …`), list items as `- a. …` (nested by two spaces);
- footnotes as Markdown footnotes labelled by the article (`[^41-1]`), defined right after it, so an amendment only
  renumbers the notes of the article it touches;
- tables as HTML (Fedlex tables have merged cells), links kept, bold/italic/sup/sub kept.
Nothing is reworded. `text_tokens()` gives the words of the XML and of the Markdown so a run can check that every
word arrived (`check()`).
"""
import html
import re
import xml.etree.ElementTree as ET

CONTAINERS = {"book", "part", "title", "subtitle", "chapter", "subchapter", "section", "subsection", "level",
              "subdivision", "division", "transitional", "proviso", "container", "hcontainer", "clause", "tome",
              "subpart", "point"}
INLINE = {"b", "i", "u", "sup", "sub", "span", "inline", "ref", "s", "abbr", "term", "date", "docNumber", "foreign",
          "docTitle", "docType", "docDate", "docProponent", "docStatus", "signature", "person", "role",
          "organization", "location", "entity", "placeholder", "mref", "rref", "def", "quantity", "img", "br",
          "authorialNote", "noteRef", "marker", "a", "mmlMath", "math"}


def local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def squash(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def esc(s: str) -> str:
    """Markdown-escape running text (not line starts: those are handled where lines are made)."""
    s = s.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    return s


def line_safe(s: str) -> str:
    """A line that Markdown would read as a heading, list, quote or rule is escaped at its start."""
    if re.match(r"^(#|>|[-+*]\s|\d+[.)]\s|={3,}|-{3,}|\|)", s):
        return "\\" + s
    return s


def math_text(el) -> str:
    """MathML as one line of text: E = (V_2 − V_1)/(V_1); sub/superscripts with _ and ^, fractions in brackets."""
    t = local(el.tag)
    kids = [c for c in el]
    if t in ("mi", "mn", "mo", "mtext", "ms"):
        return (el.text or "").strip()
    if t == "mfrac" and len(kids) == 2:
        return f"({math_text(kids[0])})/({math_text(kids[1])})"
    if t in ("msub", "msup") and len(kids) == 2:
        return math_text(kids[0]) + ("_" if t == "msub" else "^") + math_text(kids[1])
    if t == "msubsup" and len(kids) == 3:
        return f"{math_text(kids[0])}_{math_text(kids[1])}^{math_text(kids[2])}"
    if t in ("msqrt",):
        return "√(" + " ".join(math_text(c) for c in kids) + ")"
    parts = [math_text(c) for c in kids]
    return " ".join(x for x in parts if x)


def label_of(eid: str) -> str:
    """Footnote label scope from an eId: art_40_g → 40g, disp_u1/art_1 → u1-1, part_1/tit_1/chap_2 → part1-tit1-chap2."""
    if not eid:
        return "x"
    parts = []
    for seg in eid.split("/"):
        m = re.fullmatch(r"art_(\w+)", seg)
        if m:
            parts.append(m.group(1).replace("_", ""))
        else:
            parts.append(seg.replace("disp_", "").replace("_", ""))
    return "-".join(p for p in parts if p) or "x"


class Doc:
    def __init__(self, base: str = ""):
        self.base = base                       # the XML's URL: images are relative to it
        self.lines: list[str] = []
        self.scope = "t"
        self.count: dict[str, int] = {}
        self.pending: list[tuple[str, str]] = []

    # ---- footnotes
    def note(self, el) -> str:
        k = self.count.get(self.scope, 0) + 1
        self.count[self.scope] = k
        lab = f"{self.scope}-{k}"
        body = self.inline_children(el)            # every part of the note (a note can hold a table), on one line
        self.pending.append((lab, squash(body)))
        return f"[^{lab}]"

    def flush_notes(self):
        if self.pending:
            self.blank()
            for lab, body in self.pending:
                self.lines.append(f"[^{lab}]: {body}")
            self.pending = []

    # ---- inline text
    def inline(self, el) -> str:
        t = local(el.tag)
        if t == "authorialNote":
            return self.note(el)
        if t == "br":
            return " "
        inner = self.inline_children(el)
        core = inner.strip()
        lead, trail = inner[:len(inner) - len(inner.lstrip())], inner[len(inner.rstrip()):]
        mark = {"b": ("**", "**"), "i": ("*", "*"), "sup": ("<sup>", "</sup>"), "sub": ("<sub>", "</sub>")}.get(t)
        if mark:
            return f"{lead}{mark[0]}{core}{mark[1]}{trail}" if core else inner
        if t == "ref":
            href = el.get("href") or ""
            txt = squash(inner.replace("**", ""))          # "RO <b>2025 7</b>63": Fedlex's bold is not always the year
            if href.startswith("http") and txt:
                return f"[{txt}]({href})"
            return inner
        if t in ("foreign", "math", "mmlMath"):
            m = math_text(el)
            return f" {esc(m)} " if m else ""
        if t == "img":
            src = el.get("src") or ""
            if src and not src.startswith("http") and self.base:
                src = self.base.rsplit("/", 1)[0] + "/" + src.lstrip("./")
            return f"![{esc(el.get('alt') or '')}]({src})" if src else ""
        return inner

    def inline_children(self, el) -> str:
        out = [esc(el.text or "")]
        for ch in el:
            t = local(ch.tag)
            if t not in INLINE:                                 # block inside inline context: its words stand apart
                out.append(" " + self.inline_children(ch) + " ")
            else:
                out.append(self.inline(ch))
            out.append(esc(ch.tail or ""))
        return re.sub(r"[ \t\r\n]+", " ", "".join(out))

    # ---- blocks
    def blank(self):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def para(self, s: str, prefix: str = ""):
        s = squash(s)
        if not s:
            return
        self.blank()
        self.lines.append(prefix + line_safe(s) if not prefix else prefix + s)

    def num_text(self, el) -> str:
        for ch in el:
            if local(ch.tag) == "num":
                return self.inline_children(ch)
        return ""

    def heading_text(self, el) -> str:
        """Every heading of the element: the AS writes an empty one before the real one ("<heading/><heading>Übergangs-
        bestimmung</heading>")."""
        return " ".join(h for h in (self.inline_children(ch) for ch in el if local(ch.tag) == "heading") if h.strip())

    def container(self, el, depth: int):
        eid = el.get("eId") or ""
        old = self.scope
        self.scope = label_of(eid) if eid else self.scope
        num, head = squash(self.num_text(el)), squash(self.heading_text(el))
        title = squash(f"{num} {head}") if num or head else ""
        if title:
            self.blank()
            self.lines.append(("##" if depth <= 0 else "###") + " " + title)
            self.flush_notes()
        if el.text and el.text.strip():
            self.para(esc(el.text))
        for ch in el:
            t = local(ch.tag)
            if t not in ("num", "heading"):
                self.block(ch, depth + 1)
            if ch.tail and ch.tail.strip():                 # text between the parts ("… zu ermitteln; hierbei bedeuten")
                self.para(esc(ch.tail))
        self.flush_notes()
        self.scope = old

    def article(self, el):
        eid = el.get("eId") or ""
        old = self.scope
        self.scope = label_of(eid)
        num = squash(re.sub(r"\*\*|(?<!\\)\*", "", self.num_text(el)))
        head = squash(self.heading_text(el))
        self.blank()
        if num and getattr(self, "in_mod", False):        # an article quoted in an amending act: no heading of its own
            self.lines.append(f"**{num}**")
        elif num:                                        # an article without a number gets no heading of its own
            self.lines.append("#### " + num)
        if head:
            self.lines.append("")
            self.lines.append(f"**{head}**")
        for ch in el:
            t = local(ch.tag)
            if t in ("num", "heading"):
                continue
            self.block(ch, 9)
        self.flush_notes()
        self.scope = old

    def paragraph(self, el, depth):
        num = squash(self.num_text(el))
        parts = []
        rest = []
        for ch in el:
            t = local(ch.tag)
            if t == "num":
                continue
            if t == "content":
                for c in ch:
                    if local(c.tag) == "p":
                        parts.append(self.inline_children(c))
                    else:
                        rest.append(c)
                if ch.text and ch.text.strip():
                    parts.insert(0, esc(ch.text))
            else:
                rest.append(ch)
        first = True
        for p in parts:
            s = squash(p)
            if not s:
                continue
            if first and num:
                self.para(f"<sup>{num}</sup> {s}")
            else:
                self.para(s)
            first = False
        if first and num and not rest:
            self.para(f"<sup>{num}</sup>")
        for ch in rest:
            self.block(ch, depth, lead=f"<sup>{num}</sup> " if first and num else "")
            first = False

    def blocklist(self, el, indent: int):
        pad = "  " * indent
        for ch in el:
            t = local(ch.tag)
            if t == "listIntroduction":
                s = squash(self.inline_children(ch))
                if s:
                    self.para(s, pad if indent else "")
            elif t == "item":
                num = squash(self.num_text(ch))
                texts, subs = [], []
                for c in ch:
                    ct = local(c.tag)
                    if ct == "num":
                        continue
                    if ct in ("blockList", "list"):
                        subs.append(c)
                    elif ct == "p":
                        texts.append(self.inline_children(c))
                    elif ct == "content":
                        for cc in c:
                            (subs if local(cc.tag) in ("blockList", "list") else texts).append(
                                cc if local(cc.tag) in ("blockList", "list") else self.inline_children(cc))
                    else:
                        texts.append(self.inline_children(c))
                body = squash(" ".join(texts))
                numtxt = re.sub(r"^(\d+)\.", r"\1\\.", num)
                if self.lines and self.lines[-1] != "" and not self.lines[-1].lstrip().startswith("- "):
                    self.blank()
                self.lines.append(f"{pad}- " + squash(f"{numtxt} {body}") if (num or body) else f"{pad}-")
                for s in subs:
                    self.blocklist(s, indent + 1)
            elif t == "listWrapUp":
                self.para(self.inline_children(ch), pad)
            else:
                self.block(ch, 9)
        self.blank()

    def table(self, el):
        def cell(c):
            txt = squash(self.inline_children(c))
            attrs = "".join(f' {a}="{c.get(a)}"' for a in ("colspan", "rowspan") if c.get(a))
            tag = "th" if local(c.tag) == "th" else "td"
            return f"<{tag}{attrs}>{txt}</{tag}>"
        def own_rows(t):                                  # this table's rows, not those of a table inside a cell
            for c in t:
                if local(c.tag) == "tr":
                    yield c
                elif local(c.tag) in ("thead", "tbody", "tfoot"):
                    yield from own_rows(c)
        rows = []
        for tr in own_rows(el):
            if True:
                cells = [cell(c) for c in tr if local(c.tag) in ("td", "th")]
                if any(re.sub(r"<[^>]+>", "", x).strip() for x in cells):
                    rows.append("<tr>" + "".join(cells) + "</tr>")
        if rows:
            self.blank()
            self.lines.append("<table>")
            self.lines += rows
            self.lines.append("</table>")
            self.blank()

    def mod_p(self, el):
        """A paragraph holding amendments (<mod>): the text around them, each amended element's designation in bold,
        then the new text as quoted (quotedStructure: blocks; quotedText: inline)."""
        pre = [esc(el.text or "")]
        for ch in el:
            if local(ch.tag) != "mod":
                pre.append(self.inline(ch) if local(ch.tag) in INLINE or local(ch.tag) == "authorialNote"
                           else " " + self.inline_children(ch) + " ")
                pre.append(esc(ch.tail or ""))
                continue
            if squash("".join(pre)):
                self.para(squash("".join(pre)))
            pre = []
            ref, rest = [], []
            for c in ch:
                if local(c.tag) == "ref" and (c.get("{http://www.fedlex.admin.ch/eli/fedlex}role") or c.get("role") or "") \
                        .endswith("modification-reference") or (local(c.tag) == "ref" and not ref and not rest):
                    ref.append(self.inline_children(c))
                else:
                    rest.append(c)
            lead = esc(ch.text or "")
            head = squash(lead + " ".join(ref))
            if head:
                self.para(f"**{head}**")
            old = getattr(self, "in_mod", False)
            self.in_mod = True
            for c in rest:
                if local(c.tag) == "quotedStructure":
                    for q in c:
                        self.block(q, 9)
                    if c.text and c.text.strip():
                        self.para(esc(c.text))
                elif local(c.tag) == "quotedText":
                    self.para(self.inline_children(c))
                else:
                    self.para(self.inline(c) if local(c.tag) in INLINE else self.inline_children(c))
                if c.tail and c.tail.strip():
                    self.para(esc(c.tail))
            self.in_mod = old
            pre.append(esc(ch.tail or ""))
        if squash("".join(pre)):
            self.para(squash("".join(pre)))

    def block(self, el, depth: int, lead: str = ""):
        t = local(el.tag)
        if t in CONTAINERS:
            self.container(el, depth)
        elif t == "article":
            self.article(el)
        elif t in ("paragraph", "subparagraph"):
            self.paragraph(el, depth)
        elif t in ("blockList", "list"):
            if lead:
                self.para(lead.strip())
            self.blocklist(el, 0)
        elif t == "table":
            self.table(el)
        elif t == "foreign":
            self.para(self.inline(el))
        elif t in ("body", "content", "intro", "wrapUp", "alinea", "block", "blockContainer", "mainBody",
                   "components", "component", "doc", "attachments", "attachment", "conclusions", "formula", "coverPage"):
            if t in ("doc", "attachment", "component"):
                self.blank()
            for ch in el:
                self.block(ch, depth)
            if el.text and el.text.strip():
                self.para(esc(el.text))
            self.flush_notes() if t in ("doc", "attachment", "component") else None
        elif t == "p" and any(local(c.tag) == "mod" for c in el):
            self.mod_p(el)                               # an amending act: "Art. 6 Abs. 5bis" + the new text
        elif t in ("p", "heading", "num", "subheading", "crossHeading"):
            s = self.inline_children(el)
            if t in ("heading", "subheading", "crossHeading") and squash(s):
                self.blank()
                self.lines.append("### " + squash(s))
            else:
                self.para(lead + s if lead else s)
        elif t in ("meta", "references"):
            return
        elif t in INLINE:
            self.para(self.inline(el))
        else:
            s = self.inline_children(el)
            self.para(s)


def convert(xml: bytes, front: dict, notice: str) -> str:
    root = ET.fromstring(xml)
    act = next((e for e in root.iter() if local(e.tag) in ("act", "doc", "bill")), root)
    d = Doc(front.get("source") or "")
    title = ""
    preface = next((e for e in act if local(e.tag) == "preface"), None)
    for e in (preface.iter() if preface is not None else []):
        if local(e.tag) == "docTitle":
            title = squash(d.inline_children(e))
            break
    d.scope = "t"
    d.lines.append(f"# {title or front.get('title') or front.get('sr')}")
    if preface is not None:
        first = True
        for p in preface:
            if local(p.tag) != "p":
                continue
            if any(local(x.tag) in ("docTitle", "docNumber") for x in p.iter()):
                if not first:                            # a second title: the part of an amending act ("Vorlage B: …")
                    for x in p:
                        if local(x.tag) == "docTitle" and squash(d.inline_children(x)):
                            d.para(f"**{squash(d.inline_children(x))}**")
                first = first and not any(local(x.tag) == "docTitle" for x in p.iter())
                rest = "".join(esc(x.tail or "") for x in p if local(x.tag) in ("docTitle", "docNumber"))
                if squash(rest):
                    d.para(rest)
                continue
            d.para(d.inline_children(p))
    d.flush_notes()
    for part in act:
        t = local(part.tag)
        if t in ("meta", "preface"):
            continue
        if t == "preamble":
            d.scope = "ingress"
            for p in part:
                d.block(p, 1)
            d.flush_notes()
        else:
            d.scope = "t"
            d.block(part, 0)
            d.flush_notes()
    yaml = ["---"] + [f"{k}: {yval(v)}" for k, v in front.items() if v not in (None, "", [])] + ["---", "", f"> {notice}", ""]
    body = "\n".join(d.lines)
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    return "\n".join(yaml) + "\n" + body


def yval(v) -> str:
    if isinstance(v, (list, tuple)):                     # a YAML flow sequence, every item quoted
        return "[" + ", ".join('"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"' for x in v) + "]"
    s = str(v)
    if re.search(r"[:#\[\]{}&*!|>'\"%@`,]|^\s|\s$|^[-?]", s) or s in ("yes", "no", "true", "false", "null") or re.fullmatch(r"[\d.]+", s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


# ---- verification: every word of the XML's text arrives in the Markdown
def text_tokens_xml(xml: bytes) -> list[str]:
    root = ET.fromstring(xml)
    parts = []
    def walk(e):
        if local(e.tag) in ("meta", "docNumber", "RDF", "style"):   # metadata Fedlex puts beside the act; CSS of an SVG
            return
        sep = "" if local(e.tag) in INLINE - {"authorialNote", "br", "ref"} else " "
        parts.append(sep + (e.text or ""))
        for c in e:
            walk(c)
            parts.append(("" if local(c.tag) in INLINE - {"authorialNote", "br", "ref"} else " ") + (c.tail or ""))
    walk(root)
    return re.findall(r"[0-9A-Za-zÀ-ÿĀ-ž]+", html.unescape("".join(parts)))


def text_tokens_md(md: str) -> list[str]:
    body = md.split("\n---\n", 1)[1] if md.startswith("---") else md
    body = re.sub(r"^> .*$", "", body, count=1, flags=re.M)               # the notice
    body = re.sub(r"\[\^[^\]]+\]:?", " ", body)                            # footnote labels
    body = re.sub(r"\]\((?:https?://[^)]+)\)", "] ", body)                 # link targets
    body = re.sub(r"</?(?:table|tr|td|th)[^>]*>|<br\s*/?>", " ", body)
    body = re.sub(r"</?(?:sup|sub)>", "", body)                           # inline, as in the XML
    body = re.sub(r"(?<!\\)\*+", "", body)                               # emphasis marks
    body = html.unescape(body.replace("\\", ""))
    body = re.sub(r"^#+ ", " ", body, flags=re.M)
    return re.findall(r"[0-9A-Za-zÀ-ÿĀ-ž]+", body)


def check(xml: bytes, md: str) -> tuple[int, int, list[str]]:
    """(tokens in XML, tokens in Markdown, first missing tokens) — order-insensitive multiset comparison."""
    from collections import Counter
    a, b = Counter(text_tokens_xml(xml)), Counter(text_tokens_md(md))
    miss = list((a - b).elements())
    return sum(a.values()), sum(b.values()), miss[:20]
