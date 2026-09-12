#!/bin/bash
# macOS LaunchAgent 등록(재등록): 30분마다 scripts/run_auto.sh 실행
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.woo.newssignal"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"
sed "s|/Users/woo/News Signal|$ROOT|g" "$ROOT/scripts/$LABEL.plist" > "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "등록 완료: $LABEL (30분마다). 상태: launchctl list | grep $LABEL · 로그: $ROOT/logs/collect.log"
echo "해제: launchctl bootout gui/\$(id -u)/$LABEL && rm \"$PLIST\""
