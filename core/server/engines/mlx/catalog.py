# coding: utf-8
# 菜单只列出本地已经放好权重的模型。不在这里下载。
from pathlib import Path


MENU = (
    ('sensevoice', 'SenseVoice Small', ('SenseVoiceSmall',), None),
    ('fun_asr_nano', 'Fun-ASR Nano', ('Fun-ASR-Nano-2512',), None),
    ('qwen_asr:1.7b', 'Qwen3-ASR 1.7B 8bit', ('Qwen3-ASR-1.7B-8bit',), 'https://huggingface.co/mlx-community/Qwen3-ASR-1.7B-8bit'),
    ('qwen_asr:1.7b-6bit', 'Qwen3-ASR 1.7B 6bit', ('Qwen3-ASR-1.7B-6bit',), None),
    ('qwen_asr:1.7b-4bit', 'Qwen3-ASR 1.7B 4bit', ('Qwen3-ASR-1.7B-4bit',), 'https://huggingface.co/mlx-community/Qwen3-ASR-1.7B-4bit'),
    ('qwen_asr:1.7b-mxfp4', 'Qwen3-ASR 1.7B mxfp4', ('Qwen3-ASR-1.7B-mxfp4',), None),
    ('qwen_asr:0.6b', 'Qwen3-ASR 0.6B 8bit', ('Qwen3-ASR-0.6B-8bit',), 'https://huggingface.co/mlx-community/Qwen3-ASR-0.6B-8bit'),
    ('qwen_asr:0.6b-6bit', 'Qwen3-ASR 0.6B 6bit', ('Qwen3-ASR-0.6B-6bit',), None),
    ('qwen_asr:0.6b-4bit', 'Qwen3-ASR 0.6B 4bit', ('Qwen3-ASR-0.6B-4bit',), 'https://huggingface.co/mlx-community/Qwen3-ASR-0.6B-4bit'),
    ('qwen_asr:0.6b-mxfp4', 'Qwen3-ASR 0.6B mxfp4', ('Qwen3-ASR-0.6B-mxfp4',), None),
    ('paraformer', 'Paraformer', ('Paraformer',), None),
)

# 这次安装包只带这几份。对齐器仍要带上，文件字幕还用它。
PACK_DIRS = (
    'SenseVoiceSmall',
    'Qwen3-ASR-0.6B-6bit',
    'Qwen3-ASR-0.6B-mxfp4',
    'Qwen3-ASR-1.7B-6bit',
    'Qwen3-ASR-1.7B-4bit',
    'Qwen3-ForcedAligner-0.6B-8bit',
)


def weights_present(path):
    path = Path(path)
    if not path.is_dir():
        return False
    names = (
        'model.safetensors',
        'model.onnx',
        'model.int8.onnx',
        'encoder.onnx',
    )
    if any((path / name).is_file() for name in names):
        return True
    return any(path.rglob('model.safetensors')) or any(path.rglob('*.onnx'))


def installed_choices(mlx_dir, paraformer_dir=None):
    root = Path(mlx_dir)
    found = []
    for key, label, folders, _url in MENU:
        if key == 'paraformer':
            ready = weights_present(paraformer_dir) if paraformer_dir else False
        else:
            ready = any(weights_present(root / name) for name in folders)
        if ready:
            found.append((key, label))
    return found
