"""SQLite 저장소 — 스냅샷(수집 시각)별 순위·기사·포털 원본·지역 트렌드."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, ts TEXT UNIQUE, meta TEXT);
CREATE TABLE IF NOT EXISTS ranks(snapshot_id INTEGER, category TEXT, keyword TEXT, rank INTEGER,
    score REAL, search REAL, publish INTEGER, consume INTEGER, sources TEXT, spike REAL DEFAULT 0, display TEXT DEFAULT '',
    PRIMARY KEY(snapshot_id, category, keyword));
CREATE INDEX IF NOT EXISTS ranks_kw ON ranks(keyword, category, snapshot_id);
CREATE TABLE IF NOT EXISTS articles(url TEXT PRIMARY KEY, title TEXT, press TEXT, published TEXT, origin TEXT, first_seen TEXT);
CREATE TABLE IF NOT EXISTS keyword_articles(snapshot_id INTEGER, keyword TEXT, url TEXT, PRIMARY KEY(snapshot_id, keyword, url));
CREATE TABLE IF NOT EXISTS portal_items(snapshot_id INTEGER, source TEXT, rank INTEGER, keyword TEXT, traffic INTEGER, extra TEXT,
    PRIMARY KEY(snapshot_id, source, rank));
CREATE TABLE IF NOT EXISTS ranking_news(snapshot_id INTEGER, press TEXT, rank INTEGER, title TEXT, url TEXT, published TEXT,
    PRIMARY KEY(snapshot_id, press, rank));
CREATE TABLE IF NOT EXISTS stories(snapshot_id INTEGER, story_id TEXT, category TEXT, rank INTEGER, score REAL, label TEXT,
    rep_title TEXT, rep_url TEXT, rep_press TEXT, n_articles INTEGER, outlets INTEGER, search REAL, sources TEXT, spike REAL,
    first_seen TEXT, keywords TEXT, PRIMARY KEY(snapshot_id, category, story_id));
CREATE TABLE IF NOT EXISTS story_articles(snapshot_id INTEGER, story_id TEXT, url TEXT, ranked TEXT, PRIMARY KEY(snapshot_id, story_id, url));
CREATE TABLE IF NOT EXISTS related(snapshot_id INTEGER, keyword TEXT, data TEXT, PRIMARY KEY(snapshot_id, keyword));
CREATE TABLE IF NOT EXISTS daily_counts(date TEXT, category TEXT, keyword TEXT, publish_sum INTEGER, n INTEGER,
    PRIMARY KEY(date, category, keyword));
CREATE TABLE IF NOT EXISTS region_trends(snapshot_id INTEGER, region TEXT, rank INTEGER, keyword TEXT, traffic INTEGER,
    national INTEGER, regions INTEGER, PRIMARY KEY(snapshot_id, region, rank));
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()
        self.conn.executescript(SCHEMA)

    def _migrate(self) -> None:
        """예전 stories 표(기본키에 category 없음)는 지우고 다시 만든다 — 스토리 이력만 잃고 나머지는 그대로."""
        row = self.conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='stories'").fetchone()
        if row and "PRIMARY KEY(snapshot_id, category, story_id)" not in row["sql"]:
            with self.conn:
                self.conn.execute("DROP TABLE stories")
                self.conn.execute("DROP TABLE IF EXISTS story_articles")

    # ---- 읽기 ----
    def prev_ranks(self, before_ts: str) -> dict[str, dict[str, int]]:
        """직전 스냅샷의 {category: {keyword: rank}} (변동 표시용)"""
        row = self.conn.execute("SELECT id FROM snapshots WHERE ts < ? ORDER BY ts DESC LIMIT 1", (before_ts,)).fetchone()
        if not row:
            return {}
        out: dict[str, dict[str, int]] = {}
        for r in self.conn.execute("SELECT category, keyword, rank FROM ranks WHERE snapshot_id=?", (row["id"],)):
            out.setdefault(r["category"], {})[r["keyword"]] = r["rank"]
        return out

    def baseline(self, since_date: str) -> tuple[dict[tuple[str, str], float], int]:
        """지난 N일 (category, keyword)별 스냅샷당 평균 기사 수 + 그 기간 스냅샷 수"""
        n = self.conn.execute("SELECT COUNT(*) FROM snapshots WHERE substr(ts,1,10) >= ?", (since_date,)).fetchone()[0]
        if not n:
            return {}, 0
        out = {}
        for r in self.conn.execute("SELECT category, keyword, SUM(publish_sum) FROM daily_counts WHERE date >= ? GROUP BY 1,2", (since_date,)):
            out[(r[0], r[1])] = r[2] / n
        return out, n

    def add_daily_counts(self, date: str, rows: list[tuple[str, str, int]]) -> None:
        with self.conn:
            self.conn.executemany(
                "INSERT INTO daily_counts(date, category, keyword, publish_sum, n) VALUES(?,?,?,?,1) "
                "ON CONFLICT(date, category, keyword) DO UPDATE SET publish_sum=publish_sum+excluded.publish_sum, n=n+1",
                [(date, c, k, p) for c, k, p in rows])

    def prev_stories(self, before_ts: str) -> tuple[list[dict], dict[str, dict[str, int]]]:
        """직전 스냅샷의 스토리(id, urls, label, n, first_seen) + {category: {story_id: rank}}"""
        row = self.conn.execute("SELECT id FROM snapshots WHERE ts < ? ORDER BY ts DESC LIMIT 1", (before_ts,)).fetchone()
        if not row:
            return [], {}
        urls: dict[str, set[str]] = {}
        for r in self.conn.execute("SELECT story_id, url FROM story_articles WHERE snapshot_id=?", (row["id"],)):
            urls.setdefault(r["story_id"], set()).add(r["url"])
        out, ranks, seen = [], {}, set()
        for r in self.conn.execute("SELECT * FROM stories WHERE snapshot_id=?", (row["id"],)):
            ranks.setdefault(r["category"], {})[r["story_id"]] = r["rank"]
            if r["story_id"] in seen:
                continue
            seen.add(r["story_id"])
            out.append({"id": r["story_id"], "urls": urls.get(r["story_id"], set()), "label": json.loads(r["label"]),
                        "n": r["n_articles"], "first_seen": r["first_seen"]})
        return out, ranks

    def stories_for(self, snapshot_id: int, keep_n: int) -> dict[str, list[sqlite3.Row]]:
        out: dict[str, list] = {}
        for r in self.conn.execute("SELECT * FROM stories WHERE snapshot_id=? AND rank<=? ORDER BY category, rank", (snapshot_id, keep_n)):
            out.setdefault(r["category"], []).append(r)
        return out

    def story_articles_for_day(self, snapshot_ids: list[int], cap: int = 30) -> dict[str, list[dict]]:
        if not snapshot_ids:
            return {}
        q = ",".join("?" * len(snapshot_ids))
        out: dict[str, dict[str, dict]] = {}
        for r in self.conn.execute(
            f"SELECT sa.story_id, sa.ranked, a.url, a.title, a.press, a.published, a.origin FROM story_articles sa "
            f"JOIN articles a ON a.url=sa.url WHERE sa.snapshot_id IN ({q})", snapshot_ids):
            out.setdefault(r["story_id"], {})[r["url"]] = {"t": r["title"], "u": r["url"], "p": r["press"], "d": r["published"], "o": r["origin"],
                                                           "rp": json.loads(r["ranked"]) if r["ranked"] else []}
        return {k: sorted(v.values(), key=lambda a: (-len(a["rp"]), a["d"]), reverse=False)[:cap] for k, v in out.items()}

    def related_for(self, snapshot_id: int) -> dict[str, list]:
        return {r["keyword"]: json.loads(r["data"]) for r in self.conn.execute("SELECT keyword, data FROM related WHERE snapshot_id=?", (snapshot_id,))}

    def snapshot_dates(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT DISTINCT substr(ts,1,10) FROM snapshots ORDER BY 1")]

    def snapshots_on(self, date: str) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT id, ts, meta FROM snapshots WHERE substr(ts,1,10)=? ORDER BY ts", (date,)).fetchall()

    def latest_snapshot(self) -> sqlite3.Row | None:
        return self.conn.execute("SELECT id, ts, meta FROM snapshots ORDER BY ts DESC LIMIT 1").fetchone()

    def ranks_for(self, snapshot_id: int, keep_n: int) -> dict[str, list[sqlite3.Row]]:
        out: dict[str, list] = {}
        for r in self.conn.execute("SELECT * FROM ranks WHERE snapshot_id=? AND rank<=? ORDER BY category, rank", (snapshot_id, keep_n)):
            out.setdefault(r["category"], []).append(r)
        return out

    def articles_for_day(self, snapshot_ids: list[int], cap: int = 20) -> dict[str, list[dict]]:
        if not snapshot_ids:
            return {}
        q = ",".join("?" * len(snapshot_ids))
        out: dict[str, dict[str, dict]] = {}
        for r in self.conn.execute(
            f"SELECT ka.keyword, a.url, a.title, a.press, a.published, a.origin FROM keyword_articles ka "
            f"JOIN articles a ON a.url=ka.url WHERE ka.snapshot_id IN ({q})", snapshot_ids):
            out.setdefault(r["keyword"], {})[r["url"]] = {"t": r["title"], "u": r["url"], "p": r["press"], "d": r["published"], "o": r["origin"]}
        return {k: sorted(v.values(), key=lambda a: a["d"], reverse=True)[:cap] for k, v in out.items()}

    def portal_items(self, snapshot_id: int) -> dict[str, list[dict]]:
        out: dict[str, list] = {}
        for r in self.conn.execute("SELECT * FROM portal_items WHERE snapshot_id=? ORDER BY source, rank", (snapshot_id,)):
            out.setdefault(r["source"], []).append({"r": r["rank"], "k": r["keyword"], "tr": r["traffic"], **(json.loads(r["extra"]) if r["extra"] else {})})
        return out

    def regions(self, snapshot_id: int) -> dict[str, list[dict]]:
        out: dict[str, list] = {}
        for r in self.conn.execute("SELECT * FROM region_trends WHERE snapshot_id=? ORDER BY region, rank", (snapshot_id,)):
            out.setdefault(r["region"], []).append({"r": r["rank"], "k": r["keyword"], "tr": r["traffic"], "nat": bool(r["national"]), "n": r["regions"]})
        return out

    def ranking_news(self, snapshot_id: int, home_press: str, all_rows: bool) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM ranking_news WHERE snapshot_id=? ORDER BY press, rank", (snapshot_id,)).fetchall()
        out = []
        for r in rows:
            if all_rows or r["press"] == home_press or r["rank"] == 1:
                out.append({"press": r["press"], "r": r["rank"], "t": r["title"], "u": r["url"], "d": r["published"]})
        return out

    def series(self, keyword: str, category: str, since_ts: str) -> list[tuple[str, float, int]]:
        return [(r["ts"], r["score"], r["rank"]) for r in self.conn.execute(
            "SELECT s.ts, r.score, r.rank FROM ranks r JOIN snapshots s ON s.id=r.snapshot_id "
            "WHERE r.keyword=? AND r.category=? AND s.ts>=? ORDER BY s.ts", (keyword, category, since_ts))]

    # ---- 쓰기 ----
    def save_snapshot(self, snap: dict) -> int:
        c = self.conn
        with c:
            cur = c.execute("INSERT OR REPLACE INTO snapshots(ts, meta) VALUES(?,?)", (snap["ts"], json.dumps(snap["meta"], ensure_ascii=False)))
            sid = cur.lastrowid
            for t in ("ranks", "keyword_articles", "portal_items", "ranking_news", "region_trends", "stories", "story_articles", "related"):
                c.execute(f"DELETE FROM {t} WHERE snapshot_id=?", (sid,))
            for cat, rows in snap["categories"].items():
                c.executemany("INSERT INTO ranks VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                              [(sid, cat, r["k"], r["r"], r["s"], r["sig"]["search"], r["sig"]["publish"], r["sig"]["consume"], r["src"],
                                r["sig"].get("spike", 0), r.get("kd", r["k"])) for r in rows])
            for kw, arts in snap["articles"].items():
                for a in arts:
                    c.execute("INSERT INTO articles VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title, press=excluded.press, published=excluded.published", (a["u"], a["t"], a["p"], a["d"], a["o"], snap["ts"]))
                    c.execute("INSERT OR IGNORE INTO keyword_articles VALUES(?,?,?)", (sid, kw, a["u"]))
            for src, items in snap["portals"].items():
                if src == "naver_ranking":
                    continue
                c.executemany("INSERT OR REPLACE INTO portal_items VALUES(?,?,?,?,?,?)",
                              [(sid, src, it["r"], it["k"], it.get("tr", 0), json.dumps({k: v for k, v in it.items() if k not in ("r", "k", "tr")}, ensure_ascii=False)) for it in items])
            c.executemany("INSERT OR REPLACE INTO ranking_news VALUES(?,?,?,?,?,?)",
                          [(sid, it["press"], it["r"], it["t"], it["u"], it["d"]) for it in snap["portals"].get("naver_ranking", [])])
            for cat, rows in snap.get("stories", {}).items():
                c.executemany("INSERT OR REPLACE INTO stories VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              [(sid, r["id"], cat, r["r"], r["s"], json.dumps(r["label"], ensure_ascii=False), r["title"], r["url"], r["press"],
                                r["n"], r["outlets"], r["search"], r["src"], r["spike"], r["first"], json.dumps(r["kw"], ensure_ascii=False)) for r in rows])
            for stid, arts in snap.get("story_articles", {}).items():
                for a in arts:
                    c.execute("INSERT INTO articles VALUES(?,?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title, press=excluded.press, published=excluded.published", (a["u"], a["t"], a["p"], a["d"], a["o"], snap["ts"]))
                    c.execute("INSERT OR IGNORE INTO story_articles VALUES(?,?,?,?)", (sid, stid, a["u"], json.dumps(a.get("rp", []), ensure_ascii=False)))
            c.executemany("INSERT OR REPLACE INTO related VALUES(?,?,?)",
                          [(sid, kw, json.dumps(rel, ensure_ascii=False)) for kw, rel in snap.get("related", {}).items()])
            for code, items in snap["regions"].items():
                c.executemany("INSERT OR REPLACE INTO region_trends VALUES(?,?,?,?,?,?,?)",
                              [(sid, code, it["r"], it["k"], it.get("tr", 0), int(it["nat"]), it["n"]) for it in items])
        return sid
