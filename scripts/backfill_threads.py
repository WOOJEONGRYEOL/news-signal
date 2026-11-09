"""이미 공개된 날짜별 파일(site/data/days)에 흐름 번호(tid)를 소급해 채운다.

수집기는 2026-11-09 부터 회차마다 흐름 번호를 매기지만(newssignal/threads.py), 그 전 기록에는 없다.
같은 기준(최근 6회차와 기사 URL 겹침)으로 처음 날짜부터 차례로 다시 매겨, 지난 흐름 그래프도 이어지게 한다.

    python3 scripts/backfill_threads.py          # 미리보기(바뀌는 줄 수만)
    python3 scripts/backfill_threads.py --apply  # 실제로 파일을 고친다
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from newssignal.threads import Threads  # noqa: E402

DATA = ROOT / "site" / "data"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    T = Threads()
    changed_total = 0
    last_tids: dict[tuple[str, str], str] = {}
    for day_path in sorted((DATA / "days").glob("*.json")):
        day = json.loads(day_path.read_text(encoding="utf-8"))
        arts = DATA / "articles" / day_path.name
        sa = json.loads(arts.read_text(encoding="utf-8")).get("story_articles", {}) if arts.exists() else {}
        changed = 0
        for s in sorted(day.get("snapshots", []), key=lambda x: x["ts"]):
            stories = s.get("stories") or {}
            issues: dict[str, dict] = {}
            for rows in stories.values():
                for r in rows:
                    if r[0] not in issues:
                        anc = r[14] if len(r) > 14 and r[14] and not r[14].startswith("s:") else ""
                        issues[r[0]] = {"id": r[0], "anc": anc, "urls": {a["u"] for a in sa.get(r[0], []) if a.get("u")}}
            tid_of = T.assign(list(issues.values()))
            for cat, rows in stories.items():
                for r in rows:
                    while len(r) < 17:
                        r.append("" if len(r) != 15 else "[]")
                    if r[16] != tid_of[r[0]]:
                        r[16] = tid_of[r[0]]
                        changed += 1
                    last_tids[(cat, r[0])] = r[16]
            T.feed_rows(s["ts"], stories, sa)
        changed_total += changed
        print(f"{day_path.stem}: 회차 {len(day.get('snapshots', []))} · 흐름 번호 {changed}줄")
        if args.apply and changed:
            day_path.write_text(json.dumps(day, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    latest_path = DATA / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    n = 0
    for cat, rows in (latest.get("stories") or {}).items():
        for o in rows:
            tid = last_tids.get((cat, o["id"]))
            if tid and o.get("tid") != tid:
                o["tid"] = tid
                n += 1
    print(f"latest.json: {n}줄")
    if args.apply and n:
        latest_path.write_text(json.dumps(latest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"합계 {changed_total}줄" + ("" if args.apply else " — 미리보기입니다. --apply 로 실제 반영"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
