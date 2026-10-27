"""A canton's PDF of a version → Markdown, in the format of akn2md.py (decision 36), for versions LexWork publishes only
as PDF. The PDFs are born digital (set by the collections' publishing systems), so the characters are exact; the
structure is read from the layout:

- body size S = the commonest character size; a character < 0.8 of its line's size and raised above the line's
  baseline is a superscript: at the start of a paragraph its number (<sup>2</sup>), elsewhere a footnote call when a
  footnote of that number exists ("¹", "1)", "1 )");
- page furniture: lines near the top or bottom edge that recur on the pages with their digits masked (collection
  name, SR number, "Stand …"), bare page numbers ("2", "- 2 -"), and the act's number on page 1; the block in smaller
  print at the bottom of a page that starts with a number is the page's footnotes;
- a line splits into segments at a gap wider than 1.8·S; a segment that lies left of the body's left edge (GR, AG, SH
  …) or right of the body's right edge (AI …) is a marginal note: it becomes the bold heading of the article it
  stands beside;
- a segment that starts with "Art. N", "Artikel N", "§ N", "Article N" in bold or italics starts an article; a segment
  in larger print, or bold throughout, is a title; a paragraph starts at a superscript number, a list marker ("a)",
  "1.", "–"), a gap of more than 1.45 line pitches, a centred line, or after a line that ends short;
- a word broken at the line end ("Zustän-" + "digkeit") is joined, unless the next word is a conjunction ("Straf- und")
  or starts with a capital ("Kantons-Spital" keeps its hyphen).

text_tokens() gives the words of everything that is not furniture (after the same joins), the counterpart of
akn2md.text_tokens_md: the check proves that the Markdown drops nothing the reading found. Files say `text: pdf`.
"""
import re
from collections import Counter

import pdfplumber

from akn2md import esc, line_safe, squash, yval

NUM = r"(?:\d+\s?[a-z]?(?:\s?(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies))?|premier|première|unique|primo|unico)"
ART = re.compile(rf"^((?:Art\.|Artikel|Article|Articolo|Art|§§?)\s*{NUM})(?![\w])\.?\s*(.*)$", re.S)
LISTM = re.compile(r"^(?:[a-z]{1,2}\)|[a-z]{1,2}\.(?=\s)|\d{1,2}\.(?=\s)|\d{1,2}\)(?=\s)|[ivx]+\)|[–\-•·](?=\s)|\d+°)")
ENACT = re.compile(r"(beschlie(?:ss|ß)t|verordnet|erl(?:ä|ae)sst|beschliessen|d(?:é|e)cr(?:è|e)te|arr(?:ê|e)te|d(?:é|e)cide|ordonne|"
                   r"decreta|risolve|ordina|delibera|decida|decreta|conclude|vereinbaren|schliessen)\s*:?\s*$", re.I)
DATE_START = re.compile(r"^\d{1,2}\.\s?(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember|"
                        r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|gennaio|"
                        r"febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\b")   # "2. April 1911"
HEAD = re.compile(r"^(?:\d+[a-z]?\.\s*(?:Kapitel|Abschnitt|Unterabschnitt|Titel|Teil|Buch)\b|(?:Kapitel|Abschnitt|Titel|Teil)\s+\d|"
                  r"(?:Chapitre|Section|Titre|Capitolo|Sezione|Titolo|Capo)\s+(?:\d|[IVXLC]+\b|premier|primo|unique))")
FOOT = re.compile(r"^\s*(?:\d{1,3}\s?\)|\*+\)?|\d{1,3}(?=\s*[^\d\s.,:/–-]))")       # "1)", "12 Text", "*" — not "12.06.2003"
TEMPLATE = re.compile(r"^(?:\s*(?:«\s*[$%][^»]*»|\d{1,4}\s*/\s*\d{1,4}|(?:AS|SR|BBl|RO|FF|RU)\s*…|\d{4}[-–]\.{3}))+\s*$")   # Fedlex template
STAMP = re.compile(r"^Powered by TCPDF \(www\.tcpdf\.org\)$")      # the PDF library's mark on the last page (VS)
CONJ = {"und", "oder", "bzw", "sowie", "resp", "et", "ou", "e", "o", "ed", "od", "u", "respektive", "beziehungsweise"}
WORD = re.compile(r"[0-9A-Za-zÀ-ÿĀ-ž]+")
BODY_FONT = ""


def bold(fn: str) -> bool:
    f = fn.split("+")[-1].lower()
    return any(k in f for k in ("bold", "black", "heavy", "semibold", "demi", "-bd", ",bd")) or f.endswith("bd")


