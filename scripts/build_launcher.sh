#!/bin/bash
# 바탕화면 런처(News Signal.app) 만들기: assets/icon.html → 아이콘 렌더링 → .icns → ~/Desktop/News Signal.app
# 실행: bash scripts/build_launcher.sh   (scripts/webshot 이 먼저 빌드돼 있어야 함: swiftc -O -o scripts/webshot scripts/webshot.swift)
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; SP="$ROOT/assets/build"; mkdir -p "$SP"; "$ROOT/scripts/webshot" "file://$ROOT/assets/icon.html" "$SP/icon1024.png" 1024 1024 2 transparent
cd "$SP"
sips -s dpiWidth 72 -s dpiHeight 72 -z 1024 1024 icon1024.png --out icon1024_72.png >/dev/null
rm -rf AppIcon.iconset AppIcon.icns; mkdir AppIcon.iconset
while read -r size name; do sips -z "$size" "$size" icon1024_72.png --out "AppIcon.iconset/$name.png" >/dev/null; done <<'LIST'
16 icon_16x16
32 icon_16x16@2x
32 icon_32x32
64 icon_32x32@2x
128 icon_128x128
256 icon_128x128@2x
256 icon_256x256
512 icon_256x256@2x
512 icon_512x512
1024 icon_512x512@2x
LIST
iconutil -c icns AppIcon.iconset -o AppIcon.icns
echo "icns: $(stat -f %z AppIcon.icns) bytes"
APP="$HOME/Desktop/News Signal.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"
cat > "$APP/Contents/Info.plist" <<'PL'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>News Signal</string>
  <key>CFBundleDisplayName</key><string>News Signal</string>
  <key>CFBundleIdentifier</key><string>com.woo.newssignal.launcher</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PL
cat > "$APP/Contents/MacOS/launcher" <<'SH'
#!/usr/bin/env bash
# News Signal — 바탕화면 런처
# 이 맥의 로컬 대시보드(8770)가 떠 있으면 연다 → 없으면 켜고 연다 → 그래도 안 되면 공개 주소를 연다.
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
PROJECT="/Users/woo/News Signal"
PORT=8770
LOCAL="http://127.0.0.1:$PORT/"
PUBLIC="https://woojeongryeol.github.io/news-signal/"
DRY="${NEWSSIGNAL_DRY_RUN:-}"

up() { curl -s -o /dev/null -m 2 "$LOCAL" ; }
go() { if [ -n "$DRY" ]; then echo "would open: $1"; else open "$1"; fi; }

if up; then go "$LOCAL"; exit 0; fi

if [ -d "$PROJECT" ] && command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
  mkdir -p "$PROJECT/logs"
  if [ -n "$DRY" ]; then echo "would start: python3 -m newssignal serve --port $PORT (cwd $PROJECT)"; go "$LOCAL"; exit 0; fi
  ( cd "$PROJECT" && nohup python3 -m newssignal serve --port "$PORT" >> "$PROJECT/logs/serve.log" 2>&1 & )
  for i in 1 2 3 4 5 6 7 8; do sleep 0.5; if up; then go "$LOCAL"; exit 0; fi; done
fi

go "$PUBLIC"
SH
chmod +x "$APP/Contents/MacOS/launcher"
plutil -lint "$APP/Contents/Info.plist"
touch "$APP"
echo "--- dry run ---"; NEWSSIGNAL_DRY_RUN=1 "$APP/Contents/MacOS/launcher"
echo "--- bundle ---"; find "$APP" -type f | sed "s|$HOME/Desktop/||"
