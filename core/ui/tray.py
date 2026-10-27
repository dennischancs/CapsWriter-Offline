# coding: utf-8
"""
托盘图标模块

提供最小化到系统托盘的功能。
仅在 Windows 平台有效。

功能：
- 禁用控制台窗口的关闭按钮（防止误关）
- 最小化时自动隐藏到托盘
- 双击托盘图标显示/隐藏窗口
- 托盘菜单退出程序

注意：pystray 在 Linux 无 GUI 环境下无法导入，因此采用延迟导入。
"""

import os
import sys
import time
import threading
import platform
import subprocess
from typing import Optional
from . import logger, set_ui_logger

# 退出回调函数（由主程序传入）
_exit_callback = None
_before_restart = None

# 是否可用（在 enable_min_to_tray 时检测）
_tray_available = None

def _set_exit_callback(callback):
    """设置退出回调函数"""
    global _exit_callback
    _exit_callback = callback

def _get_exit_callback():
    return _exit_callback


def set_before_restart(callback):
    """重启前先放开客户端锁，避免新进程误以为自己是第二个。"""
    global _before_restart
    _before_restart = callback


def _check_tray_available() -> bool:
    """
    检查托盘功能是否可用
    
    Returns:
        bool: 是否可用
    """
    global _tray_available
    
    if _tray_available is not None:
        return _tray_available
    
    # 非 Windows 系统不支持
    if platform.system() not in ('Windows', 'Darwin'):
        _tray_available = False
        return False
    
    # 尝试导入 pystray
    try:
        import pystray
        from PIL import Image
        _tray_available = True
    except ImportError as e:
        logger.warning(f"托盘功能不可用: {e}")
        _tray_available = False
    except Exception as e:
        logger.warning(f"托盘功能检测失败: {e}")
        _tray_available = False
    
    return _tray_available


# Windows API（延迟初始化）
_win_api_initialized = False
user32 = None
kernel32 = None

SW_HIDE = 0
SW_RESTORE = 9
SW_SHOW = 5
SC_CLOSE = 0xF060
MF_BYCOMMAND = 0x00000000
GA_ROOT = 3


def _init_win_api():
    """初始化 Windows API"""
    global _win_api_initialized, user32, kernel32
    
    if _win_api_initialized:
        return
    
    if platform.system() != 'Windows':
        return
    
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        _win_api_initialized = True
    except Exception as e:
        logger.warning(f"Windows API 初始化失败: {e}")


# 全局变量
_tray_instance: Optional['_TraySystem'] = None
_lock = threading.Lock()


def _get_console_hwnd():
    if platform.system() != 'Windows':
        return None
    _init_win_api()
    if kernel32 is None or user32 is None:
        return None
    hwnd = kernel32.GetConsoleWindow()
    if hwnd:
        # 在 Windows Terminal 中，GetConsoleWindow 返回的是内部窗口句柄。
        # 为了能让“退出按钮不可用”以及“从任务栏消失”生效，我们需要操作最外层的顶层窗口。
        # 对于普通 CMD，GetAncestor(hwnd, GA_ROOT) 依然返回 hwnd 本身。
        root_hwnd = user32.GetAncestor(hwnd, GA_ROOT)
        if root_hwnd:
            return root_hwnd
    return hwnd


def _disable_close_button(hwnd: int) -> None:
    """禁用窗口的关闭按钮"""
    if user32 is None:
        return
    h_menu = user32.GetSystemMenu(hwnd, False)
    if h_menu:
        user32.DeleteMenu(h_menu, SC_CLOSE, MF_BYCOMMAND)


def _enable_close_button(hwnd: int) -> None:
    """恢复窗口的关闭按钮"""
    if user32 is None:
        return
    user32.GetSystemMenu(hwnd, True)


def _is_window_minimized(hwnd: int) -> bool:
    """检查窗口是否最小化"""
    if user32 is None:
        return False
    return user32.IsIconic(hwnd) != 0


def _is_window_visible(hwnd: int) -> bool:
    """检查窗口是否可见"""
    if user32 is None:
        return False
    return user32.IsWindowVisible(hwnd) != 0


