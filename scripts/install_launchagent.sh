#!/bin/bash
# macOS LaunchAgent 등록(재등록): 매시 0분·30분에 scripts/run_auto.sh 실행
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.woo.newssignal"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/logs"
sed "s|/Users/woo/News Signal|$ROOT|g" "$ROOT/scripts/$LABEL.plist" > "$PLIST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "등록 완료: $LABEL (매시 0분·30분). 상태: launchctl list | grep $LABEL · 로그: $ROOT/logs/collect.log"
echo "해제: launchctl bootout gui/\$(id -u)/$LABEL && rm \"$PLIST\""
