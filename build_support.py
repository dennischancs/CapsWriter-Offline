# coding: utf-8
"""PyInstaller spec 的平台分支。Windows 的图标、UPX 和目录联接保持原样。"""
from os import makedirs, remove, walk
from os.path import abspath, basename, dirname, exists, isdir, islink, join, relpath
from platform import system
from shutil import copyfile, copytree, ignore_patterns, rmtree


DARWIN_COPY_FOLDERS = (
    'models',
    'assets',
    'core',
    'LLM',
    'docs',
)
DARWIN_EMPTY_FOLDERS = (
    'logs',
    'log',
)
DARWIN_RUNTIME_FOLDERS = DARWIN_COPY_FOLDERS + DARWIN_EMPTY_FOLDERS


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
    for extra in ('mlx', 'mlx.core', 'mlx_audio', 'mlx_audio.stt', 'AppKit'):
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


def _discard(path):
    """先解开符号链接。不能对链接用 rmtree，否则会删掉仓库里的模型。"""
    if islink(path):
        remove(path)
        return
    if not exists(path):
        return
    if isdir(path):
        rmtree(path)
        return
    remove(path)


def _ignore_unpacked_mlx(folder, names):
    """安装包只带指定的 MLX 目录。其余模型留在仓库里。"""
    if basename(folder) != 'mlx':
        return set()
    allowed = {
        'SenseVoiceSmall',
        'Qwen3-ASR-0.6B-6bit',
        'Qwen3-ASR-0.6B-mxfp4',
        'Qwen3-ASR-1.7B-6bit',
        'Qwen3-ASR-1.7B-4bit',
        'Qwen3-ForcedAligner-0.6B-8bit',
    }
    return {
        name for name in names
        if name not in allowed and not name.startswith('.') and isdir(join(folder, name))
    }


def copy_runtime_folders(dest_root, folders=None, platform_name=None, empty_folders=None):
    """Darwin 上复制真实目录。缺的跳过。logs 只建空目录，不把开发机日志打进去。"""
    if not is_darwin(platform_name):
        return []
    copied = []
    names = DARWIN_COPY_FOLDERS if folders is None else folders
    for folder in names:
        if not exists(folder):
            continue
        dest_folder = join(dest_root, folder)
        _discard(dest_folder)
        copytree(
            folder,
            dest_folder,
            symlinks=False,
            ignore=lambda src, items: ignore_patterns('__pycache__', '*.pyc', '.DS_Store')(src, items)
            | _ignore_unpacked_mlx(src, items),
        )
        copied.append(dest_folder)
    blanks = DARWIN_EMPTY_FOLDERS if empty_folders is None else empty_folders
    for folder in blanks:
        dest_folder = join(dest_root, folder)
        _discard(dest_folder)
        makedirs(dest_folder, exist_ok=True)
        copied.append(dest_folder)
    return copied


def link_runtime_folders(dest_root, folders=None, platform_name=None):
    """旧名字。Darwin 上改为复制，不再链回仓库的绝对路径。"""
    return copy_runtime_folders(dest_root, folders=folders, platform_name=platform_name)


def linked_runtime_errors(dest_root):
    """包里的运行目录必须是真实文件。符号链接拿到别的机器上会断。"""
    errors = []
    for folder in DARWIN_RUNTIME_FOLDERS:
        path = join(dest_root, folder)
        if islink(path):
            errors.append('%s 是符号链接，包里要放真实文件' % path)
    return errors


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
