# coding: utf-8
"""界面日志里的发送进度和转录进度。分子按音频里的 60 秒往前走。"""
from __future__ import annotations

import re


PROGRESS_STEP_SECONDS = 60
_NUMBER = re.compile(r'(?:发送进度|转录进度)：\s*([0-9]+(?:\.[0-9]+)?)')


def progress_kind(line) -> str | None:
    """完成、失败和文件名不是进度，返回 None。"""
    text = str(line or '')
    if '发送进度' in text:
        return 'send'
    if '转录进度' in text:
        return 'transcribe'
    return None


def progress_numerator(line):
    """日志行里的分子。没有就返回 None。"""
    match = _NUMBER.search(str(line or ''))
    if match is None:
        return None
    return round(float(match.group(1)), 2)


def _seconds_text(seconds) -> str:
    value = float(seconds)
    nearest = round(value)
    if abs(value - nearest) < 1e-4:
        return str(int(nearest))
    return '%.2f' % value


def progress_mark(progress, interval=PROGRESS_STEP_SECONDS, total=None, finished=False) -> float:
    """已经读到或转完的档：0、60、120。结束时用音频的真实长度。"""
    step = float(interval) if interval else PROGRESS_STEP_SECONDS
    if step <= 0:
        step = PROGRESS_STEP_SECONDS
    value = max(0.0, float(progress or 0))
    end = float(total) if total else 0.0
    if finished or (end > 0 and value >= end - 0.01):
        if end > 0:
            return end
        return value
    steps = int((value + 0.05) // step)
    mark = steps * step
    if end > 0 and mark > end:
        return end
    return float(mark)


def send_progress_text(progress, total, interval, finished=False) -> str:
    end = float(total) if total else 0.0
    mark = progress_mark(progress, interval, end, finished=finished)
    if end > 0:
        return '    发送进度：%ss / %ss' % (_seconds_text(mark), _seconds_text(end))
    return '    发送进度：%ss' % _seconds_text(mark)


def transcribe_progress_text(progress, interval, finished=False) -> str:
    mark = progress_mark(progress, interval, progress if finished else None, finished=finished)
    return '    转录进度：%ss' % _seconds_text(mark)


class ProgressGate:
    """界面把同一种进度收成一行。分子变小是下一个文件，才另起一行。"""

    def __init__(self, interval=None, now=None):
        self.interval = PROGRESS_STEP_SECONDS if interval is None else interval
        self._seen = {}

    def decide(self, line, identity=None) -> str:
        """drop 重复，replace 原地改，append 新的一行。"""
        kind = progress_kind(line)
        if kind is None:
            return 'append'
        mark = progress_numerator(line)
        if mark is None:
            return 'append'
        key = kind if identity is None else '%s:%s' % (kind, identity)
        previous = self._seen.get(key)
        if previous is not None and abs(previous - mark) < 0.001:
            return 'drop'
        self._seen[key] = mark
        if previous is None or mark + 0.001 < previous:
            return 'append'
        return 'replace'

    def allow(self, line, moment=None, identity=None) -> bool:
        return self.decide(line, identity=identity) != 'drop'


def replace_last_progress(text, kind, line) -> str:
    """同一种进度只改最后那一行，旁边的文件名和耗时不动。"""
    marker = '发送进度' if kind == 'send' else '转录进度'
    raw = str(line or '').rstrip('\r\n')
    body = text[:-1] if str(text).endswith('\n') else str(text)
    lines = body.split('\n') if body else []
    found = None
    for index, item in enumerate(lines):
        if marker in item:
            found = index
    if found is None:
        lines.append(raw)
    else:
        lines[found] = raw
    return '\n'.join(lines) + '\n'


def apply_progress_line(text, line, gate, identity=None) -> str:
    """发送进度一行，转录进度另一行。完成时间留在被替换的那一行上。"""
    raw = str(line or '').rstrip('\r\n')
    if not raw:
        return text
    decision = gate.decide(raw, identity=identity)
    if decision == 'drop':
        return text
    if decision == 'replace':
        kind = progress_kind(raw)
        if kind:
            return replace_last_progress(text, kind, raw)
    if text and not str(text).endswith('\n'):
        text += '\n'
    return str(text) + raw + '\n'


def show_progress(console, gate, line, identity=None, moment=None) -> bool:
    """分子变了才打印。窗口再把同一种进度收成一行。完成、失败和文件名不挡。"""
    if not gate.allow(line, moment=moment, identity=identity):
        return False
    console.print(line)
    return True
