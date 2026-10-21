"""音频检测器。输入一帧，输出零个或多个事件。

唤醒、语音活动检测放在这个包里。需要在唤醒前拦住上行语音时，把
``gates_uplink`` 设为 True。流水线在收到 ``wake`` 之前改送静音，收到
``sleep`` 后再拦住。
"""

from __future__ import annotations

from engineai_robotics_chat.audio.frame import AudioEvent, AudioFrame


class AudioDetector:
    gates_uplink = False

    def process(self, frame: AudioFrame) -> list[AudioEvent]:
        return []
