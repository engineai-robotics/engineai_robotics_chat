"""麦克风收音，和豆包端到端实时语音对话。

默认半双工：助手播报时暂停上行麦克风，避免喇叭回声被当成下一句。
若是有回声消除时，可以加 ``--duplex``参数变成全双工对话。

用法：

    python mic_chat.py --list-devices
    python mic_chat.py
    python mic_chat.py --input-device 0 --output-device 6
    python mic_chat.py --duplex
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import sys
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from doubao_dialog.config import load_config
from doubao_dialog.event_types import (
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
from doubao_dialog.realtime import RealtimeClient

FRAME_MS = 20
# AIUI-USB-MC 硬件锁 8 声道 / 16 kHz。0、1 路几乎是静音，
# 2–5 是麦克风，6–7 是扬声器回采参考。
AIUI_MIC_CHANNELS = (2, 3, 4, 5)


class PcmPlayer:
    """24 kHz s16le 单声道播放。回调从缓冲取数据，欠载补静音。"""

    def __init__(self, sample_rate: int, device: int | None):
        self.sample_rate = sample_rate
        self._buf = bytearray()
        self._sync = threading.Lock()
        block = max(1, int(sample_rate * FRAME_MS / 1000))
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=device,
            blocksize=block,
            callback=self._callback,
        )

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()
        self._stream.close()

    def write(self, pcm: bytes) -> None:
        if not pcm:
            return
        if len(pcm) % 2:
            pcm = pcm[:-1]
        with self._sync:
            self._buf.extend(pcm)

    def clear(self) -> None:
        with self._sync:
            self._buf.clear()

    def pending(self) -> int:
        with self._sync:
            return len(self._buf)

    def _callback(self, outdata, frames, _time, status) -> None:
        if status:
            print(f"\n[播放] {status}", file=sys.stderr)
        need = frames * 2
        with self._sync:
            got = bytes(self._buf[:need])
            del self._buf[:need]
        if len(got) < need:
            got += b"\x00" * (need - len(got))
        outdata[:] = np.frombuffer(got, dtype=np.int16).reshape(-1, 1)


class ChatSession:
    def __init__(self, client: RealtimeClient, player: PcmPlayer, duplex: bool):
        self.client = client
        self.player = player
        self.duplex = duplex
        self.drop_mic = False
        self._assistant_open = False
        self._unmute_task: asyncio.Task | None = None

    async def send_mic(self, queue: asyncio.Queue) -> None:
        # 播报时改送静音，而不是停发。服务端靠连续上行保活，
        # 中间断流会超时，之后再说话也不会有回复。
        while True:
            pcm = await queue.get()
            if self.drop_mic:
                pcm = bytes(len(pcm))
            await self.client.input_audio_append(pcm)

    async def handle_event(self, event: dict) -> bool:
        """返回 True 表示会话应结束。"""

        event_type = event.get("type")
        if event_type == TYPE_TRANSCRIPTION_STARTED:
            if self.duplex and self.player.pending():
                self.player.clear()
                await self.client.response_cancel()
            return False
        if event_type == TYPE_TRANSCRIPTION_COMPLETED:
            text = (event.get("transcript") or event.get("text") or "").strip()
            if text:
                if self._assistant_open:
                    print()
                    self._assistant_open = False
                print(f"\n你: {text}", flush=True)
            return False
        if event_type == TYPE_TRANSCRIPTION_FAILED:
            print("\n[识别失败]", event.get("error") or event, file=sys.stderr)
            return False
        if event_type == TYPE_RESPONSE_OUTPUT_TEXT_DELTA:
            delta = event.get("delta") or ""
            if delta:
                if not self._assistant_open:
                    print("助手: ", end="", flush=True)
                    self._assistant_open = True
                print(delta, end="", flush=True)
            return False
        if event_type == TYPE_RESPONSE_OUTPUT_TEXT_DONE:
            if self._assistant_open:
                print(flush=True)
                self._assistant_open = False
            elif (event.get("text") or "").strip():
                print(f"助手: {event.get('text')}", flush=True)
            return False
        if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_STARTED:
            await self._mute_input()
            return False
        if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_DELTA:
            try:
                pcm = base64.b64decode(event.get("delta") or "")
            except Exception:
                return False
            self.player.write(pcm)
            return False
        if event_type == TYPE_RESPONSE_OUTPUT_AUDIO_DONE:
            self._schedule_unmute()
            return False
        if event_type == TYPE_RESPONSE_CANCELED:
            self.player.clear()
            await self._unmute_input()
            return False
        if event_type == TYPE_RESPONSE_DONE:
            self._schedule_unmute()
            return False
        if event_type == TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
            name = event.get("name") or event.get("function", {}).get("name")
            print(f"\n[模型请求了工具 {name}，本示例未注册工具]", file=sys.stderr)
            return False
        if event_type == TYPE_SESSION_CLOSED:
            return True
        if event_type == TYPE_ERROR:
            print(f"\n[服务端错误] {event}", file=sys.stderr)
            return True
        return False

    async def _mute_input(self) -> None:
        if self.duplex or self.drop_mic:
            return
        self.drop_mic = True
        await self.client.input_audio_mute()

    async def _unmute_input(self) -> None:
        if self._unmute_task is not None and not self._unmute_task.done():
            self._unmute_task.cancel()
            self._unmute_task = None
        if not self.drop_mic:
            return
        self.drop_mic = False
        await self.client.input_audio_unmute()

    def _schedule_unmute(self) -> None:
        if self.duplex or not self.drop_mic:
            return
        if self._unmute_task is not None and not self._unmute_task.done():
            return
        self._unmute_task = asyncio.create_task(self._unmute_after_playback())

    async def _unmute_after_playback(self) -> None:
        while self.player.pending() > 0:
            await asyncio.sleep(0.05)
        # 留一点尾巴，避免最后一帧还在声卡缓冲里就被麦克风采回去。
        await asyncio.sleep(0.15)
        await self._unmute_input()


def list_devices() -> None:
    print(sd.query_devices())
    default_in, default_out = sd.default.device
    print(f"默认输入={default_in}  默认输出={default_out}")


def pick_input_device(explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    for index, dev in enumerate(sd.query_devices()):
        name = str(dev["name"])
        if dev["max_input_channels"] > 0 and "AIUI" in name:
            return index
    return None


def capture_layout(device: int | None) -> tuple[int, list[int], str]:
    """返回 (打开声道数, 混音用的声道下标, 说明)。"""

    info = sd.query_devices(device, "input") if device is not None else sd.query_devices(kind="input")
    name = str(info["name"])
    max_in = int(info["max_input_channels"])
    if "AIUI" in name and max_in >= 6:
        pick = [ch for ch in AIUI_MIC_CHANNELS if ch < max_in]
        return max_in, pick, name
    return 1, [0], name


def _to_mono(indata: np.ndarray, pick: list[int]) -> bytes:
    if indata.shape[1] == 1:
        return indata.tobytes()
    picked = indata[:, pick].astype(np.float32)
    mono = np.clip(picked.mean(axis=1), -32768, 32767).astype(np.int16)
    return mono.tobytes()


def open_mic(
    sample_rate: int,
    device: int | None,
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue,
    channels: int,
    pick: list[int],
):
    block = max(1, int(sample_rate * FRAME_MS / 1000))
    level = {"peak": 0}

    def callback(indata, _frames, _time, status) -> None:
        if status:
            print(f"\n[采集] {status}", file=sys.stderr)
        pcm = _to_mono(indata, pick)
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size:
            peak = int(np.max(np.abs(samples)))
            if peak > level["peak"]:
                level["peak"] = peak

        def _enqueue() -> None:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(pcm)

        loop.call_soon_threadsafe(_enqueue)

    stream = sd.InputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype="int16",
        device=device,
        blocksize=block,
        callback=callback,
    )
    stream.start()
    return stream, level


async def run(args: argparse.Namespace) -> None:
    cfg = load_config()
    client = RealtimeClient(cfg)
    player = PcmPlayer(cfg.tts_sample_rate, args.output_device)
    chat = ChatSession(client, player, duplex=args.duplex)
    mic_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    loop = asyncio.get_running_loop()
    mic = None
    send_task = None
    try:
        print("正在连接豆包实时语音…", flush=True)
        await client.connect()
        await client.session_create()
        print(f"会话已建立 dialog_id={client.dialog_id}", flush=True)
        player.start()
        input_device = pick_input_device(args.input_device)
        in_channels, mic_pick, in_name = capture_layout(input_device)
        mic, mic_level = open_mic(
            cfg.capture_sample_rate,
            input_device,
            loop,
            mic_queue,
            in_channels,
            mic_pick,
        )
        out_name = (
            "默认"
            if args.output_device is None
            else sd.query_devices(args.output_device)["name"]
        )
        mode = "全双工" if args.duplex else "半双工（播报时暂停收音）"
        print(f"输入设备: {in_name}  打开 {in_channels} 声道，使用 {mic_pick}", flush=True)
        print(f"输出设备: {out_name}", flush=True)
        print(f"模式: {mode}。对着麦克风说话，Ctrl+C 结束。", flush=True)
        asyncio.create_task(_warn_if_mic_silent(mic_level))
        if args.greet:
            await client.say("你好，我在。")
        send_task = asyncio.create_task(chat.send_mic(mic_queue))
        while True:
            event = await client.recv_event()
            if await chat.handle_event(event):
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
        await client.close()
        print("\n已断开。", flush=True)


async def _warn_if_mic_silent(level: dict) -> None:
    await asyncio.sleep(1.0)
    peak = int(level.get("peak") or 0)
    if peak <= 8:
        print(
            f"[收音] 开麦 1 秒内峰值只有 {peak}，上行几乎是静音。"
            "若用的是 AIUI-USB-MC，需要采集 8 声道并混音 2–5 路。",
            file=sys.stderr,
            flush=True,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="麦克风与豆包实时语音对话")
    parser.add_argument("--list-devices", action="store_true", help="列出声卡后退出")
    parser.add_argument("--input-device", type=int, default=None, help="输入设备编号")
    parser.add_argument("--output-device", type=int, default=None, help="输出设备编号")
    parser.add_argument(
        "--duplex",
        action="store_true",
        help="播报时继续上传麦克风（需要设备自带回声消除）",
    )
    parser.add_argument("--greet", action="store_true", help="连接后先播一句问候")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_devices:
        list_devices()
        return
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n已退出。", flush=True)


if __name__ == "__main__":
    main()
