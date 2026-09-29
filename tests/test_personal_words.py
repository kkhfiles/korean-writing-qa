"""개인 낱말 목록 — 저장소 밖 파일에 각자 채운 동사를 1층이 「주의」로 낸다.

**왜 있나** — 사용자 결정(2026-09-29 「1층에서 별도 명시하는 파일을 두고, 개인이 채워넣는
방식을 사용하면 된다」). 입말 동사(잡다·재다)는 흔한 낱말이라 단어 점검이 못 보고, 공용
규칙으로 하나씩 넣으면 「낱말을 하나씩 더하기」가 된다. 말뭉치로 목록을 만들면 명사에 사람
이름이 섞여 공개 저장소로 나갈 수 있다. 그래서 목록은 각자의 기계에만 둔다.

**놓을 쪽** — 명사를 적은 줄은 그 명사 뒤의 동사만 본다(「균형을 잡다」는 안 걸림).
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

HEAD = "---\nform: prose\n---\n\n# 시험\n\n**검사 대상** — 한 줄\n\n"


def has_kiwi() -> bool:
    try:
        import kiwipiepy  # noqa: F401
    except Exception:
        return False
    return True


class PersonalWordsTests(unittest.TestCase):
    def run_checker(self, rows: str, body: str) -> str:
        with tempfile.TemporaryDirectory() as d:
            words = Path(d) / "words.tsv"
            words.write_text(rows, encoding="utf-8")
            doc = Path(d) / "t.md"
            doc.write_text(HEAD + body, encoding="utf-8")
            env = {**os.environ, "KOREAN_QA_PERSONAL_WORDS": str(words)}
            return subprocess.run([sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(doc),
                                   "--no-rules", "-v"], capture_output=True, text=True,
                                  encoding="utf-8", env=env).stdout

    @unittest.skipUnless(has_kiwi(), "형태소 분석기가 없다")
    def test_a_verb_with_its_noun_is_caught_and_other_objects_are_not(self) -> None:
        out = self.run_checker("# 주석\n잡다\t결함\t검출\t보고서 검토\n",
                               "- 주입한 결함을 잡는 테스트입니다.\n- 두 기준 사이에서 균형을 잡았습니다.\n")
        self.assertIn("개인 목록 · 「검출」 쪽으로 · 보고서 검토", out)
        self.assertIn("9행", out)
        self.assertNotIn("10행  「잡았습니다.」", out)

    @unittest.skipUnless(has_kiwi(), "형태소 분석기가 없다")
    def test_an_empty_noun_means_everywhere(self) -> None:
        out = self.run_checker("부르다\t\t호출\t\n", "- 새로고침 함수가 다시 불러옵니다.\n- 함수를 부릅니다.\n")
        self.assertIn("「부릅니다.」 — 개인 목록 · 「호출」 쪽으로", out)

    def test_a_pinned_missing_file_turns_it_off(self) -> None:
        """지정한 파일이 없으면 목록이 없는 것 — 끄는 길이다(제품 이름 목록과 같은 규칙)."""
        with tempfile.TemporaryDirectory() as d:
            doc = Path(d) / "t.md"
            doc.write_text(HEAD + "- 결함을 잡는 테스트입니다.\n", encoding="utf-8")
            env = {**os.environ, "KOREAN_QA_PERSONAL_WORDS": str(Path(d) / "없음.tsv")}
            out = subprocess.run([sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(doc),
                                  "--no-rules", "-v"], capture_output=True, text=True,
                                 encoding="utf-8", env=env).stdout
        self.assertNotIn("개인 목록", out)


if __name__ == "__main__":
    unittest.main()
