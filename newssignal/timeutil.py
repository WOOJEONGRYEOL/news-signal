"""Time parsing helpers (RSS pubDate, 네이버 상대시각) → KST ISO strings."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from . import KST


def iso(dt: datetime) -> str:
    return dt.astimezone(KST).replace(microsecond=0).isoformat(timespec="minutes")


def from_rfc822(s: str) -> str:
    try:
        return iso(parsedate_to_datetime(s.strip()))
    except Exception:
        return ""


REL = re.compile(r"(\d+)\s*(분|시간|일)\s*전")


def from_relative(s: str, now: datetime) -> str:
    """'10시간전' → ISO. Unknown formats → ''."""
    s = s.strip()
    m = REL.search(s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"분": timedelta(minutes=n), "시간": timedelta(hours=n), "일": timedelta(days=n)}[unit]
        return iso(now - delta)
    m = re.match(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.?\s*(오전|오후)?\s*(\d{1,2}):(\d{2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h, mi = int(m.group(5)), int(m.group(6))
        if m.group(4) == "오후" and h < 12:
            h += 12
        if m.group(4) == "오전" and h == 12:
            h = 0
        return iso(datetime(y, mo, d, h, mi, tzinfo=KST))
    return ""
