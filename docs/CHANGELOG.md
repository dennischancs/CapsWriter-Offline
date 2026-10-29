# 更新日志

## v2.33.0

- **安装盘**：`./build-macos.sh` 在 `dist/CapsWriter.app` 旁边打出未签名的 `dist/CapsWriter-2.33.0.dmg`。打开后左边是 CapsWriter，右边是「应用程序」，拖过去即可安装。`./build-macos.sh client` 不打这个盘。`./clean-macos.sh` 仍一次删掉 `dist`，盘和 app 一起消失，仓库里的模型不动。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_macos_build tests.test_build_support`，34 项通过。没有重跑 PyInstaller，也没有重编 Swift。用已经存在的 `dist/CapsWriter.app` 打出 6.3GB 的 dmg。只读挂载后是 `CapsWriter.app` 和 `Applications -> /Applications`，随后卸掉。

## v2.32.3

- **换模型会换掉已经开着的服务端**：批量窗口里从 SenseVoice Small 换成 Qwen，或在 Qwen 1.7B 和 0.6B 之间换，下一次开始会先停掉还在用旧模型的进程，再按新模型拉起。配置文件提前写好也不再直接复用 6016 上的旧进程。窗口先把新模型写入配置时，只要这份配置比正在运行的服务端新，打包后的 `batch_transcribe` 也会重启。端口关不掉时不开始，并写明服务端还在用原来的模型。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_config_form tests.test_progress_log tests.test_batch_transcribe tests.test_build_support`，68 项通过。`swift test --package-path macos/CapsWriterShell --disable-sandbox --scratch-path /tmp/cw-swift`，19 项通过。没有整包重打，模型仍是原来的副本。换进 app 的是 Swift 界面，以及重新打包的 `batch_transcribe`。

## v2.32.2

- **进度不再往下刷**：发送进度始终一行，转录进度始终另一行。数字仍按这段音频的 0、60、120 往前改，最后停在真实时长上，完成时间留在这一行的时间戳里。处理耗时、完成、失败和文件名仍另起一行。下一个文件从头计时，不改掉上一份已经结束的那一行。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_config_form tests.test_progress_log tests.test_batch_transcribe tests.test_build_support`，66 项通过。`swift test --package-path macos/CapsWriterShell --disable-sandbox --scratch-path /tmp/cw-swift`，18 项通过。这次没有重跑整包，只换了 `dist/CapsWriter.app` 里的 Swift 界面。

## v2.32.1

- **client 和 server 能打开**：这两个标签读配置时不再 `import batch_transcribe`。打包后的 `batch_transcribe` 是可执行文件，不是 Python 模块，所以原来整页都是 `No module named 'batch_transcribe'`。`auto` 仍按内存展开成 `1.7b` 或 `0.6b`，选了具体规格或换成别的引擎后，摘要跟着变。
- **发送进度不再刷屏**：605.77 秒的文件不再从 `0.04s`、`0.06s`、`1.09s` 一直写到结尾。分子按这段音频的 0、60、120 留下，最后一行是 `605.77s`。转录进度用同样的全角冒号和分档。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_config_form tests.test_progress_log tests.test_batch_transcribe tests.test_build_support`，65 项通过。`swift test --package-path macos/CapsWriterShell --disable-sandbox --scratch-path /tmp/cw-swift`，18 项通过。`./build-macos.sh` 打出 `dist/CapsWriter.app`，短版本 2.32.1。包内 `python -m core.tools.config_form dump` 能写出摘要，`auto` 展开成 `1.7b`。打开 app 后，client 和 server 都是配置页，不再是那条导入错误。

## v2.32.0

- **去掉 macOS 的 Tk 依赖**：`requirements-macos.txt` 不再列 `tkhtmlview` 和 `tkinterdnd2`。`pyproject.toml` 里的 `tkhtmlview` 只留给 Windows。Darwin 打包不再收集 `tkinterdnd2`。安装说明不再要求 `python-tk`。
- **不打开 Tk**：在 macOS 上不带参数运行 `batch_transcribe.py` 退出码是 2，并提示打开 `dist/CapsWriter.app`。Windows 不带参数仍打开原来的批量窗口。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_batch_transcribe tests.test_build_support tests.test_macos_port`，91 项通过。这次没有重跑 PyInstaller，也没有组装 app。

## v2.31.0

- **同一个模型**：批量菜单里看到的模型和 Qwen 规格，server 标签「现在这样跑」显示同一个值。配置写成 `auto` 时，两边都按内存展开成 `1.7b` 或 `0.6b`，不再一边是具体规格、一边停在 auto。选了 `0.6b` 或换到 SenseVoice 之后，摘要跟着变。client 标签没有模型项，不跟着变。下面的配置表单仍显示文件里的原文，写入后下次启动才生效。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_config_form tests.test_batch_transcribe tests.test_build_support`，57 项通过。`swift test --package-path macos/CapsWriterShell`，18 项通过。这次没有重跑 PyInstaller，也没有组装 app。

## v2.30.0

- **模型和标签**：批量转换里一换模型，马上写入 `config_server.py`。server 标签的「现在这样跑」和下面的模型、Qwen 规格跟着变成同一个值。client 标签没有模型项，不跟着变。正在转录时仍不能换。
- 验证：和 2.31.0 一起跑。capswriter 环境的 `python3 -m unittest tests.test_config_form tests.test_batch_transcribe tests.test_build_support`，57 项通过。`swift test --package-path macos/CapsWriterShell`，18 项通过。

## v2.29.1

