"""Google News 검색 RSS — 키워드 관련 기사 보강용. 키 불필요."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

from ..fetch import get
from ..timeutil import from_rfc822


# 주제별 헤드라인 피드 → 카테고리 (NATION은 정치·사회가 섞여 제외)
TOPICS = {
    "ENTERTAINMENT": "연예", "SPORTS": "스포츠", "BUSINESS": "경제", "TECHNOLOGY": "IT/과학",
    "SCIENCE": "IT/과학", "WORLD": "세계", "HEALTH": "생활/문화",
}


def fetch_topic(topic: str, limit: int = 80) -> list[dict]:
    url = f"https://news.google.com/rss/headlines/section/topic/{topic}?hl=ko&gl=KR&ceid=KR:ko"
    return _parse(get(url), limit)


def search_news(query: str, limit: int = 10) -> list[dict]:
    url = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    return _parse(get(url), limit)


def _parse(xml: str, limit: int) -> list[dict]:
    root = ET.fromstring(xml)
    out: list[dict] = []
    for item in root.iter("item"):
        title = html.unescape(item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        src = (item.findtext("source") or "").strip()
        if not title or not link:
            continue
        if src and title.endswith(" - " + src):
            title = title[: -(len(src) + 3)].strip()
        else:
            title = re.sub(r"\s+-\s+[^-]{1,20}$", "", title)
        out.append({"title": title, "url": link, "press": src,
                    "published": from_rfc822(item.findtext("pubDate") or ""), "lede": ""})
        if len(out) >= limit:
            break
    return out
