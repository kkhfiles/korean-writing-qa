"""`bootstrap.py` 하나로 빈 환경에 설치하고, 스킬이 저장소 도구를 찾는 데까지 확인한다.

**왜 있나** — 코딩 에이전트에게 설치를 맡기면 확인, 설치, 검증 명령마다 승인을 묻는다. 판단이
필요 없는 일을 이 파일 하나로 묶었다. 설치 시험이 설치까지만 보면 「설치는 되고 첫 사용에서
깨짐」을 못 잡으므로(2026-10-29), 설치된 입구로 저장소 도구를 불러 보는 데까지 간다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BootstrapTests(unittest.TestCase):
    def _bootstrap(self, env: dict) -> tuple[int, str]:
        done = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "bootstrap.py"), "--no-pip"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=env, timeout=600)
        return done.returncode, done.stdout + done.stderr

    def test_fresh_claude_home_is_installed_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            claude = Path(d) / "claude"
            claude.mkdir()
            env = {k: v for k, v in os.environ.items() if k != "KOREAN_WRITING_QA_HOME"}
            env.update(CLAUDE_HOME=str(claude), CODEX_HOME=str(Path(d) / "no-codex"))
            rc, out = self._bootstrap(env)
            self.assertEqual(0, rc, out)
            self.assertIn("스킬이 저장소 도구를 찾음", out)
            self.assertIn("설치와 검증 모두 통과", out)
            self.assertTrue((claude / "settings.json").is_file(), "훅을 걸 설정 파일을 만듦")
            self.assertIn("doc-style-gate.py", (claude / "settings.json").read_text(encoding="utf-8"))

    def test_without_any_agent_it_says_what_to_do(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, CLAUDE_HOME=str(Path(d) / "none"), CODEX_HOME=str(Path(d) / "none2"),
                       PATH=str(Path(d)))
            done = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "bootstrap.py"), "--no-pip"],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  env=env, timeout=120)
            self.assertEqual(2, done.returncode, done.stdout)
            self.assertIn("한 번 실행한 뒤", done.stdout)


if __name__ == "__main__":
    unittest.main()
