"""훅이 `-X utf8` 없이 불려도 받은 한글 명령을 그대로 읽는지 본다.

설치된 훅은 `python "<훅>"` 으로 불린다(`-X utf8` 없음). 이 PC 의 파이썬은 그때 표준 입력을 cp949 와
`surrogateescape` 로 읽어, UTF-8 로 온 한글 명령이 깨진 글자와 서로게이트가 됐다. 2026-11-06 에
발행 게이트가 막는 사유를 출력하다 `UnicodeEncodeError` 로 넘어져 진짜 사유 대신 「판정하지 못했습니다」만
보였다. 다른 시험은 훅을 `-X utf8` 로 불러 이 증상이 안 나는 조건에서만 쟀다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "hooks"


def plain_env() -> dict:
    """설치된 훅과 같은 조건 — UTF-8 모드를 켜는 변수를 걷어 낸다."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env.pop("KOREAN_PUBLISH_FORCE", None)
    return env


class StdinEncodingTests(unittest.TestCase):

    def test_every_hook_that_reads_stdin_sets_utf8(self) -> None:
        """새 훅이 빠지지 않게 — 표준 입력을 JSON 으로 읽는 훅은 모두 UTF-8 로 다시 설정한다."""
        readers = [p for p in HOOKS.glob("*.py") if re.search(r"json\.load\(sys\.stdin\)", p.read_text(encoding="utf-8"))]
        self.assertTrue(readers)
        for p in readers:
            with self.subTest(p.name):
                self.assertIn('sys.stdin.reconfigure(encoding="utf-8")', p.read_text(encoding="utf-8"))

    def test_the_gate_keeps_a_korean_branch_name_intact(self) -> None:
        """없는 한글 가지를 미는 명령 — 막는 사유에 그 이름이 글자 그대로 나와야 한다."""
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "stdin-utf8",
                   "cwd": str(ROOT), "tool_input": {"command": "git push origin 없는가지"}}
        done = subprocess.run([sys.executable, str(HOOKS / "doc-style-gate.py")],
                              input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                              capture_output=True, env=plain_env(), timeout=240)
        out = done.stdout.decode("utf-8", "replace")
        self.assertNotIn("UnicodeEncodeError", out + done.stderr.decode("utf-8", "replace"))
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("없는가지", reason)


if __name__ == "__main__":
    unittest.main()
