from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.build_multiformat_ai_sample import (
    build,
    discover_candidates,
    select_candidates,
)


class MultiformatAiSampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_root = Path(__file__).parent / "fixtures" / "multiformat-reports"

    def test_discovery_requires_explicit_generation_evidence(self) -> None:
        candidates = discover_candidates(self.source_root)
        counts = {
            group: sum(item["sample_group"] == group for item in candidates)
            for group in ("markdown", "jsonl", "text")
        }

        self.assertEqual(counts, {"markdown": 1, "jsonl": 2, "text": 1})
        self.assertFalse(any("ignored" in str(item["relative_path"]) for item in candidates))
        self.assertFalse(any("err" in str(item["relative_path"]) for item in candidates))

    def test_selection_is_deterministic_and_keeps_all_text(self) -> None:
        candidates = discover_candidates(self.source_root)

        first = select_candidates(candidates, markdown_count=1, jsonl_count=1)
        second = select_candidates(candidates, markdown_count=1, jsonl_count=1)

        self.assertEqual(
            [item["source_unit_id"] for item in first],
            [item["source_unit_id"] for item in second],
        )
        self.assertEqual([item["sample_group"] for item in first].count("text"), 1)

    def test_build_copies_units_and_keeps_raw_content_out_of_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary)
            manifest = build(
                self.source_root,
                project_root,
                "test-run",
                markdown_count=1,
                jsonl_count=1,
            )

            self.assertEqual(manifest["sample_size"], 3)
            self.assertTrue(
                all((project_root / str(item["copy_path"])).is_file() for item in manifest["units"])
            )
            catalog = (
                project_root / "data" / "catalog" / "multiformat-ai-units.jsonl"
            ).read_text(encoding="utf-8")
            self.assertNotIn("본문 문장", catalog)
            self.assertNotIn("_raw_bytes", catalog)


if __name__ == "__main__":
    unittest.main()
