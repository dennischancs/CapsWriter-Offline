#!/bin/bash
# 只编译 Swift 界面，方便单独看窗口。
# 带服务端和模型的 dist/CapsWriter.app 由仓库根目录的 ./build-macos.sh 生成。
# 已经有完整包时不覆盖。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c 'import pathlib,re,sys; text=pathlib.Path(sys.argv[1]).read_text(); print(re.search(r"^version = \"([^\"]+)\"", text, re.M).group(1))' "$ROOT/pyproject.toml")"
cd "$ROOT/macos/CapsWriterShell"
swift build -c release
BIN="$(swift build -c release --show-bin-path)/CapsWriter"
APP="$ROOT/dist/CapsWriter.app"
if [[ -d "$APP/Contents/Resources/runtime" ]]; then
    echo "已有完整的 $APP，不覆盖。要重打请运行 ./build-macos.sh" >&2
    exit 1
fi
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/CapsWriter"
cp "$ROOT/macos/AppIcon.icns" "$APP/Contents/Resources/AppIcon.icns"
sed "s/__VERSION__/$VERSION/g" "$ROOT/macos/Info.plist.in" > "$APP/Contents/Info.plist"
chmod +x "$APP/Contents/MacOS/CapsWriter"
echo "$APP"
