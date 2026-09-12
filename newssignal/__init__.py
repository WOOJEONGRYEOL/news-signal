"""News Signal — 뉴스룸용 실시간 뉴스·검색 트렌드 대시보드 (stdlib only, zero cost)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

__version__ = "0.1.0"

KST = timezone(timedelta(hours=9), "KST")


def now_kst() -> datetime:
    return datetime.now(KST).replace(microsecond=0)