def _create_icon(icon_path: Optional[str] = None):
    """
    创建托盘图标
    
    优先从指定路径加载图标文件，如果不存在则动态生成。
    
    Args:
        icon_path: 图标文件路径
        
    Returns:
        PIL Image 对象
    """
    from PIL import Image, ImageDraw
    
    # 如果图标文件存在，直接加载
    if icon_path and os.path.exists(icon_path):
        try:
            image = Image.open(icon_path)
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            return image.resize((64, 64), Image.Resampling.LANCZOS)
        except Exception:
            pass  # 加载失败则使用动态生成

    # 动态生成图标
    size = 64
    scale = 4
    real_size = size * scale

    image = Image.new('RGBA', (real_size, real_size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)

    blue = (55, 118, 171)
    yellow = (255, 211, 67)
    white = (255, 255, 255)

    # 蓝色圆角背景
    m = 2 * scale
    dc.rounded_rectangle(
        [m, m, real_size - m, real_size - m],
        radius=real_size // 4,
        fill=blue
    )

    # 黄色圆圈
    center = real_size // 2
    r = real_size // 3.5
    dc.ellipse([center - r, center - r, center + r, center + r], fill=yellow)

    # 白色圆点
    r2 = r // 2
    dc.ellipse([center - r2, center - r2, center + r2, center + r2], fill=white)

    return image.resize((size, size), Image.Resampling.LANCZOS)



def _status_item_metrics(item):
    """返回 (x, width)。窗口还没排好时 x 常常是 0，宽度可能是 0。"""
    try:
        frame = item.button().window().frame()
        x = float(frame.origin.x)
    except Exception:
        return None
    width = None
    try:
        width = float(frame.size.width)
    except Exception:
        pass
    return x, width


def _status_item_origin_x(item):
    metrics = _status_item_metrics(item)
    if metrics is None:
        return None
    return metrics[0]


def _status_item_offscreen(item) -> bool:
    origin = _status_item_origin_x(item)
    return origin is not None and origin < 0


def _leftmost_visible_status_x():
    """最靠左、还在屏幕里的菜单栏图标。读不到时返回 None。"""
    xs = _status_windows_x(name=None, on_screen_only=True)
    if not xs:
        return None
    return min(xs)


def _capswriter_status_positions():
    """控制中心画出来的 CapsWriter 窗口横坐标。按钮自己的 frame 不算。"""
    return _status_windows_x(name='CapsWriter', on_screen_only=False)


def _status_windows_x(name, on_screen_only):
    try:
        import Quartz
    except Exception:
        return None
    try:
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionAll,
            Quartz.kCGNullWindowID,
        )
    except Exception:
        return []
    found = []
    for window in windows or []:
        if window.get('kCGWindowLayer') != 25:
            continue
        title = window.get('kCGWindowName') or ''
        if name is not None and title != name:
            continue
        bounds = window.get('kCGWindowBounds') or {}
        try:
            x = float(bounds.get('X', 0))
            width = float(bounds.get('Width', 0))
            height = float(bounds.get('Height', 0))
        except Exception:
            continue
        if width < 8 or height <= 0 or height > 80:
            continue
        if on_screen_only and x < 0:
            continue
        found.append(x)
    return found


_fallback_icon_holder = {}
_FallbackClick = None


def _fallback_click_class():
    global _FallbackClick
    if _FallbackClick is not None:
        return _FallbackClick
    import AppKit
    import objc

    class FallbackClick(AppKit.NSObject):
        def onClick_(self, sender):
            icon = _fallback_icon_holder.get('icon')
            item = getattr(icon, '_status_item', None)
            if item is None:
                return
            try:
                menu = item.menu()
            except Exception:
                menu = None
            if menu is None:
                return
            try:
                bounds = sender.bounds()
                menu.popUpMenuPositioningItem_atLocation_inView_(
                    None,
                    AppKit.NSPoint(0, bounds.size.height),
                    sender,
                )
            except Exception:
                logger.debug('不能弹出菜单栏菜单')

    _FallbackClick = FallbackClick
    return _FallbackClick


