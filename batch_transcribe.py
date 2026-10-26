# coding: utf-8
"""批量把文件夹里的音视频转录成同名 .srt 和 .txt。

用法:
    python batch_transcribe.py /path/to/media
    python batch_transcribe.py a.mp4 b.mkv /path/to/folder

和旧的 capswriter-all.ps1 / media2srt.py 相比:
- 不再先导出整条 WAV，也不再为每个片段新开一个客户端进程。
  当前服务端已经按 config_client.file_seg_duration（默认 60 秒）流式识别。
- 同名 srt 和 txt 都在、且字幕里有时间轴时才跳过。只剩一半的文件会重做。
- 单个文件失败不影响后面的文件。超过 3 小时且整文件失败时，才按 2 小时切段重试。
- 服务端没开时自动拉起，端口通了就继续，不再固定睡 80 秒。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent

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
LONG_FILE_SECONDS = 3 * 60 * 60
FALLBACK_SEGMENT_SECONDS = 2 * 60 * 60
PART_MARK = '.capswriter-part-'

_TIME_RE = re.compile(
    r'(?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})'
)


@dataclass
class Report:
    ok: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)

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
    """同名 srt 和 txt 都在，且字幕里至少有一条时间轴。"""
    srt_path = media.with_suffix('.srt')
    txt_path = media.with_suffix('.txt')
    try:
        if not srt_path.is_file() or not txt_path.is_file():
            return False
        if srt_path.stat().st_size == 0 or txt_path.stat().st_size == 0:
            return False
        text = srt_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    return '-->' in text


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
        return max(minimum, LONG_FILE_SECONDS)
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
    if not ClientConfig.file_save_srt or not ClientConfig.file_save_txt:
        return 'config_client.py 里 file_save_srt 和 file_save_txt 都要为 True，否则无法留下同名字幕和文本'
    return None


def ensure_server(start: bool, timeout: float) -> subprocess.Popen | None:
    """端口已通时返回 None。否则按需启动 start_server.py，返回子进程。"""
    host, port = server_endpoint()
    if server_is_up(host, port):
        print(f'服务端已在 {host}:{port}')
        return None
    if not start:
        raise RuntimeError(f'服务端 {host}:{port} 没开。先运行 start_server.py，或去掉 --no-start-server')

    log_dir = ROOT / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'batch_server.log'
    log_handle = open(log_path, 'ab')
    print(f'正在启动服务端，日志: {log_path}')
    process = subprocess.Popen(
        [sys.executable, str(ROOT / 'start_server.py')],
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    log_handle.close()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server_is_up(host, port):
            print(f'服务端已就绪 {host}:{port} (pid {process.pid})')
            return process
        if process.poll() is not None:
            tail = _log_tail(log_path)
            raise RuntimeError(f'服务端启动后立刻退出 (code {process.returncode})。\n{tail}')
        time.sleep(1)
    process.terminate()
    tail = _log_tail(log_path)
    raise RuntimeError(f'{timeout:.0f}s 内服务端没有开始监听 {host}:{port}。\n{tail}')


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
        if not is_complete(media):
            raise RuntimeError('转录结束，但没有留下有效的同名 srt 和 txt')

    async def _run(self, transcriber) -> None:
        if not await transcriber.check():
            raise RuntimeError('环境或服务端连接检查失败')
        if not await transcriber.send():
            raise RuntimeError('音频发送失败')
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


def publish_merged(media: Path, srt_text: str, txt_text: str) -> None:
    if not srt_text.strip() or not txt_text.strip():
        raise RuntimeError('切段结果合并后是空的')
    srt_path = media.with_suffix('.srt')
    txt_path = media.with_suffix('.txt')
    _replace_text(srt_path, srt_text)
    _replace_text(txt_path, txt_text)


def _replace_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + '.partial')
    temporary.write_text(text, encoding='utf-8')
    os.replace(temporary, path)


async def transcribe_segments(
    session: TranscribeSession,
    media: Path,
    segment_seconds: float,
    timeout_factor: float,
    min_timeout: float,
) -> None:
    directory = Path(tempfile.mkdtemp(prefix='capswriter-batch-'))
    try:
        parts = split_audio(media, directory, segment_seconds)
        srt_chunks: list[tuple[str, float]] = []
        txt_chunks: list[str] = []
        offset = 0.0
        for index, part in enumerate(parts, start=1):
            print(f'    切段 {index}/{len(parts)}: {part.name}')
            duration = probe_duration(part) or segment_seconds
            await _attempt(
                session,
                part,
                file_timeout(duration, timeout_factor, min_timeout),
            )
            srt_chunks.append((part.with_suffix('.srt').read_text(encoding='utf-8'), offset))
            txt_chunks.append(part.with_suffix('.txt').read_text(encoding='utf-8'))
            offset += duration
        publish_merged(media, merge_srt(srt_chunks), merge_txt(txt_chunks))
    finally:
        shutil.rmtree(directory, ignore_errors=True)


async def _attempt(session: TranscribeSession, media: Path, timeout: float, tries: int = 2) -> None:
    last = '未知错误'
    for attempt in range(1, tries + 1):
        try:
            await session.one(media, timeout)
            return
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
) -> str:
    """成功时返回 whole 或 segmented。"""
    duration = probe_duration(media)
    if plan_segments(duration, segment_seconds):
        print(f'    时长 {duration:.0f}s，按 {segment_seconds:.0f}s 预切')
        await transcribe_segments(session, media, segment_seconds, timeout_factor, min_timeout)
        return 'segmented'

    try:
        await _attempt(session, media, file_timeout(duration, timeout_factor, min_timeout))
        return 'whole'
    except Exception:
        if not long_fallback or segment_seconds > 0 or duration < LONG_FILE_SECONDS:
            raise
        print(f'    整文件失败，且时长 {duration:.0f}s，改为按 {FALLBACK_SEGMENT_SECONDS // 3600} 小时切段重试')
        await transcribe_segments(
            session, media, FALLBACK_SEGMENT_SECONDS, timeout_factor, min_timeout,
        )
        return 'segmented-fallback'


async def run_batch(args: argparse.Namespace) -> Report:
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

    server = ensure_server(start=not args.no_start_server, timeout=args.server_timeout)
    session = TranscribeSession()
    try:
        for index, media in enumerate(pending, start=1):
            print(f'[{index}/{len(pending)}] {media}')
            try:
                mode = await transcribe_media(
                    session,
                    media,
                    segment_seconds=args.segment_seconds,
                    timeout_factor=args.timeout_factor,
                    min_timeout=args.min_timeout,
                    long_fallback=not args.no_long_fallback,
                )
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
        description='递归转录文件夹里的音视频，在同目录留下同名 .srt 和 .txt',
    )
    parser.add_argument('paths', nargs='+', type=Path, help='文件或文件夹，可以传多个')
    parser.add_argument('--no-recursive', action='store_true', help='只看文件夹的第一层')
    parser.add_argument('--force', action='store_true', help='即使已有 srt 和 txt 也重做')
    parser.add_argument('--hidden', action='store_true', help='包含点开头的文件和目录')
    parser.add_argument('--dry-run', action='store_true', help='只列出将要转录的文件')
    parser.add_argument('--no-start-server', action='store_true', help='服务端没开时不要自动启动')
    parser.add_argument('--stop-server', action='store_true', help='结束后关掉本次启动的服务端')
    parser.add_argument('--server-timeout', type=float, default=180, help='等待服务端监听的秒数')
    parser.add_argument('--timeout-factor', type=float, default=4.0, help='单文件超时 = 时长 × 系数 + 60 秒')
    parser.add_argument('--min-timeout', type=float, default=180, help='单文件最少等待秒数')
    parser.add_argument(
        '--segment-seconds', type=float, default=0,
        help='大于 0 时，超过这个时长就先切段再合并。0 表示整文件流式转录',
    )
    parser.add_argument(
        '--no-long-fallback', action='store_true',
        help='超过 3 小时且整文件失败时，不要自动按 2 小时切段重试',
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.segment_seconds < 0:
        print('--segment-seconds 不能是负数', file=sys.stderr)
        return 2
    lock = BatchLock(ROOT / 'logs' / 'batch_transcribe.lock')
    if not args.dry_run:
        try:
            lock.acquire()
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 2
    try:
        report = asyncio.run(run_batch(args))
    except KeyboardInterrupt:
        print('\n已中断', file=sys.stderr)
        return 130
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 2
    finally:
        lock.release()

    if not args.dry_run:
        report_path = write_report(report)
        print(
            f'完成 {len(report.ok)}，跳过 {len(report.skipped)}，'
            f'失败 {report.failed_count}。记录: {report_path}'
        )
    return 1 if report.failed_count else 0


if __name__ == '__main__':
    sys.exit(main())