- **批量转录**：恢复被清空的 `core/client/transcribe/file_transcriber.py`。`FileTranscriber` 又能导入。已打进 `dist/CapsWriter.app` 的那份空文件也换回这份源码，不用整包重打。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_build_support tests.test_batch_transcribe`，47 项通过。打包副本能 `import FileTranscriber`。

## v2.29.0

- **一次打出 app**：`./build-macos.sh` 打出未签名的 `dist/CapsWriter.app`。Swift 界面在 `Contents/MacOS`，服务端、客户端、批量转录和模型在 `Contents/Resources/runtime`。模型是复制进去的真实文件，不是指回仓库的符号链接。成功后删掉 PyInstaller 的 `build`、Swift 的 `.build` 和 `/tmp/cw-swift`。`./build-macos.sh client` 仍只打客户端。
- **一次清理**：`./clean-macos.sh` 删掉 `build`、`dist`（含这个 app）、`macos/CapsWriterShell/.build` 和 `/tmp/cw-swift`。仓库里的 `models` 不动。这些程序还在跑时不删，也不开始编译。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_macos_build tests.test_build_support`，31 项通过。`./build-macos.sh` 打出 7.5GB 的 `dist/CapsWriter.app`，短版本 2.29.0。Swift 界面、`start_server`、`batch_transcribe` 都是 arm64 Mach-O。包里的 `models` 没有符号链接，仓库里的 `models` 仍是 6.9GB。`build`、`.build` 和 `/tmp/cw-swift` 已经不在。

## v2.28.0

- **Qwen3-ASR**：批量窗口的模型菜单分成 Qwen3-ASR 1.7B 和 Qwen3-ASR 0.6B。选中后写入 `model_type = qwen_asr`，以及 `qwen_mlx_variant` 的 `1.7b` 或 `0.6b`。SenseVoice、Fun-ASR Nano、Paraformer 不变。配置里的 `auto` 不单列；窗口按内存显示将要加载的那一个，和当前一致时不重启服务端。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_batch_transcribe tests.test_build_support`，46 项通过。`swift test --package-path macos/CapsWriterShell`，18 项通过。这次没有重跑 PyInstaller，也没有组装 app。

## v2.27.0

- **进度分子**：发送进度和转录进度不再写「音频文件的 60 秒」这句说明。分子按这段音频往前走：0、60、120、180，直到音频结束。605.77 秒的文件最后一行是 605.77，不是停在 600。同一档不重复写。完成、失败和文件名仍马上留下。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_progress_log tests.test_batch_transcribe tests.test_build_support`，50 项通过。`swift build --package-path macos/CapsWriterShell` 通过。`swift test --package-path macos/CapsWriterShell`，17 项通过。这次没有重跑 PyInstaller，也没有组装 app。

## v2.26.0

- **client 和 server**：外壳窗口的首页仍是批量转换。另外两个标签叫 client 和 server。上面是 start_client、start_server 启动时能看到的版本、地址、快捷键和模型，下面是 `config_client.py`、`config_server.py` 里的全部可改项。打开时按文件里的值填好。默认关着的保持关，例如粘贴（Windows）、合并长文本、UDP 和显卡预加速。
- **推荐值**：阈值、分段、模型路径和引擎参数是灰的。双击这一行，确认「这是推荐值。确定要修改吗？」之后才能改。只在这一次打开窗口里记住，不另写一份。
- **说明**：鼠标停在每一项上能看到它是干什么的。分段里的 60 秒仍是音频里的秒，不是系统时间。改完要点「写入配置」，下次启动客户端或服务端才生效。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_config_form tests.test_build_support`，18 项通过。`swift build --package-path macos/CapsWriterShell` 通过。`swift test --package-path macos/CapsWriterShell`，17 项通过。这次没有重跑 PyInstaller，也没有组装 app。

## v2.25.0

- **进度里的 60 秒**：发送进度和转录进度写明，这一段是音频文件的 60 秒，不是系统时间的 60 秒。界面仍按系统时间至少隔 30 秒才再留一行。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_progress_log tests.test_build_support`，12 项通过。这次没有重跑 PyInstaller，也没有编译 Swift。

## v2.24.0

- **进度日志**：界面里的「发送进度」和「转录进度」至少隔 30 秒一行。同一种进度的第一行马上出现。完成、失败、文件名，以及「未找到 ffmpeg」这类说明仍立刻出现。
- **一个 app**：`./build-macos.sh` 打出未签名的 `dist/CapsWriter.app`。Swift 界面在 `Contents/MacOS`，服务端、批量转录和模型在 `Contents/Resources/runtime`。模型是复制进去的真实文件，不是指回仓库的符号链接。`./build-macos.sh client` 仍只打客户端，不带模型，也不组装这个 app。
- **清理**：`./clean-macos.sh` 仍只删除仓库里的 `build` 和 `dist`。包里的模型副本跟着 `dist` 一起删。仓库里的 `models` 不动。这些程序还在跑就不删。
- 验证：`swift test --package-path macos/CapsWriterShell`，17 项通过。capswriter 环境的 `python3 -m unittest tests.test_progress_log tests.test_batch_transcribe tests.test_build_support tests.test_macos_build`，66 项通过。这次没有重跑 PyInstaller，也没有复制整套模型。

## v2.23.0

- **图标和关于**：`dist/CapsWriter.app` 使用 Cw 图标。菜单栏是同一个标记。应用菜单和右键菜单里有「关于 CapsWriter」。
- **关闭时可以选择并勾选记住**：点关闭会问缩小到菜单栏，还是退出。勾选「记住我的选择」后，下次关闭按这次的来。不勾选就下次再问。取消则窗口还在。已经记住时，菜单里的「下次关闭再询问」可以清掉。
- **缩到菜单栏之后**：左键打开批量转录窗口。右键（或按住 Control 再点）打开菜单，里面有显示窗口、关于、日志、热词和退出。
- 验证：`swift test --package-path macos/CapsWriterShell`，15 项通过。capswriter 环境的 `python3 -m unittest tests.test_batch_transcribe tests.test_build_support`，43 项通过。`./macos/build-shell.sh` 打出 arm64 的 `dist/CapsWriter.app`，短版本 2.23.0，图标文件是 AppIcon。

