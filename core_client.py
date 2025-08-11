# coding: utf-8

import os
import sys
import asyncio
import signal
from pathlib import Path
from platform import system
from typing import List



import typer
import colorama
import keyboard

from config import ClientConfig as Config
from util.client_cosmic import console, Cosmic
from util.client_stream import stream_open, stream_close
from util.client_shortcut_handler import bond_shortcut
from util.client_recv_result import recv_result
from util.client_show_tips import show_mic_tips, show_file_tips
from util.client_hot_update import update_hot_all, observe_hot

from util.client_transcribe import transcribe_check, transcribe_send, transcribe_recv
from util.client_adjust_srt import adjust_srt
from util.client_transcribe_advanced import process_media_file

from util.empty_working_set import empty_current_working_set

# 确保根目录位置正确，用相对路径加载模型
ORIGINAL_CWD = os.getcwd() # Capture the original CWD before changing it
USER_CWD = os.getcwd() # Capture the user's current working directory (where command is run)
BASE_DIR = os.path.dirname(__file__); os.chdir(BASE_DIR)

# 确保终端能使用 ANSI 控制字符
colorama.init()

# MacOS 的权限设置
if system() == 'Darwin' and not sys.argv[1:]:
    # These functions are only available on Unix-like systems
    import pwd # Ensure pwd is imported for getuid context, though not directly used here
    if os.getuid() != 0: # type: ignore
        print('在 MacOS 上需要以管理员启动客户端才能监听键盘活动，请 sudo 启动')
        input('按回车退出'); sys.exit()
    else:
        os.umask(0o000) # type: ignore


async def main_mic():
    Cosmic.loop = asyncio.get_event_loop()
    Cosmic.queue_in = asyncio.Queue()
    Cosmic.queue_out = asyncio.Queue()

    show_mic_tips()

    # 更新热词
    update_hot_all()

    # 实时更新热词
    observer = observe_hot()

    # 打开音频流
    Cosmic.stream = stream_open()

    # Ctrl-C 关闭音频流，触发自动重启
    signal.signal(signal.SIGINT, stream_close)

    # 绑定按键
    bond_shortcut()

    # 清空物理内存工作集
    if system() == 'Windows':
        empty_current_working_set()

    # 接收结果
    while True:
        await recv_result()


async def main_file(files: List[Path]):
    show_file_tips()

    for file in files:
        if file.suffix in ['.txt', '.json', 'srt']:
            adjust_srt(file)
        else: # Process media files with the new advanced logic
            try:
                await process_media_file(file) # Call the new async function
            except Exception as e:
                console.print(f"[bold red]An unexpected error occurred while processing {file}: {e}[/bold red]")
                # Optionally, continue to the next file or re-raise if critical

    if Cosmic.websocket:
        await Cosmic.websocket.close()
    input('\n按回车退出\n')


def init_mic():
    try:
        asyncio.run(main_mic())
    except KeyboardInterrupt:
        console.print(f'再见！')
    finally:
        print('...')


def init_file(files: List[Path]):
    """
    用 CapsWriter Server 转录音视频文件，生成 srt 字幕
    """
    files_to_process = []
    for item in files:
        # Convert relative path to absolute path first
        if not item.is_absolute():
            # Use USER_CWD which captures the user's current working directory where the command is run
            # This is captured before any directory changes occur in the script
            current_cwd = Path(USER_CWD)
            abs_item = (current_cwd / item).resolve()
        else:
            abs_item = item.resolve()
        
        console.print(f"[dim]Resolved path: {item} -> {abs_item}[/dim]")
        
        if abs_item.is_dir():
            console.print(f"[bold blue]Processing directory: {abs_item}[/bold blue]")
            for sub_item in abs_item.iterdir():
                if sub_item.is_file(): # Ensure we only process files
                    files_to_process.append(sub_item)
        elif abs_item.is_file():
            files_to_process.append(abs_item)
        else:
            console.print(f"[bold yellow]Warning: {abs_item} is not a valid file or directory. Skipping.[/bold yellow]")
    
    if not files_to_process:
        console.print("[bold red]No files to process. Exiting.[/bold red]")
        input('按回车退出\n')
        return

    try:
        asyncio.run(main_file(files_to_process))
    except KeyboardInterrupt:
        console.print(f'再见！')
        sys.exit()


if __name__ == "__main__":
    # 如果参数传入文件，那就转录文件
    # 如果没有多余参数，就从麦克风输入
    if sys.argv[1:]:
        typer.run(init_file)
    else:
        init_mic()
