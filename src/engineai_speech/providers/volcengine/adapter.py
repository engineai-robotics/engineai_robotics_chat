"""火山引擎端到端对话。协议细节留在 ``RealtimeClient``。"""

from __future__ import annotations

from engineai_speech.dialog.events import SpeechEvent
from engineai_speech.providers.volcengine.client import RealtimeClient
from engineai_speech.providers.volcengine.config import DialogConfig
from engineai_speech.providers.volcengine.translate import translate_event


class VolcengineProvider:
    def __init__(self, cfg: DialogConfig):
        self.client = RealtimeClient(cfg)

    @property
    def dialog_id(self) -> str:
        return self.client.dialog_id

    async def connect(self) -> None:
        await self.client.connect()

    async def start_session(self) -> None:
        await self.client.session_create()

    async def send_audio(self, pcm: bytes) -> None:
        await self.client.input_audio_append(pcm)

    async def recv(self) -> SpeechEvent:
        return translate_event(await self.client.recv_event())

    async def mute(self) -> None:
        await self.client.input_audio_mute()

    async def unmute(self) -> None:
        await self.client.input_audio_unmute()

    async def cancel_response(self) -> None:
        await self.client.response_cancel()

    async def say(self, text: str) -> None:
        await self.client.say(text)

    async def submit_tool_result(self, call_id: str, text: str) -> None:
        await self.client.send_tool_result(call_id, text)

    async def close(self) -> None:
        await self.client.close()
