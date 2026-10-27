# 开发计划：Apple Silicon 用 MLX，CoreML 只作退路

配套需求见 [prd.md](prd.md)。基线是 `latest` @ `84912d5`。

上一版计划写过「MLX 不进第一期，Mac 用 CoreML Execution Provider + llama.cpp Metal」。那个判断过时了，作废。主线改为：Darwin 上四个主模型进 MLX，Metal 由 MLX 使用；CoreML 只留给没有 MLX 端口的 ONNX；不为 macOS 编译或分发 llama.cpp b10621。

识别、合并、热词 RAG、协议、批量脚本不动。要动的是依赖怎么按平台拆、引擎工厂在 Darwin 上创建哪一个类、Win32 输入和托盘怎么分支。

待办就是 [prd.md](prd.md) 文首的验收清单，不另建任务表。下面各阶段只说明为了勾上哪一条。2.8.0 已勾上 A3 到 A9，以及不下载权重就能证明的 Windows 依赖和 readme。2.8.1 修的是会议录音字幕和口误数字，不是新阶段。A1、A2 要人在「文本编辑」和系统权限里看，没有勾，也不要当成已经听写成功。

## 1. 加速分工

| 现在 | Darwin 主路径 | 退路 | 明确不做 |
| --- | --- | --- | --- |
| SenseVoice ONNX | `mlx_audio.stt.load` 加载 `models/mlx/SenseVoiceSmall` | 现有 fp16 ONNX + `CoreMLExecutionProvider`，再失败才 CPU | 把 SenseVoice 再导出成 `.mlpackage` 当默认 |
| Fun-ASR-Nano ONNX + GGUF | MLX 整模 `Fun-ASR-Nano-2512` | 无。失败就这个 `model_type` 报错，不静默去加载 Windows DLL | llama.cpp Metal 动态库 |
| Qwen3-ASR ONNX + GGUF | MLX 8bit，1.7B 或 0.6B | 1.7B 内存失败时改 0.6B，只一次 | 把 GGUF 转成 CoreML |
| ForcedAligner ONNX + GGUF | MLX `Qwen3-ForcedAligner-0.6B-8bit` | 对齐失败时管道原有的按字均分，日志标明 | 用 Qwen 的粗片段时间冒充字级时间 |
| Paraformer、CT-Transformer | sherpa-onnx。轮子支持 `provider=coreml` 就用，否则 CPU | CPU | 引入 OminiX 的 Rust crate，或为标点重写模型 |
| `nvidia-smi` 锁频率 | Darwin 跳过 | 无 | 找一个 Apple 的锁频接口 |

客户端不加载 MLX。Metal / CoreML 只发生在服务端 worker 里，和现在模型不进客户端的切分一致。

不要同时依赖 `mlx-audio` 和 `mlx-qwen3-asr`。前者已经覆盖这四个模型。只有中文对齐探针达不到阶段 0 的中文对齐标准时，才允许把对齐器单独换成 `mlx-qwen3-asr` 的 ForcedAligner，ASR 仍留在 `mlx-audio`。

## 2. 库：替换、留下、不要引进

### 按平台拆开的依赖

`pyproject.toml` 改成 marker，不要为了 Mac 去改 Windows 锁里的 directml 版本。

```toml
"onnxruntime-directml; sys_platform == 'win32'",
"onnxruntime; sys_platform == 'darwin' and platform_machine == 'arm64'",
"mlx; sys_platform == 'darwin' and platform_machine == 'arm64'",
"mlx-audio[stt]; sys_platform == 'darwin' and platform_machine == 'arm64'",
"huggingface_hub; sys_platform == 'darwin' and platform_machine == 'arm64'",
"pywin32; sys_platform == 'win32'",
"keyboard; sys_platform == 'win32'",
```

`uv.lock` 今天解不开 Mac。Darwin 另给 `requirements-macos.txt`，或在 arm64 轮子齐全之后单独生成锁。`onnxruntime` 只为 CoreML 退路和 Paraformer / 标点存在，默认听写不 import 它。

