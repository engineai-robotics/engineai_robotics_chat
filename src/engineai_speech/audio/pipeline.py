"""采集之后、送入会话之前的音频流水线。

顺序是：处理阶段（降噪、回声消除、波束成形）改写帧，检测器（唤醒、语音活动）
只产出事件，最后才把麦克风声道混成单声道。没有唤醒检测器时，上行音频原样送出。
有唤醒检测器时，唤醒前改送同样长度的静音，避免已经连上的会话因为断流超时。
"""

from __future__ import annotations

from collections.abc import Callable

from engineai_speech.audio.frame import AudioEvent, AudioFrame, mix_to_mono


class AudioPipeline:
    def __init__(self, stages=None, detectors=None) -> None:
        self.stages = list(stages or [])
        self.detectors = list(detectors or [])
        self.gates_uplink = any(getattr(item, "gates_uplink", False) for item in self.detectors)
        self.awake = not self.gates_uplink
        self._reference_source: Callable[[], bytes] | None = None

    def set_reference_source(self, source: Callable[[], bytes] | None) -> None:
        """没有硬件回采时，用播放器最近播出的样本充当参考。"""

        self._reference_source = source

    def feed(self, frame: AudioFrame) -> tuple[bytes, list[AudioEvent]]:
        if not frame.reference and self._reference_source is not None:
            frame.reference = self._reference_source() or b""
            if frame.reference:
                frame.reference_channels = 1
        for stage in self.stages:
            frame = stage.process(frame)
        events: list[AudioEvent] = []
        for detector in self.detectors:
            events.extend(detector.process(frame) or [])
        for event in events:
            if event.kind == "wake":
                self.awake = True
            elif event.kind == "sleep":
                self.awake = False
        mono = mix_to_mono(frame)
        if self.gates_uplink and not self.awake:
            mono = bytes(len(mono))
        return mono, events