def italic(fn: str) -> bool:
    f = fn.split("+")[-1].lower()
    return any(k in f for k in ("italic", "oblique", "-it", ",it", "kursiv"))


# ---------------------------------------------------------------- reading the layout
def read(path, number=""):
    """Pages → lines (furniture removed) → segments split by column: dict(page, top, bottom, x0, x1, size, bold, lead,
    marg, runs=[(text, sup)]). Returns (S, pages); a page holds "body" and "foot" lines."""
    with pdfplumber.open(path) as pdf:
        sizes, raw = Counter(), []
        for p in pdf.pages:
            cs = [c for c in p.chars if c.get("upright", True) and c["text"] not in ("\u00ad", "\x00")]
            raw.append((p.page_number, float(p.height), cs))
            for c in cs:
                if c["text"].strip():
                    sizes[round(c["size"], 1)] += 1
    S = sizes.most_common(1)[0][0] if sizes else 10.0
    fonts = Counter(c["fontname"] for _, _, cs in raw for c in cs if c["text"].strip() and abs(c["size"] - S) < 0.6)
    global BODY_FONT
    BODY_FONT = fonts.most_common(1)[0][0] if fonts else ""
    pages = [{"no": no, "h": h, "lines": cluster(cs, S)} for no, h, cs in raw]
    furniture(S, pages, number)
    cols = {}
    for pg in pages:                                    # the body column of each page (layouts mirror on odd pages)
        st, en = Counter(), Counter()
        for ln in pg["lines"]:
            body = [c for c in ln["cs"] if c["text"].strip() and abs(c["size"] - S) < 0.6]
            if len(body) >= 8:
                st[round(min(c["x0"] for c in body))] += 1
                en[round(max(c["x1"] for c in body))] += 1
        tot = sum(st.values())
        lefts = [x for x, k in st.items() if k >= max(3, 0.15 * tot)]   # the leftmost frequent start (lists indent the text)
        rights = [x for x, k in en.items() if k >= max(3, 0.15 * tot)]
        pg["col"] = (min(lefts), max(rights) if rights else en.most_common(1)[0][0]) if lefts else None
        if pg["col"]:
            cols.setdefault(pg["no"] % 2, []).append(pg["col"])
    nxt = 1
    for pg in pages:
        if pg["col"] is None:
            same = cols.get(pg["no"] % 2) or [c for v in cols.values() for c in v]
            pg["col"] = Counter(same).most_common(1)[0][0] if same else (0, 10 ** 4)
        L, R = pg["col"]
        R = max(R, max((max(c["x1"] for c in ln["cs"] if c["text"].strip()) for ln in pg["lines"]
                        if sum(1 for c in ln["cs"] if c["text"].strip() and abs(c["size"] - S) < 0.6) >= 8
                        and max(c["x1"] for c in ln["cs"] if c["text"].strip()) <= R + 1.5), default=R))
        ends = [max(c["x1"] for c in ln["cs"] if c["text"].strip()) for ln in pg["lines"]
                if sum(1 for c in ln["cs"] if c["text"].strip() and abs(c["size"] - S) < 0.6) >= 8]
        just = bool(ends) and sum(1 for e in ends if abs(e - R) <= 1.5) >= 0.45 * len(ends)   # justified: lines end at R
        for ln in pg["lines"]:
            ln["segs"] = segments(ln, S, L, R, just)
            for sg in ln["segs"]:
                sg["page"] = pg["no"]
        nxt = split_foot(S, pg, nxt)
    return S, pages


def cluster(cs, S):
    """Characters → lines by their top edge (a superscript shares the top of its line, a subscript would not)."""
    lines = []
    for c in sorted(cs, key=lambda c: (c["top"], c["x0"])):
        ln = lines[-1] if lines else None
        if not c["text"].strip():
            if ln is not None and c["top"] <= ln["top"] + 0.6 * ln["size"]:
                ln["cs"].append(c)
            continue
        if ln is not None and c["top"] < ln["top"] + 0.6 * max(ln["size"], c["size"] if c["size"] >= 0.8 * ln["size"] else 0):
            ln["cs"].append(c)
            ln["size"] = max(ln["size"], c["size"])
        else:
            lines.append({"top": c["top"], "size": c["size"], "cs": [c]})
    for ln in lines:
        ln["cs"].sort(key=lambda c: c["x0"])
        glyphs = [c for c in ln["cs"] if c["text"].strip()]      # a space set over a letter (ZH justifies the line but leaves
        ln["cs"] = [c for c in ln["cs"] if c["text"].strip() or not any(   # its last space where it stood: "Mär z", "un d")
            min(c["x1"], g["x1"]) - max(c["x0"], g["x0"]) > 0.4 * max(c["x1"] - c["x0"], 0.1) for g in glyphs)]
        big = [c for c in ln["cs"] if c["text"].strip() and c["size"] >= 0.8 * ln["size"]]
        ln["size"] = Counter(round(c["size"], 1) for c in big).most_common(1)[0][0] if big else ln["size"]
        ln["text"] = "".join(c["text"] for c in ln["cs"]).strip()
    return lines


