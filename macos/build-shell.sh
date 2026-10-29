#!/bin/bash
# 和仓库根目录的 ./build-macos.sh 是同一次完整打包。
# 产物是 dist/CapsWriter.app，里面有 Swift 界面、服务端和复制进来的模型。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/build-macos.sh" "$@"
