# -*- mode: python ; coding: utf-8 -*-
"""
现代化 PyInstaller 打包配置
适配 PyInstaller 6.0+ 版本
"""

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
# from PyInstaller.building.build_main import Analysis, COLLECT
from os.path import join, basename, dirname, exists
from os import getenv, walk, makedirs
from shutil import copyfile, rmtree

from build_support import (
    exclude_accel_binary,
    exe_icon,
    hiddenimports_for,
    copy_runtime_folders,
    ensure_darwin_mlx_runtime,
    remove_darwin_apps,
    skip_collected_data,
    use_upx,
)

# ==================== 打包配置选项 ====================

# 是否收集 CUDA provider
# - True: 包含 onnxruntime_providers_cuda.dll，支持 GPU 加速（需要在用户机器安装 CUDA 和 CUDNN）
# - False: 不包含 CUDA provider，只使用 CPU 模式（打包体积更小，兼容性更好）
INCLUDE_CUDA_PROVIDER = False

# ====================================================


# 初始化空列表
binaries = []
hiddenimports = []
datas = []

# 收集 sherpa_onnx 相关文件
try:
    sherpa_datas = collect_data_files('sherpa_onnx', include_py_files=False)

    # 根据 INCLUDE_CUDA_PROVIDER 决定是否收集 CUDA provider
    if not INCLUDE_CUDA_PROVIDER:
        # 过滤掉 CUDA provider 文件
        filtered_datas = []
        for src, dest in sherpa_datas:
            # 检查是否是 CUDA provider 相关文件
            if not skip_collected_data(src):
                filtered_datas.append((src, dest))
            else:
                print(f"[INFO] 排除加速 provider: {basename(src)}")
        sherpa_datas = filtered_datas

    datas += sherpa_datas
except:
    pass

# 收集 Pillow 相关文件（用于托盘图标）
try:
    pillow_datas = collect_data_files('PIL', include_py_files=False)
    datas += pillow_datas
    pillow_binaries = collect_all('PIL')
    binaries += pillow_binaries[1]
except:
    pass

# 隐藏导入 - 确保所有需要的模块都被包含
hiddenimports += [
    'websockets',
    'websockets.client',
    'websockets.server',
    'rich',
    'rich.console',
    'rich.markdown',
    'rich._unicode_data.unicode17-0-0',
    'keyboard',
    'pyclip', 
    'numpy',
    'sounddevice',
    'pypinyin',
    'watchdog',
    'typer',
    'srt',
    'sherpa_onnx',
    'PIL',           # Pillow 用于托盘图标
    'PIL.Image',
    'pystray',       # 托盘图标库
]

hiddenimports = hiddenimports_for(hiddenimports)
_USE_UPX = use_upx()
_ICON = exe_icon()

# # 对所有模块用 .py 源码而非 .pyc（猴子补丁 _get_module_collection_mode）
# import PyInstaller.building.build_main as _bm
# _bm._get_module_collection_mode = lambda md, n, na=False: _bm._ModuleCollectionMode.PY

