"""Article numbers: parse, order and expand blocks ("Art. 274–274g", "Art. 627 und 628").

Standard library only; shared by the Fedlex fetchers and step 2.
An article number is digits, optionally a letter, optionally a Latin ordinal:
"41", "6a", "6bis", "329gbis".
"""
import re

LATIN = ["bis", "ter", "quater", "quinquies", "sexies", "septies", "octies", "novies", "decies"]
_L = "(?:" + "|".join(LATIN) + ")"
TOKEN = re.compile(r"(\d+)\s*([a-z]?\s*" + _L + r"|[a-z])?(?![a-z0-9])", re.I)
FULL = re.compile(r"^(\d+)([a-z]?)(" + "|".join(LATIN) + r")?$")
MAX_BLOCK = 300


def split(num: str) -> tuple[int, str, str] | None:
    m = FULL.match(num)
    return (int(m.group(1)), m.group(2) or "", m.group(3) or "") if m else None


def sort_key(num: str) -> tuple:
    p = split(num)
    if not p:
        return (10 ** 9, "", 0, num)
    return (p[0], p[1], LATIN.index(p[2]) + 1 if p[2] else 0, "")


def expand_range(a: str, b: str) -> list[str]:
    """Every article number from a to b inclusive, as Fedlex numbers them."""
    pa, pb = split(a), split(b)
    if not pa or not pb or sort_key(b) <= sort_key(a):
        return [a]
    out = [a]
    if pa[0] == pb[0]:
        if pb[2] and not pb[1]:                      # 6–6quater, 6bis–6quater
            start = LATIN.index(pa[2]) + 1 if pa[2] else 0
            out += [f"{pb[0]}{x}" for x in LATIN[start:LATIN.index(pb[2]) + 1]]
        elif pb[1]:                                  # 226a–226d, 274–274g
            start = ord(pa[1]) + 1 if pa[1] else ord("a")
            out += [f"{pb[0]}{chr(k)}" for k in range(start, ord(pb[1]) + 1)]
    elif pb[0] - pa[0] <= MAX_BLOCK:                 # 637–639, 268–278quater
        out += [str(k) for k in range(pa[0] + 1, pb[0] + 1)]
        if pb[1]:
            out += [f"{pb[0]}{chr(k)}" for k in range(ord("a"), ord(pb[1]) + 1)]
        elif pb[2]:
            out += [f"{pb[0]}{x}" for x in LATIN[:LATIN.index(pb[2]) + 1]]
    return list(dict.fromkeys(out))


def parse_num(text: str) -> list[str]:
    """Article numbers named by an article heading's <num> text."""
    t = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    t = re.sub(r"^(?:Art\.?|Artikel|Article|Articolo|§)\s*", "", t, flags=re.I)
    m = TOKEN.match(t)
    if not m:
        return []
    a = (m.group(1) + re.sub(r"\s+", "", m.group(2) or "")).lower()
    rest = t[m.end():]
    sep = re.match(r"\s*(–|-|bis\b|und\b|et\b|e\b|,)\s*", rest)
    if sep:
        m2 = TOKEN.match(rest[sep.end():])
        if m2:
            b = (m2.group(1) + re.sub(r"\s+", "", m2.group(2) or "")).lower()
            return expand_range(a, b) if sep.group(1) in ("–", "-", "bis") else [a, b]
    return [a]


def parse_eid(eid: str) -> list[str]:
    """Article numbers named by an Akoma Ntoso eId ("art_274_274_g" -> 274..274g)."""
    seg = eid.rsplit("/", 1)[-1]
    if not seg.startswith("art_"):
        return []
    ends, cur = [], None
    for tok in seg[4:].split("_"):
        if tok.isdigit():
            if cur:
                ends.append(cur)
            cur = tok
        elif cur and re.fullmatch(r"[a-z]|" + _L, tok):
            cur += tok
    if cur:
        ends.append(cur)
    if len(ends) == 2:
        return expand_range(ends[0], ends[1])
    return ends[:1]
