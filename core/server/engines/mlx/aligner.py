# coding: utf-8
# 把 MLX ForcedAligner 的结果收成 items[].start_time。
import importlib.util
from pathlib import Path

from config_server import ServerConfig as Config, ModelPaths
from ..base import BaseAlignEngine
from ..language import ENGINE_ALIGNER, get_language
from .audio import as_model_input
from .loader import load_mlx_model, release


def _align_types():
    # 只拿结果数据结构。不要执行 GGUF 包的 __init__，那里会去加载 ONNX 和 llama。
    path = Path(__file__).resolve().parents[1] / 'force_aligner_gguf' / 'inference' / 'schema.py'
    spec = importlib.util.spec_from_file_location('capswriter_mlx_align_schema', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ForcedAlignItem, module.ForcedAlignResult


ForcedAlignItem, ForcedAlignResult = _align_types()

REPO_ID = 'mlx-community/Qwen3-ForcedAligner-0.6B-8bit'


def align_language(language):
    # 和 GGUF 对齐器一样：auto 或未知代码退回中文，避免中文被当成按空格分词。
    if not language:
        return 'Chinese'
    mapped = get_language(ENGINE_ALIGNER, str(language).lower())
    return mapped or 'Chinese'


def _row_fields(row):
    if row is None or isinstance(row, (str, bytes)):
        return None
    if isinstance(row, dict):
        if 'start_time' not in row and 'start' not in row:
            return None
        text = row.get('text', '')
        start = row.get('start_time', row.get('start', 0.0))
        end = row.get('end_time', row.get('end', start))
        return text, start, end
    if not hasattr(row, 'start_time') and not hasattr(row, 'start'):
        return None
    text = getattr(row, 'text', '')
    start = getattr(row, 'start_time', getattr(row, 'start', 0.0))
    end = getattr(row, 'end_time', getattr(row, 'end', start))
    return text, start, end


def _extract_rows(raw):
    if raw is None:
        return []
    if isinstance(raw, dict):
        if 'items' in raw:
            return list(raw['items'])
        if 'segments' in raw:
            return list(raw['segments'])
        return [raw]
    items = getattr(raw, 'items', None)
    if items is not None:
        return list(items)
    segments = getattr(raw, 'segments', None)
    if segments is not None:
        return list(segments)
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return [raw]


def adapt_align_items(raw, offset_sec=0.0):
    # 乱序先按开始时间排。结束早于开始则拒绝。排完后仍单调。
    parsed = []
    for row in _extract_rows(raw):
        fields = _row_fields(row)
        if fields is None:
            continue
        text, start, end = fields
        if not str(text).strip():
            continue
        start = float(start) + float(offset_sec or 0.0)
        end = float(end) + float(offset_sec or 0.0)
        if end < start:
            raise ValueError('对齐时间倒序: %s %s > %s' % (text, start, end))
        parsed.append((str(text), start, end))
    parsed.sort(key=lambda item: (item[1], item[2]))
    items = []
    last = None
    for text, start, end in parsed:
        if last is not None and start < last:
            start = last
        if end < start:
            end = start
        last = end
        items.append(ForcedAlignItem(text=text, start_time=start, end_time=end))
    return items


class MlxAlignEngine(BaseAlignEngine):
    def __init__(self, config=None):
        super().__init__(config)
        self.model_dir = ModelPaths.mlx_aligner_dir
        self.model = load_mlx_model(
            self.model_dir,
            REPO_ID,
            auto_download=getattr(Config, 'mlx_auto_download', False),
        )

    def align(self, audio, text, language='Chinese', offset_sec=0.0, **kwargs):
        lang = align_language(language)
        array_input, _ = as_model_input(audio, kwargs.get('sample_rate', 16000))
        if hasattr(self.model, 'align'):
            raw = self.model.align(array_input, text=text, language=lang)
        else:
            raw = self.model.generate(array_input, text=text, language=lang)
        items = adapt_align_items(raw, offset_sec=offset_sec)
        return ForcedAlignResult(items=items)

    def cleanup(self):
        self.model = None
        release(self.model_dir)