def _menu_bar_band():
    """菜单栏那一条的 Cocoa 原点 y 和高度。读不到时按 24 点估。"""
    import AppKit
    screen = AppKit.NSScreen.mainScreen()
    frame = screen.frame()
    visible = screen.visibleFrame()
    top = float(visible.origin.y + visible.size.height)
    height = float(frame.size.height) - top
    if height < 22.0:
        try:
            height = float(AppKit.NSStatusBar.systemStatusBar().thickness())
        except Exception:
            height = 24.0
        top = float(frame.size.height) - height
    return top, height


def _fallback_origin():
    """放在最左边那个可见图标的左侧。菜单栏装不下时控制中心会把新图标排到屏幕外。"""
    width = 24.0
    leftmost = _leftmost_visible_status_x()
    if leftmost is None:
        return 24.0, width
    return max(24.0, leftmost - width - 8.0), width


def _hide_menu_bar_fallback(icon) -> None:
    panel = getattr(icon, '_menu_bar_panel', None)
    if panel is None:
        return
    try:
        panel.orderOut_(None)
    except Exception:
        pass


def _show_menu_bar_fallback(icon) -> None:
    """真状态项在屏幕外时，在菜单栏空档放一个能点的同样菜单。"""
    import AppKit
    item = getattr(icon, '_status_item', None)
    if item is None:
        return
    try:
        image = item.button().image()
    except Exception:
        image = None
    x, width = _fallback_origin()
    y, height = _menu_bar_band()
    _fallback_icon_holder['icon'] = icon
    panel = getattr(icon, '_menu_bar_panel', None)
    if panel is None:
        rect = AppKit.NSMakeRect(x, y, width, height)
        panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            AppKit.NSWindowStyleMaskBorderless | AppKit.NSWindowStyleMaskNonactivatingPanel,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(AppKit.NSColor.clearColor())
        panel.setHidesOnDeactivate_(False)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        button = AppKit.NSButton.alloc().initWithFrame_(AppKit.NSMakeRect(0, 0, width, height))
        button.setBordered_(False)
        button.setImagePosition_(AppKit.NSImageOnly)
        button.setImageScaling_(AppKit.NSImageScaleProportionallyDown)
        target = _fallback_click_class().alloc().init()
        icon._menu_bar_target = target
        button.setTarget_(target)
        button.setAction_('onClick:')
        panel.contentView().addSubview_(button)
        icon._menu_bar_panel = panel
        icon._menu_bar_button = button
    else:
        panel.setFrame_display_(AppKit.NSMakeRect(x, y, width, height), True)
        icon._menu_bar_button.setFrame_(AppKit.NSMakeRect(0, 0, width, height))
    if image is not None:
        icon._menu_bar_button.setImage_(image)
    panel.setLevel_(AppKit.NSStatusWindowLevel + 1)
    panel.orderFrontRegardless()
    panel.setLevel_(AppKit.NSStatusWindowLevel + 1)
    frame = panel.frame()
    shown = (round(float(frame.origin.x)), round(float(frame.origin.y)))
    if getattr(icon, '_menu_bar_fallback_at', None) != shown:
        logger.info('菜单栏状态项在屏幕外，改在 x=%.0f y=%.0f 显示', shown[0], shown[1])
        icon._menu_bar_fallback_at = shown


def _reveal_offscreen_status_item(icon) -> str:
    """控制中心画在屏幕外时，改用菜单栏空档里的按钮。已经在屏幕上就不动。"""
    positions = _capswriter_status_positions()
    if positions is None:
        positions = []
    on_screen = [x for x in positions if x >= 0]
    if on_screen:
        _hide_menu_bar_fallback(icon)
        logger.info('菜单栏状态项: CapsWriter x=%.0f', min(on_screen))
        return 'visible'
    offscreen = bool(positions) or _status_item_offscreen(getattr(icon, '_status_item', None))
    if not offscreen:
        return 'wait'
    _show_menu_bar_fallback(icon)
    return 'fallback'


def _move_status_item_on_screen(icon) -> None:
    _reveal_offscreen_status_item(icon)


