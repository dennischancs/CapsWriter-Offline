"""
前台窗口检测器

检测当前前台活动的应用程序信息，用于兼容性配置
"""
import platform


def get_active_window_info() -> dict:
    """
    获取当前前台窗口信息

    Returns:
        包含窗口信息的字典:
        - title: 窗口标题
        - class_name: 窗口类名
        - process_name: 进程名
        - app_name: 应用名称（推测）
    """
    system = platform.system()

    if system == 'Windows':
        return _get_windows_window_info()
    elif system == 'Darwin':  # macOS
        return _get_macos_window_info()
    elif system == 'Linux':
        return _get_linux_window_info()
    else:
        return {}


def _get_windows_window_info() -> dict:
    """Windows 平台窗口检测"""
    try:
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()

        # 获取窗口标题
        title = win32gui.GetWindowText(hwnd)

        # 获取窗口类名
        class_name = win32gui.GetClassName(hwnd)

        # 获取进程 ID 和进程名
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            import psutil
            process = psutil.Process(pid)
            process_name = process.name()
        except:
            process_name = ""

        # 推测应用名称
        app_name = _guess_app_name(title, class_name, process_name)

        return {
            'title': title,
            'class_name': class_name,
            'process_name': process_name,
            'app_name': app_name
        }
    except ImportError:
        # 如果没有安装依赖，返回空信息
        return {}
    except Exception:
        return {}


_front_app_warned = False


def _app_record(name: str, bundle: str = '') -> dict:
    return {
        'title': '',
        'class_name': bundle,
        'process_name': name,
        'app_name': name,
    }


def _get_macos_window_info() -> dict:
    """读前台应用名。不走 System Events，因此不需要自动化权限。"""
    info = _front_app_from_workspace()
    if info:
        return info
    info = _front_app_from_lsappinfo()
    if info:
        return info
    _warn_front_app_once()
    return {}


def _front_app_from_workspace():
    """NSWorkspace 能给出显示名，不会弹出自动化授权。"""
    try:
        from AppKit import NSWorkspace
    except Exception:
        return None
    try:
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception:
        return None
    if app is None:
        return None
    try:
        name = str(app.localizedName() or '').strip()
        bundle = str(app.bundleIdentifier() or '')
    except Exception:
        return None
    if not name:
        return None
    return _app_record(name, bundle)


def _front_app_from_lsappinfo():
    try:
        import subprocess

        front = subprocess.run(
            ['lsappinfo', 'front'],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    if front.returncode != 0:
        return None
    asn = (front.stdout or '').strip()
    if not asn:
        return None
    try:
        info = subprocess.run(
            ['lsappinfo', 'info', '-only', 'name', asn],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    if info.returncode != 0:
        return None
    import re
    match = re.search(r'"LSDisplayName"="([^"]*)"', info.stdout or '')
    if not match:
        return None
    name = match.group(1).strip()
    if not name:
        return None
    return _app_record(name)


def _warn_front_app_once() -> None:
    """同一次进程里只警告一次。听写不依赖窗口信息。"""
    global _front_app_warned
    if _front_app_warned:
        return
    _front_app_warned = True
    message = '读不到前台应用，窗口信息为空，听写继续'
    try:
        from core import get_logger
        get_logger('client').warning(message)
    except Exception:
        pass


def _get_linux_window_info() -> dict:
    """Linux 平台窗口检测"""
    try:
        import subprocess

        # 使用 wmctrl 获取活动窗口
        result = subprocess.run(
            ['wmctrl', '-G', '-a', ':ACTIVE:'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if len(parts) >= 5:
                title = ' '.join(parts[5:])
                return {
                    'title': title,
                    'class_name': '',
                    'process_name': '',
                    'app_name': title.split()[0] if title else ''
                }
    except Exception:
        pass

    return {}


def _guess_app_name(title: str, class_name: str, process_name: str) -> str:
    """
    根据窗口信息推测应用名称

    Args:
        title: 窗口标题
        class_name: 窗口类名
        process_name: 进程名

    Returns:
        推测的应用名称
    """
    # 优先使用进程名
    if process_name:
        # 去除 .exe 后缀
        name = process_name.replace('.exe', '').lower()
        return name

    # 其次使用类名
    if class_name:
        # Windows 常见类名映射
        class_mappings = {
            'chrome': 'Chrome',
            'msedge': 'Edge',
            'firefox': 'Firefox',
            'notepad': 'Notepad',
            'notepad++': 'Notepad++',
            'vscode': 'VSCode',
            'winword': 'Word',
            'xlmain': 'Excel',
            'pptmain': 'PowerPoint',
            'wndclass_desktop_glass': 'Desktop',
        }

        class_lower = class_name.lower()
        for key, value in class_mappings.items():
            if key in class_lower:
                return value

    # 最后使用标题的第一个词
    if title:
        first_word = title.split()[0]
        return first_word

    return ''


def is_likely_editor(window_info: dict) -> bool:
    """
    判断当前窗口是否可能是编辑器

    Args:
        window_info: 窗口信息字典

    Returns:
        True 表示可能是编辑器
    """
    if not window_info:
        return True  # 默认安全起见

    title = window_info.get('title', '').lower()
    class_name = window_info.get('class_name', '').lower()
    process_name = window_info.get('process_name', '').lower()

    # 编辑器关键词
    editor_keywords = [
        'visual studio', 'vscode', 'vim', 'nano', 'emacs',
        'notepad', 'sublime', 'atom', 'intellij', 'pycharm',
        'webstorm', 'idea', 'editor'
    ]

    # 检查标题
    for keyword in editor_keywords:
        if keyword in title or keyword in class_name or keyword in process_name:
            return True

    return False


def is_likely_browser(window_info: dict) -> bool:
    """
    判断当前窗口是否可能是浏览器

    Args:
        window_info: 窗口信息字典

    Returns:
        True 表示可能是浏览器
    """
    if not window_info:
        return False

    class_name = window_info.get('class_name', '').lower()
    process_name = window_info.get('process_name', '').lower()

    browser_keywords = ['chrome', 'firefox', 'edge', 'safari', 'opera', 'brave']

    for keyword in browser_keywords:
        if keyword in class_name or keyword in process_name:
            return True

    return False
