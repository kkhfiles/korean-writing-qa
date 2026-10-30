"""작업 폴더의 글 파일이 `.gitattributes` 대로 **LF 인지** 본다.

(2026-10-30) `.gitattributes` 가 `eol=lf` 인데 기본 checkout 의 파일 116개가 CRLF 였다. 설치본은
기본 checkout 에서 복사되므로 둘 다 CRLF 라 설치본 대조 시험은 거기서 조용히 통과했고, 새로 만든
작업 트리(LF)에서만 「다름」이 나 세 번을 손으로 조사했다. 저장소 · 설치본 · 설정 백업이 바이트까지
같아야 한다는 약속(`.gitattributes` 머리)이 기본 checkout 에서 깨져 있던 것이다.
고치는 법 — 그 파일을 지우고 `git checkout -- <파일>` 로 다시 꺼낸 뒤 `python install.py`.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WorkingTreeLfTests(unittest.TestCase):

    def test_text_files_are_lf_in_the_working_tree(self) -> None:
        got = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--eol"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        if got.returncode:
            self.skipTest("git 저장소가 아닙니다")
        bad = [line.split("\t", 1)[-1] for line in got.stdout.splitlines()
               if "eol=lf" in line and ("w/crlf" in line or "w/mixed" in line)]
        self.assertEqual([], bad, f"LF 로 둘 파일이 작업 폴더에서 CRLF 입니다 — {len(bad)}개, 앞 다섯: {bad[:5]}")


if __name__ == "__main__":
    unittest.main()
