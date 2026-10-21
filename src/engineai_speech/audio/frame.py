"""一帧麦克风音频。处理阶段看到的是混成单声道之前的多声道。"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

FRAME_MS = 20


@dataclass
class AudioFrame:
    """交错存放的 16 位小端 PCM。

    ``mic_channels`` 是要合成上行语音的声道下标。为空表示全部声道都是麦克风。
    ``reference`` 是扬声器回采，供回声消除使用，不会被混进上行语音。
    """

    pcm: bytes
    sample_rate: int
    channels: int
    mic_channels: tuple[int, ...] = ()
    reference: bytes = b""
    reference_channels: int = 0
    timestamp: float = 0.0


@dataclass
class AudioEvent:
    """前端检测事件。``kind`` 使用 wake、sleep、speech_start、speech_end。"""

    kind: str
    name: str = ""


def frame_from_input(
    indata: np.ndarray,
    sample_rate: int,
    mic_channels: list[int],
    ref_channels: list[int],
) -> AudioFrame:
    """从声卡回调的 ``(frames, channels)`` int16 数组复制出一帧。"""

    channels = int(indata.shape[1]) if indata.ndim == 2 else 1
    pcm = np.ascontiguousarray(indata).tobytes()
    reference = b""
    if ref_channels:
        reference = np.ascontiguousarray(indata[:, ref_channels]).tobytes()
    return AudioFrame(
        pcm=pcm,
        sample_rate=sample_rate,
        channels=channels,
        mic_channels=tuple(mic_channels),
        reference=reference,
        reference_channels=len(ref_channels),
        timestamp=time.monotonic(),
    )


def mix_to_mono(frame: AudioFrame) -> bytes:
    """把麦克风声道平均成单声道。扬声器参考不参与平均。"""

    if frame.channels <= 1:
        return frame.pcm
    samples = np.frombuffer(frame.pcm, dtype=np.int16)
    width = frame.channels
    usable = samples.size - (samples.size % width)
    if usable <= 0:
        return b""
    data = samples[:usable].reshape(-1, width)
    pick = [ch for ch in frame.mic_channels if 0 <= ch < width]
    if not pick:
        pick = list(range(width))
    mono = np.clip(data[:, pick].astype(np.float32).mean(axis=1), -32768, 32767).astype(np.int16)
    return mono.tobytes()
