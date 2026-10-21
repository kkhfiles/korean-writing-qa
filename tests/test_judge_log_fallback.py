"""판정 기록을 못 쓸 때 줄을 잃지 않는지 본다 — 모델은 안 부른다.

(2026-10-21) Codex 백엔드 판정이 10-14~10-20 여러 번 실패했는데 판정 기록에는 Codex 실패가 한 줄도 없었다.
기록 쓰기(`log_call`)가 예외를 안 받아, 기록 폴더(`~/.claude/state`)를 막는 Codex 샌드박스(workspace-write)에서는
실패 줄을 적다가 권한 오류가 나 줄이 사라지고 원래 실패 사유까지 권한 오류로 덮였다. 재판정은 모델을 부르기 전
재생 입력(`save_case`)을 적다가, 성공한 판정은 직전 시스템 프롬프트(`save_system`)를 적다가 같은 오류로 죽었다.

**지키는 것**

- 기록을 못 쓰면 임시 폴더의 대신 적는 파일에 같은 줄을 적고 표준 출력에 그 위치를 알린다
- 실패한 판정은 원래 예외로 올라간다(권한 오류로 덮이지 않는다)
- 같은 폴더의 부속 파일(재생 입력 · 직전 시스템 프롬프트)을 못 써도 판정은 끝까지 간다
- 다음에 기록을 쓸 수 있으면 대신 적은 줄을 본 기록에 합치고 대신 적은 파일을 지운다 — 이미 있는 줄은 다시 안 넣는다
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402


class LogFallbackTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # 기록 폴더 자리에 파일을 두어 폴더를 못 만들게 한다 — 샌드박스의 쓰기 거부와 같은 OSError
        self.blocker = self.dir / "state"
        self.blocker.write_text("", encoding="utf-8")
        self.saved_log, judge.LOG = judge.LOG, self.blocker / "calls.jsonl"
        # 대신 적는 곳은 임시 폴더 아래다 — 시험 폴더로 돌려 실제 임시 폴더를 안 건드린다
        (self.dir / "tmp").mkdir()
        self.saved_tempdir, tempfile.tempdir = tempfile.tempdir, str(self.dir / "tmp")
        self.doc = self.dir / "d.md"
        self.doc.write_text("# 소개\n\n업무 목록은 매일 갱신됩니다.\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG = self.saved_log
        tempfile.tempdir = self.saved_tempdir
        self.tmp.cleanup()

    def spare(self) -> Path:
        return coverage.fallback_log(judge.LOG)

    def rows(self, p: Path) -> list[dict]:
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

    def unblock(self) -> None:
        self.blocker.unlink()

    def run_judge(self, backend: FakeBackend, targets=None) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            judge.judge(self.doc, "opus", 10, backend.pair(), targets)
        return out.getvalue()

    def test_the_spare_file_sits_in_the_temp_folder(self) -> None:
        self.assertEqual(Path(tempfile.gettempdir()), self.spare().parent)

    def test_a_failed_call_is_kept_in_the_spare_file(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(TimeoutError):
            judge.judge(self.doc, "opus", 10, FakeBackend(fail=True).pair())
        self.assertFalse(judge.LOG.exists())
        got = self.rows(self.spare())
        self.assertEqual([False], [r["ok"] for r in got])
        self.assertIn("시험용 실패", got[0]["error"])
        self.assertIn(str(self.spare()), out.getvalue())

    def test_the_next_writable_call_merges_and_removes_the_spare_file(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(TimeoutError):
            judge.judge(self.doc, "opus", 10, FakeBackend(fail=True).pair())
        self.unblock()
        self.run_judge(FakeBackend([]))
        self.assertEqual([False, True], [r["ok"] for r in self.rows(judge.LOG)])
        self.assertFalse(self.spare().exists())

    def test_a_line_already_in_the_log_is_not_merged_twice(self) -> None:
        # 합치다 지우기 전에 끊긴 경우 — 같은 줄이 두 곳에 남아 있다
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(TimeoutError):
            judge.judge(self.doc, "opus", 10, FakeBackend(fail=True).pair())
        line = self.spare().read_text(encoding="utf-8")
        self.unblock()
        judge.LOG.parent.mkdir()
        judge.LOG.write_text(line, encoding="utf-8")
        self.run_judge(FakeBackend([]))
        self.assertEqual([False, True], [r["ok"] for r in self.rows(judge.LOG)])
        self.assertFalse(self.spare().exists())

    def test_a_rejudge_finishes_without_its_side_files(self) -> None:
        # 재판정은 재생 입력과 직전 시스템 프롬프트를 기록 폴더 옆에 적는다 — 못 적어도 판정은 끝까지 간다
        self.run_judge(FakeBackend([]), targets=[3])
        got = self.rows(self.spare())
        self.assertEqual([True], [r["ok"] for r in got])
        self.assertEqual(1, got[0]["targets"])

    def test_a_writable_log_leaves_no_spare_file(self) -> None:
        self.unblock()
        out = self.run_judge(FakeBackend([]))
        self.assertEqual(1, len(self.rows(judge.LOG)))
        self.assertFalse(self.spare().exists())
        self.assertNotIn("대신 적었", out)


if __name__ == "__main__":
    unittest.main()