## v2.22.1

- **外壳能找到 Homebrew 的 ffmpeg**：从 Finder 打开 `CapsWriter.app` 做文件转录时，Python 进程的 PATH 会带上存在的 `/opt/homebrew/bin` 和 `/usr/local/bin`。原来的 PATH 还在。没装 ffmpeg 时，日志仍是「未找到 ffmpeg」。
- 验证：`swift test --package-path macos/CapsWriterShell`，15 项通过。capswriter 环境的 `python3 -m unittest tests.test_batch_transcribe tests.test_build_support`，42 项通过。`./macos/build-shell.sh` 打出的 app 短版本是 2.22.1。

## v2.22.0

- **macOS 外壳**：`./macos/build-shell.sh` 打出未签名的 `dist/CapsWriter.app`。菜单栏、麦克风和辅助功能、右 Option 听写、粘贴，以及批量转录窗口都在这个外壳里。窗口上的地址、六个选项、模型和日志等级跟 `batch_transcribe.py` 一样。窗口先出现，绿灯后才能开始。识别仍由现在的 `start_server` 做。
- **听写**：按住右 Option 说话，松开后只粘贴识别结果里的 `text`。按得太短会提示「按得太短」，这段没有声音会提示「这段录音是静音」。热词和 LLM 仍由 Python 客户端做。`./build-macos.sh` 的收集目录仍不生成这个 app。
- 验证：`swift test --package-path macos/CapsWriterShell`，14 项通过。capswriter 环境的 `python3 -m unittest tests.test_batch_transcribe tests.test_build_support`，42 项通过。`./macos/build-shell.sh` 打出的 app 短版本是 2.22.0。

## v2.21.0

- **关闭窗口可以选择**：第一次点关闭时，可选「缩小到托盘」或「退出」。选过一次就记住，之后不再询问。缩到菜单栏后，图标里可以重新显示窗口，也可以退出。
- **退出会结束后台**：退出时结束本程序的服务端、它拉起的子进程，以及正在转码的 ffmpeg。其它占用端口的程序不动。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_batch_transcribe tests.test_build_support`，41 项通过。这次没有重跑 PyInstaller。

## v2.20.0

- **转录结束后窗口能关掉**：srt、txt 和 json 写好后，状态从「转录中」变成「完成」。关闭按钮会退出窗口，不再停在那里。开始按钮和模型选择也会重新可用。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_batch_transcribe tests.test_build_support`，35 项通过。这次没有重跑 PyInstaller。

## v2.19.0

- **转录结束后不再卡在「转录中」**：srt、txt 和 json 写好后，窗口状态会变成「完成」。有失败是「完成，有失败」，中途停止是「已停止」。开始按钮和模型选择也会重新可用。
- **日志等级**：窗口可以选 DEBUG、INFO、WARNING、ERROR。低于所选等级的服务端日志不显示，文件进度始终显示。服务端日志会跟着出现在窗口里。每一行前面是 `[年-月-日 时:分:秒.毫秒]`。
- **手动换模型**：SenseVoice Small、Fun-ASR Nano、Qwen3-ASR、Paraformer。和当前不一样时，下次开始前写入 `config_server.py` 并重启服务端。正在转录时不能换。
- 验证：capswriter 环境的 `python3 -m unittest tests.test_batch_transcribe`，26 项通过。这次没有重跑 PyInstaller。

## v2.18.0

- **地址栏可以拖入文件或文件夹**：从 Finder 拖一个音视频或文件夹到批量转录的地址栏，路径会填进去。一次拖入多个时只用第一个。带空格的路径不会被拆开。粘贴和打开按钮还在。
- **编译改用本机 capswriter**：`./build-macos.sh` 和 `./clean-macos.sh` 用 miniforge 里的 `capswriter`（Python 3.13.18）。这个环境里已经有 PyInstaller。没设 `CAPSWRITER_PYTHON`、这个环境也不在时，才退回系统的 `python3`。仓库的 Python 下限仍是 3.14，没有为 Mac 降下去。
- 验证：`/opt/homebrew/Caskroom/miniforge/base/envs/capswriter/bin/python3 -m unittest tests.test_batch_transcribe tests.test_macos_build tests.test_build_support`，45 项通过。这次没有重跑 PyInstaller。

## v2.17.0

- **悬停说明跟着系统外观**：批量转录窗口里，鼠标停在地址、勾选、开始、停止和状态灯上时，暗色主题用浅色字、深色底，浅色主题用深色字、浅色底。每次悬停重新读系统外观，切主题后不用重启窗口。
- 验证：`/usr/bin/python3 -m unittest tests.test_batch_transcribe tests.test_build_support`，批量转录 20 项通过。版本检查用 conda 的 Python 3.14，1 项通过。这次没有重跑 PyInstaller：原来那个带 PyInstaller 的 Python 3.14 已经不在，`dist` 也已经清掉。

## v2.16.0

- **批量转录不再让人改等待时间**：窗口拿掉「等待服务端」「超时系数」「单文件最少等待」和「超过几时切开」。这几项固定为 180 秒、时长的 4 倍再加 60 秒、最少 180 秒、超过 2 小时切开。它们是放弃线，识别完成会立刻返回，调小会把还在算的文件判失败。鼠标停在地址、勾选、开始、停止和状态灯上会看到说明。
- 验证：`/usr/bin/python3 -m unittest tests.test_batch_transcribe`，19 项通过。窗口传入更短的等待秒数仍是 180。版本检查用 conda 的 Python 3.14，1 项通过。这次没有重跑 PyInstaller：原来那个带 PyInstaller 的 Python 3.14 已经不在。

