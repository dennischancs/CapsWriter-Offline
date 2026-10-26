# coding: utf-8
from typing import List, Optional

from config_server import ServerConfig as Config, ModelPaths
from ..base import BaseASREngine, EngineCapabilities
from ..language import ENGINE_FUN_ASR_NANO, get_language
from .audio import build_fun_context, result_text, transcribe
from .loader import load_mlx_model, release
from .stream import WaveformStream

REPO_ID = 'mlx-community/Fun-ASR-Nano-2512'


class FunASRMLXEngine(BaseASREngine):
    # 失败就抛出，不回退到 Windows DLL。

    def __init__(self, config=None):
        super().__init__(config)
        self.model_dir = ModelPaths.mlx_fun_asr_dir
        self._hotwords = []
        self.model = load_mlx_model(
            self.model_dir,
            REPO_ID,
            auto_download=getattr(Config, 'mlx_auto_download', False),
        )

    @property
    def capabilities(self) -> List[EngineCapabilities]:
        return [EngineCapabilities.ASR, EngineCapabilities.PUNC, EngineCapabilities.HOTWORDS]

    def create_stream(self, hotwords: Optional[str] = None) -> WaveformStream:
        return WaveformStream()

    def update_hotwords(self, hotwords: List[str]):
        self._hotwords = list(hotwords or [])

    def decode_stream(self, stream, context: Optional[str] = None, language: Optional[str] = None, **kwargs):
        if stream.audio_data is None:
            return
        lang = get_language(ENGINE_FUN_ASR_NANO, language) if language else None
        packed = build_fun_context(self._hotwords, context)
        result = transcribe(
            self.model,
            stream.audio_data,
            stream.sample_rate,
            context=packed,
            language=lang,
        )
        stream.result.text = result_text(result)

    def cleanup(self):
        self.model = None
        release(self.model_dir)
