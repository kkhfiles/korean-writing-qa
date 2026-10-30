"""시험 실행 도구가 **실패한 시험 이름을 잃지 않고 종료 코드를 지키는지** 본다.

(2026-10-30) 전체 시험 출력을 `| tail` 로 잘라 실패 이름을 잃고 9분을 다시 돌렸다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_tests  # noqa: E402

SAMPLE = """..F.E
======================================================================
FAIL: test_a (tests.test_x.XTests.test_a)
----------------------------------------------------------------------
AssertionError: 1 != 2
======================================================================
ERROR: test_b (tests.test_x.XTests.test_b)
----------------------------------------------------------------------
Ran 5 tests in 0.010s

FAILED (failures=1, errors=1)
"""


class RunTestsTests(unittest.TestCase):

    def test_the_summary_keeps_failed_names_and_totals(self) -> None:
        got = run_tests.summarize(SAMPLE)
        self.assertEqual(["FAIL: test_a (tests.test_x.XTests.test_a)",
                          "ERROR: test_b (tests.test_x.XTests.test_b)",
                          "Ran 5 tests in 0.010s", "FAILED (failures=1, errors=1)"], got)

    def test_a_failing_run_keeps_its_exit_code_and_names(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            mod = Path(tmp) / "test_always_fails.py"
            mod.write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                           "    def test_no(self):\n        self.assertEqual(1, 2)\n", encoding="utf-8")
            name = f"tests.{Path(tmp).name}.test_always_fails"
            (Path(tmp) / "__init__.py").write_text("", encoding="utf-8")
            done = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "run_tests.py"), name],
                                  cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(0, done.returncode, "실패한 시험이 있는데 종료 코드가 0 입니다")
        self.assertIn("FAIL: test_no", done.stdout)
        self.assertIn("로그 — ", done.stdout)

    def test_a_passing_run_exits_zero(self) -> None:
        done = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "run_tests.py"),
                               "tests.test_run_tests.RunTestsTests.test_the_summary_keeps_failed_names_and_totals"],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, done.returncode, done.stdout)
        self.assertIn("OK", done.stdout)


if __name__ == "__main__":
    unittest.main()
