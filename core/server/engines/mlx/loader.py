# coding: utf-8
# 按本地目录加载一次 MLX 模型，并写下 backend 和设备。
from pathlib import Path

import numpy as np

from .. import logger
from .audio import transcribe

_CACHE = {}


def describe_device():
    import mlx.core as mx
    try:
        mx.set_default_device(mx.gpu)
    except Exception as exc:
        logger.warning('无法把 MLX 默认设备设为 GPU: %s' % exc)
    device = mx.default_device()
    return str(device)


def clear_mlx_cache():
    try:
        import mlx.core as mx
    except Exception:
        return
    try:
        if hasattr(mx, 'clear_cache'):
            mx.clear_cache()
        elif hasattr(mx, 'metal') and hasattr(mx.metal, 'clear_cache'):
            mx.metal.clear_cache()
    except Exception as exc:
        logger.debug('清理 MLX 缓存失败: %s' % exc)


def release(local_dir):
    _CACHE.pop(str(Path(local_dir)), None)
    clear_mlx_cache()


def _warmup(model):
    silence = np.zeros(1600, dtype=np.float32)
    try:
        transcribe(model, silence, 16000)
    except Exception as exc:
        logger.warning('MLX 预热失败: %s' % exc)


def load_mlx_model(local_dir, repo_id, auto_download=False):
    path = Path(local_dir)
    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    if not path.is_dir():
        if auto_download:
            from .download import download_repo
            download_repo(repo_id, path)
        if not path.is_dir():
            raise FileNotFoundError('缺少 MLX 权重目录 %s，期望路径 %s' % (path.name, path))
    try:
        device = describe_device()
    except Exception as exc:
        raise RuntimeError('无法导入 MLX（目录 %s）: %s' % (path.name, exc))
    logger.info('backend=mlx repo=%s device=%s' % (repo_id, device))
    if 'gpu' not in device.lower():
        logger.warning('MLX 默认设备不是 GPU: %s' % device)
    try:
        from mlx_audio.stt import load
    except Exception as exc:
        raise RuntimeError('无法导入 mlx_audio（目录 %s）: %s' % (path.name, exc))
    model = load(str(path))
    _CACHE[key] = model
    _warmup(model)
    return model
