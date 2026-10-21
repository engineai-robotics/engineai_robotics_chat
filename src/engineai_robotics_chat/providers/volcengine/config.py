"""火山引擎端到端对话连接配置。

密钥只从环境变量或仓库根目录 ``.env`` 读取。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engineai_robotics_chat.providers.volcengine.prompt import CHAT_INSTRUCTIONS

ENDPOINT_URL = "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
MODEL = "1.2.6.1"
SPEAKER = "zh_male_m191_uranus_bigtts"


def project_root() -> Path:
    """含 ``pyproject.toml`` 的仓库根。先看当前目录，再看本文件所在的源码树。"""

    starts = [Path.cwd(), Path(__file__).resolve()]
    seen: set[Path] = set()
    for start in starts:
        for parent in [start, *start.parents]:
            if parent in seen:
                continue
            seen.add(parent)
            if (parent / "pyproject.toml").is_file():
                return parent
    return Path.cwd()


def load_dotenv(path: Path | None = None) -> None:
    """Fill missing process env vars from a ``.env`` file. Existing vars win."""

    env_path = path or (project_root() / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class DialogConfig:
    """Fields consumed by ``RealtimeClient`` (``cfg.<name>``)."""

    api_key: str
    endpoint_url: str = ENDPOINT_URL
    model: str = MODEL
    speaker: str = SPEAKER
    hotwords: list[str] = field(default_factory=list)
    asr_format: str = "pcm"
    tts_format: str = "pcm_s16le"
    capture_sample_rate: int = 16000
    capture_channels: int = 1
    tts_sample_rate: int = 24000
    tts_channels: int = 1
    instructions: str = CHAT_INSTRUCTIONS
    tools: list[dict[str, Any]] = field(default_factory=list)
    location: dict[str, Any] = field(
        default_factory=lambda: {
            "longitude": 114.305556,
            "latitude": 22.62,
            "city": "深圳",
            "country": "中国",
            "province": "广东省",
            "district": "南山区",
            "town": "深圳",
            "country_code": "CN",
            "address": "中国深圳市南山区",
        }
    )


def load_config() -> DialogConfig:
    load_dotenv()
    api_key = os.environ.get("SEEDUPLEX_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "缺少火山引擎端到端对话的 API Key。请在项目根目录 .env 中设置 SEEDUPLEX_API_KEY，"
            "或导出同名环境变量。"
        )
    speaker = os.environ.get("SEEDUPLEX_SPEAKER", "").strip() or SPEAKER
    model = os.environ.get("SEEDUPLEX_MODEL", "").strip() or MODEL
    return DialogConfig(api_key=api_key, speaker=speaker, model=model)
