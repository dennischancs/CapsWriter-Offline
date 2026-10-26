# coding: utf-8
import sys
from typing import Any
from ..base import BasePuncEngine


class CTTransformerPuncEngine(BasePuncEngine):
    """
    基于 CT-Transformer 的标点补全引擎 (使用 sherpa-onnx 实现)
    """

    def __init__(self, model_path: str):
        super().__init__(model_path)
        self.model_path = model_path
        self.engine = None
        self._initialize()

    def _initialize(self):
        """延迟初始化内核"""
        import sherpa_onnx
        if sys.platform == 'darwin':
            try:
                self.engine = self._build(sherpa_onnx, 'coreml')
                return
            except Exception as exc:
                from .. import logger
                logger.warning(f"标点 CoreML 失败，改用 CPU: {exc}")
        self.engine = self._build(sherpa_onnx, None)

    def _build(self, sherpa_onnx, provider):
        model_kwargs = {'ct_transformer': self.model_path}
        if provider:
            model_kwargs['provider'] = provider
        try:
            model = sherpa_onnx.OfflinePunctuationModelConfig(**model_kwargs)
        except TypeError:
            if provider:
                raise RuntimeError('当前 sherpa-onnx 不接受标点 provider')
            raise
        return sherpa_onnx.OfflinePunctuation(
            sherpa_onnx.OfflinePunctuationConfig(model=model)
        )

    def punctuate(self, text: str) -> str:
        """为文本注入标点"""
        if not self.engine or not text:
            return text
        try:
            return self.engine.add_punctuation(text)
        except Exception:
            return text

    def cleanup(self):
        """释放资源"""
        self.engine = None
