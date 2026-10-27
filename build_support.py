# coding: utf-8
"""PyInstaller spec 的平台分支。Windows 的图标、UPX 和目录联接保持原样。"""
from os import chmod, makedirs, remove, symlink, walk
from os.path import abspath, basename, dirname, exists, islink, join, relpath
from platform import system
from shutil import copyfile, rmtree


DARWIN_RUNTIME_FOLDERS = (
    'models',
    'assets',
    'core',
    'LLM',
    'docs',
    'logs',
    'log',
)


def is_darwin(platform_name=None):
    name = system() if platform_name is None else platform_name
    return name == 'Darwin'


def use_upx(platform_name=None):
    return not is_darwin(platform_name)


def exe_icon(platform_name=None):
    if is_darwin(platform_name):
        return None
    return ['assets\\\\icon.ico']


def hiddenimports_for(names, platform_name=None):
    items = list(names)
    if not is_darwin(platform_name):
        return items
    items = [name for name in items if name != 'keyboard']
    for extra in ('mlx', 'mlx.core', 'mlx_audio', 'mlx_audio.stt'):
        if extra not in items:
            items.append(extra)
    return items


def exclude_accel_binary(name, src, platform_name=None):
    """Darwin 上按文件名丢掉 CUDA / DirectML。Windows 仍由 spec 里的原判断处理。"""
    if not is_darwin(platform_name):
        return False
    name_lower = (name or '').lower()
    src_lower = src.lower() if isinstance(src, str) else ''
    tokens = ('providers_cuda', 'directml', 'cudnn', 'nvcuda')
    return any(token in name_lower or token in src_lower for token in tokens)


def skip_collected_data(src, platform_name=None):
    base = basename(src).lower()
    if 'providers_cuda' in base:
        return True
    if is_darwin(platform_name) and any(token in base for token in ('directml', 'cudnn')):
        return True
    return False


def link_runtime_folders(dest_root, folders=None, platform_name=None):
    """Darwin 上把已有运行目录链到绝对路径。缺的跳过，不改 Windows 的 mklink。"""
    if not is_darwin(platform_name):
        return []
    linked = []
    for folder in folders or DARWIN_RUNTIME_FOLDERS:
        if not exists(folder):
            continue
        dest_folder = join(dest_root, folder)
        if islink(dest_folder):
            remove(dest_folder)
        elif exists(dest_folder):
            rmtree(dest_folder)
        symlink(abspath(folder), dest_folder)
        linked.append(dest_folder)
    return linked


def _package_root(name):
    try:
        import importlib.util
        spec = importlib.util.find_spec(name)
    except Exception:
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    return spec.submodule_search_locations[0]


def _sync_tree(src_root, dest_root, copied):
    skip_dirs = {'__pycache__', 'include', 'share', 'cmake'}
    for dirpath, dirnames, filenames in walk(src_root):
        dirnames[:] = [name for name in dirnames if name not in skip_dirs]
        for filename in filenames:
            if filename.endswith('.pyc'):
                continue
            src = join(dirpath, filename)
            dest = join(dest_root, relpath(src, src_root))
            makedirs(dirname(dest), exist_ok=True)
            copyfile(src, dest)
            copied.append(dest)


def ensure_darwin_mlx_runtime(dest_root, platform_name=None):
    """补上 PyInstaller 漏掉的 MLX 模块，并把 libjaccl 放到改写后的 rpath 上。"""
    if not is_darwin(platform_name):
        return []
    internal = join(dest_root, 'internal')
    if not exists(internal):
        return []
    copied = []
    mlx_root = _package_root('mlx')
    if mlx_root:
        _sync_tree(mlx_root, join(internal, 'mlx'), copied)
        jaccl = join(mlx_root, 'lib', 'libjaccl.dylib')
        if exists(jaccl):
            for dest in (
                join(internal, 'libjaccl.dylib'),
                join(internal, 'mlx', 'libjaccl.dylib'),
            ):
                makedirs(dirname(dest), exist_ok=True)
                copyfile(jaccl, dest)
                copied.append(dest)
    audio_root = _package_root('mlx_audio')
    if audio_root:
        _sync_tree(audio_root, join(internal, 'mlx_audio'), copied)
    return copied


def _project_version():
    import tomllib
    with open(join(dirname(abspath(__file__)), 'pyproject.toml'), 'rb') as handle:
        return tomllib.load(handle)['project']['version']


def _launcher_script(target):
    return (
        '#!/bin/bash\n'
        'ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"\n'
        'exec "$ROOT/%s" "$@"\n' % target
    )


def write_darwin_apps(dest_root, platform_name=None, version=None):
    """在收集目录旁边放两个未签名的薄启动器。二进制和 internal 留在原地。"""
    if not is_darwin(platform_name):
        return []
    if version is None:
        version = _project_version()
    specs = (
        {
            'folder': 'CapsWriter.app',
            'executable': 'CapsWriter',
            'bundle_id': 'offline.capswriter.client',
            'name': 'CapsWriter',
            'target': 'start_client',
            'microphone': 'CapsWriter 需要麦克风来把语音转成文字。',
        },
        {
            'folder': 'CapsWriter Server.app',
            'executable': 'CapsWriter Server',
            'bundle_id': 'offline.capswriter.server',
            'name': 'CapsWriter Server',
            'target': 'start_server',
            'microphone': None,
        },
    )
    return [_write_one_app(dest_root, version, spec) for spec in specs]


def _write_one_app(dest_root, version, spec):
    import plistlib
    app_root = join(dest_root, spec['folder'])
    contents = join(app_root, 'Contents')
    mac_dir = join(contents, 'MacOS')
    makedirs(mac_dir, exist_ok=True)
    executable = join(mac_dir, spec['executable'])
    with open(executable, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(_launcher_script(spec['target']))
    chmod(executable, 0o755)
    plist = {
        'CFBundleName': spec['name'],
        'CFBundleDisplayName': spec['name'],
        'CFBundleIdentifier': spec['bundle_id'],
        'CFBundleVersion': version,
        'CFBundleShortVersionString': version,
        'CFBundleExecutable': spec['executable'],
        'CFBundlePackageType': 'APPL',
        'LSUIElement': True,
        'LSMultipleInstancesProhibited': False,
        'NSHighResolutionCapable': True,
    }
    if spec['microphone']:
        plist['NSMicrophoneUsageDescription'] = spec['microphone']
    with open(join(contents, 'Info.plist'), 'wb') as handle:
        plistlib.dump(plist, handle)
    return app_root