`huggingface_hub` 用来把权重下到 `models/mlx/<名字>/`。下载完成后 `load(本地目录)`，断网仍可启动。不要把唯一副本留在 `~/.cache/huggingface`。

### 留下

| 依赖 | 原因 |
| --- | --- |
| `sherpa-onnx` | Paraformer 和 CT-Transformer。MLX 主路径不 import 它 |
| `numpy`、`soundfile`、`sounddevice`、`websockets` | 波形、麦克风、协议 |
| `pynput`、`pyclip`、`pystray`、`Pillow` | Mac 上的按键、粘贴、菜单栏 |
| `srt`、`pypinyin`、`rapidfuzz`、`numba` | 字幕和热词。`numba` 没有 arm64 / cp314 轮子时走已有的纯 Python 分支，不换库 |
| `nagisa`、`soynlp` | 对齐器的日文 / 韩文分词，依赖已在 |

### 不要引进

| 库 | 原因 |
| --- | --- |
| `mlx-audio-plus` | Fun-ASR 的 fp16 卡提到过它。先用 `mlx-audio` 的 `load()`。探针加载失败再考虑，不预装两套 |
| `mlx-qwen3-asr` | 同上，只在对齐器中文探针失败时作为对齐器的替换 |
| `mlx-audio-swift`、`mlx-swift-asr` | Swift 参考实现，不是这个 Python 产品的运行时 |
| OminiX Rust 组件 | 进程模型整个换掉，接不进 `BaseASREngine` |
| `keyboard` 的 Mac 安装 | 需要 root，README 已经放弃 |
| 新的 llama.cpp 源码树 | 主线不编译。只在第 8 节的应急里出现 |

### Python 版本

阶段 0 在本机看 `mlx`、`mlx-audio`、`onnxruntime`、`sherpa-onnx` 有没有 macOS arm64 的 cp314 轮子。有就用 3.14。没有就用 3.13，还没有再用 3.12。Windows 继续 3.14。不要为了迁就 Mac 把 `requires-python` 降下去，除非维护者决定全仓库统一。

## 3. 重构什么，新建什么，别动什么

### 新建：MLX 适配层

只新增这些文件，不把 MLX 调用散落到现有 ONNX 引擎里：

| 文件 | 职责 |
| --- | --- |
| `core/server/engines/mlx/loader.py` | 按本地目录 `load` 一次，按仓库 ID 缓存。打印 `backend=mlx` 和默认设备。设备不是 GPU 就警告 |
| `core/server/engines/mlx/audio.py` | 把管道里的 float32、16 kHz 波形交给模型。`generate` 能收数组就不要写临时 wav；只能收路径时，用完即删 |
| `core/server/engines/mlx/sensevoice.py` | 实现 `BaseASREngine`。能力：`ASR`、`PUNC`。不声明 `TIMESTAMPS`，不声明 `HOTWORDS` |
| `core/server/engines/mlx/fun_asr.py` | 能力：`ASR`、`PUNC`、`HOTWORDS`。`update_hotwords` 和 `context` 合成 `generate` 的 context |
| `core/server/engines/mlx/qwen_asr.py` | 能力：`ASR`、`PUNC`。不把片段 `start/end` 写进 `timestamps` |
| `core/server/engines/mlx/aligner.py` | 实现 `BaseAlignEngine`。把 MLX 的 `text` / `start_time` / `end_time` 收成现有的 `ForcedAlignItem` 列表 |
| `core/server/engines/ort_session.py` | 仅 ONNX 退路使用。把 `CPU` / `DML` / `CUDA` / `TRT` / `COREML` 收成一处，避免六个编码器各抄一遍 |

`EngineFactory._load_*` 是唯一的平台分叉：

- Darwin 且 `model_backend` 为 `auto` 或 `mlx`：返回 MLX 类。
- `model_backend=onnx`，或不是 Darwin：返回现在的 ONNX / GGUF 类。
- `paraformer` 永远走现有 sherpa 类。

