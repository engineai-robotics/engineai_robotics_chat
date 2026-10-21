import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engineai_robotics_chat.audio.detectors import AudioDetector
from engineai_robotics_chat.audio.frame import AudioEvent, AudioFrame, frame_from_input, mix_to_mono
from engineai_robotics_chat.audio.pipeline import AudioPipeline
from engineai_robotics_chat.audio.stages import AudioStage


def _frame(values, mic_channels, ref_channels=()):
    data = np.asarray(values, dtype=np.int16)
    return frame_from_input(data, 16000, list(mic_channels), list(ref_channels))


class MixTests(unittest.TestCase):
    def test_mono_passthrough(self):
        frame = _frame([[100], [-200]], mic_channels=[0])
        self.assertEqual(mix_to_mono(frame), frame.pcm)

    def test_aiui_mix_ignores_loopback(self):
        # 一行 8 声道：0、1 静音，2–5 是麦，6–7 是回采。
        frame = _frame([[0, 0, 10, 20, 30, 40, 30000, -30000]], mic_channels=[2, 3, 4, 5], ref_channels=[6, 7])
        mono = np.frombuffer(mix_to_mono(frame), dtype=np.int16)
        self.assertEqual(mono.tolist(), [25])
        self.assertEqual(frame.reference_channels, 2)
        self.assertEqual(np.frombuffer(frame.reference, dtype=np.int16).tolist(), [30000, -30000])


class _Mark(AudioStage):
    def __init__(self):
        self.channels = 0
        self.reference = b""

    def process(self, frame):
        self.channels = frame.channels
        self.reference = frame.reference
        return frame


class _Wake(AudioDetector):
    gates_uplink = True

    def __init__(self):
        self.seen = 0

    def process(self, frame):
        self.seen += 1
        if self.seen == 2:
            return [AudioEvent(kind="wake", name="test")]
        return []


class PipelineTests(unittest.TestCase):
    def test_stage_sees_multichannel_and_hardware_reference(self):
        stage = _Mark()
        pipeline = AudioPipeline(stages=[stage])
        pipeline.set_reference_source(lambda: b"\x09\x00")
        frame = _frame([[0, 0, 10, 20, 30, 40, 30000, -30000]], [2, 3, 4, 5], [6, 7])
        uplink, events = pipeline.feed(frame)
        self.assertEqual(events, [])
        self.assertEqual(stage.channels, 8)
        self.assertEqual(stage.reference, frame.reference)
        self.assertEqual(np.frombuffer(uplink, dtype=np.int16).tolist(), [25])

    def test_player_reference_fills_empty_loopback(self):
        stage = _Mark()
        pipeline = AudioPipeline(stages=[stage])
        pipeline.set_reference_source(lambda: b"\x09\x00")
        frame = _frame([[100]], [0])
        pipeline.feed(frame)
        self.assertEqual(stage.reference, b"\x09\x00")

    def test_wake_gate_sends_silence_until_wake(self):
        pipeline = AudioPipeline(detectors=[_Wake()])
        frame = _frame([[100], [200]], [0])
        first, _ = pipeline.feed(frame)
        self.assertEqual(first, bytes(len(frame.pcm)))
        self.assertFalse(pipeline.awake)
        second, events = pipeline.feed(frame)
        self.assertEqual(events[0].kind, "wake")
        self.assertTrue(pipeline.awake)
        self.assertEqual(second, frame.pcm)


if __name__ == "__main__":
    unittest.main()
