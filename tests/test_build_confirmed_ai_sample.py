from __future__ import annotations

import unittest
from pathlib import Path

from scripts.build_confirmed_ai_sample import confirmed_documents, parse_frontmatter


class ConfirmedAiSampleTests(unittest.TestCase):
    def test_parse_frontmatter(self) -> None:
        text = """---
type: competitors
generated_at: 2026-08-01T00:11:00+09:00
model: Gemini Flash
---
# 보고서
"""
        self.assertEqual(parse_frontmatter(text)["type"], "competitors")
        self.assertEqual(parse_frontmatter(text)["model"], "Gemini Flash")

    def test_requires_model_and_generated_at(self) -> None:
        root = Path(__file__).parent / "fixtures" / "confirmed"
        documents = confirmed_documents(root)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["document_type"], "report")


if __name__ == "__main__":
    unittest.main()