`ModelLoader` 里无条件 `import sherpa_onnx` 改成懒加载。只有创建 Paraformer 或标点引擎时才 import。这样 Mac 上只装 MLX 也能听写。

`ManagedAlignerProxy` 继续包住对齐器。`cleanup` 时如果 MLX 提供清缓存的函数就调用，不要每个麦克风分片都清，否则下一句要重新编译。

### 小改，不是重写

| 位置 | 改动 |
| --- | --- |
| `core/server/engines/factory.py` | 按上面的规则选类 |
| `core/server/worker/model_loader.py` | sherpa 懒加载；MLX 引擎不挂标点模型 |
| `config_server.py` | 增加第 5 节的字段。不删 `DML` / `CUDA` |
| `config_client.py` | 增加 Darwin 专用快捷键和粘贴开关，不改 Windows 那组默认值 |
| `core/client/shortcut/key_mapper.py` | `win32` 才 import `KeyTranslator` |
| `core/client/shortcut/shortcut_manager.py` | Darwin 用 `on_press` / `on_release`。不要传 `win32_event_filter` |
| `text_output.py`、`result_processor.py`、`llm_output_typing.py`、`llm_get_selection.py` | Darwin 分支改走已经在用的 `pynput`。选区用 Command+C |
| `core/ui/tray.py` | Darwin 用 `pystray`，不调用 `_init_win_api`。菜单：日志目录、热词、退出 |
| 六个 ONNX `encoder.py` | 只有退路才改为调用 `ort_session.py`。MLX 默认路径不进这些文件 |

### 不动

- `core/server/merger/`、`core/server/worker/pipeline.py` 的合并和对齐门闩。MLX 引擎不声明 `TIMESTAMPS` 之后，文件任务会自己调用对齐器，麦克风不会。
- `core/server/engines/sensevoice_onnx/`、`fun_asr_gguf/`、`qwen_asr_gguf/`、`force_aligner_gguf/` 的算法。Windows 继续用。
- `core/protocol.py`、热词 RAG、`batch_transcribe.py`、ffmpeg 流式发送。
- `core/client/__init__.py` 里已经做的 `CapsWriterClient` 延迟导入。保留，批量脚本不能再被 `key_mapper` 拖死。

SenseVoice 从「自带 CTC 时间」变成「文件任务走对齐器」，是工厂换引擎之后的结果，不是去改 `pipeline.py`。

## 4. 适配器要守住的合同

`decode_stream` 只填 `stream.result.text`。`tokens` 和 `timestamps` 留空。管道会用文本做听写拼接；文件任务再由对齐器填 token。

对齐器返回的对象必须有 `.items`，元素有 `.text` 和 `.start_time`，单位秒。这是 `TaskPipeline` 已经在读的字段。语言代码继续走 `get_language(ENGINE_ALIGNER, ...)`，不要在适配器里另写一套中英映射。

Fun-ASR 的热词是提示词，不是 CTC 雷达。把 `hot-server.txt` 的词和任务里的 `context` 拼成一段字符串传给 `generate`。传不进去的关键字就丢掉并打一条 warning，不要因此让识别失败。

SenseVoice 的情绪和事件可以放进 `performance` 字典。第一期不展示、不写进字幕。

波形进模型之前确认是单声道 float32、16 kHz。客户端已经按这个格式送。适配器不做重采样以外的音效处理。

MLX 调用留在 worker 进程的识别线程上。不要为 `generate` 再开线程池。服务端现在就是一个任务一个任务做，批量脚本也是串行的。

启动加载成功后，用不超过 0.5 秒的静音或现成短音频跑一次并丢掉文本。这次允许很慢。失败只记日志，不阻止服务启动。

## 5. 配置

`config_server.py` 增加，不替换现有 Windows 字段：

```python
model_backend = 'auto'          # auto | mlx | onnx
qwen_mlx_variant = 'auto'       # auto | 0.6b | 1.7b
```

