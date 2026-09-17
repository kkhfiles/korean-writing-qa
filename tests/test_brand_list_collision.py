"""목록 검사기가 **묻힌 음차**를 잡는지 본다.

**왜 있나**(2026-09-17). 예방용으로 넣은 「아콘」이 실문서에서
「우아콘(WOOWACON)」에 걸렸다. 목록에 「겹치는 말은 없나」라고 적어 두고도
넣기 전에 확인하지 않았다 — **글로 적는 것으로는 안 지켜져서** 도구로 옮겼다.

이 갈래는 **오류** 등급이라 헛짚으면 발행이 막힌다. 그래서 잡는 쪽뿐 아니라
**정상을 안 잡는 쪽**도 함께 지킨다 — 「디베라에서」의 조사는 겹침이 아니다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

SCRIPT = repo_paths.REPO / "scripts" / "check_brand_list.py"


def run(doc: str, brands: str | None):
    """목록과 문서를 임시로 만들어 검사기를 부른다."""
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "doc.md").write_text(doc, encoding="utf-8")
        env = dict(os.environ)
        if brands is None:
            # 지정한 자리가 없으면 검사기가 목록을 끈다
            env["KOREAN_QA_BRANDS"] = str(Path(d) / "없는파일.txt")
        else:
            listing = Path(d) / "brands.txt"
            listing.write_text(brands, encoding="utf-8")
            env["KOREAN_QA_BRANDS"] = str(listing)
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPT), d],
            capture_output=True, text=True, encoding="utf-8", env=env)
        return done.returncode, (done.stdout or "") + (done.stderr or "")


class BrandListCollisionTests(unittest.TestCase):

    def test_a_buried_transliteration_is_caught(self) -> None:
        """실제로 겪은 그 모양으로 짠다 — 「우아콘」 안의 「아콘」."""
        rc, out = run("우아콘(WOOWACON) 2025 가 열립니다.\n",
                      "ARCHON = 아콘\n")
        self.assertEqual(1, rc, f"묻힌 음차를 못 잡습니다:\n{out}")
        self.assertIn("아콘", out)
        self.assertIn("우아콘", out)

    def test_a_particle_is_not_a_collision(self) -> None:
        """뒤에 붙는 조사·어미는 정상이다 — 잡으면 목록을 못 쓴다."""
        rc, out = run("디베라에서 프로젝트를 인식합니다. 디베라가 돕니다.\n",
                      "DVERA = 디베라\n")
        self.assertEqual(0, rc, f"조사를 겹침으로 셉니다:\n{out}")
        self.assertIn("묻힌 음차 없음", out)

    def test_it_says_so_when_there_is_no_list(self) -> None:
        """목록은 각자 기계에만 있다 — 없는 것이 정상이고 그렇다고 적는다."""
        rc, out = run("아무 글.\n", None)
        self.assertEqual(0, rc)
        self.assertIn("제품 이름 목록이 없습니다", out)

    def test_it_asks_for_a_path(self) -> None:
        """자기 글에 대고 봐야 뜻이 있다 — 경로 없이 통과시키지 않는다."""
        with tempfile.TemporaryDirectory() as d:
            listing = Path(d) / "brands.txt"
            listing.write_text("ACME = 애크미\n", encoding="utf-8")
            env = dict(os.environ)
            env["KOREAN_QA_BRANDS"] = str(listing)
            done = subprocess.run(
                [sys.executable, "-X", "utf8", str(SCRIPT)],
                capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(2, done.returncode,
                         "경로 없이 0 으로 끝나면 통과로 읽힙니다")
        self.assertIn("문서 경로를 주십시오", done.stdout)


if __name__ == "__main__":
    unittest.main()
