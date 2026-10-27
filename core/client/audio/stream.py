# coding: utf-8
"""
音频流管理模块

提供 AudioStreamManager 类用于管理音频输入流，包括流的创建、
启动、停止和设备检测。
"""

from __future__ import annotations

import sys
import time
import threading
from typing import TYPE_CHECKING, Optional

import numpy as np
import sounddevice as sd

from core.client.state import console
from . import logger

if TYPE_CHECKING:
    from core.client.state import ClientState
    from ..app import CapsWriterClient



FALLBACK_OPEN_TIMEOUT = 2.0


def _seconds(timeout) -> str:
    number = float(timeout)
    if number.is_integer():
        return str(int(number))
    return f'{number:.1f}'


def input_index_from_default(default_device):
    """从 sounddevice 的默认设备对里取出输入编号。

    `default.device` 是 `_InputOutputPair`，不是 list 或 tuple。
    """
    if default_device is None or isinstance(default_device, (str, bytes, int, float)):
        value = default_device
    else:
        try:
            value = default_device[0]
        except (TypeError, KeyError, IndexError):
            value = default_device
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def list_input_devices(devices):
    """只保留有输入声道的设备，返回 (编号, 名称, 声道数)。"""
    found = []
    if not devices:
        return found
    for index, info in enumerate(devices):
        try:
            channels = int(info['max_input_channels'])
            name = info['name']
        except (KeyError, TypeError, ValueError):
            continue
        if channels <= 0:
            continue
        found.append((index, str(name), channels))
    return found


def format_input_devices(inputs) -> str:
    if not inputs:
        return '无'
    return '，'.join(
        f'{index} {name}（{channels} 声道）' for index, name, channels in inputs
    )


_VIRTUAL_INPUT_MARKERS = (
    'virtual',
    'blackhole',
    'soundflower',
    'loopback',
    'teams audio',
    'zoom',
    'aggregate',
    'cable',
)


def input_looks_virtual(name) -> bool:
    folded = str(name).casefold()
    return any(marker in folded for marker in _VIRTUAL_INPUT_MARKERS)


def virtual_input_warning(chosen_name, inputs) -> str:
    """选中的是虚拟声卡时，说明它不会录到人声。"""
    physical = [item for item in inputs if not input_looks_virtual(item[1])]
    if not physical:
        return (
            f'{chosen_name} 不是麦克风。可用输入里没有麦克风，'
            '录进去的是静音，识别结果会是空的。'
            '请接上麦克风，或到系统设置 > 声音更换输入。'
        )
    names = '，'.join(f'{index} {name}' for index, name, _channels in physical)
    return (
        f'正在使用 {chosen_name}，这不是麦克风。'
        f'麦克风 {names} 没有打开。'
        '请到系统设置 > 声音更换输入。'
    )


def darwin_input_failure_message(default_index, inputs, timeout) -> str:
    """设备还在时，不要把默认输入 -1 说成没有麦克风权限。"""
    listing = format_input_devices(inputs)
    if not inputs:
        return '没有麦克风权限，或没有可用的输入设备。请到系统设置 > 隐私与安全性 > 麦克风打开权限。'
    if default_index == -1:
        return (
            f'默认输入设备编号是 -1。可用输入：{listing}。'
            f'这些设备在 {_seconds(timeout)} 秒内都没有打开。'
            '请到系统设置 > 声音，把输入改成真实麦克风。'
        )
    return (
        f'默认输入打不开（编号 {default_index}）。可用输入：{listing}。'
        '如果系统拒绝了麦克风，请到系统设置 > 隐私与安全性 > 麦克风允许当前终端。'
    )


def open_with_timeout(open_device, index, channels, timeout):
    """打开设备。超时后放弃，避免虚拟声卡把客户端卡住。"""
    holder = {}
    errors = {}
    cancelled = threading.Event()
    lock = threading.Lock()

    def run():
        try:
            stream = open_device(index, channels)
        except Exception as exc:
            errors['exc'] = exc
            return
        with lock:
            abandon = cancelled.is_set()
            if not abandon:
                holder['stream'] = stream
        if abandon:
            closer = getattr(stream, 'close', None)
            if callable(closer):
                try:
                    closer()
                except Exception:
                    pass

    worker = threading.Thread(target=run, name=f'mic-open-{index}', daemon=True)
    worker.start()
    worker.join(timeout)
    with lock:
        if worker.is_alive() or 'stream' not in holder:
            cancelled.set()
            stream = None
        else:
            stream = holder['stream']
    if stream is not None:
        return stream, None
    if 'exc' in errors:
        return None, errors['exc']
    return None, 'timeout'