`auto` 在 Darwin 上是 `mlx`，在 Windows 上是 `onnx`。Darwin 上只有 SenseVoice 的 `model_backend=onnx` 会创建这条 ONNX 会话：`onnx_provider` 留着默认的 `CPU`，也会和 `DML`、`CUDA` 一样先改写成 `COREML` 并警告。Windows 上不改。不要在 MLX 路径里改这个字段。Fun-ASR 和 Qwen 的 ONNX 半边不走这个改写，不能拿来当作退路已经可用。

`gpu_boost_enabled` 在 Darwin 上忽略。

Qwen 仓库选择放在工厂旁边的一个函数里，不写进每个引擎：

- `1.7b`：`mlx-community/Qwen3-ASR-1.7B-8bit`
- `0.6b`：`mlx-community/Qwen3-ASR-0.6B-8bit`
- `auto`：`psutil` 看到的总内存大于等于 16GB 用 1.7B，否则 0.6B
- 加载 1.7B 出现内存错误时改 0.6B，日志写明，只重试一次

`config_client.py` 增加一组 Darwin 值，Windows 默认值原样保留：

- `darwin_shortcuts`：右 Option，`suppress=False`，`hold_mode=True`
- `darwin_paste = True`

客户端在 Darwin 上读这组，不读 CapsLock 那组。用户要改 Mac 快捷键就改 `darwin_shortcuts`。不要在运行时猜测「用户是不是还没改过默认值」。

`llm_use_gpu` 只对 ONNX / GGUF 有意义。MLX 路径忽略它。没有「MLX 跑在 CPU 上」的正式开关。

## 6. 客户端平台层

快捷键：

- Windows：现有 `win32_event_filter` 和抑制逻辑一行不删。
- Darwin：`pynput` 的按下 / 松开。按住超过 `threshold` 开始录音，松开停止。做不到系统级吞噬。`suppress=True` 在 Darwin 上打 warning 然后按不抑制处理。
- 默认键不用 CapsLock。右 Option 不可用时，文档让用户改成 `f8`，代码不自动再挑一个键。
- pynput 在 Darwin 上用虚拟键码 `0x3D` 先后登记 `alt_r` 和 `alt_gr`，监听器交出的名字是 `alt_gr`。配置里的 `alt_r` 和事件里的 `alt_gr` 都算右 Option。

上屏：

- Darwin 默认粘贴，沿用 `clipboard.py` 里已有的 Command+V。
- 打字输出和自动回车如果还开着，用 `pynput.keyboard.Controller`，不用 `keyboard` 包。
- LLM 读选区在 Darwin 上发送 Command+C。没辅助功能权限时返回空，并 Toast 说明，不抛未捕获异常。

托盘：

- `tray.py` 现在非 Windows 直接返回不可用。改成 Darwin 可以创建 `pystray` 图标。
- 所有 `kernel32` / `user32` 留在 `sys.platform == 'win32'` 里面。
- 打开目录的 `open` 调用，`tray_manager.py` 里已经有，菜单复用它。

`block_mouse_forward.py` 是独立的 Windows 小工具，不参与启动，不用移植。

## 7. CoreML 退路怎么接

默认安装可以带着 `onnxruntime`，但默认 `model_type` 不创建 ORT 会话。

`ort_session.py` 只做三件事：

1. `COREML` 映射成 `CoreMLExecutionProvider` 加 `CPUExecutionProvider`。选项名以装上的 `onnxruntime` 文档为准，预期包括 `MLComputeUnits=ALL`、静态形状、缓存目录 `~/Library/Caches/CapsWriter/coreml`。
2. Darwin 上见到 `CPU`、`DML` 或 `CUDA` 时改成 `COREML` 并警告。配置默认值就是 `CPU`，不改的话 CoreML 不会被尝试。Windows 上 `CPU` 和 `DML` 保持原样。
3. CoreML 创建失败就只用 CPU 再建一次。一条模型失败不影响别的模型。

谁调用它：

