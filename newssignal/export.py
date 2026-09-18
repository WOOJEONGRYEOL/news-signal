"""DB → site/data/*.json (대시보드가 fetch로 읽는 정적 파일)."""
from __future__ import annotations

import json
from pathlib import Path

from . import __version__, now_kst
from .config import Config
from .sources.google_trends import REGIONS
from .store import Store


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _merge_day(path: Path, fresh: dict) -> dict:
    """이미 쌓인 시각을 지우지 않고 합친다.

    수집이 두 곳(맥·클라우드)에서 돌 수 있고 각자 데이터베이스가 다르다. 파일을 통째로 덮어쓰면
    상대가 기록한 시각이 사라져 흐름 그래프에 구멍이 난다. 같은 시각은 새 값이 이긴다.
    """
    old = _read(path)
    if not isinstance(old, dict) or not isinstance(old.get("snapshots"), list):
        return fresh
    by_ts = {s.get("ts"): s for s in old["snapshots"] if isinstance(s, dict)}
    by_ts.update({s["ts"]: s for s in fresh["snapshots"]})
    fresh["snapshots"] = [by_ts[t] for t in sorted(by_ts)]
    return fresh


def _merge_articles(path: Path, fresh: dict) -> dict:
    old = _read(path)
    if not isinstance(old, dict):
        return fresh
    for key in ("articles", "story_articles"):
        merged = dict(old.get(key) or {})
        merged.update(fresh.get(key) or {})
        fresh[key] = merged
    return fresh


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def export_latest(cfg: Config, snap: dict) -> None:
    data = {k: v for k, v in snap.items() if k != "log"}
    data["related"] = {**snap.get("related_more", {}), **snap.get("related", {})}
    data.pop("related_more", None)
    data["version"] = __version__
    _write(cfg.site_dir / "data" / "latest.json", data)


def export_day(cfg: Config, store: Store, date: str) -> None:
    snaps = store.snapshots_on(date)
    day = {"date": date, "snapshots": []}
    extras = {"date": date, "snapshots": []}
    ids = []
    for s in snaps:
        ids.append(s["id"])
        cats = {cat: [[r["keyword"], r["rank"], r["score"], r["search"], r["publish"], r["consume"], r["sources"], r["spike"], r["display"]] for r in rows]
                for cat, rows in store.ranks_for(s["id"], cfg.keep_n).items()}
        sts = {cat: [[r["story_id"], r["rank"], r["score"], r["label"], r["rep_title"], r["rep_url"], r["rep_press"], r["n_articles"],
                      r["outlets"], r["search"], r["sources"], r["spike"], r["first_seen"], r["keywords"], r["issue"], r["subs"]] for r in rows]
               for cat, rows in store.stories_for(s["id"], cfg.keep_n).items()}
        day["snapshots"].append({"ts": s["ts"], "cats": cats, "stories": sts})
        extras["snapshots"].append({"ts": s["ts"], "portals": store.portal_items(s["id"]), "regions": store.regions(s["id"]),
                                    "naver_ranking": store.ranking_news(s["id"], cfg.home_press, all_rows=False),
                                    "related": store.related_for(s["id"])})
    day_path = cfg.site_dir / "data" / "days" / f"{date}.json"
    extras_path = cfg.site_dir / "data" / "extras" / f"{date}.json"
    arts_path = cfg.site_dir / "data" / "articles" / f"{date}.json"
    _write(day_path, _merge_day(day_path, day))
    _write(extras_path, _merge_day(extras_path, extras))
    _write(arts_path, _merge_articles(arts_path, {"date": date, "articles": store.articles_for_day(ids),
                                                  "story_articles": store.story_articles_for_day(ids)}))


def export_manifest(cfg: Config, store: Store) -> None:
    """시각 목록은 이미 올라가 있는 manifest 와 합친다.

    클라우드는 데이터베이스를 최근 몇 회차만 남기고 줄이므로(compact) DB 만 보고 쓰면 지난 날짜가
    시점 목록에서 사라지고, 맥과 클라우드가 서로 기록한 시각을 지우게 된다.
    """
    path = cfg.site_dir / "data" / "manifest.json"
    old = _read(path)
    old = old if isinstance(old, dict) else {}
    days = {d: set(v) for d, v in (old.get("days") or {}).items() if isinstance(v, list)}
    for d in store.snapshot_dates():
        days.setdefault(d, set()).update(s["ts"] for s in store.snapshots_on(d))
    latest = store.latest_snapshot()
    latest_ts = max(filter(None, (latest["ts"] if latest else None, old.get("latest"))), default=None)
    _write(path, {
        "generated": now_kst().isoformat(timespec="minutes"),
        "latest": latest_ts,
        "days": {d: sorted(days[d]) for d in sorted(days)},
        "home_press": cfg.home_press,
        "weights": cfg.weights,
        "story_weights": cfg.story_weights,
        "top_n": cfg.top_n,
        "keep_n": cfg.keep_n,
        "region_names": REGIONS,
        "version": __version__,
    })


def export_all(cfg: Config, store: Store, *, dates: list[str] | None = None) -> None:
    for d in (dates or store.snapshot_dates()):
        export_day(cfg, store, d)
    export_manifest(cfg, store)
