# coding: utf-8
"""界面日志里的发送进度和转录进度。最短间隔 30 秒一行。"""
from __future__ import annotations

import time


PROGRESS_INTERVAL_SECONDS = 30


def progress_kind(line) -> str | None:
    """完成、失败和文件名不是进度，返回 None。"""
    text = str(line or '')
    if '发送进度' in text:
        return 'send'
    if '转录进度' in text:
        return 'transcribe'
    return None


class ProgressGate:
    """同一种进度，第一行马上通过，之后没到间隔就丢掉。"""

    def __init__(self, interval=PROGRESS_INTERVAL_SECONDS, now=None):
        self.interval = PROGRESS_INTERVAL_SECONDS if interval is None else interval
        self._now = time.monotonic if now is None else now
        self._seen = {}

    def allow(self, line, moment=None, identity=None) -> bool:
        kind = progress_kind(line)
        if kind is None:
            return True
        key = kind if identity is None else '%s:%s' % (kind, identity)
        current = self._now() if moment is None else moment
        previous = self._seen.get(key)
        if previous is not None and (current - previous) < self.interval:
            return False
        self._seen[key] = current
        return True


def show_progress(console, gate, line, identity=None, moment=None) -> bool:
    """允许时另起一行。不再用回车覆盖，避免界面把每一次覆盖当成新日志。"""
    if not gate.allow(line, moment=moment, identity=identity):
        return False
    console.print(line)
    return True