def _schedule_status_item_repair(icon) -> None:
    """创建当下窗口还在 (0, 0)，等主循环把位置排完再查一次。"""
    if getattr(icon, '_status_repair_scheduled', False):
        return
    if _status_item_origin_x(getattr(icon, '_status_item', None)) is None:
        return
    try:
        import AppKit
    except Exception:
        return

    def check(timer):
        try:
            icon._status_repair_ticks = getattr(icon, '_status_repair_ticks', 0) + 1
            state = _reveal_offscreen_status_item(icon)
            if state == 'visible' or icon._status_repair_ticks >= 8:
                timer.invalidate()
        except Exception:
            logger.debug('复查菜单栏位置失败')

    try:
        icon._status_repair_block = check
        AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(0.45, True, check)
        icon._status_repair_scheduled = True
    except Exception:
        logger.debug('不能稍后复查菜单栏位置')


def _keep_macos_status_item(icon) -> None:
    """Darwin 上给状态项固定名字，避免被系统收成隐藏的 Item-N。

    控制中心若把图标排到屏幕外，就在可见图标左侧放一个同样的菜单按钮。
    """
    if platform.system() != 'Darwin':
        return
    item = getattr(icon, '_status_item', None)
    if item is None:
        return
    try:
        item.setAutosaveName_('CapsWriter')
    except Exception:
        logger.debug('菜单栏状态项不能设置固定名字')
        return
    try:
        item.setVisible_(True)
    except Exception:
        pass
    try:
        item.button().setHidden_(False)
    except Exception:
        pass
    _move_status_item_on_screen(icon)
    _schedule_status_item_repair(icon)
    origin = _status_item_origin_x(getattr(icon, '_status_item', None))
    if origin is None:
        logger.info('菜单栏状态项: CapsWriter')
    else:
        logger.info('菜单栏状态项: CapsWriter x=%.0f', origin)


class _TraySystem:
    """托盘系统内部类"""
    
    def __init__(self, name: Optional[str] = None, icon_path: Optional[str] = None, more_options: list = None):
        # 延迟导入 pystray
        import pystray
        from pystray import MenuItem as item
        
        self.hwnd = _get_console_hwnd()
        self.should_exit = False
        self.title = name if name else (os.path.basename(sys.argv[0]) or "Console App")

        # 禁用关闭按钮
        if self.hwnd:
            _disable_close_button(self.hwnd)

        # 定义菜单
        menu_items = [
            item(f"{self.title}", lambda: None, enabled=False),
            item('👁️ 显示/隐藏', self.toggle_window, default=True),
        ]

        # 添加额外选项
        if more_options:
            for opt_name, opt_func in more_options:
                menu_items.append(item(opt_name, opt_func))

        menu_items.append(item('🔄 重启', self.on_restart))
        menu_items.append(item('❌ 退出', self.on_exit))

        self.icon = pystray.Icon(
            "console_tray",
            _create_icon(icon_path),
            title=f"{self.title}",
            menu=tuple(menu_items)
        )
        _keep_macos_status_item(self.icon)

    def toggle_window(self) -> None:
        """切换窗口显示状态"""
        if not self.hwnd or user32 is None:
            return

        if _is_window_visible(self.hwnd):
            user32.ShowWindow(self.hwnd, SW_HIDE)
        else:
            user32.ShowWindow(self.hwnd, SW_RESTORE)
            user32.SetForegroundWindow(self.hwnd)

    def monitor_loop(self) -> None:
        """监控线程：检测最小化操作"""
        while not self.should_exit:
            if self.hwnd and user32:
                # 窗口可见且最小化 -> 隐藏到托盘
                if _is_window_visible(self.hwnd) and _is_window_minimized(self.hwnd):
                    user32.ShowWindow(self.hwnd, SW_HIDE)
            time.sleep(0.2)

    def on_restart(self, icon, item) -> None:
        """托盘重启处理：启动新进程后退出当前进程"""
        logger.info("托盘重启: 用户点击重启菜单，准备重启程序")
        if _before_restart is not None:
            try:
                _before_restart()
            except Exception as exc:
                logger.error(f"重启前释放实例失败: {exc}")
        try:
            if getattr(sys, 'frozen', False):
                cmd = sys.argv
            else:
                cmd = [sys.executable] + sys.argv
            subprocess.Popen(cmd)
        except Exception as e:
            logger.error(f"重启失败: {e}")
            return

        # 启动新进程成功后，调用退出回调退出当前进程
        exit_callback = _get_exit_callback()
        if exit_callback:
            try:
                exit_callback()
            except Exception as e:
                logger.error(f"重启时调用退出回调发生错误: {e}")

    def on_exit(self, icon, item) -> None:
        """托盘退出处理"""
        exit_callback = _get_exit_callback()

        logger.info("托盘退出: 用户点击退出菜单，准备清理资源并退出")

        # 1. 设置退出标志，停止监控循环
        self.should_exit = True
        logger.debug("已设置托盘退出标志")

        # 2. 恢复窗口关闭按钮并显示窗口
        if self.hwnd and user32:
            _enable_close_button(self.hwnd)
            user32.ShowWindow(self.hwnd, SW_RESTORE)
            logger.debug("已恢复窗口显示")

        # 3. 调用退出回调函数，请求主程序退出
        if exit_callback:
            try:
                logger.debug("正在调用退出回调函数...")
                exit_callback()
                logger.info("退出回调函数已调用")
            except Exception as e:
                logger.error(f"调用退出回调函数时发生错误: {e}")



        # 5. 停止托盘图标
        try:
            logger.debug("正在停止托盘图标线程...")
            self.icon.stop()
            logger.debug("托盘图标线程已停止")
        except Exception as e:
            logger.warning(f"停止托盘图标时发生错误: {e}")

    def start(self) -> None:
        """启动托盘系统"""
        # macOS 的状态栏菜单必须在主线程跑 NSApplication。这里只创建图标。
        if platform.system() == 'Darwin':
            return

        # 托盘图标线程
        t_tray = threading.Thread(target=self.icon.run, daemon=False)
        t_tray.start()

        if not self.hwnd:
            return

        # 状态监控线程
        t_monitor = threading.Thread(target=self.monitor_loop, daemon=True)
        t_monitor.start()

        # 启动时隐藏窗口
        self.toggle_window()


