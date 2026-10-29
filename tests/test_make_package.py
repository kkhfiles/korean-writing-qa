"""응모 꾸러미에 설치에 필요한 것은 들어가고 연구 기록과 개발 규칙은 빠진다.

**왜 있나** — 압축을 푼 폴더에서 에이전트를 열면 맨 위의 `AGENTS.md`, `CLAUDE.md` 를 읽는다.
저장소의 개발 규칙이 실리면 설치와 무관한 지시가 섞이므로, 꾸러미에서는 설치 안내로 바꿔
넣는다(2026-10-29 계획). 그 안내는 사람도 읽으므로 검사기 오류 0 을 지킨다.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import make_package  # noqa: E402


class MakePackageTests(unittest.TestCase):
    def test_install_files_are_kept(self) -> None:
        for path in ("bootstrap.py", "install.py", "repo_paths.py", "assets/doc-style-check.py",
                     "scripts/korean_qa_run.py", "skills/finalize-korean-document/SKILL.md",
                     "tests/fixtures/paired/exempt-fixture.md", "README.md", "docs/user-guide.md"):
            with self.subTest(path=path):
                self.assertTrue(make_package.wanted(path))

    def test_research_and_dev_rules_are_left_out(self) -> None:
        for path in ("runs/x/notes.md", "docs/archived/review-001.md", "docs/calibration-20260929.md",
                     ".github/workflows/ci.yml", "AGENTS.md", "CLAUDE.md", "korean-qa.toml"):
            with self.subTest(path=path):
                self.assertFalse(make_package.wanted(path))

    def test_install_guide_passes_the_checker(self) -> None:
        done = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "assets" / "doc-style-check.py"),
                               "--no-rules", str(ROOT / "scripts" / "package_agents.md")],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertIn("오류 0", done.stdout, done.stdout)


if __name__ == "__main__":
    unittest.main()
