"""火山引擎端到端对话 WebSocket 客户端。"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import uuid
from typing import Any, Dict, List, Tuple

import websockets

from engineai_robotics_chat.providers.volcengine.events import (
    TYPE_CONVERSATION_ITEM_CREATE,
    TYPE_ERROR,
    TYPE_INPUT_AUDIO_BUFFER_APPEND,
    TYPE_INPUT_AUDIO_BUFFER_COMMIT,
    TYPE_INPUT_AUDIO_MUTE,
    TYPE_INPUT_AUDIO_UNMUTE,
    TYPE_RESPONSE_CANCEL,
    TYPE_SESSION_CLOSE,
    TYPE_SESSION_CLOSED,
    TYPE_SESSION_CREATE,
    TYPE_SESSION_CREATED,
    TYPE_SESSION_UPDATE,
    TYPE_SESSION_UPDATED,
    TYPE_SPEECH_TEXT_BUFFER_APPEND,
    TYPE_SPEECH_TEXT_BUFFER_COMMIT,
)

_CONNECT_HEADER_KWARG = (
    "additional_headers"
    if "additional_headers" in inspect.signature(websockets.connect).parameters
    else "extra_headers"
)


class RealtimeClient:
    """Volcengine end-to-end dialogue connection and JSON-event protocol client."""

    def __init__(self, cfg: Any):
        self.cfg = cfg
        self.ws: Any = None
        self.session_id = str(uuid.uuid4())
        self.dialog_id = ""
        self.turn_event_id = ""
        self._write_lock = asyncio.Lock()
        self._event_seq = 0

    def set_turn_event_id(self, event_id: str) -> None:
        self.turn_event_id = str(event_id or "")
        self._event_seq = 0

    def new_event_id(self) -> str:
        if self.turn_event_id:
            self._event_seq += 1
            return f"{self.turn_event_id}_{self._event_seq}"
        return f"event_{uuid.uuid4().hex}"

    async def connect(self) -> None:
        self.session_id = str(uuid.uuid4())
        self.dialog_id = ""
        headers = {"X-Api-Key": self.cfg.api_key}
        self.ws = await websockets.connect(
            self.cfg.endpoint_url,
            ping_interval=None,
            max_size=None,
            open_timeout=10,
            **{_CONNECT_HEADER_KWARG: headers},
        )

    async def close(self) -> None:
        if self.ws is None:
            return
        try:
            await self.session_close()
            await self._wait_session_closed()
        except Exception:
            pass
        await self.ws.close()
        self.ws = None

    async def disconnect(self) -> None:
        """Drop only the transport, preserving the server-side dialog."""

        ws, self.ws = self.ws, None
        if ws is not None:
            await ws.close()

    async def _wait_session_closed(self, timeout: float = 3.0) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return
            try:
                event = await asyncio.wait_for(self.recv_event(), timeout=remaining)
            except (asyncio.TimeoutError, Exception):
                return
            if event.get("type") == TYPE_SESSION_CLOSED:
                return

    async def send_event(self, event: Dict[str, Any]) -> None:
        if self.ws is None:
            raise RuntimeError("websocket is not connected")
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        async with self._write_lock:
            await self.ws.send(payload)

    async def recv_event(self) -> Dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("websocket is not connected")
        frame = await self.ws.recv()
        if isinstance(frame, bytes):
            frame = frame.decode("utf-8")
        event = json.loads(frame)
        return event

    def build_session_config(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        session = {
            "id": self.session_id,
            "model": self.cfg.model,
            "instructions": self.cfg.instructions,
            "audio": {
                "input": {
                    "format": {
                        "type": self.cfg.asr_format,
                        "rate": self.cfg.capture_sample_rate,
                    }
                },
                "output": {
                    "format": {
                        "type": self.cfg.tts_format,
                        "rate": self.cfg.tts_sample_rate,
                    },
                    "voice": self.cfg.speaker,
                },
            },
            "tools": list(getattr(self.cfg, "tools", None) or []),
        }
        dialog_extra: Dict[str, Any] = {
            "audit_response": (
                "Sorry, I can't answer this question. You can change to another topic."
                "I will do my best to assist you."
            ),
            "enable_loudness_norm": True,
            "enable_music": False,
            "enable_volc_websearch": bool(
                getattr(self.cfg, "enable_volc_websearch", False)
            ),
        }
        asr_extra: Dict[str, Any] = {
            "input_mod": "keep_alive",
            "context": {
                "hotwords": [{"word": word} for word in (self.cfg.hotwords or [])]
            },
        }
        extension = {
            "asr": {"extra": asr_extra},
            "tts": {"extra": {}},
            "dialog": {
                "location": self.cfg.location,
                "extra": dialog_extra,
            },
        }
        return session, extension

    async def session_create(self) -> None:
        session, extension = self.build_session_config()
        await self.send_event(
            {
                "type": TYPE_SESSION_CREATE,
                "event_id": self.new_event_id(),
                "session": session,
                "extension": extension,
            }
        )
        while True:
            event = await self.recv_event()
            event_type = event.get("type")
            if event_type == TYPE_SESSION_CREATED:
                self.dialog_id = event.get("session", {}).get("id", "")
                return
            if event_type == TYPE_ERROR:
                raise RuntimeError(f"session.create error: {event}")

    async def session_resume_history(self, dialog_id: str) -> None:
        """Bind an active newly-created session to prior dialog history."""

        session, extension = self.build_session_config()
        session["id"] = dialog_id
        await self.send_event(
            {
                "type": TYPE_SESSION_UPDATE,
                "event_id": self.new_event_id(),
                "session": session,
                "extension": extension,
            }
        )
        while True:
            event = await self.recv_event()
            event_type = event.get("type")
            if event_type == TYPE_SESSION_UPDATED:
                self.dialog_id = event.get("session", {}).get("id") or dialog_id
                return
            if event_type == TYPE_ERROR:
                raise RuntimeError(f"session.update error: {event}")

    async def session_close(self) -> None:
        await self.send_event(
            {
                "type": TYPE_SESSION_CLOSE,
                "event_id": self.new_event_id(),
            }
        )

    async def input_audio_append(self, data: bytes) -> None:
        await self.send_event(
            {
                "type": TYPE_INPUT_AUDIO_BUFFER_APPEND,
                "event_id": self.new_event_id(),
                "audio": base64.b64encode(data).decode("ascii"),
            }
        )

    async def input_audio_commit(self) -> None:
        await self.send_event(
            {
                "type": TYPE_INPUT_AUDIO_BUFFER_COMMIT,
                "event_id": self.new_event_id(),
            }
        )

    async def input_audio_mute(self) -> None:
        await self.send_event(
            {
                "type": TYPE_INPUT_AUDIO_MUTE,
                "event_id": self.new_event_id(),
            }
        )

    async def input_audio_unmute(self) -> None:
        await self.send_event(
            {
                "type": TYPE_INPUT_AUDIO_UNMUTE,
                "event_id": self.new_event_id(),
            }
        )

    async def response_cancel(self) -> None:
        """Cancel the in-flight response. Server acks with ``response.canceled``."""

        await self.send_event(
            {
                "type": TYPE_RESPONSE_CANCEL,
                "event_id": self.new_event_id(),
            }
        )

    async def speech_text_append(self, speech_id: str, text: str) -> None:
        await self.send_event(
            {
                "type": TYPE_SPEECH_TEXT_BUFFER_APPEND,
                "event_id": self.new_event_id(),
                "speech_id": speech_id,
                "text": text,
            }
        )

    async def speech_text_commit(self, speech_id: str, text: str) -> None:
        await self.send_event(
            {
                "type": TYPE_SPEECH_TEXT_BUFFER_COMMIT,
                "event_id": self.new_event_id(),
                "speech_id": speech_id,
                "text": text,
            }
        )

    async def say(self, text: str) -> None:
        """Speak text with the current session voice."""

        text = (text or "").strip()
        if not text:
            return
        speech_id = str(uuid.uuid4())
        cut = max(1, len(text) // 2)
        await self.speech_text_append(speech_id, text[:cut])
        await self.speech_text_commit(speech_id, text[cut:])

    async def conversation_item_create(self, items: List[Dict[str, Any]]) -> None:
        await self.send_event(
            {
                "type": TYPE_CONVERSATION_ITEM_CREATE,
                "event_id": self.new_event_id(),
                "items": items,
            }
        )

    async def send_tool_result(self, call_id: str, text: str) -> None:
        await self.conversation_item_create(
            [
                {
                    "type": "message",
                    "role": "tool",
                    "call_id": call_id,
                    "content": [{"type": "input_text", "text": text}],
                }
            ]
        )