def run_tray() -> None:
    """在当前线程阻塞运行托盘。Darwin 上要由主线程调用。"""
    if _tray_instance is None or _tray_instance.icon is None:
        return
    _tray_instance.icon.run()


def tray_running() -> bool:
    return _tray_instance is not None and getattr(_tray_instance, 'icon', None) is not None


def enable_min_to_tray(name: Optional[str] = None, icon_path: Optional[str] = None, exit_callback=None, more_options: list = None) -> None:
    """
    启用最小化到托盘功能

    如果检测不到控制台窗口（如 .pyw 运行），则不执行任何操作。
    如果在 Linux 等无 GUI 环境下运行，也会跳过。

    Args:
        name: 托盘图标显示的名称，默认使用程序名称
        icon_path: 图标文件路径，默认动态生成
        exit_callback: 退出回调函数，当用户点击托盘退出菜单时调用
        more_options: 额外菜单项列表，格式为 [(名称, 回调函数), ...]
    """
    global _tray_instance

    global _tray_instance

    # 设置退出回调函数
    if exit_callback is not None:
        _set_exit_callback(exit_callback)

    # 检查托盘功能是否可用
    if not _check_tray_available():
        logger.info("托盘功能不可用，跳过启用")
        return

    # DPI 感知设置
    if platform.system() == 'Windows':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    with _lock:
        if _tray_instance is not None:
            return  # 已启动

        if platform.system() == 'Windows' and not _get_console_hwnd():
            return  # 没有控制台窗口

        _tray_instance = _TraySystem(name, icon_path, more_options)
        _tray_instance.start()



def stop_tray() -> None:
    """停止托盘图标"""
    global _tray_instance
    if _tray_instance and _tray_instance.icon:
        try:
            _tray_instance.icon.stop()
        except Exception:
            pass
    _tray_instance = None


if __name__ == "__main__":
    enable_min_to_tray()
    print("程序运行中... 你可以双击托盘图标隐藏我。")
    while True:
        time.sleep(1)