def furniture(S, pages, number):
    """Drop the head and foot of the pages: recurring edge lines (digits masked), bare page numbers, the act's number."""
    n = len(pages)
    edge = Counter()
    for pg in pages:
        for ln in pg["lines"]:
            if ln["top"] < 0.12 * pg["h"] or ln["top"] > 0.9 * pg["h"]:
                edge[mask(ln["text"])] += 1
    rec = {k for k, v in edge.items() if v >= max(2, 0.4 * n)}
    nb = re.sub(r"\s+", "", number or "")
    for pg in pages:
        keep = []
        for ln in pg["lines"]:
            t = re.sub(r"\s+", " ", ln["text"])
            at = ln["top"] < 0.12 * pg["h"] or ln["top"] > 0.9 * pg["h"]
            rest = re.sub(r"\s+", " ", t.replace(number, " ")).strip() if number else t
            flat = re.sub(r"\s+", "", t)
            title = pg is pages[0] and ln["size"] >= 1.1 * S and not (nb and nb in flat)   # the act's title on the first page,
            #                                                    though the running header repeats it (the header has the number)
            if TEMPLATE.match(t) or STAMP.match(t) or at and ((mask(t) in rec and mask(t) and not title) or re.fullmatch(r"[-–—]?\s*\d{1,4}\s*[-–—]?", t)
                       or (nb and re.sub(r"\s+", "", t) == nb) or (number and number in t and re.fullmatch(r"\d{0,4}", rest))
                       or (number and (t.startswith(number + " ") or t.endswith(" " + number)))
                       or (nb and (flat.startswith(nb) or flat.endswith(nb)) and not re.match(re.escape(nb) + r"[\d.]", flat))
                       or "(cid:" in t):                  # "…an der ZHAW414.253.811": the number glued to the header
                continue
            keep.append(ln)
        pg["lines"] = keep


def mask(t: str) -> str:
    """An edge line with its digits gone and its words sorted: "2 Schaffhauser Rechtsbuch 1997" = "… 1997 1"."""
    return " ".join(sorted(w for w in re.findall(r"[^\W\d]+", t) if len(w) > 1))