def select_fallback_input(devices, open_device, timeout=FALLBACK_OPEN_TIMEOUT):
    """按编号尝试输入设备。返回 (流, 编号, 名称, 声道) 或 None，以及每次尝试。"""
    chosen = None
    attempts = []
    for index, name, channels in list_input_devices(devices):
        stream, problem = open_with_timeout(open_device, index, channels, timeout)
        attempts.append((index, name, problem))
        if problem == 'timeout':
            logger.warning(f'打开输入设备 {index} {name} 超过 {_seconds(timeout)} 秒，跳过')
        elif problem is not None:
            logger.warning(f'打开输入设备 {index} {name} 失败: {problem}')
        if stream is not None:
            chosen = (stream, index, name, min(2, channels))
            break
    return chosen, attempts


class AudioStreamManager:
    """
    音频流管理器

    负责管理音频输入流的生命周期，包括：
    - 检测和选择音频设备
    - 创建和启动音频流
    - 处理音频数据回调
    - 流的重启和关闭

    Attributes:
        state: 客户端状态实例
        sample_rate: 采样率（默认 48000Hz）
        block_duration: 每个数据块的时长（秒，默认 0.05s）
    """

    SAMPLE_RATE = 48000
    BLOCK_DURATION = 0.05  # 50ms

    def __init__(self, app: CapsWriterClient):
        """
        初始化音频流管理器

        Args:
            app: 客户端 App 实例
        """
        self.app = app
        self._channels = 1
        self._running = False  # 标志是否应该运行

    @property
    def state(self) -> ClientState:
        """快捷访问状态单例"""
        return self.app.state

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info,
        status: sd.CallbackFlags
    ) -> None:
        """
        音频数据回调函数

        当音频流接收到新数据时调用，将数据放入异步队列中。
        """
        # 只在录音状态时处理数据
        if not self.state.recording:
            return

        import asyncio

        # 将数据放入队列
        if self.app.loop and self.state.queue_in:
            asyncio.run_coroutine_threadsafe(
                self.state.queue_in.put({
                    'type': 'data',
                    'time': time.time(),
                    'data': indata.copy(),
                }),
                self.app.loop
            )

    def _on_stream_finished(self) -> None:
        """音频流结束回调"""
        if not threading.main_thread().is_alive():
            return
        if not self._running:
            return

        logger.info("音频流意外结束，正在尝试重启...")
        self.reopen()

    def start(self) -> Optional[sd.InputStream]:
        """
        启动音频流

        Returns:
            创建的音频输入流，如果失败返回 None
        """
        if self._running:
            logger.debug("音频流已在运行，跳过启动")
            return self.state.stream

        try:
            device = sd.query_devices(kind='input')
        except UnicodeDecodeError:
            logger.warning("无法获取音频设备名称（编码问题）")
            return self._open_started_stream(None, self._channels)
        except sd.PortAudioError as exc:
            if sys.platform == 'darwin':
                logger.warning(f"默认输入设备打不开: {exc}")
                return self._start_darwin_fallback()
            logger.error("未找到麦克风设备")
            input('按回车键退出')
            sys.exit(1)

        self._channels = min(2, int(device['max_input_channels']))
        device_name = device.get('name', '未知设备')
        console.print(
            f'使用默认音频设备：[italic]{device_name}，声道数：{self._channels}',
            end='\n\n'
        )
        logger.info(f"找到音频设备: {device_name}, 声道数: {self._channels}")
        return self._open_started_stream(None, self._channels)

    def _start_darwin_fallback(self) -> Optional[sd.InputStream]:
        """默认输入打不开时，列出有输入声道的设备，并限时逐个打开。"""
        try:
            default_device = sd.default.device
        except Exception as exc:
            logger.warning(f"读不到默认输入设备: {exc}")
            default_device = None
        default_index = input_index_from_default(default_device)
        try:
            devices = sd.query_devices()
        except (sd.PortAudioError, UnicodeDecodeError) as exc:
            logger.error(f"无法列出音频设备: {exc}")
            devices = []

        inputs = list_input_devices(devices)
        listing = format_input_devices(inputs)
        if default_index == -1:
            logger.warning(f"默认输入设备编号是 -1。可用输入：{listing}")
        else:
            logger.warning(f"默认输入不可用（编号 {default_index}）。可用输入：{listing}")
        if not inputs:
            _darwin_mic_denied(
                darwin_input_failure_message(default_index, inputs, FALLBACK_OPEN_TIMEOUT)
            )
            return None

        def open_device(index, channels):
            return self._build_stream(index, min(2, channels))

        chosen, _attempts = select_fallback_input(
            devices, open_device, FALLBACK_OPEN_TIMEOUT
        )
        if chosen is None:
            _darwin_mic_denied(
                darwin_input_failure_message(default_index, inputs, FALLBACK_OPEN_TIMEOUT)
            )
            return None

        stream, index, name, channels = chosen
        self._channels = channels
        self.state.stream = stream
        self._running = True
        logger.info(f"默认输入不可用，改用输入设备 {index} {name}，声道数 {channels}")
        console.print(
            f'使用音频设备：[italic]{name}，声道数：{channels}',
            end='\n\n'
        )
        if input_looks_virtual(name):
            warning = virtual_input_warning(name, inputs)
            logger.warning(warning)
            console.print(f'[yellow]{warning}[/yellow]\n')
        logger.debug(
            f"音频流已启动: 采样率={self.SAMPLE_RATE}, "
            f"块大小={int(self.BLOCK_DURATION * self.SAMPLE_RATE)}, 设备={index}"
        )
        return stream

    def _build_stream(self, device, channels) -> sd.InputStream:
        stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            blocksize=int(self.BLOCK_DURATION * self.SAMPLE_RATE),
            device=device,
            dtype="float32",
            channels=channels,
            callback=self._audio_callback,
            finished_callback=self._on_stream_finished,
        )
        stream.start()
        return stream

    def _open_started_stream(self, device, channels) -> Optional[sd.InputStream]:
        try:
            stream = self._build_stream(device, channels)
        except sd.PortAudioError as e:
            logger.error(f"创建音频流失败: {e}", exc_info=True)
            if sys.platform == 'darwin':
                _darwin_mic_denied("没有麦克风权限，或麦克风被占用。请到系统设置 > 隐私与安全性 > 麦克风，允许当前终端。")
                return None
            if '-9999' in str(e):
                console.print("""
[bold red]检测到麦克风被占用或权限异常（错误码 -9999）[/bold red]
请尝试以下解决方案：

  1. 设置 > 隐私和安全性 > 麦克风，将「允许桌面应用访问麦克风」打开
  2. 状态栏右下角音量图标 > 右键菜单 > 声音 > 麦克风的属性，关闭「允许应用程序独占控制该设备」
  3. 状态栏右下角音量图标 > 右键菜单 > 声音 > 麦克风的属性，关闭「增强效果」
""")
            return None
        except Exception as e:
            logger.error(f"创建音频流失败: {e}", exc_info=True)
            return None

        self.state.stream = stream
        self._running = True
        logger.debug(
            f"音频流已启动: 采样率={self.SAMPLE_RATE}, "
            f"块大小={int(self.BLOCK_DURATION * self.SAMPLE_RATE)}"
        )
        return stream

    def stop(self) -> None:
        """停止音频流"""
        if not self._running:
            return

        self._running = False  # 标记为停止
        if self.state.stream is not None:
            try:
                self.state.stream.close()
                logger.debug("音频流已停止")
            except Exception as e:
                logger.debug(f"停止音频流时发生错误: {e}")
            finally:
                self.state.stream = None

    def reopen(self) -> Optional[sd.InputStream]:
        """
        重新启动音频流

        Returns:
            新创建的音频输入流
        """
        logger.info("正在重启音频流...")

        # 停止旧流
        self.stop()

        # 重载 PortAudio，更新设备列表
        try:
            sd._terminate()
            sd._ffi.dlclose(sd._lib)
            sd._lib = sd._ffi.dlopen(sd._libname)
            sd._initialize()
        except Exception as e:
            logger.warning(f"重载 PortAudio 时发生警告: {e}")

        # 等待设备稳定
        time.sleep(0.1)

        # 启动新流
        return self.start()


def _darwin_mic_denied(message: str) -> None:
    logger.error(message)
    console.print(f'[bold red]{message}[/bold red]')
    try:
        from core.ui.toast import toast
        toast(message, duration=8000)
    except Exception:
        pass
