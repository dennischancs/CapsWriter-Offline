# PRD：把 CapsWriter 移植成 Apple Silicon 上可听写的离线输入法

- 基线：`latest` @ `84912d5`
- 本文替换上一版「用 CoreML 跑现有 ONNX、用 llama.cpp Metal 跑 GGUF」的主路线
- 怎么改见 [dev-plan.md](dev-plan.md)

## 验收清单

版本只认 `pyproject.toml` 的 `version`，现在是 `2.8.0`。做法仍在 [dev-plan.md](dev-plan.md)，不要另建 `SPEC.md` 或 `TASKS.md`。

### 已完成

- [x] 2.7.0 对一个文件夹递归转录音视频，每个文件旁边留下同名 `.srt` 和 `.txt`。两个成品都有效才跳过。一个失败，后面的继续。
- [x] 2.8.0 Windows 的 DirectML 配置和 CapsLock 抑制还在。Darwin 的依赖不会装上 `onnxruntime-directml`。
- [x] 2.8.0 `readme.md` 写明 Apple Silicon 可以从源码跑，Intel 除外。DirectML 的说明还在。
- [x] A3. 服务端日志出现 `backend=mlx`、具体仓库 ID，以及 GPU 设备。看不到 `DmlExecutionProvider`，也看不到找不到 `llama.dll`。
- [x] A4. SenseVoice 对约 5 秒中文，预热后 RTF 小于 0.3，文本非空可读。第二次不再明显慢于第一次。
- [x] A5. Qwen3-ASR 对约 10 秒中文，预热后 RTF 小于 0.5，带标点。统一内存低于 16GB，或 1.7B 加载失败时，日志写明改用 0.6B，并且仍然返回文本。
- [x] A6. 把 `model_type` 改成 `fun_asr_nano` 后，一段中文能返回带标点的文本。热词或 context 进入当次识别。这个模型失败时直接报错，不静默去加载 Windows DLL。
- [x] A7. 权重在 `models/mlx/`。断网可以再次启动。目录不存在时，错误写明缺哪个目录，而不是 `kernel32` 或 `windll`。
- [x] A8. 一条中文音视频经文件转录或 `batch_transcribe.py` 得到非空 `.srt` 和 `.txt`。时间轴单调。日志能看出时间来自对齐器。对齐失败时写明退回按字均分，不把均分说成对齐成功。
- [x] A9. `model_backend=onnx` 时，SenseVoice 仍能出文本，并尝试 CoreML，失败再退 CPU。Fun-ASR 和 Qwen 不靠这条退路交差。

### 不做

- [x] 不做 Intel Mac。
- [x] 不把客户端改写成 Swift，也不套 `mlx-audio` 的 HTTP 服务。
- [x] 不做签名公证的 `.app`，不做 Mac App Store。
- [x] 不把 llama.cpp Metal 动态库当作 macOS 主路径，不把 GGUF 导出成 CoreML。
- [x] 不移植 SenseVoice 的 CTC 热词雷达。热词保证留在客户端替换。
- [x] 不在 Mac 上吞噬 CapsLock。
- [x] 不引入 OminiX 的 Rust 组件，不为标点重写模型。

### 还没有

- [ ] A1. Mac 上启动客户端，按住右 Option 说话，松开后文字出现在「文本编辑」。不需要 root。这一步的识别可以还是 CPU，只要进程不是因为 Win32 导入退出。
- [ ] A2. 菜单栏能打开日志目录、打开热词文件、退出。没有麦克风权限、并且列不出任何输入设备时，提示去系统设置，进程不崩溃。默认输入编号是 -1、但还能列出输入设备时，日志写出这些编号，约 2 秒打不开就跳过，不把这件事说成没有麦克风权限。没有辅助功能权限时文字留在系统通知和终端里，不上屏。


不下载权重的检查用 `python3 -m unittest discover -s tests -p 'test_*.py'`。仓库 `.gitignore` 忽略 `test_*.py`，这些测试留在本地，不入库。真机听写、RTF 和系统权限只有人能看。

## 1. 要做成什么

在 M 系列 Mac 上，从源码启动服务端和客户端，按住一个键说话，松开后文字进当前焦点应用。识别走 Apple Silicon 的原生推理栈，而不是在 Windows 引擎外面套一层能 import 的兼容壳。

原生栈的分工：

