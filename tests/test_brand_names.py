"""제품·상표 이름의 정본 표기 — 목록은 저장소 밖에 있고 **있으면 읽는다.**

**왜 이 모양인가.** 이 저장소는 공개다. 전역 규칙이 「가리개를 만들 때 가릴 대상을
코드에 적지 않는다 — 그 코드가 곧 명단이다」라고 못 박았다. 그래서 규칙은 모두가
나눠 쓰고 **이름은 각자 자기 기계에만** 둔다. 신원 목록이 쓰는 방식과 같다.

**넣을 것은 자사 제품 이름뿐.** 실측(문서 272개) — 「노션」 96회·「슬랙」 72회·
「지라」 56회가 전부 정당했고, 음차가 실제로 문제였던 것은 자사 제품 이름 하나(10회)다.
「음차 금지」로 넓히면 정상 224건이 걸린다.

**목록이 없으면 안 본다 · 안 봤다고 적는다.** 조용히 넘기면 「오류 0」이 통과인지 안
본 것인지 갈리지 않는다.
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

EXAMPLE = repo_paths.REPO / "data" / "catalog" / "local-brand-names.example.txt"
HEAD = "---\nform: structured\n---\n\n# 이름 시험\n\n"

#: 본보기의 이름은 지어낸 것이다 — 실제 제품 이름을 시험에 적지 않는다.
LIST = "ACME = 애크미, 액미\nFooBase = 푸베이스\n# 주석 줄\n\n"


def check(doc: str, brands: str | None):
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "doc.md"
        target.write_text(HEAD + doc, encoding="utf-8")
        env = dict(os.environ)
        if brands is None:
            # 아무 파일도 못 찾게 한다 — 있는 목록을 우연히 읽으면 시험이 헛돈다
            env["KOREAN_QA_BRANDS"] = str(Path(d) / "없는파일.txt")
            env["HOME"] = d
            env["USERPROFILE"] = d
        else:
            listing = Path(d) / "brands.txt"
            listing.write_text(brands, encoding="utf-8")
            env["KOREAN_QA_BRANDS"] = str(listing)
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(target)],
            capture_output=True, text=True, encoding="utf-8", env=env)
        return done.stdout or ""


class BrandNameTests(unittest.TestCase):
    def test_the_example_file_ships_and_the_real_one_does_not(self) -> None:
        """본보기는 저장소에 있고 실제 목록은 gitignore 대상이다."""
        self.assertTrue(EXAMPLE.is_file(), f"본보기가 없다: {EXAMPLE}")
        ignore = (repo_paths.REPO / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/catalog/local-brand-names.txt", ignore)

    def test_the_example_holds_no_real_product_name(self) -> None:
        """⛔ 본보기에 진짜 이름을 적으면 그 파일이 곧 명단이다."""
        text = EXAMPLE.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.strip().startswith("#") or "=" not in line:
                continue
            with self.subTest(line.strip()):
                self.assertIn(line.split("=")[0].strip(), ("ACME", "FooBase"),
                              "본보기에는 지어낸 이름만 적는다")

    def test_a_transliteration_is_caught(self) -> None:
        out = check("- **음차** — 애크미 검증 도구\n", LIST)
        self.assertIn("제품 이름 음차", out)
        self.assertIn("ACME", out)

    def test_the_canonical_form_passes(self) -> None:
        out = check("- **정본** — ACME 검증 도구\n", LIST)
        self.assertNotIn("제품 이름 음차", out)

    def test_a_settled_tool_name_is_not_caught(self) -> None:
        """⛔ 「노션」·「슬랙」은 정착한 표기다 — 목록에 없으면 안 걸려야 한다."""
        out = check("- **게시** — 노션에 올리고 슬랙으로 알림\n", LIST)
        self.assertNotIn("제품 이름 음차", out)

    def test_without_a_list_it_says_it_did_not_look(self) -> None:
        """침묵은 합격이 아니다 — 안 봤으면 안 봤다고 적는다."""
        out = check("- **음차** — 애크미 검증 도구\n", None)
        self.assertNotIn("제품 이름 음차", out)
        self.assertIn("제품 이름 안 봄", out)
        self.assertIn("local-brand-names.example.txt", out)

    def test_the_rule_is_registered_so_it_can_be_turned_off(self) -> None:
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), "--list-rules"],
            capture_output=True, text=True, encoding="utf-8")
        self.assertIn("제품 이름 음차", done.stdout)


if __name__ == "__main__":
    unittest.main()
