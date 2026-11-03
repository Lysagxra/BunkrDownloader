#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
export PYINSTALLER_CONFIG_DIR="$ROOT/build/pyinstaller-cache"
export CLANG_MODULE_CACHE_PATH="$ROOT/build/clang-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$ROOT/build/swift-cache"
APP="$ROOT/dist/Bunkr.app"
SDK="${SDK:-$(xcrun --sdk macosx --show-sdk-path)}"
"$PYTHON" -m PyInstaller --noconfirm --clean --onedir --name BunkrEngine \
  --paths "$ROOT" --distpath "$ROOT/build/engine" --workpath "$ROOT/build/pyinstaller" \
  --specpath "$ROOT/build" "$ROOT/macos/bridge.py"
xcrun swiftc -swift-version 5 -parse-as-library -sdk "$SDK" -target "$(uname -m)-apple-macosx27.0" \
  -module-cache-path "$ROOT/build/clang-cache" -O macos/Sources/*.swift -o "$ROOT/build/Bunkr"
# Recreate only this generated app bundle; user queue/downloads live elsewhere.
if [ -d "$APP" ]; then rm -rf "$APP"; fi
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$ROOT/build/Bunkr" "$APP/Contents/MacOS/Bunkr"
# ditto updates the dedicated engine bundle; clear its old build to avoid stale modules.
if [ -d "$APP/Contents/Resources/BunkrEngine" ]; then rm -rf "$APP/Contents/Resources/BunkrEngine"; fi
ditto "$ROOT/build/engine/BunkrEngine" "$APP/Contents/Resources/BunkrEngine"
cp macos/Info.plist "$APP/Contents/Info.plist"
cp LICENSE "$APP/Contents/Resources/LICENSE"
cp -R src "$APP/Contents/Resources/EngineSource"
cp downloader.py macos/bridge.py requirements.txt "$APP/Contents/Resources/"
swift macos/GenerateIcon.swift "$ROOT/build/AppIcon.iconset"
"$PYTHON" macos/package_icon.py "$ROOT/build/AppIcon.iconset" "$APP/Contents/Resources/AppIcon.icns"
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP"
"$APP/Contents/Resources/BunkrEngine/BunkrEngine" --check
printf '\nBuilt %s\n' "$APP"
