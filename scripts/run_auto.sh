#!/bin/bash
# launchd(매시 0분·30분) → 수집 → site/data 변경분 커밋·푸시(원격이 있을 때만). 로그: logs/collect.log
cd "$(dirname "$0")/.." || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p logs
exec >> logs/collect.log 2>&1
echo "=== $(date '+%F %T') ==="

python3 -m newssignal collect || exit 1

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
remote=$(git remote 2>/dev/null | head -1)
git add -A -- site/data
git diff --cached --quiet && exit 0
git commit -q -m "data: $(date '+%F %H:%M') 수집" || exit 0
if [ -n "$remote" ]; then
  for i in 1 2 3; do git push -q && break; git pull --rebase -q; sleep 3; done
fi
