"""하루 첫 세션 회귀 점검이 제대로 걸려 있는지 고정한다.

**왜 있나** — 시험이 지키는 것은 배포된 전역 자산인데, 그 파일들은 **어느 프로젝트
세션에서든** 바뀐다. 시험은 이 저장소에 있어서, 여기를 안 여는 날에는 아무도 안 돌린다.
실측(8/24~9/4)으로는 자산이 바뀐 9일이 9일 다 덮였지만, 마침 여기서 고쳤기 때문이지
구조가 보장한 것이 아니다.

**동기 스크립트에 안 붙인 까닭** — `sync.sh` 는 하루 20~25번 돈다. 9초를 거기 붙이면
하루 4분을 막는다. 세션 시작은 하루 몇 번이고 그중 첫 번만 돈다.

**첫 실행에서 값을 했다** — 붙이자마자 이 저장소의 불안정한 시험 하나를 잡았다
(`--days 0` 으로 「기록 없음」을 흉내 내던 것 · 지금 세션 기록이 계속 쓰여 결과가
달라졌다).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

CHECK = Path.home() / ".claude" / "hooks" / "korean-gate-daily-check.py"
SETTINGS = Path.home() / ".claude" / "settings.json"


def load_check():
    spec = importlib.util.spec_from_file_location("korean_gate_daily_check", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DailyHealthCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECK.is_file():
            raise unittest.SkipTest(f"점검 훅이 없습니다: {CHECK}")
        cls.check = load_check()

    def test_its_own_self_test_passes(self) -> None:
        """주기 판단이 틀리면 매 세션 돌거나 영영 안 돈다."""
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(CHECK), "--self-test"],
            capture_output=True, text=True, encoding="utf-8")

        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_it_runs_once_a_day(self) -> None:
        now = datetime(2026, 9, 4, 10, 0)

        self.assertTrue(self.check.due({}, now))
        self.assertFalse(self.check.due({"last_checked_date": "2026-09-04"}, now))
        self.assertTrue(self.check.due({"last_checked_date": "2026-09-03"}, now))

    def test_an_undecidable_run_does_not_mark_the_day_seen(self) -> None:
        """못 돌린 날을 「봤다」로 적으면 그날 하루가 통째로 빈다."""
        now = datetime(2026, 9, 4, 10, 0)
        state = {"last_attempt_at": (now - timedelta(hours=7)).isoformat()}

        self.assertTrue(self.check.due(state, now),
                        "판단 불가 뒤 유예가 지나면 다시 돌려야 합니다")

    def test_it_cannot_run_without_the_repo(self) -> None:
        """저장소가 없으면 통과로 처리하지 않고 판단 불가로 끝낸다."""
        original = self.check.REPO
        self.check.REPO = original.with_name("no-such-repo")
        try:
            passed, why = self.check.run_suite()
        finally:
            self.check.REPO = original

        self.assertIsNone(passed)
        self.assertIn("없다", why)

    def test_the_failure_message_names_what_it_guards(self) -> None:
        """무엇이 깨졌는지 모르면 읽고도 아무것도 못 한다."""
        text = self.check.render("1 failed, 269 passed")

        for part in ("doc-style-check.py", "doc-style-gate.py", "finalize-korean-document"):
            with self.subTest(part=part):
                self.assertIn(part, text)

    def test_batch_and_scheduled_runs_exit_at_once(self) -> None:
        """자동으로 도는 세션에서 9초짜리 시험을 돌리면 안 된다.

        SessionStart 훅 넷이 다 이 검사를 하는데 이것만 빠져 있었다(재검토에서 잡음).
        """
        import os
        for flag in ("CLAUDE_BATCH_MODE", "CLAUDE_SCHEDULED"):
            with self.subTest(flag=flag):
                env = dict(os.environ, **{flag: "1"})
                start = __import__("time").monotonic()
                done = subprocess.run(
                    [sys.executable, "-X", "utf8", str(CHECK)],
                    input="{}", capture_output=True, text=True,
                    encoding="utf-8", env=env)
                elapsed = __import__("time").monotonic() - start

                self.assertEqual(done.returncode, 0)
                self.assertEqual((done.stdout or "").strip(), "")
                self.assertLess(elapsed, 3.0, "즉시 끝나야 합니다")

    def test_it_is_wired_into_session_start(self) -> None:
        """훅을 써 두고 등록을 안 하면 규칙이 존재만 하고 효력이 0이다."""
        if not SETTINGS.is_file():
            self.skipTest("설정 파일이 없습니다")
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        commands = [hook.get("command", "")
                    for group in data.get("hooks", {}).get("SessionStart", [])
                    for hook in group.get("hooks", [])]

        self.assertTrue(any("korean-gate-daily-check.py" in c for c in commands),
                        "SessionStart 에 등록돼 있지 않습니다")
