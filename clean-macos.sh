#!/bin/bash
# 只删除本仓库的 build 和 dist。models 不动。程序还在跑就不删。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
exec python3 "$ROOT/macos_build.py" clean "$@"
