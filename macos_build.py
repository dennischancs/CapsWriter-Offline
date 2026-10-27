# coding: utf-8
"""Apple Silicon 的本地编译和清理。

build 只调用 build.spec 或 build-client.spec。
clean 只删除仓库里的 build 和 dist。models、日志和仓库外的路径不动。
dist 里的 start_server / start_client 还被进程占用时，两件事都不做。
解释器会跳过没有 PyInstaller 的 python3。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


FULL_SPEC = 'build.spec'
CLIENT_SPEC = 'build-client.spec'
FULL_DIR = 'CapsWriter-Offline'
CLIENT_DIR = 'CapsWriter-Offline-Client'
APP_NAMES = ('CapsWriter.app', 'CapsWriter Server.app')
WATCHED = (
    (FULL_DIR, 'start_server'),
    (FULL_DIR, 'start_client'),
    (CLIENT_DIR, 'start_client'),
)


class BuildError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def is_apple_silicon(system_name=None, machine=None):
    import platform
    system_name = platform.system() if system_name is None else system_name
    machine = platform.machine() if machine is None else machine
    return system_name == 'Darwin' and machine == 'arm64'


FALLBACK_TOOL_DIRS = (
    '/tmp/capswriter-macos-test/bin',
    '/private/tmp/capswriter-macos-test/bin',
)
VERSIONED_PYTHONS = ('python3.14', 'python3.13', 'python3.12', 'python3')
HOMEBREW_PYTHON314 = '/opt/homebrew/bin/python3.14'


def resolve_python(candidate, which=None):
    if not candidate:
        return None
    locate = shutil.which if which is None else which
    path = Path(candidate)
    try:
        is_file = path.is_file()
    except OSError:
        is_file = False
    if is_file and os.access(path, os.X_OK):
        return str(path)
    return locate(candidate)


def _add_python(found, candidate, which=None):
    resolved = resolve_python(candidate, which=which)
    if resolved and resolved not in found:
        found.append(resolved)


def pyinstaller_bindirs(which, tool_dirs):
    dirs = []
    seen = set()

    def add(raw):
        if not raw:
            return
        path = Path(raw)
        if not path.is_dir():
            return
        try:
            key = str(path.resolve())
        except OSError:
            key = str(path)
        if key in seen:
            return
        seen.add(key)
        dirs.append(str(path))

    located = which('pyinstaller')
    if located:
        add(Path(located).parent)
    for raw in tool_dirs:
        add(raw)
    return dirs


def python_candidates(root, env_python=None, which=None, tool_dirs=None):
    locate = shutil.which if which is None else which
    if tool_dirs is None:
        tool_dirs = FALLBACK_TOOL_DIRS
    found = []
    _add_python(found, env_python, locate)
    root = Path(root)
    _add_python(found, str(root / '.venv' / 'bin' / 'python'), locate)
    _add_python(found, str(root / '.venv' / 'bin' / 'python3'), locate)
    for directory in pyinstaller_bindirs(locate, tool_dirs):
        _add_python(found, str(Path(directory) / 'python'), locate)
        _add_python(found, str(Path(directory) / 'python3'), locate)
    for name in VERSIONED_PYTHONS:
        _add_python(found, name, locate)
    _add_python(found, HOMEBREW_PYTHON314, locate)
    return found


def probe_pyinstaller(python):
    try:
        proc = subprocess.run(
            [python, '-c', 'import PyInstaller'],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, 'ok'
    detail = (proc.stderr or proc.stdout or 'import failed').strip().splitlines()
    return False, detail[-1] if detail else 'import failed'


def format_missing_python(tried):
    lines = [
        '没有找到带 PyInstaller 的 Python。',
        '系统自带的 python3 不够，需要带 PyInstaller 的 Python 3.14。',
    ]
    if tried:
        lines.extend('%s: %s' % (path, detail) for path, detail in tried)
    else:
        lines.append('没有可执行的 Python。')
    return '\n'.join(lines)


def first_working_python(candidates, probe):
    tried = []
    for candidate in candidates:
        ok, detail = probe(candidate)
        tried.append((candidate, detail))
        if ok:
            return candidate, tried
    return None, tried


def pyinstaller_command(python, spec):
    return [python, '-m', 'PyInstaller', '--noconfirm', '--clean', spec]


def artifact_dirs(root):
    root = Path(root)
    return [root / 'build', root / 'dist']


def _inside(path, root):
    path = Path(path).resolve()
    root = Path(root).resolve()
    return path == root or root in path.parents


def remove_artifact(path, root):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_symlink():
        path.unlink()
        return True
    if Path(path).resolve() == Path(root).resolve() or not _inside(path, root):
        raise BuildError('拒绝删除仓库外面的路径: %s' % path)
    shutil.rmtree(path)
    return True


def watched_binaries(root):
    root = Path(root)
    return [root / 'dist' / folder / name for folder, name in WATCHED]


def busy_entries(root, lsof_fn):
    entries = []
    for path in watched_binaries(root):
        if not path.is_file():
            continue
        found = lsof_fn(path) or []
        pids = []
        for item in found:
            text = str(item).strip()
            if text.isdigit():
                pids.append(int(text))
        if pids:
            entries.append((path, pids))
    return entries


def default_lsof(path):
    try:
        proc = subprocess.run(
            ['lsof', '-t', '--', str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _ps_pids(path)
    if proc.returncode not in (0, 1):
        return _ps_pids(path)
    return [int(item) for item in proc.stdout.split() if item.isdigit()]


def _ps_pids(path):
    try:
        proc = subprocess.run(
            ['ps', '-ax', '-o', 'pid=,command='],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    needle = str(Path(path).resolve())
    pids = []
    for line in proc.stdout.splitlines():
        text = line.strip()
        if needle not in text:
            continue
        head = text.split(None, 1)[0]
        if head.isdigit():
            pids.append(int(head))
    return pids


def format_busy(entries):
    lines = ['dist 里的程序还在运行，没有删除，也没有开始编译：']
    for path, pids in entries:
        lines.append('%s  pid=%s' % (path, ','.join(str(pid) for pid in pids)))
    lines.append('先退出这些进程，再运行 clean-macos.sh 或 build-macos.sh。')
    return '\n'.join(lines)


def clean_repo(root, lsof_fn=None, remove_fn=None):
    root = Path(root)
    lsof_fn = default_lsof if lsof_fn is None else lsof_fn
    remove_fn = remove_artifact if remove_fn is None else remove_fn
    busy = busy_entries(root, lsof_fn)
    if busy:
        raise BuildError(format_busy(busy))
    removed = []
    for path in artifact_dirs(root):
        if remove_fn(path, root):
            removed.append(path)
    return removed


def file_kind(path):
    try:
        proc = subprocess.run(
            ['file', '-b', '--', str(path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ''
    if proc.returncode != 0:
        return ''
    return proc.stdout.strip()


def check_collect(dest, names, kind_of, require_mlx):
    dest = Path(dest)
    errors = []
    for name in names:
        path = dest / name
        if not path.is_file() or not os.access(path, os.X_OK):
            errors.append('缺少可执行文件 %s' % path)
            continue
        kind = kind_of(path)
        if 'Mach-O' not in kind or 'arm64' not in kind:
            errors.append('%s 不是 arm64 Mach-O：%s' % (path, kind or '未知'))
    for name in APP_NAMES:
        if (dest / name).exists():
            errors.append('不应存在 %s' % (dest / name))
    if require_mlx:
        jaccl = dest / 'internal' / 'libjaccl.dylib'
        metallib = dest / 'internal' / 'mlx' / 'lib' / 'mlx.metallib'
        if not jaccl.is_file():
            errors.append('缺少 %s' % jaccl)
        if not metallib.is_file():
            errors.append('缺少 %s' % metallib)
    return errors


def build_repo(root, client_only=False, python=None, runner=None, kind_of=None, lsof_fn=None, probe=None, candidates=None):
    root = Path(root)
    lsof_fn = default_lsof if lsof_fn is None else lsof_fn
    busy = busy_entries(root, lsof_fn)
    if busy:
        raise BuildError(format_busy(busy))
    if python is None:
        probe_fn = probe_pyinstaller if probe is None else probe
        pool = candidates if candidates is not None else python_candidates(
            root, os.environ.get('CAPSWRITER_PYTHON')
        )
        chosen, tried = first_working_python(pool, probe_fn)
        if chosen is None:
            raise BuildError(format_missing_python(tried))
        python = chosen
    spec = CLIENT_SPEC if client_only else FULL_SPEC
    command = pyinstaller_command(python, spec)
    run = subprocess.run if runner is None else runner
    proc = run(command, cwd=str(root))
    code = proc.returncode if hasattr(proc, 'returncode') else int(proc)
    if code != 0:
        raise BuildError('PyInstaller 失败，退出码 %s' % code, code if code else 1)
    dest_name = CLIENT_DIR if client_only else FULL_DIR
    names = ('start_client',) if client_only else ('start_server', 'start_client')
    kind_of = file_kind if kind_of is None else kind_of
    errors = check_collect(root / 'dist' / dest_name, names, kind_of, require_mlx=not client_only)
    if errors:
        raise BuildError('\n'.join(errors))
    return [root / 'dist' / dest_name / name for name in names]


def dispatch(argv, root, system_name=None, machine=None, **kwargs):
    argv = list(argv)
    extra = argv[2:] if len(argv) > 2 else []
    if len(argv) < 2 or argv[1] not in ('build', 'clean') or extra not in ([], ['client']) or (argv[1] == 'clean' and extra):
        print('用法: build-macos.sh [client]  或  clean-macos.sh', file=sys.stderr)
        return 2
    if not is_apple_silicon(system_name, machine):
        print('只支持 Apple Silicon（M 系列）。', file=sys.stderr)
        return 2
    try:
        if argv[1] == 'clean':
            removed = clean_repo(root, lsof_fn=kwargs.get('lsof_fn'), remove_fn=kwargs.get('remove_fn'))
            if removed:
                print('已删除：')
                for path in removed:
                    print(path)
            else:
                print('没有 build 或 dist。')
            return 0
        made = build_repo(root, client_only=extra == ['client'], **{
            key: kwargs[key]
            for key in ('python', 'runner', 'kind_of', 'lsof_fn', 'probe')
            if key in kwargs
        })
    except BuildError as exc:
        print(exc, file=sys.stderr)
        return exc.code or 1
    print('已编译：')
    for path in made:
        print(path)
    return 0


def main(argv=None):
    return dispatch(sys.argv if argv is None else argv, Path(__file__).resolve().parent)


if __name__ == '__main__':
    sys.exit(main())
