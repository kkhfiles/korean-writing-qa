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

    def test_anonymize_removes_every_author_trace(self) -> None:
        """익명 응모용 꾸러미(2026-11-03 사용자 결정) — 문서가 바뀌어 무늬가 빗나가면 여기서 깨진다."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for rel in make_package.ANONYMIZE:
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                (dest / rel).write_bytes((ROOT / rel).read_bytes())
            self.assertEqual(make_package.anonymize(dest), [])
            owner = make_package.owner_pattern()
            for rel in make_package.ANONYMIZE:
                for n, line in enumerate((dest / rel).read_text(encoding="utf-8").splitlines(), 1):
                    with self.subTest(at=f"{rel}:{n}"):
                        self.assertIsNone(make_package.IDENTIFYING.search(line), line)
                        if owner:
                            self.assertIsNone(owner.search(line), line)

    def test_context_terms_are_replaced_outside_font_blobs(self) -> None:
        """부서와 도구 이름은 저장소 밖 목록대로 꾸러미에서만 바꾼다(2026-11-12 사용자 결정).
        심은 서체의 base64 안에서 우연히 맞은 글자는 건드리지 않는다."""
        import tempfile
        blob = "QUJD" * 12 + "ZETA" + "QUJD" * 12
        with tempfile.TemporaryDirectory() as tmp:
            dest, lst = Path(tmp) / "pkg", Path(tmp) / "list.txt"
            dest.mkdir()
            lst.write_text("# 보기\nZETA => NOVA\nZETA 랩 => 사내\n", encoding="utf-8")
            (dest / "a.md").write_text("ZETA 랩 세미나 · ZETA를 붙여\n", encoding="utf-8")
            (dest / "b.html").write_text(f"<style>src:url(data:font/woff2;base64,{blob})</style>\n",
                                         encoding="utf-8")
            count, left = make_package.replace_context(dest, make_package.context_terms(lst))
            self.assertEqual((dest / "a.md").read_text(encoding="utf-8"), "사내 세미나 · NOVA를 붙여\n")
            self.assertIn(blob, (dest / "b.html").read_text(encoding="utf-8"))
            self.assertEqual((count, left), (2, []))

    def test_package_tool_is_left_out(self) -> None:
        """가리는 무늬가 적힌 도구 자신이 꾸러미에 실리면 그 무늬가 곧 작성자 단서다."""
        for path in ("scripts/make_package.py", "tests/test_make_package.py"):
            self.assertFalse(make_package.wanted(path))

    def test_owner_name_is_caught_before_a_korean_particle(self) -> None:
        """「\\b」는 한글도 낱말 글자로 봐 「<계정>이 만든」을 놓쳤다(2026-11-03 검토)."""
        from unittest import mock
        done = subprocess.CompletedProcess([], 0, stdout="https://github.com/someone/repo.git\n")
        with mock.patch.object(make_package.subprocess, "run", return_value=done):
            owner = make_package.owner_pattern()
        for line in ("개발자 someone이 만든", "someone의 저장소", "(someone)"):
            self.assertIsNotNone(owner.search(line), line)
        self.assertIsNone(owner.search("someones 와 nosomeone"))

    def test_install_guide_passes_the_checker(self) -> None:
        done = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "assets" / "doc-style-check.py"),
                               "--no-rules", str(ROOT / "scripts" / "package_agents.md")],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertIn("오류 0", done.stdout, done.stdout)


if __name__ == "__main__":
    unittest.main()
