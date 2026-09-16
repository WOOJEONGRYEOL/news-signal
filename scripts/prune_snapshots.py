"""검증용으로 몰아서 돌린 스냅샷을 정리한다.

수집을 짧은 간격으로 여러 번 돌리면(개발·검증) 그 시간대에 점이 몰려 흐름 그래프가 뭉쳐 보인다.
이 스크립트는 지정한 날짜·시각대에서 남길 분(分)만 남기고 나머지 스냅샷을 지운다.

    python3 scripts/prune_snapshots.py --date 2026-09-15 --hour 15 --keep 00,30          # 미리보기
    python3 scripts/prune_snapshots.py --date 2026-09-15 --hour 15 --keep 00,30 --apply  # 실제 삭제

급상승 기준선은 '스냅샷당 평균 기사 수'라서, 스냅샷을 지우면 그날 누적(daily_counts)도
같은 비율로 줄여야 평균이 유지된다. --apply 는 그 보정까지 함께 한다.
삭제 전 data/ 아래에 백업본을 남긴다.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "newssignal.sqlite3"
SNAP_TABLES = ("stories", "story_articles", "ranks", "keyword_articles",
               "portal_items", "ranking_news", "region_trends", "related")


def main() -> int:
    ap = argparse.ArgumentParser(description="몰아서 찍힌 스냅샷 정리")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--hour", required=True, help="정리할 시각대 (예: 15)")
    ap.add_argument("--keep", default="00,30", help="남길 분, 쉼표 구분 (기본 00,30)")
    ap.add_argument("--apply", action="store_true", help="실제로 삭제 (없으면 미리보기)")
    args = ap.parse_args()

    keep = {m.strip().zfill(2) for m in args.keep.split(",") if m.strip()}
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    prefix = f"{args.date}T{args.hour.zfill(2)}:"
    rows = conn.execute("SELECT id, ts FROM snapshots WHERE ts LIKE ? ORDER BY ts", (prefix + "%",)).fetchall()
    if not rows:
        print(f"{prefix} 에 해당하는 스냅샷이 없습니다.")
        return 1
    doomed = [r for r in rows if r["ts"][14:16] not in keep]
    kept = [r for r in rows if r["ts"][14:16] in keep]
    print(f"{args.date} {args.hour}시대 스냅샷 {len(rows)}개")
    print("  남김:", ", ".join(r["ts"][11:16] for r in kept) or "(없음)")
    print("  삭제:", ", ".join(r["ts"][11:16] for r in doomed) or "(없음)")
    if not doomed:
        return 0
    if not args.apply:
        print("\n미리보기입니다. 실제로 지우려면 --apply 를 붙이세요.")
        return 0

    backup = DB.with_name(f"newssignal.backup-{datetime.now():%Y%m%d-%H%M%S}.sqlite3")
    shutil.copy2(DB, backup)
    print(f"\n백업: {backup.name} ({backup.stat().st_size // 1024} KB)")

    ids = [r["id"] for r in doomed]
    q = ",".join("?" * len(ids))
    day_total = conn.execute("SELECT COUNT(*) FROM snapshots WHERE ts LIKE ?", (args.date + "%",)).fetchone()[0]
    ratio = (day_total - len(ids)) / day_total if day_total else 1.0
    with conn:
        for t in SNAP_TABLES:
            n = conn.execute(f"DELETE FROM {t} WHERE snapshot_id IN ({q})", ids).rowcount
            print(f"  {t:16s} {n:6d}행 삭제")
        conn.execute(f"DELETE FROM snapshots WHERE id IN ({q})", ids)
        conn.execute("UPDATE daily_counts SET publish_sum = CAST(ROUND(publish_sum * ?) AS INTEGER),"
                     " n = MAX(1, CAST(ROUND(n * ?) AS INTEGER)) WHERE date = ?", (ratio, ratio, args.date))
        print(f"  daily_counts     기준선을 × {ratio:.2f} 로 보정")
    conn.execute("VACUUM")
    left = conn.execute("SELECT COUNT(*) FROM snapshots WHERE ts LIKE ?", (args.date + "%",)).fetchone()[0]
    print(f"\n{args.date} 스냅샷 {day_total} → {left}개")
    print("이제 `python3 -m newssignal build` 로 site/data 를 다시 만드세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
