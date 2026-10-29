#!/bin/bash
# Apple Silicon 一次打出 dist/CapsWriter.app 和 dist/CapsWriter-<version>.dmg。
# app 里有 Swift 界面、服务端、批量转录和复制进来的模型。
# dmg 里是这个 app，以及指向「应用程序」的链接。
# 成功后清掉 PyInstaller 的 build、Swift 的 .build 和 /tmp/cw-swift。
# 入口用本机 miniforge 的 capswriter。没有时再退回 python3。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="${CAPSWRITER_PYTHON:-/opt/homebrew/Caskroom/miniforge/base/envs/capswriter/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON=python3
fi
exec "$PYTHON" "$ROOT/macos_build.py" build "$@"
