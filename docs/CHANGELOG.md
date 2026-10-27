# 更新日志

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
