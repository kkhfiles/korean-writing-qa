"""`install.py --codex` 가 Codex 쪽에 스킬과 훅을 **남의 것을 안 건드리고** 거는지 본다.

**왜 있나.** Codex 가 주력인 사람이 이 검사기를 설치하면 지금까지는 스킬도 게이트도 못 받았다 —
설치기가 `~/.claude/` 만 봤다(2026-10-01). Codex 는 사용자 스킬을 `~/.agents/skills` 에서,
훅을 `~/.codex/hooks.json` 에서 읽는다.

**막는 것 셋**
- 다시 돌리면 훅이 겹쳐 쌓이는 것
- 남이 건 훅·남이 만든 같은 이름 스킬을 지우는 것
- 설정 거울 투영이 관리하는 PC 에서 같은 파일을 덮는 것(파일마다 관리 주체는 하나)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.py"
SKILL = "finalize-korean-document"
MARK = ".installed-by-korean-writing-qa"


class InstallCodexTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.claude, self.codex, self.skills = t / "claude", t / "codex", t / "agents" / "skills"
        self.codex.mkdir(parents=True)
        self.env = dict(os.environ, CLAUDE_HOME=str(self.claude), CODEX_HOME=str(self.codex),
                        KOREAN_QA_AGENTS_SKILLS=str(self.skills))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def install(self, *extra: str) -> tuple[int, str]:
        done = subprocess.run([sys.executable, "-X", "utf8", str(INSTALL), "--codex", *extra],
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              env=self.env, timeout=300)
        return done.returncode, done.stdout + done.stderr

    def hooks(self) -> dict:
        return json.loads((self.codex / "hooks.json").read_text(encoding="utf-8"))["hooks"]

    def commands(self, event: str) -> list[str]:
        return [h["command"] for g in self.hooks().get(event, []) for h in g["hooks"]]

    def test_skills_and_hooks_are_installed(self) -> None:
        rc, out = self.install()
        self.assertEqual(0, rc, out)
        self.assertTrue((self.skills / SKILL / "SKILL.md").is_file(), "스킬을 Codex 위치에 안 깔았습니다")
        self.assertTrue((self.skills / SKILL / MARK).is_file(), "관리 표시가 없으면 다음 설치가 못 고칩니다")
        pre, post = self.commands("PreToolUse"), self.commands("PostToolUse")
        self.assertTrue(any("doc-style-gate.py" in c for c in pre), "발행·push 게이트가 없습니다")
        self.assertTrue(any("public-push-gate.py" in c for c in pre))
        self.assertTrue(any("doc-style-gate.py" in c for c in post), "쓰는 순간 검사가 없습니다")
        self.assertIn("apply_patch", [g["matcher"] for g in self.hooks()["PostToolUse"]][0])
        self.assertIn("승인", out, "Codex 는 훅을 승인해야 돈다 — 그 사실을 알려야 합니다")

    def test_running_twice_does_not_stack_hooks(self) -> None:
        self.install()
        self.install()
        pre = self.commands("PreToolUse")
        self.assertEqual(1, sum("doc-style-gate.py" in c for c in pre), f"훅이 겹쳤습니다: {pre}")

    def test_other_hooks_and_skills_are_left_alone(self) -> None:
        mine = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "python other-guard.py"}]}]}}
        (self.codex / "hooks.json").write_text(json.dumps(mine), encoding="utf-8")
        foreign = self.skills / SKILL
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("남이 만든 스킬", encoding="utf-8")
        rc, out = self.install()
        self.assertEqual(0, rc, out)
        self.assertIn("python other-guard.py", self.commands("PreToolUse"), "남이 건 훅을 지웠습니다")
        self.assertEqual("남이 만든 스킬", (foreign / "SKILL.md").read_text(encoding="utf-8"),
                         "관리 표시 없는 같은 이름 스킬을 덮었습니다")
        self.assertIn("건너뜀", out)

    def test_a_pc_managed_by_the_projection_is_skipped(self) -> None:
        (self.codex / "claude-sync-manifest.json").write_text("{}", encoding="utf-8")
        rc, out = self.install()
        self.assertEqual(0, rc, out)
        self.assertFalse((self.codex / "hooks.json").exists(), "투영이 관리하는 파일을 덮었습니다")
        self.assertFalse(self.skills.exists())

    def test_no_codex_is_reported_not_silent(self) -> None:
        self.codex.rmdir()
        rc, out = self.install()
        self.assertEqual(1, rc)
        self.assertIn("Codex 설치 흔적이 없다", out)


if __name__ == "__main__":
    unittest.main()
