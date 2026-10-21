"""把麦克风、流水线、会话和供应商接到一起。"""

from __future__ import annotations

import argparse
import asyncio
import sys

from engineai_speech.audio.capture import open_mic
from engineai_speech.audio.devices import (
    capture_layout,
    list_devices,
    output_device_name,
    pick_input_device,
)
from engineai_speech.audio.pipeline import AudioPipeline
from engineai_speech.dialog.session import DialogSession


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--list-devices", action="store_true", help="列出声卡后退出")
    parser.add_argument("--input-device", type=int, default=None, help="输入设备编号")
    parser.add_argument("--output-device", type=int, default=None, help="输出设备编号")
    parser.add_argument(
        "--duplex",
        action="store_true",
        help="播报时继续上传麦克风（需要设备自带回声消除）",
    )
    parser.add_argument("--greet", action="store_true", help="连接后先播一句问候")
    return parser


async def warn_if_mic_silent(level: dict) -> None:
    await asyncio.sleep(1.0)
    peak = int(level.get("peak") or 0)
    if peak <= 8:
        print(
            f"[收音] 开麦 1 秒内峰值只有 {peak}，上行几乎是静音。"
            "若用的是 AIUI-USB-MC，需要采集 8 声道并混音 2–5 路。",
            file=sys.stderr,
            flush=True,
        )


async def _pump(queue: asyncio.Queue, pipeline: AudioPipeline, session: DialogSession) -> None:
    while True:
        frame = await queue.get()
        pcm, _events = pipeline.feed(frame)
        await session.send_pcm(pcm)


async def run_microphone_dialog(
    provider,
    session: DialogSession,
    player,
    *,
    sample_rate: int,
    input_device: int | None,
    output_device: int | None,
    greet: bool,
    ready_message: str,
    pipeline: AudioPipeline | None = None,
    connecting_message: str = "正在连接…",
) -> None:
    pipeline = pipeline or AudioPipeline()
    pipeline.set_reference_source(player.reference)
    mic_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    loop = asyncio.get_running_loop()
    mic = None
    send_task = None
    try:
        print(connecting_message, flush=True)
        await provider.connect()
        await provider.start_session()
        print(f"会话已建立 dialog_id={provider.dialog_id}", flush=True)
        player.start()
        selected = pick_input_device(input_device)
        in_channels, mic_pick, ref_pick, in_name = capture_layout(selected)
        mic, mic_level = open_mic(
            sample_rate,
            selected,
            loop,
            mic_queue,
            in_channels,
            mic_pick,
            ref_pick,
        )
        mode = "全双工" if session.duplex else "半双工（播报时暂停收音）"
        print(f"输入设备: {in_name}  打开 {in_channels} 声道，使用 {mic_pick}", flush=True)
        print(f"输出设备: {output_device_name(output_device)}", flush=True)
        print(f"模式: {mode}。{ready_message}", flush=True)
        asyncio.create_task(warn_if_mic_silent(mic_level))
        if greet:
            await provider.say("你好，我在。")
        send_task = asyncio.create_task(_pump(mic_queue, pipeline, session))
        while True:
            event = await provider.recv()
            if await session.handle(event):
                break
    finally:
        if send_task is not None:
            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass
        if mic is not None:
            mic.stop()
            mic.close()
        try:
            player.stop()
        except Exception:
            pass
        await provider.close()
        print("\n已断开。", flush=True)


def run_until_interrupted(coro) -> None:
    try:
        asyncio.run(coro)
    except KeyboardInterrupt:
        print("\n已退出。", flush=True)


__all__ = [
    "build_parser",
    "list_devices",
    "run_microphone_dialog",
    "run_until_interrupted",
]
