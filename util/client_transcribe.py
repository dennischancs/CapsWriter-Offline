import base64
import json
import os
import sys
import platform
import uuid
from pathlib import Path
import time
import re
import wave
import asyncio
import subprocess

import numpy as np
import websockets
import typer
import colorama
from util import srt_from_txt
from util.client_cosmic import console, Cosmic
from util.client_check_websocket import check_websocket
from config import ClientConfig as Config



async def transcribe_check(file: Path):
    # 检查连接
    if not await check_websocket():
        console.print('无法连接到服务端')
        sys.exit()

    if not file.exists():
        console.print(f'文件不存在：{file}')
        return False

async def transcribe_send(file: Path):

    # 获取连接
    websocket = Cosmic.websocket

    # 生成任务 id
    task_id = str(uuid.uuid1())
    console.print(f'\n任务标识：{task_id}')
    console.print(f'    处理文件：{file}')

    # 获取音频数据，ffmpeg 输出采样率 16000，单声道，float32 格式
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", file,
        "-f", "f32le",
        "-ac", "1",
        "-ar", "16000",
        "-",
    ]
    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    console.print(f'    正在提取音频', end='\r')
    if process.stdout is None:
        console.print("\n[bold red]错误：无法启动 FFmpeg 进程以提取音频。[/bold red]")
        return
    data = process.stdout.read()
    audio_duration = len(data) / 4 / 16000
    console.print(f'    音频长度：{audio_duration:.2f}s')

    # 构建分段消息，发送给服务端
    offset = 0
    while True:
        chunk_end = offset + 16000*4*60
        is_final = False if chunk_end < len(data) else True
        message = {
            'task_id': task_id,                     # 任务 ID
            'seg_duration': Config.file_seg_duration,    # 分段长度
            'seg_overlap': Config.file_seg_overlap,      # 分段重叠
            'is_final': is_final,                       # 是否结束
            'time_start': time.time(),              # 录音起始时间
            'time_frame': time.time(),              # 该帧时间
            'source': 'file',                       # 数据来源：从文件读的数据
            'data': base64.b64encode(
                        data[offset: chunk_end]
                    ).decode('utf-8'),
        }
        offset = chunk_end
        progress = min(offset / 4 / 16000, audio_duration)
        await websocket.send(json.dumps(message))
        console.print(f'    发送进度：{progress:.2f}s', end='\r')
        if is_final:
            break

async def transcribe_recv(file: Path):

    # 获取连接
    websocket = Cosmic.websocket

    # 接收结果，并添加超时机制
    message = None
    try:
        # 设置一个较长的超时时间，例如按音频时长的比例计算，或一个固定的较大值
        # 例如：每分钟音频给60秒超时，至少300秒
        # 我们这里先用一个固定的大超时值，比如 2 小时 (7200秒)
        # 因为文件可能很长。
        timeout_seconds = 7200 

        async def receive_messages():
            nonlocal message
            async for msg in websocket:
                parsed_msg = json.loads(msg)
                console.print(f'    转录进度: {parsed_msg["duration"]:.2f}s', end='\r')
                if parsed_msg['is_final']:
                    message = parsed_msg # 将最终消息赋值给外部变量
                    return # 结束此内部协程

        await asyncio.wait_for(receive_messages(), timeout=timeout_seconds)

    except asyncio.TimeoutError:
        console.print("\n[bold red]错误：从服务器接收结果超时。服务器可能已停止响应。[/bold red]")
        # 可以选择在这里关闭websocket或执行其他清理操作
        if Cosmic.websocket:
            await Cosmic.websocket.close()
        return # 提前退出函数
    except websockets.exceptions.ConnectionClosed as e:
        console.print(f"\n[bold red]错误：WebSocket 连接意外关闭: {e}[/bold red]")
        # Connection is already closed, no need to close again.
        return
    except Exception as e:
        console.print(f"\n[bold red]错误：接收结果时发生未知错误: {e}[/bold red]")
        if Cosmic.websocket:
            await Cosmic.websocket.close()
        return

    if message is None:
        console.print("\n[bold red]错误：未能从服务器接收到最终消息。[/bold red]")
        return

    # 解析结果
    text_merge = message['text']
    text_split = re.sub('[，。？]', '\n', text_merge)
    timestamps = message['timestamps']
    tokens = message['tokens']

    # 得到文件名
    json_filename = Path(file).with_suffix(".json")
    txt_filename = Path(file).with_suffix(".txt")
    merge_filename = Path(file).with_suffix(".merge.txt")

    # 写入结果
    with open(merge_filename, "w", encoding="utf-8") as f:
        f.write(text_merge)
    with open(txt_filename, "w", encoding="utf-8") as f:
        f.write(text_split)
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump({'timestamps': timestamps, 'tokens': tokens}, f, ensure_ascii=False)
    srt_from_txt.one_task(txt_filename)

    process_duration = message['time_complete'] - message['time_start']
    console.print(f'\033[K    处理耗时：{process_duration:.2f}s')
    console.print(f'    识别结果：\n[green]{message["text"]}')
