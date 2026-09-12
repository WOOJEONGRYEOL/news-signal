"""한 번의 수집(스냅샷): 출처 가져오기 → 카테고리별 키워드 신호 결합 → 순위 → 관련 기사 → 지역."""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import now_kst
from .config import Config
from .keywords import CLAUSE_MARK, Extractor, load_stopwords, query_tokens, stems_match
from .sources import google_news, google_trends, nate, naver, yna, zum
from .sources.google_trends import REGIONS
from .store import Store
from .stories import build_stories, related_keywords

CATEGORIES = ["전체", "정치", "경제", "사회", "생활/문화", "세계", "IT/과학", "스포츠", "연예"]
SOURCE_LABEL = {"google": "G", "nate": "N", "zum": "Z"}
SEARCH_FULL = 2.5        # 검색 신호가 1.0(만점)이 되는 가중치 합 (구글 1위 + 트래픽 보너스 수준)
SPIKE_FULL = 5.0         # 지난 7일 평균 대비 5배면 급상승 만점


@dataclass
class Article:
    title: str
    url: str
    press: str
    published: str
    category: str
    origin: str          # naver_section / yna / naver_ranking / google_trends / google_news
    lede: str = ""
    stems: set[str] = field(default_factory=set)

    def out(self) -> dict:
        return {"t": self.title, "u": self.url, "p": self.press, "d": self.published, "o": self.origin}


@dataclass
class SearchTerm:
    term: str
    tokens: list[str]
    weight: float
    source: str
    rank: int
    traffic: int = 0
    news: list[dict] | None = None


def _safe(log: list[str], name: str, fn, *a, **kw):
    try:
        t0 = time.time()
        r = fn(*a, **kw)
        log.append(f"ok   {name}: {len(r) if hasattr(r, '__len__') else ''} ({time.time() - t0:.1f}s)")
        return r
    except Exception as e:  # 출처 하나가 죽어도 나머지는 계속
        log.append(f"FAIL {name}: {e}")
        return []


BOILERPLATE = re.compile(r"^\s*\[(표|게시판|인사|부고|동정|그래픽|사진|포토|영상|카드뉴스|알림|오늘의 날씨|날씨|증시 마감|마감시황)\]")


def _ts(iso_s: str) -> float:
    try:
        return datetime.fromisoformat(iso_s).timestamp()
    except Exception:
        return 0.0


