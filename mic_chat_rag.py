"""麦克风对话，站点事实走本地 BM25。

知识库默认是本目录 ``knowledge_text/knowledge_text.txt``。
豆包在 ``session.tools`` 里拿到 ``retrieve``。它发出函数调用后，
本脚本用 jieba + BM25Okapi 查原文片段，再按同一个 ``call_id`` 交回去，
由全双工模型把片段说出来。

用法::

    python mic_chat_rag.py
    python mic_chat_rag.py --knowledge knowledge_text/knowledge_text.txt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import sounddevice as sd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from doubao_dialog.bm25_rag import Bm25Retriever
from doubao_dialog.config import load_config
from doubao_dialog.event_types import TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE
from doubao_dialog.realtime import RealtimeClient
from mic_chat import (
    ChatSession,
    PcmPlayer,
    _warn_if_mic_silent,
    capture_layout,
    list_devices,
    open_mic,
    pick_input_device,
)

DEFAULT_KNOWLEDGE = ROOT / "knowledge_text" / "knowledge_text.txt"

RAG_INSTRUCTIONS = """
You are a spoken conversational assistant. The user talks to you through a microphone.
A local knowledge base covers the 众擎机器人零售旗舰店, 深圳市众擎机器人科技有限公司, and the products PM01 and T800.
Rules:
1. Reply in the user's language. Chinese input gets Chinese speech; English input gets English speech.
2. Keep replies short and spoken: usually one or two sentences. Give a longer answer only when the user asks for detail.
3. For any fact about the store, the company, products, prices, specs, battery life, or scenarios, call retrieve exactly once. Pass the user's question as query. Answer only from the returned passages.
4. If retrieve returns no matching passages, say you do not know. Do not invent prices, specs, or dates.
5. Greetings, your name, and small talk that need no store facts: answer directly and do not call retrieve.
6. Do not output stage directions. Do not mention APIs, BM25, retrieval, or tool names aloud.
""".strip()

RETRIEVE_TOOL = {
    "type": "function",
    "name": "retrieve",
    "description": (
        "Search the local site knowledge base once. Call this for questions about "
        "the 众擎 store, the company, PM01, or T800. Pass the user's question. "
        "Answer only from the returned passages."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The user's question for this turn.",
            }
        },
        "required": ["query"],
    },
}


class RagChatSession(ChatSession):
    def __init__(self, client: RealtimeClient, player: PcmPlayer, duplex: bool, retriever: Bm25Retriever):
        super().__init__(client, player, duplex)
        self.retriever = retriever

    async def handle_event(self, event: dict) -> bool:
        if event.get("type") == TYPE_RESPONSE_FUNCTION_CALL_ARGUMENTS_DONE:
            await self._handle_retrieve(event)
            return False
        return await super().handle_event(event)

    async def _handle_retrieve(self, event: dict) -> None:
        items = event.get("items") or []
        if not items and event.get("call_id"):
            items = [event]
        if not items:
            print("\n[检索] 函数调用没有 call_id", file=sys.stderr, flush=True)
            return
        for item in items:
            call_id = str(item.get("call_id") or "")
            name = str(item.get("name") or "")
            if name != "retrieve":
                await self.client.send_tool_result(
                    call_id, f"The {name} tool is not registered."
                )
                continue
            query = _query_from_arguments(item.get("arguments"))
            print(f"\n[检索] {query or '(空)'}", flush=True)
            if not query:
                await self.client.send_tool_result(call_id, "Empty query; nothing retrieved.")
                continue
            hits = await asyncio.to_thread(self.retriever.search, query)
            if not hits:
                print("[检索] 没有命中", flush=True)
                await self.client.send_tool_result(call_id, "No matching passages.")
                continue
            print(f"[检索] 命中 {len(hits)} 段", flush=True)
            await self.client.send_tool_result(call_id, "\n\n".join(hits))


def _query_from_arguments(raw) -> str:
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


def load_retriever(path: Path) -> Bm25Retriever:
    if not path.is_file():
        raise RuntimeError(f"找不到知识库文件: {path}")
    retriever = Bm25Retriever.from_text_file(path)
    print(f"知识库: {path}  {len(retriever.chunks)} 段", flush=True)
    return retriever


async def run(args: argparse.Namespace) -> None:
    retriever = load_retriever(args.knowledge)
    cfg = load_config()
    cfg.instructions = RAG_INSTRUCTIONS
    cfg.tools = [RETRIEVE_TOOL]
    cfg.hotwords = ["众擎", "PM01", "T800"]
    client = RealtimeClient(cfg)
    player = PcmPlayer(cfg.tts_sample_rate, args.output_device)
    chat = RagChatSession(client, player, duplex=args.duplex, retriever=retriever)
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
        print(f"模式: {mode}。问门店或产品时会先检索知识库。Ctrl+C 结束。", flush=True)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="麦克风对话，本地 BM25 知识库")
    parser.add_argument("--list-devices", action="store_true", help="列出声卡后退出")
    parser.add_argument("--input-device", type=int, default=None, help="输入设备编号")
    parser.add_argument("--output-device", type=int, default=None, help="输出设备编号")
    parser.add_argument(
        "--duplex",
        action="store_true",
        help="播报时继续上传麦克风（需要设备自带回声消除）",
    )
    parser.add_argument("--greet", action="store_true", help="连接后先播一句问候")
    parser.add_argument(
        "--knowledge",
        type=Path,
        default=DEFAULT_KNOWLEDGE,
        help="知识库文本，默认 knowledge_text/knowledge_text.txt",
    )
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