| 框架 | 在本产品里干什么 | 不干什么 |
| --- | --- | --- |
| MLX | 主推理。SenseVoice、Fun-ASR-Nano、Qwen3-ASR、Qwen3-ForcedAligner 都在进程里调用 MLX | 不把客户端或界面改写成 Swift |
| Metal | MLX 的 GPU 设备。启动日志必须看到默认设备是 GPU，而不是 CPU | 不自写 shader，也不再为 macOS 维护一套 llama.cpp b10621 动态库 |
| CoreML | 没有 MLX 端口的 ONNX 图：Paraformer，以及只在缺标点时才加载的 CT-Transformer。SenseVoice 的现有 fp16 ONNX 保留为可切换退路 | 不把 GGUF 或自回归解码器导出成 `.mlpackage` |

MLX 不使用神经网络引擎。自回归解码和变长语音也不适合把 ANE 当主路径。SenseVoice 这种非自回归模型，如果以后测出 CoreML 比 MLX 更快，允许单模型切回 ONNX + CoreML，不改变默认。

Intel Mac 不在范围内。MLX 不能在 Intel 上跑。

## 2. 为什么换掉上一版主路线

上一版计划是：ONNX Runtime 的 CoreML Execution Provider 跑声学模型，同一套 ctypes 绑定换一份 `GGML_METAL=ON` 的 llama.cpp 跑解码。那样 Windows 的文件布局可以少动，但 Mac 上会同时留下三套运行时（ONNX、GGUF、以及仍然用不上的 DirectML 锁），而且这些模型的 MLX 实现已经覆盖了现在的四条主链路：

- SenseVoice：`mlx-community/SenseVoiceSmall`。非自回归，上游说明约 10 秒音频 70 毫秒量级。公开 API 给文本、语种、情绪和事件，不给 CapsWriter 现在用的 CTC token 时间戳。
- Fun-ASR-Nano：`mlx-community/Fun-ASR-Nano-2512`。支持语种和 hotwords / context。公开权重只出文本，不出可用的字级时间戳。
- Qwen3-ASR：`mlx-community/Qwen3-ASR-0.6B-8bit` 与 `Qwen3-ASR-1.7B-8bit`。片段时间是粗边界，生成 token 本身没有真实对齐。
- Qwen3-ForcedAligner：`mlx-community/Qwen3-ForcedAligner-0.6B-8bit`。字词级 `start_time` / `end_time`，这是文件字幕的时间来源。

因此 Mac 上不再加载「ONNX 编码器 + GGUF 解码器」这一对。同一个 `model_type` 在 Darwin 上换成对应的整模 MLX 权重。协议、分片、合并、热词替换、文件转录都不重写。

Paraformer 和 CT-Transformer 标点没有可接入的 Python MLX 实现。它们继续走 sherpa-onnx，能开 CoreML 就开，不能就 CPU。OminiX 的 Rust 移植不引入本仓库。

## 3. 目标

1. Apple Silicon 上 `start_server.py` 和 `start_client.py` 都能启动。不需要 root。
2. 默认后端是 MLX。日志写明 `backend=mlx`、仓库 ID、以及 MLX 默认设备为 GPU。
3. 按住快捷键说话，松开后文字出现在「文本编辑」或其他普通文本框。中文走粘贴。
4. 拖入或批量转录音视频时，旁边留下同名 `.srt` 和 `.txt`。时间轴来自 MLX 对齐器，单调、能对上字。
5. MLX 加载失败时，SenseVoice 可以退回现有 ONNX，并尝试 CoreML；再失败才退出。进程不能因为 DirectML 或 Vulkan DLL 不存在而在 import 阶段崩溃。
6. Windows 行为不变：DirectML、Vulkan、`pywin32`、CapsLock 抑制都还在。

## 4. 非目标

- 不重写识别算法，不改 WebSocket 协议，不改 `text` / `text_accu` 合并。
- 不把产品改成 Swift，也不把 `mlx-audio` 的 HTTP 服务套在外面再转一层。MLX 在现有 worker 进程里调用。
- 第一期不做签名公证的 `.app`，不做 Mac App Store。权限先授给运行 Python 的终端。
- 不承诺 8GB 内存流畅跑 Qwen3-ASR 1.7B。内存不够时自动改用 0.6B 8bit，并写日志。
- 不把 Paraformer 当成需要加速的引擎。它仍然是纪念引擎。
- 不在 Mac 上复刻 CapsLock 吞噬。系统会自己翻转这个灯，默认键必须换掉。
- 不保证 MLX SenseVoice 复现 ONNX 引擎里的 CTC 热词雷达。热词的产品保证在客户端替换，见第 8 节。

