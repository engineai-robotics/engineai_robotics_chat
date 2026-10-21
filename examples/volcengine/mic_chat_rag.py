"""麦克风对话，站点事实走本地 BM25。

知识库默认是仓库里的 ``data/knowledge_text.txt``。
火山引擎端到端对话在 ``session.tools`` 里拿到 ``retrieve``。它发出函数调用后，
本脚本用 jieba + BM25Okapi 查原文片段，再按同一个 ``call_id`` 交回去，
由模型把片段说出来。

用法::

    python examples/volcengine/mic_chat_rag.py
    python examples/volcengine/mic_chat_rag.py --knowledge data/knowledge_text.txt
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from engineai_speech.audio.playback import PcmPlayer
from engineai_speech.dialog.microphone import (
    build_parser,
    list_devices,
    run_microphone_dialog,
    run_until_interrupted,
)
from engineai_speech.dialog.session import DialogSession
from engineai_speech.dialog.tools import SpeechTool, query_from_arguments, tool_schemas
from engineai_speech.knowledge.bm25 import Bm25Retriever
from engineai_speech.providers.volcengine.adapter import VolcengineProvider
from engineai_speech.providers.volcengine.config import load_config

DEFAULT_KNOWLEDGE = ROOT / "data" / "knowledge_text.txt"

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


class RetrieveTool(SpeechTool):
    name = "retrieve"
    description = (
        "Search the local site knowledge base once. Call this for questions about "
        "the 众擎 store, the company, PM01, or T800. Pass the user's question. "
        "Answer only from the returned passages."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The user's question for this turn.",
            }
        },
        "required": ["query"],
    }

    def __init__(self, retriever: Bm25Retriever):
        self.retriever = retriever

    async def run(self, arguments) -> str:
        query = query_from_arguments(arguments)
        print(f"\n[检索] {query or '(空)'}", flush=True)
        if not query:
            return "Empty query; nothing retrieved."
        hits = await asyncio.to_thread(self.retriever.search, query)
        if not hits:
            print("[检索] 没有命中", flush=True)
            return "No matching passages."
        print(f"[检索] 命中 {len(hits)} 段", flush=True)
        return "\n\n".join(hits)


def load_retriever(path: Path) -> Bm25Retriever:
    if not path.is_file():
        raise RuntimeError(f"找不到知识库文件: {path}")
    retriever = Bm25Retriever.from_text_file(path)
    print(f"知识库: {path}  {len(retriever.chunks)} 段", flush=True)
    return retriever


async def run(args) -> None:
    retriever = load_retriever(args.knowledge)
    cfg = load_config()
    tool = RetrieveTool(retriever)
    cfg.instructions = RAG_INSTRUCTIONS
    cfg.tools = tool_schemas([tool])
    cfg.hotwords = ["众擎", "PM01", "T800"]
    provider = VolcengineProvider(cfg)
    player = PcmPlayer(cfg.tts_sample_rate, args.output_device)
    session = DialogSession(provider, player, duplex=args.duplex, tools=[tool])
    await run_microphone_dialog(
        provider,
        session,
        player,
        sample_rate=cfg.capture_sample_rate,
        input_device=args.input_device,
        output_device=args.output_device,
        greet=args.greet,
        ready_message="问门店或产品时会先检索知识库。Ctrl+C 结束。",
        connecting_message="正在连接火山引擎端到端对话…",
    )


def main() -> None:
    parser = build_parser("麦克风对话，本地 BM25 知识库")
    parser.add_argument(
        "--knowledge",
        type=Path,
        default=DEFAULT_KNOWLEDGE,
        help="知识库文本，默认 data/knowledge_text.txt",
    )
    args = parser.parse_args()
    if args.list_devices:
        list_devices()
        return
    run_until_interrupted(run(args))


if __name__ == "__main__":
    main()
