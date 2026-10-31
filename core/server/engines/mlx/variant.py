# coding: utf-8
from pathlib import Path
# Qwen3-ASR 在 MLX 上的体积选择。不在这里加载模型。

QWEN_17_8BIT_REPO = 'mlx-community/Qwen3-ASR-1.7B-8bit'
QWEN_06_8BIT_REPO = 'mlx-community/Qwen3-ASR-0.6B-8bit'
QWEN_17_4BIT_REPO = 'mlx-community/Qwen3-ASR-1.7B-4bit'
QWEN_06_4BIT_REPO = 'mlx-community/Qwen3-ASR-0.6B-4bit'

# 旧名字仍指向默认 8bit，避免别处还在用这两个常量。
QWEN_17_REPO = QWEN_17_8BIT_REPO
QWEN_06_REPO = QWEN_06_8BIT_REPO

# 4bit 有 mlx-community 仓库。6bit 和 mxfp4 由本地 8bit 再量化，没有上游仓库。
QWEN_VARIANTS = {
    '1.7b': ('1.7b', QWEN_17_8BIT_REPO, 'Qwen3-ASR-1.7B-8bit'),
    '1.7b-8bit': ('1.7b-8bit', QWEN_17_8BIT_REPO, 'Qwen3-ASR-1.7B-8bit'),
    '1.7b-6bit': ('1.7b-6bit', QWEN_17_8BIT_REPO, 'Qwen3-ASR-1.7B-6bit'),
    '1.7b-4bit': ('1.7b-4bit', QWEN_17_4BIT_REPO, 'Qwen3-ASR-1.7B-4bit'),
    '1.7b-mxfp4': ('1.7b-mxfp4', QWEN_17_8BIT_REPO, 'Qwen3-ASR-1.7B-mxfp4'),
    '0.6b': ('0.6b', QWEN_06_8BIT_REPO, 'Qwen3-ASR-0.6B-8bit'),
    '0.6b-8bit': ('0.6b-8bit', QWEN_06_8BIT_REPO, 'Qwen3-ASR-0.6B-8bit'),
    '0.6b-6bit': ('0.6b-6bit', QWEN_06_8BIT_REPO, 'Qwen3-ASR-0.6B-6bit'),
    '0.6b-4bit': ('0.6b-4bit', QWEN_06_4BIT_REPO, 'Qwen3-ASR-0.6B-4bit'),
    '0.6b-mxfp4': ('0.6b-mxfp4', QWEN_06_8BIT_REPO, 'Qwen3-ASR-0.6B-mxfp4'),
}
QWEN_17_DIR = QWEN_VARIANTS['1.7b'][2]
QWEN_06_DIR = QWEN_VARIANTS['0.6b'][2]
MEMORY_16GB = 16 * 1024 ** 3

_ALIASES = {
    '1.7': '1.7b',
    '1.7b': '1.7b',
    '1.7b-8bit': '1.7b-8bit',
    '1.7b-6bit': '1.7b-6bit',
    '1.7b-4bit': '1.7b-4bit',
    '1.7b-mxfp4': '1.7b-mxfp4',
    '0.6': '0.6b',
    '0.6b': '0.6b',
    '0.6b-8bit': '0.6b-8bit',
    '0.6b-6bit': '0.6b-6bit',
    '0.6b-4bit': '0.6b-4bit',
    '0.6b-mxfp4': '0.6b-mxfp4',
}


def normalize_qwen_variant(preference):
    pref = (preference or 'auto').lower().strip()
    return _ALIASES.get(pref, pref)


AUTO_LARGE = (
    '1.7b',
    '1.7b-6bit',
    '1.7b-4bit',
    '1.7b-mxfp4',
    '0.6b',
    '0.6b-6bit',
    '0.6b-4bit',
    '0.6b-mxfp4',
)
AUTO_SMALL = (
    '0.6b',
    '0.6b-6bit',
    '0.6b-4bit',
    '0.6b-mxfp4',
    '1.7b',
    '1.7b-6bit',
    '1.7b-4bit',
    '1.7b-mxfp4',
)
AUTO_ORDER = AUTO_LARGE


def select_qwen_variant(preference, total_memory_bytes, present=None):
    # 返回 (variant, repo_id, directory_name)。
    # 写明规格时照做，不顺着往下找。
    # auto 按内存选一条顺序，用本机已有目录里的第一份。
    pref = normalize_qwen_variant(preference)
    if pref in QWEN_VARIANTS:
        return QWEN_VARIANTS[pref]
    order = AUTO_LARGE if int(total_memory_bytes) >= MEMORY_16GB else AUTO_SMALL
    if present:
        names = {Path(path).name for path in present}
        for key in order:
            if QWEN_VARIANTS[key][2] in names:
                return QWEN_VARIANTS[key]
    if int(total_memory_bytes) >= MEMORY_16GB:
        return QWEN_VARIANTS['1.7b']
    return QWEN_VARIANTS['0.6b']


def is_memory_error(exc):
    if isinstance(exc, MemoryError):
        return True
    text = '%s %s' % (type(exc).__name__, exc)
    text = text.lower()
    keys = (
        'memoryerror',
        'out of memory',
        'outofmemory',
        'oom',
        'insufficient memory',
        'unable to allocate',
        'failed to allocate',
        'cannot allocate',
        "can't allocate",
        'attempting to allocate',
        'allocation failed',
        'metal::malloc',
    )
    return any(key in text for key in keys)


def load_qwen_with_fallback(preference, total_memory_bytes, loader, present=None):
    # loader(repo_id, directory_name)。1.7B 遇到内存错误时只改试一次 0.6B。
    # present 是本机已有目录。auto 会从里面选，不再固定去要没装上的 8bit。
    variant, repo, dirname = select_qwen_variant(preference, total_memory_bytes, present)
    try:
        model = loader(repo, dirname)
        return model, variant, False
    except Exception as exc:
        if not str(variant).startswith('1.7') or not is_memory_error(exc):
            raise
        fallback = None
        if present:
            names = {Path(path).name for path in present}
            for key in AUTO_ORDER:
                if key.startswith('0.6') and QWEN_VARIANTS[key][2] in names:
                    fallback = QWEN_VARIANTS[key]
                    break
        if fallback is None:
            fallback = QWEN_VARIANTS['0.6b']
        model = loader(fallback[1], fallback[2])
        return model, fallback[0], True
