"""把火山引擎端到端对话的 JSON 事件翻译成会话层的 ``SpeechEvent``。"""

from __future__ import annotations

import base64

from engineai_robotics_chat.dialog.events import SpeechEvent, ToolCall
from engineai_robotics_chat.providers.volcengine.events import (
    TYPE_ERROR,
    TYPE_RESPONSE_CANCELED,
    TYPE_RESPONSE_DONE,
    TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE,
    TYPE_RESPONSE_OUTPUT_AUDIO_DELTA,
    TYPE_RESPONSE_OUTPUT_AUDIO_DONE,
    TYPE_RESPONSE_OUTPUT_AUDIO_STARTED,
    TYPE_RESPONSE_OUTPUT_TEXT_DELTA,
    TYPE_RESPONSE_OUTPUT_TEXT_DONE,
    TYPE_SESSION_CLOSED,
    TYPE_TRANSCRIPTION_COMPLETED,
    TYPE_TRANSCRIPTION_FAILED,
    TYPE_TRANSCRIPTION_STARTED,
)


def _tool_name(item: dict) -> str:
    name = item.get("name") or (item.get("function") or {}).get("name")
    return "" if name is None else str(name)


def translate_event(event: dict) -> SpeechEvent:
    event_type = event.get("type")
    if event_type == TYPE_TRANSCRIPTION_STARTED:
        return SpeechEvent(kind="transcription_started", raw=event)
    if event_type == TYPE_TRANSCRIPTION_COMPLETED:
        text = (event.get("transcript") or event.get("text") or "").strip()
        return SpeechEvent(kind="transcript", text=text, raw=event)
    if event_type == TYPE_TRANSCRIPTION_FAILED:
        return SpeechEvent(kind="transcription_failed", error=event.get("error"), raw=event)
    if event_type == TYPE_RESPONSE_OUTPUT_TEXT_DELTA:
        return SpeechEvent(kind="text_delta", text=event.get("delta") or "", raw=event)
    if event_type == TYPE_RESPONSE_OUTPUT_TEXT_DONE:
        return SpeechEvent(kind="text_done", text=event.get("text") or "", raw=event)
    if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_STARTED:
        return SpeechEvent(kind="audio_started", raw=event)
    if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_DELTA:
        try:
            pcm = base64.b64decode(event.get("delta") or "")
        except Exception:
            return SpeechEvent(kind="ignore", raw=event)
        return SpeechEvent(kind="audio_delta", pcm=pcm, raw=event)
    if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_DONE:
        return SpeechEvent(kind="audio_done", raw=event)
    if event_type == TYPE_RESPONSE_CANCELED:
        return SpeechEvent(kind="response_canceled", raw=event)
    if event_type == TYPE_RESPONSE_DONE:
        return SpeechEvent(kind="response_done", raw=event)
    if event_type == TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
        items = event.get("items") or []
        if not items and event.get("call_id"):
            items = [event]
        calls = [
            ToolCall(
                call_id=str(item.get("call_id") or ""),
                name=_tool_name(item),
                arguments=item.get("arguments"),
            )
            for item in items
        ]
        return SpeechEvent(kind="tool_call", name=_tool_name(event), calls=calls, raw=event)
    if event_type == TYPE_SESSION_CLOSED:
        return SpeechEvent(kind="closed", raw=event)
    if event_type == TYPE_ERROR:
        return SpeechEvent(kind="error", error=event, raw=event)
    return SpeechEvent(kind="ignore", raw=event)
