"""把声卡回调里的多声道块放进异步队列。混音留到流水线。"""

from __future__ import annotations

import asyncio
import sys

import numpy as np
import sounddevice as sd

from engineai_robotics_chat.audio.frame import FRAME_MS, frame_from_input, mix_to_mono


def open_mic(
    sample_rate: int,
    device: int | None,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    channels: int,
    mic_channels: list[int],
    ref_channels: list[int],
):
    block = max(1, int(sample_rate * FRAME_MS / 1000))
    level = {"peak": 0}

    def callback(indata, _frames, _time, status) -> None:
        if status:
            print(f"\n[采集] {status}", file=sys.stderr)
        frame = frame_from_input(indata, sample_rate, mic_channels, ref_channels)
        samples = np.frombuffer(mix_to_mono(frame), dtype=np.int16)
        if samples.size:
            peak = int(np.max(np.abs(samples)))
            if peak > level["peak"]:
                level["peak"] = peak

        def _enqueue() -> None:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(frame)

        loop.call_soon_threadsafe(_enqueue)

    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype="int16",
        device=device,
        blocksize=block,
        callback=callback,
    )
    stream.start()
    return stream, level