def segments(ln, S, L, R, just=False):
    """A line's characters as segments: the body column, and marginal notes left or right of it."""
    parts = {"l": [], "b": [], "r": []}
    chunks, cur, prev = [], [], None                     # runs of characters without a gap wider than 1.2·S
    for c in ln["cs"]:
        if not c["text"].strip():
            cur.append(c)
            continue
        gap = c["x0"] - prev["x1"] if prev is not None else 0
        raised = c["bottom"] < max(p["bottom"] for p in ln["cs"]) - 0.25 * c["size"]
        if prev is not None and (gap > 1.2 * max(S, ln["size"])
                                 or (prev["x1"] <= L - 1 and c["x0"] >= L - 1 and gap > 0.1 * S)       # out of the left margin
                                 or (c["x0"] >= R + 1.5 and prev["x1"] <= R + 1.5 and gap > 0.15 * S
                                     and (just or (c["size"] < 0.88 * S and (c["size"] >= 0.7 * S or not raised))))):   # into the right margin
            chunks.append(cur)                           # a wide gap, or a word that crosses the column's edge
            cur = []
        cur.append(c)
        prev = c
    chunks.append(cur)
    for k, ch in enumerate(chunks):
        vis = [c for c in ch if c["text"].strip()]
        if not vis:
            continue
        x0, x1 = min(c["x0"] for c in vis), max(c["x1"] for c in vis)
        if x1 <= L - 1.5:
            parts["l"] += ch                             # a marginal note left of the column (GR, AG, SH …)
        elif x0 >= R + 1.5 or (k > 0 and x0 >= R - 0.35 * (R - L) and any(c["text"].strip() for c in parts["b"])
                               and x0 - max(c["x1"] for c in parts["b"] if c["text"].strip()) > 2.5 * S):
            parts["r"] += ch                             # right of the column, set apart by a wide gap (AI …)
        else:
            parts["b"] += ch
    out = []
    for side in ("l", "b", "r"):
        cs = parts[side]
        if not any(c["text"].strip() for c in cs):
            continue
        big = [c for c in cs if c["text"].strip() and c["size"] >= 0.8 * ln["size"]] or [c for c in cs if c["text"].strip()]
        lsize = Counter(round(c["size"], 1) for c in big).most_common(1)[0][0]
        base = Counter(round(c["bottom"]) for c in big).most_common(1)[0][0]
        sg = {"top": min(c["top"] for c in cs if c["text"].strip()), "bottom": max(c["bottom"] for c in cs),
              "x0": min(c["x0"] for c in cs if c["text"].strip()), "x1": max(c["x1"] for c in cs if c["text"].strip()),
              "size": lsize, "marg": side != "b", "runs": []}
        runs, prev = [], None
        for c in cs:
            if not c["text"].strip():
                if runs and not runs[-1][0].endswith(" "):
                    runs.append((" ", False))
                continue
            small = c["size"] < 0.8 * lsize
            sup = small and (c["bottom"] < base - 0.12 * lsize or (not any(t.strip() for t, _ in runs) and c["text"].isdigit()))
            if prev is not None and c["x0"] - prev["x1"] > 0.12 * min(c["size"], prev["size"]) and runs and not runs[-1][0].endswith(" "):
                runs.append((" ", False))
            runs.append((c["text"], sup))
            prev = c
        merged = []
        for t, sup in runs:
            sup = sup and t != " "
            if merged and merged[-1][1] == sup:
                merged[-1] = (merged[-1][0] + t, sup)
            else:
                merged.append((t, sup))
        sg["runs"] = [(re.sub(r"_{4,}", " ", t), sup) for t, sup in merged]   # separator rules typed as underscores
        norm = big
        sg["bold"] = sum(bold(c["fontname"]) for c in norm) >= 0.8 * len(norm)
        lead = []
        for c in cs:
            if not c["text"].strip():
                continue
            if c["size"] < 0.8 * lsize:
                if lead:
                    break
                continue
            if not (bold(c["fontname"]) or italic(c["fontname"]) or (BODY_FONT and c["fontname"] != BODY_FONT)):
                break
            lead.append(c)
        sg["lead"] = len(lead)
        sg["other"] = bool(norm) and all(c["fontname"] != BODY_FONT for c in norm)
        out.append(sg)
    return out


def split_foot(S, pg, nxt=1):
    """The page's footnotes: the block of smaller print at the bottom that starts with a number. Returns the number the
    next page's notes would continue with (ZH prints its notes after the last article, 1 … n over one or more pages)."""
    keep = pg["lines"]
    tail = []                                            # short lines at the very bottom ("nGS 28–45") do not end the notes
    while keep and keep[-1]["top"] > 0.9 * pg["h"] and keep[-1]["size"] > 0.92 * S and len(keep[-1]["text"]) < 40:
        keep[-1]["tail"] = True
        tail.insert(0, keep[-1])
        keep = keep[:-1]
    k = len(keep)
    while k > 0 and keep[k - 1]["size"] <= 0.92 * S:
        k -= 1
    while k < len(keep) and not FOOT.match(keep[k]["text"]):
        if k + 1 < len(keep) and re.fullmatch(r"\d{1,3}", keep[k + 1]["text"]):     # the number set below its first line
            num, first = keep[k + 1], keep[k]
            keep[k] = {**first, "cs": num["cs"] + first["cs"], "text": num["text"] + " " + first["text"],
                       "size": min(num["size"], first["size"])}
            del keep[k + 1]
            continue
        k += 1
    nums = [int(m.group(1)) for ln in keep[k:] for m in [re.match(r"^\s*(\d{1,3})(?!\d)", ln["text"])] if m and FOOT.match(ln["text"])]
    run = len(nums) >= 3 and nums[0] in (1, nxt) and nums == list(range(nums[0], nums[0] + len(nums)))
    if len(keep) - k > 0.6 * len(keep) and len(keep) > 6 and not run:
        k = len(keep)                                    # a page in small print (a change table, an annex): text, not notes
    pg["body"], pg["foot"] = keep[:k] + tail, keep[k:]
    return nums[-1] + 1 if run else nxt


def text_of(sg, md=False):
    return "".join((f"<sup>{t.strip()}</sup>" + (" " if t.endswith(" ") else "")) if sup and md else t for t, sup in sg["runs"])


def plain(sg):
    return "".join(t for t, _ in sg["runs"]).strip()


def plain_tok(sg):
    """As plain(), a superscript set apart (the Markdown writes "<sup>1</sup> Die", the PDF "¹Die")."""
    r = sg["runs"]
    return "".join(f"{t} " if sup and i == 0 else t for i, (t, sup) in enumerate(r)).strip()