- 真正接上的是 SenseVoice 的编码器和解码器，而且只在 `model_backend=onnx` 时创建。Fun / Qwen / 对齐器仍用各自的 provider 选择，GGUF 半边在 Mac 上没有 Metal 库，不能用它们的输出证明这条退路。Mac 上的 ONNX 退路只保证 SenseVoice。Fun 和 Qwen 要可用就用 MLX。
- Paraformer：创建 sherpa `OfflineRecognizer` 时，若当前版本文档有 `provider='coreml'` 就传入，捕获异常后不带 provider 再试一次。
- 标点：同样。只有引擎没有 `PUNC` 时才会加载，MLX 主路径不会碰到。

`dml_pad_to` 在 CoreML 退路上仍然是固定形状长度。Mac 上这条退路的默认垫长用 8 秒，不要把 Windows 的 30 秒原样编译进 8GB 机器。MLX 路径没有这个垫长。

## 8. 阶段

### 阶段 0：探针

不单独勾清单。在目标 Mac 上确认四件事，记在测试笔记里，不改产品代码：

1. `mlx`、`mlx-audio` 的轮子和 Python 版本。
2. `load(本地目录)` 能否接受 numpy 波形；不能的话，临时文件方案就定下来。
3. Fun-ASR 的 `generate` 是否接受 context / hotwords 关键字。
4. 一句中文经过 ForcedAligner 后，`start_time` 单调，文字能对上。这一条失败就改用第 1 节允许的对齐器替换，不换 ASR 库。

同时看启动时 MLX 默认设备是不是 GPU。

### 阶段 1：勾 A1、A2，并保住 A10 的 Windows 半边

- 依赖 marker。
- `key_mapper`、托盘、`windll` 守卫。
- Darwin 快捷键和粘贴。
- 服务端这时可以还是 CPU ONNX SenseVoice。
- 2026-10-27：菜单循环留在主线程，麦克风在旁边的线程。没有辅助功能时不上屏。右 Option 的 `alt_gr` 会对上 `alt_r`。提示走系统通知，不在菜单进程里开 Tk。A1、A2 仍要人在「文本编辑」和系统权限里看，没有勾。
- 2026-10-27：默认输入编号是 -1 时，列出有输入声道的设备并逐个打开，单次超过 2 秒就跳过。设备还在时不说成没有麦克风权限。列不出设备时才提示去系统设置。A1、A2 仍没有勾。

### 阶段 2：勾 A3、A4、A7

- `loader.py`、`audio.py`、`sensevoice.py`、工厂分叉、权重下载到 `models/mlx/`。
- 预热和 GPU 日志。1.7B 的内存重试留到下一阶段。

### 阶段 3：勾 A5、A6

- Qwen、Fun 两个引擎类，变体选择，内存失败重试，Fun 的 context。
- 不声明 `TIMESTAMPS`。

### 阶段 4：勾 A8

- `aligner.py` 接上 `ManagedAlignerProxy`。
- 用现有文件转录或 `batch_transcribe.py` 出 `.srt` / `.txt`。

### 阶段 5：勾 A9

- `ort_session.py` 和 SenseVoice ONNX 的调用点。Darwin 上默认 `CPU` 也会先改成 CoreML。
- Paraformer / 标点能开 CoreML 就开。
- 2026-10-27 已在 Mac mini M4 上用现有 fp16 ONNX 跑通。会话提供者是 CoreML，文本非空。强制创建失败后退回 CPU。Fun-ASR 和 Qwen 没有参与这次交差。

### 阶段 6：勾 A11

- `readme.md` 去掉「macOS 不可用」。
- `docs/环境依赖安装说明.md` 增加 Mac 的 Python、ffmpeg、权限。
- `docs/显卡加速的若干问题.md` 增加 MLX / Metal 和 CoreML 退路。DirectML 章节保留。

打包签名公证的 `.app` 仍然不做。权限仍是授给终端，不是授给 `.app`。

2026-10-27 在这台 Mac 上用 `build.spec` 做了本地编译，版本仍是 2.8.0：

