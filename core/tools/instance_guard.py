# coding: utf-8
"""Darwin 上保证只有一个服务端、一个菜单栏客户端。

探测「锁是不是我们的」时不抢 flock。抢一下再放开会让真正的服务端误以为自己是第二份。
服务端在拿到锁之后立刻写下 pid。进程还在、命令行也对，才算锁被占用。
"""
from __future__ import annotations

import errno
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path


SERVER_MARK = 'capswriter-server'
CLIENT_MARK = 'capswriter-client'
SERVER_APP_NAME = 'CapsWriter Server.app'
CLIENT_APP_NAME = 'CapsWriter.app'
_STATUS = logging.getLogger('capswriter.instance')


class Admission:
    def __init__(self, action, code, message, hold=None):
        self.action = action
        self.code = code
        self.message = message
        self.hold = hold


class Gate:
    def __init__(self, action, code, message, session=None):
        self.action = action
        self.code = code
        self.message = message
        self.session = session


class ServerHold:
    def __init__(self, fd):
        self._fd = fd

    def release(self):
        fd = self._fd
        self._fd = None
        if fd is not None:
            _unlock(fd)


class DarwinSession:
    """客户端自己的锁，外加一个用来接收文件的 Unix socket。"""

    def __init__(self, base_dir, fd):
        self.base_dir = Path(base_dir)
        self._fd = fd
        self._srv = None
        self._thread = None
        self._stop = threading.Event()

    def serve(self, on_files):
        import socket
        if self._srv is not None:
            return
        sock_path = client_sock_path(self.base_dir)
        try:
            sock_path.unlink()
        except OSError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            try:
                srv.set_inheritable(False)
            except Exception:
                pass
            srv.bind(str(sock_path))
            srv.listen(8)
            srv.settimeout(0.5)
        except Exception:
            srv.close()
            raise
        self._srv = srv

        def loop():
            while not self._stop.is_set():
                try:
                    conn, _addr = srv.accept()
                except (TimeoutError, OSError):
                    continue
                try:
                    data = _read_limited(conn)
                finally:
                    conn.close()
                paths = [line for line in data.decode('utf-8', errors='replace').splitlines() if line.strip()]
                if not paths:
                    continue
                try:
                    on_files(paths)
                except Exception:
                    _STATUS.exception('handoff callback failed')

        self._thread = threading.Thread(target=loop, name='capswriter-client-handoff', daemon=True)
        self._thread.start()

    def release(self):
        self._stop.set()
        srv = self._srv
        self._srv = None
        if srv is not None:
            try:
                srv.close()
            except OSError:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.join(timeout=1.5)
        try:
            client_sock_path(self.base_dir).unlink()
        except OSError:
            pass
        fd = self._fd
        self._fd = None
        if fd is not None:
            _unlock(fd)


def logs_dir(base_dir):
    path = Path(base_dir) / 'logs'
    path.mkdir(parents=True, exist_ok=True)
    return path


def server_lock_path(base_dir):
    return logs_dir(base_dir) / 'server.lock'


def client_lock_path(base_dir):
    return logs_dir(base_dir) / 'client.lock'


def client_sock_path(base_dir):
    return logs_dir(base_dir) / 'client.sock'


def notify(message):
    text = ' '.join(str(message or '').split())
    if not text:
        return
    if len(text) > 180:
        text = text[:177] + '...'
    print(text, flush=True)
    try:
        from core.logger import Logger
        for name in ('server', 'client'):
            logger = Logger._loggers.get(name)
            if logger is not None:
                logger.info(text)
    except Exception:
        _STATUS.info(text)
    if sys.platform != 'darwin':
        return
    script = 'display notification "%s" with title "CapsWriter"' % (
        text.replace('\\', '\\\\').replace('"', '\\"')
    )
    try:
        subprocess.run(
            ['osascript', '-e', script],
            check=False,
            timeout=3,
            capture_output=True,
        )
    except Exception:
        _STATUS.info('notification failed')


def port_open(host, port, timeout=0.3):
    import socket
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def server_state(base_dir, port, probe=None, command_lookup=None):
    """ready / starting / foreign / down。端口探测固定走 127.0.0.1。"""
    held = server_is_ours(base_dir, command_lookup=command_lookup)
    probe_fn = port_open if probe is None else probe
    up = bool(probe_fn('127.0.0.1', int(port)))
    if held and up:
        return 'ready'
    if held and not up:
        return 'starting'
    if up and not held:
        return 'foreign'
    return 'down'


