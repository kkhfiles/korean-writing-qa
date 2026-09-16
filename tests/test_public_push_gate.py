"""공개 저장소 푸시 게이트가 **막을 것만 막는지** 본다.

**왜 이 시험이 필요한가.** 2026-09-16 에 「푸시는 기본으로 하고 공개 저장소만
게이트」로 정했다. 이 훅이 잘못 넓으면 **개인 저장소 푸시가 전부 막히고**, 잘못
좁으면 그 사고(공개 저장소로 실명 554종이 엿새)가 그대로 되풀이된다.

**둘 다 시험한다** — 막는 쪽만 재면 「전부 막음」이 만점이 된다(이 저장소의 짝 시료
원칙과 같다).
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HOOK = repo_paths.hook("public-push-gate.py")


def load_hook():
    """이름에 하이픈이 있어 그냥 import 가 안 된다 — 경로로 읽어 온다."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("public_push_gate", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(command: str, cwd: Path | None = None, env_extra: dict | None = None):
    import os                                        # noqa: PLC0415
    env = dict(os.environ)
    env.pop("KOREAN_PUSH_FORCE", None)
    env.update(env_extra or {})
    payload = json.dumps({"tool_input": {"command": command},
                          "cwd": str(cwd or repo_paths.REPO)})
    return subprocess.run([sys.executable, "-X", "utf8", str(HOOK)],
                          input=payload, capture_output=True, text=True,
                          encoding="utf-8", env=env)


class PublicPushGateTests(unittest.TestCase):
    def test_the_hook_exists_and_is_installed(self) -> None:
        self.assertTrue(HOOK.is_file(), f"훅이 없다: {HOOK}")
        import install                                # noqa: PLC0415
        self.assertIn("public-push-gate.py", install.HOOK_FILES)
        self.assertIn(("PreToolUse", "Bash|PowerShell", "public-push-gate.py"),
                      install.HOOK_WIRING)

    def test_non_push_commands_pass(self) -> None:
        """푸시가 아닌 것을 막으면 이 저장소에서 아무 일도 못 한다."""
        for cmd in ("git status", "git commit -m 'x'", "ls",
                    "git log --oneline -3", "echo push"):
            with self.subTest(cmd):
                self.assertEqual(0, run(cmd).returncode)

    def test_push_shapes_are_recognised(self) -> None:
        """`&&` 로 이어 붙이거나 앞에 옵션이 붙어도 푸시는 푸시다."""
        pat = load_hook().PUSH
        for cmd in ("git push", "git push origin main",
                    "git add -A && git push", "git -C /tmp/x push"):
            with self.subTest(cmd):
                self.assertTrue(pat.search(cmd))
        for cmd in ("git status", "echo 'git pushed'", "git pushnothing",
                    "git log --grep push", "git log --oneline"):
            with self.subTest(cmd):
                self.assertIsNone(pat.search(cmd))

    def test_escape_hatch_lets_it_through(self) -> None:
        """막되 푸는 길을 둔다 — 열쇠 없는 자물쇠를 만들지 않는다."""
        done = run("git push", env_extra={"KOREAN_PUSH_FORCE": "1"})
        self.assertEqual(0, done.returncode)
        self.assertIn("넘겼습니다", done.stderr)

    def test_public_repo_push_is_gated_and_says_why(self) -> None:
        """이 저장소는 공개다 — 검사를 거쳐야 하고, 통과하면 보내야 한다."""
        done = run("git push")
        self.assertIn(done.returncode, (0, 2))
        if done.returncode == 2:
            self.assertIn("공개 저장소", done.stderr)
            self.assertIn("KOREAN_PUSH_FORCE", done.stderr)


if __name__ == "__main__":
    unittest.main()
