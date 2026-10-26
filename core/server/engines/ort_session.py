# coding: utf-8
# Windows 的 DML 保持原样。Darwin 上 CPU/DML/CUDA 先改成 CoreML，会话创建失败再退 CPU。
import sys
from pathlib import Path


def effective_provider(requested, platform=None):
    platform = platform if platform is not None else sys.platform
    name = (requested or 'CPU').upper()
    # 配置里的默认值是 CPU。Darwin 上 SenseVoice 仍要先试 CoreML，失败再由会话创建退回 CPU。
    if platform == 'darwin' and name in ('CPU', 'DML', 'CUDA'):
        return 'COREML', 'Darwin 上把 %s 改成 COREML' % name
    return name, None


def uses_fixed_shape(provider):
    return provider in ('DML', 'COREML')


def fixed_pad_seconds(provider, dml_pad_to):
    if provider == 'COREML':
        return 8
    if provider == 'DML':
        return int(dml_pad_to)
    return 0


def coreml_cache_dir():
    return Path.home() / 'Library' / 'Caches' / 'CapsWriter' / 'coreml'


def build_providers(provider, available, cache_dir=None):
    providers = ['CPUExecutionProvider']
    available = list(available or [])
    if provider in ('TRT', 'TENSORRT') and 'TensorrtExecutionProvider' in available:
        providers.insert(0, ('TensorrtExecutionProvider', {
            'trt_fp16_enable': True,
            'trt_engine_cache_enable': True,
        }))
    elif provider == 'DML' and 'DmlExecutionProvider' in available:
        providers.insert(0, 'DmlExecutionProvider')
    elif provider == 'CUDA' and 'CUDAExecutionProvider' in available:
        providers.insert(0, 'CUDAExecutionProvider')
    elif provider == 'COREML' and 'CoreMLExecutionProvider' in available:
        cache = Path(cache_dir) if cache_dir else coreml_cache_dir()
        try:
            cache.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            from . import logger
            logger.warning('CoreML 缓存目录不可用，改用 CPU: %s' % exc)
            return ['CPUExecutionProvider']
        providers.insert(0, ('CoreMLExecutionProvider', {
            'MLComputeUnits': 'ALL',
            'RequireStaticInputShapes': '1',
            'ModelCacheDirectory': str(cache),
        }))
    return providers


def _default_options():
    import onnxruntime as ort
    options = ort.SessionOptions()
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    options.add_session_config_entry('session.inter_op.allow_spinning', '0')
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return options


def create_ort_session(model_path, provider, available=None, session_factory=None, options_factory=None, cache_dir=None):
    import onnxruntime as ort
    if available is None:
        available = ort.get_available_providers()
    providers = build_providers(provider, available, cache_dir=cache_dir)
    factory = session_factory or ort.InferenceSession
    options = options_factory() if options_factory else _default_options()
    try:
        return factory(str(model_path), providers=providers, sess_options=options)
    except Exception:
        coreml = any('CoreML' in str(item) for item in providers)
        if provider == 'COREML' and coreml:
            from . import logger
            logger.warning('CoreML 会话创建失败，改用 CPU')
            return factory(str(model_path), providers=['CPUExecutionProvider'], sess_options=options)
        raise
