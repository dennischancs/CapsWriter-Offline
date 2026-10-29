# coding: utf-8
"""Apple Silicon 的本地编译和清理。

build 一次打出 dist/CapsWriter.app 和 dist/CapsWriter-<version>.dmg。
app 里是 Swift 界面、服务端和复制进来的模型。
dmg 里是这个 app，以及指向 /Applications 的 Applications 链接。
client 只打客户端收集目录，不打 app，也不打 dmg。
成功之后删掉 PyInstaller 的 build、Swift 的 .build，以及 /tmp/cw-swift。
clean 连同 dist 一起删。仓库里的 models 不动。
dist 里的程序还在跑时，两件事都不做。
解释器会跳过没有 PyInstaller 的 python3。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from build_support import linked_runtime_errors


FULL_SPEC = 'build.spec'
CLIENT_SPEC = 'build-client.spec'
FULL_DIR = 'CapsWriter-Offline'
CLIENT_DIR = 'CapsWriter-Offline-Client'
APP_NAMES = ('CapsWriter.app', 'CapsWriter Server.app')
FULL_BINARIES = ('start_server', 'start_client', 'batch_transcribe')
WATCHED = tuple((FULL_DIR, name) for name in FULL_BINARIES) + (
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
MINIFORGE_CAPSWRITER_PYTHON = (
    '/opt/homebrew/Caskroom/miniforge/base/envs/capswriter/bin/python3'
)


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
    _add_python(found, MINIFORGE_CAPSWRITER_PYTHON, locate)
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
        '系统自带的 python3 不够。本机用 miniforge 的 capswriter 环境，'
        '需要这个环境里能 import PyInstaller。',
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


SWIFT_SCRATCH = Path('/tmp/cw-swift')


def process_junk_dirs(root, scratch=None):
    """PyInstaller 工作目录、包内 .build，以及本机 Swift 临时目录。"""
    root = Path(root)
    scratch = SWIFT_SCRATCH if scratch is None else Path(scratch)
    return [
        root / 'build',
        root / 'macos' / 'CapsWriterShell' / '.build',
        scratch,
    ]


def clean_dirs(root, scratch=None):
    return [Path(root) / 'dist'] + process_junk_dirs(root, scratch)


def artifact_dirs(root):
    return clean_dirs(root)


def _inside(path, root):
    path = Path(path).resolve()
    root = Path(root).resolve()
    return path == root or root in path.parents


def _scratch_allowed(scratch, root):
    """只允许删 /tmp/cw-swift，或测试仓库里同名的那一个。"""
    scratch = Path(scratch)
    root = Path(root).resolve()
    if scratch.name != 'cw-swift' or scratch.is_symlink():
        return False
    try:
        resolved = scratch.resolve() if scratch.exists() else scratch
    except OSError:
        return False
    banned = {
        Path('/'), Path('/tmp'), Path('/private'), Path('/private/tmp'),
        Path('/Volumes'), Path('/Users'), Path('/System'),
    }
    if resolved in banned or resolved == root:
        return False
    for name in ('models', 'logs'):
        folder = root / name
        if resolved == folder or folder in resolved.parents:
            return False
    if root in resolved.parents:
        return True
    return scratch.parent.as_posix() in ('/tmp', '/private/tmp')


def _link_lives_in_repo(path, root):
    parent = Path(path).parent.resolve()
    root = Path(root).resolve()
    return parent == root or root in parent.parents


def remove_artifact(path, root, scratch=None):
    path = Path(path)
    root = Path(root)
    scratch = SWIFT_SCRATCH if scratch is None else Path(scratch)
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_symlink():
        if not (_link_lives_in_repo(path, root) or path == scratch):
            raise BuildError('拒绝删除仓库外面的路径: %s' % path)
        path.unlink()
        return True
    inside = _inside(path, root) and Path(path).resolve() != Path(root).resolve()
    if inside:
        resolved = Path(path).resolve()
        root_resolved = Path(root).resolve()
        for name in ('models', 'logs'):
            folder = root_resolved / name
            if resolved == folder or folder in resolved.parents:
                raise BuildError('拒绝删除仓库外面的路径: %s' % path)
        shutil.rmtree(path)
        return True
    if path == scratch and _scratch_allowed(scratch, root):
        shutil.rmtree(path)
        return True
    raise BuildError('拒绝删除仓库外面的路径: %s' % path)


def watched_binaries(root):
    root = Path(root)
    paths = [root / 'dist' / folder / name for folder, name in WATCHED]
    app = root / 'dist' / 'CapsWriter.app'
    paths.extend([
        app / 'Contents' / 'MacOS' / 'CapsWriter',
        app / 'Contents' / 'Resources' / 'runtime' / 'start_server',
        app / 'Contents' / 'Resources' / 'runtime' / 'start_client',
        app / 'Contents' / 'Resources' / 'runtime' / 'batch_transcribe',
    ])
    return paths


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


def _remover(remove_fn, scratch):
    if remove_fn is not None:
        return remove_fn

    def remove(path, root):
        return remove_artifact(path, root, scratch=scratch)

    return remove


def clean_repo(root, lsof_fn=None, remove_fn=None, scratch=None):
    root = Path(root)
    scratch = SWIFT_SCRATCH if scratch is None else Path(scratch)
    lsof_fn = default_lsof if lsof_fn is None else lsof_fn
    remove = _remover(remove_fn, scratch)
    busy = busy_entries(root, lsof_fn)
    if busy:
        raise BuildError(format_busy(busy))
    removed = []
    for path in clean_dirs(root, scratch):
        if remove(path, root):
            removed.append(path)
    return removed


def drop_process_junk(root, scratch=None, remove_fn=None):
    """编译已经成功时，删掉中间文件。dist 里的 app 留下。"""
    root = Path(root)
    scratch = SWIFT_SCRATCH if scratch is None else Path(scratch)
    remove = _remover(remove_fn, scratch)
    removed = []
    for path in process_junk_dirs(root, scratch):
        if remove(path, root):
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


DMG_VOLUME = 'CapsWriter'
DMG_FORMAT = 'UDZO'


def dmg_name(version):
    return 'CapsWriter-%s.dmg' % version


def dmg_layout(app, version):
    """镜像里放 app，以及名为 Applications、指向 /Applications 的链接。"""
    app = Path(app)
    image = app.parent / dmg_name(version)
    stage = app.parent / ('.dmg-stage-%s' % version)
    return {
        'image': image,
        'stage': stage,
        'app': stage / app.name,
        'applications': stage / 'Applications',
        'volume': DMG_VOLUME,
        'format': DMG_FORMAT,
    }


def stage_dmg(app, version):
    """准备拖进「应用程序」的目录。app 用 APFS 克隆，失败再复制。"""
    app = Path(app)
    if not app.is_dir():
        raise BuildError('没有 app %s' % app)
    layout = dmg_layout(app, version)
    stage = layout['stage']
    if stage.is_symlink():
        stage.unlink()
    elif stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    cloned = subprocess.run(
        ['cp', '-cR', str(app), str(layout['app'])],
        capture_output=True,
        text=True,
    )
    if cloned.returncode != 0:
        shutil.copytree(app, layout['app'], symlinks=True)
    layout['applications'].symlink_to('/Applications')
    return layout


def hdiutil_command(layout):
    return [
        'hdiutil', 'create',
        '-volname', layout['volume'],
        '-srcfolder', str(layout['stage']),
        '-ov',
        '-format', layout['format'],
        str(layout['image']),
    ]


def create_dmg(app, version, runner=None):
    """打出未签名的 dmg。镜像里是 app 和 Applications 链接，不是符号链接回仓库。"""
    layout = stage_dmg(app, version)
    command = hdiutil_command(layout)
    run = subprocess.run if runner is None else runner
    try:
        proc = run(command)
        code = proc.returncode if hasattr(proc, 'returncode') else int(proc)
        if code != 0:
            raise BuildError('hdiutil 失败，退出码 %s' % code, code or 1)
        image = layout['image']
        if runner is None and not image.is_file():
            raise BuildError('没有打出 %s' % image)
    finally:
        stage = layout['stage']
        if stage.is_symlink():
            stage.unlink()
        elif stage.exists():
            shutil.rmtree(stage)
    return layout['image']


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


def read_project_version(path):
    text = Path(path).read_text(encoding='utf-8')
    match = re.search(r'^version = "([^"]+)"', text, re.M)
    if not match:
        raise BuildError('pyproject.toml 里没有 version')
    return match.group(1)


def compile_shell(root, runner=None, scratch=None):
    """编 Swift 界面。临时文件放在本机 /tmp，不堆在外置盘的 .build 里。"""
    root = Path(root)
    scratch = SWIFT_SCRATCH if scratch is None else Path(scratch)
    package = root / 'macos' / 'CapsWriterShell'
    command = [
        'swift', 'build', '-c', 'release',
        '--package-path', str(package),
        '--scratch-path', str(scratch),
    ]
    run = subprocess.run if runner is None else runner
    proc = run(command, cwd=str(root))
    code = proc.returncode if hasattr(proc, 'returncode') else int(proc)
    if code != 0:
        raise BuildError('Swift 界面编译失败，退出码 %s' % code, code or 1)
    if runner is not None:
        return None
    shown = subprocess.run(
        command + ['--show-bin-path'],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if shown.returncode != 0:
        detail = (shown.stderr or shown.stdout or '').strip()
        raise BuildError('找不到 Swift 界面的输出目录%s' % ((': ' + detail) if detail else ''))
    binary = Path(shown.stdout.strip()) / 'CapsWriter'
    if not binary.is_file():
        raise BuildError('没有打出 Swift 界面 %s' % binary)
    return binary


def assemble_macos_app(root, collect, shell_binary, version=None):
    """把收集目录移进 CapsWriter.app。模型已经在收集目录里，不再复制第二份。"""
    root = Path(root)
    collect = Path(collect)
    shell_binary = Path(shell_binary)
    if not shell_binary.is_file():
        raise BuildError('没有 Swift 界面 %s' % shell_binary)
    if not collect.is_dir():
        raise BuildError('没有收集目录 %s' % collect)
    app = root / 'dist' / 'CapsWriter.app'
    if app.is_symlink():
        app.unlink()
    elif app.exists():
        shutil.rmtree(app)
    macos_dir = app / 'Contents' / 'MacOS'
    resources = app / 'Contents' / 'Resources'
    macos_dir.mkdir(parents=True)
    resources.mkdir(parents=True)
    dest_bin = macos_dir / 'CapsWriter'
    shutil.copy2(shell_binary, dest_bin)
    dest_bin.chmod(0o755)
    icon_src = root / 'macos' / 'AppIcon.icns'
    if not icon_src.is_file():
        raise BuildError('缺少图标 %s' % icon_src)
    shutil.copy2(icon_src, resources / 'AppIcon.icns')
    template = root / 'macos' / 'Info.plist.in'
    if not template.is_file():
        raise BuildError('缺少 %s' % template)
    if version is None:
        version = read_project_version(root / 'pyproject.toml')
    plist = template.read_text(encoding='utf-8').replace('__VERSION__', version)
    (app / 'Contents' / 'Info.plist').write_text(plist, encoding='utf-8')
    runtime = resources / 'runtime'
    shutil.move(str(collect), str(runtime))
    return app


def build_repo(root, client_only=False, python=None, runner=None, kind_of=None, lsof_fn=None, probe=None, candidates=None, package_app=True, shell_binary=None, swift_runner=None, scratch=None, dmg_runner=None):
    root = Path(root)
    scratch = SWIFT_SCRATCH if scratch is None else Path(scratch)
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
    names = ('start_client',) if client_only else FULL_BINARIES
    kind_of = file_kind if kind_of is None else kind_of
    collect = root / 'dist' / dest_name
    errors = check_collect(collect, names, kind_of, require_mlx=not client_only)
    errors.extend(linked_runtime_errors(collect))
    if errors:
        raise BuildError('\n'.join(errors))
    if client_only or not package_app:
        drop_process_junk(root, scratch=scratch)
        return [collect / name for name in names]
    binary = Path(shell_binary) if shell_binary else compile_shell(root, runner=swift_runner, scratch=scratch)
    if binary is None:
        raise BuildError('没有打出 Swift 界面')
    version = read_project_version(root / 'pyproject.toml')
    app = assemble_macos_app(root, collect, binary, version=version)
    runtime = app / 'Contents' / 'Resources' / 'runtime'
    packed = check_collect(runtime, names, kind_of, require_mlx=not client_only)
    packed.extend(linked_runtime_errors(runtime))
    shell_path = app / 'Contents' / 'MacOS' / 'CapsWriter'
    if not shell_path.is_file() or not os.access(shell_path, os.X_OK):
        packed.append('缺少 Swift 界面 %s' % shell_path)
    else:
        kind = kind_of(shell_path)
        if 'Mach-O' not in kind or 'arm64' not in kind:
            packed.append('%s 不是 arm64 Mach-O：%s' % (shell_path, kind or '未知'))
    plist = (app / 'Contents' / 'Info.plist').read_text(encoding='utf-8')
    if version not in plist:
        packed.append('Info.plist 没有版本 %s' % version)
    if not (app / 'Contents' / 'Resources' / 'AppIcon.icns').is_file():
        packed.append('包里没有图标')
    if packed:
        raise BuildError('\n'.join(packed))
    image = create_dmg(app, version, runner=dmg_runner)
    drop_process_junk(root, scratch=scratch)
    return [app, image]


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
            removed = clean_repo(
                root,
                lsof_fn=kwargs.get('lsof_fn'),
                remove_fn=kwargs.get('remove_fn'),
                scratch=kwargs.get('scratch'),
            )
            if removed:
                print('已删除：')
                for path in removed:
                    print(path)
            else:
                print('没有需要清理的编译文件。')
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
