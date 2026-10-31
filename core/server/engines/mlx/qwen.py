# coding: utf-8
from typing import List, Optional

import psutil

from config_server import ServerConfig as Config, ModelPaths
from .. import logger
from ..base import BaseASREngine, EngineCapabilities
from ..language import ENGINE_QWEN_ASR, get_language
from .audio import result_text, transcribe
from .loader import load_mlx_model, release
from .stream import WaveformStream
from .variant import load_qwen_with_fallback


class QwenMLXEngine(BaseASREngine):
    # 1.7B 内存失败时只改用一次 0.6B。不声明时间戳。

    def __init__(self, config=None):
        super().__init__(config)
        self.model_dir = None
        self.model = None
        self._load()

    def _load(self):
        preference = getattr(Config, 'qwen_mlx_variant', 'auto')
        memory = int(psutil.virtual_memory().total)

        def loader(repo_id, dirname):
            path = ModelPaths.mlx_dir / dirname
            model = load_mlx_model(
                path,
                repo_id,
                auto_download=getattr(Config, 'mlx_auto_download', False),
            )
            self.model_dir = path
            return model

        self.model, variant, fell_back = load_qwen_with_fallback(preference, memory, loader)
        if fell_back:
            logger.warning('1.7B 加载失败，改用 0.6B 8bit')

    @property
    def capabilities(self) -> List[EngineCapabilities]:
        return [EngineCapabilities.ASR, EngineCapabilities.PUNC]

    def create_stream(self, hotwords: Optional[str] = None) -> WaveformStream:
        return WaveformStream()

    def decode_stream(self, stream, context: Optional[str] = None, language: Optional[str] = None, **kwargs):
        if stream.audio_data is None:
            return
        lang = get_language(ENGINE_QWEN_ASR, language) if language else None
        result = transcribe(
            self.model,
            stream.audio_data,
            stream.sample_rate,
            language=lang,
            context=context,
        )
        stream.result.text = result_text(result)

    def cleanup(self):
        self.model = None
        if self.model_dir is not None:
            release(self.model_dir)
