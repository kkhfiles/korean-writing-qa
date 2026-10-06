"""「낯선 사내 용어」 갈래가 사람이 읽는 문서에서만 걸리는지 고정한다.

**왜 이 갈래가 생겼나**(2026-10-06 사용자 — 「정본 이라는 단어는 익숙하지 않은데」).
공개 소개 페이지에 「md 파일 하나가 정본입니다」가 나갔다. 사내 지시 파일에서
「정본」은 「여기가 기준이다」를 뜻하는 정해 둔 말이라, 그 관례가 소개 글로 옮아간 것이다.
형태소 분석이 「정본」을 한 낱말로 안 잡아 단어 점검이 원리적으로 못 본다.

**지켜야 하는 것이 셋이다** — 사람이 읽는 문서에서는 걸림 · 낱말 속의 「정본」(수정본·
검정본)은 안 걸림 · Claude 만 읽는 지시 파일(SKILL.md 등)에서는 빠짐. 셋째가 깨지면
지시 파일을 고칠 때마다 같은 주의가 쌓인다.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HEAD = "---\nform: prose\n---\n\n# 시험\n\n**검사 대상** — 한 줄\n\n"
KIND = "낯선 사내 용어"


def run(name: str, body: str, sub: str = "") -> str:
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d) / sub if sub else Path(d)
        folder.mkdir(parents=True, exist_ok=True)
        p = folder / name
        p.write_text(HEAD + body, encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(p), "--no-rules", "-v"],
            capture_output=True, text=True, encoding="utf-8").stdout


class UnfamiliarTermTests(unittest.TestCase):
    def test_caught_in_a_human_document(self) -> None:
        for line in ("- md 파일 하나가 정본입니다.", "- 정본은 노션에 둡니다.", "- 정본도 함께 고칩니다."):
            self.assertIn(KIND, run("page.md", line + "\n"), line)

    def test_words_that_merely_contain_it_are_clean(self) -> None:
        out = run("page.md", "- 수정본과 검정본을 비교합니다.\n")
        self.assertNotIn(KIND, out)

    def test_spared_in_claude_instruction_files(self) -> None:
        line = "- 설정 정본은 이 파일입니다.\n"
        self.assertNotIn(KIND, run("SKILL.md", line))
        self.assertNotIn(KIND, run("notes.md", line, sub="skills/x"))
        # 같은 줄이 사람이 읽는 문서에서는 걸려야 위 두 줄이 뜻을 가진다
        self.assertIn(KIND, run("notes.md", line))


if __name__ == "__main__":
    unittest.main()
