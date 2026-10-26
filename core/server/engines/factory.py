# coding: utf-8
import sys
from typing import Any, Dict, Type, Optional
from .base import BaseASREngine, BasePuncEngine, BaseAlignEngine
from config_server import (
    ServerConfig as Config,
    ParaformerArgs, SenseVoiceArgs, 
    FunASRNanoGGUFArgs, Qwen3ASRGGUFArgs,
    ModelPaths, ForceAlignerGGUFArgs
)


class EngineFactory:
    """
    引擎工厂类
    
    统一管理所有识别引擎、标点引擎和对齐引擎的实例化逻辑。
    使用延迟加载模式避免启动过慢。
    """

    # --- ASR 引擎加载器 ---

    @staticmethod
    def _load_sensevoice():
        from .sensevoice_onnx.asr_engine import SenseVoiceEngine, SenseVoiceConfig
        return SenseVoiceEngine, SenseVoiceConfig, SenseVoiceArgs

    @staticmethod
    def _load_paraformer():
        from .paraformer_onnx.asr_engine import ParaformerEngine, ParaformerConfig
        return ParaformerEngine, ParaformerConfig, ParaformerArgs

    @staticmethod
    def _load_fun_asr_nano():
        from .fun_asr_gguf.asr_engine import FunASREngine, ASREngineConfig as FunASRConfig
        return FunASREngine, FunASRConfig, FunASRNanoGGUFArgs

    @staticmethod
    def _load_qwen_asr():
        from .qwen_asr_gguf.asr_engine import QwenASREngine, ASREngineConfig as QwenASRConfig
        return QwenASREngine, QwenASRConfig, Qwen3ASRGGUFArgs

    _ASR_LOADERS = {
        'sensevoice': _load_sensevoice,
        'paraformer': _load_paraformer,
        'fun_asr_nano': _load_fun_asr_nano,
        'qwen_asr': _load_qwen_asr
    }

    @staticmethod
    def use_mlx_backend(platform, model_backend, model_type) -> bool:
        if platform != 'darwin':
            return False
        if model_type == 'paraformer':
            return False
        backend = (model_backend or 'auto').lower()
        if backend == 'onnx':
            return False
        if backend not in ('auto', 'mlx'):
            return False
        return model_type in ('sensevoice', 'fun_asr_nano', 'qwen_asr')

    @staticmethod
    def use_mlx_aligner(platform, model_backend) -> bool:
        if platform != 'darwin':
            return False
        return (model_backend or 'auto').lower() != 'onnx'

    @staticmethod
    def _create_mlx_engine(model_type: str) -> BaseASREngine:
        if model_type == 'sensevoice':
            from .mlx.sensevoice import SenseVoiceMLXEngine
            return SenseVoiceMLXEngine()
        if model_type == 'fun_asr_nano':
            from .mlx.funasr import FunASRMLXEngine
            return FunASRMLXEngine()
        if model_type == 'qwen_asr':
            from .mlx.qwen import QwenMLXEngine
            return QwenMLXEngine()
        raise ValueError(f"EngineFactory: 不支持的 MLX ASR 类型 '{model_type}'")

    @staticmethod
    def create_asr_engine(model_type: str) -> BaseASREngine:
        """创建 ASR 核心引擎"""
        model_type = model_type.lower()
        backend = getattr(Config, 'model_backend', 'auto')
        if EngineFactory.use_mlx_backend(sys.platform, backend, model_type):
            # MLX 失败不能静默改去加载 Windows DLL。
            return EngineFactory._create_mlx_engine(model_type)
        if model_type not in EngineFactory._ASR_LOADERS:
            raise ValueError(f"EngineFactory: 不支持的 ASR 类型 '{model_type}'")

        loader = EngineFactory._ASR_LOADERS[model_type]
        EngineClass, ConfigClass, ArgsObj = loader()
        
        config_data = {k: v for k, v in ArgsObj.__dict__.items() if not k.startswith('_')}
        config = ConfigClass(**config_data)
        
        return EngineClass(config)

    # --- 辅助引擎加载器 ---

    @staticmethod
    def create_punc_engine() -> BasePuncEngine:
        """创建标点引擎 (目前使用 CT-Transformer)"""
        try:
            from .ct_transformer.punc_engine import CTTransformerPuncEngine
            model_path = ModelPaths.punc_model_dir.as_posix()
            return CTTransformerPuncEngine(model_path)
        except Exception as e:
            from . import logger
            logger.warning(f"⚠️ [警告] 标点模型加载失败 (原因: {e})，系统将以【无标点模式】继续运行...")
            return BasePuncEngine(None)

    @staticmethod
    def create_align_engine() -> BaseAlignEngine:
        """创建对齐引擎 (目前使用 Qwen Force Aligner)"""
        backend = getattr(Config, 'model_backend', 'auto')
        if EngineFactory.use_mlx_aligner(sys.platform, backend):
            try:
                from .mlx.aligner import MlxAlignEngine
                return MlxAlignEngine()
            except Exception as e:
                from . import logger
                logger.warning(
                    f"MLX 对齐器加载失败: {e}\n将退回按字均分，这不是对齐成功。\n"
                )
                return BaseAlignEngine(None)
        try:
            from .force_aligner_gguf.align_engine import QwenForceAligner, AlignerConfig
            align_cfg_data = {
                k: v for k, v in ForceAlignerGGUFArgs.__dict__.items() 
                if not k.startswith('_')
            }
            config = AlignerConfig(**align_cfg_data)
            return QwenForceAligner(config)
        except Exception as e:
            from . import logger
            msg = f"⚠️ [警告] 对齐模型加载失败，原因: \n\n{e}\n\n系统将以【无精确时间戳模式】继续运行...\n\n"
            # 检查模型文件是否错放到上级目录
            aligner_dir = ModelPaths.force_aligner_gguf_dir
            aligner_files = [
                ModelPaths.force_aligner_gguf_encoder_frontend,
                ModelPaths.force_aligner_gguf_encoder_backend,
                ModelPaths.force_aligner_gguf_llm_decode,
            ]
            for parent in aligner_dir.parents:
                if any((parent / fp.name).exists() for fp in aligner_files):
                    msg += f"模型文件似乎错放到了上级目录，应解压到：[bold yellow]{aligner_dir}[/bold yellow]\n\n"
                    break
            logger.warning(msg)
            return BaseAlignEngine(None)
