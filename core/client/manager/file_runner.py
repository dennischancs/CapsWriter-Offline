# coding: utf-8
from __future__ import annotations
import sys
from pathlib import Path
from . import logger
from config_client import ClientConfig as Config, __version__


class FileRunner:
    """
    文件模式运行器：负责文件转录模式下的逻辑，包括音视频文件的 ASR 转录和字幕文件的时间轴调整。
    """
    def __init__(self, app, files: list[Path], wait_for_enter: bool = True, isolated: bool = False):
        self.app = app
        self.files = files
        self.wait_for_enter = wait_for_enter
        self.isolated = isolated

    @property
    def state(self):
        return self.app.state

    @property
    def ws_manager(self):
        return self.app.ws

    def _should_wait(self) -> bool:
        if not self.wait_for_enter:
            return False
        if sys.platform != 'darwin':
            return True
        stdin = sys.stdin
        try:
            return stdin is not None and stdin.isatty()
        except Exception:
            return False

    def _take_pending(self) -> list:
        pending = getattr(self.app, '_pending_files', None)
        lock = getattr(self.app, '_pending_lock', None)
        if not pending:
            return []
        if lock is None:
            extra = list(pending)
            pending.clear()
            return extra
        with lock:
            extra = list(pending)
            pending.clear()
            return extra

    async def run(self):
        """文件转录模式主循环 (Coroutine)"""
        from ..transcribe import FileTranscriber, SrtAdjuster
        from ..ui import TipsDisplay

        files = list(self.files)
        if not self.isolated:
            TipsDisplay.show_file_tips()
            files.extend(self._take_pending())

        logger.info(f"待处理文件: {[str(f) for f in files]}")

        own_ws = None
        if self.isolated:
            from ..connection import WebSocketManager
            own_ws = WebSocketManager(self.app, isolated=True)

        started_hotword = False
        try:
            if not getattr(self.app.hotword, '_is_watcher_started', False):
                self.app.hotword.start()
                started_hotword = True

            for file in files:

                logger.info(f"正在处理文件: {file}")
                
                # 情况 1：文本类文件，执行 SRT 时间轴调整
                if file.suffix.lower() in ['.txt', '.json', '.srt', '.vtt']:
                    srt_adjuster = SrtAdjuster()
                    srt_adjuster.adjust(file)
                    
                # 情况 2：媒体文件，执行 ASR 识别转录
                else:
                    transcriber = FileTranscriber(self.app, file, ws=own_ws)
                    if await transcriber.check():
                        await transcriber.send()
                        await transcriber.receive()
                        await transcriber.close()
                
                logger.info(f"文件处理完成: {file}")
            
            logger.info("所有文件已处理完成")

            if self._should_wait():
                try:
                    input('\n按回车退出\n')
                except EOFError:
                    logger.info('没有终端输入，文件转录完成后直接退出')

        except Exception as e:
            logger.error(f"文件模式运行异常: {e}", exc_info=True)
            raise
        finally:
            if started_hotword and not self.isolated:
                self.app.hotword.stop()
            if own_ws is not None:
                await own_ws.close()