- Darwin 关闭 UPX，不传 Windows 的 `assets\\icon.ico`，不把 `keyboard` 当隐藏导入。
- 不收集 CUDA / DirectML。Windows 的 `mklink` 列表不动。
- `models`、`assets`、`core`、`LLM`、`docs`、`logs` 链到仓库的绝对路径。没有 `log` 目录就跳过。
- `check_model` 在 MLX 路径上检查 `models/mlx/` 里的目录。Windows 和 `model_backend=onnx` 仍查原来的 ONNX / GGUF 文件。
- PyInstaller 会漏掉 `libjaccl.dylib`、`mlx.metallib` 和一部分 MLX Python 文件。`build_support.py` 在收集之后补进 `internal/`。
- 短跑 `dist/CapsWriter-Offline/start_server` 能过模型检查并写出 `backend=mlx`、`Device(gpu, 0)`。这不是 A1 或 A2。

2026-10-27 修了这份会议录音上能看见的坏结果，版本 2.8.1。A1、A2 仍然没有勾。

- 对齐器只回字。识别文本里的标点会插回 token。605.77 秒录音的 txt 有 89 行，srt 有 89 条，最后结束在 605.92 秒，没有把一条字幕撑过音长。
- 「五五十套」写成 50套，「第三一个」保留成第3一个，「三百五百」分成 300 和 500。多位数字之间的空格不再粘成一个数。
- ffmpeg 失败时，日志带上 stderr 尾部，不再只有退出码。
- 同一天用 `python -m PyInstaller build.spec` 和 `build-client.spec` 重新打出 arm64 Mach-O 的 `start_server`、`start_client` 和客户端包里的 `start_client`。短跑打包后的服务端，模型检查通过，日志是 `backend=mlx` 和 `Device(gpu, 0)`，然后关掉。6016 没有继续占用。

2026-10-27 版本 2.9.0。Darwin 上打开客户端会带起没在跑的服务端，并等到端口开始监听。第二份服务端在加载模型之前退出。第二份客户端不再登记快捷键；带了文件就交给已经在菜单栏里的那一个。关掉客户端不会关掉服务端。菜单「全部退出」只向锁里记下、且命令行对得上的服务端发 SIGTERM。`build.spec` 在收集目录放未签名的 `CapsWriter.app` 和 `CapsWriter Server.app`，拉起时不用 `open -n`。直接运行 Mach-O 正常。用 `open` 打开未签名 app 会停在 dyld 的 `__open`，不听端口。不做签名公证。A1、A2 仍然没有勾。

2026-10-27 版本 2.9.1。JBL Quantum Stream 上 2.05 秒录音识别成「一二三四五六七。」，格式化后是 1234567。在这之前，Mac mini 没有麦克风，程序退到 Virtual Audio，两段录音都是 -91 dB 的静音，空文本却被印成整个 STTOutput。现在空文本保持为空。选中的输入如果是虚拟声卡，会说明它不是麦克风。峰值低于 -60 dB 时，松开后写明这段录音是静音。打包后的辅助功能和输入监控提示写出 `start_client`。A1、A2 仍然没有勾。

2026-10-27 版本 2.9.2。松开一次会三次读取前台应用，每次都用 System Events 的 AppleScript，所以「没有自动化权限」连着出现三次。识别本身已经返回文本。现在应用名先走 NSWorkspace，失败再用 lsappinfo，不再为这个用途申请自动化权限。读不到时同一进程只警告一次，听写继续。A1、A2 仍然没有勾。

2026-10-27 版本 2.9.3。系统设置的辅助功能里没有 `start_client`，终端那一项是关的。以前只写日志，程序不会出现在列表里。现在启动时如果辅助功能被拒绝，会调用系统接口把当前进程列进去，不改开关。A1、A2 仍然没有勾。
2026-10-27 版本 2.9.4。权限请求原来发生在麦克风线程，系统对话框经常不出现，输入监控也没有被请求。现在先在主线程请求辅助功能和输入监控，麦克风线程只负责把调用排过去。开关仍要自己打开。A1、A2 仍然没有勾。



