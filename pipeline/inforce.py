"""Which federal acts are in force (decision 33): Fedlex's status, corrected by Fedlex's own dates.

`data/sr_eli.csv` gives each act under an SR number with its inForceStatus (0 in force, 1 no longer in the SR,
2 obsolete, 3 no longer in force, 4 not yet in force), read on RUN_DATE. The status lags behind publication in
both directions: acts that entered into force since 2024 often carry no status at all yet (SR 745.13
Fahrplanverordnung of 20 December 2024, in force since 1 February 2025, beside its predecessor marked repealed on
that day), and acts repealed since 2019 can still be marked in force while their repeal date is recorded (the
EU note exchanges SR 0.142.392.680.01–03, repealed 26 January 2026). The dates of `data/fedlex_history.json`
(entry into force, repeal, end of applicability) decide:

  an act is in force when it entered into force on or before RUN_DATE, no repeal on or before RUN_DATE and no
  end of applicability before RUN_DATE is recorded, and Fedlex marks it in force (0) or gives no status; an act
  without status must have entered into force in 2000 or later (an older one may simply lack its end).

Statuses 1–4 stand as Fedlex gives them (checked 2026-10-27: no act marked 4 has entered into force, no act marked
0 enters into force later). Every consumer reads `rows()` instead of the CSV, so the rule lives here only.
"""
import csv
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_DATE = "2026-10-26"                     # the day sr_eli.csv and the consolidated texts were read
IN_FORCE = "https://fedlex.data.admin.ch/vocabulary/enforcement-status/0"
SINCE = "2000-01-01"


def live(a: dict) -> bool:
    """Do an act's dates say it is in force on RUN_DATE?"""
    f, rep, end = a.get("in_force"), a.get("repealed"), a.get("end")
    return bool(f) and f <= RUN_DATE and not (rep and rep <= RUN_DATE) and not (end and end < RUN_DATE)


@lru_cache(maxsize=1)
def rows() -> tuple[dict, ...]:
    """The rows of sr_eli.csv with `inForce` as the dates decide; `fedlex` keeps the status Fedlex gives and `why`
    says what changed ("dates": no status, in force by its dates; "ended": marked in force, ended by its dates)."""
    p = ROOT / "data/fedlex_history.json"
    hist = json.load(open(p)) if p.exists() else {}         # without the history the status stands as it is
    out = []
    for r in csv.DictReader(open(ROOT / "data/sr_eli.csv", encoding="utf-8")):
        r = {**r, "fedlex": r["inForce"], "why": ""}
        a = hist.get(r["act"].rstrip("/"))
        st = (r["inForce"] or "").rsplit("/", 1)[-1]
        if a is not None and st == "0" and not live(a):
            r["inForce"], r["why"] = "", "ended"
        elif a is not None and st == "" and live(a) and a["in_force"] >= SINCE:
            r["inForce"], r["why"] = IN_FORCE, "dates"
        out.append(r)
    return tuple(out)


def in_force(r: dict) -> bool:
    return (r["inForce"] or "").endswith("/0")


if __name__ == "__main__":
    from collections import Counter
    c = Counter(r["why"] for r in rows() if r["why"])
    fed = Counter((r["why"], "treaty" if r["notation"].startswith("0.") else "federal") for r in rows() if r["why"])
    print(f"{sum(map(in_force, rows()))} acts in force; changed by the dates: {dict(c)}; {dict(fed)}")