def server_is_ours(base_dir, command_lookup=None):
    pid = _pid_from_record(read_record(server_lock_path(base_dir)), SERVER_MARK)
    if pid <= 1:
        return False
    return _command_matches(_lookup_command(pid, command_lookup))


def admit_server(base_dir, port, probe=None, notify_fn=None):
    """拿到锁才允许加载模型。锁被占用时以 0 退出；端口被别人占用时以 1 退出。"""
    fd = _try_lock(server_lock_path(base_dir))
    if fd is None:
        _emit(notify_fn, '服务端已在运行')
        return Admission('exit', 0, '服务端已在运行')
    probe_fn = port_open if probe is None else probe
    if probe_fn('127.0.0.1', int(port)):
        _unlock(fd)
        _emit(notify_fn, '端口已被其它程序占用')
        return Admission('exit', 1, '端口已被其它程序占用')
    _write_record(fd, SERVER_MARK, os.getpid(), port)
    return Admission('serve', 0, '', ServerHold(fd))


def enter_client(
    base_dir,
    files,
    collect_root,
    port,
    probe=None,
    spawn=None,
    notify_fn=None,
    command_lookup=None,
    sleep=None,
    wait_timeout=180,
    wait_interval=0.5,
    handoff_timeout=3.0,
    on_files=None,
):
    fd = _try_lock(client_lock_path(base_dir))
    if fd is None:
        if _clean_paths(files):
            if send_files(base_dir, files, timeout=handoff_timeout):
                return Gate('exit', 0, '')
            _emit(notify_fn, '没有交到正在运行的客户端')
            return Gate('exit', 1, '没有交到正在运行的客户端')
        _emit(notify_fn, '已在菜单栏')
        return Gate('exit', 0, '已在菜单栏')

    _write_record(fd, CLIENT_MARK, os.getpid(), port)
    session = DarwinSession(base_dir, fd)
    if on_files is not None:
        try:
            session.serve(on_files)
        except Exception:
            session.release()
            raise
    state = _wait_server(
        base_dir,
        port,
        probe,
        command_lookup,
        sleep,
        wait_timeout,
        wait_interval,
    )
    if state == 'down':
        kind = launch_server(collect_root, base_dir, spawn=spawn, notify_fn=notify_fn)
        if kind == 'missing':
            session.release()
            return Gate('exit', 1, '没有找到服务端')
        state = _wait_until_usable(
            base_dir,
            port,
            probe,
            command_lookup,
            sleep,
            wait_timeout,
            wait_interval,
        )
    if state == 'foreign':
        session.release()
        _emit(notify_fn, '端口已被其它程序占用')
        return Gate('exit', 1, '端口已被其它程序占用', None)
    if state != 'ready':
        _emit(notify_fn, '服务端仍在加载')
    return Gate('run', 0, '', session)


def launch_server(collect_root, base_dir, spawn=None, notify_fn=None):
    """旁边有 app 就用 open，不要 open -n。否则拉起二进制或 start_server.py。"""
    root = Path(collect_root)
    app = root / SERVER_APP_NAME
    binary = root / 'start_server'
    script = Path(base_dir) / 'start_server.py'
    spawn_fn = _default_spawn if spawn is None else spawn
    if app.is_dir():
        spawn_fn(['open', str(app)], new_session=False)
        return 'app'
    if binary.is_file() and os.access(binary, os.X_OK):
        spawn_fn([str(binary)], new_session=True)
        return 'binary'
    if script.is_file():
        spawn_fn([sys.executable, str(script)], new_session=True)
        return 'script'
    _emit(notify_fn, '没有找到服务端')
    return 'missing'


def send_files(base_dir, files, timeout=3.0):
    import socket
    payload = ''.join(path + '\n' for path in _clean_paths(files)).encode('utf-8')
    if not payload:
        return False
    if len(payload) > 1_000_000:
        payload = payload[:1_000_000]
    sock_path = str(client_sock_path(base_dir))
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(timeout)
                conn.connect(sock_path)
                conn.sendall(payload)
                return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


def stop_recorded_server(base_dir, command_lookup=None, kill=None):
    """只向锁文件里的 pid 发 SIGTERM。pid <= 1，或命令行对不上，都不杀。"""
    pid = _pid_from_record(read_record(server_lock_path(base_dir)), SERVER_MARK)
    if pid <= 1:
        return False
    if not _command_matches(_lookup_command(pid, command_lookup)):
        return False
    killer = os.kill if kill is None else kill
    killer(pid, _sigterm())
    return True


