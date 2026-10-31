# coding: utf-8
# 把已经下好的 Qwen3-ASR 8bit 再量化成 4bit、6bit 或 mxfp4。
# 音频编码器保持原来的精度。6bit 和 mxfp4 没有 mlx-community 仓库。
#
#   python -m core.server.engines.mlx.quantize 8bit目录 6bit models/mlx/Qwen3-ASR-1.7B-6bit
#
import json
import sys
import shutil
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_unflatten
from mlx_audio.lm.convert import save_config, save_model
from mlx_audio.stt import load

RECIPES = {
    '4bit': {'group_size': 64, 'bits': 4, 'mode': 'affine'},
    '6bit': {'group_size': 64, 'bits': 6, 'mode': 'affine'},
    'mxfp4': {'group_size': 32, 'bits': 4, 'mode': 'mxfp4'},
}
COPY_GLOBS = ('*.txt', '*.json', '*.jinja', '*.model')
SKIP_JSON = {'config.json', 'model.safetensors.index.json'}
def dequantize_loaded(model):
    """8bit 权重先还原成线性层，才能换成另一种比特数。"""
    replacements = []
    for name, module in model.named_modules():
        if isinstance(module, nn.QuantizedLinear):
            weight = mx.dequantize(
                module.weight,
                module.scales,
                module.biases,
                module.group_size,
                module.bits,
                module.mode,
            )
            layer = nn.Linear(weight.shape[1], weight.shape[0], bias=('bias' in module))
            layer.weight = weight
            if 'bias' in module:
                layer.bias = module.bias
            replacements.append((name, layer))
        elif isinstance(module, nn.QuantizedEmbedding):
            weight = mx.dequantize(
                module.weight,
                module.scales,
                module.biases,
                module.group_size,
                module.bits,
                module.mode,
            )
            layer = nn.Embedding(weight.shape[0], weight.shape[1])
            layer.weight = weight
            replacements.append((name, layer))
    if replacements:
        model.update_modules(tree_unflatten(replacements))
    return len(replacements)


def _keep_audio(path, module):
    # 音频编码器和归一化层保持原精度。只再量化语言模型的线性层和词表。
    if str(path).startswith('audio_tower'):
        return False
    return isinstance(module, (nn.Linear, nn.Embedding))


def requantize(model, recipe):
    spec = RECIPES[recipe]
    nn.quantize(
        model,
        group_size=spec['group_size'],
        bits=spec['bits'],
        mode=spec['mode'],
        class_predicate=_keep_audio,
    )
    mx.eval(model.parameters())
    return spec


def _copy_sidecars(src, dest):
    for pattern in COPY_GLOBS:
        for file in src.glob(pattern):
            if file.name in SKIP_JSON:
                continue
            shutil.copy(file, dest / file.name)


def convert_qwen(src, dest, recipe):
    """从本地 8bit 目录写出一份新的量化目录。目标已存在则不覆盖。"""
    src = Path(src)
    dest = Path(dest)
    if recipe not in RECIPES:
        raise ValueError('不支持的量化: %s' % recipe)
    if dest.exists():
        raise FileExistsError('量化目录已存在: %s' % dest)
    if not (src / 'model.safetensors').is_file() and not (src / 'config.json').is_file():
        raise FileNotFoundError('缺少 8bit 权重: %s' % src)

    model = load(str(src))
    dequantize_loaded(model)
    mx.eval(model.parameters())
    spec = requantize(model, recipe)

    dest.mkdir(parents=True)
    try:
        _copy_sidecars(src, dest)
        config = json.loads((src / 'config.json').read_text(encoding='utf-8'))
        config['quantization'] = spec
        config['quantization_config'] = spec
        save_config(config, dest / 'config.json')
        save_model(dest, model, donate_model=True)
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest
1] not in RECIPES:
        print(
            '用法: python -m core.server.engines.mlx.quantize 8bit目录 4bit|6bit|mxfp4 输出目录',
            file=sys.stderr,
        )
        return 2
    convert_qwen(argv[0], argv[2], argv[1])
    print(argv[2])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
