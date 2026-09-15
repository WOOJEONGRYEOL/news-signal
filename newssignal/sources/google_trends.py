"""Google Trends 'Daily Search Trends' RSS — 전국(KR) + 17개 시·도. 키 불필요."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..fetch import clean_xml, get
from ..timeutil import from_rfc822

NS = {"ht": "https://trends.google.com/trending/rss"}

# 세종(KR-50)은 Google Trends가 400을 돌려줘 제외 — 16개 시·도만 지원
REGIONS = {
    "KR-11": "서울", "KR-26": "부산", "KR-27": "대구", "KR-28": "인천", "KR-29": "광주",
    "KR-30": "대전", "KR-31": "울산", "KR-41": "경기", "KR-42": "강원",
    "KR-43": "충북", "KR-44": "충남", "KR-45": "전북", "KR-46": "전남", "KR-47": "경북",
    "KR-48": "경남", "KR-49": "제주",
}


def parse_traffic(s: str) -> int:
    s = s.strip().replace(",", "").replace("+", "")
    m = re.match(r"(\d+(?:\.\d+)?)\s*(만|천)?", s)
    if not m:
        return 0
    n = float(m.group(1))
    unit = m.group(2)
    return int(n * (10000 if unit == "만" else 1000 if unit == "천" else 1))


def fetch_trends(geo: str = "KR") -> list[dict]:
    root = ET.fromstring(clean_xml(get(f"https://trends.google.com/trending/rss?geo={geo}")))
    out: list[dict] = []
    for i, item in enumerate(root.iter("item"), 1):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        traffic = parse_traffic(item.findtext("ht:approx_traffic", default="", namespaces=NS))
        started = from_rfc822(item.findtext("pubDate") or "")
        news = []
        for n in item.findall("ht:news_item", NS):
            t = (n.findtext("ht:news_item_title", default="", namespaces=NS) or "").strip()
            u = (n.findtext("ht:news_item_url", default="", namespaces=NS) or "").strip()
            src = (n.findtext("ht:news_item_source", default="", namespaces=NS) or "").strip()
            if t and u:
                news.append({"title": t, "url": u, "press": src})
        out.append({"rank": i, "keyword": title, "traffic": traffic, "started": started, "news": news})
    return out
