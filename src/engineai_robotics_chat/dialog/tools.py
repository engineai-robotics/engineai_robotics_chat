"""对话工具。供应商只负责把调用交回来，执行在本地完成。"""

from __future__ import annotations

import json
from typing import Any


class SpeechTool:
    name: str
    description: str
    parameters: dict

    def schema(self) -> dict:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    async def run(self, arguments: Any) -> str:
        raise NotImplementedError


def tool_schemas(tools: list[SpeechTool]) -> list[dict]:
    return [tool.schema() for tool in tools]


def query_from_arguments(raw: Any) -> str:
    if isinstance(raw, dict):
        return str(raw.get("query") or "").strip()
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(data, dict):
        return str(data.get("query") or "").strip()
    return text
