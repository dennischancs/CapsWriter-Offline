#!/bin/bash
# Apple Silicon 本地编译。产物在 dist/CapsWriter-Offline。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
exec python3 "$ROOT/macos_build.py" build "$@"
