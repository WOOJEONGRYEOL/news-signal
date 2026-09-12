"""연합뉴스 카테고리별 RSS (발행량 신호). 키 불필요."""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

from ..fetch import get
from ..timeutil import from_rfc822

CATS = {
    "politics": "정치", "economy": "경제", "society": "사회", "local": "사회",
    "international": "세계", "culture": "생활/문화", "sports": "스포츠", "entertainment": "연예",
    "industry": "경제", "market": "경제", "health": "생활/문화",
}
TAG = re.compile(r"<[^>]+>")


def fetch_yna(slug: str) -> list[dict]:
    xml = get(f"https://www.yna.co.kr/rss/{slug}.xml")
    root = ET.fromstring(xml)
    out: list[dict] = []
    for item in root.iter("item"):
        title = html.unescape(TAG.sub("", item.findtext("title") or "")).strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        desc = html.unescape(TAG.sub("", item.findtext("description") or "")).strip()
        out.append({
            "title": title,
            "url": link,
            "press": "연합뉴스",
            "published": from_rfc822(item.findtext("pubDate") or ""),
            "lede": desc[:200],
        })
    return out