## v2.15.0

- **批量转录窗口先出现**：双击或不带参数运行 `batch_transcribe` 时，窗口马上显示。服务端还在加载时不再挡住界面。左下角红灯是还没准备好，黄灯是正在准备，绿灯旁边写 Ready。没到绿灯时，开始转录不会跑。地址栏和打开在准备期间仍可使用。
- 验证：`/private/tmp/capswriter-macos-test/bin/python -m unittest tests.test_batch_transcribe tests.test_build_support`，27 项通过。窗口先显示黄灯，准备完成后变绿灯；失败保持红灯，开始转录不启动。`./build-macos.sh` 重新打出 arm64 的 `batch_transcribe`。

## v2.14.0

- **批量转录窗口**：不带参数运行 `batch_transcribe` 会打开自己的窗口。一行地址可以粘贴文件或文件夹，打开按钮用来选择。是否进子文件夹、长文件切开、已有字幕重做、等待时间这些都有默认值，也可以改。开始和停止只作用于这一轮批量转录。超过几小时切开仍只写在这个脚本里，`start_client` 和 `start_server` 没有这条界面。
- 验证：`python3 -m unittest tests.test_batch_transcribe`，16 项通过。本机创建窗口后能看到地址、打开、参数、开始转录和停止转录。这次没有重跑 PyInstaller。

## v2.13.0

- **默认模型**：`config_server.py` 的 `model_type` 改为 `sensevoice`。Apple Silicon 上仍走 MLX，算在 GPU 上。神经引擎不再作为加速路线。Qwen、Fun-ASR、Paraformer 还在，改配置就能换。
- **批量转录**：先探测时长。超过 2 小时就按 2 小时切开，临时片段识别后再合并成一个 `.srt`、`.txt` 和 `.json`。不再整段试跑失败后才切。两小时及以内仍整文件送。`--no-long-fallback` 可以关掉这次预切。
- 验证：`python3 -m unittest tests.test_batch_transcribe`，13 项通过。`./build-macos.sh` 打出 arm64 的 `batch_transcribe`，`--help` 写明超过 2 小时才按 2 小时先切开。重新打开的服务端日志是 `sensevoice`、`mlx-community/SenseVoiceSmall`、`Device(gpu, 0)`。

## v2.12.0

- **批量转录**：只看同名 `.srt`。这个文件已经在就跳过，不管旁边有没有 `.txt` 或 `.json`。没有 `.srt` 就再转录一次，并留下非空的 `.srt`、`.txt` 和 `.json`。`--force` 仍会重做已有字幕的文件。
- 验证：`python3 -m unittest tests.test_batch_transcribe`，12 项通过。

## v2.11.0

- **批量转录**：`./build-macos.sh` 的完整收集目录里多一个可执行文件 `batch_transcribe`，和 `start_server`、`start_client` 放在一起。在该目录运行 `./batch_transcribe 文件夹`，服务端没开时拉起旁边的 `start_server`，每个音视频旁边留下同名 `.srt` 和 `.txt`。源码用法仍是 `python batch_transcribe.py 文件夹`。只打客户端时没有这个文件。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，103 项通过。PyInstaller 6.22.3 把完整目录打到临时目录，`batch_transcribe` 是 arm64 Mach-O。`--help` 和空目录 `--dry-run` 退出码都是 0。正在听 6016 的 `start_server` 没有重写，只把新的 `batch_transcribe` 放进 `dist/CapsWriter-Offline`。


## v2.10.1

- **本地编译**：`./build-macos.sh` 不再停在没有 PyInstaller 的系统 `python3` 上。它会继续找仓库 `.venv`、`pyinstaller` 旁边的 Python，以及 `python3.14`。找到能 `import PyInstaller` 的才拿来编译。一个都没有时，错误里列出试过的解释器和原因。系统自带的 `python3` 不够，需要带 PyInstaller 的 Python 3.14。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，97 项通过。选中的解释器是 `/tmp/capswriter-macos-test/bin/python`。这次没有重跑 PyInstaller。


## v2.10.0

- **本地编译**：Apple Silicon 上用 `./build-macos.sh` 打出 `dist/CapsWriter-Offline` 的 `start_server` 和 `start_client`。只打客户端用 `./build-macos.sh client`。`./clean-macos.sh` 只删除仓库里的 `build` 和 `dist`。这两个程序还被占用时不删除，也不开始编译。`models` 和仓库外的路径不动。仍然不生成 `CapsWriter.app`。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，93 项通过。这次没有重跑 PyInstaller，收集目录里的 `start_client` 和 `start_server` 还在。


## v2.9.6

- **本地编译**：不再生成 `CapsWriter.app` 和 `CapsWriter Server.app`。这两个薄启动器双击起不来，也没有托盘。收集目录只留 `start_client` 和 `start_server`。客户端带起服务端时运行旁边的 `start_server`，不再 `open` 那个 app。菜单栏仍由 `start_client` 提供。不做签名公证。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，83 项通过。收集目录里已经没有这两个 app，`start_client` 和 `start_server` 还在。


## v2.9.5

