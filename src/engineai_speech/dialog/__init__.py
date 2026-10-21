"""对话会话：半双工、工具调用，以及麦克风示例的接线。"""

from engineai_speech.dialog.events import SpeechEvent, ToolCall
from engineai_speech.dialog.session import DialogSession
from engineai_speech.dialog.tools import SpeechTool, query_from_arguments, tool_schemas

__all__ = [
    "DialogSession",
    "SpeechEvent",
    "SpeechTool",
    "ToolCall",
    "query_from_arguments",
    "tool_schemas",
]
