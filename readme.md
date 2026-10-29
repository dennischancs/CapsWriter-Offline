# CapsWriter-Offline

![demo](assets/demo.png)

> **按住 CapsLock（Mac 上是右 Option）说话，松开就上屏。就这么简单。**

**CapsWriter-Offline** 是一个**完全离线**语音输入工具。Windows 用 DirectML。Apple Silicon 从源码跑，识别走 MLX / Metal。

## ✨ 核心特性

-   **语音输入**：按住 `CapsLock键` 或 `鼠标侧键X2` 说话，松开即输入，超低延迟，默认去除末尾逗句号。支持对讲机模式和单击录音模式。
-   **文件转录**：音视频文件往客户端 exe 一丢，字幕 (`.srt`)、文本 (`.txt`)、时间戳 (`.json`) 统统都有。
-   **数字 ITN**：自动将「十五六个」转为「15~16个」，支持各种复杂数字格式。
-   **热词替换**：在 `hot.txt` 记下偏僻词，通过音素模糊匹配，相似度大于阈值则强制替换。
-   **正则替换**：在 `hot-rule.txt` 用正则或简单等号规则，精准强制替换。
-   **LLM 角色**：预置了润色、小助理等角色，当识别结果的开头匹配任一角色名字时，将交由该角色处理。
-   **托盘菜单**：右键托盘图标即可添加热词、复制结果、清除LLM记忆。
-   **C/S 架构**：服务端与客户端分离，虽然 Win7 老电脑跑不了服务端模型，但最少能用客户端输入。
-   **日记归档**：按日期保存你的每一句语音及其识别结果。
-   **录音保存**：所有语音均保存为本地音频文件，隐私安全，永不丢失。

**CapsWriter-Offline** 的精髓在于：**完全离线**（不受网络限制）、**响应极快**、**高准确率** 且 **高度自定义**。我追求的是一种「如臂使指」的流畅感，让它成为一个专属的一体化输入利器。无需安装，一个U盘就能带走，随插随用，保密电脑也能用。

以下为支持的模型：

| 引擎名 | 准确性 | 速度 | 格式 | 显卡加速 |
|------|-------|------|------|---------|
| Paraformer | ★★★☆☆ | ★★★★★ | ONNX | ❌ |
| SenseVoice-Small | ★★★☆☆ | ★★★★★ | ONNX | ✅ |
| Fun-ASR-Nano | ★★★★☆ | ★★★★☆ | ONNX + GGUF | ✅ |
| Qwen3-ASR | ★★★★★ | ★★★☆☆ | ONNX + GGUF | ✅ |


性能参考（20s 音频转录延迟）：

| 模型 | CPU U9-285H | GPU RTX5050 |
|------|------------|------------|
| Paraformer | 0.6s | - |
| SenseVoice-Small | 0.6s | 0.15s |
| Fun-ASR-Nano | 2.0s | 0.5s |
| Qwen3-ASR-1.7B | 4.0s | 1.0s |

Apple Silicon 上，SenseVoice、Fun-ASR-Nano、Qwen3-ASR 使用 `models/mlx/` 里的 MLX 权重。上表的 ONNX + GGUF 和 DirectML 仍是 Windows 的路径。

详细功能说明请参考 [`docs/`](docs/) 目录：
- [环境依赖安装说明](docs/环境依赖安装说明.md) — VC++ 运行库、FFmpeg 安装
- [热词功能如何使用](docs/热词功能如何使用.md) — 热词替换、规则替换、自定义短语
- [角色功能如何使用](docs/角色功能如何使用.md) — LLM 角色配置、输出模式、创建新角色
- [识别语言如何配置](docs/识别语言如何配置.md) — 各引擎语言支持范围与配置方法
- [文件转录功能如何使用](docs/文件转录功能如何使用.md) — 拖拽转字幕、时间戳对齐
- [显卡加速的若干问题](docs/显卡加速的若干问题.md) — DirectML、Vulkan 加速配置
- [模型下载的若干问题](docs/模型下载的若干问题.md) — 引擎选择、模型下载、目录结构
- [常见问题](docs/常见问题.md) — FAQ
- [更新日志](docs/CHANGELOG.md)
- [模型对比](模型对比.md) — 这台 Mac mini M4 上四个 MLX 模型的耗时、字错率和 GPU 占用，没有录音正文
- [优化计划](优化计划.md) — SenseVoice Small 要把字错率收到 10% 以内；神经引擎只做一次对照，不拿它提精度

