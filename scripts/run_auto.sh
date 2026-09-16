#!/bin/bash
# launchd(매시 0분·30분) → 수집 → site/data 변경분 커밋·푸시(원격이 있을 때만). 로그: logs/collect.log
#
# 한 회차가 끝나지 않으면 launchd 는 다음 회차를 띄우지 않는다. 망이 끊긴 채로 수집이 시작되면
# 출처마다 시간제한을 기다리느라 몇 시간씩 매달리고 그동안 수집이 통째로 멈춘다.
# 그래서 ① 파이썬 쪽에서 연결을 먼저 확인하고 ② 여기서도 하드 타임아웃으로 강제 종료한다.
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p logs
exec >> logs/collect.log 2>&1
echo "=== $(date '+%F %T') ==="

TIMEOUT=${NEWSSIGNAL_TIMEOUT:-420}      # 한 회차 최대 7분
python3 -m newssignal collect &
PID=$!
( sleep "$TIMEOUT"; kill -0 "$PID" 2>/dev/null && { echo "!! ${TIMEOUT}초를 넘겨 중단합니다"; kill -9 "$PID" 2>/dev/null; } ) &
WATCHDOG=$!
wait "$PID"; STATUS=$?
kill "$WATCHDOG" 2>/dev/null
[ "$STATUS" -ne 0 ] && exit "$STATUS"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
remote=$(git remote 2>/dev/null | head -1)
git add -A -- site/data
git diff --cached --quiet && exit 0
git commit -q -m "data: $(date '+%F %H:%M') 수집" || exit 0
if [ -n "$remote" ]; then
  for i in 1 2 3; do git push -q && break; git pull --rebase -q; sleep 3; done
fi
