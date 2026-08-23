from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.build_diagnostic_sample import catalog, select_sample


class DiagnosticSampleTests(unittest.TestCase):
    def test_catalog_uses_relative_paths_and_text_extensions(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary:
            root = Path(temporary)
            (root / "area").mkdir()
            (root / "area" / "report.md").write_text(
                "한글 문서입니다. " * 30, encoding="utf-8"
            )
            (root / "ignored.json").write_text("{}", encoding="utf-8")

            documents = catalog(root)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["relative_path"], "area/report.md")
        self.assertEqual(documents[0]["source_bucket"], "area")

    def test_selection_is_deterministic_and_balanced_by_stratum(self) -> None:
        documents = []
        for bucket in ("a", "b"):
            for size in ("small", "large"):
                for index in range(3):
                    documents.append(
                        {
                            "relative_path": f"{bucket}/{size}-{index}.md",
                            "extension": ".md",
                            "bytes": 30_000 if size == "large" else 2_000,
                            "korean_chars": 500,
                            "source_bucket": bucket,
                            "size_bucket": size,
                            "sha256": f"{bucket}-{size}-{index}",
                        }
                    )

        first = select_sample(documents, 4)
        second = select_sample(list(reversed(documents)), 4)

        self.assertEqual(first, second)
        self.assertEqual(
            {(item["source_bucket"], item["size_bucket"]) for item in first},
            {("a", "small"), ("a", "large"), ("b", "small"), ("b", "large")},
        )


if __name__ == "__main__":
    unittest.main()
