# coding: utf-8
import numpy as np

from ..base import RecognitionStream


class WaveformStream(RecognitionStream):
    def __init__(self, sample_rate=16000):
        super().__init__(sample_rate)
        self.audio_data = None

    def accept_waveform(self, sample_rate, audio):
        self.sample_rate = sample_rate
        self.audio_data = np.asarray(audio, dtype=np.float32)
