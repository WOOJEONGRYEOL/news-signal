"""기사를 '스토리(같은 사건을 다룬 기사 묶음)'로 묶는다 — stdlib only.

원리: 제목마다 변별력 있는 키워드(너무 흔하지도, 한 번만 나오지도 않는 말)를 idf 가중 벡터로 만들고,
중심(centroid)과의 코사인 유사도로 묶는다. 중심과 비교하기 때문에 '경찰'처럼 여러 사건에 걸친 한 단어로
사건들이 줄줄이 이어 붙는(chaining) 문제가 덜하다. 두 번 훑어 안정시키고, 너무 비슷한 묶음은 합친다.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass, field

MIN_ARTICLES = 2      # 이만큼 못 모으면 스토리로 안 침
SIM_TH = 0.30         # 묶음에 넣는 최소 유사도
MERGE_TH = 0.55       # 묶음끼리 합치는 유사도
MAX_DF_RATIO = 0.12   # 전체 기사의 이 비율보다 많이 나오는 말은 묶는 근거로 안 씀(AI, 대통령 …)


@dataclass
class Story:
    id: str
    ids: list[int]                       # everything 인덱스
    label: list[str] = field(default_factory=list)   # 줄기 키워드 2~3개
    label_display: str = ""
    rep: int = -1                        # 대표 기사 인덱스
    category: str = "전체"
    n_articles: int = 0
    outlets: int = 0
    ranked: int = 0                      # 많이 본 기사에 오른 회원 기사 수
    search: float = 0.0
    sources: set[str] = field(default_factory=set)
    keywords: list[tuple[str, int]] = field(default_factory=list)  # (표시 키워드, 기사 수)
    vocab: set[str] = field(default_factory=set)
    urls: set[str] = field(default_factory=set)
    first_seen: str = ""
    prev_n: int | None = None
    spike: float = 0.0
    score: float = 0.0


def _cos(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    dot = 0.0
    for k, v in a.items():
        w = b.get(k)
        if w:
            dot += v * w
    if not dot:
        return 0.0
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def _cluster(vecs: list[dict], order: list[int]) -> list[list[int]]:
    clusters: list[dict] = []
    assign = [-1] * len(vecs)

    def best_for(i: int) -> tuple[int, float]:
        v = vecs[i]
        best, bs = -1, 0.0
        if not v:
            return best, bs
        for ci, c in enumerate(clusters):
            if not c["ids"]:
                continue
            shared = [k for k in v if k in c["sum"]]
            if len(shared) < 2 and not any(" " in k for k in shared):
                continue
            s = _cos(v, c["sum"])
            if s > bs:
                best, bs = ci, s
        return best, bs

    for i in order:                                   # 1차: 리더 방식
        ci, s = best_for(i)
        if ci >= 0 and s >= SIM_TH:
            clusters[ci]["ids"].append(i)
            clusters[ci]["sum"].update(vecs[i])
            assign[i] = ci
        else:
            clusters.append({"ids": [i], "sum": Counter(vecs[i])})
            assign[i] = len(clusters) - 1
    moved = {}                                        # 2차: 중심이 잡힌 뒤 더 맞는 묶음으로 옮김
    for i in order:
        ci, s = best_for(i)
        if ci >= 0 and s >= SIM_TH and ci != assign[i]:
            moved[i] = ci
    for i, ci in moved.items():
        old = clusters[assign[i]]
        old["ids"].remove(i)
        old["sum"].subtract(vecs[i])
        clusters[ci]["ids"].append(i)
        clusters[ci]["sum"].update(vecs[i])
        assign[i] = ci
    live = [c for c in clusters if c["ids"]]          # 3차: 아주 비슷한 묶음끼리 합침
    live.sort(key=lambda c: -len(c["ids"]))
    merged: list[dict] = []
    for c in live:
        for m in merged:
            if _cos(c["sum"], m["sum"]) >= MERGE_TH:
                m["ids"].extend(c["ids"])
                m["sum"].update(c["sum"])
                break
        else:
            merged.append(c)
    return [c["ids"] for c in merged]


def build_stories(everything, kws_by_title, ex, ranked_by_url, terms, term_kw, gt_news_urls, prev_stories, ts, story_weights):
    """everything: Article 목록(stems·category·url·title·press·published 보유). 반환: (stories, vocab_df)"""
    N = len(everything)
    df: Counter[str] = Counter(k for s in kws_by_title for k in s)
    max_df = max(3, int(N * MAX_DF_RATIO))
    idf = {k: math.log(N / d) for k, d in df.items()}
    vecs = [{k: idf[k] for k in s if 2 <= df[k] <= max_df} for s in kws_by_title]
    order = sorted(range(N), key=lambda i: (-len(ranked_by_url.get(everything[i].url, ())), -len(vecs[i])))
    groups = [g for g in _cluster(vecs, order) if len({everything[i].url for i in g}) >= MIN_ARTICLES]

    stories: list[Story] = []
    for g in groups:
        st = Story(id="", ids=g)
        st.urls = {everything[i].url for i in g}
        st.n_articles = len(st.urls)
        cnt: Counter[str] = Counter()
        for i in g:
            cnt.update(k for k in kws_by_title[i])
        n = len(g)
        # 라벨: 묶음 안에서 자주(30% 이상) 나오는 변별력 있는 말 2~3개. 부분 겹침은 하나만.
        scored = sorted(((c * (1 + idf.get(k, 0)), k) for k, c in cnt.items() if c >= max(2, n * 0.3) and df[k] <= max_df * 2), reverse=True)
        label: list[str] = []
        for _, k in scored:
            kt = set(k.split())
            if any(kt <= set(l.split()) or set(l.split()) <= kt for l in label):
                continue
            label.append(k)
            if len(label) == 3:
                break
        if not label or (len(label) == 1 and len({everything[i].url for i in g}) < 4):   # 변별력 있는 공통어가 없으면 스토리가 아님
            continue
        st.label = label
        st.label_display = " · ".join(ex.display(k) for k in label)
        st.vocab = {k for k, c in cnt.items() if c >= 2} | set(label)
        st.keywords = [(ex.display(k), c) for k, c in cnt.most_common(30) if c >= 2 and " " not in k][:8]
        # 대표 기사: 중심에 가깝고, 많이 본 기사면 우선, 너무 긴 제목은 뒤로
        cent = Counter()
        for i in g:
            cent.update(vecs[i])
        def rep_key(i):
            a = everything[i]
            return (_cos(vecs[i], cent) + (0.4 if ranked_by_url.get(a.url) else 0) + (0.1 if len(a.title) <= 45 else 0), a.published)
        st.rep = max(g, key=rep_key)
        # 지표
        presses = set()
        for u in st.urls:
            presses.update(ranked_by_url.get(u, ()))
        st.outlets = len(presses)
        st.ranked = sum(1 for u in st.urls if ranked_by_url.get(u))
        cats: Counter[str] = Counter()
        for i in g:
            a = everything[i]
            if a.category:
                cats[a.category] += 0.5 if a.origin == "google_news_topic" else 1.0
        st.category = cats.most_common(1)[0][0] if cats else "전체"
        for ti, t in enumerate(terms):
            stems = term_kw.get(ti, "").split()
            hit = 0.0
            if stems:
                cov = sum(1 for s in stems if s in st.vocab or any(v.startswith(s) for v in st.vocab if len(s) >= 3)) / len(stems)
                if cov >= 0.5:
                    hit = cov
            if gt_news_urls.get(ti) and (gt_news_urls[ti] & st.urls):
                hit = 1.0
            if hit:
                st.search += t.weight * hit
                st.sources.add(t.source)
        stories.append(st)

    # 직전 스냅샷의 스토리와 이어 붙이기(같은 기사 URL이 겹치면 같은 스토리)
    used = set()
    cands = []
    for st in stories:
        for p in prev_stories:
            shared = len(st.urls & p["urls"])
            if shared >= 2 and shared / min(len(st.urls), len(p["urls"])) >= 0.3:
                cands.append((shared, st, p))
            elif len(set(st.label) & set(p["label"])) >= 2:
                cands.append((1, st, p))
    cands.sort(key=lambda x: -x[0])
    for _, st, p in cands:
        if st.id or p["id"] in used:
            continue
        st.id, st.first_seen, st.prev_n = p["id"], p["first_seen"], p["n"]
        used.add(p["id"])
    for st in stories:
        if not st.id:
            h = hashlib.sha1(("|".join(sorted(st.urls)[:5]) + ts).encode()).hexdigest()[:6]
            st.id = f"s{ts[5:16].replace('-', '').replace(':', '').replace('T', '-')}-{h}"
            st.first_seen = ts
    # 급상승: 처음 등장 후 3시간 동안 서서히 식는 '새 스토리' 점수와, 직전 대비 기사 증가율 중 큰 값
    from datetime import datetime
    now_dt = datetime.fromisoformat(ts)
    for st in stories:
        try:
            hours = (now_dt - datetime.fromisoformat(st.first_seen)).total_seconds() / 3600
        except Exception:
            hours = 0.0
        novelty = max(0.0, 1.0 - hours / 3.0) * (1.0 if st.n_articles >= 3 else 0.5)
        growth = 0.0 if st.prev_n is None else min(1.0, max(0.0, st.n_articles / max(1, st.prev_n) - 1.0) / 2.0)
        st.spike = round(max(novelty, growth), 2)
    W = story_weights
    n_max = max((s.n_articles for s in stories), default=1) or 1
    o_max = max((s.outlets for s in stories), default=1) or 1
    for st in stories:
        st.score = round(100 * (W["consume"] * st.outlets / o_max + W["publish"] * st.n_articles / n_max
                                + W["search"] * min(1.0, st.search / 2.5) + W["spike"] * st.spike), 1)
    stories.sort(key=lambda s: (-s.score, -s.outlets, -s.n_articles))
    return stories


def related_keywords(everything, focus: list[str], stop: set[str], top: int = 10) -> dict[str, list[tuple[str, int]]]:
    """키워드별 연관어(같은 제목에 함께 나온 말) — 연관어 지도용"""
    out: dict[str, list[tuple[str, int]]] = {}
    stems_list = [a.stems for a in everything]
    for kw in focus:
        parts = kw.split()
        co: Counter[str] = Counter()
        for st in stems_list:
            if all(p in st for p in parts):
                co.update(s for s in st if s not in parts and s not in stop and len(s) >= 2)
        out[kw] = [(k, c) for k, c in co.most_common(top * 2) if c >= 2][:top]
    return out
