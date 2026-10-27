# coding: utf-8
"""
CapsWriter Offline 客户端主程序门面类 (Facade)

采用外观模式统一管理音频流 (AudioStreamManager)、
识别结果处理 (ResultProcessor) 和快捷键管理 (ShortcutManager)。
"""

import os
import sys
import asyncio
import threading
from pathlib import Path

from .state import ClientState
from . import logger
from config_client import ClientConfig as Config, __version__, active_shortcuts
from core.tools.signal_handler import register_signal
from .state import console
from .connection import WebSocketManager
from typing import TYPE_CHECKING, Optional
from .manager import (
    TrayManager,
    MicRunner, FileRunner
)
from .audio.stream import AudioStreamManager
from .shortcut.shortcut_manager import ShortcutManager
from .shortcut.shortcut_config import Shortcut

from .udp.udp_control import UDPController

from .hotword.manager import HotwordManager
from .llm.llm_handler import LLMHandler
from .output.text_output import TextOutput
from .diary.diary_writer import DiaryWriter
from core.tools.empty_working_set import empty_current_working_set
from platform import system



class CapsWriterClient:
    """
    CapsWriter 客户端门面类
    
    管理的外部接口简洁：start()。
    """
    def __init__(self):
        # 确保正确的工作目录
        self.base_dir = Path(__file__).parents[2]
        os.chdir(self.base_dir)
            
        # 初始化事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
            
        # 初始化状态容器
        self.state = ClientState(app=self)
        self._stopped = False

        # 初始化热词管理器
        self.hotword = HotwordManager(
            hotword_files=None,
            threshold=Config.hot_thresh,
            similar_threshold=Config.hot_similar
        )

        # 4. 初始化 LLM 润色系统
        self.llm = LLMHandler(app=self)
        
        self.output = TextOutput()
        self.diary = DiaryWriter(base_path=self.base_dir)

        # 初始化各管理器
        self.ws = WebSocketManager(self)
        self.tray = TrayManager(self)

        # 实例化硬件资源管理组件
        self.stream = AudioStreamManager(self)
        self.shortcut = ShortcutManager(self, [Shortcut(**sc) for sc in active_shortcuts()])
        self.udp = UDPController(self.shortcut)

        # 内存清理
        empty_current_working_set()
        self._darwin_session = None
        self._pending_files = []
        self._pending_lock = threading.Lock()

    def stop(self):
        """
        统一释放所有资源（清理顺序：硬件 -> 托盘 -> WebSocket -> State）
        """
        if self._stopped:
            return
        self._stopped = True
        self._release_darwin_session()
        logger.info("正在执行 CapsWriterClient 资源释放...")

        # 1. 停止核心运行组件
        self.udp.stop()
        self.shortcut.stop()
        self.stream.stop()

        # 2. 托盘资源
        self.tray.stop()

        # 3. 关闭监控
        self.hotword.stop()
        self.llm.stop()

        # 4. 关闭 WebSocket 连接
        self.ws.close_sync()

        # 5. 重置 State
        try:
            self.state.reset()
        except Exception as e:
            logger.warning(f"重置状态时发生错误: {e}")

        # 6. 停止事件循环（最后一步，确保前面的异步操作已调度）
        self.loop.stop()

        logger.info("资源释放完成")
        console.print('[green4]再见！')


    def start(self):
        """
        启动客户端 (唯一入口)
        
        自动根据命令行参数识别模式。内部管理异步循环。
        """

        # 注册退出函数
        register_signal(self.stop)

        files = [Path(f) for f in sys.argv[1:] if os.path.exists(f)]

        if sys.platform == 'darwin':
            from core.tools.instance_guard import collect_root, enter_client
            gate = enter_client(
                self.base_dir,
                files,
                collect_root(self.base_dir),
                Config.port,
                on_files=self._accept_handed_files,
            )
            if gate.action == 'exit':
                raise SystemExit(gate.code)
            self._darwin_session = gate.session
            if gate.session is not None:
                gate.session.serve(self._accept_handed_files)
                from core.ui.tray import set_before_restart
                set_before_restart(self._release_darwin_session)

        if files:
            # 文件转录模式
            runner = FileRunner(self, files)
            self._run_runner(runner)
            return

        runner = MicRunner(self)
        # 菜单栏的 NSApplication 只能占住主线程。麦克风和识别放到旁边。
        if sys.platform == 'darwin' and Config.enable_tray:
            self._start_mic_with_menu(runner)
            return
        self._run_runner(runner)

    def _run_runner(self, runner) -> None:
        try:
            self.loop.run_until_complete(runner.run())
        except RuntimeError:
            return

    def _start_mic_with_menu(self, runner) -> None:
        try:
            self.tray.start()
        except Exception as exc:
            logger.warning('菜单栏没有起来: %s' % exc)

        def worker():
            asyncio.set_event_loop(self.loop)
            self._run_runner(runner)

        # 没有菜单时，工作线程必须能撑住进程。
        has_menu = self.tray.running
        thread = threading.Thread(
            target=worker,
            name='capswriter-client',
            daemon=has_menu,
        )
        thread.start()
        if not has_menu:
            thread.join()
            return
        try:
            self.tray.run_blocking()
        finally:
            if self.loop.is_running():
                self.loop.call_soon_threadsafe(self.stop)
            else:
                self.stop()
            thread.join(timeout=3)

    def _release_darwin_session(self):
        session = getattr(self, '_darwin_session', None)
        self._darwin_session = None
        if session is not None:
            session.release()

    def _accept_handed_files(self, paths):
        existing = [Path(path) for path in paths if os.path.exists(path)]
        if not existing:
            return
        logger.info('收到待转录文件 %s 个' % len(existing))
        with self._pending_lock:
            self._pending_files.extend(existing)
        if self.loop.is_running():
            self.loop.call_soon_threadsafe(self.flush_handed_files)

    def flush_handed_files(self):
        if not self.loop.is_running():
            return
        with self._pending_lock:
            paths = list(self._pending_files)
            self._pending_files.clear()
        if not paths:
            return
        runner = FileRunner(self, paths, wait_for_enter=False, isolated=True)
        task = self.loop.create_task(runner.run())
        task.add_done_callback(self._log_handed_files)

    def _log_handed_files(self, task):
        try:
            exc = task.exception()
        except Exception:
            return
        if exc:
            logger.error('移交的文件没有转录完: %s' % exc)
