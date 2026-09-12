"""네이버 뉴스 — 언론사별 랭킹뉴스(모바일, 많이 본 기사) + 섹션별 헤드라인. 키 불필요."""
from __future__ import annotations

import html
import re
from datetime import datetime

from ..fetch import get
from ..timeutil import from_relative

SECTIONS = {"100": "정치", "101": "경제", "102": "사회", "103": "생활/문화", "104": "세계", "105": "IT/과학"}

TAG = re.compile(r"<[^>]+>")


def clean(s: str) -> str:
    return html.unescape(TAG.sub("", s)).replace("\xa0", " ").strip()


def strip_query(url: str) -> str:
    return url.split("?", 1)[0].replace("n.news.naver.com/mnews/article/", "n.news.naver.com/article/")


def fetch_ranking(now: datetime) -> list[dict]:
    """언론사별 '많이 본 뉴스' Top 5 (데스크톱 페이지, EUC-KR) → [{press, rank, title, url, published}]"""
    s = get("https://news.naver.com/main/ranking/popularDay.naver")
    out: list[dict] = []
    for m in re.finditer(r'<strong class="rankingnews_name">([^<]*)</strong>(.*?)</ul>', s, re.S):
        press = clean(m.group(1))
        block = m.group(2)
        for a in re.finditer(
            r'<em class="list_ranking_num">(\d+)(?:<span[^>]*>[^<]*</span>)?</em>\s*'
            r'<div class="list_content">\s*<a href="([^"]*)"[^>]*class="list_title[^"]*"[^>]*>(.*?)</a>\s*'
            r'<span class="list_time[^"]*">([^<]*)</span>', block, re.S):
            out.append({
                "press": press,
                "rank": int(a.group(1)),
                "title": clean(a.group(3)),
                "url": strip_query(html.unescape(a.group(2))),
                "published": from_relative(a.group(4), now),
            })
    return out


def fetch_section(sid: str, now: datetime) -> list[dict]:
    """섹션 헤드라인 → [{title, url, press, published, lede}]"""
    s = get(f"https://news.naver.com/section/{sid}")
    out: list[dict] = []
    seen: set[str] = set()
    for chunk in s.split('class="sa_text"')[1:]:
        m = re.search(r'<a href="([^"]*)" class="sa_text_title[^"]*"[^>]*>\s*'
                      r'<strong class="sa_text_strong">(.*?)</strong>', chunk, re.S)
        if not m:
            continue
        url = strip_query(html.unescape(m.group(1)))
        if url in seen:
            continue
        seen.add(url)
        lede = re.search(r'class="sa_text_lede">(.*?)</div>', chunk, re.S)
        press = re.search(r'class="sa_text_press">(.*?)</div>', chunk, re.S)
        dt = re.search(r'class="sa_text_datetime[^"]*">\s*(?:<b>)?\s*([^<]*?)\s*<', chunk)
        out.append({
            "title": clean(m.group(2)),
            "url": url,
            "press": clean(press.group(1)) if press else "",
            "published": from_relative(dt.group(1), now) if dt else "",
            "lede": clean(lede.group(1)) if lede else "",
        })
    return out
