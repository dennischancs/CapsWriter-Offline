from util.client_cosmic import Cosmic, console
from pathlib import Path
import time
from os import makedirs


def rename_audio(task_id, text, time_start) -> Path | None:

    # 获取旧文件名
    file_path = Path(Cosmic.audio_files[task_id])

    # 确保旧文件存在
    if not file_path.exists():
        console.print(f'    文件不存在：{file_path}')
        return

    # 构建新文件名
    time_year = time.strftime('%Y', time.localtime(time_start))
    time_month = time.strftime('%m', time.localtime(time_start))
    time_ymdhms = time.strftime("%Y%m%d-%H%M%S", time.localtime(time_start))
    file_stem = f'({time_ymdhms}){text[:20]}'

    # 重命名
    file_path_new = file_path.with_stem(file_stem)
    file_path.rename(file_path_new)

    # 返回新的录音文件路径
    return file_path_new
