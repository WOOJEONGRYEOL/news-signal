"""DB → site/data/*.json (대시보드가 fetch로 읽는 정적 파일)."""
from __future__ import annotations

import json
from pathlib import Path

from . import __version__, now_kst
from .config import Config
from .sources.google_trends import REGIONS
from .store import Store


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
                      r["outlets"], r["search"], r["sources"], r["spike"], r["first_seen"], r["keywords"]] for r in rows]
               for cat, rows in store.stories_for(s["id"], cfg.keep_n).items()}
        day["snapshots"].append({"ts": s["ts"], "cats": cats, "stories": sts})
        extras["snapshots"].append({"ts": s["ts"], "portals": store.portal_items(s["id"]), "regions": store.regions(s["id"]),
                                    "naver_ranking": store.ranking_news(s["id"], cfg.home_press, all_rows=False),
                                    "related": store.related_for(s["id"])})
    _write(cfg.site_dir / "data" / "days" / f"{date}.json", day)
    _write(cfg.site_dir / "data" / "extras" / f"{date}.json", extras)
    _write(cfg.site_dir / "data" / "articles" / f"{date}.json", {"date": date, "articles": store.articles_for_day(ids),
                                                                  "story_articles": store.story_articles_for_day(ids)})


def export_manifest(cfg: Config, store: Store) -> None:
    latest = store.latest_snapshot()
    days = {d: [s["ts"] for s in store.snapshots_on(d)] for d in store.snapshot_dates()}
    _write(cfg.site_dir / "data" / "manifest.json", {
        "generated": now_kst().isoformat(timespec="minutes"),
        "latest": latest["ts"] if latest else None,
        "days": days,
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
