"""줌(zum.com) 'AI 이슈트렌드' 키워드. 키 불필요.

2026-10-12 오후 줌 첫 화면이 카드형으로 바뀌면서 HTML 에는 1위 카드 하나만 그려지고 나머지는 화면이 뜬 뒤
채워진다. 예전 방식(목록 HTML 긁기)은 0건을 돌려주면서도 오류가 나지 않아 4주 동안 조용히 비어 있었다.

지금은 페이지에 함께 실려 오는 원본 데이터(Next.js RSC 페이로드)를 읽는다. 그 안에 목록이 두 개 있는데,
화면에 보이는 것은 displayRank(표시 순위)가 붙은 'items' 10개다. 'issueWords' 배열은 순서·구성이 화면과
다르므로(같은 시각에 대조해 확인) 쓰지 않는다.
"""
from __future__ import annotations

import html
import json
import re

from ..fetch import get

TOP = 10


def _payload(page: str) -> str:
    blob = ""
    for c in re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', page, re.S):
        try:
            blob += json.loads(c)
        except ValueError:
            continue
    return blob


def _display_items(page: str) -> list[dict]:
    blob = _payload(page)
    dec = json.JSONDecoder()
    for m in re.finditer(r'"items":\[', blob):
        try:
            arr, _ = dec.raw_decode(blob, m.end() - 1)
        except ValueError:
            continue
        rows = [x for x in arr if isinstance(x, dict) and "displayRank" in x and str(x.get("keyword") or "").strip()]
        if rows:
            rows.sort(key=lambda x: int(x["displayRank"]))
            return [{"rank": int(x["displayRank"]), "keyword": str(x["keyword"]).strip()} for x in rows[:TOP]]
    return []


def _from_markup(page: str) -> list[dict]:
    """원본 데이터를 못 찾았을 때의 예비: 예전 목록형·지금 카드형 HTML 에서 보이는 만큼만(카드형은 1위뿐)."""
    out: list[dict] = []
    for pat in (r'issue-word-list__rank">\s*(\d+)\s*</span>\s*<span class="issue-word-list__keyword[^"]*"[^>]*>(.*?)</span>',
                r'issue-word-list__card-rank">\s*(\d+)\s*<small>.*?issue-word-list__card-keyword[^"]*"[^>]*>(.*?)</span>'):
        for m in re.finditer(pat, page, re.S):
            kw = html.unescape(re.sub(r"<[^>]+>", "", m.group(2))).strip()
            if kw:
                out.append({"rank": int(m.group(1)), "keyword": kw})
    seen: set[int] = set()
    uniq = []
    for it in sorted(out, key=lambda x: x["rank"]):   # 같은 순위가 여러 번(슬라이드 복제) 나오면 첫 번째만
        if it["rank"] not in seen:
            seen.add(it["rank"])
            uniq.append(it)
    return uniq


def fetch_zum() -> list[dict]:
    page = get("https://zum.com/")
    items = _display_items(page) or _from_markup(page)
    if not items:
        # 조용히 빈 목록을 돌려주면 수집 로그에 '실패'로 남지 않는다. 화면 구조가 또 바뀌면 바로 드러나게 오류로 올린다.
        raise RuntimeError("AI 이슈트렌드를 찾지 못함(페이지 구조 변경?)")
    return items
