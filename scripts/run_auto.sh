#!/bin/bash
# launchd(매시 0분·30분)에서 도는 스크립트.
#
#  1) 원격에서 최신 결과를 받아 온다 — 수집은 GitHub Actions 가 주로 담당한다(맥이 꺼져 있어도 돌도록).
#  2) 클라우드가 75분 넘게 밀렸으면 이 맥이 대신 수집해 밀어 넣는다.
#
# 망이 끊긴 채 시작된 회차가 출처마다 시간제한을 기다리며 몇 시간씩 매달리면 launchd 가 다음 회차를
# 띄우지 않아 수집이 통째로 멈춘다. 그래서 연결을 먼저 확인하고, 하드 타임아웃으로도 한 번 더 막는다.
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p logs
exec >> logs/collect.log 2>&1
echo "=== $(date '+%F %T') ==="

if ! python3 -c "import sys; from newssignal.fetch import online; sys.exit(0 if online() else 1)"; then
  echo "네트워크 없음 — 건너뜁니다"
  exit 0
fi

git pull --rebase -q --autostash 2>/dev/null || echo "git pull 실패"

STALE=$(python3 - <<'PY'
import json
from datetime import datetime, timedelta, timezone
try:
    latest = json.load(open("site/data/manifest.json"))["latest"]
    age = (datetime.now(timezone(timedelta(hours=9))) - datetime.fromisoformat(latest)).total_seconds() / 60
except Exception:
    age = 9999
print(int(age))
PY
)
echo "최신 수집: ${STALE}분 전"
if [ "${STALE:-9999}" -lt 75 ]; then
  echo "클라우드가 최신이라 받아만 왔습니다"
  exit 0
fi

echo "클라우드가 밀려 이 맥이 대신 수집합니다"
TIMEOUT=${NEWSSIGNAL_TIMEOUT:-420}      # 한 회차 최대 7분
python3 -m newssignal collect &
PID=$!
( sleep "$TIMEOUT"; kill -0 "$PID" 2>/dev/null && { echo "!! ${TIMEOUT}초를 넘겨 중단합니다"; kill -9 "$PID" 2>/dev/null; } ) &
WATCHDOG=$!
wait "$PID"; STATUS=$?
kill "$WATCHDOG" 2>/dev/null
[ "$STATUS" -ne 0 ] && exit "$STATUS"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git add -A -- site/data
git diff --cached --quiet && exit 0
git commit -q -m "data: $(date '+%F %H:%M') 수집 (맥 대체)" || exit 0
for i in 1 2 3; do git push -q && break; git pull --rebase -q; sleep 3; done
