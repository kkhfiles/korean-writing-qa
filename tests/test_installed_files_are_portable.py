"""설치되는 파일에 작성자 PC 의 저장소 경로가 다시 들어오면 깨진다.

**왜 있나** — 스킬 문서와 훅이 `P:/github/korean-writing-qa/…` 를 기본값으로 적어 두어서,
받은 사람 PC 에서는 설치가 성공하고 첫 사용에서 깨졌다(2026-10-29 확인, 스킬 문서 11곳 ·
스크립트 1 · 훅 1). 설치 시험은 설치까지만 봐서 이것을 못 잡았다. 저장소 도구는
`korean_qa_run.py` 입구로, 저장소 위치는 `install.py` 가 적은 기록으로 찾는다.

**빼는 것** — 정상 판정 목록(`known-words.jsonl`)의 적용 범위는 이 PC 의 경로 무늬라
다른 PC 에서는 맞는 파일이 없을 뿐 깨지지 않는다. `local-` 목록은 각자 PC 의 것이다.
"""

from __future__ import annotations

import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import install  # noqa: E402
import korean_qa_run  # noqa: E402
import repo_paths  # noqa: E402

#: 저장소를 특정 위치로 가정하는 경로 — 드라이브 문자 꼴과 Git Bash 꼴
AUTHOR_REPO = re.compile(r"(?i)(\b[a-z]:[/\\]|/[a-z]/)github[/\\]korean-writing-qa")
SKIP = {"known-words.jsonl"}


class InstalledFilesArePortableTests(unittest.TestCase):
    def test_no_author_repo_path_in_installed_files(self) -> None:
        found = []
        for src, _ in install.pairs():
            if src.name in SKIP or src.name.startswith("local-"):
                continue
            try:
                text = src.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if AUTHOR_REPO.search(line):
                    found.append(f"{src.relative_to(repo_paths.REPO).as_posix()}:{n}")
        self.assertEqual([], found, "설치되는 파일이 작성자 PC 의 저장소 경로를 가정합니다")

    def test_runner_is_installed(self) -> None:
        names = {src.name for src, _ in install.pairs()}
        self.assertIn("korean_qa_run.py", names)


class RunnerFindsTheRepoTests(unittest.TestCase):
    def _fake_repo(self, d: str) -> Path:
        root = Path(d) / "repo"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "hello.py").write_text(
            "import sys\nprint('안녕', *sys.argv[1:])\nraise SystemExit(3)\n", encoding="utf-8")
        return root

    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        saved = list(sys.argv), list(sys.path)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = korean_qa_run.main(argv)
        finally:
            sys.argv[:], sys.path[:] = saved
        return code, out.getvalue(), err.getvalue()

    def test_pointer_written_by_install_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = self._fake_repo(d)
            claude = Path(d) / "claude"
            with mock.patch.object(repo_paths, "REPO", root), \
                 mock.patch.object(repo_paths, "INSTALLED", claude), \
                 redirect_stdout(io.StringIO()):
                install.write_pointer(dry_run=False)
            env = {k: v for k, v in os.environ.items() if k != "KOREAN_WRITING_QA_HOME"}
            env["CLAUDE_HOME"] = str(claude)
            outside = Path(d) / "installed" / "assets"
            outside.mkdir(parents=True)
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(korean_qa_run, "__file__", str(outside / "korean_qa_run.py")):
                code, out, _ = self._run(["hello", "가"])
        self.assertEqual(3, code)
        self.assertIn("안녕 가", out)

    def test_unknown_location_says_how_to_fix(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if k != "KOREAN_WRITING_QA_HOME"}
            env["CLAUDE_HOME"] = str(Path(d) / "empty")
            outside = Path(d) / "installed" / "assets"
            outside.mkdir(parents=True)
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(korean_qa_run, "__file__", str(outside / "korean_qa_run.py")):
                code, _, err = self._run(["hello"])
        self.assertEqual(2, code)
        self.assertIn("install.py", err)

    def test_tool_name_is_a_plain_name(self) -> None:
        code, _, _ = self._run(["../evil"])
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
