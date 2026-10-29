#!/bin/bash
# 一次删掉本仓库的 build、dist、Swift 的 .build，以及 /tmp/cw-swift。
# dist 里的 CapsWriter.app 和 dmg 也在里面。仓库里的 models 不动。程序还在跑就不删。
# 入口用本机 miniforge 的 capswriter。没有时再退回 python3。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="${CAPSWRITER_PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/capswriter/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON=python3
fi
exec "$PYTHON" "$ROOT/macos_build.py" clean "$@"
