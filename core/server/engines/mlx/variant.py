# coding: utf-8
# Qwen3-ASR 在 MLX 上的体积选择。不在这里加载模型。

QWEN_17_REPO = 'mlx-community/Qwen3-ASR-1.7B-8bit'
QWEN_06_REPO = 'mlx-community/Qwen3-ASR-0.6B-8bit'
QWEN_17_DIR = 'Qwen3-ASR-1.7B-8bit'
QWEN_06_DIR = 'Qwen3-ASR-0.6B-8bit'
MEMORY_16GB = 16 * 1024 ** 3


def select_qwen_variant(preference, total_memory_bytes):
    # 返回 (variant, repo_id, directory_name)。
    pref = (preference or 'auto').lower().strip()
    if pref in ('0.6b', '0.6'):
        return '0.6b', QWEN_06_REPO, QWEN_06_DIR
    if pref in ('1.7b', '1.7'):
        return '1.7b', QWEN_17_REPO, QWEN_17_DIR
    if int(total_memory_bytes) >= MEMORY_16GB:
        return '1.7b', QWEN_17_REPO, QWEN_17_DIR
    return '0.6b', QWEN_06_REPO, QWEN_06_DIR


def is_memory_error(exc):
    text = '%s %s' % (type(exc).__name__, exc)
    text = text.lower()
    keys = ('memoryerror', 'out of memory', 'outofmemory', 'oom', 'insufficient memory')
    return any(key in text for key in keys)


def load_qwen_with_fallback(preference, total_memory_bytes, loader):
    # loader(repo_id, directory_name)。1.7B 遇到内存错误时只改试一次 0.6B。
    variant, repo, dirname = select_qwen_variant(preference, total_memory_bytes)
    try:
        model = loader(repo, dirname)
        return model, variant, False
    except Exception as exc:
        if variant != '1.7b' or not is_memory_error(exc):
            raise
        model = loader(QWEN_06_REPO, QWEN_06_DIR)
        return model, '0.6b', True
