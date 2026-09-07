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
        # 원문과 수정본 둘 다 작성자 기계에만 있는 연구 자료다. 원문(`data/raw/**`)은
        # 처음부터 Git 제외였고, 수정본은 사내 보고서 통짜라 공개본에서 뺐다(2026-09-07).
        # 클론한 기계에서는 이 시험이 늘 건너뛴다 — 있을 때만 표시 구간을 대조한다.
        if not raw_root.exists():
            self.skipTest("진단용 원문 복사본이 없습니다 — 작성자 기계에만 있는 자료입니다")
        if not revision_root.exists():
            self.skipTest("수정본이 없습니다 — 사내 보고서라 공개본에서 뺐습니다")

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
