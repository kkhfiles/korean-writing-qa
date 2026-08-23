from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from scripts.scan_user_feedback import load_feedback, scan_path, scan_text


class UserFeedbackScannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        project_root = Path(__file__).resolve().parents[1]
        cls.project_root = project_root
        cls.feedback = load_feedback(
            project_root
            / "data"
            / "annotations"
            / "user-confirmed-phrases.jsonl"
        )
        cls.formats = project_root / "tests" / "fixtures" / "formats"

    def test_exact_replacement_is_suggested(self) -> None:
        findings = scan_text("제품화 경로를 정합니다.", self.feedback)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["action"], "suggest_exact")
        self.assertEqual(findings[0]["suggestion"], "제품화 단계")

    def test_presenter_example_requires_context_review(self) -> None:
        findings = scan_text(
            "뒤의 것은 커버리지를 더 올립니다", self.feedback
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["action"], "review_context")
        self.assertTrue(findings[0]["requires_context"])

    def test_clean_text_has_no_findings(self) -> None:
        self.assertEqual(scan_text("요구사항 기반 테스트를 설계합니다.", self.feedback), [])

    def test_before_after_example_on_same_line_is_ignored(self) -> None:
        self.assertEqual(
            scan_text("제품화 경로 → 제품화 단계", self.feedback), []
        )

    def test_structured_value_is_scanned_with_logical_path(self) -> None:
        findings = scan_path(self.formats / "feedback.json", self.feedback)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["logical_path"], "/message")
        self.assertEqual(findings[0]["source_format"], ".json")
        self.assertIsNone(findings[0]["line_number"])

    def test_markdown_code_fence_is_not_scanned(self) -> None:
        self.assertEqual(
            scan_path(self.formats / "feedback-code.md", self.feedback), []
        )

    def test_command_can_run_as_a_script(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/scan_user_feedback.py", "--help"],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
