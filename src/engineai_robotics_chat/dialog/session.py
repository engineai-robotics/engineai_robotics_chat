"""半双工会话：播报时改送静音，全双工时允许打断。"""

from __future__ import annotations

import asyncio
import sys

from engineai_robotics_chat.dialog.events import SpeechEvent
from engineai_robotics_chat.dialog.tools import SpeechTool


class DialogSession:
    def __init__(self, provider, player, duplex: bool, tools: list[SpeechTool] | None = None):
        self.provider = provider
        self.player = player
        self.duplex = duplex
        self.drop_mic = False
        self._assistant_open = False
        self._unmute_task: asyncio.Task | None = None
        self._tools = {tool.name: tool for tool in (tools or [])}

    async def send_pcm(self, pcm: bytes) -> None:
        # 播报时改送静音，而不是停发。服务端靠连续上行保活，
        # 中间断流会超时，之后再说话也不会有回复。
        if self.drop_mic:
            pcm = bytes(len(pcm))
        await self.provider.send_audio(pcm)

    async def handle(self, event: SpeechEvent) -> bool:
        """返回 True 表示会话应结束。"""

        if event.kind == "transcription_started":
            if self.duplex and self.player.pending():
                self.player.clear()
                await self.provider.cancel_response()
            return False
        if event.kind == "transcript":
            text = event.text.strip()
            if text:
                if self._assistant_open:
                    print()
                    self._assistant_open = False
                print(f"\n你: {text}", flush=True)
            return False
        if event.kind == "transcription_failed":
            print("\n[识别失败]", event.error or event.raw, file=sys.stderr)
            return False
        if event.kind == "text_delta":
            if event.text:
                if not self._assistant_open:
                    print("助手: ", end="", flush=True)
                    self._assistant_open = True
                print(event.text, end="", flush=True)
            return False
        if event.kind == "text_done":
            if self._assistant_open:
                print(flush=True)
                self._assistant_open = False
            elif event.text.strip():
                print(f"助手: {event.text}", flush=True)
            return False
        if event.kind == "audio_started":
            await self._mute_input()
            return False
        if event.kind == "audio_delta":
            if event.pcm:
                self.player.write(event.pcm)
            return False
        if event.kind == "audio_done":
            self._schedule_unmute()
            return False
        if event.kind == "response_canceled":
            self.player.clear()
            await self._unmute_input()
            return False
        if event.kind == "response_done":
            self._schedule_unmute()
            return False
        if event.kind == "tool_call":
            await self._handle_tool(event)
            return False
        if event.kind == "closed":
            return True
        if event.kind == "error":
            print(f"\n[服务端错误] {event.raw if event.raw is not None else event.error}", file=sys.stderr)
            return True
        return False

    async def _handle_tool(self, event: SpeechEvent) -> None:
        if not event.calls:
            if not self._tools:
                print(f"\n[模型请求了工具 {event.name}，本示例未注册工具]", file=sys.stderr)
            else:
                print("\n[检索] 函数调用没有 call_id", file=sys.stderr, flush=True)
            return
        for call in event.calls:
            tool = self._tools.get(call.name)
            if tool is None:
                if not self._tools:
                    print(f"\n[模型请求了工具 {call.name}，本示例未注册工具]", file=sys.stderr)
                    continue
                await self.provider.submit_tool_result(
                    call.call_id, f"The {call.name} tool is not registered."
                )
                continue
            text = await tool.run(call.arguments)
            await self.provider.submit_tool_result(call.call_id, text)

    async def _mute_input(self) -> None:
        if self.duplex or self.drop_mic:
            return
        self.drop_mic = True
        await self.provider.mute()

    async def _unmute_input(self) -> None:
        if self._unmute_task is not None and not self._unmute_task.done():
            self._unmute_task.cancel()
            self._unmute_task = None
        if not self.drop_mic:
            return
        self.drop_mic = False
        await self.provider.unmute()

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