- **菜单栏**：状态项仍使用固定名字 CapsWriter。控制中心把它排到屏幕外时，菜单栏空档里会出现同一个菜单的按钮。这次按钮在 x=1095，紧挨麦克风图标左边，没有盖住它。点开能看到日志、热词和退出，Esc 关掉。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，81 项通过。17:20 点开 x=1095 的按钮，菜单里有日志、热词、退出，随后按 Esc 关闭，没有点「全部退出」。14:24 的听写记录仍在：前台是「文本编辑」，日记是「今天天气很好。今天天气很好。」
- **本地编译**：PyInstaller 6.22.3、Python 3.14.10 重新打出 arm64 Mach-O：`dist/CapsWriter-Offline/start_server`、`start_client`，以及未签名公证的 `CapsWriter.app`、`CapsWriter Server.app`，短版本 2.9.5。`codesign` 只有 adhoc，没有 TeamIdentifier。`core`、`models` 仍是指向仓库的绝对软链接。`internal/libjaccl.dylib` 和 `internal/mlx/lib/mlx.metallib` 都在。短跑打包后的服务端，日志是「模型文件检查通过 (qwen_asr, mlx)」和 `backend=mlx repo=mlx-community/Qwen3-ASR-1.7B-8bit device=Device(gpu, 0)`，随后继续听 6016。


## v2.9.4

- **权限**：没有辅助功能或输入监控时，启动会在主线程请求系统把当前程序列进这两处。开关不会被程序打开。麦克风线程不再直接发这个请求，避免系统对话框不出现。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，79 项通过。测试用假的系统接口，没有弹出授权框。PyInstaller 6.22.3 重新打出 arm64 Mach-O，`CapsWriter.app` 和 `CapsWriter Server.app` 的短版本是 2.9.4，仍然没有签名公证。A1、A2 仍然没有勾。


## v2.9.3

- **辅助功能**：启动时如果没有辅助功能权限，会请系统把当前程序列进「隐私与安全性 > 辅助功能」。开关不会被程序打开。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，77 项通过。测试用假的系统接口，没有弹出授权框。系统设置里辅助功能列表当时没有 `start_client`，终端是关的。PyInstaller 重新打出未签名的 2.9.3。A1、A2 仍然没有勾。


## v2.9.2

- **前台应用**：松开后不再连着三次警告「没有自动化权限」。应用名改由 NSWorkspace 读取，不申请自动化权限。NSWorkspace 不可用时再问 lsappinfo。两边都读不到时，同一进程只警告一次，听写继续。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，76 项通过。沙箱外读到前台应用名，没有发出警告。PyInstaller 6.22.3 重新打出 arm64 Mach-O，`CapsWriter.app` 的短版本是 2.9.2，仍然没有签名。`internal/AppKit` 在包里。A1、A2 仍然没有勾。


## v2.9.1

- **空结果**：模型返回的文本是空的时候，终端写「识别结果为空」，不再把整个 `STTOutput(...)` 印出来，录音文件名也不再带上这段对象文本。
- **虚拟声卡**：默认输入打不开、而且可用输入里没有麦克风时，会说明当前设备不是麦克风，录进去的是静音。录音峰值低于 -60 dB 时，松开后写明这段录音是静音。
- **权限提示**：打包后的 `start_client` 被拒绝辅助功能或输入监控时，提示里写 `start_client`。用源码跑时仍写当前终端。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，73 项通过。JBL Quantum Stream 上 2.05 秒录音，模型输出「一二三四五六七。」，格式化后是 `1234567`。在这之前 Virtual Audio 的两段录音平均音量是 -91 dB。A1、A2 仍然没有勾。PyInstaller 6.22.3 重新打出 arm64 Mach-O，`CapsWriter.app` 的短版本是 2.9.1，仍然没有签名。

## v2.9.0

- **单实例**：Darwin 上打开客户端会带起没在跑的服务端，并等到它开始监听。再运行一次 `start_server` 退出码 0，提示「服务端已在运行」，不会再加载一份模型。再运行一次客户端会停在「已在菜单栏」，不再登记一套快捷键；带上文件则交给已经在菜单栏里的那一个。关掉客户端时服务端还在。菜单「全部退出」只向锁里记下、且命令行含 `start_server` 或 `CapsWriter Server` 的进程发 SIGTERM。
- **本地编译**：PyInstaller 6.22.3、Python 3.14.10 打出 arm64 Mach-O：`dist/CapsWriter-Offline/start_server`、`start_client`，以及未签名的 `CapsWriter.app`、`CapsWriter Server.app`，版本 2.9.0。两者都是 `LSUIElement`，`LSMultipleInstancesProhibited` 为 false。只有客户端写了麦克风用途。启动器是 `exec` 旁边的二进制，没有 `open -n`。`models`、`core`、`logs` 仍是指向仓库的绝对软链接。`internal/libjaccl.dylib` 和 `internal/mlx/lib/mlx.metallib` 都在。`codesign` 显示 completely unsigned。
- **怎么启动**：请直接运行收集目录里的 `start_server` 和 `start_client`。用 `open` 打开未签名 app 时，进程停在 dyld 的 `__open`，内存只有一百多 KB，不听 6016。这不是签名公证的 app。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，69 项通过。打包后的 `./dist/CapsWriter-Offline/start_server` 日志是 `backend=mlx repo=mlx-community/Qwen3-ASR-1.7B-8bit device=Device(gpu, 0)`，并监听 `0.0.0.0:6016`。第二次启动退出码 0，父进程不变。客户端版本 2.9.0，连上 `ws://127.0.0.1:6016`，没有再拉起服务端。客户端结束后 6016 仍由原服务端占用。`stop_recorded_server` 发出 SIGTERM 后，服务端日志写「再见！」，退出码 0，6016 释放，子进程也没了。菜单栏客户端收不到 SIGTERM。没有输入监控和辅助功能权限，文字没有上屏。A1、A2 仍然没有勾。

