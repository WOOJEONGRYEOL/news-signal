#!/bin/bash
# launchd(매시 0분·30분)에서 도는 스크립트.
#
# 데이터를 쓰는 곳은 원칙적으로 클라우드(GitHub Actions) 하나다. 맥과 클라우드가 같은 JSON 을 동시에
# 고치면 git 이 줄 단위로 합치다 충돌하는데(2026-09-18 02:00 실제로 났다), 예전 스크립트는 그 상태로
# 멈춰 이후 12시간 동안 맥의 수집분을 하나도 올리지 못했다.
#
#  1) 원격의 최신 결과를 받아 온다.
#  2) 25분 넘게 새 수집이 없으면 클라우드 수집을 깨운다(gh workflow run).
#     GitHub 예약 실행은 몇 시간씩 거르므로, 맥이 켜져 있는 동안은 맥이 자명종 역할을 한다.
#  3) 90분 넘게 밀렸거나 클라우드를 깨울 수 없을 때만 이 맥이 직접 수집해 올린다.
#     올리다 충돌하면 git 의 줄 단위 병합 대신 클라우드 파일 위에 이 맥의 데이터베이스를 다시 합쳐 쓴다.
#  4) 어떤 경우에도 저장소를 rebase 도중 상태로 남기지 않는다.
#
# 망이 끊긴 채 시작된 회차가 출처마다 시간제한을 기다리며 몇 시간씩 매달리면 launchd 가 다음 회차를
# 띄우지 않아 수집이 통째로 멈춘다. 그래서 연결을 먼저 확인하고, 하드 타임아웃으로도 한 번 더 막는다.
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p logs
exec >> logs/collect.log 2>&1
echo "=== $(date '+%F %T') ==="

WAKE_AFTER=${NEWSSIGNAL_WAKE_AFTER:-25}   # 이만큼(분) 밀리면 클라우드를 깨운다
SELF_AFTER=${NEWSSIGNAL_SELF_AFTER:-90}   # 이만큼(분) 밀리면 맥이 직접 수집한다

rebasing() { [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; }

# 이전 회차가 남긴 rebase/merge 중간 상태를 치운다.
heal() {
  if rebasing; then echo "멈춘 rebase 를 되돌립니다"; git rebase --abort 2>/dev/null || git rebase --quit; fi
  if [ -f .git/MERGE_HEAD ]; then echo "멈춘 merge 를 되돌립니다"; git merge --abort; fi
  [ "$(git branch --show-current)" = "main" ] || { echo "!! main 브랜치가 아닙니다 — git 작업을 건너뜁니다"; return 1; }
}

# rebase 가 site/data 에서만 충돌했으면: 원격(클라우드) 파일을 기준으로 두고, 이 맥 데이터베이스의
# 최근 이틀을 프로그램의 병합(시각별 합치기)으로 다시 써 넣는다. 그 밖의 충돌이면 되돌린다.
resolve_rebase() {
  local n=0 conflicted
  while rebasing && [ $n -lt 20 ]; do
    n=$((n + 1))
    conflicted=$(git diff --name-only --diff-filter=U)
    if [ -n "$conflicted" ]; then
      if echo "$conflicted" | grep -qv '^site/data/'; then echo "!! 데이터 밖의 파일이 충돌했습니다"; break; fi
      echo "$conflicted" | while read -r f; do git checkout -q --ours -- "$f" 2>/dev/null || git checkout -q --theirs -- "$f"; done
      python3 -m newssignal build --days 2 >/dev/null || break
      python3 - <<'PY'
import json, subprocess
mine = subprocess.run(["git", "show", "REBASE_HEAD:site/data/latest.json"], capture_output=True, text=True).stdout
try:
    cur = json.load(open("site/data/latest.json", encoding="utf-8"))
    if mine and json.loads(mine).get("ts", "") > cur.get("ts", ""):
        open("site/data/latest.json", "w", encoding="utf-8").write(mine)
except Exception as e:
    print("latest.json 비교 실패:", e)
PY
      git add -A -- site/data
    fi
    if ! GIT_EDITOR=true git rebase --continue >/dev/null 2>&1; then
      [ -z "$(git diff --name-only --diff-filter=U)" ] && git diff --cached --quiet && git rebase --skip >/dev/null 2>&1
    fi
  done
  if rebasing; then echo "!! 자동 병합 실패 — 되돌립니다"; git rebase --abort; return 1; fi
  echo "데이터 충돌을 자동으로 합쳤습니다"
}

sync() {
  git fetch -q origin main || { echo "git fetch 실패"; return 1; }
  git rebase -q --autostash origin/main 2>/dev/null && return 0
  rebasing || { echo "git rebase 실패"; return 1; }
  resolve_rebase
}

publish() {
  for i in 1 2 3; do
    git push -q origin main && { echo "올렸습니다"; return 0; }
    sync || return 1
  done
  echo "!! 올리지 못했습니다"; return 1
}

stale_minutes() {
  python3 - <<'PY'
import json
from datetime import datetime, timedelta, timezone
try:
    latest = json.load(open("site/data/manifest.json"))["latest"]
    print(int((datetime.now(timezone(timedelta(hours=9))) - datetime.fromisoformat(latest)).total_seconds() // 60))
except Exception:
    print(9999)
PY
}

if ! python3 -c "import sys; from newssignal.fetch import online; sys.exit(0 if online() else 1)"; then
  echo "네트워크 없음 — 건너뜁니다"
  exit 0
fi

GIT_OK=0
if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && heal; then
  GIT_OK=1
  sync || echo "git 동기화 실패"
  # 지난 회차에 못 올린 수집 커밋이 남아 있으면 올린다(수집 커밋만 있을 때만 — 작업 중인 코드는 건드리지 않는다).
  AHEAD=$(git log --format=%s origin/main..main 2>/dev/null)
  if [ -n "$AHEAD" ] && ! echo "$AHEAD" | grep -qv '^data: '; then publish; fi
fi

STALE=$(stale_minutes)
echo "최신 수집: ${STALE}분 전"
if [ "${STALE:-9999}" -lt "$WAKE_AFTER" ]; then
  echo "최신이라 받아만 왔습니다"
  exit 0
fi

if [ "$STALE" -lt "$SELF_AFTER" ] && command -v gh >/dev/null 2>&1 \
   && gh workflow run collect.yml --ref main -f mode=collect >/dev/null 2>&1; then
  echo "클라우드 수집을 깨웠습니다"
  exit 0
fi

echo "클라우드가 응답하지 않아 이 맥이 직접 수집합니다"
TIMEOUT=${NEWSSIGNAL_TIMEOUT:-420}      # 한 회차 최대 7분
python3 -m newssignal collect &
PID=$!
( sleep "$TIMEOUT"; kill -0 "$PID" 2>/dev/null && { echo "!! ${TIMEOUT}초를 넘겨 중단합니다"; kill -9 "$PID" 2>/dev/null; } ) &
WATCHDOG=$!
wait "$PID"; STATUS=$?
kill "$WATCHDOG" 2>/dev/null
[ "$STATUS" -ne 0 ] && exit "$STATUS"

[ "$GIT_OK" = 1 ] || exit 0
git add -A -- site/data
git diff --cached --quiet && exit 0
git commit -q -m "data: $(date '+%F %H:%M') 수집 (맥 대체)" || exit 0
publish
