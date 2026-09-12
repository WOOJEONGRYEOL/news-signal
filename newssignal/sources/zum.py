"""줌(zum.com) 'AI 이슈트렌드' 키워드. 키 불필요."""
from __future__ import annotations

import html
import re

from ..fetch import get


def fetch_zum() -> list[dict]:
    s = get("https://zum.com/")
    out: list[dict] = []
    for m in re.finditer(r'issue-word-list__rank">\s*(\d+)\s*</span>\s*<span class="issue-word-list__keyword[^"]*"[^>]*>(.*?)</span>', s, re.S):
        kw = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
        if kw:
            out.append({"rank": int(m.group(1)), "keyword": kw})
    # 같은 순위가 여러 번 나오면(슬라이드 복제) 첫 번째만
    seen: set[int] = set()
    uniq = []
    for it in sorted(out, key=lambda x: x["rank"]):
        if it["rank"] in seen:
            continue
        seen.add(it["rank"])
        uniq.append(it)
    return uniq
