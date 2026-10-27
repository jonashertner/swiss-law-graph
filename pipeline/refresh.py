"""The weekly refresh (decision 39): which cached files a fetcher reads again, and the day of the run.

Lists, headers and texts in force change: Fedlex's version lists and its history, a canton's index, an act's header
with its versions, the text in force Geneva, Neuchâtel and Jura publish. The document of a version does not, once
published: the XML of a consolidation, a LexWork or BLV version, the PDF of a Zürich Nachtrag. Those stay cached.

SWISSLAW_REFRESH=<unix time> (the start of the run) makes a cached copy of something that changes count only if it was
written since then, so a second script in the same run reuses what the first fetched; without it every cache counts,
as before. SWISSLAW_TODAY=YYYY-MM-DD fixes the day of the run (tests); otherwise it is today in Zürich.
"""
import datetime as dt
import hashlib
import os
from pathlib import Path
from zoneinfo import ZoneInfo

SINCE = float(os.environ.get("SWISSLAW_REFRESH") or 0)
TODAY = os.environ.get("SWISSLAW_TODAY") or dt.datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat()


def fresh(p: Path) -> bool:
    """A cached copy of something that changes: usable unless this run refreshes and it is older than the run."""
    return p.exists() and (not SINCE or p.stat().st_mtime >= SINCE)


def digest(p: Path) -> str:
    """The content of a source a converter read, so that it converts again only when the source changed."""
    return hashlib.sha1(p.read_bytes()).hexdigest()[:16]
