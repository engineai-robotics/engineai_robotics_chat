"""会话层认识的事件。供应商负责把自己的协议翻译成这些事件。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: Any = None


@dataclass
class SpeechEvent:
    kind: str
    text: str = ""
    pcm: bytes = b""
    name: str = ""
    error: Any = None
    calls: list[ToolCall] = field(default_factory=list)
    raw: dict | None = None
