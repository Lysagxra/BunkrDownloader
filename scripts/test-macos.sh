#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p build
"${PYTHON:-$ROOT/.venv/bin/python}" -m unittest discover -s tests -v
xcrun swiftc -swift-version 5 -D STANDALONE -parse-as-library \
  -module-cache-path "$ROOT/build/clang-cache" \
  macos/Sources/LinkParser.swift macos/Sources/Models.swift macos/Sources/DownloadStore.swift \
  macos/Tests/BunkrTests.swift macos/TestSupport/Standalone.swift -o build/NativeTests
build/NativeTests
