#!/bin/bash
# Apple Silicon 本地编译。产物在 dist/CapsWriter-Offline。
# 入口用本机 miniforge 的 capswriter。没有时再退回 python3。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="${CAPSWRITER_PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/capswriter/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON=python3
fi
exec "$PYTHON" "$ROOT/macos_build.py" build "$@"
