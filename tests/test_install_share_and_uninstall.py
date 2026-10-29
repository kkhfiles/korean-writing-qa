"""공유용 설치는 한글 검사 훅만 걸고, 설치 해제는 이 설치기가 넣은 것만 지운다.

**왜 있나** — `--hooks` 가 한글 검사와 무관한 작성자의 개인 훅 둘(셸 겹 역슬래시 차단, 공개
저장소 push 차단)까지 받은 사람 PC 에 걸었고, 지우는 방법이 없었다(2026-10-29 확인). 처음
쓰는 사람에게 「되돌릴 수 있나」는 설치를 정하는 조건이다. 작성자 PC 는 개인 설정 파일
(`data/catalog/local-install-personal.txt`) 하나로 지금 동작을 유지한다.
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install  # noqa: E402
import repo_paths  # noqa: E402

FOREIGN = {"type": "command", "command": "python other-tool.py"}


def hook_commands(settings: Path) -> list[str]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    return [h["command"] for groups in data.get("hooks", {}).values()
            for g in groups for h in g.get("hooks", [])]


class InstallShareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "claude"
        self.home.mkdir()
        self.settings = self.home / "settings.json"
        self.settings.write_text(json.dumps(
            {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [FOREIGN]}]}}), encoding="utf-8")
        self.patches = [mock.patch.object(repo_paths, "INSTALLED", self.home)]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def _install(self, personal: bool) -> None:
        with mock.patch.object(install, "personal", return_value=personal), redirect_stdout(io.StringIO()):
            install.do_install(dry_run=False)
            install.wire_hooks(dry_run=False)

    def test_share_install_wires_only_korean_hooks(self) -> None:
        self._install(personal=False)
        commands = hook_commands(self.settings)
        for name in install.PERSONAL_HOOKS:
            self.assertFalse(any(name in c for c in commands), name)
            self.assertFalse((self.home / "hooks" / name).exists(), name)
        self.assertTrue(any("doc-style-gate.py" in c for c in commands))
        self.assertIn(FOREIGN["command"], commands)
        self.assertTrue(self.settings.with_suffix(".json.bak").is_file(), "설정을 고치기 전 백업")

    def test_personal_switch_keeps_every_hook(self) -> None:
        self._install(personal=True)
        commands = hook_commands(self.settings)
        for name in install.HOOK_FILES:
            self.assertTrue(any(name in c for c in commands), name)

    def test_uninstall_removes_only_ours(self) -> None:
        self._install(personal=False)
        skill_dir = next(p for p in (self.home / "skills").iterdir() if p.is_dir())
        mine = skill_dir / "my-note.md"
        mine.write_text("사용자가 넣은 파일\n", encoding="utf-8")
        self.assertTrue(install.pointer().is_file())
        with mock.patch.object(install, "personal", return_value=False), redirect_stdout(io.StringIO()):
            install.uninstall(dry_run=False, codex=False)
        self.assertEqual([FOREIGN["command"]], hook_commands(self.settings))
        self.assertFalse(install.pointer().exists())
        self.assertEqual([], [d for _, d in install.pairs() if d.exists()])
        self.assertTrue(mine.is_file(), "사용자가 넣은 파일은 남김")
        leftover = [p for p in (self.home / "skills").iterdir() if p != skill_dir]
        self.assertEqual([], leftover, "비게 된 스킬 폴더는 지움")

    def test_uninstall_dry_run_writes_nothing(self) -> None:
        self._install(personal=False)
        before = sorted(p for p in self.home.rglob("*"))
        with mock.patch.object(install, "personal", return_value=False), redirect_stdout(io.StringIO()):
            install.uninstall(dry_run=True, codex=False)
        self.assertEqual(before, sorted(p for p in self.home.rglob("*")))


if __name__ == "__main__":
    unittest.main()
