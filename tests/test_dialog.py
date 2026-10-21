import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engineai_robotics_chat.dialog.events import SpeechEvent, ToolCall
from engineai_robotics_chat.dialog.session import DialogSession
from engineai_robotics_chat.dialog.tools import SpeechTool, query_from_arguments
from engineai_robotics_chat.providers.volcengine.events import (
    TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE,
    TYPE_RESPONSE_OUTPUT_AUDIO_DELTA,
    TYPE_TRANSCRIPTION_COMPLETED,
)
from engineai_robotics_chat.providers.volcengine.translate import translate_event


class FakeProvider:
    def __init__(self):
        self.sent = []
        self.muted = []
        self.results = []
        self.canceled = False

    async def send_audio(self, pcm):
        self.sent.append(pcm)

    async def mute(self):
        self.muted.append(True)

    async def unmute(self):
        self.muted.append(False)

    async def cancel_response(self):
        self.canceled = True

    async def submit_tool_result(self, call_id, text):
        self.results.append((call_id, text))


class FakePlayer:
    def __init__(self, pending=0):
        self.written = b""
        self.cleared = False
        self._pending = pending

    def write(self, pcm):
        self.written += pcm

    def clear(self):
        self.cleared = True
        self._pending = 0

    def pending(self):
        return self._pending


class EchoTool(SpeechTool):
    name = "retrieve"
    description = "search"
    parameters = {}

    async def run(self, arguments):
        return "passage"


class SessionTests(unittest.TestCase):
    def test_half_duplex_replaces_mic_with_silence(self):
        provider = FakeProvider()
        session = DialogSession(provider, FakePlayer(), duplex=False)
        asyncio.run(session.handle(SpeechEvent(kind="audio_started")))
        asyncio.run(session.send_pcm(b"\x01\x02\x03\x04"))
        self.assertEqual(provider.muted, [True])
        self.assertEqual(provider.sent, [b"\x00\x00\x00\x00"])

    def test_duplex_keeps_mic_and_cancels_on_barge_in(self):
        provider = FakeProvider()
        player = FakePlayer(pending=8)
        session = DialogSession(provider, player, duplex=True)
        asyncio.run(session.handle(SpeechEvent(kind="audio_started")))
        asyncio.run(session.handle(SpeechEvent(kind="transcription_started")))
        self.assertEqual(provider.muted, [])
        self.assertTrue(player.cleared)
        self.assertTrue(provider.canceled)

    def test_registered_tool_returns_text(self):
        provider = FakeProvider()
        session = DialogSession(provider, FakePlayer(), duplex=False, tools=[EchoTool()])
        event = SpeechEvent(kind="tool_call", calls=[ToolCall("call-1", "retrieve", {"query": "PM01"})])
        asyncio.run(session.handle(event))
        self.assertEqual(provider.results, [("call-1", "passage")])

    def test_unknown_tool_is_reported_back(self):
        provider = FakeProvider()
        session = DialogSession(provider, FakePlayer(), duplex=False, tools=[EchoTool()])
        event = SpeechEvent(kind="tool_call", calls=[ToolCall("call-2", "weather", {})])
        asyncio.run(session.handle(event))
        self.assertEqual(provider.results, [("call-2", "The weather tool is not registered.")])


class TranslateTests(unittest.TestCase):
    def test_transcript_and_audio(self):
        text = translate_event({"type": TYPE_TRANSCRIPTION_COMPLETED, "transcript": " 你好 "})
        self.assertEqual(text.kind, "transcript")
        self.assertEqual(text.text, "你好")
        audio = translate_event({"type": TYPE_RESPONSE_OUTPUT_AUDIO_DELTA, "delta": "AQID"})
        self.assertEqual(audio.kind, "audio_delta")
        self.assertEqual(audio.pcm, b"\x01\x02\x03")

    def test_tool_call_items(self):
        event = translate_event(
            {
                "type": TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE,
                "items": [{"call_id": "c", "name": "retrieve", "arguments": "{\"query\": \"T800\"}"}],
            }
        )
        self.assertEqual(event.kind, "tool_call")
        self.assertEqual(event.calls[0].call_id, "c")
        self.assertEqual(event.calls[0].name, "retrieve")
        self.assertEqual(query_from_arguments(event.calls[0].arguments), "T800")


if __name__ == "__main__":
    unittest.main()