## v2.8.1

- **会议录音**：约 10 分钟的中文会议，txt 保留标点并分行，不再收成没有标点的一行。srt 有多条，时间单调，最后一条的结束时间不超出音长。
- **数字**：「五五十套」写成 50套，不再变成 5510。「第三一个」保留成第3一个，不再变成第31个。没有顿号的「三百五百」分成 300 和 500，不再变成 350100。已经分开的多位数字不再被空格粘成一个数。五十五、三百五、二十一个仍然按原来的数字转换。
- ffmpeg 解码失败时，日志带上 stderr 尾部，不再只剩退出码。
- 验证：`/tmp/capswriter-macos-test/bin/python -m unittest tests.test_meeting_regressions tests.test_macos_port tests.test_batch_transcribe tests.test_build_support -v`，50 项通过。同一份 605.77 秒 m4a 在临时目录重跑：txt 89 行，srt 89 条，最后结束 605.92 秒。文本里有 50套、第3一个、300、500，没有 5510、第31、350100。`logs/server_latest.log` 是 `backend=mlx repo=mlx-community/Qwen3-ASR-1.7B-8bit`，分片写「文件时间轴来自对齐器」。原录音和对照 txt 没有改。A1、A2 仍然没有人在「文本编辑」里看过。
- **本地编译**：PyInstaller 6.22.3、Python 3.14.10 重新打出 arm64 Mach-O：`dist/CapsWriter-Offline/start_server`、`start_client`，以及 `dist/CapsWriter-Offline-Client/start_client`。运行目录仍是指向仓库的绝对软链接。`internal` 里有 `libjaccl.dylib` 和 `mlx.metallib`。短跑打包后的服务端，日志是「模型文件检查通过 (qwen_asr, mlx)」和 `backend=mlx repo=mlx-community/Qwen3-ASR-1.7B-8bit device=Device(gpu, 0)`，随后连同子进程关掉，6016 没有继续占用。这不是签名公证的 `.app`。

## v2.8.0

- **Apple Silicon**：M 系列可以从源码跑。SenseVoice、Fun-ASR-Nano、Qwen3-ASR 和对齐器走 MLX / Metal。`model_backend=onnx` 时 SenseVoice 试 CoreML，失败再退 CPU。Paraformer 和缺标点时的标点模型同样能开 CoreML 就开。Intel Mac 除外。
- 听写默认按住右 Option，松开后粘贴，不吞噬 CapsLock。没有麦克风权限、并且列不出输入设备时提示去系统设置，进程不退出。默认输入编号是 -1 但还能看到输入设备时，日志写出编号，约 2 秒打不开就跳过，不把这件事说成没有麦克风权限。没有辅助功能权限时文字留在提示里。
- Windows 的 DirectML、CapsLock 抑制和 `nvidia-smi` 锁频率保持原样。Mac 上跳过锁频率。
- **本地编译**：Darwin 上可以打出 arm64 Mach-O 的 `start_server` 和 `start_client`。不用 UPX，不收 Windows 图标路径，不收 CUDA / DirectML。运行目录是指向仓库的绝对软链接。MLX 权重目录在就通过检查，不再拿旁边不存在的 ONNX / GGUF 挡启动。这不是签名公证的 `.app`。
- 验证：`python3 -m unittest discover -s tests -p 'test_*.py'`，36 项通过。默认输入编号是 -1 时，假设备会在约 2 秒后被跳过，提示里不出现「没有麦克风权限」。Mac mini M4、16GB、macOS 26.7.1 上断网复跑：SenseVoice 6.23 秒中文，RTF 0.027 然后 0.006；Qwen3-ASR 1.7B 10 秒中文，RTF 0.085 然后 0.086，日志是 `Device(gpu, 0)`。`model_backend=onnx` 时，SenseVoice 默认的 `CPU` 被改成 CoreML，编码器和解码器会话都是 `CoreMLExecutionProvider`，一段中文文本非空。强制 CoreML 创建失败后，会话退回 `CPUExecutionProvider`。Fun-ASR 和 Qwen 没有用 ONNX 交差。客户端可以启动并停在菜单栏：提示写右 Option，`alt_gr` 会对上配置里的 `alt_r`。没有麦克风权限时提示去系统设置，进程不退出。没有输入监控和辅助功能时只写日志。菜单进程里不再开 Tk，也不再因为重复监视仓库根目录抛出 FSEvents 异常。还没有人在「文本编辑」里按住右 Option 看文字出现。同一套 unittest 后来是 41 项通过。PyInstaller 6.22.3、Python 3.14.10 编出上述两个 Mach-O。短跑打包后的服务端，模型检查通过，日志是 `backend=mlx repo=mlx-community/Qwen3-ASR-1.7B-8bit device=Device(gpu, 0)`。客户端短跑后已关掉。

## v2.7

- **批量转录**：新增 `batch_transcribe.py`。对文件夹递归转录音视频，在同目录留下同名 `.srt` 和 `.txt`。已有有效字幕和文本的文件会跳过；单个失败不影响后续文件。默认走现有的流式文件转录，不再先导出整段 WAV。
- 验证：`python3 -m unittest tests.test_batch_transcribe`，6 项通过。真实音视频仍要本机服务端和 ffmpeg，脚本的 dry-run 能列出待转录文件。

## v2.6