def on_port_conflict(prompt, platform_name=None, notify_fn=None):
    name = sys.platform if platform_name is None else platform_name
    if name == 'darwin':
        _emit(notify_fn, '端口已被其它程序占用')
        raise SystemExit(1)
    prompt()


def collect_root(base_dir, argv0=None, frozen=None, executable=None):
    """启动脚本 exec 之后，sys.argv[0] 不再位于 .app 里。app 要到二进制旁边找。"""
    is_frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    exe = Path(sys.executable if executable is None else executable)
    if is_frozen:
        return exe.resolve().parent
    raw = Path(sys.argv[0] if argv0 is None else argv0)
    if raw.name in ('start_client', 'start_server'):
        try:
            if raw.is_file():
                return raw.resolve().parent
        except OSError:
            pass
    return Path(base_dir)


def read_record(path):
    try:
        text = Path(path).read_text(encoding='utf-8')
    except OSError:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    record = {'mark': lines[0]}
    for line in lines[1:]:
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        record[key.strip()] = value.strip()
    return record


def _wait_server(base_dir, port, probe, command_lookup, sleep, wait_timeout, wait_interval):
    state = server_state(base_dir, port, probe=probe, command_lookup=command_lookup)
    if state != 'starting':
        return state
    sleeper = time.sleep if sleep is None else sleep
    deadline = time.monotonic() + wait_timeout
    while state == 'starting' and time.monotonic() < deadline:
        sleeper(wait_interval)
        state = server_state(base_dir, port, probe=probe, command_lookup=command_lookup)
    return state


def _wait_until_usable(base_dir, port, probe, command_lookup, sleep, wait_timeout, wait_interval):
    """刚拉起时锁和端口都还没有。down 和 starting 都继续等，直到监听或超时。"""
    sleeper = time.sleep if sleep is None else sleep
    deadline = time.monotonic() + wait_timeout
    state = server_state(base_dir, port, probe=probe, command_lookup=command_lookup)
    while state in ('down', 'starting') and time.monotonic() < deadline:
        sleeper(wait_interval)
        state = server_state(base_dir, port, probe=probe, command_lookup=command_lookup)
    return state


def _emit(notify_fn, message):
    if notify_fn is None:
        notify(message)
        return
    notify_fn(message)


def _clean_paths(files):
    cleaned = []
    for item in files or []:
        text = str(item)
        if not text or '\n' in text or '\r' in text:
            continue
        cleaned.append(str(Path(text)))
    return cleaned


def _read_limited(conn, limit=1_000_000):
    chunks = []
    size = 0
    while size < limit:
        block = conn.recv(65536)
        if not block:
            break
        chunks.append(block)
        size += len(block)
    return b''.join(chunks)


def _pid_from_record(record, mark):
    if not record or record.get('mark') != mark:
        return 0
    try:
        pid = int(record.get('pid', '0'))
    except (TypeError, ValueError):
        return 0
    if pid <= 1:
        return 0
    return pid


def _command_matches(command):
    text = command or ''
    return 'start_server' in text or 'CapsWriter Server' in text


def _lookup_command(pid, command_lookup):
    if command_lookup is not None:
        return command_lookup(pid) or ''
    return _command_line(pid)


def _command_line(pid):
    if pid <= 1:
        return ''
    try:
        out = subprocess.check_output(
            ['ps', '-p', str(int(pid)), '-o', 'command='],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
    except Exception:
        return ''
    return out.strip()


def _sigterm():
    import signal
    return signal.SIGTERM


def _default_spawn(argv, new_session=False):
    subprocess.Popen(
        list(argv),
        start_new_session=bool(new_session),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _try_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_CLOEXEC', 0)
    fd = os.open(str(path), flags, 0o644)
    try:
        _fcntl().flock(fd, _fcntl().LOCK_EX | _fcntl().LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
            return None
        raise
    return fd


def _unlock(fd):
    try:
        _fcntl().flock(fd, _fcntl().LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def _write_record(fd, mark, pid, port):
    payload = ('%s\npid=%s\nport=%s\n' % (mark, int(pid), int(port))).encode('ascii')
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, payload)


def _fcntl():
    import fcntl
    return fcntl