## 5. 用户能完成的事

1. **听写**。菜单栏有客户端。按住右 Option 说话，松开后文字粘贴进焦点应用。右 Option 不抑制，避免和系统键抢。
2. **服务端常驻**。模型只在服务端子进程里加载一次。菜单栏或终端能退出。日志仍在 `logs/server_latest.log`。
3. **文件与批量**。本机有 ffmpeg 时，拖入音视频，或 `python batch_transcribe.py 文件夹`，得到同名 `.srt` 和 `.txt`。字级 `.json` 仍由现有文件转录留下。
4. **换模型**。还是改 `config_server.py` 的 `model_type`：`sensevoice`、`fun_asr_nano`、`qwen_asr`、`paraformer`。Darwin 上前三个加载 MLX 权重，不是 ONNX / GGUF。要强制走 ONNX 时把 `model_backend` 设成 `onnx`。

## 6. 必须留下的部分

这些已经和平台无关，移植时不准推倒：

- 客户端 / 服务端、任务分片、`TaskPipeline`、文本合并、token 合并、热词 RAG、规则、LLM 角色、日记、UDP。
- `BaseASREngine` / `BasePuncEngine` / `BaseAlignEngine`，以及 `RecognitionResult` 的 `text`、`tokens`、`timestamps`。
- 麦克风的 `text` 拼接不依赖时间戳。文件任务只在引擎没有 `TIMESTAMPS` 时调用对齐器。MLX 引擎利用这条现成门闩，而不是另写一套字幕逻辑。
- `sounddevice`、`pyclip`、粘贴时 Darwin 用 Command+V、前台窗口的 AppleScript 分支。
- [batch_transcribe.py](batch_transcribe.py)。它不加载模型，服务端换成 MLX 之后批量结果自动走新后端。

## 7. 必须拆开的平台断点

不处理这些，Mac 上服务端即使装了 MLX 也听不了写：

- `core/client/shortcut/key_mapper.py` 无条件导入 `pynput._util.win32`。这会让完整客户端起不来。批量脚本已经绕开这条导入，听写客户端不行。
- `core/client/shortcut/shortcut_manager.py` 把逻辑放在 `win32_event_filter` 里。pynput 在 macOS 上忽略这个参数。
- `keyboard` 包用于打字、回车和复制选区（`text_output.py`、`result_processor.py`、`llm_output_typing.py`、`llm_get_selection.py`）。macOS 上它要 root，不能留在 Mac 路径里。
- `core/ui/tray.py` 在非 Windows 上直接认为托盘不可用，后面仍有 `kernel32` 调用。Mac 要走 `pystray` 的菜单栏，并且永远不碰 Win32。
- `core/ui/dialogs.py`、`toast_base.py` 里的 DPI 调用已经能吞掉 `windll` 缺失。保持这种写法，不要在 Mac 上再增加无保护的 `ctypes.windll`。
- `gpu_boost.py` 和 `empty_working_set.py` 是 Windows / NVIDIA。Darwin 上跳过，不找替代的「锁 GPU 频率」接口。
- `pyproject.toml` 把 `onnxruntime-directml`、`pywin32`、`keyboard` 写成了全平台依赖，锁文件只有 Windows cp314。Mac 装不上。

## 8. 允许和 Windows 不一样的行为

这些差异要写进日志和文档，不能当成 bug 悄悄改掉合并算法：

| 行为 | Windows 现在 | macOS |
| --- | --- | --- |
| 声学 + 解码 | ONNX 与 GGUF 两段 | 一个 MLX 模型 |
| SenseVoice 时间戳 | 引擎自带 CTC 时间，文件任务不对齐 | MLX 引擎不声明 `TIMESTAMPS`。文件任务走 ForcedAligner。麦克风仍只做文本拼接 |
| Qwen 片段时间 | 不拿来当字级时间 | 同样不拿。上游的片段边界不是字对齐 |
| Fun-ASR 热词 | CTC 召回后写进提示词 | MLX 路径把热词和 `context` 传给 `generate`。没有 CTC 网格 |
| SenseVoice 热词雷达 | 引擎内部后处理 | 第一期不移植。客户端 RAG 替换仍然生效 |
| 标点模型 | 引擎没有标点才加载 | MLX 的 SenseVoice / Fun / Qwen 都声明自带标点，不加载 CT-Transformer |
| 默认快捷键 | CapsLock 长按 | 右 Option 长按，不抑制 |
| 输出 | 可打字 | 默认粘贴 |
| 1.7B | GGUF q 量化，配置里写死 | MLX 8bit。统一内存低于 16GB，或 1.7B 加载失败时，改用 0.6B 8bit |

