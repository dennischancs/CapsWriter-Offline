from pathlib import Path
import json
import sys
import numpy as np
from core.server.engines.ort_session import (
    create_ort_session,
    effective_provider,
    fixed_pad_seconds,
    uses_fixed_shape,
)

class SenseVoiceEncoder:
    def __init__(self, encoder_path: str, onnx_provider="cpu", dml_pad_to: int = 30):
        # 1. 资源路径
        self.model_path = encoder_path # 记录路径用于 TRT 缓存
        encoder_path = Path(encoder_path)
        
        self.onnx_provider = onnx_provider.upper()

        # 2. 初始化会话 (职责下放：稳健的 Provider 选择逻辑)
        
        # 3. 初始化会话 (职责下放：稳健的 Provider 选择逻辑)
        effective, warning = effective_provider(self.onnx_provider, sys.platform)
        if warning:
            print(f"[Encoder] {warning}")
        self.onnx_provider = effective
        self.session = create_ort_session(str(encoder_path), self.onnx_provider)
        
        # 3. 从 Metadata 加载内部配置 (配置全内置模式)
        meta = self.session.get_modelmeta().custom_metadata_map
        if "lid_dict" in meta:
            self.config = {
                "lid_dict": json.loads(meta["lid_dict"]),
                "textnorm_dict": json.loads(meta["textnorm_dict"]),
                "emo_dict": json.loads(meta["emo_dict"]),
                "input_size": int(meta.get("input_size", 560)),
                "output_size": int(meta.get("output_size", 512))
            }
        else:
            print("[Encoder] 警告：在 ONNX 中未找到元数据，将回退至硬编码配置。")
            self.config = {} # 或设置默认值

        # 4. 精度适配 (检测模型是 FP32 还是 FP16)
        in_type = self.session.get_inputs()[0].type
        self.input_dtype = np.float16 if 'float16' in in_type else np.float32

        # 5. DML 策略设置 (仅在 DML 模式下生效)
        self.use_dml = uses_fixed_shape(self.onnx_provider)
        pad_seconds = fixed_pad_seconds(self.onnx_provider, dml_pad_to)
        self.fixed_len = int(pad_seconds * 17) # 1s ≈ 17帧 LFR
        if self.use_dml and pad_seconds > 0:
            self.warmup()

    def warmup(self):
        """执行一次全量形状推理，触发 DML 算子特化"""
        dummy_lfr = np.random.randn(1, self.fixed_len, 560).astype(self.input_dtype)
        dummy_mask = np.ones((1, self.fixed_len), dtype=self.input_dtype)
        dummy_prompt = np.zeros((1, 4, 560), dtype=self.input_dtype)
        print(f"[Encoder] DML 推理模式：正在使用形状为 {dummy_lfr.shape} 的 {self.fixed_len//17}s 随机数据进行预热...")
        self.session.run(None, {
            "speech_feat": dummy_lfr,
            "mask": dummy_mask,
            "prompt_ids": np.zeros((1, 4), dtype=np.int64)
        })
        print("[Encoder] DML 预热完成。")

    def construct_prompt(self, lid="auto", itn=True):
        """构造 4 个 Prompt Token ID"""
        lid_dict = self.config.get("lid_dict", {})
        itn_dict = self.config.get("textnorm_dict", {})
        
        lid_idx = lid_dict.get(lid, 0) 
        itn_str = "withitn" if itn else "woitn"
        itn_idx = itn_dict.get(itn_str, 14)
        
        # 核心逻辑镜像 official: Language(1) -> Event_Emo(2) -> Style(1)
        # 现在只返回索引，Gather 操作在 ONNX 内部完成
        prompt_ids = np.array([lid_idx, 1, 2, itn_idx], dtype=np.int64)
        return prompt_ids[np.newaxis, :] # (1, 4)

    def forward(self, lfr_feat, lid="zh", itn=True):
        """
        执行 Encoder 推理
        返回: enc_out (1, T+4, 512)
        """
        # 1. 构造 Prompt ID 序列
        prompt_ids = self.construct_prompt(lid=lid, itn=itn)
        
        T_valid = lfr_feat.shape[0]
        
        if self.use_dml and T_valid < self.fixed_len:
            # DML 填充策略：Uniform Padding + Replicate Padding
            T_target = self.fixed_len
            
            # 构造 Mask (1为有效, 0为填充)
            mask = np.zeros((1, T_target), dtype=self.input_dtype)
            mask[0, :T_valid] = 1.0
            
            # 构造填充后的特征 (使用最后一帧复读填充)
            full_feat = np.empty((1, T_target, 560), dtype=self.input_dtype)
            full_feat[0, :T_valid, :] = lfr_feat.astype(self.input_dtype)
            full_feat[0, T_valid:, :] = lfr_feat[-1, :].astype(self.input_dtype) # Replicate
            
            # 3. 推理
            enc_out = self.session.run(None, {
                "speech_feat": full_feat,
                "mask": mask,
                "prompt_ids": prompt_ids
            })[0]
            
            # 4. 直接返回全量结果 (包括填充部分)
            # 填充区的输出已被内部掩码清零，保留它们可使 Decoder 形状同样保持稳定
            return enc_out
        else:
            # 动态轴推理 (非 DML 模式或长度已超过固定值)
            mask = np.ones((1, T_valid), dtype=self.input_dtype)
            enc_out = self.session.run(None, {
                "speech_feat": lfr_feat[np.newaxis, ...].astype(self.input_dtype),
                "mask": mask,
                "prompt_ids": prompt_ids
            })[0]
            return enc_out