def run_collect(cfg: Config, store: Store, *, use_news_search: bool = True, verbose: bool = False) -> dict:
    now = now_kst()
    ts = now.isoformat(timespec="minutes")
    log: list[str] = []
    stop = load_stopwords(cfg.stopwords_file)
    W = cfg.weights

    # ---------- 1. 출처 수집 ----------
    gt_kr = _safe(log, "google_trends KR", google_trends.fetch_trends, "KR")
    gt_regions: dict[str, list[dict]] = {}
    for code in (cfg.region_codes or list(REGIONS)):
        gt_regions[code] = _safe(log, f"google_trends {code} {REGIONS.get(code, '')}", google_trends.fetch_trends, code)
        time.sleep(0.2)
    ranking = _safe(log, "naver_ranking", naver.fetch_ranking, now)
    corpus: dict[str, list[Article]] = {c: [] for c in CATEGORIES if c != "전체"}
    for sid, cat in naver.SECTIONS.items():
        for a in _safe(log, f"naver_section {cat}", naver.fetch_section, sid, now):
            corpus[cat].append(Article(a["title"], a["url"], a["press"], a["published"], cat, "naver_section", a["lede"]))
    cutoff = now.timestamp() - 24 * 3600
    for slug, cat in yna.CATS.items():
        for a in _safe(log, f"yna {slug}", yna.fetch_yna, slug):
            if a["published"] and _ts(a["published"]) < cutoff:
                continue
            corpus[cat].append(Article(a["title"], a["url"], a["press"], a["published"], cat, "yna", a["lede"]))
    for topic, cat in google_news.TOPICS.items():
        for a in _safe(log, f"google_news_topic {topic}", google_news.fetch_topic, topic):
            if a["published"] and _ts(a["published"]) < cutoff:
                continue
            corpus[cat].append(Article(a["title"], a["url"], a["press"], a["published"], cat, "google_news_topic"))
        time.sleep(0.2)
    nate_items = _safe(log, "nate", nate.fetch_nate)
    zum_items = _safe(log, "zum", zum.fetch_zum)

    # ---------- 2. 포털 실시간 검색어 → 검색 신호 ----------
    terms: list[SearchTerm] = []
    for it in gt_kr:
        w = 2.0 * (11 - min(it["rank"], 10)) / 10 + (1.0 if it["traffic"] >= 10000 else 0.5 if it["traffic"] >= 2000 else 0.0)
        terms.append(SearchTerm(it["keyword"], query_tokens(it["keyword"]), w, "google", it["rank"], it["traffic"], it["news"]))
    for it in nate_items:
        terms.append(SearchTerm(it["keyword"], query_tokens(it["short"]), 1.0 * (11 - min(it["rank"], 10)) / 10, "nate", it["rank"]))
    for it in zum_items:
        terms.append(SearchTerm(it["keyword"], query_tokens(it["keyword"]), 0.8 * (11 - min(it["rank"], 10)) / 10, "zum", it["rank"]))

    # ---------- 3. 말뭉치 전체로 줄기 사전을 만들고, 제목마다 키워드 집합 계산 ----------
    for cat in corpus:
        corpus[cat] = [a for a in corpus[cat] if not BOILERPLATE.match(a.title)]
    all_articles: list[Article] = [a for arts in corpus.values() for a in arts]
    ranked_by_url: dict[str, list[str]] = {}
    for r in ranking:
        ranked_by_url.setdefault(r["url"], []).append(r["press"])
    corpus_urls = {a.url for a in all_articles}
    rank_articles = [Article(r["title"], r["url"], r["press"], r["published"], "", "naver_ranking") for r in ranking if r["url"] not in corpus_urls]
    everything = all_articles + rank_articles
    press_names = {a.press.lower() for a in everything if a.press} | {p.lower() for ps in ranked_by_url.values() for p in ps}
    stop = stop | {p for p in press_names if len(p) >= 2}
    ex = Extractor([a.title for a in everything], stop)
    kws_by_title: list[set[str]] = []
    for i, a in enumerate(everything):
        kws, ordered = ex.keywords_of(i)
        a.stems = set(ordered)
        kws_by_title.append(kws)
    n_corpus = len(all_articles)

    # 검색어 → 줄기 키워드(최대 3어절)
    term_kw: dict[int, str] = {}
    for ti, t in enumerate(terms):
        stems = [s for s in (ex.stem(x) for x in t.tokens) if s]
        if stems:
            term_kw[ti] = " ".join(stems[:3])

    def signals_for(idx_list: list[int]) -> dict[str, dict]:
        """제목 인덱스 목록(한 카테고리)에 대한 {키워드: 신호}"""
        hits: dict[str, set[int]] = defaultdict(set)
        for i in idx_list:
            for k in kws_by_title[i]:
                hits[k].add(i)
        rows: dict[str, dict] = {}
        for kw, idxs in hits.items():
            if " " in kw and len(idxs) < 2:
                continue
            rows[kw] = {"publish": len(idxs), "search": 0.0, "consume": 0, "src": set(), "term": False, "idx": idxs}
        for ti, kw in term_kw.items():
            if kw not in rows:
                idxs = {i for i in idx_list if stems_match(kw, everything[i].stems)}
                rows[kw] = {"publish": len(idxs), "search": 0.0, "consume": 0, "src": set(), "term": True, "idx": idxs}
        for kw, row in rows.items():
            kt = set(kw.split())
            for ti, t in enumerate(terms):
                tk = set(term_kw.get(ti, "").split())
                tt = set(t.tokens) | tk
                if kw == term_kw.get(ti):
                    frac = 1.0
                elif kt <= tt:                       # 후보가 검색어의 일부: 겹치는 비율만큼
                    frac = len(kt) / max(1, len(tk) or len(tt))
                elif tk and tk <= kt:                # 검색어가 후보의 일부
                    frac = 1.0
                else:
                    continue
                row["search"] += t.weight * frac
                row["src"].add(t.source)
            row["consume"] = sum(1 for a in everything if a.url in ranked_by_url and stems_match(kw, a.stems))
        return rows

    cat_idx = {cat: [i for i, a in enumerate(all_articles) if a.category == cat] for cat in corpus}
    per_cat: dict[str, dict[str, dict]] = {cat: signals_for(idx) for cat, idx in cat_idx.items()}
    per_cat["전체"] = signals_for(list(range(n_corpus)))

    # 급상승 기준선(지난 N일 스냅샷당 평균 기사 수)
    since = (now - timedelta(days=cfg.baseline_days)).strftime("%Y-%m-%d")
    baseline, n_base = store.baseline(since)
    for cat, rows in per_cat.items():
        for kw, r in rows.items():
            b = baseline.get((cat, kw), 0.0)
            ratio = r["publish"] / max(b, 1.0)
            r["spike"] = round(ratio, 2)
            r["spike_norm"] = min(1.0, max(0.0, ratio - 1.0) / (SPIKE_FULL - 1.0))
            r["baseline"] = round(b, 2)

    # 검색어(발행 2건 미만)는 가장 잘 맞는 카테고리 하나에만
    best_cat: dict[str, str] = {}
    for kw in {k for c in per_cat.values() for k, r in c.items() if r["publish"] < 2}:
        cats = [(per_cat[c][kw]["publish"], c) for c in corpus if kw in per_cat[c]]
        if cats:
            best_cat[kw] = max(cats)[1]
    consume_max = max((r["consume"] for rows in per_cat.values() for r in rows.values()), default=0) or 1

    def rank_category(cat: str, rows: dict[str, dict]) -> list[dict]:
        keep = {}
        for kw, r in rows.items():
            if cat != "전체" and r["publish"] < 2:
                if r["publish"] == 0 or best_cat.get(kw) != cat:
                    continue
            if r["publish"] < 2 and r["search"] <= 0:
                continue
            keep[kw] = r
        if not keep:
            return []
        publish_max = max(r["publish"] for r in keep.values()) or 1
        scored = []
        for kw, r in keep.items():
            s = 100 * (W["search"] * min(1.0, r["search"] / SEARCH_FULL)
                       + W["publish"] * r["publish"] / publish_max
                       + W["consume"] * r["consume"] / consume_max
                       + W["spike"] * r["spike_norm"])
            scored.append((round(s, 1), r["publish"], kw, r))
        scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
        out: list[dict] = []
        for s, _, kw, r in scored:
            kt = set(kw.split())
            dup = False
            for o in out:
                ot = set(o["k"].split())
                if kt <= ot or ot <= kt:
                    a, b = r["idx"], o["_idx"]
                    if not a or not b or len(a & b) / max(1, min(len(a), len(b))) >= 0.6:
                        dup = True
                        break
            if dup:
                continue
            out.append({"k": kw, "kd": ex.display(kw), "s": s,
                        "sig": {"search": round(r["search"], 2), "publish": r["publish"], "consume": r["consume"],
                                "spike": r["spike"], "baseline": r["baseline"]},
                        "src": "".join(SOURCE_LABEL[x] for x in sorted(r["src"])), "_idx": r["idx"]})
            if len(out) >= cfg.keep_n:
                break
        for i, o in enumerate(out, 1):
            o["r"] = i
        return out

    prev = store.prev_ranks(ts)
    categories: dict[str, list[dict]] = {}
    for cat in CATEGORIES:
        rows = rank_category(cat, per_cat[cat])
        pr = prev.get(cat, {})
        for o in rows:
            o["d"] = "new" if o["k"] not in pr else pr[o["k"]] - o["r"]
            o.pop("_idx", None)
        categories[cat] = rows
    store.add_daily_counts(ts[:10], [(cat, kw, r["publish"]) for cat, rows in per_cat.items() for kw, r in rows.items() if r["publish"] >= 1])

    # ---------- 4. 키워드별 관련 기사 ----------
    gt_news_by_kw: dict[str, list[dict]] = {}
    for ti, t in enumerate(terms):
        if t.news and ti in term_kw:
            gt_news_by_kw.setdefault(term_kw[ti], []).extend(t.news)
    articles: dict[str, list[dict]] = {}
    need_search: list[str] = []
    for cat, rows in categories.items():
        for o in rows:
            kw = o["k"]
            if kw in articles:
                continue
            found: dict[str, dict] = {}
            for a in everything:
                if stems_match(kw, a.stems):
                    found.setdefault(a.url, a.out())
            kt = set(kw.split())
            for tk, news in gt_news_by_kw.items():
                if kt <= set(tk.split()) or set(tk.split()) <= kt:
                    for n in news:
                        found.setdefault(n["url"], {"t": n["title"], "u": n["url"], "p": n["press"], "d": "", "o": "google_trends"})
            arts = sorted(found.values(), key=lambda a: a["d"], reverse=True)
            articles[kw] = arts[:15]
            if o["r"] <= cfg.top_n and len(arts) < 3:
                need_search.append(kw)
    if use_news_search:
        for kw in need_search[: cfg.news_search_limit]:
            extra = _safe(log, f"google_news '{kw}'", google_news.search_news, ex.display(kw), 8)
            have = {a["u"] for a in articles[kw]}
            for a in extra:
                if a["url"] not in have:
                    articles[kw].append({"t": a["title"], "u": a["url"], "p": a["press"], "d": a["published"], "o": "google_news"})
            articles[kw] = sorted(articles[kw], key=lambda a: a["d"], reverse=True)[:15]
            time.sleep(0.4)

    # ---------- 4b. 스토리(기사 묶음) ----------
    gt_news_urls = {ti: {n["url"] for n in t.news} for ti, t in enumerate(terms) if t.news}
    prev_stories, prev_story_ranks = store.prev_stories(ts)
    story_objs = build_stories(everything, kws_by_title, ex, ranked_by_url, terms, term_kw, gt_news_urls, prev_stories, ts, cfg.story_weights)
    stories: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
    story_articles: dict[str, list[dict]] = {}
    for st in story_objs:
        rep = everything[st.rep]
        row = {"id": st.id, "s": st.score, "label": st.label, "ld": st.label_display, "title": rep.title, "url": rep.url, "press": rep.press,
               "n": st.n_articles, "outlets": st.outlets, "ranked": st.ranked, "search": round(st.search, 2),
               "src": "".join(SOURCE_LABEL[x] for x in sorted(st.sources)), "spike": round(st.spike, 2), "first": st.first_seen,
               "kw": st.keywords, "cat": st.category}
        for cat in dict.fromkeys(("전체", st.category)):
            if cat in stories and len(stories[cat]) < cfg.keep_n:
                stories[cat].append(dict(row))
        seen_u: set[str] = set()
        arts: list[dict] = []
        for i in st.ids:
            a = everything[i]
            if a.url in seen_u:
                continue
            seen_u.add(a.url)
            d = a.out()
            d["rp"] = ranked_by_url.get(a.url, [])
            arts.append(d)
        arts.sort(key=lambda a: (-len(a["rp"]), a["d"]), reverse=False)
        arts.sort(key=lambda a: -len(a["rp"]))
        story_articles[st.id] = arts[:30]
    for cat, rows in stories.items():
        pr = prev_story_ranks.get(cat, {})
        for i, row in enumerate(rows, 1):
            row["r"] = i
            row["d"] = "new" if row["id"] not in pr else pr[row["id"]] - i
    focus = sorted({o["k"] for rows in categories.values() for o in rows})
    related = {kw: rel for kw, rel in related_keywords(everything, focus, stop).items() if rel}
    hop2 = sorted({k for rel in related.values() for k, _ in rel} - set(focus))
    related_more = {kw: rel for kw, rel in related_keywords(everything, hop2, stop).items() if rel}
    related_display = {kw: [[k, ex.display(k), c] for k, c in rel] for kw, rel in related.items()}
    related_more_display = {kw: [[k, ex.display(k), c] for k, c in rel] for kw, rel in related_more.items()}

    # ---------- 5. 지역 ----------
    national = {it["keyword"].lower() for it in gt_kr}
    region_count: Counter[str] = Counter()
    for items in gt_regions.values():
        region_count.update(it["keyword"].lower() for it in items)
    regions = {code: [{"r": it["rank"], "k": it["keyword"], "tr": it["traffic"], "nat": it["keyword"].lower() in national,
                       "n": region_count[it["keyword"].lower()]} for it in items] for code, items in gt_regions.items()}

    portals = {
        "google": [{"r": it["rank"], "k": it["keyword"], "tr": it["traffic"], "since": it["started"]} for it in gt_kr],
        "nate": [{"r": it["rank"], "k": it["keyword"], "chg": it["change"], "delta": it["delta"]} for it in nate_items],
        "zum": [{"r": it["rank"], "k": it["keyword"]} for it in zum_items],
        "naver_ranking": [{"press": r["press"], "r": r["rank"], "t": r["title"], "u": r["url"], "d": r["published"]} for r in ranking],
    }
    meta = {"corpus": {c: len(a) for c, a in corpus.items()}, "ranking_rows": len(ranking), "terms": len(terms),
            "regions": len(gt_regions), "baseline_snapshots": n_base, "stories": len(story_objs),
            "failures": [l for l in log if l.startswith("FAIL")]}
    snap = {"ts": ts, "meta": meta, "categories": categories, "articles": articles, "stories": stories,
            "story_articles": story_articles, "related": related_display, "related_more": related_more_display, "portals": portals,
            "regions": regions, "region_names": REGIONS, "home_press": cfg.home_press, "weights": W,
            "story_weights": cfg.story_weights, "log": log}
    if verbose:
        for l in log:
            print(" ", l)
    return snap