a_1 = Analysis(
    ['start_server.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['build_hook.py'],
    excludes=['IPython',
              'PySide6', 'PySide2', 'PyQt5',
              'matplotlib', 'wx',
              'funasr', 'pydantic', 'torch',
              ],
    noarchive=True,
)

# 过滤掉从二进制依赖分析中收集的 DLL
# 这些 DLL 是 PyInstaller 在分析 DLL 依赖时自动收集的
# 我们排除从系统 CUDA 安装目录收集的 DLL（它们应该运行时从系统加载）
filtered_binaries = []
for name, src, type in a_1.binaries:
    src_lower = src.lower() if isinstance(src, str) else ''
    is_system_cuda_dll = (
        '\\nvidia gpu computing toolkit\\cuda\\' in src_lower or
        '\\nvidia\\cudnn\\' in src_lower or
        ('\\cuda\\v' in src_lower and '\\bin\\' in src_lower)
    )
    is_unwanted_onnx_dll = (
        'onnxruntime_providers_cuda.dll' in name.lower() 
    )

    if exclude_accel_binary(name, src) or is_system_cuda_dll or is_unwanted_onnx_dll:
        reason = "环境 CUDA DLL" if is_system_cuda_dll else "冗余 ONNX / DirectML"
        print(f"[INFO] 排除 {reason}: {name} (从 {src} 收集)")
    else:
        filtered_binaries.append((name, src, type))
a_1.binaries = filtered_binaries

a_2 = Analysis(
    ['start_client.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['build_hook.py'],
    excludes=['IPython',
              'PySide6', 'PySide2', 'PyQt5',
              'matplotlib', 'wx',
              ],
    noarchive=True,
)

# 客户端也过滤从系统 CUDA 目录收集的 DLL（保持一致性）
filtered_binaries = []
for name, src, type in a_2.binaries:
    src_lower = src.lower() if isinstance(src, str) else ''
    is_system_cuda_dll = (
        '\\nvidia gpu computing toolkit\\cuda\\' in src_lower or
        '\\nvidia\\cudnn\\' in src_lower or
        ('\\cuda\\v' in src_lower and '\\bin\\' in src_lower)
    )
    is_unwanted_onnx_dll = (
        'onnxruntime_providers_cuda.dll' in name.lower() or
        'directml.dll' in name.lower()
    )

    if exclude_accel_binary(name, src) or is_system_cuda_dll or is_unwanted_onnx_dll:
        reason = "环境 CUDA DLL" if is_system_cuda_dll else "冗余 ONNX / DirectML"
        print(f"[INFO] 排除 {reason}: {name} (从 {src} 收集)")
    else:
        filtered_binaries.append((name, src, type))
a_2.binaries = filtered_binaries


a_3 = Analysis(
    ['batch_transcribe.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['build_hook.py'],
    excludes=['IPython',
              'PySide6', 'PySide2', 'PyQt5',
              'matplotlib', 'wx',
              ],
    noarchive=True,
)

filtered_binaries = []
for name, src, type in a_3.binaries:
    src_lower = src.lower() if isinstance(src, str) else ''
    is_system_cuda_dll = (
        '\\nvidia gpu computing toolkit\\cuda\\' in src_lower or
        '\\nvidia\\cudnn\\' in src_lower or
        ('\\cuda\\v' in src_lower and '\\bin\\' in src_lower)
    )
    is_unwanted_onnx_dll = (
        'onnxruntime_providers_cuda.dll' in name.lower() or
        'directml.dll' in name.lower()
    )

    if exclude_accel_binary(name, src) or is_system_cuda_dll or is_unwanted_onnx_dll:
        reason = "环境 CUDA DLL" if is_system_cuda_dll else "冗余 ONNX / DirectML"
        print(f"[INFO] 排除 {reason}: {name} (从 {src} 收集)")
    else:
        filtered_binaries.append((name, src, type))
a_3.binaries = filtered_binaries


# 排除不要打包的模块（这些将作为源文件复制）
private_module = ['core', 'config_client', 'config_server', 'LLM', ]

for which in (a_1, a_2, a_3):
    filtered = []
    for name, src, type in which.pure:
        if not any(name == m or name.startswith(m + '.') for m in private_module):
            filtered.append((name, src, type))
    which.pure = filtered

# noarchive 会将私有模块也编译成 .pyc 放进 datas，排除掉以保持源码运行
for which in (a_1, a_2, a_3):
    filtered = []
    for name, src, type in which.datas:
        is_private = any(
            name.startswith(m + '/') or name.startswith(m + '\\') or name in (m + '.py', m + '.pyc')
            for m in private_module
        )
        if not is_private:
            filtered.append((name, src, type))
    which.datas = filtered


pyz_1 = PYZ(a_1.pure)
pyz_2 = PYZ(a_2.pure)
pyz_3 = PYZ(a_3.pure)


exe_1 = EXE(
    pyz_1,
    a_1.scripts,
    [],
    exclude_binaries=True,
    name='start_server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=_USE_UPX,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
    # 所有第三方依赖放入 internal 目录
    contents_directory='internal',
)
exe_2 = EXE(
    pyz_2,
    a_2.scripts,
    [],
    exclude_binaries=True,
    name='start_client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=_USE_UPX,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
    # 所有第三方依赖放入 internal 目录
    contents_directory='internal',
)

exe_3 = EXE(
    pyz_3,
    a_3.scripts,
    [],
    exclude_binaries=True,
    name='batch_transcribe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=_USE_UPX,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
    contents_directory='internal',
)

coll = COLLECT(
    exe_1,
    a_1.binaries,
    a_1.datas,

    exe_2,
    a_2.binaries,
    a_2.datas,

    exe_3,
    a_3.binaries,
    a_3.datas,

    strip=False,
    upx=_USE_UPX,
    upx_exclude=[],
    name='CapsWriter-Offline',
)


# 复制额外所需的文件（只复制用户自己写的文件）
my_files = [
    'config_client.py',
    'config_server.py',
    'core_server.py',
    'core_client.py',
    'hot.txt',
    'hot-server.txt',
    'hot-rule.txt',
    'readme.md',
    'LICENSE'
]
my_folders = []     # 这里是要复制的文件夹
dest_root = join(DISTPATH, basename(coll.name))

# 复制文件夹中的文件
for folder in my_folders:
    if not exists(folder):
        continue
    for dirpath, dirnames, filenames in walk(folder):
        for filename in filenames:
            src_file = join(dirpath, filename)
            if exists(src_file):
                my_files.append(src_file)

# 执行文件复制到根目录（不是 internal）
for file in my_files:
    if not exists(file):
        continue
    # 保持相对路径结构
    rel_path = file.replace('\\', '/') if '\\' in file else file
    dest_file = join(dest_root, rel_path)
    dest_folder = dirname(dest_file)
    makedirs(dest_folder, exist_ok=True)
    copyfile(file, dest_file)


# 为 models 文件夹建立链接，免去复制大文件
from platform import system
from subprocess import run

if system() == 'Windows':
    link_folders = ['models', 'assets', 'core', 'LLM', 'docs', 'log']  
    for folder in link_folders:
        if not exists(folder):
            continue
        dest_folder = join(dest_root, folder)
        if exists(dest_folder):
            rmtree(dest_folder)
        # 使用管理员权限运行的命令提示符来创建目录连接符
        cmd = ['mklink', '/j', dest_folder, folder]
        try:
            run(cmd, shell=True, check=True)
        except:
            print(f'警告：无法创建目录连接符 {dest_folder}，请手动创建或复制文件夹')

# Darwin 复制真实目录。缺的跳过。logs 只建空目录。Windows 仍用上面的 mklink。
# CAPSWRITER_SKIP_MODEL_COPY=1 只用于替换 batch_transcribe，不把模型再复制一份。
_copy_folders = None
if getenv('CAPSWRITER_SKIP_MODEL_COPY') == '1':
    from build_support import DARWIN_COPY_FOLDERS
    _copy_folders = tuple(name for name in DARWIN_COPY_FOLDERS if name != 'models')
copy_runtime_folders(dest_root, folders=_copy_folders)
ensure_darwin_mlx_runtime(dest_root)
remove_darwin_apps(dest_root)
