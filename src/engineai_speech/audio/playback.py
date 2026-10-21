"""24 kHz s16le 单声道播放。回调从缓冲取数据，欠载补静音。"""

from __future__ import annotations

import sys
import threading

import numpy as np
import sounddevice as sd

from engineai_speech.audio.frame import FRAME_MS


class PcmPlayer:
    def __init__(self, sample_rate: int, device: int | None):
        self.sample_rate = sample_rate
        self._buf = bytearray()
        self._played = bytearray()
        self._sync = threading.Lock()
        block = max(1, int(sample_rate * FRAME_MS / 1000))
        self._played_limit = max(block, int(sample_rate * 0.2)) * 2
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device,
            blocksize=block,
            callback=self._callback,
        )

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()
        self._stream.close()

    def write(self, pcm: bytes) -> None:
        if not pcm:
            return
        if len(pcm) % 2:
            pcm = pcm[:-1]
        with self._sync:
            self._buf.extend(pcm)

    def clear(self) -> None:
        with self._sync:
            self._buf.clear()

    def pending(self) -> int:
        with self._sync:
            return len(self._buf)

    def reference(self) -> bytes:
        """最近约 200 毫秒已经交给声卡的样本，给没有硬件回采的回声消除用。"""

        with self._sync:
            return bytes(self._played)

    def _callback(self, outdata, frames, _time, status) -> None:
        if status:
            print(f"\n[播放] {status}", file=sys.stderr)
        need = frames * 2
        with self._sync:
            got = bytes(self._buf[:need])
            del self._buf[:need]
            self._played.extend(got)
            extra = len(self._played) - self._played_limit
            if extra > 0:
                del self._played[:extra]
        if len(got) < need:
            got += b"\x00" * (need - len(got))
        outdata[:] = np.frombuffer(got, dtype=np.int16).reshape(-1, 1)
