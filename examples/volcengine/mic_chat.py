"""麦克风收音，接入火山引擎端到端对话。

默认半双工：助手播报时暂停上行麦克风，避免喇叭回声被当成下一句。
若是有回声消除时，可以加 ``--duplex`` 参数变成全双工对话。

用法：

    python examples/volcengine/mic_chat.py --list-devices
    python examples/volcengine/mic_chat.py
    python examples/volcengine/mic_chat.py --input-device 0 --output-device 6
    python examples/volcengine/mic_chat.py --duplex
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from engineai_robotics_chat.audio.playback import PcmPlayer
from engineai_robotics_chat.dialog.microphone import (
    build_parser,
    list_devices,
    run_microphone_dialog,
    run_until_interrupted,
)
from engineai_robotics_chat.dialog.session import DialogSession
from engineai_robotics_chat.providers.volcengine.adapter import VolcengineProvider
from engineai_robotics_chat.providers.volcengine.config import load_config


async def run(args) -> None:
    cfg = load_config()
    provider = VolcengineProvider(cfg)
    player = PcmPlayer(cfg.tts_sample_rate, args.output_device)
    session = DialogSession(provider, player, duplex=args.duplex)
    await run_microphone_dialog(
        provider,
        session,
        player,
        sample_rate=cfg.capture_sample_rate,
        input_device=args.input_device,
        output_device=args.output_device,
        greet=args.greet,
        ready_message="对着麦克风说话，Ctrl+C 结束。",
        connecting_message="正在连接火山引擎端到端对话…",
    )


def main() -> None:
    args = build_parser("麦克风与火山引擎端到端对话").parse_args()
    if args.list_devices:
        list_devices()
        return
    run_until_interrupted(run(args))


if __name__ == "__main__":
    main()
