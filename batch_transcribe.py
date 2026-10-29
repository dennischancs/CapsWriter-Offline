# coding: utf-8
"""批量把文件夹里的音视频转录成同名 .srt、.txt 和 .json。

用法:
    python batch_transcribe.py
    python batch_transcribe.py /path/to/media
    python batch_transcribe.py a.mp4 b.mkv /path/to/folder
    ./batch_transcribe /path/to/media

不带参数时先打开批量转录自己的窗口，再在后台等服务端。切分只发生在这个脚本里。

最后一种是编译进收集目录之后的可执行文件，和 start_server 放在一起。

和旧的 capswriter-all.ps1 / media2srt.py 相比:
- 不再先导出整条 WAV，也不再为每个片段新开一个客户端进程。
  当前服务端已经按 config_client.file_seg_duration（默认 60 秒）流式识别。
- 只看同名 .srt。这个文件已经在就跳过，不管 .txt 和 .json 缺不缺。
  没有 .srt 就再转录，并留下这三个文件。
- 单个文件失败不影响后面的文件。先探测时长，超过 2 小时就按 2 小时切开再识别，
  不再整段试跑失败后才切。临时片段合并成一个 srt、txt 和 json。
- 服务端没开时自动拉起，端口通了就继续，不再固定睡 80 秒。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path

from core.tools.progress_log import ProgressGate, apply_progress_line

def install_root(file_path=None, frozen=None, executable=None) -> Path:
    """源码在脚本旁边。打包后可执行文件的目录才是配置、core 和服务端所在处。"""
    is_frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    if is_frozen:
        exe = sys.executable if executable is None else executable
        return Path(exe).resolve().parent
    source = __file__ if file_path is None else file_path
    return Path(source).resolve().parent


def server_launch_command(root: Path, frozen=None) -> list[str]:
    """旁边有 start_server 就直接运行。打包后的本程序不是 Python，不能拿来跑 .py。"""
    is_frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    for name in ('start_server', 'start_server.exe'):
        binary = root / name
        if binary.is_file() and os.access(binary, os.X_OK):
            return [str(binary)]
    if is_frozen:
        raise RuntimeError(
            '旁边没有可执行的 start_server。请在完整收集目录里运行 batch_transcribe，'
            '该目录应同时有 start_server。'
        )
    return [sys.executable, str(root / 'start_server.py')]


ROOT = install_root()

VIDEO_EXTENSIONS = {
    '.mp4', '.wmv', '.avi', '.swf', '.f4v', '.amr', '.ts', '.m4v',
    '.webm', '.mov', '.flv', '.mkv', '.mpg', '.mpeg', '.3gpp', '.dsv',
}
AUDIO_EXTENSIONS = {
    '.wav', '.mp3', '.aac', '.m4a', '.ogg', '.wma', '.au', '.aifc',
    '.aiff', '.aif', '.flac', '.mp2', '.opus', '.caf',
}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# 旧脚本把 .m3u 播放列表和 MIDI/tracker 也送去识别，那些不是语音容器，这里丢掉。
SPLIT_AFTER_SECONDS = 2 * 60 * 60
UNKNOWN_DURATION_TIMEOUT = 3 * 60 * 60
# 窗口不暴露这些数。它们是放弃线，不是速度。识别完成会立刻返回。
SERVER_WAIT_SECONDS = 180
FILE_TIMEOUT_FACTOR = 4.0
FILE_MIN_TIMEOUT = 180
LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
LOG_RANK = {name: index for index, name in enumerate(LOG_LEVELS)}
MODEL_CHOICES = (
    ('sensevoice', 'SenseVoice Small'),
    ('fun_asr_nano', 'Fun-ASR Nano'),
    ('qwen_asr:1.7b', 'Qwen3-ASR 1.7B'),
    ('qwen_asr:0.6b', 'Qwen3-ASR 0.6B'),
    ('paraformer', 'Paraformer'),
)
MENU_IDS = tuple(item[0] for item in MODEL_CHOICES)
MODEL_IDS = ('sensevoice', 'fun_asr_nano', 'qwen_asr', 'paraformer')
MODEL_ARGUMENTS = (
    'sensevoice', 'fun_asr_nano', 'qwen_asr',
    'qwen_asr:1.7b', 'qwen_asr:0.6b', 'paraformer',
)
_MODEL_LABELS = {key: label for key, label in MODEL_CHOICES}
_QWEN_VARIANTS = ('1.7b', '0.6b')
_VARIANT_RE = re.compile(
    r"""(?m)^(?P<indent>[ \t]*qwen_mlx_variant\s*=\s*)(?P<quote>['\"])(?P<value>[A-Za-z0-9_.]+)(?P=quote)"""
)
PART_MARK = '.capswriter-part-'
CLOSE_TRAY = 'tray'
CLOSE_QUIT = 'quit'
_batch_tray = {}
_BatchTrayTarget = None

_TIME_RE = re.compile(
    r'(?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})'
)


@dataclass
class Report:
    ok: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    stopped: bool = False

    @property
    def failed_count(self) -> int:
        return len(self.failed)


def is_media(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTENSIONS and PART_MARK not in path.name


def collect_media(paths: list[Path], recursive: bool, hidden: bool) -> tuple[list[Path], list[tuple[Path, str]]]:
    """返回要处理的媒体，以及路径本身就无效的错误。"""
    found: list[Path] = []
    errors: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(resolved)

    for raw in paths:
        path = raw.expanduser()
        if not path.exists():
            errors.append((path, '路径不存在'))
            continue
        if path.is_file():
            if is_media(path):
                add(path)
            else:
                errors.append((path, '不是支持的音视频'))
            continue
        if not path.is_dir():
            errors.append((path, '不是文件或目录'))
            continue

        if recursive:
            for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
                if not hidden:
                    dirnames[:] = [name for name in dirnames if not name.startswith('.')]
                for name in filenames:
                    if not hidden and name.startswith('.'):
                        continue
                    candidate = Path(dirpath) / name
                    if candidate.is_file() and is_media(candidate):
                        add(candidate)
        else:
            for candidate in path.iterdir():
                if not hidden and candidate.name.startswith('.'):
                    continue
                if candidate.is_file() and is_media(candidate):
                    add(candidate)

    found.sort()
    return found, errors


def is_complete(media: Path) -> bool:
    """写好的同名 .srt 才跳过。空文件、没有时间轴的半截，以及 .partial，都不算做完。"""
    path = media.with_suffix('.srt')
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    return '-->' in text and bool(text.strip())


def outputs_ready(media: Path) -> bool:
    """这一轮做完后，同名 .srt、.txt、.json 都是非空文件。"""
    for suffix in ('.srt', '.txt', '.json'):
        path = media.with_suffix(suffix)
        try:
            if not path.is_file() or path.stat().st_size == 0:
                return False
        except OSError:
            return False
    return True


def parse_timestamp(value: str) -> float:
    match = _TIME_RE.search(value)
    if not match:
        raise ValueError(f'无法解析时间戳: {value}')
    return (
        int(match.group('h')) * 3600
        + int(match.group('m')) * 60
        + int(match.group('s'))
        + int(match.group('ms')) / 1000
    )


def format_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, total_ms = divmod(total_ms, 3600_000)
    minutes, total_ms = divmod(total_ms, 60_000)
    secs, millis = divmod(total_ms, 1000)
    return f'{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}'


def _srt_cues(text: str) -> list[list[str]]:
    normalized = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not normalized:
        return []
    cues = []
    for block in re.split(r'\n\s*\n', normalized):
        lines = [line for line in block.split('\n')]
        if not lines:
            continue
        time_at = 0
        if '-->' not in lines[0] and len(lines) > 1 and '-->' in lines[1]:
            time_at = 1
        if '-->' not in lines[time_at]:
            continue
        cues.append(lines[time_at:])
    return cues


def shift_timeline(line: str, offset: float) -> str:
    left, right = line.split('-->', 1)
    return (
        f'{format_timestamp(parse_timestamp(left) + offset)} --> '
        f'{format_timestamp(parse_timestamp(right) + offset)}'
    )


def merge_srt(chunks: list[tuple[str, float]]) -> str:
    """按每段真实起点拼接字幕，并重新编号。chunks 是 (srt 文本, 起点秒)。"""
    blocks = []
    index = 1
    for text, offset in chunks:
        for cue in _srt_cues(text):
            body = [str(index), shift_timeline(cue[0], offset), *cue[1:]]
            blocks.append('\n'.join(body))
            index += 1
    if not blocks:
        return ''
    return '\n\n'.join(blocks) + '\n'


def merge_txt(chunks: list[str]) -> str:
    pieces = [chunk.strip('\ufeff').strip() for chunk in chunks if chunk.strip()]
    if not pieces:
        return ''
    return '\n'.join(pieces) + '\n'


def merge_json(chunks: list[tuple[dict, float]]) -> dict:
    """把每段字级时间从片段内秒数改到整文件秒数。"""
    timestamps: list[float] = []
    tokens: list = []
    for payload, offset in chunks:
        part_tokens = list(payload.get('tokens') or [])
        part_times = list(payload.get('timestamps') or [])
        tokens.extend(part_tokens)
        for value in part_times:
            timestamps.append(float(value) + offset)
    return {'timestamps': timestamps, 'tokens': tokens}


def presplit_seconds(duration: float, segment_seconds: float, split_long: bool) -> float:
    """返回预切段长。0 表示整文件直接送识别。

    显式段长优先。否则只在超过 2 小时时按 2 小时切开，不再先整段试跑。
    """
    if segment_seconds > 0:
        return segment_seconds
    if split_long and duration > SPLIT_AFTER_SECONDS:
        return float(SPLIT_AFTER_SECONDS)
    return 0.0


def plan_segments(duration: float, segment_seconds: float) -> list[tuple[float, float]]:
    """需要预切时返回 (起点, 长度)。空列表表示整文件直接送。"""
    if segment_seconds <= 0 or duration <= segment_seconds:
        return []
    spans = []
    start = 0.0
    while start < duration - 0.05:
        length = min(segment_seconds, duration - start)
        spans.append((start, length))
        start += segment_seconds
    return spans


def probe_duration(path: Path) -> float:
    if shutil.which('ffprobe') is None:
        return 0.0
    try:
        result = subprocess.run(
            [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    if result.returncode != 0:
        return 0.0
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError:
        return 0.0


def file_timeout(duration: float, factor: float, minimum: float) -> float:
    if duration <= 0:
        return max(minimum, UNKNOWN_DURATION_TIMEOUT)
    return max(minimum, duration * factor + 60)


def server_endpoint() -> tuple[str, int]:
    from config_client import ClientConfig
    return ClientConfig.addr, int(ClientConfig.port)


def server_is_up(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class BatchLock:
    def __init__(self, path: Path):
        self.path = path
        self._held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                pid = int(self.path.read_text(encoding='utf-8').strip() or '0')
            except (OSError, ValueError):
                pid = 0
            if _pid_alive(pid):
                raise RuntimeError(f'已有批量转录在运行 (pid {pid})。等它结束，或确认已经退出后删掉 {self.path}')
            try:
                self.path.unlink()
            except OSError:
                pass
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f'已有批量转录在运行: {self.path}') from exc
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(str(os.getpid()))
        self._held = True

    def release(self) -> None:
        if not self._held:
            return
        try:
            current = int(self.path.read_text(encoding='utf-8').strip() or '0')
        except (OSError, ValueError):
            current = os.getpid()
        if current == os.getpid():
            try:
                self.path.unlink()
            except OSError:
                pass
        self._held = False


def output_flags_error() -> str | None:
    from config_client import ClientConfig
    if not (
        ClientConfig.file_save_srt
        and ClientConfig.file_save_txt
        and ClientConfig.file_save_json
    ):
        return (
            'config_client.py 里 file_save_srt、file_save_txt 和 file_save_json '
            '都要为 True，否则无法留下同名字幕、文本和时间戳'
        )
    return None


class LogTail:
    """跟着服务端日志文件往下读。窗口因此能看到识别过程，而不只是开始和结束。"""

    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0

    def read(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            return ''
        if size < self.offset:
            self.offset = 0
        if size == self.offset:
            return ''
        with self.path.open('r', encoding='utf-8', errors='replace') as handle:
            handle.seek(self.offset)
            text = handle.read()
            self.offset = handle.tell()
        return text


def loaded_model_path(root=None):
    """这次拉起的服务端实际加载的菜单项。旧进程还在时不能只看配置文件。"""
    return Path(root or ROOT) / 'logs' / 'loaded_model.txt'


def read_loaded_model(path=None):
    target = loaded_model_path() if path is None else Path(path)
    try:
        return target.read_text(encoding='utf-8').strip()
    except OSError:
        return ''


def record_loaded_model(started, config_text, path):
    """只有这次真的拉起了进程才记下模型。端口上原来就有的，不覆盖。"""
    if started is None:
        return False
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(read_model_choice(config_text) + '\n', encoding='utf-8')
    return True


def parse_process_start(text):
    """ps -o lstart= 的本地时间。解析不了就当不知道。"""
    raw = ' '.join(str(text or '').split())
    if not raw:
        return None
    try:
        moment = datetime.strptime(raw, '%a %b %d %H:%M:%S %Y')
    except ValueError:
        return None
    return moment.timestamp()


def process_started_at(pid, runner=None):
    if int(pid) <= 1:
        return None
    run = subprocess.run if runner is None else runner
    try:
        result = run(
            ['ps', '-p', str(int(pid)), '-o', 'lstart='],
            capture_output=True, text=True, check=False,
            env={**os.environ, 'LC_ALL': 'C'},
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return parse_process_start(getattr(result, 'stdout', '') or '')


def listening_server_started_at(port, listener_lookup=None, started_lookup=None):
    """端口上最早那个监听进程的启动时间。没有就返回 None。"""
    listeners = listener_pids(port) if listener_lookup is None else listener_lookup(port)
    lookup = process_started_at if started_lookup is None else started_lookup
    times = []
    for pid in listeners or []:
        moment = lookup(pid)
        if moment is not None:
            times.append(moment)
    if not times:
        return None
    return min(times)


def config_is_newer_than_server(config_path, started_at, slack=1.0):
    """配置文件比服务端进程新一秒以上，说明进程读到的还是旧配置。"""
    if started_at is None:
        return False
    try:
        mtime = Path(config_path).stat().st_mtime
    except OSError:
        return False
    return mtime > float(started_at) + float(slack)


def apply_model_choice(
    model, config_path=None, restart=None, memory=None,
    server_up=False, loaded_model=None, config_stale=False,
):
    """写入配置。引擎、规格变了，进程里还是旧模型，或配置比进程新，都要重启。"""
    path = ROOT / 'config_server.py' if config_path is None else Path(config_path)
    text = path.read_text(encoding='utf-8')
    engine, variant = split_model_choice(model)
    current_engine = read_model_type(text)
    current_variant = read_qwen_variant(text)
    same_engine = engine == current_engine
    if variant is None or variant == current_variant:
        same_variant = True
    elif current_variant == 'auto' and effective_qwen_variant('auto', memory) == variant:
        same_variant = same_engine
    else:
        same_variant = False
    requested = menu_id_for(engine, variant if variant else current_variant, memory)
    label = model_label(requested)
    running = str(loaded_model or '').strip()
    loaded_differs = bool(server_up) and bool(running) and running != requested
    stale = bool(server_up) and bool(config_stale)
    if same_engine and same_variant and not loaded_differs and not stale:
        print(f'模型: {label}')
        return False
    if not (same_engine and same_variant):
        path.write_text(write_model_choice(text, model), encoding='utf-8')
        current_label = model_label(menu_id_for(current_engine, current_variant, memory))
        print(f'模型从 {current_label} 换成 {label}。正在重启服务端。')
    elif loaded_differs:
        print(f'服务端仍是 {model_label(running)}，正在换成 {label}。')
    else:
        print(f'配置比正在运行的服务端新，正在重启后再用 {label}。')
    if restart is not None:
        restart()
    return True


def restart_running_server():
    """结束正在听 6016 的服务端。下一轮 ensure_server 会按新模型拉起。"""
    host, port = server_endpoint()
    if not server_is_up(host, port, timeout=0.4):
        return
    result = subprocess.run(
        ['lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'],
        capture_output=True, text=True, check=False,
    )
    pids = []
    for line in (result.stdout or '').splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid > 0 and pid != os.getpid():
            pids.append(pid)
    for pid in pids:
        try:
            os.kill(pid, 15)
        except OSError:
            continue
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and server_is_up(host, port, timeout=0.3):
        time.sleep(0.3)
    if server_is_up(host, port, timeout=0.4):
        raise RuntimeError(f'服务端仍占用 {host}:{port}，模型没有换上')


def ensure_server(start: bool, timeout: float) -> subprocess.Popen | None:
    """端口已通时返回 None。否则按需启动 start_server.py，返回子进程。"""
    host, port = server_endpoint()
    if server_is_up(host, port):
        print(f'服务端已在 {host}:{port}')
        return None
    if not start:
        raise RuntimeError(f'服务端 {host}:{port} 没开。先运行 start_server.py，或去掉 --no-start-server')

    command = server_launch_command(ROOT)
    log_dir = ROOT / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'batch_server.log'
    log_handle = open(log_path, 'ab')
    print(f'正在启动服务端，日志: {log_path}')
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_handle.close()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server_is_up(host, port):
            print(f'服务端已就绪 {host}:{port} (pid {process.pid})')
            try:
                config_text = (ROOT / 'config_server.py').read_text(encoding='utf-8')
                record_loaded_model(process, config_text, loaded_model_path())
            except OSError:
                pass
            return process
        if process.poll() is not None:
            tail = _log_tail(log_path)
            raise RuntimeError(f'服务端启动后立刻退出 (code {process.returncode})。\n{tail}')
        time.sleep(1)
    process.terminate()
    tail = _log_tail(log_path)
    raise RuntimeError(f'{timeout:.0f}s 内服务端没有开始监听 {host}:{port}。\n{tail}')


def prepare_server(start: bool = True, timeout: float = 180, should_stop=None) -> str:
    """给窗口用的准备结果。端口通了才是就绪，失败原因原样返回。"""
    if should_stop is not None and should_stop():
        return '已取消'
    host, port = server_endpoint()
    if server_is_up(host, port, timeout=0.4):
        return f'ready {host}:{port}'
    if not start:
        return f'not-ready {host}:{port} 没开'
    try:
        ensure_server(True, timeout)
    except Exception as exc:
        return str(exc)
    if should_stop is not None and should_stop():
        return '已取消'
    if not server_is_up(host, port, timeout=0.4):
        return f'not-ready {host}:{port} 没有开始监听'
    return f'ready {host}:{port}'


def _log_tail(path: Path, limit: int = 20) -> str:
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError as exc:
        return f'(读不到日志: {exc})'
    return '\n'.join(lines[-limit:])


class TranscribeSession:
    """复用一条 WebSocket 和一份热词，逐个文件送给现有的 FileTranscriber。"""

    def __init__(self):
        self._ready = False
        self.app = None
        self.FileTranscriber = None

    def open(self) -> None:
        if self._ready:
            return
        os.chdir(ROOT)
        from config_client import ClientConfig
        from core.client.connection.websocket_manager import WebSocketManager
        from core.client.hotword.manager import HotwordManager
        from core.client.state import ClientState
        from core.client.transcribe.file_transcriber import FileTranscriber

        class _App:
            pass

        app = _App()
        app.loop = asyncio.get_running_loop()
        app.state = ClientState(app=app)
        app.ws = WebSocketManager(app)
        app.hotword = HotwordManager(
            threshold=ClientConfig.hot_thresh,
            similar_threshold=ClientConfig.hot_similar,
        )
        app.hotword.start()
        self.app = app
        self.FileTranscriber = FileTranscriber
        self._ready = True

    async def close(self) -> None:
        if not self._ready:
            return
        try:
            await self._drop_socket()
        finally:
            self.app.hotword.stop()
            self._ready = False

    async def _drop_socket(self) -> None:
        """关掉当前连接。close() 抛错时也要把引用清掉，否则下次还会以为连着。"""
        if not self._ready:
            return
        try:
            await self.app.ws.close()
        except Exception:
            self.app.state.websocket = None

    async def one(self, media: Path, timeout: float) -> None:
        self.open()
        transcriber = self.FileTranscriber(self.app, media)
        try:
            await asyncio.wait_for(self._run(transcriber), timeout=timeout)
        except asyncio.TimeoutError as exc:
            proc = getattr(transcriber, '_ffmpeg_proc', None)
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except OSError:
                    pass
            await self._drop_socket()
            raise TimeoutError(f'超过 {timeout:.0f}s 仍未完成') from exc
        if not outputs_ready(media):
            raise RuntimeError('转录结束，但没有同时留下非空的同名 srt、txt 和 json')

    async def _run(self, transcriber) -> None:
        if not await transcriber.check():
            raise RuntimeError('环境或服务端连接检查失败')
        if not await transcriber.send():
            detail = getattr(transcriber, 'send_error', '') or '音频发送失败'
            raise RuntimeError(detail)
        if not await transcriber.receive():
            raise RuntimeError('没有收到最终识别结果')


def split_audio(media: Path, directory: Path, segment_seconds: float) -> list[Path]:
    if shutil.which('ffmpeg') is None:
        raise RuntimeError('未找到 ffmpeg，无法切段')
    pattern = str(directory / 'part%04d.wav')
    result = subprocess.run(
        [
            'ffmpeg', '-hide_banner', '-y', '-i', str(media),
            '-vn', '-af', 'aresample=async=1:first_pts=0',
            '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le',
            '-f', 'segment', '-segment_time', str(segment_seconds),
            '-reset_timestamps', '1', pattern,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    parts = sorted(directory.glob('part*.wav'))
    if result.returncode != 0 or not parts:
        tail = '\n'.join(result.stderr.splitlines()[-15:])
        raise RuntimeError(f'ffmpeg 切段失败\n{tail}')
    return parts


def publish_merged(media: Path, srt_text: str, txt_text: str, payload: dict) -> None:
    if not srt_text.strip() or not txt_text.strip():
        raise RuntimeError('切段结果合并后是空的')
    if not payload.get('tokens') and not payload.get('timestamps'):
        raise RuntimeError('切段结果合并后没有字级时间戳')
    txt_path = media.with_suffix('.txt')
    json_path = media.with_suffix('.json')
    srt_path = media.with_suffix('.srt')
    # srt 最后写。中途失败时旁边还没有跳过标记，下次会再做一遍。
    _replace_text(txt_path, txt_text)
    _replace_text(json_path, json.dumps(payload, ensure_ascii=False))
    _replace_text(srt_path, srt_text)


def _replace_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)


class BatchCancelled(RuntimeError):
    """用户按下停止。已经写好的字幕留下，后面的文件不再开始。"""


class StopFlag:
    def __init__(self):
        self._event = threading.Event()

    def request(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    def checkpoint(self) -> None:
        if self.is_set():
            raise BatchCancelled('已停止')


async def transcribe_segments(
    session: TranscribeSession,
    media: Path,
    segment_seconds: float,
    timeout_factor: float,
    min_timeout: float,
    stop: StopFlag | None = None,
) -> None:
    directory = Path(tempfile.mkdtemp(prefix='capswriter-batch-'))
    try:
        parts = split_audio(media, directory, segment_seconds)
        srt_chunks: list[tuple[str, float]] = []
        txt_chunks: list[str] = []
        json_chunks: list[tuple[dict, float]] = []
        offset = 0.0
        for index, part in enumerate(parts, start=1):
            if stop is not None:
                stop.checkpoint()
            print(f'    切段 {index}/{len(parts)}: {part.name}')
            duration = probe_duration(part) or segment_seconds
            await _attempt(
                session,
                part,
                file_timeout(duration, timeout_factor, min_timeout),
            )
            srt_chunks.append((part.with_suffix('.srt').read_text(encoding='utf-8'), offset))
            txt_chunks.append(part.with_suffix('.txt').read_text(encoding='utf-8'))
            payload = json.loads(part.with_suffix('.json').read_text(encoding='utf-8'))
            if not isinstance(payload, dict):
                raise RuntimeError(f'{part.name} 的 json 不是对象')
            json_chunks.append((payload, offset))
            offset += duration
        publish_merged(
            media,
            merge_srt(srt_chunks),
            merge_txt(txt_chunks),
            merge_json(json_chunks),
        )
    finally:
        shutil.rmtree(directory, ignore_errors=True)


async def _attempt(
    session: TranscribeSession,
    media: Path,
    timeout: float,
    tries: int = 2,
    stop: StopFlag | None = None,
) -> None:
    last = '未知错误'
    for attempt in range(1, tries + 1):
        if stop is not None:
            stop.checkpoint()
        try:
            await session.one(media, timeout)
            return
        except BatchCancelled:
            raise
        except Exception as exc:
            last = str(exc)
            print(f'    第 {attempt}/{tries} 次失败: {last}')
            await session._drop_socket()
    raise RuntimeError(last)


async def transcribe_media(
    session: TranscribeSession,
    media: Path,
    segment_seconds: float,
    timeout_factor: float,
    min_timeout: float,
    long_fallback: bool,
    stop: StopFlag | None = None,
) -> str:
    """成功时返回 whole 或 segmented。长文件先切，不再失败后再切一次。"""
    if stop is not None:
        stop.checkpoint()
    duration = probe_duration(media)
    chunk = presplit_seconds(duration, segment_seconds, long_fallback)
    if plan_segments(duration, chunk):
        print(f'    时长 {duration:.0f}s，先按 {chunk:.0f}s 切开再识别')
        await transcribe_segments(
            session, media, chunk, timeout_factor, min_timeout, stop,
        )
        return 'segmented'
    await _attempt(
        session, media, file_timeout(duration, timeout_factor, min_timeout), stop=stop,
    )
    return 'whole'


async def run_batch(args: argparse.Namespace, stop: StopFlag | None = None) -> Report:
    files, errors = collect_media(args.paths, recursive=not args.no_recursive, hidden=args.hidden)
    report = Report()
    for path, reason in errors:
        report.failed.append({'path': str(path), 'error': reason})

    pending = []
    for media in files:
        if not args.force and is_complete(media):
            report.skipped.append(str(media))
        else:
            pending.append(media)

    print(f'找到 {len(files)} 个音视频，跳过 {len(report.skipped)} 个，待转录 {len(pending)} 个')
    if args.dry_run:
        for media in pending:
            print(f'  将转录: {media}')
        return report
    if not pending:
        return report

    flag_error = output_flags_error()
    if flag_error:
        raise RuntimeError(flag_error)
    if shutil.which('ffmpeg') is None:
        raise RuntimeError('未找到 ffmpeg。文件转录要用它抽出 16kHz 单声道音频')

    chosen = getattr(args, 'model', None)
    if chosen:
        host, port = server_endpoint()
        server_up = server_is_up(host, port, timeout=0.4)
        started = listening_server_started_at(port) if server_up else None
        apply_model_choice(
            chosen,
            restart=restart_running_server,
            server_up=server_up,
            loaded_model=read_loaded_model(),
            config_stale=config_is_newer_than_server(ROOT / 'config_server.py', started),
        )
    server = ensure_server(start=not args.no_start_server, timeout=args.server_timeout)
    session = TranscribeSession()
    try:
        for index, media in enumerate(pending, start=1):
            if stop is not None:
                stop.checkpoint()
            if not args.force and is_complete(media):
                print(f'  已有字幕，不复写 {media}')
                report.skipped.append(str(media))
                continue
            print(f'[{index}/{len(pending)}] {media}')
            try:
                mode = await transcribe_media(
                    session,
                    media,
                    segment_seconds=args.segment_seconds,
                    timeout_factor=args.timeout_factor,
                    min_timeout=args.min_timeout,
                    long_fallback=not args.no_long_fallback,
                    stop=stop,
                )
            except BatchCancelled:
                print('  已停止，后面的文件不再开始')
                report.stopped = True
                break
            except Exception as exc:
                print(f'  失败: {exc}')
                report.failed.append({'path': str(media), 'error': str(exc)})
                continue
            print(f'  完成 ({mode})')
            report.ok.append(str(media))
    finally:
        await session.close()
        if server is not None and args.stop_server:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        elif server is not None:
            print(f'服务端保持运行 (pid {server.pid})。不需要时再结束它。')
    return report


def write_report(report: Report) -> Path:
    path = ROOT / 'logs' / 'batch_transcribe_report.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'ok': report.ok,
        'skipped': report.skipped,
        'failed': report.failed,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='递归转录文件夹里的音视频。没有同名 srt 时生成 srt、txt 和 json；已有 srt 则跳过',
    )
    parser.add_argument('paths', nargs='+', type=Path, help='文件或文件夹，可以传多个')
    parser.add_argument(
        '--model',
        choices=MODEL_ARGUMENTS,
        default=None,
        help='开始前写入 config_server.py。Qwen3-ASR 用 qwen_asr:1.7b 或 qwen_asr:0.6b。配置或正在运行的模型不一样时先重启服务端',
    )
    parser.add_argument('--no-recursive', action='store_true', help='只看文件夹的第一层')
    parser.add_argument('--force', action='store_true', help='即使已有同名 srt 也重做')
    parser.add_argument('--hidden', action='store_true', help='包含点开头的文件和目录')
    parser.add_argument('--dry-run', action='store_true', help='只列出将要转录的文件')
    parser.add_argument('--no-start-server', action='store_true', help='服务端没开时不要自动启动')
    parser.add_argument('--stop-server', action='store_true', help='结束后关掉本次启动的服务端')
    parser.add_argument('--server-timeout', type=float, default=180, help='等待服务端监听的秒数')
    parser.add_argument('--timeout-factor', type=float, default=4.0, help='单文件超时 = 时长 × 系数 + 60 秒')
    parser.add_argument('--min-timeout', type=float, default=180, help='单文件最少等待秒数')
    parser.add_argument(
        '--segment-seconds', type=float, default=0,
        help='大于 0 时用这个秒数切段。0 表示只有超过 2 小时才按 2 小时先切开',
    )
    parser.add_argument(
        '--no-long-fallback', action='store_true',
        help='超过 2 小时也不预切，整文件直接送识别',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    incoming = list(sys.argv[1:] if argv is None else argv)
    if incoming[:1] == ['--prepare']:
        start = '--no-start-server' not in incoming
        message = prepare_server(start=start, timeout=SERVER_WAIT_SECONDS)
        print(message)
        return 0 if str(message).startswith('ready ') else 1
    if incoming == ['--stop-background']:
        stop_background_servers(ROOT, server_endpoint()[1])
        return 0
    if not incoming:
        if sys.platform == 'darwin':
            print('macOS 批量窗口在 CapsWriter.app 里，不打开 Tk。请传入文件或文件夹。', file=sys.stderr)
            return 2
        return run_gui()
    args = build_parser().parse_args(incoming)
    args.segment_hours = None
    return execute_batch(args)


def read_model_type(text, choices=MODEL_IDS):
    """从配置文本里读当前模型。认不出就用第一项。"""
    match = re.search(r"model_type\s*=\s*['\"]([A-Za-z0-9_]+)['\"]", text or '')
    found = match.group(1) if match else ''
    if found in choices:
        return found
    return choices[0]


def write_model_type(text, model, choices=MODEL_IDS):
    """只替换 model_type 这一行。其它配置不动。"""
    if model not in choices:
        raise ValueError(f'不支持的模型: {model}')
    pattern = r"(model_type\s*=\s*['\"])[A-Za-z0-9_]+(['\"])"
    updated, count = re.subn(pattern, lambda match: match.group(1) + model + match.group(2), text or '', count=1)
    if count != 1:
        raise ValueError('config_server.py 里没有 model_type')
    return updated


def current_model_type(path, choices=MODEL_IDS):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError:
        return choices[0]
    return read_model_type(text, choices)


def save_model_type(path, model, choices=MODEL_IDS):
    file = Path(path)
    text = file.read_text(encoding='utf-8')
    file.write_text(write_model_type(text, model, choices), encoding='utf-8')


def read_qwen_variant(text):
    """读 Qwen 规格。没有这一行时按 auto。"""
    match = _VARIANT_RE.search(text or '')
    found = match.group('value').lower() if match else 'auto'
    if found in ('1.7b', '1.7'):
        return '1.7b'
    if found in ('0.6b', '0.6'):
        return '0.6b'
    return 'auto'


def write_qwen_variant(text, variant):
    """只替换 qwen_mlx_variant 这一行。"""
    if variant not in _QWEN_VARIANTS:
        raise ValueError(f'不支持的 Qwen 规格: {variant}')

    def replace(match):
        return match.group('indent') + match.group('quote') + variant + match.group('quote')

    updated, count = _VARIANT_RE.subn(replace, text or '', count=1)
    if count != 1:
        raise ValueError('config_server.py 里没有 qwen_mlx_variant')
    return updated


def effective_qwen_variant(preference='auto', memory=None):
    """auto 按统一内存选规格，规则和加载模型时相同。"""
    from core.server.engines.mlx.variant import MEMORY_16GB, select_qwen_variant

    if memory is None:
        try:
            import psutil
            memory = int(psutil.virtual_memory().total)
        except Exception:
            memory = MEMORY_16GB
    variant, _repo, _dirname = select_qwen_variant(preference, memory)
    return variant


def split_model_choice(choice):
    """菜单值可以是 qwen_asr:1.7b。旧的 qwen_asr 不改规格。"""
    text = str(choice or '').strip()
    if text in MENU_IDS and ':' in text:
        engine, variant = text.split(':', 1)
        if engine not in MODEL_IDS or variant not in _QWEN_VARIANTS:
            raise ValueError(f'不支持的模型: {choice}')
        return engine, variant
    if text in MODEL_IDS:
        return text, None
    raise ValueError(f'不支持的模型: {choice}')


def menu_id_for(engine, variant=None, memory=None):
    if engine == 'qwen_asr':
        size = variant if variant in _QWEN_VARIANTS else effective_qwen_variant(variant or 'auto', memory)
        return f'qwen_asr:{size}'
    if engine in MODEL_IDS:
        return engine
    return MENU_IDS[0]


def model_label(choice):
    return _MODEL_LABELS.get(choice, choice)


def read_model_choice(text, memory=None):
    return menu_id_for(read_model_type(text), read_qwen_variant(text), memory)


def write_model_choice(text, choice):
    """Qwen 的两个菜单项同时写 model_type 和 qwen_mlx_variant。其它模型只写引擎。"""
    engine, variant = split_model_choice(choice)
    updated = write_model_type(text, engine)
    if variant:
        updated = write_qwen_variant(updated, variant)
    return updated


def normalize_menu_model(model, config_text='', memory=None):
    if model in MENU_IDS:
        return model
    if model in MODEL_IDS and model != 'qwen_asr':
        return model
    if model == 'qwen_asr':
        return 'qwen_asr:1.7b'
    if config_text:
        return read_model_choice(config_text, memory)
    return MENU_IDS[0]


def stamp_line(line, now=None):
    """进度行前面加上日期和时间，精确到毫秒。已经带时间的日志不再加一次。"""
    text = str(line or '')
    if re.match(r'^\[\d{4}-\d{2}-\d{2} \d\d:\d\d:\d\d\.\d{3}\]', text):
        return text
    moment = datetime.now() if now is None else now
    prefix = moment.strftime('[%Y-%m-%d %H:%M:%S.') + f'{moment.microsecond // 1000:03d}]'
    return f'{prefix} {text}' if text else prefix


def log_line_visible(line, level):
    """窗口只显示不低于所选等级的日志。进度行不按等级隐藏，另按 30 秒收一次。"""
    rank = LOG_RANK.get(str(level or 'INFO').upper(), LOG_RANK['INFO'])
    match = re.match(
        r'^(?:\[?\d{4}-\d{2}-\d{2}[ T]\d\d:\d\d:\d\d(?:\.\d+)?\]?\s+)?([A-Z]{4,8})\b',
        line or '',
    )
    if match is None:
        return True
    found = LOG_RANK.get(match.group(1))
    if found is None:
        return True
    return found >= rank


def batch_exit_label(code):
    if code == 130:
        return '已停止'
    if code == 0:
        return '完成'
    if code == 1:
        return '完成，有失败'
    return '没有开始'


def settings_from_form(values: dict) -> argparse.Namespace:
    """窗口里的勾选收成命令行同一套参数。等待和切开时长固定，不从窗口读。"""
    target = str(values.get('target') or '').strip()
    if not target:
        raise ValueError('先填入或打开一个文件、文件夹')
    return argparse.Namespace(
        paths=[Path(target)],
        no_recursive=not bool(values.get('recursive', True)),
        force=bool(values.get('force', False)),
        hidden=bool(values.get('hidden', False)),
        dry_run=False,
        no_start_server=not bool(values.get('start_server', True)),
        stop_server=bool(values.get('stop_server', False)),
        server_timeout=SERVER_WAIT_SECONDS,
        timeout_factor=FILE_TIMEOUT_FACTOR,
        min_timeout=FILE_MIN_TIMEOUT,
        segment_seconds=0.0,
        no_long_fallback=not bool(values.get('split_long', True)),
        segment_hours=SPLIT_AFTER_SECONDS / 3600,
        model=str(values.get('model') or MODEL_IDS[0]),
        log_level=str(values.get('log_level') or 'INFO').upper(),
    )


def tcl_list(data):
    """拆开 Tk 拖放给出的路径列表。花括号里的空格属于同一个路径。"""
    text = str(data or '')
    parts = []
    token = []
    depth = 0
    escaped = False
    for char in text:
        if escaped:
            token.append(char)
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if char == '{' and depth == 0 and not token:
            depth = 1
            continue
        if char == '{' and depth:
            depth += 1
            token.append(char)
            continue
        if char == '}' and depth:
            depth -= 1
            if depth:
                token.append(char)
            else:
                parts.append(''.join(token))
                token = []
            continue
        if char.isspace() and depth == 0:
            if token:
                parts.append(''.join(token))
                token = []
            continue
        token.append(char)
    if token:
        parts.append(''.join(token))
    return parts


def dropped_paths(data):
    """把拖进来的文件或文件夹收成路径。带空格的路径按 Tcl 列表拆开。"""
    return [part for part in tcl_list(data) if part]


def accept_drop(target, data):
    """多个路径只留下第一个。地址栏一次只转一个文件或文件夹。"""
    paths = dropped_paths(data)
    if not paths:
        return False
    target.set(paths[0])
    return True


def bind_file_drop(widget, on_drop, dnd_files):
    """地址栏注册文件拖放。库没装上时保持粘贴和打开按钮。"""
    master = widget.winfo_toplevel() if hasattr(widget, 'winfo_toplevel') else None
    if dnd_files is None or master is None or not hasattr(master, 'drop_target_register'):
        return False
    try:
        widget.drop_target_register(dnd_files)
        widget.dnd_bind('<<Drop>>', on_drop)
    except Exception:
        return False
    return True


def interface_colors(style=None):
    """跟着系统外观选对比色。暗色用浅字深底，浅色反过来。"""
    if style is None:
        style = read_interface_style()
    if str(style).strip().lower() == 'dark':
        return '#f2f2f7', '#2c2c2e'
    return '#1d1d1f', '#fff8dc'


def read_interface_style():
    """读当前用户的浅色或暗色。读不到就当浅色，避免提示变成白字浅底。"""
    import platform
    if platform.system() != 'Darwin':
        return 'Light'
    try:
        result = subprocess.run(
            ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
            capture_output=True, text=True, timeout=1, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 'Light'
    text = (result.stdout or '').strip()
    return text or 'Light'


class _HoverTip:
    """鼠标停在控件上时说明它做什么。窗口本身不放这些句子。"""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind('<Enter>', self._show, add='+')
        widget.bind('<Leave>', self._hide, add='+')

    def _show(self, _event=None):
        if self.tip is not None:
            return
        import tkinter as tk
        foreground, background = interface_colors()
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f'+{x}+{y}')
        tk.Label(
            self.tip, text=self.text, justify='left',
            foreground=foreground, background=background,
            relief='solid', borderwidth=1, padx=6, pady=3, wraplength=280,
        ).pack()

    def _hide(self, _event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


def close_choice_path(root=None) -> Path:
    """记住关闭按钮是缩到菜单栏还是退出。放在 logs 里，不进版本库。"""
    return Path(root or ROOT) / 'logs' / 'batch_window_close.txt'


def read_close_choice(path) -> str | None:
    try:
        text = Path(path).read_text(encoding='utf-8').strip().lower()
    except OSError:
        return None
    if text in (CLOSE_TRAY, CLOSE_QUIT):
        return text
    return None


def write_close_choice(path, choice) -> None:
    if choice not in (CLOSE_TRAY, CLOSE_QUIT):
        raise ValueError(choice)
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_suffix(file.suffix + '.partial')
    temporary.write_text(choice + '\n', encoding='utf-8')
    os.replace(temporary, file)


def _server_command(command) -> bool:
    text = command or ''
    return 'start_server' in text or 'CapsWriter Server' in text


def _ffmpeg_command(command) -> bool:
    parts = (command or '').split()
    if not parts:
        return False
    return os.path.basename(parts[0]) == 'ffmpeg'


def recorded_server_pid(base_dir) -> int:
    from core.tools.instance_guard import read_record, server_lock_path
    record = read_record(server_lock_path(base_dir))
    if not record or record.get('mark') != 'capswriter-server':
        return 0
    try:
        pid = int(record.get('pid', '0'))
    except (TypeError, ValueError):
        return 0
    return pid if pid > 1 else 0


def descendant_pids(root, children_of, self_pid) -> list[int]:
    found = []
    seen = {root, self_pid}
    pending = list(children_of(root) or [])
    while pending:
        pid = pending.pop()
        if pid in seen or pid <= 1:
            continue
        seen.add(pid)
        found.append(pid)
        pending.extend(children_of(pid) or [])
    return found


def server_pids_to_stop(recorded_pid, listeners, command_of, children_of, self_pid) -> list[int]:
    """服务端、它的子进程，以及本程序拉起的 ffmpeg。别的端口占用和自己都不动。"""
    roots = []
    for pid in [recorded_pid, *(listeners or [])]:
        if pid <= 1 or pid == self_pid or pid in roots:
            continue
        if _server_command(command_of(pid)):
            roots.append(pid)
    for pid in children_of(self_pid) or []:
        if pid <= 1 or pid == self_pid or pid in roots:
            continue
        command = command_of(pid)
        if _server_command(command) or _ffmpeg_command(command):
            roots.append(pid)
    ordered = []
    seen = set()

    def add(pid):
        if pid <= 1 or pid == self_pid or pid in seen:
            return
        seen.add(pid)
        ordered.append(pid)

    for root_pid in roots:
        add(root_pid)
        for child in descendant_pids(root_pid, children_of, self_pid):
            add(child)
    return ordered


def signal_pids(pids, kill, alive, pause, term=None, kill_sig=None) -> None:
    term = signal.SIGTERM if term is None else term
    kill_sig = signal.SIGKILL if kill_sig is None else kill_sig
    for pid in pids:
        try:
            kill(pid, term)
        except OSError:
            pass
    if pause is not None:
        pause(0.4)
    for pid in pids:
        try:
            if alive(pid):
                kill(pid, kill_sig)
        except OSError:
            pass


def listener_pids(port) -> list[int]:
    try:
        result = subprocess.run(
            ['lsof', '-nP', f'-iTCP:{int(port)}', '-sTCP:LISTEN', '-t'],
            capture_output=True, text=True, check=False, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in (result.stdout or '').splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid > 1:
            found.append(pid)
    return found


def process_command(pid) -> str:
    if pid <= 1:
        return ''
    try:
        out = subprocess.check_output(
            ['ps', '-p', str(int(pid)), '-o', 'command='],
            text=True, stderr=subprocess.DEVNULL, timeout=2,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        return ''
    return out.strip()


def process_children_map() -> dict[int, list[int]]:
    try:
        result = subprocess.run(
            ['ps', '-ax', '-o', 'pid=,ppid='],
            capture_output=True, text=True, check=False, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    children = {}
    for line in (result.stdout or '').splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, parent = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(parent, []).append(pid)
    return children


def stop_background_servers(
    base_dir, port, kill=None, command_lookup=None, listener_lookup=None,
    children_lookup=None, recorded_pid=None, self_pid=None, alive=None, pause=None,
) -> list[int]:
    """结束本程序的服务端和 ffmpeg。命令行对不上的监听不杀。"""
    killer = os.kill if kill is None else kill
    commands = process_command if command_lookup is None else command_lookup
    listeners = listener_pids if listener_lookup is None else listener_lookup
    if children_lookup is None:
        mapping = process_children_map()
        children_lookup = lambda pid: mapping.get(pid, [])
    if recorded_pid is None:
        recorded_pid = recorded_server_pid(base_dir)
    own = os.getpid() if self_pid is None else self_pid
    pids = server_pids_to_stop(
        recorded_pid, listeners(port), commands, children_lookup, own,
    )
    signal_pids(
        pids, killer,
        _pid_alive if alive is None else alive,
        time.sleep if pause is None else pause,
    )
    return pids


def ask_close_choice(master):
    """第一次关闭时问清是缩到菜单栏还是退出。关掉这个问句不算选择。"""
    import tkinter as tk
    from tkinter import ttk
    picked = {'value': None}
    dialog = tk.Toplevel(master)
    dialog.title('关闭批量转录')
    dialog.resizable(False, False)
    dialog.transient(master)
    ttk.Label(
        dialog,
        text='关闭窗口时缩到菜单栏，还是退出并结束后台服务？\n选过一次，以后关闭按钮就按这次的来，不再询问。',
        justify='left',
    ).pack(padx=16, pady=(14, 8))
    row = ttk.Frame(dialog)
    row.pack(padx=16, pady=(0, 14))

    def choose(value):
        picked['value'] = value
        dialog.destroy()

    ttk.Button(row, text='缩小到托盘', command=lambda: choose(CLOSE_TRAY)).pack(side='left')
    ttk.Button(row, text='退出', command=lambda: choose(CLOSE_QUIT)).pack(side='left', padx=8)
    dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
    dialog.grab_set()
    master.wait_window(dialog)
    return picked['value']


def _batch_tray_target():
    global _BatchTrayTarget
    if _BatchTrayTarget is not None:
        return _BatchTrayTarget
    import AppKit

    class BatchTrayTarget(AppKit.NSObject):
        def show_(self, _sender):
            callback = getattr(self, 'on_show', None)
            if callback is not None:
                callback()

        def quit_(self, _sender):
            callback = getattr(self, 'on_quit', None)
            if callback is not None:
                callback()

    _BatchTrayTarget = BatchTrayTarget
    return _BatchTrayTarget


def _install_darwin_batch_tray(on_show, on_quit) -> bool:
    try:
        import AppKit
    except ImportError:
        return False
    status = AppKit.NSStatusBar.systemStatusBar()
    item = status.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
    button = item.button()
    if button is not None:
        button.setTitle_('批量')
        button.setToolTip_('批量转录')
    menu = AppKit.NSMenu.alloc().init()
    target = _batch_tray_target().alloc().init()
    target.on_show = on_show
    target.on_quit = on_quit
    show = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('显示窗口', 'show:', '')
    show.setTarget_(target)
    leave = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('退出', 'quit:', '')
    leave.setTarget_(target)
    menu.addItem_(show)
    menu.addItem_(leave)
    item.setMenu_(menu)
    _batch_tray['item'] = item
    _batch_tray['bar'] = status
    _batch_tray['target'] = target
    return True


def _install_pystray_batch_tray(on_show, on_quit) -> bool:
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return False
    image = Image.new('RGB', (64, 64), '#2f9e44')
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill='#f2f2f7')
    menu = pystray.Menu(
        pystray.MenuItem('显示窗口', lambda icon, item: on_show()),
        pystray.MenuItem('退出', lambda icon, item: on_quit()),
    )
    icon = pystray.Icon('capswriter-batch', image, '批量转录', menu)
    threading.Thread(target=icon.run, daemon=True).start()
    _batch_tray['icon'] = icon
    return True


def install_batch_tray(on_show, on_quit) -> bool:
    """菜单栏图标。Mac 跟 Tk 共用主线程，不再另开一套事件循环。"""
    if _batch_tray.get('item') is not None or _batch_tray.get('icon') is not None:
        return True
    if sys.platform == 'darwin':
        return _install_darwin_batch_tray(on_show, on_quit)
    return _install_pystray_batch_tray(on_show, on_quit)


def remove_batch_tray() -> None:
    item = _batch_tray.pop('item', None)
    bar = _batch_tray.pop('bar', None)
    icon = _batch_tray.pop('icon', None)
    _batch_tray.pop('target', None)
    if item is not None and bar is not None:
        try:
            bar.removeStatusItem_(item)
        except Exception:
            pass
    if icon is not None:
        try:
            icon.stop()
        except Exception:
            pass


try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None


def run_gui(root=None, prepare=None, schedule_updates=None, model=None) -> int:
    """批量转录自己的窗口。不改 start_client 和 start_server。"""
    import tkinter as tk
    from tkinter import filedialog, ttk

    LAMP = {
        'off': '#c4c4c4',
        'red': '#d64545',
        'yellow': '#e0b000',
        'green': '#2f9e44',
    }

    class _QueueWriter:
        def __init__(self, queue):
            self.queue = queue

        def write(self, text):
            if not text:
                return
            lines = []
            for line in str(text).splitlines(keepends=True):
                ending = ''
                body = line
                if body.endswith('\n'):
                    ending = '\n'
                    body = body[:-1]
                    if body.endswith('\r'):
                        body = body[:-1]
                lines.append(stamp_line(body) + ending)
            self.queue.put(''.join(lines))

        def flush(self):
            return None

    class Window:
        def __init__(self, master, prepare=None, schedule_updates=True):
            self.master = master
            self.master.title('批量转录')
            self.master.geometry('860x620')
            self.master.minsize(760, 520)
            self._placed = False
            self.shown = False
            self.worker = None
            self.preparing = False
            self.ready = False
            self._prepare_call = prepare if prepare is not None else prepare_server
            self.stop = StopFlag()
            self.lines = []
            self.finish_code = None
            self.queue = queue.Queue()
            self.ready_queue = queue.Queue()
            self.finish_queue = queue.Queue()
            self.close_choice_path = close_choice_path()
            self._tray_ready = False
            self._progress = ProgressGate()
            self._build(tips=schedule_updates)
            if schedule_updates:
                self._show_now()
                self._place_on_screen()
            else:
                self.shown = True
            self._begin_prepare()
            if schedule_updates:
                self.master.after(120, self._drain)
                self.master.after(80, self._drain_ready)
                self.master.after(80, self._drain_finish)
            self.master.protocol('WM_DELETE_WINDOW', self._close)

        def _build(self, tips=True):
            pad = {'padx': 12, 'pady': 4}
            path_row = ttk.Frame(self.master)
            path_row.pack(fill='x', **pad)
            ttk.Label(path_row, text='地址').pack(side='left')
            self.target = tk.StringVar()
            entry = ttk.Entry(path_row, textvariable=self.target)
            entry.pack(side='left', fill='x', expand=True, padx=8)
            self._drop_bound = bind_file_drop(entry, self._on_drop, globals().get('DND_FILES'))
            open_button = ttk.Button(path_row, text='打开', command=self._browse)
            open_button.pack(side='left')
            self._tips = []
            if tips:
                self._tips.extend([
                    _HoverTip(entry, '粘贴路径，或从 Finder 把一个文件、文件夹拖到这里。程序自己判断是文件还是文件夹。'),
                    _HoverTip(open_button, '先选文件夹。取消后再选一个文件。'),
                ])

            options = ttk.LabelFrame(self.master, text='参数')
            options.pack(fill='x', padx=12, pady=8)
            self.recursive = tk.BooleanVar(value=True)
            self.split_long = tk.BooleanVar(value=True)
            self.force = tk.BooleanVar(value=False)
            self.hidden = tk.BooleanVar(value=False)
            self.start_server = tk.BooleanVar(value=True)
            self.stop_server = tk.BooleanVar(value=False)
            tool_row = ttk.Frame(self.master)
            tool_row.pack(fill='x', padx=12, pady=(0, 4))
            ttk.Label(tool_row, text='模型').pack(side='left')
            if model in MENU_IDS or model in MODEL_IDS:
                config_text = ''
            else:
                try:
                    config_text = (ROOT / 'config_server.py').read_text(encoding='utf-8')
                except OSError:
                    config_text = ''
            selected = normalize_menu_model(model, config_text)
            self.model = tk.StringVar(value=selected)
            model_box = ttk.Combobox(
                tool_row, textvariable=self.model, state='readonly', width=22,
                values=[label for _key, label in MODEL_CHOICES],
            )
            labels = {key: label for key, label in MODEL_CHOICES}
            keys = {label: key for key, label in MODEL_CHOICES}
            model_box.set(labels.get(self.model.get(), labels[MENU_IDS[0]]))
            self._model_keys = keys
            self._model_box = model_box
            model_box.pack(side='left', padx=(6, 16))
            ttk.Label(tool_row, text='日志').pack(side='left')
            self.log_level = tk.StringVar(value='INFO')
            level_box = ttk.Combobox(
                tool_row, textvariable=self.log_level, state='readonly', width=10,
                values=LOG_LEVELS,
            )
            level_box.pack(side='left', padx=6)
            if tips:
                self._tips.append(_HoverTip(model_box, 'Qwen3-ASR 可选 1.7B 或 0.6B。下次开始前写入配置并重启服务端。正在转录时不能换。'))
                self._tips.append(_HoverTip(level_box, '窗口里显示到哪一级。DEBUG 最详细，ERROR 只留错误。发送进度和转录进度各自只占一行，数字从 0、60、120 改到这段音频结束。'))

            checks = (
                (self.recursive, '包含子文件夹', '会进入里面的文件夹。关掉后只看这一层。'),
                (self.split_long, '长文件先切开', '超过 2 小时先切开再识别，最后仍合并成一个字幕、文本和 json。这个 2 小时是固定的。'),
                (self.force, '已有字幕也重做', '旁边已经写好同名 srt 时平常会跳过，不复写。空的或没写完的会再做。勾上后重新转录。'),
                (self.hidden, '包含隐藏文件', '名字以点开头的文件和文件夹也会处理。'),
                (self.start_server, '服务端没开就启动', '6016 没在听时，由这里拉起旁边的服务端。窗口不会等模型加载完才出现。'),
                (self.stop_server, '结束后关掉本次启动的服务端', '只关掉这一次拉起的服务端。原来就已经开着的不会关。'),
            )
            for index, (variable, label, hint) in enumerate(checks):
                box = ttk.Checkbutton(options, text=label, variable=variable)
                box.grid(row=index // 2, column=index % 2, sticky='w', padx=10, pady=3)
                self._tips.append(_HoverTip(box, hint))

            actions = ttk.Frame(self.master)
            actions.pack(fill='x', padx=12, pady=8)
            self.start_button = ttk.Button(actions, text='开始转录', command=self._start)
            self.start_button.pack(side='left')
            self.stop_button = ttk.Button(actions, text='停止转录', command=self._stop, state='disabled')
            self.stop_button.pack(side='left', padx=8)
            if tips:
                self._tips.append(_HoverTip(self.start_button, '绿灯之后才开始。单个文件最多等「时长的 4 倍再加 60 秒」，并且不少于 180 秒。识别完成会马上返回，不会故意等满。'))
                self._tips.append(_HoverTip(self.stop_button, '当前这段做完就停。已经写好的字幕保留，后面的文件不再开始。'))
            self.status = tk.StringVar(value='空闲')
            ttk.Label(actions, textvariable=self.status).pack(side='left', padx=8)

            lamp_row = ttk.Frame(self.master)
            lamp_row.pack(fill='x', padx=12, pady=(0, 4))
            self.lamp = tk.Canvas(
                lamp_row, width=18, height=18, highlightthickness=0, bd=0,
            )
            self.lamp.pack(side='left')
            self._lamp_dot = self.lamp.create_oval(2, 2, 16, 16, outline='', fill=LAMP['red'])
            self.ready_text = tk.StringVar(value='还没准备好')
            ready_label = ttk.Label(lamp_row, textvariable=self.ready_text)
            ready_label.pack(side='left', padx=6)
            if tips:
                self._tips.append(_HoverTip(
                    ready_label,
                    '红灯：还没准备好。黄灯：正在等服务端，最多 180 秒。绿灯 Ready：可以开始。这个等待不是识别速度，模型好了就会变绿。',
                ))

            log_frame = ttk.Frame(self.master)
            log_frame.pack(fill='both', expand=True, padx=12, pady=(0, 12))
            self.log = tk.Text(log_frame, height=16, wrap='word', state='disabled')
            scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
            self.log.configure(yscrollcommand=scroll.set)
            self.log.pack(side='left', fill='both', expand=True)
            scroll.pack(side='right', fill='y')

        def _place_on_screen(self):
            if self._placed:
                return
            self.master.update_idletasks()
            width = max(self.master.winfo_reqwidth(), 860)
            height = max(self.master.winfo_reqheight(), 620)
            screen_w = self.master.winfo_screenwidth()
            screen_h = self.master.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 3)
            self.master.geometry(f'{width}x{height}+{x}+{y}')
            self._placed = True

        def _show_now(self):
            """先把窗口画出来。服务端加载不能挡在这一步前面。"""
            self.master.update_idletasks()
            self.master.deiconify()
            self.master.lift()
            try:
                self.master.attributes('-topmost', True)
                self.master.update()
                self.master.attributes('-topmost', False)
            except tk.TclError:
                self.master.update()
            self.shown = True

        def _paint_lamp(self, color, text):
            self.lamp.itemconfigure(self._lamp_dot, fill=LAMP[color])
            self.ready_text.set(text)

        def _begin_prepare(self):
            if self.preparing or self.ready:
                return
            if not self.shown:
                self._show_now()
            start = bool(self.start_server.get())
            timeout = SERVER_WAIT_SECONDS
            self.preparing = True
            self.ready = False
            self._paint_lamp('yellow', '正在准备')
            self.start_button.configure(state='disabled')
            threading.Thread(
                target=self._prepare, args=(start, timeout), daemon=True,
            ).start()

        def _prepare(self, start, timeout):
            message = self._prepare_call(
                start=start,
                timeout=timeout,
                should_stop=lambda: not self.preparing,
            )
            failed = not message.startswith('ready ')
            self.ready_queue.put((message, failed))

        def _drain_ready(self):
            try:
                if not self.master.winfo_exists():
                    return
                while True:
                    message, failed = self.ready_queue.get_nowait()
                    self._prepared(message, failed)
            except Exception:
                pass
            try:
                if self.master.winfo_exists():
                    self.master.after(80, self._drain_ready)
            except tk.TclError:
                return

        def _prepared(self, message, failed):
            self.preparing = False
            if not self.master.winfo_exists():
                return
            if message == '已取消':
                self.ready = False
                self._paint_lamp('red', '还没准备好')
            elif failed:
                self.ready = False
                self._paint_lamp('red', '还没准备好')
                self.status.set(message)
            else:
                self.ready = True
                self._paint_lamp('green', 'Ready')
                self.status.set('空闲')
            if self.worker is None or not self.worker.is_alive():
                self.start_button.configure(state='normal')
            self._append(message + '\n')

        def _on_drop(self, event):
            accept_drop(self.target, getattr(event, 'data', ''))
            return event.action if hasattr(event, 'action') else None

        def _browse(self):
            choice = filedialog.askdirectory(title='打开文件夹')
            if not choice:
                choice = filedialog.askopenfilename(title='打开文件')
            if choice:
                self.target.set(choice)

        def _append(self, text):
            current = self.log.get('1.0', 'end-1c')
            updated = current
            for line in str(text).splitlines():
                body = line.rstrip('\r')
                if not body or not log_line_visible(body, self.log_level.get()):
                    continue
                updated = apply_progress_line(updated, body, self._progress)
            if updated == current:
                return
            if not updated.endswith('\n'):
                updated += '\n'
            self.log.configure(state='normal')
            self.log.delete('1.0', 'end')
            self.log.insert('1.0', updated)
            self.log.see('end')
            self.log.configure(state='disabled')

        def _drain(self):
            try:
                if not self.master.winfo_exists():
                    return
                while True:
                    self._append(self.queue.get_nowait())
            except Exception:
                pass
            try:
                if self.master.winfo_exists():
                    self.master.after(120, self._drain)
            except tk.TclError:
                return

        def _values(self):
            shown = self._model_box.get()
            return {
                'target': self.target.get(),
                'recursive': self.recursive.get(),
                'split_long': self.split_long.get(),
                'force': self.force.get(),
                'hidden': self.hidden.get(),
                'start_server': self.start_server.get(),
                'stop_server': self.stop_server.get(),
                'model': self._model_keys.get(shown, MENU_IDS[0]),
                'log_level': self.log_level.get(),
            }

        def _start(self):
            if self.worker is not None and self.worker.is_alive():
                return
            if not self.ready:
                self.status.set('还没准备好')
                return
            try:
                args = settings_from_form(self._values())
            except ValueError as exc:
                self.status.set(str(exc))
                return
            self.stop = StopFlag()
            self.finish_code = None
            self._set_controls_busy(True)
            self.status.set('转录中')
            self.worker = threading.Thread(target=self._run, args=(args, self.stop), daemon=True)
            self.worker.start()

        def _set_controls_busy(self, busy):
            state = 'disabled' if busy else 'normal'
            self.start_button.configure(state='disabled' if busy else 'normal')
            self.stop_button.configure(state='normal' if busy else 'disabled')
            self._model_box.configure(state='disabled' if busy else 'readonly')

        def _run(self, args, stop):
            # macOS 上只有主线程能碰 Tk。这里只写队列，状态由 _drain_finish 改。
            writer = _QueueWriter(self.queue)
            old_out, old_err = sys.stdout, sys.stderr
            code = 2
            try:
                sys.stdout = writer
                sys.stderr = writer
                code = execute_batch(args, stop)
            except Exception as exc:
                print(exc)
                code = 2
            finally:
                sys.stdout = old_out
                sys.stderr = old_err
                self.finish_code = code
                self.finish_queue.put(code)

        def _drain_finish(self):
            try:
                if not self.master.winfo_exists():
                    return
                while True:
                    code = self.finish_queue.get_nowait()
                    self._finished(code)
            except queue.Empty:
                pass
            except tk.TclError:
                return
            try:
                if self.master.winfo_exists():
                    self.master.after(80, self._drain_finish)
            except tk.TclError:
                return

        def _stop(self):
            self.stop.request()
            self.status.set('正在停止')
            self.stop_button.configure(state='disabled')

        def _finished(self, code):
            self.finish_code = code
            self.status.set(batch_exit_label(code))
            self._set_controls_busy(False)

        def _close(self):
            saved = read_close_choice(self.close_choice_path)
            choice = saved
            if choice is None:
                choice = self._ask_close()
            if choice == CLOSE_TRAY:
                if not self._hide_to_tray():
                    self.status.set('托盘不可用，窗口还在')
                    return
                if saved is None:
                    self._remember_close(CLOSE_TRAY)
                return
            if choice != CLOSE_QUIT:
                return
            if saved is None:
                self._remember_close(CLOSE_QUIT)
            self._quit_app()

        def _remember_close(self, choice):
            try:
                write_close_choice(self.close_choice_path, choice)
            except OSError:
                return

        def _ask_close(self):
            ask = getattr(self, 'ask_close', None)
            if ask is not None:
                return ask()
            return ask_close_choice(self.master)

        def _hide_to_tray(self):
            if not self._install_tray():
                return False
            try:
                self.master.withdraw()
            except tk.TclError:
                return False
            return True

        def _install_tray(self):
            if self._tray_ready:
                return True

            def show():
                self.master.after(0, self._show_from_tray)

            def leave():
                self.master.after(0, self._quit_app)

            self._tray_ready = bool(install_batch_tray(show, leave))
            return self._tray_ready

        def _show_from_tray(self):
            try:
                if not self.master.winfo_exists():
                    return
                self.master.deiconify()
                self.master.lift()
            except tk.TclError:
                return

        def _stop_background(self):
            _host, port = server_endpoint()
            stop_background_servers(ROOT, port)

        def _quit_app(self):
            self.preparing = False
            self.stop.request()
            try:
                self._stop_background()
            finally:
                remove_batch_tray()
                self._tray_ready = False
                try:
                    self.master.quit()
                except tk.TclError:
                    pass
                try:
                    self.master.destroy()
                except tk.TclError:
                    pass

    created = root is None
    if created and TkinterDnD is not None:
        master = TkinterDnD.Tk()
    else:
        master = tk.Tk() if created else root
    if schedule_updates is None:
        schedule_updates = created
    window = Window(master, prepare=prepare, schedule_updates=schedule_updates)
    if created:
        master.mainloop()
    else:
        master._batch_window = window
    return 0


def execute_batch(args: argparse.Namespace, stop: StopFlag | None = None) -> int:
    """跑一轮批量转录。窗口和命令行共用。"""
    global SPLIT_AFTER_SECONDS
    if args.segment_seconds < 0:
        print('--segment-seconds 不能是负数', file=sys.stderr)
        return 2
    hours = getattr(args, 'segment_hours', None)
    previous = SPLIT_AFTER_SECONDS
    if hours is not None:
        SPLIT_AFTER_SECONDS = int(float(hours) * 3600)
    lock = BatchLock(ROOT / 'logs' / 'batch_transcribe.lock')
    if not args.dry_run:
        try:
            lock.acquire()
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            SPLIT_AFTER_SECONDS = previous
            return 2
    try:
        report = asyncio.run(run_batch(args, stop))
    except KeyboardInterrupt:
        print('\n已中断', file=sys.stderr)
        return 130
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 2
    finally:
        SPLIT_AFTER_SECONDS = previous
        lock.release()

    if stop is not None and stop.is_set():
        report.stopped = True
    if not args.dry_run:
        report_path = write_report(report)
        print(
            f'完成 {len(report.ok)}，跳过 {len(report.skipped)}，'
            f'失败 {report.failed_count}。记录: {report_path}'
        )
    if report.stopped:
        return 130
    return 1 if report.failed_count else 0


def lead_process_group(setpgrp=None) -> bool:
    """本进程当组长。停止时的信号能到 ffmpeg，到不了另开会话的服务端。

    测试会调用 main()，所以只有直接运行这个文件时才入组。
    """
    if setpgrp is None:
        setpgrp = os.setpgrp
    try:
        setpgrp()
    except OSError:
        return False
    return True


if __name__ == '__main__':
    lead_process_group()
    sys.exit(main())
