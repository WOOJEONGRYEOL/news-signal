"""네이트 실시간 이슈 키워드 (cp949 JSON). 키 불필요."""
from __future__ import annotations

import json

from ..fetch import get

CHANGE = {"n": "new", "s": "same", "+": "up", "-": "down"}


def fetch_nate() -> list[dict]:
    s = get("https://www.nate.com/js/data/jsonLiveKeywordDataV1.js", encoding="cp949").strip()
    s = s.lstrip("﻿")
    data = json.loads(s)
    out: list[dict] = []
    for row in data:
        if not isinstance(row, list) or len(row) < 5:
            continue
        out.append({
            "rank": int(row[0]),
            "keyword": str(row[1]).strip(),
            "short": str(row[4]).strip() or str(row[1]).strip(),
            "change": CHANGE.get(str(row[2]), str(row[2])),
            "delta": int(row[3] or 0) if str(row[3]).lstrip("-").isdigit() else 0,
        })
    return out
