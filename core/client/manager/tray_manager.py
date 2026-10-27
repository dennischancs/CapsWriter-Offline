# coding: utf-8
import os
from . import logger
import os, sys, subprocess, time, threading
from config_client import ClientConfig as Config


class TrayManager:
    """
    托盘管理器：负责系统托盘图标的初始化、菜单构建及回调处理。
    """
    def __init__(self, app):
        self.app = app

    @property
    def state(self):
        return self.app.state

    def start(self):
        """初始化系统托盘图标"""
        if not Config.enable_tray:
            return
        # 状态栏只能在主线程创建。麦克风线程再进来时，图标已经在了。
        if sys.platform == 'darwin' and threading.current_thread() is not threading.main_thread():
            logger.debug('菜单栏只在主线程创建')
            return

        try:
            from ..ui import enable_min_to_tray
        except ImportError as e:
            logger.warning(f"托盘模块导入失败，跳过托盘功能: {e}")
            return

        # 获取图标路径
        icon_path = os.path.join(self.app.base_dir, 'assets', 'icon.ico')
        
        # 启用托盘
        menu = self.menu_items()
        enable_min_to_tray(
            'CapsWriter Client',
            icon_path,
            exit_callback=self.app.stop,
            more_options=menu
        )
        logger.info("托盘图标已启用")

    def menu_items(self):
        menu = [
            ('📋 复制结果', self._copy_last_result),
            ('📁 日记', self._open_diary),
            ('📝 上下文', self._add_context),
            ('✨ 热词', self._add_hotword),
            ('🧹 清除记忆', self._clear_memory),
            ('♻️ 重开音频', self._restart_audio),
        ]
        if sys.platform == 'darwin':
            menu.insert(0, ('📂 日志', self._open_logs))
            menu.append(('全部退出', self._quit_all))
        return menu

    def _quit_all(self, icon=None, item=None):
        """关掉客户端，并只结束锁里记下的那一个服务端。"""
        try:
            from core.tools.instance_guard import stop_recorded_server
            stop_recorded_server(self.app.base_dir)
        except Exception as exc:
            logger.warning('结束服务端失败: %s' % exc)
        self.app.stop()

    def run_blocking(self) -> None:
        """Darwin 上由主线程阻塞在菜单循环里。没有图标时立刻返回。"""
        if not Config.enable_tray:
            return
        try:
            from ..ui import run_tray
        except ImportError:
            return
        run_tray()

    @property
    def running(self) -> bool:
        try:
            from ..ui import tray_running
        except ImportError:
            return False
        return bool(tray_running())

    def _open_logs(self):
        folder = os.path.join(self.app.base_dir, 'logs')
        os.makedirs(folder, exist_ok=True)
        subprocess.Popen(['open', folder])

    def stop(self):
        """停止托盘图标"""
        if not Config.enable_tray:
            return
            
        try:
            from ..ui import stop_tray
            stop_tray()
            logger.info("TrayManager: 托盘图标已卸载")
        except Exception as e:
            logger.debug(f"TrayManager: 卸载托盘时发生错误: {e}")

    def _restart_audio(self):
        """重启音频流回调"""
        if hasattr(self.app, 'stream') and self.app.stream:
            self.app.stream.reopen()
            logger.info("用户请求重启音频")

    def _clear_memory(self):
        """清除 LLM 对话历史回调"""
        from ..ui import toast
        if self.app.llm:
            self.app.llm.clear_history()
            toast("清除成功：已清除所有角色的对话历史记录", duration=3000, bg="#075077")

    def _open_diary(self):
        """用系统默认方式打开当月日记文件夹回调"""
        base = self.app.diary.base_path
        folder = base / time.strftime('%Y') / time.strftime('%m')
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])

    def _add_hotword(self):
        """用系统默认方式打开热词文件回调"""
        
        target = os.path.abspath('hot.txt')
        if sys.platform == 'win32':
            os.startfile(target)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', target])
        else:
            subprocess.Popen(['xdg-open', target])

    def _add_context(self):
        """打开编辑上下文界面回调"""
        try:
            from ..ui import on_edit_context
            on_edit_context()
        except ImportError as e:
            logger.warning(f"无法导入上下文菜单处理器: {e}")

    def _copy_last_result(self):
        """复制最后一次识别结果到剪贴板回调"""
        text = self.state.last_output_text
        if text:
            from ..llm.llm_clipboard import copy_to_clipboard
            copy_to_clipboard(text)

    def _request_exit(self, icon=None, item=None):
        """托盘图标引用的退出回调"""
        logger.info("托盘退出: 用户点击退出菜单，准备清理资源并退出")
        self.app.stop()