- **GPU 预加速**：服务端新配置（默认关闭），适用于 Nvidia 独显，录音开始时主动锁定显存高频率，大幅降低模型转录延迟至 0.1s
- **标点处理优化**：仅对 8 词以内的结果去除末尾标点，长句不再误伤；可通过配置 config_client.py 指定某些程序强制去除标点
- **带延迟的附加回车**：用于同花顺等场景，输入股票名后等待 0.5s 自动回车切换，可在 config_client.py 配置
- **角色功能简化**：角色功能简化为单一开关；默认角色改用 DeepSeek API，方便新用户填入密钥后直接体验
- **ITN 增强**：连续多数字转换更鲁棒
- **活动窗口日志**：每次识别后通过 debug 日志输出当前活动窗口名，方便用户配置 paste_apps
- **标点模型容错**：取消强制检查，加载失败时静默回退，避免启动受阻
- **热词使用体验**：右键菜单点击「热词」直接打开 hot.txt 文件，不再弹窗
- **重启菜单**：托盘右键新增「重启」选项，便于修改配置后快速重启生效
- **集成显卡兼容**：加入调试性配置项，集显出问题时可通过禁用 feature 解决
- **Windows Terminal 适配**：支持隐藏 Windows Terminal 控制台窗口

## v2.5