当前版本是 `2.36.0`，只认 `pyproject.toml`。


## 💻 平台支持

目前保证：

- **Windows 10/11 (64位)**：DirectML、CapsLock 长按抑制，和原来一样。
- **Apple Silicon（M 系列）**：可以从源码跑。默认按住右 Option 说话，松开后粘贴上屏。SenseVoice、Fun-ASR-Nano、Qwen3-ASR 和对齐器走 MLX，Metal 由 MLX 使用。Paraformer 和标点可以试 CoreML。Intel Mac 除外。打开客户端会带起没在跑的服务端；再打开一次不会再加载一份模型。不带参数运行 `./build-macos.sh`，只打出未签名的 `dist/CapsWriter.app`，不打 dmg。Swift 界面、服务端、批量转录和复制进去的模型都在这个 app 里，不是指回仓库的符号链接。要安装盘就运行 `./build-macos.sh dmg`，只打出 `dist/CapsWriter-2.36.0.dmg`，成功后旁边不再留下 app。打开 dmg，把 CapsWriter 拖到「应用程序」。`./build-macos.sh client` 只打客户端，不组装 app，也不打 dmg。两个参数不能一起写。清理运行 `./clean-macos.sh`，一次删掉 `build`、`dist`、Swift 的 `.build` 和 `/tmp/cw-swift`。仓库里的 `models` 不动。这些程序还在跑时不删，也不开始编译。系统自带的 `python3` 不够。`./build-macos.sh` 用本机 miniforge 的 `capswriter` 环境，这个环境里要有 PyInstaller。菜单栏由这个 app 提供。默认模型是 SenseVoice Small，走 MLX 的 GPU。批量转录在收集目录运行 `./batch_transcribe` 打开窗口，或 `./batch_transcribe 文件夹` 直接转。源码是 `python batch_transcribe.py`。地址栏可以粘贴，也可以从 Finder 拖入一个文件或文件夹。窗口里可以选日志等级，也可以在 SenseVoice Small、Fun-ASR Nano、Qwen3-ASR 1.7B、Qwen3-ASR 0.6B、Paraformer 之间换模型。一换就写入服务端配置。server 标签「现在这样跑」里的模型和 Qwen 规格，跟批量菜单显示的是同一个值：`auto` 按内存展开成 1.7b 或 0.6b，选了具体规格就显示那个规格。client 标签没有模型项，不跟着变。下次开始转录前，如果服务端进程里还是上一个模型，会先停掉再拉起。配置文件已经改过也一样。字幕写好后状态离开「转录中」。第一次关闭会问缩小到菜单栏还是退出，选过一次不再问。退出会停掉后台服务端。日志行前面是 `[年-月-日 时:分:秒.毫秒]`。点停止会马上中断这一轮，已经写好的字幕留下，后面的文件不再开始；再点一次强制结束。本来就开着的服务端不会被卸掉。日志贴在底部时跟着最新一行，往上翻就停住，窗口可以照常拖动。批量进行时显示当前第几个、一共几个，跳过的文件不算进去。已经写好的同名 `.srt` 会跳过，不复写。空的或没写完的下次再做。中断后重新开始会再遍历，已有成品保持原样，只从未做完的文件继续。没有成品则生成 `.srt`、`.txt` 和 `.json`。超过 2 小时的文件先按 2 小时切开，再合并成这三份。不做签名公证。
- **Linux**：暂无环境进行测试和打包，无法保证兼容性。

