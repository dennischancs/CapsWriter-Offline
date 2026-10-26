from pathlib import Path
import sys
import numpy as np
from core.server.engines.ort_session import (
    create_ort_session,
    effective_provider,
    fixed_pad_seconds,
    uses_fixed_shape,
)

class SenseVoiceDecoder:
    def __init__(self, decoder_path: str, onnx_provider="cpu", dml_pad_to: int = 30):
        # 1. 资源路径
        self.model_path = decoder_path
        decoder_path = Path(decoder_path)
        
        self.onnx_provider = onnx_provider.upper()

        # 2. 初始化会话
        effective, warning = effective_provider(self.onnx_provider, sys.platform)
        if warning:
            print(f"[Decoder] {warning}")
        self.onnx_provider = effective
        self.session = create_ort_session(str(decoder_path), self.onnx_provider)

        # 3. 精度适配
        in_type = self.session.get_inputs()[0].type
        self.input_dtype = np.float16 if 'float16' in in_type else np.float32

        # 4. DML 预热
        self.use_dml = uses_fixed_shape(self.onnx_provider)
        pad_seconds = fixed_pad_seconds(self.onnx_provider, dml_pad_to)
        self.fixed_len = int(pad_seconds * 17) + 4 # 1s ≈ 17帧 + 4帧 Prompt
        if self.use_dml and pad_seconds > 0:
            self.warmup()

    def warmup(self):
        """执行一次全量形状推理，触发 CTC Head 算子特化"""
        # CTC Decoder 的输入形状通常是 (1, T_plus_4, 512)
        dummy_enc = np.zeros((1, self.fixed_len, 512), dtype=self.input_dtype)
        print(f"[Decoder] {self.onnx_provider} 推理模式：正在使用形状为 {dummy_enc.shape} 的数据进行预热...")
        self.session.run(None, {"enc_out": dummy_enc})
        print(f"[Decoder] {self.onnx_provider} 预热完成。")

    def forward(self, enc_out):
        """
        执行 CTC Head 推理 (单次推理)
        """
        if enc_out.dtype != self.input_dtype:
            enc_out = enc_out.astype(self.input_dtype)
            
        # 模型一次性返回 Top-100 的概率和索引
        topk_log_probs, topk_indices = self.session.run(None, {"enc_out": enc_out})
        return topk_log_probs, topk_indices

    def decode_all(self, enc_out, sp, top_k=20, prompt_len=4, T_valid=None, blank_id=0):
        """
        [核心接口] 单次推理获取所有解码信息
        返回: (greedy_results, radar_indices, radar_probs, top1_indices)
        """
        # 1. 唯一的一次推理调用
        topk_log_probs, topk_indices = self.forward(enc_out)
        
        # 确定有效范围 (跳过 Prompt 区域)
        start = prompt_len
        end = (T_valid + prompt_len) if T_valid is not None else topk_indices.shape[1]
        
        # --- A. 提取雷达所需 Top-K 空间 ---
        radar_indices = topk_indices[0, start:end, :].astype(np.int32)
        radar_probs = np.exp(topk_log_probs[0, start:end, :].astype(np.float32))
        top1_indices = radar_indices[:, 0]
        
        # --- B. 构造 Greedy 结果 (基于 Top-1) ---
        greedy_ids = top1_indices
        collapsed = []
        if len(greedy_ids) > 0:
            curr_id = greedy_ids[0]
            start_frame = 0
            for i in range(1, len(greedy_ids)):
                if greedy_ids[i] != curr_id:
                    collapsed.append((curr_id, start_frame))
                    curr_id = greedy_ids[i]
                    start_frame = i
            collapsed.append((curr_id, start_frame))

        greedy_results = []
        for tid, fidx in collapsed:
            if tid == blank_id: continue
            char = sp.id_to_piece(int(tid)).replace("\u2581", " ")
            if not char.strip() and char != " ": ignore_char = True
            else:
                greedy_results.append({
                    "text": char,
                    "start": round(fidx * 0.060, 3)
                })

        return greedy_results, radar_indices, radar_probs, top1_indices
