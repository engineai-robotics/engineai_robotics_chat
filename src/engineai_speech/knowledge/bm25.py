"""本地 BM25 检索

jieba 搜索模式切词，BM25Okapi 打分，返回原文片段。没有向量模型。
"""

from __future__ import annotations

import re
from pathlib import Path

import jieba
import numpy as np
from rank_bm25 import BM25Okapi

jieba.initialize()

_PARA_RE = re.compile(r"\n\s*\n+")
_SENT_RE = re.compile(r"(?<=[。！？；.!?;])")
_PUNCT_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)
_STOPWORDS = Path(__file__).resolve().parent / "stopwords.txt"

_EN_DIGIT = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}
_EN_WORD = r"(?:zero|one|two|three|four|five|six|seven|eight|nine|hundred|thousand)"
_CN_NUM_TRANS = str.maketrans("零一二三四五六七八九十百千", "0123456789000")
_CN_DIGITS = "一二三四五六七八九"


def chunk_text(text: str, chunk_size: int = 512) -> list[str]:
    """按段落、句子边界切块，单块不超过 ``chunk_size`` 个字符。"""

    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    for para in _PARA_RE.split(text):
        para = " ".join(para.split())
        if not para:
            continue
        if len(para) <= chunk_size:
            _append_piece(chunks, para, chunk_size)
            continue
        for sent in _SENT_RE.split(para):
            sent = sent.strip()
            if not sent:
                continue
            if len(sent) <= chunk_size:
                _append_piece(chunks, sent, chunk_size)
            else:
                for i in range(0, len(sent), chunk_size):
                    piece = sent[i : i + chunk_size].strip()
                    if piece:
                        chunks.append(piece)
    return chunks


def _append_piece(chunks: list[str], piece: str, size: int) -> None:
    if not chunks:
        chunks.append(piece)
        return
    tail = chunks[-1]
    if len(tail) + 1 + len(piece) <= size:
        chunks[-1] = f"{tail} {piece}"
    else:
        chunks.append(piece)


def normalize_query_numbers(query: str) -> str:
    """型号口语转数字：PM零一 / PM zero one / T八百 / T eight hundred。"""

    if not query:
        return query

    def _en_words_to_number(words: str) -> str | None:
        toks = [t for t in re.split(r"[\s-]+", (words or "").lower()) if t]
        if not toks:
            return None
        if all(t in _EN_DIGIT for t in toks):
            return "".join(_EN_DIGIT[t] for t in toks)
        if len(toks) == 2 and toks[0] in _EN_DIGIT and toks[1] in {"hundred", "thousand"}:
            return _EN_DIGIT[toks[0]] + ("00" if toks[1] == "hundred" else "000")
        return None

    query = re.sub(
        rf"([A-Za-z]+)\s+((?:{_EN_WORD})(?:[\s-]+(?:{_EN_WORD}))*)",
        lambda m: m.group(1).upper() + (_en_words_to_number(m.group(2)) or m.group(2)),
        query,
        flags=re.IGNORECASE,
    )

    def _cn_words_to_number(text: str) -> str:
        s = text or ""
        for unit, zeros in (("万", "0000"), ("千", "000"), ("百", "00")):
            s = re.sub(rf"([0-9]){unit}", lambda m: m.group(1) + zeros, s)
            s = re.sub(
                rf"([{_CN_DIGITS}]){unit}",
                lambda m: str(_CN_DIGITS.index(m.group(1)) + 1) + zeros,
                s,
            )
        s = re.sub(
            r"[零一二三四五六七八九十百千]+",
            lambda m: m.group().translate(_CN_NUM_TRANS),
            s,
        )
        return s

    return re.sub(
        r"([A-Za-z]+)([零一二三四五六七八九十百千万0-9]+)",
        lambda m: m.group(1).upper() + _cn_words_to_number(m.group(2)),
        query,
    )


def _load_stopwords(path: Path) -> frozenset[str]:
    if not path.is_file():
        return frozenset()
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip()
        if word:
            words.add(word)
    return frozenset(words)


class Bm25Retriever:
    def __init__(self, chunks: list[str], stopwords: frozenset[str] | None = None) -> None:
        self._stopwords = stopwords if stopwords is not None else _load_stopwords(_STOPWORDS)
        self.chunks = list(chunks)
        self._tokens = [self._tokenize(text) for text in self.chunks]
        usable = [tok for tok in self._tokens if tok]
        self._bm25 = BM25Okapi(usable) if usable else None
        self._usable_index = [i for i, tok in enumerate(self._tokens) if tok]

    @classmethod
    def from_text_file(cls, path: Path, chunk_size: int = 512) -> "Bm25Retriever":
        raw = path.read_text(encoding="utf-8")
        chunks = chunk_text(raw, chunk_size=chunk_size)
        if not chunks:
            raise RuntimeError(f"知识库是空的: {path}")
        return cls(chunks)

    def _tokenize(self, text: str) -> list[str]:
        out: list[str] = []
        for word in jieba.lcut_for_search(text):
            word = word.strip()
            if (
                word.lower() in self._stopwords
                or _PUNCT_RE.match(word)
                or len(word) < 2
                or word.isdigit()
            ):
                continue
            out.append(word)
        return out

    def search(self, query: str, top_k: int = 5, threshold: float = 0.0) -> list[str]:
        if self._bm25 is None or not self.chunks:
            return []
        tokens = list(
            set(self._tokenize(query) + self._tokenize(normalize_query_numbers(query)))
        )
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        order = np.argsort(scores)[::-1][:top_k]
        return [
            self.chunks[self._usable_index[int(i)]]
            for i in order
            if scores[int(i)] > threshold
        ]
