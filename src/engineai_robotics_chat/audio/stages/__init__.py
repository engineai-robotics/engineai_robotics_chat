"""音频处理阶段。输入一帧，输出一帧。

降噪、回声消除、波束成形放在这个包里。新算法实现 ``process``，再挂到
``AudioPipeline``。处理发生在混成单声道之前，因此仍能看到多路麦克风和扬声器参考。
"""

from __future__ import annotations

from engineai_robotics_chat.audio.frame import AudioFrame


class AudioStage:
    def process(self, frame: AudioFrame) -> AudioFrame:
        return frame
