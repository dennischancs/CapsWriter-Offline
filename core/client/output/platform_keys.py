# coding: utf-8
# Darwin 用 pynput 上屏。Windows 仍用 keyboard 包。
import sys


def type_text(text: str) -> None:
    if not text:
        return
    if sys.platform == 'darwin':
        from pynput.keyboard import Controller
        Controller().type(text)
        return
    import keyboard
    keyboard.write(text)


def press_enter() -> None:
    if sys.platform == 'darwin':
        from pynput.keyboard import Controller, Key
        controller = Controller()
        controller.press(Key.enter)
        controller.release(Key.enter)
        return
    import keyboard
    keyboard.press_and_release('enter')


def copy_selection() -> None:
    if sys.platform == 'darwin':
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
