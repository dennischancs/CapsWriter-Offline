# coding: utf-8
from __future__ import annotations
import os
import sys
import subprocess
from typing import TYPE_CHECKING
from config_server import ServerConfig as Config
from ..state import console
from .. import logger # Server module logger
if TYPE_CHECKING:
    from ..app import CapsWriterServer


class TrayManager:
    """
    托盘管理器：负责系统托盘图标的初始化、菜单构建及回调处理。
    """
    def __init__(self, app: CapsWriterServer):
        self.app = app

    def start(self):
        """初始化系统托盘图标"""
        if not Config.enable_tray:
            return

        try:
            from . import enable_min_to_tray
        except ImportError as e:
            logger.warning(f"托盘模块导入失败，跳过托盘功能: {e}")
            return

        # 获取图标路径
        icon_path = os.path.join(self.app.base_dir, 'assets', 'icon.ico')
        
        menu = None
        if sys.platform == 'darwin':
            menu = [
                ('📂 日志', self._open_logs),
                ('✨ 热词', self._open_hotwords),
            ]
        # 启用托盘
        enable_min_to_tray(
            'CapsWriter Server',
            icon_path,
            exit_callback=self._request_exit,
            more_options=menu
        )
        logger.info("托盘图标已启用")

    def _open_path(self, target):
        if sys.platform == 'darwin':
            subprocess.Popen(['open', target])
        elif sys.platform == 'win32':
            os.startfile(target)
        else:
            subprocess.Popen(['xdg-open', target])

    def _open_logs(self, icon=None, item=None):
        folder = os.path.join(self.app.base_dir, 'logs')
        os.makedirs(folder, exist_ok=True)
        self._open_path(folder)

    def _open_hotwords(self, icon=None, item=None):
        target = os.path.abspath('hot-server.txt')
        self._open_path(target)

    def _request_exit(self, icon=None, item=None):
        """托盘图标引用的退出回调"""
        logger.info("托盘退出: 用户点击退出菜单，准备清理资源并退出")
        self.app.stop()

    def stop(self):
        """停止托盘图标"""
        if not Config.enable_tray:
            return
            
        try:
            from core.ui.tray import stop_tray
            stop_tray()
            logger.info("TrayManager: 托盘图标已卸载")
        except Exception as e:
            logger.debug(f"TrayManager: 卸载托盘时发生错误: {e}")