麦克风结果的产品标准是文本可读、有标点、热词替换还在。文件结果的产品标准是 `.srt` 时间单调且贴字。不要求 MLX 文本和 DirectML 文本逐字相同。

## 9. 模型与内存

权重放在仓库已有的 `models/` 下，不只放在 `~/.cache/huggingface`。这是离线工具，拷走 `models/mlx/` 就应该能断网运行。

| model_type | Darwin 目录 | 上游仓库 |
| --- | --- | --- |
| `sensevoice` | `models/mlx/SenseVoiceSmall` | `mlx-community/SenseVoiceSmall` |
| `fun_asr_nano` | `models/mlx/Fun-ASR-Nano-2512` | `mlx-community/Fun-ASR-Nano-2512` |
| `qwen_asr` | `models/mlx/Qwen3-ASR-1.7B-8bit` 或 `...-0.6B-8bit` | 同名 mlx-community 仓库 |
| 对齐器 | `models/mlx/Qwen3-ForcedAligner-0.6B-8bit` | `mlx-community/Qwen3-ForcedAligner-0.6B-8bit` |

选择规则：

- 用户把 `qwen_mlx_variant` 写成 `0.6b` 或 `1.7b` 时，照做。
- `auto`：统一内存大于等于 16GB 用 1.7B 8bit，否则 0.6B 8bit。
- 1.7B 因内存加载失败时，同一进程改加载 0.6B，只重试一次。
- 麦克风不加载对齐器。文件任务才加载，闲置后按现有 `aligner_idle_timeout` 卸掉，并清 MLX 缓存。
- 不要同时常驻同一模型的 ONNX 和 MLX 两份。

听写要快，靠这几件事，而不是再包一层服务：模型常驻 worker、启动后用一段很短的音频预热、每个分片直接把内存里的 float32 波形送进模型、识别过程不按句重建模型。

## 10. 权限

| 权限 | 用途 | 没有时 |
| --- | --- | --- |
| 麦克风 | 采集 | 提示去系统设置里开，不崩溃 |
| 辅助功能 | 粘贴、模拟按键、读选区 | 文字留在系统通知、终端和日志里，不上屏。Darwin 不用 Tk 做这个提示：菜单栏已经占用 NSApplication，再开 Tk 会让进程退出 |
| 输入监控 | 全局按键 | 快捷键不生效，日志写原因 |
| 自动化 | 读前台应用名 | 窗口信息为空，听写继续 |

菜单栏至少有：打开日志目录、打开热词文件、退出。从终端启动时没有 Win32 黑窗口可藏，这不是缺陷。

## 11. 验收

活的清单在文首。做完一条就勾一条，不要在这里再写一套说法。

RTF 用管道里已经打印的那一个。数字是 M1 及更新芯片上的验收线；测完把机型、内存、第一次和第二次的墙钟时间记进测试笔记。上游「10 秒约 70 毫秒」只是 SenseVoice 的参考，不是本产品的承诺。

## 12. 批量转录

脚本已经是 [batch_transcribe.py](batch_transcribe.py)，本轮移植不重写它。它复用文件转录那条流，不导出整条 WAV，也不为每个文件新开客户端。服务端没开时拉起 `start_server.py`。两个成品都有效才跳过。失败隔离。报告只写路径和错误。

Mac 上批量「能用」的定义是：服务端勾上 A3 之后，这条脚本不用改调用方式，并满足 A8。

## 13. 风险

- **MLX 的 Python 轮子可能还没有 cp314 arm64**。仓库要求 `>=3.14`，锁文件却是 Windows。Mac 开发环境可以暂用有轮子的 3.13，不因此把全仓库的 Python 下限改掉。
- **中文对齐未在本仓库测过**。上游示例多是英文。验收必须用中文句子，不能只看 API 能返回 `start_time`。
- **Fun-ASR 的公开 MLX 权重没有时间戳**。字幕完全依赖对齐器。对齐器失败时，现有管道会退回按字均分时间，日志必须写明，不能把均分结果说成对齐成功。
- **fp16 ONNX 进 CoreML 可能只有一部分算子在 ANE 上**。这只影响退路，不影响 MLX 默认路径。
- **右 Option 在某些键盘布局上是特殊键**。若目标机器按不住，配置里改成 `f8` 这类功能键，不改回 CapsLock。
