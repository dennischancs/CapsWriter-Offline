# coding: utf-8
# Darwin 用 pynput 上屏。Windows 仍用 keyboard 包。
import sys


class AccessibilityDenied(PermissionError):
    """Darwin 没有辅助功能权限，不能模拟按键。"""


def accessibility_trusted() -> bool:
    """非 Darwin 视为允许。Darwin 上查不到接口时不拦，避免误伤。"""
    if sys.platform != 'darwin':
        return True
    trusted = _ax_is_trusted()
    if trusted is None:
        return True
    return trusted


def _ax_is_trusted():
    """True / False / None。None 表示这个进程查不到辅助功能接口。"""
    try:
        from ApplicationServices import AXIsProcessTrusted
    except Exception:
        try:
            from Quartz import AXIsProcessTrusted
        except Exception:
            return None
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return None


def _listen_event_trusted():
    """输入监控。True / False / None。只查询，不弹出系统授权框。"""
    try:
        import Quartz
    except Exception:
        return None
    probe = getattr(Quartz, 'CGPreflightListenEventAccess', None)
    if probe is None:
        return None
    try:
        return bool(probe())
    except Exception:
        return None


def probe_darwin_permissions():
    """返回 (辅助功能, 输入监控)。非 Darwin 视为都允许。"""
    if sys.platform != 'darwin':
        return True, True
    return _ax_is_trusted(), _listen_event_trusted()


def darwin_permission_subject(platform_name=None, frozen=None, argv0=None, executable=None):
    """打包后的权限要授给 start_client，源码运行才是当前终端。"""
    name = sys.platform if platform_name is None else platform_name
    if name != 'darwin':
        return '当前终端'
    is_frozen = getattr(sys, 'frozen', False) if frozen is None else frozen
    raw = sys.argv[0] if argv0 is None else argv0
    exe = sys.executable if executable is None else executable
    from pathlib import Path
    candidate = Path(str(raw or '')).name or Path(str(exe or '')).name
    if is_frozen or candidate in ('start_client', 'start_server', 'CapsWriter', 'CapsWriter Server'):
        return candidate or 'CapsWriter'
    return '当前终端'


def prompt_for_accessibility(ax_trusted):
    """辅助功能被拒绝时，请系统把当前进程列进列表。不改开关。"""
    if sys.platform != 'darwin' or ax_trusted is not False:
        return False
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
    except Exception:
        return False
    try:
        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
    except Exception:
        return False
    return True


def darwin_permission_warnings(ax_trusted, listen_trusted, subject=None):
    """只把明确拒绝的权限写成给人看的句子。查不到接口时不假装被拒绝。"""
    who = darwin_permission_subject() if subject is None else subject
    messages = []
    if listen_trusted is False:
        messages.append(
            '没有输入监控权限，全局快捷键不生效。'
            f'请到系统设置 > 隐私与安全性 > 输入监控，允许 {who} 后重新启动。'
        )
    if ax_trusted is False:
        messages.append(
            '没有辅助功能权限，松开后文字留在提示里，不会上屏。'
            f'请到系统设置 > 隐私与安全性 > 辅助功能，允许 {who}。'
        )
    return messages


def _leave_on_toast(text: str) -> None:
    message = text or '没有辅助功能权限，文字没有上屏'
    try:
        from core.client import logger
        logger.warning('没有辅助功能权限，文字留在提示里')
    except Exception:
        pass
    try:
        from core.ui.toast import toast
        toast(message, duration=8000)
    except Exception:
        pass


def type_text(text: str) -> None:
    if not text:
        return
    if sys.platform == 'darwin':
        if not accessibility_trusted():
            _leave_on_toast(text)
            return
        from pynput.keyboard import Controller
        Controller().type(text)
        return
    import keyboard
    keyboard.write(text)


def press_enter() -> None:
    if sys.platform == 'darwin':
        if not accessibility_trusted():
            try:
                from core.client import logger
                logger.warning('没有辅助功能权限，回车没有发出')
            except Exception:
                pass
            return
        from pynput.keyboard import Controller, Key
        controller = Controller()
        controller.press(Key.enter)
        controller.release(Key.enter)
        return
    import keyboard
    keyboard.press_and_release('enter')


def copy_selection() -> None:
    if sys.platform == 'darwin':
        if not accessibility_trusted():
            raise AccessibilityDenied('没有辅助功能权限')
        from pynput.keyboard import Controller, Key
        controller = Controller()
        with controller.pressed(Key.cmd):
            controller.tap('c')
        return
    import keyboard
    keyboard.press_and_release('ctrl+c')


def pressed_key_names():
    # Darwin 上 keyboard 包不在依赖里，失败就当没有按下的键。
    if sys.platform == 'darwin':
        return []
    import keyboard
    return list(keyboard._pressed_events.keys())
