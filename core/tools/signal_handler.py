import signal
import sys
import time
import asyncio


class SignalHandler:
    def __init__(self, callback):
        self.last_time = time.time()
        self.callback = callback

    def __call__(self, signum, frame):
        now = time.time()
        if now - self.last_time > 1.0:
            self.last_time = now
            print(f"\n收到 {signal.Signals(signum).name}，1秒内再次按下将会退出...")
        else:
            print(f"\n收到 {signal.Signals(signum).name}，确认退出...\n")
            self.last_time = 0
            self.callback()
            
def register_signal(callback):
    signal.signal(signal.SIGINT, SignalHandler(callback))
    if sys.platform == 'darwin':
        # 菜单里的「全部退出」发的是 SIGTERM，要走和退出一样的清理。
        signal.signal(signal.SIGTERM, lambda signum, frame: callback())
