"""겹 역슬래시 차단 훅이 실제로 무는지 확인한다.

**왜 여기서 시험하나.** 이 함정에 이 세션에서만 세 번 걸렸고, 그때마다
CLAUDE.md 에 규칙이 이미 있었다. 적어 두는 것으로는 안 막히므로 훅으로 옮겼고,
훅이 조용해지면 규칙은 다시 글자만 남는다.

**두 방향을 다 지킨다** — 겹 역슬래시를 막아야 하고, 한 겹은 통과해야 한다.
한 겹까지 막으면 평범한 명령이 다 걸려서 훅을 꺼 버리게 된다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HOOK = repo_paths.hook("block-backslash-in-shell.py")
BS = chr(92)


class BackslashHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HOOK.is_file():
            raise unittest.SkipTest(f"훅이 없습니다: {HOOK}")

    def run_hook(self, command: str, tool: str = "Bash"):
        payload = json.dumps({"tool_name": tool, "tool_input": {"command": command}})
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(HOOK)],
            input=payload, capture_output=True, text=True, encoding="utf-8",
        )
        return done.returncode, done.stderr

    def test_a_doubled_backslash_is_blocked(self) -> None:
        code, reason = self.run_hook(f'python -c "print({BS * 2})"')

        self.assertEqual(code, 2)
        self.assertIn("겹 역슬래시", reason)

    def test_the_reason_says_what_to_do_instead(self) -> None:
        """무엇을 하라는 말이 없으면 같은 명령을 다시 보낸다."""
        _code, reason = self.run_hook(f'sed -i "s/a/{BS * 2}/" x.py')

        self.assertIn("Write 도구", reason)
        self.assertIn("Edit 도구", reason)

    def test_the_reason_points_at_the_offending_line(self) -> None:
        command = "\n".join(["echo 첫 줄", f"echo {BS * 2}", "echo 셋째 줄"])
        _code, reason = self.run_hook(command)

        self.assertIn("2:", reason)

    def test_a_single_backslash_passes(self) -> None:
        """한 겹은 그대로 도착하므로 막을 이유가 없다 — 막으면 훅을 꺼 버리게 된다."""
        code, _reason = self.run_hook(f'grep -n "^{BS}|" file.md')

        self.assertEqual(code, 0)

    def test_a_plain_command_passes(self) -> None:
        code, _reason = self.run_hook("python -X utf8 -m pytest -q")

        self.assertEqual(code, 0)

    def test_other_tools_are_not_touched(self) -> None:
        """PowerShell 의 here-string 은 역슬래시가 안 벗겨진다 — 대상이 아니다."""
        code, _reason = self.run_hook(f'Write-Output "{BS * 2}"', tool="PowerShell")

        self.assertEqual(code, 0)

    def test_the_hook_itself_is_quiet(self) -> None:
        """훅이 경고를 뿜으면 차단 이유가 그 밑에 묻힌다 — 실제로 그랬다."""
        done = subprocess.run(
            [sys.executable, "-X", "utf8", "-W", "error", str(HOOK)],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(done.returncode, 0, done.stderr[:300])
        self.assertNotIn("SyntaxWarning", done.stderr)

    def test_a_broken_payload_does_not_block_everything(self) -> None:
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(HOOK)],
            input="not json", capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(done.returncode, 0)


if __name__ == "__main__":
    unittest.main()