- **引入 [Qwen3-ASR-1.7B](https://github.com/HaujetZhao/Qwen3-ASR-GGUF)**：140ms 极速推理，准确率夯爆。Decoder Vulkan 加速默认打开，需占 1.6GB 显存。显卡空闲时，会降低显存频率，冷启动转录延迟升至 300ms。若用管理员权限运行 `nvidia-smi -lmc 9000` 锁定显存不降频，实测 RTX5050 转录延迟可降至 100ms
- **集成 Force Aligner**：辅助 Qwen3-ASR 支持时间戳，按需加载、超时释放，仅文件转录时占用资源
- **热词别名**：热词支持用 `|` 分隔定义多个别名，
- **角色别名**：`name` 用 `|` 分隔定义多个别名，解决 ASR 对角色名识别不准的问题
- **移除纠错历史**：热词别名已能覆盖纠错历史的需求，移除 `hot-rectify.txt` 及相关逻辑
- **文件转录支持热词**：文件转录现在也可以使用热词功能
- **语言配置**：`config_client.py` 新增 `language` 选项，支持指定识别目标语言
- **架构重构**：进行了大量重构，方便后续维护
- **日志优化**：只保留一份日志文件

## v2.4

- **改进 [Fun-ASR-Nano-GGUF](https://github.com/HaujetZhao/Fun-ASR-GGUF) 模型，使 Encoder 支持通过 DML 用显卡（独显、集显均可）加速推理，Encoder 和 CTC 默认改为 FP16 精度，以便更好利用显卡算力**，短音频延迟最低可降至 200ms 以内。
  - 若用管理员权限运行 `nvidia-smi -lmc 9000` 锁定显存不降频，实测 RTX5050 转录延迟可降至 100ms
- 服务端 Fun-ASR-Nano 使用单独的热词文件 hot-server.txt ，只具备建议替换性，而客户端的热词具有强制替换性，二者不再混用
- 可以在句子的开头或结尾说「逗号、句号、回车」，自动转换为对应标点符号，支持说连续多个回车。
- Fun-ASR-Nano 加入采样温度，避免极端情况下的因贪婪采样导致的无限复读
- 服务端字母拼写合并处理

## v2.3

- **引入 [Fun-ASR-Nano-GGUF](https://github.com/HaujetZhao/Fun-ASR-GGUF) 模型支持，推理更轻快**
- 重构了大文件转录逻辑，采用异步流式处理
- 优化中英混排空格
- 增强了服务端对异常断连的清理逻辑

## v2.2

- **改进热词检索**：将每个热词的前两个音素作为索引进行匹配，而非只用首音素索引。
- **UDP广播和控制**：支持将结果 UDP 广播，也可以通过 UDP 控制客户端，便于做扩展。
- **Toast窗口编辑**：支持对角色输出的 Toast 窗口内容进行编辑。
- **多快捷键**：支持设置多个听写键，以及鼠标快捷键，通过 pynput 实现。
- **繁体转换**：支持输出繁体中文，通过 zhconv 实现。

## v2.1

- **更强的模型**：内置多种模型可选，速度与准确率大幅提升。
- **更准的 ITN**：重新编写了数字 ITN 逻辑，日期、分数、大写转换更智能。
- **RAG 检索增强**：热词识别不再死板，支持音素级的 fuzzy 匹配，就算发音稍有偏差也能认出。
- **LLM 角色系统**：集成大模型，支持润色、翻译、写作等多种自定义角色。
- **纠错检索**：可记录纠错历史，辅助LLM润色。
- **托盘化运行**：新增托盘图标，可以完全隐藏前台窗口。
- **完善的日志**：全链路日志记录，排查问题不再抓瞎。


## v1.0 

- 通过分段识别和去重，实现了支持无限时长语音的转写
- 客户端支持转写音视频文件为 srt 字幕，只需将音视频文件拖动到客户端 exe 上打开即可

## v0.6 


- 新增日记功能，将每日的录音结果保存在一个 Markdown 文件中
- 新增关键词日记功能，每日的以关键词开头的录音结果会保存在特别的 Markdown 文件中
- 新建录音文件夹的时候，会复制一个 Python 辅助脚本，用于清理没有被 Markdown 文件引用的附件，这样一来，通过编辑 Markdown 日记就可以清理不需要保存的录音
- 新增定义录音文件保存目录
- 默认保存48000采样率高品质录音录音，如果用户安装了 FFmpeg 则保存为 mp3 格式，否则保存为 wav 格式
- 输入方式改为模拟 Ctrl + V 粘贴，粘贴完后恢复剪贴板内容
- 使用 rich 库输出彩色文字，尽量在各种终端达到一致的显示效果

## v0.5 

- 修改热词文件后，不用重启客户端，就可以动态更新热词了。

## v0.4

- 为客户端加入了三种热词功能：中文、英文、自定义
- 改进了对中文数字的搜索，当数字的左侧或者右侧有英文时，就一定会被选中。
- 改进了中英空格排版，能够正常输出 iPhone 4s 这样的词语。


## v0.3 

- 客户端当音频设备名不可 utf-8 解码时，不再闪退
- 客户端添加配置可以编辑修改，要消除识别结果末尾哪些标点
- 客户端添加配置可以修改快捷键
- 客户端添加配置可以修改快捷键触发的时间阈值
- 客户端连接中断会自动进行重试
- 客户端提示当前所用的快捷键
- 服务端对识别结果，中英文混排进行空格校正
- 当地址无法被绑定时提示问题，而不是直接闪退


## 起源

**2020年10月**，因手机上的语音输入法很好用，但电脑上却没有足够好用的语音输入法，我手写了一个工具 **[CapsWriter](https://github.com/HaujetZhao/CapsWriter)**，通过长按大写锁定键录音，松开后，调用阿里云的一句话识别 API，识别后上屏。12月的时候，还加入图形化界面。但当时大学宿舍的校园网经常抽风，没有稳定的网络环境，转录延迟飘忽不定。有时候说完话了，等了好几秒，才发现 WiFi 没有连接，毁心态。但是当时并没有识别率能满足要求的离线中文 ASR 模型。

后来 Whisper 发布，中文识别率确实不错，但是模型延迟很高，无法满足本地语音输入。

到了**2023年5月**，在B站看到了 [极客湾](https://space.bilibili.com/25876945) 的视频 [我们做了个能对话的AI派蒙，免费给大家玩！](https://www.bilibili.com/video/BV1bm4y117ba/) ，他们实现的效果非常好，其中提到 ASR 模型用了阿里 [FunASR](https://github.com/modelscope/FunASR) 团队发布的开源 [Paraformer](https://www.modelscope.cn/models/iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8358-tensorflow1) 模型，于是就拿来测试了下，果然识别准确率很棒、延迟超低，于是弃坑 **[CapsWriter](https://github.com/HaujetZhao/CapsWriter)** ，立马新开了 **[CapsWriter-Offline](https://github.com/HaujetZhao/CapsWriter-Offline)** ，用 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 调用 Paraformer 进行转录，效果非常好。

**2025年12月09日**，我看到阿里 [FunASR](https://github.com/modelscope/FunASR) 团队开源了 [Fun-ASR-Nano](https://www.modelscope.cn/models/FunAudioLLM/Fun-ASR-Nano-2512) 模型，拿来一测，果然准确率又上一个台阶，在 sherpa_onnx 支持后，我赶紧更新了 CapsWriter-Offline v2.1，一次性加入了 SenseVoice-Small 和 Fun-ASR-Nano 模型的支持。但问题是当时 sherpa_onnx 是用 ONNX 实现的 Fun-ASR-Nano，速度有些慢。

我研究了 Fun-ASR-Nano 的架构，发现它的 Decoder 是 LLM 架构，而推理 LLM 最快的是 [LLama.cpp](https://github.com/ggml-org/llama.cpp) 。虽然我编程能力差，但刚好此时，Google 推出了 Antigravity AI 编程 IDE，里面有 Gemini 和 Claude 模型，在他们的帮助下，我成功写出了 [Fun-ASR-GGUF](https://github.com/HaujetZhao/Fun-ASR-GGUF)，用 onnx 和 gguf 格式混合运行 Fun-ASR-Nano，用 [LLama.cpp](https://github.com/ggml-org/llama.cpp) 加速它的 LLM Decoder 部分，在我的笔记本上实现了最快的推理速度：

| 设备 | RTF |
|------|-----|
| GPU RTX5050  | 0.025 |
| CPU U9-285H  | 0.1 |

**2026年01月21日**，[Qwen3-TTS](https://www.modelscope.cn/collections/Qwen/Qwen3-TTS) 开源发布了，生成效果极其优异，让我特别想要，但官方版本推理速度很慢，于是基于 [Fun-ASR-GGUF](https://github.com/HaujetZhao/Fun-ASR-GGUF) 的加速推理经验，在 Antigravity 的帮助下，我又实现了 [Qwen3-TTS-GGUF](https://github.com/HaujetZhao/Qwen3-TTS-GGUF) ，也是用 [LLama.cpp](https://github.com/ggml-org/llama.cpp) 加速它的 LLM Decoder 部分。

**2026年01月28日**，间隔没几天，[Qwen3-ASR](https://www.modelscope.cn/collections/Qwen/Qwen3-ASR) 开源发布了，本来没抱太大预期的，但下载 1.7B 一测后，又给我震惊了，准确率竟比 Fun-ASR-Nano 还上一个台阶，能吊打闭源模型！于是在 [Qwen3-TTS-GGUF](https://github.com/HaujetZhao/Qwen3-TTS-GGUF) 经验的帮助下，我马不停蹄地实现了 [Qwen3-ASR-GGUF](https://github.com/HaujetZhao/Qwen3-ASR-GGUF) 加速推理，实现了最快的推理速度：

| 设备 | RTF |
|------|-----|
| GPU RTX5050  | 0.05 |
| CPU U9-285H  | 0.2 |

这就是 CapsWriter-Offline 大致的来路。总体就是这几个组件：

- 模型推理
- 热词替换
- 按键监听与录音

当前只有 Windows 的打包，是因为我只有 Windows 电脑，没有 Linux 与 MacOS 的需求。在 Vibe Coding 时代，我相信需求的小伙伴在 Claude Code 的帮助下，也能在其系统上做出类似功能的实现。
