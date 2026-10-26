# coding: utf-8
# 把 MLX 权重下到 models/mlx/目录名。默认不在缺目录时自动调用。
from pathlib import Path


REPOS = {
    'SenseVoiceSmall': 'mlx-community/SenseVoiceSmall',
    'Fun-ASR-Nano-2512': 'mlx-community/Fun-ASR-Nano-2512',
    'Qwen3-ASR-1.7B-8bit': 'mlx-community/Qwen3-ASR-1.7B-8bit',
    'Qwen3-ASR-0.6B-8bit': 'mlx-community/Qwen3-ASR-0.6B-8bit',
    'Qwen3-ForcedAligner-0.6B-8bit': 'mlx-community/Qwen3-ForcedAligner-0.6B-8bit',
}


def download_repo(repo_id, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id, local_dir=str(dest))
    return dest


def download_all(mlx_dir):
    root = Path(mlx_dir)
    for name, repo in REPOS.items():
        download_repo(repo, root / name)
