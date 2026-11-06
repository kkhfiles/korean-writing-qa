"""push 뒤 GitHub 시험 대기(`scripts/wait_ci.py`) — 실패 이름 읽기와 push 직후 훅. `gh` 는 부르지 않는다."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wait_ci  # noqa: E402

LOG = """test (3.11)\tUNKNOWN STEP\t2026-11-05T06:43:40Z FAIL: test_balanced_rejudges (test_judge_levels.LevelTests.test_balanced_rejudges)
test (3.11)\tUNKNOWN STEP\t2026-11-05T06:43:40Z ERROR: test_x (test_y.Cls)
test (3.11)\tUNKNOWN STEP\t2026-11-05T06:43:40Z FAIL: test_balanced_rejudges (test_judge_levels.LevelTests.test_balanced_rejudges)
"""


class FailedNameTests(unittest.TestCase):
    def test_names_come_out_once_in_order(self) -> None:
        self.assertEqual(["test_judge_levels.LevelTests.test_balanced_rejudges", "test_y.Cls.test_x"],
                         wait_ci.failed_tests(LOG))


class WaitTests(unittest.TestCase):
    def run_wait(self, runs, log=""):
        out = io.StringIO()
        with mock.patch.object(wait_ci, "find_run", side_effect=runs), \
                mock.patch.object(wait_ci, "gh", return_value=log), \
                mock.patch.object(wait_ci.time, "sleep"), contextlib.redirect_stdout(out):
            rc = wait_ci.wait("f7163f2abc")
        return rc, out.getvalue()

    def test_a_failed_run_is_rc_1_with_test_names(self) -> None:
        done = {"databaseId": 1, "status": "completed", "conclusion": "failure", "url": "u"}
        rc, out = self.run_wait([None, {**done, "status": "in_progress"}, done], LOG)
        self.assertEqual(1, rc)
        self.assertIn("test_balanced_rejudges", out)

    def test_a_green_run_is_rc_0(self) -> None:
        rc, _ = self.run_wait([{"databaseId": 1, "status": "completed", "conclusion": "success", "url": "u"}])
        self.assertEqual(0, rc)

    def test_no_run_is_undecided_not_a_pass(self) -> None:
        with mock.patch.object(wait_ci, "APPEAR_WAIT", -1):
            rc, out = self.run_wait([None])
        self.assertEqual(2, rc)
        self.assertIn("판정 불가", out)


class HookTests(unittest.TestCase):
    def hook(self, command: str) -> str:
        out = io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": command}}))), \
                contextlib.redirect_stdout(out):
            self.assertEqual(0, wait_ci.hook())
        return out.getvalue()

    def test_a_push_asks_for_the_wait(self) -> None:
        note = json.loads(self.hook("git push 2>&1 | tail -3"))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("wait_ci.py", note)

    def test_other_commands_stay_silent(self) -> None:
        self.assertEqual("", self.hook("git status"))
        self.assertEqual("", self.hook("git log --oneline | grep push"))
        self.assertEqual("", self.hook("git commit -q -F - <<'EOF'\npush 뒤 시험 결과까지 확인\nEOF"),
                         "커밋 메시지의 push 를 push 명령으로 읽었습니다")


if __name__ == "__main__":
    unittest.main()
