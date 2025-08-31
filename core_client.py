# coding: utf-8

import os
import sys
import asyncio
import signal
import subprocess
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

def start_core_server():
    """启动服务器，如果尚未运行的话"""
    # 检查是否在打包环境中运行
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 在打包环境中，使用 start_server.exe
        server_exe_name = 'start_server.exe'
        server_path = Path(BASE_DIR) / server_exe_name
        process_name = server_exe_name
    else:
        # 在开发环境中，使用 core_server.py
        server_script_name = 'core_server.py'
        server_path = Path(BASE_DIR) / server_script_name
        process_name = server_script_name

    # 检查服务器是否已在运行
    try:
        if system() == 'Windows':
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                # 打包环境：检查 start_server.exe 进程
                cmd = f'tasklist /FI "IMAGENAME eq {process_name}" /FO CSV'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
                if process_name in result.stdout:
                    console.print(f"[dim]{process_name} 似乎已在运行。[/dim]")
                    return
            else:
                # 开发环境：检查 python.exe/pythonw.exe 且命令行包含 core_server.py 的进程
                cmd = f'tasklist /FI "IMAGENAME eq python.exe" /FI "IMAGENAME eq pythonw.exe" /V /FO CSV'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
                if process_name in result.stdout:
                    console.print(f"[dim]{process_name} 似乎已在运行。[/dim]")
                    return
        else:
            # Linux/macOS: 使用 pgrep 或 ps
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                # 打包环境：检查 start_server 进程
                result = subprocess.run(['pgrep', '-f', process_name], capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    console.print(f"[dim]{process_name} 似乎已在运行。[/dim]")
                    return
            else:
                # 开发环境：查找 python 且命令行包含 core_server.py 的进程
                try:
                    result = subprocess.run(['pgrep', '-f', f'python.*{process_name}'], capture_output=True, text=True, check=False)
                    if result.returncode == 0:
                        console.print(f"[dim]{process_name} 似乎已在运行。[/dim]")
                        return
                except FileNotFoundError:
                    # pgrep not found, try ps
                    ps_cmd = f"ps aux | grep 'python.*{process_name}' | grep -v grep"
                    result = subprocess.run(ps_cmd, shell=True, capture_output=True, text=True, check=False)
                    if result.stdout.strip():
                        console.print(f"[dim]{process_name} 似乎已在运行。[/dim]")
                        return
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]检查 {process_name} 进程时出错: {e}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]检查 {process_name} 进程时发生意外错误: {e}[/yellow]")

    # 如果未运行，则启动
    console.print(f"[cyan]{process_name} 未运行，正在启动...[/cyan]")
    try:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # 打包环境：直接启动 exe
            if system() == 'Windows':
                subprocess.Popen([str(server_path)], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen([str(server_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # 开发环境：使用 python 启动脚本
            if system() == 'Windows':
                python_executable = sys.executable.replace('python.exe', 'pythonw.exe')
                if not Path(python_executable).exists():
                    python_executable = sys.executable
                subprocess.Popen([python_executable, str(server_path)], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen([sys.executable, str(server_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        console.print(f"[green]{process_name} 启动请求已发送。[/green]")
    except FileNotFoundError:
        console.print(f"[bold red]Error: {process_name} not found. Cannot start server.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Error starting {process_name}: {e}[/bold red]")

def configure_boot_auto_start(enable: bool):
    """配置开机自启"""
    current_system = system()
    client_path = Path(BASE_DIR) / 'core_client.py'
    python_executable = sys.executable

    if current_system == 'Windows':
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
        app_name = "CapsWriter-Offline-Client"

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if enable:
                # 构造启动命令，使用 pythonw.exe 避免弹出控制台
                cmd = f'"{python_executable.replace("python.exe", "pythonw.exe")}" "{client_path}"'
                if not Path(python_executable.replace("python.exe", "pythonw.exe")).exists():
                    cmd = f'"{python_executable}" "{client_path}"'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                console.print(f"[bold green]已配置开机自启: {app_name}[/bold green]")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    console.print(f"[bold yellow]已取消开机自启: {app_name}[/bold yellow]")
                except FileNotFoundError:
                    console.print(f"[dim]开机自启项未找到: {app_name}[/dim]")
            winreg.CloseKey(key)
        except PermissionError:
            console.print("[bold red]权限不足，请以管理员身份运行以修改开机自启设置。[/bold red]")
        except Exception as e:
            console.print(f"[bold red]修改开机自启设置时出错: {e}[/bold red]")

    elif current_system == 'Linux':
        # 使用 systemd user units
        # 需要用户手动执行: systemctl --user enable/disable capswriter-client.service
        service_content = f"""[Unit]
Description=CapsWriter Offline Client
After=network.target

[Service]
ExecStart={python_executable} {client_path}
Restart=always
RestartSec=5
User=%i

[Install]
WantedBy=default.target
"""
        service_file_path = Path.home() / ".config" / "systemd" / "user" / "capswriter-client.service"
        if enable:
            try:
                service_file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(service_file_path, 'w', encoding='utf-8') as f:
                    f.write(service_content)
                console.print(f"[bold green]Systemd service file created at: {service_file_path}[/bold green]")
                console.print("[yellow]请手动执行以下命令以启用服务:[/yellow]")
                console.print(f"[cyan]systemctl --user daemon-reload && systemctl --user enable capswriter-client.service[/cyan]")
            except Exception as e:
                console.print(f"[bold red]创建 systemd service 文件时出错: {e}[/bold red]")
        else:
            try:
                if service_file_path.exists():
                    service_file_path.unlink()
                    console.print(f"[bold yellow]Systemd service file removed: {service_file_path}[/bold yellow]")
                    console.print("[yellow]请手动执行以下命令以禁用服务:[/yellow]")
                    console.print(f"[cyan]systemctl --user disable capswriter-client.service[/cyan]")
                else:
                    console.print("[dim]Systemd service file not found.[/dim]")
            except Exception as e:
                console.print(f"[bold red]移除 systemd service 文件时出错: {e}[/bold red]")

    elif current_system == 'Darwin': # macOS
        # 使用 launchd agent
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.capswriter.offline.client</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_executable}</string>
        <string>{client_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/capswriter_client.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/capswriter_client.err.log</string>
</dict>
</plist>
"""
        launch_agent_dir = Path.home() / "Library" / "LaunchAgents"
        plist_file_path = launch_agent_dir / "com.capswriter.offline.client.plist"
        if enable:
            try:
                launch_agent_dir.mkdir(parents=True, exist_ok=True)
                with open(plist_file_path, 'w', encoding='utf-8') as f:
                    f.write(plist_content)
                console.print(f"[bold green]LaunchAgent plist file created at: {plist_file_path}[/bold green]")
                console.print("[yellow]请手动执行以下命令以加载服务:[/yellow]")
                console.print(f"[cyan]launchctl load {plist_file_path}[/cyan]")
            except Exception as e:
                console.print(f"[bold red]创建 LaunchAgent plist 文件时出错: {e}[/bold red]")
        else:
            try:
                if plist_file_path.exists():
                    # 先尝试卸载
                    subprocess.run(["launchctl", "unload", str(plist_file_path)], check=False, capture_output=True)
                    plist_file_path.unlink()
                    console.print(f"[bold yellow]LaunchAgent plist file removed: {plist_file_path}[/bold yellow]")
                else:
                    console.print("[dim]LaunchAgent plist file not found.[/dim]")
            except Exception as e:
                console.print(f"[bold red]移除 LaunchAgent plist 文件时出错: {e}[/bold red]")
    else:
        console.print(f"[bold yellow]不支持的操作系统: {current_system}, 无法自动配置开机自启。[/bold yellow]")


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
    console.print("[cyan]尝试启动 core_server...[/cyan]")
    start_core_server()
    console.print("[green]core_server 启动请求已发送。[/green]")
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
    
    def scan_directory_recursive(directory: Path):
        """递归扫描目录及其子目录中的所有文件"""
        console.print(f"[bold blue]Processing directory: {directory}[/bold blue]")
        for item in directory.rglob('*'):
            if item.is_file():
                console.print(f"[dim]Found file: {item}[/dim]")
                files_to_process.append(item)
    
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
            scan_directory_recursive(abs_item)
        elif abs_item.is_file():
            # 排除核心脚本文件，防止它们被当作媒体文件处理
            if abs_item.name in ['core_client.py', 'core_server.py']:
                console.print(f"[dim]Skipping core script: {abs_item.name}[/dim]")
            else:
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
        # 检查并配置开机自启
        # 注意：此操作可能会在 Windows 上弹出 UAC 提示，或在 Linux/macOS 上需要后续手动步骤
        if hasattr(Config, 'boot_auto_start') and Config.boot_auto_start:
            console.print("[cyan]正在检查/配置开机自启...[/cyan]")
            configure_boot_auto_start(True)
        elif hasattr(Config, 'boot_auto_start') and not Config.boot_auto_start:
            console.print("[cyan]正在检查/取消开机自启...[/cyan]")
            configure_boot_auto_start(False)
        init_mic()
