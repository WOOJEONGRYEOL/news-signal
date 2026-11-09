"""회차를 건너 같은 사건을 잇는 '흐름 번호(tid)'.

흐름 그래프는 회차마다 같은 사건의 점수를 찾아 이어 그린다. 예전에는 그 연결 키로 이슈 앵커(핵심어)나
스토리 id 를 썼는데, 둘 다 회차마다 쉽게 바뀌었다.
  · 앵커가 바뀜: 같은 '젠슨 황 불륜' 이슈가 18:16 엔 '젠슨', 18:43 엔 'ai' 로 묶임
  · id 가 끊김: 한 회차라도 순위 밖으로 밀리면 다음 회차에 새 id 를 받음(김종인 발언 기사 4건이 오후에 id 3개)
그래서 순위가 높은데도 그래프가 '내내 0'으로 나오는 일이 잦았다(2026-11-09 확인: 회차마다 절반가량이 새 id).

여기서는 최근 몇 회차에 나온 이슈들과 **기사 URL 이 얼마나 겹치는지**로 같은 사건을 찾아 흐름 번호를 물려준다.
같은 스토리 id 가 남아 있으면 그것을 먼저 믿는다. 직전 회차 정보는 데이터베이스가 아니라 이미 공개된
site/data(날짜별 파일 + 기사 파일)에서 읽는다 — 클라우드 데이터베이스는 최근 3회차만 남기고 줄이기 때문이고,
지난 기록을 소급해 채운 값(scripts/backfill_threads.py)과도 같은 기준이 되게 하려는 것이다.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

LOOKBACK = 12       # 최근 몇 회차까지 거슬러 찾을지(약 5시간 반 — 밤사이 순위 밖으로 빠졌다 돌아와도 잇게)
MIN_SHARED = 2      # 겹치는 기사가 이만큼은 돼야
MIN_RATIO = 0.3     # 둘 중 작은 쪽 기사의 30% 이상이 겹쳐야 같은 사건


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _subs(v) -> list:
    if isinstance(v, str):
        try:
            v = json.loads(v or "[]")
        except ValueError:
            return []
    return v if isinstance(v, list) else []


def new_tid(lead_id: str) -> str:
    return "t" + (lead_id[1:] if lead_id.startswith("s") else lead_id)


def row_tid(r: list) -> str:
    """날짜별 파일의 스토리 줄에서 흐름 번호. 소급 이전 줄은 예전 키(이슈 앵커 또는 스토리 id)."""
    if len(r) > 16 and r[16]:
        return r[16]
    return (r[14] if len(r) > 14 and r[14] else "") or r[0]


class Threads:
    """최근 회차들의 흐름(tid → 기사 URL·스토리 id·처음 본 시각)과 직전 회차 순위."""

    def __init__(self):
        self.recent: list[tuple[str, dict, dict]] = []   # (ts, {tid: info}, {category: {tid: rank}})

    def feed_rows(self, ts: str, stories: dict, story_articles: dict) -> None:
        """날짜별 파일의 한 회차(stories: {category: [row…]})를 기억에 넣는다."""
        info: dict[str, dict] = {}
        ranks: dict[str, dict[str, int]] = {}
        for cat, rows in (stories or {}).items():
            for r in rows:
                tid = row_tid(r)
                ranks.setdefault(cat, {})[tid] = r[1]
                d = info.setdefault(tid, {"urls": set(), "ids": set(), "anc": set(), "first": r[12] if len(r) > 12 else ts})
                d["ids"].add(r[0])
                if len(r) > 14 and r[14] and not r[14].startswith("s:"):
                    d["anc"].add(r[14])
                d["urls"].update(a["u"] for a in story_articles.get(r[0], []) if isinstance(a, dict) and a.get("u"))
                if len(r) > 12 and r[12] and r[12] < d["first"]:
                    d["first"] = r[12]
                d["n"] = max(d.get("n", 0), r[7] if len(r) > 7 and isinstance(r[7], int) else 0)
        self.recent.append((ts, info, ranks))
        self.recent = self.recent[-LOOKBACK:]

    def prev_rank(self, cat: str, tid: str):
        """바로 앞 회차 그 분야에서의 순위(없으면 None). 앞 회차가 아예 없으면 False."""
        if not self.recent:
            return False
        return self.recent[-1][2].get(cat, {}).get(tid)

    def prev_size(self, tid: str):
        """이 흐름이 가장 최근에 보였던 회차의 기사 수(없으면 None)."""
        for _, info, _ in reversed(self.recent):
            if tid in info and info[tid].get("n"):
                return info[tid]["n"]
        return None

    def first_seen(self, tid: str):
        firsts = [info[tid]["first"] for _, info, _ in self.recent if tid in info and info[tid]["first"]]
        return min(firsts) if firsts else None

    def assign(self, issues: list[dict]) -> dict[str, str]:
        """issues: [{"id": 대표 스토리 id, "anc": 이슈 핵심어, "urls": {기사 URL…}}] → {대표 id: tid}

        이어 붙이는 근거(강한 순): ① 대표 스토리 id 가 그대로 이어짐 ② 기사가 2건 이상·30% 이상 겹침
        ③ 핵심어가 같고 기사가 1건이라도 겹침. 이슈가 다른 갈래를 흡수했을 때 그 갈래의 옛 번호를 가져가지
        않도록 구성 스토리 id 는 근거로 쓰지 않는다."""
        known: dict[str, dict] = {}
        for _, info, _ in self.recent:        # 오래된 회차부터 — 같은 흐름은 가장 최근 모습이 남는다
            for tid, d in info.items():
                prev = known.get(tid)
                known[tid] = {"urls": d["urls"], "ids": d["ids"] | (prev["ids"] if prev else set()),
                              "anc": d["anc"] | (prev["anc"] if prev else set())}
        by_url: dict[str, set[str]] = defaultdict(set)
        by_id: dict[str, str] = {}
        for tid, d in known.items():
            for u in d["urls"]:
                by_url[u].add(tid)
            for sid in d["ids"]:
                by_id[sid] = tid
        cands = []
        for it in issues:
            if it["id"] in by_id:                 # 대표 스토리 id 가 이어졌으면 그쪽이 가장 확실
                cands.append((10 ** 6, it["id"], by_id[it["id"]]))
            shared: dict[str, int] = defaultdict(int)
            for u in it["urls"]:
                for tid in by_url.get(u, ()):
                    shared[tid] += 1
            for tid, n in shared.items():
                small = min(len(it["urls"]), len(known[tid]["urls"])) or 1
                if n >= MIN_SHARED and n / small >= MIN_RATIO:
                    cands.append((n, it["id"], tid))
                elif it.get("anc") and it["anc"] in known[tid]["anc"]:
                    cands.append((1.5, it["id"], tid))
        cands.sort(key=lambda c: -c[0])
        out: dict[str, str] = {}
        taken: set[str] = set()
        for _, lead, tid in cands:
            if lead in out or tid in taken:
                continue
            out[lead] = tid
            taken.add(tid)
        for it in issues:
            out.setdefault(it["id"], new_tid(it["id"]))
        return out


def from_files(data_dir: Path, before_ts: str) -> Threads:
    """공개된 site/data 에서 before_ts 직전 LOOKBACK 회차를 읽어 Threads 를 만든다(자정을 넘겨도 되게 전날 포함)."""
    d0 = date.fromisoformat(before_ts[:10])
    snaps = []
    for d in (d0 - timedelta(days=1), d0):
        day = _read(data_dir / "days" / f"{d.isoformat()}.json")
        if not isinstance(day, dict):
            continue
        sa = (_read(data_dir / "articles" / f"{d.isoformat()}.json") or {}).get("story_articles", {})
        for s in day.get("snapshots", []):
            if isinstance(s, dict) and s.get("ts", "") < before_ts:
                snaps.append((s, sa))
    snaps.sort(key=lambda x: x[0]["ts"])
    T = Threads()
    for s, sa in snaps[-LOOKBACK:]:
        T.feed_rows(s["ts"], s.get("stories") or {}, sa)
    return T
