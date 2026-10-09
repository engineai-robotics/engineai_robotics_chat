"""豆包端到端实时语音对话客户端。"""

from doubao_dialog.config import DialogConfig, load_config
from doubao_dialog.realtime import RealtimeClient

__all__ = ["DialogConfig", "RealtimeClient", "load_config"]
