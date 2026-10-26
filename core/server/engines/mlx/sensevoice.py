# coding: utf-8
from typing import List, Optional

from config_server import ServerConfig as Config, ModelPaths
from ..base import BaseASREngine, EngineCapabilities
from ..language import ENGINE_SENSEVOICE, get_language
from .audio import result_text, transcribe
from .loader import load_mlx_model, release
from .stream import WaveformStream

REPO_ID = 'mlx-community/SenseVoiceSmall'


class SenseVoiceMLXEngine(BaseASREngine):
    # 不声明时间戳，也不做 CTC 热词雷达。

    def __init__(self, config=None):
        super().__init__(config)
        self.model_dir = ModelPaths.mlx_sensevoice_dir
        self.model = load_mlx_model(
            self.model_dir,
            REPO_ID,
            auto_download=getattr(Config, 'mlx_auto_download', False),
        )

    @property
    def capabilities(self) -> List[EngineCapabilities]:
        return [EngineCapabilities.ASR, EngineCapabilities.PUNC]

    def create_stream(self, hotwords: Optional[str] = None) -> WaveformStream:
        return WaveformStream()

    def decode_stream(self, stream, context: Optional[str] = None, language: Optional[str] = None, itn: bool = True, **kwargs):
        if stream.audio_data is None:
            return
        lid = get_language(ENGINE_SENSEVOICE, language) if language else 'auto'
        result = transcribe(
            self.model,
            stream.audio_data,
            stream.sample_rate,
            language=lid or 'auto',
            use_itn=itn,
        )
        stream.result.text = result_text(result)

    def cleanup(self):
        self.model = None
        release(self.model_dir)
