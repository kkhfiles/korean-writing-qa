from __future__ import annotations

import json
import unittest
from pathlib import Path


class AnnotationSpanTests(unittest.TestCase):
    def test_annotated_spans_exist_in_source_and_revision(self) -> None:
        project_root = Path(__file__).parents[1]
        annotations = project_root / "data" / "annotations" / "diagnostic-002-review.jsonl"
        revision_root = project_root / "runs" / "diagnostic-002" / "revisions"
        raw_root = project_root / "data" / "raw" / "diagnostic-002"
        if not raw_root.exists():
            self.skipTest("local diagnostic raw sample is not present")

        for line in annotations.read_text(encoding="utf-8").splitlines():
            annotation = json.loads(line)
            document_id = annotation["document_id"]
            original = (
                raw_root / f"{document_id}.md"
            ).read_text(encoding="utf-8")
            revised = (
                revision_root
                / document_id
                / "_workspace"
                / "2026-08-24-001"
                / "final.md"
            ).read_text(encoding="utf-8")

            with self.subTest(annotation_id=annotation["annotation_id"]):
                self.assertIn(annotation["original"], original)
                if annotation["revised"]:
                    self.assertIn(annotation["revised"], revised)
                else:
                    self.assertNotIn(annotation["original"], revised)


if __name__ == "__main__":
    unittest.main()
