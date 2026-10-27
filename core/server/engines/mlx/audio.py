# coding: utf-8
# 把内存里的 float32 波形交给 MLX。模型只收路径时才落临时文件。
import os
import tempfile

import numpy as np


def waveform(samples, sample_rate=16000):
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if sample_rate and int(sample_rate) != 16000 and audio.size:
        duration = audio.size / float(sample_rate)
        target = max(1, int(duration * 16000))
        src = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
        dst = np.linspace(0.0, 1.0, num=target, endpoint=False)
        audio = np.interp(dst, src, audio).astype(np.float32)
    return audio


def as_model_input(samples, sample_rate=16000):
    audio = waveform(samples, sample_rate)
    try:
        import mlx.core as mx
        return mx.array(audio), None
    except Exception:
        return audio, None


def result_text(result):
    """取出识别文本。空文本保持为空，不要把整个结果对象印出来。"""
    if result is None:
        return ''
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return str(result.get('text') or '')
    if hasattr(result, 'text'):
        return str(getattr(result, 'text') or '')
    return str(result)


def transcribe(model, samples, sample_rate=16000, **kwargs):
    kwargs = dict((key, value) for key, value in kwargs.items() if value is not None)
    array_input, _ = as_model_input(samples, sample_rate)
    try:
        return model.generate(array_input, **kwargs)
    except TypeError:
        pass
    audio = waveform(samples, sample_rate)
    path = None
    try:
        import soundfile as sf
        handle = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        path = handle.name
        handle.close()
        sf.write(path, audio, 16000)
        return model.generate(path, **kwargs)
    finally:
        if path and os.path.exists(path):
            os.remove(path)


def build_fun_context(hotwords, context):
    parts = []
    words = [str(word).strip() for word in (hotwords or []) if str(word).strip()]
    if words:
        parts.append(' '.join(words))
    if context and str(context).strip():
        parts.append(str(context).strip())
    if not parts:
        return None
    return '\n'.join(parts)