[LazyTyper](https://lazytyper.com/) 和 [闪电说](https://shandianshuo.cn/) 也是很优秀的作品，都有离线引擎，都支持 Windows Linux 与 MacOS，并都有漂亮的图形化页面，推荐使用。

CapsWriter 的特别之处在于追求：

- 无感输入
- 完全离线，不受网络约束
- 低延迟，尽量做到硬件极限的最快速度
- 高度自定义的热词系统


## macOS 上为什么不用 Tk

macOS 上的菜单栏、权限、右 Option、粘贴和批量窗口用 Swift 写。同一个窗口里，批量转换是首页，另外两个标签叫 client 和 server，能改 `config_client.py` 和 `config_server.py` 里的全部设置。推荐值是灰的，双击并确认后才能改。识别仍是现在的 Python `start_server`，走 `127.0.0.1:6016`。Mac 上不再装 `tkhtmlview`、`tkinterdnd2`，也不再为提示窗口装 `python-tk`。不带参数运行 `batch_transcribe.py` 不会打开 Tk，要打开 `dist/CapsWriter.app`。Windows 的 Tk 提示还在。

慢的不是模型。SenseVoice、Fun-ASR、Qwen3-ASR 在 Apple Silicon 上仍走 MLX / Metal，Swift 不重写识别。差在界面。在 macOS 上，Tk 不能一点就开，跑起来还会卡死。Swift 的窗口先出来，转录时菜单和按钮也还能动。

Tk 是 Python 的 `tkinter`，底下是 Tcl/Tk。Mac 上它不走系统自己的界面，要再套一层 Aqua，经 `_tkinter` 跟 Python 说话。Homebrew 的 Python 还要另装 `python-tk`，否则提示窗口起不来。进程得先把 Python 和这套库拉起来，窗口才可能出现。服务端若正在加载模型，准备又和画窗口挤在同一条主线程上，界面要等模型好了才看得到。后来改成先把窗口画出来，灯先是黄的，开始要等绿灯。即便这样，也要等 Python 和 Tk 就绪，做不到瞬间打开。

Swift 用的是系统自己的 AppKit / SwiftUI。启动时先把窗口放到前面，再去准备服务端。模型还在加载时窗口已经在。重画、关闭和菜单栏都在系统界面上，不跟识别挤在一起。

跑起来卡死，是因为 macOS 只允许主线程碰 Tk。转录若在别的线程里改窗口，状态会停在「转录中」，关闭也没反应。后来改成工作线程只把结果放进队列，主线程再关掉窗口。菜单栏也要这条主线程，不能再开第二套事件循环。菜单栏和 Tk 不能放在同一个进程里，所以菜单还在跑的时候，热词之类的提示不开 Tk 窗口。主线程一旦去等模型、抽音频或刷日志，按钮和关闭就冻住。日志若每零点几秒插一行，主线程一直在改文本，窗口被拉得很长，点什么都慢。

Swift 外壳和识别不在同一个进程里。界面只管窗口、菜单栏、权限、快捷键和粘贴。识别、ffmpeg 和 WebSocket 在旁边。client 和 server 直接读两个配置文件，不导入打包后的 `batch_transcribe`。发送进度和转录进度各自只占一行，数字从这段音频的 0、60、120 改到结尾，完成时间留在这一行上。处理耗时另起一行。完成、失败和文件名仍马上留下。所以转录的时候界面仍然顺。要开的 macOS 窗口就是 `./build-macos.sh` 打出的 `dist/CapsWriter.app`。安装盘是另一个命令：`./build-macos.sh dmg`。


## 🎬 快速开始

1.  **准备环境**：确保安装了 [VC++ 运行库](https://learn.microsoft.com/zh-cn/cpp/windows/latest-supported-vc-redist)。若要使用文件转录功能，还需安装 [ffmpeg](https://ffmpeg.org/download.html) 并确保其在系统 PATH 中。
2.  **下载解压**：下载 [Latest Release](https://github.com/HaujetZhao/CapsWriter-Offline/releases/latest) 里的软件本体，再到 [Models Release](https://github.com/HaujetZhao/CapsWriter-Offline/releases/tag/models) 下载模型压缩包，将模型解压，放入 `models` 文件夹中对应模型的文件夹里。
3.  **启动服务**：双击 `start_server.exe`，**它会自动最小化到托盘菜单**。
4.  **启动听写**：双击 `start_client.exe`，**它会自动最小化到托盘菜单**。
5.  **开始录音**：按住 `CapsLock键` 或 `鼠标侧键X2` 就可以说话了！


## ⚙️ 个性化配置

所有的设置都在根目录的 `config_server.py` 和 `config_client.py` 里，可直接编辑。


## 🛠️ 常见问题


**Q: 为什么按了没反应？**  
A: 请确认 `start_client.exe` 的黑窗口还在运行。若想在管理员权限运行的程序中输入，也需以管理员权限运行客户端。

**Q: 为什么识别结果没字？**  
A: 到 `年/月/assets` 文件夹中检查录音文件，看是不是没有录到音；听听录音效果，是不是麦克风太差，建议使用桌面 USB 麦克风；检查麦克风权限。

**Q: 想要隐藏黑窗口？**  
A: 点击托盘菜单即可隐藏黑窗口。

**Q: 如何开机启动？**  
A: `Win+R` 输入 `shell:startup` 打开启动文件夹，将服务端、客户端的快捷方式放进去即可。

更多问题请参阅 [docs/常见问题.md](docs/常见问题.md)。


## 🚀 我的其他优质项目推荐

| 项目名称 | 说明 | 体验地址 |
| :--- | :--- | :--- |
| [**IME_Indicator**](https://github.com/HaujetZhao/IME_Indicator) | Windows 输入法中英状态指示器 | [下载即用](https://github.com/HaujetZhao/IME_Indicator/releases/latest/download/IME-Indicator.exe) |
| [**Rust-Tray**](https://github.com/HaujetZhao/Rust-Tray) | 将控制台最小化到托盘图标的工具 | [下载即用](https://github.com/HaujetZhao/Rust-Tray/releases/latest/download/Tray.exe) |
| [**Gallery-Viewer**](https://github.com/HaujetZhao/Gallery-Viewer-HTML) | 网页端图库查看器，纯 HTML 实现 | [点击即用](https://haujetzhao.github.io/Gallery-Viewer-HTML/) |
| [**全景图片查看器**](https://github.com/HaujetZhao/Panorama-Viewer-HTML) | 单个网页实现全景照片、视频查看 | [点击即用](https://haujetzhao.github.io/Panorama-Viewer-HTML/) |
| [**图标生成器**](https://github.com/HaujetZhao/Font-Awesome-Icon-Generator-HTML) | 使用 Font-Awesome 生成网站 Icon | [点击即用](https://haujetzhao.github.io/Font-Awesome-Icon-Generator-HTML/) |
| [**五笔编码反查**](https://github.com/HaujetZhao/wubi86-revert-query) | 86 五笔编码在线反查 | [点击即用](https://haujetzhao.github.io/wubi86-revert-query/) |
| [**快捷键映射图**](https://github.com/HaujetZhao/ShortcutMapper_Chinese) | 可视化、交互式的快捷键映射图 (中文版) | [点击即用](https://haujetzhao.github.io/ShortcutMapper_Chinese/) |


## ❤️ 致谢

本项目基于以下优秀的开源项目：

-   [Sherpa-ONNX](https://github.com/k2-fsa/sherpa-onnx)
-   [FunASR](https://github.com/alibaba-damo-academy/FunASR)

感谢 Google Antigravity、Anthropic Claude、GLM、DeepSeek，如果不是这些编程助手，许多功能（例如基于音素的热词检索算法）我是无力实现的。

特别感谢那些慷慨解囊的捐助者，你们的捐助让我用在了购买这些优质的 AI 编程助手服务，并最终将这些成果反馈到了软件的更新里。


如果觉得好用，欢迎点个 Star 或者打赏支持：


![sponsor](assets/sponsor.jpg)	