# ---------------------------------------------------------------- footnotes
def footnotes(S, pages):
    """{(page, number): text} from the footnote blocks at the foot of the pages (numbering may restart per page)."""
    notes, cur = {}, None
    for pg in pages:
        for ln in pg["foot"]:
            s = " ".join(text_of(x) for x in ln["segs"]).strip()
            m = re.match(r"^\s*(\d+|\*+)\s?\)?\s*(.*)$", s)
            if m and FOOT.match(ln["text"]):
                cur = (pg["no"], m.group(1))
                notes[cur] = m.group(2)
            elif cur is not None:
                notes[cur] = join_lines(notes[cur], s)
    return notes


def join_lines(a: str, b: str) -> str:
    a, b = a.rstrip(), b.lstrip()
    if not a:
        return b
    m = re.search(r"([A-Za-zÀ-ÿĀ-ž]+)-$", a)
    if m and b[:1].islower():
        w = re.match(r"[A-Za-zÀ-ÿĀ-ž]+", b)
        if w and w.group(0).lower() in CONJ:
            return a + " " + b
        return a[:-1] + b
    if a.endswith("-") and b[:1].isupper() and m:
        return a + b
    if a.endswith("/") and b.startswith("-"):
        return a + b
    return a + " " + b


# ---------------------------------------------------------------- blocks
def blocks(S, pages):
    pitch = []
    for pg in pages:
        ts = [ln["top"] for ln in pg["body"] if any(abs(s["size"] - S) < 0.6 and not s["marg"] for s in ln["segs"])]
        pitch += [b - a for a, b in zip(ts, ts[1:]) if 0 < b - a < 3 * S]
    P = sorted(pitch)[len(pitch) // 2] if pitch else 1.2 * S
    out, marg = [], []
    prev, enacted, enum = None, False, 0                 # enum: the number of the last item "4. Das Haftungsgesetz …"
    for pg in pages:
        L, R = pg["col"]
        for ln in pg["body"]:
            for s in ln["segs"]:
                if s["marg"]:
                    marg.append((pg["no"], s["top"], s))
                    continue
                s["tail"] = ln.get("tail", False)
                t = plain(s)
                if not t:
                    continue
                m = ART.match(t)
                kind = "text"
                centred = s["x0"] > L + 3 * S and s["x1"] < R - 3 * S and abs((s["x0"] - L) - (R - s["x1"])) < 2 * S
                at_start = prev is None or prev["kind"] != "text" or bool(re.search(r"[.:;!?]$", prev["tail"]))
                if m and (s["lead"] >= len(m.group(1).replace(" ", "")) - 1 or s["bold"]):
                    # the number in bold; a rest in plain type is the article's text, not its heading (JU, SO)
                    kind = "art_inline" if m.group(2).strip() and not s["bold"] and \
                        s["lead"] < len(m.group(1).replace(" ", "")) + 2 and m.group(2)[:1].isupper() and \
                        (s["x1"] >= R - 3 * S or re.search(r"[.:;!?]$", m.group(2).strip())) else "art"
                    # a rest that ends the line short without a stop is the article's heading ("Art. 3   Egalité", VS)
                elif m and not m.group(2).strip() and (centred or at_start):
                    kind = "art"                        # "Art. 1" alone on its line (AI: centred, regular)
                elif at_start and re.match(r"^(?:§§?|Art\.|Artikel|Article|Articolo)\s*(?:\d+\s?[a-z]?(?:bis|ter|quater)?\.|premier|unique|primo)\s+(?:\d+[a-z]?\s+)?[A-ZÀ-Ý«]", t):
                    kind = "art_inline"                 # "§ 1. Der Staat …" (older SO acts: number and text on one line)
                elif s["size"] > 1.12 * S or (enacted and ((s["bold"] and len(t) > 2 and not t[:1].islower()) or (
                        s.get("other") and abs(s["size"] - S) < 0.6 and len(t) < 90 and not re.search(r"[.,;:]$", t)
                        and t[:1].isupper() and not LISTM.match(t)))):
                    kind = "title"
                if kind == "text" and HEAD.match(t) and len(t) < 120 and not re.search(r"[.;,]$", t):
                    kind = "title"                      # "1. Kapitel: …", "2. Abschnitt: Landrat", "Chapitre premier"
                me = None if DATE_START.match(t) else re.match(r"^(\d{1,2})\.\s?[A-ZÀ-Ý]", t)
                if kind == "title" and me and int(me.group(1)) == enum + 1 and not HEAD.match(t):
                    kind = "text"                       # the next item of a numbered list, not a heading (ZH annexes)
                if me:
                    enum = int(me.group(1))
                if s["tail"]:
                    kind = "text"
                if kind in ("art", "art_inline") or ENACT.search(t):
                    enacted = True
                gap = s["top"] - prev["last_top"] if prev is not None and prev["page"] == pg["no"] else 0
                if prev is not None and kind == "title" and prev["kind"] == "title" and prev["page"] == pg["no"] \
                        and abs(prev["size"] - s["size"]) < 0.3 and gap < 1.8 * s["size"]:
                    new = False                         # a title over several lines
                else:
                    new = prev is None or kind != "text" or prev["kind"] in ("art", "title")
                    if kind == "text" and prev is not None and prev["kind"] == "art_inline":
                        new = None                      # the text of "§ 1. …" runs on: the usual paragraph rules
                    if new is None or not new:
                        first = s["runs"][0]
                        listy = bool(LISTM.match(t)) and not DATE_START.match(t) and (prev["list"] or bool(re.search(r"[:;,.]$", prev["tail"])))
                        row = bool(re.match(r"^\d{1,5}\s+[A-ZÀ-Ý]", t)) and bool(re.search(r"(?:[–\-]|\d|\.)\s*$", prev["tail"]))
                        new = bool(first[1] and re.match(r"\d", first[0].strip() or "x")) or listy or row or s["tail"] \
                            or gap > 1.45 * P or centred or prev["centred"] \
                            or (prev["x1"] < R - 3 * S and bool(re.search(r"[.:;!?]$", prev["tail"])))
                if new:
                    prev = {"kind": kind, "segs": [s], "page": pg["no"], "top": s["top"], "last_top": s["top"], "x1": s["x1"],
                            "tail": t, "centred": centred, "size": s["size"], "marg": [], "list": bool(LISTM.match(t))}
                    out.append(prev)
                else:
                    prev["segs"].append(s)
                    prev.update(last_top=s["top"], x1=s["x1"], tail=t, page=pg["no"])
    # marginal notes: grouped by proximity, attached to the block beside or after them
    groups = []
    for no, top, s in marg:
        if groups and groups[-1]["page"] == no and top - groups[-1]["bottom"] < 0.9 * S and abs(s["x0"] - groups[-1]["x0"]) < 4 * S:
            groups[-1]["text"] = join_lines(groups[-1]["text"], text_of(s))
            groups[-1]["bottom"] = s["bottom"]
        else:
            groups.append({"page": no, "top": top, "bottom": s["bottom"], "x0": s["x0"], "text": text_of(s)})
    for g in groups:
        cand = [b for b in out if b["page"] == g["page"] and b["top"] >= g["top"] - 1.2 * S] or \
               [b for b in out if b["page"] > g["page"]]
        target = min(cand, key=lambda b: (b["page"], abs(b["top"] - g["top"]))) if cand else (out[-1] if out else None)
        if target is not None:
            target["marg"].append(g["text"])
    return out


# ---------------------------------------------------------------- Markdown
class Writer:
    def __init__(self, notes, lang):
        self.notes, self.lang = notes, lang
        self.lines, self.pending, self.scope, self.count, self.used, self.scopes = [], [], "t", {}, set(), set()
        self.calls, self.src = [], Counter()
        # endnotes (SH "Fussnoten:", NW, ZH): at least three notes, numbered 1, 2, 3 … without a gap or repeat, on pages
        # that follow one another
        nums = [int(k[1]) for k in notes if k[1].isdigit()]
        pgs = sorted({k[0] for k in notes})
        self.endnotes = len(nums) >= 3 and len(nums) == len(notes) and sorted(nums) == list(range(1, len(nums) + 1)) \
            and pgs[-1] - pgs[0] + 1 == len(pgs)

    def set_scope(self, s):
        s = re.sub(r"\W", "", s) or "a"
        base, k = s, 1
        while s in self.scopes:
            k += 1
            s = f"{base}_{k}"
        self.scopes.add(s)
        self.scope = s

    def blank(self):
        if self.lines and self.lines[-1] != "":
            self.lines.append("")

    def flush(self):
        if self.pending:
            self.blank()
            self.lines += [f"[^{a}]: {b}" for a, b, _ in self.pending]
            self.pending = []

    def find(self, n, page):
        """The note a call means: the same page first (footnotes stand where they are called), then the next, the one
        before; endnotes (SH "Fussnoten:") by their number when it is unique."""
        for p in (page, page + 1, page - 1):
            if (p, n) in self.notes:
                return (p, n)
        if self.endnotes:                                # by number, wherever they stand (ZH: before the annex)
            ks = [k for k in self.notes if k[1] == n]
            return ks[0] if len(ks) == 1 else None
        return None

    def call(self, key):
        n = key
        self.used.add(n)
        self.calls.append(n[1])
        for lab, _, m in self.pending:
            if m == n:
                return f"[^{lab}]"                   # the same note called twice in one article
        k = self.count.get(self.scope, 0) + 1
        self.count[self.scope] = k
        lab = f"{self.scope}-{k}"
        self.pending.append((lab, squash(esc(self.notes[n])), n))
        return f"[^{lab}]"

    def render(self, segs):
        """The text of a block's segments, lines joined; superscripts as paragraph numbers or footnote calls. The words
        written go to self.src (the counterpart of the Markdown's words, footnote labels aside)."""
        out, plain_out = "", ""
        for i, s in enumerate(segs):
            parts, plain_ = [], []
            runs = list(s["runs"])
            for j, (t, sup) in enumerate(runs):
                if sup:
                    n = t.strip().rstrip(")").strip()
                    comma = n.endswith(",") and n[:-1].strip().isdigit()      # "(vom 20. April 2015)¹,²": two calls
                    n = n.rstrip(",").strip() if comma else n
                    nxt = runs[j + 1][0] if j + 1 < len(runs) else ""
                    prv = runs[j - 1][0] if j > 0 else ""
                    unit = n in ("2", "3") and re.search(r"(?:\b[kcdm]?m|CO|m³)\s?$", prv)   # m², km², CO₂ (set raised)
                    key = self.find(n, s.get("page", 0)) if (i > 0 or j > 0 or parts) and not unit else None
                    parnum = (not t.strip().endswith(")") and not nxt.lstrip().startswith(")") and (not prv or prv.endswith(" "))
                              and re.match(r"\s*[A-ZÀ-Ý«(]", nxt or "") is not None)
                    if key and not parnum:
                        parts.append(self.call(key) + ("," if comma else ""))
                        if nxt.lstrip().startswith(")") and not t.strip().endswith(")"):
                            runs[j + 1] = (re.sub(r"^\s*\)", "", nxt, count=1), False)
                        continue
                    lead = i == 0 and j == 0 and not parts
                    parts.append(f"<sup>{esc(t.strip())}</sup>" + (" " if lead else ""))
                    plain_.append(t.strip() + (" " if lead else ""))
                    continue
                parts.append(esc(t))
                plain_.append(t)
            line = "".join(parts)
            pg = s.get("page", 0)

            def plain_call(m):                           # "(GesV)6)", "HMG1))": a call in body-size type (SH)
                key = self.find(m.group(1), pg)
                return self.call(key) if key and key not in self.used else m.group(0)
            line2 = re.sub(r"(?<=[A-Za-zÀ-ÿ\)\]])(\d{1,3})\)", plain_call, line)
            if line2 != line:
                plain_ = [re.sub(r"(?<=[A-Za-zÀ-ÿ\)\]])(\d{1,3})\)", lambda m: "" if self.find(m.group(1), pg) else m.group(0), "".join(plain_))]
                line = line2
            out = join_lines(out, line) if out else line
            pl = "".join(plain_)
            plain_out = join_lines(plain_out, pl) if plain_out else pl
        self.src.update(WORD.findall(plain_out))
        out = re.sub(r"(?:\s?\.){5,}\s?", " … ", out)    # dot leaders of tariffs and tables
        return re.sub(r"\s+(\[\^)", r"\1", squash(out))


def convert(path, front: dict, notice: str, lang: str = "de", number: str = ""):
    return convert_checked(path, front, notice, lang, number)[0]


def convert_checked(path, front: dict, notice: str, lang: str = "de", number: str = ""):
    """(Markdown, Counter of the words the Markdown must hold): every word the reading kept, less the footnote calls
    and footnote numbers that became labels."""
    S, pages = read(path, number)
    notes = footnotes(S, pages)
    bl = blocks(S, pages)
    w = Writer(notes, lang)
    title, seen_art, after_art, enacted = "", False, False, False
    titles = [b for b in bl if b["kind"] == "title"]
    big = max((b["segs"][0]["size"] for b in titles), default=S)
    for b in bl:
        txt = w.render(b["segs"])
        if not txt:
            continue
        if b["kind"] == "title" and not title and not seen_art and not enacted and not HEAD.match(txt) \
                and not re.search(r"[.:]$", txt) and len(txt) < 400:
            title = txt                                  # a call in the title stays in the heading
            continue
        enacted = enacted or bool(b["kind"] == "text" and ENACT.search(re.sub(r"\[\^[^\]]+\]$", "", txt)))
        if b["kind"] in ("art", "art_inline"):
            seen_art = True
            w.flush()
            txt = re.sub(r"^((?:Art\.|Artikel|Article|Articolo|Art|§§?)\s*\d+)\s?<sup>([a-z]{1,9})</sup>", r"\1\2", txt)
            m = re.match(rf"^((?:Art\.|Artikel|Article|Articolo|Art|§§?)\s*{NUM})(?![\w])\.?\s*", txt)
            num = squash(m.group(1)) if m else txt[:12]
            rest = squash(txt[m.end():]) if m else ""
            w.set_scope(num.replace("Artikel", "").replace("Article", "").replace("Art.", "").replace("§", ""))
            calls = "".join(re.findall(r"^\s*((?:\[\^[^\]]+\])+)", rest)) if rest.startswith("[^") else ""
            rest = rest[len(calls):].strip()
            w.blank()
            w.lines.append("#### " + num + calls)
            for g in b["marg"]:
                w.lines += ["", f"**{squash(w.render([{'runs': [(g, False)]}]))}**"]
            head = b["segs"][0]["lead"] >= len(num) + 2 or (
                len(b["segs"]) == 1 and len(rest) < 90 and not rest.startswith("<sup>") and not re.search(r"[.:;,]$", rest))
            if rest:
                w.lines += ["", f"**{rest}**" if head else line_safe(rest)]
            after_art = not rest and not b["marg"]
            continue
        if after_art and b["kind"] == "text" and len(b["segs"]) == 1 and len(txt) < 90 and not txt.startswith("<sup>") \
                and not LISTM.match(txt) and not re.search(r"[.:;,]$", re.sub(r"\[\^[^\]]+\]$", "", txt)):
            after_art = False                            # the article's heading on the line below its number (VS, NW …)
            w.blank()
            w.lines.append(f"**{txt}**")
            continue
        after_art = False
        for g in b["marg"]:
            w.blank()
            w.lines.append(f"**{squash(w.render([{'runs': [(g, False)]}]))}**")
        if b["kind"] == "title":
            w.flush()
            w.set_scope("h" + txt[:20])
            w.blank()
            w.lines.append(("## " if b["segs"][0]["size"] >= big - 0.1 and b["segs"][0]["size"] > S else "### ") + txt)
            continue
        w.blank()
        if LISTM.match(txt) and not txt.startswith("<sup>") and not DATE_START.match(txt):
            w.lines.append("- " + re.sub(r"^(\d+)\.(?=\s)", r"\1\\.", re.sub(r"^[–\-•·]\s+", "", txt)))   # a dash item: the bullet is the dash
        else:
            w.lines.append(line_safe(txt))
    w.flush()
    rest = [n for n in notes if n not in w.used]
    if rest:
        w.blank()
        w.lines += ["## " + {"fr": "Autres notes", "it": "Altre note"}.get(lang, "Weitere Fussnoten"), ""]
        w.lines += [f"- [{n[1]}] {squash(esc(notes[n]))}" for n in rest]
    yaml = ["---"] + [f"{k}: {yval(v)}" for k, v in front.items() if v not in (None, "", [])] + ["---", "", f"> {notice}", ""]
    body = re.sub(r"\n{3,}", "\n\n", "\n".join([f"# {title or front.get('title', '')}", ""] + w.lines)).strip() + "\n"
    src = w.src
    for n, t in notes.items():
        src.update(WORD.findall(re.sub(r"<sup>|</sup>", "", t)))
    return "\n".join(yaml) + "\n" + body, src


MONTHS = {**{m: i + 1 for i, m in enumerate("januar februar märz april mai juni juli august september oktober november dezember".split())},
          **{m: i + 1 for i, m in enumerate("janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split())},
          **{m: i + 1 for i, m in enumerate("gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre".split())}}
SINCE = re.compile(r"(?:in Kraft (?:seit|ab|getreten am)|en vigueur (?:depuis le|dès le|le)|in vigore (?:dal|il))\s+"
                   r"(\d{1,2})\.?\s*(?:er|°)?\s*([A-Za-zäéèûô]+)\s+(\d{4})", re.I)


def latest_in_force(text: str, today: str) -> str:
    """The day the text took effect, from its change notes: the latest "in Kraft seit …" / "en vigueur depuis le …" up to today."""
    best = ""
    for d, m, y in SINCE.findall(text.replace("\xa0", " ")):
        mo = MONTHS.get(m.lower())
        if mo:
            x = f"{y}-{mo:02d}-{int(d):02d}"
            if x <= today and x > best:
                best = x
    return best
