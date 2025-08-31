# coding: utf-8


"""
这个文件仅仅是为了 PyInstaller 打包用
"""

import sys
import typer
from core_client import init_file, init_mic, configure_boot_auto_start
from config import ClientConfig as Config

if __name__ == "__main__":
    # 如果参数传入文件，那就转录文件
    # 如果没有多余参数，就从麦克风输入
    if sys.argv[1:]:
        typer.run(init_file)
    else:
        # 检查并配置开机自启
        if hasattr(Config, 'boot_auto_start') and Config.boot_auto_start:
            from util.client_cosmic import console
            console.print("[cyan]正在检查/配置开机自启...[/cyan]")
            configure_boot_auto_start(True)
        elif hasattr(Config, 'boot_auto_start') and not Config.boot_auto_start:
            from util.client_cosmic import console
            console.print("[cyan]正在检查/取消开机自启...[/cyan]")
            configure_boot_auto_start(False)
        
        init_mic()