## 9. llama.cpp Metal 只是应急，不排期

阶段 0 如果 `mlx` 完全装不上，而用户的 Mac 又必须先听写，才允许临时用现有 ctypes 绑定去加载一份本机编译的 b10621 Metal 库。那不是本计划的交付，不写进依赖，不替代 MLX 任务。SenseVoice 在那种情况下用 ONNX CPU 或 CoreML 即可，它本来就没有 GGUF 半边。

不要为了「两条路都做」把应急写进阶段 2。两套解码器会让 DirectML 回归和 Metal 加载失败混在同一次改动里。

## 10. 测试

沿用 `unittest`。不下载权重的测试：

1. 工厂：Darwin + `auto` 选 MLX 类；Windows + `auto` 选现有类；`model_backend=onnx` 在 Darwin 上仍选 ONNX 类。用假的类替换加载器，不真的 import MLX。
2. Qwen 变体：16GB 以上选 1.7B，以下选 0.6B；模拟内存错误后只切换一次。
3. 对齐适配：假的 MLX 结果映射成 `.items[].start_time`，乱序输入在适配器里拒绝或按时间排序后仍单调。
4. Fun context：热词列表和任务 context 拼进同一次调用参数。
5. `key_mapper` 在非 Windows 分支不访问 `pynput._util.win32`。可以用 `sys.platform` 的测试替身，或把导入放进函数后直接测函数。
6. 现有 `python3 -m unittest tests.test_batch_transcribe -v` 继续通过。
7. 默认输入编号是 -1 时，假设备列表里声道为 0 的不出现。第一个打开卡住就在超时后跳过，下一条能打开就用它。消息里不出现「没有麦克风权限」。一个输入设备都没有时才提示去开麦克风权限。

要真机、不进 CI 的：

- 文本编辑里按一次右 Option。
- SenseVoice 与 Qwen 的 RTF。
- 一条中文音视频的 srt。
- 关掉麦克风权限后的提示。

Windows 回归只看：`win32_event_filter` 还在，`DML` 会话参数没有被 `ort_session.py` 丢掉。

## 11. 建议的提交拆分

1. 依赖 marker + import 守卫 + Darwin 快捷键和粘贴。CPU 听写能闭环。
2. MLX loader + SenseVoice。
3. Qwen、Fun、变体和内存重试。
4. MLX 对齐器。文件和批量出 srt。
5. `ort_session.py` 与 Paraformer / 标点的 CoreML 退路。
6. README 和两篇 docs。

每一步都应该在 Windows 上仍能启动。不要把 1 到 4 合成一个改动。

## 12. 批量脚本

[batch_transcribe.py](batch_transcribe.py) 已经按「一条 WebSocket、不预导出整段 WAV、两个成品都有效才跳过」实现。本计划不改它的流程。

它和移植的接口只有一个：服务端要能在 Mac 上被 `start_server.py` 拉起，并且文件任务会因为 MLX 引擎没有 `TIMESTAMPS` 而走到阶段 4 的对齐器。阶段 4 之前，批量可以出文本，字幕时间可能是均分的，不算完成。

`config_client.py` 的 `file_save_srt` 和 `file_save_txt` 保持 True。

2026-10-27 版本 2.9.5。控制中心把名字为 CapsWriter 的状态项排在 x=-695。菜单栏空档里的按钮最后停在 x=1095、高 30，左边是空的，右边是麦克风图标，没有盖住。17:20 点这个按钮，菜单里有日志、热词、退出，按 Esc 关闭，没有点「全部退出」。`/tmp/capswriter-macos-test/bin/python -m unittest discover -s tests -p 'test_*.py'`，81 项通过。A1 的证据仍是 14:24 的客户端日志：辅助功能已允许，前台是「文本编辑」，剪贴板长度 14，已粘贴；日记是「今天天气很好。今天天气很好。」A1、A2 勾上。
