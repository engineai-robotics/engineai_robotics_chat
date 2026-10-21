import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engineai_robotics_chat.knowledge.bm25 import Bm25Retriever, chunk_text, normalize_query_numbers


class Bm25Tests(unittest.TestCase):
    def test_chunk_and_number_normalize(self):
        text = "第一段。\n\n" + ("第二段" * 300)
        chunks = chunk_text(text, chunk_size=64)
        self.assertGreater(len(chunks), 1)
        self.assertLessEqual(max(len(item) for item in chunks), 64)
        self.assertEqual(normalize_query_numbers("介绍一下 PM零一 和 T八百"), "介绍一下 PM01 和 T800")

    def test_search_returns_matching_passage(self):
        retriever = Bm25Retriever(
            [
                "PM01 是众擎的人形机器人，续航两小时。",
                "今天天气很好，适合出门。",
                "T800 用于工业搬运和展厅讲解。",
            ]
        )
        hits = retriever.search("PM01 续航多久")
        self.assertTrue(hits)
        self.assertIn("PM01", hits[0])


if __name__ == "__main__":
    unittest.main()
