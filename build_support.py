# coding: utf-8
"""PyInstaller spec 的平台分支。Windows 的图标、UPX 和目录联接保持原样。"""
from os import makedirs, remove, symlink, walk
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
    for extra in ('mlx', 'mlx.core', 'mlx_audio', 'mlx_audio.stt', 'AppKit', 'tkinterdnd2'):
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


DARWIN_APP_BUNDLES = (
    'CapsWriter.app',
    'CapsWriter Server.app',
)


def _project_version():
    import tomllib
    with open(join(dirname(abspath(__file__)), 'pyproject.toml'), 'rb') as handle:
        return tomllib.load(handle)['project']['version']


def remove_darwin_apps(dest_root, platform_name=None):
    """删掉收集目录里打不开、也没有托盘的薄启动器。二进制和 internal 不动。"""
    if not is_darwin(platform_name):
        return []
    removed = []
    for name in DARWIN_APP_BUNDLES:
        path = join(dest_root, name)
        if exists(path):
            rmtree(path)
            removed.append(path)
    return removed
