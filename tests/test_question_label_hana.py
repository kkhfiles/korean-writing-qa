"""「하나」로 끝나는 의문문 라벨을 잡되 수사 「하나」는 통과시키는지 지킨다.

**어디가 새고 있었나.** 의문문 라벨 규칙의 종결 검사가 `(?<!하)나$` 였다 —
수사 「하나」(「남은 방법은 하나」)를 빼려고 「하」 앞을 막은 것이다. 그 제외가
**의문 어미 「~하나」까지 통째로 빠져나가게** 했다. 「누가 정하나」·「무엇을 하나」·
「왜 제안하나」가 전부 그 형태다.

**무엇으로 가르나 — 앞의 의문사다.** 관형사(어느·몇·얼마)는 뒤에 수사가 올 수 있고
서술어를 요구하지 않는다. 나머지 의문사(무엇·뭐·어디·언제·누가·누구·왜·어떻게)는
서술어를 요구하므로 뒤의 「하나」가 수사일 수 없다.

**실측**(문서 1,629개) — 새로 걸린 것 37건이 **전부 정당한 지적**이고 수사가 잘못
걸린 것은 0건. 사라진 지적도 0건이다(하나 있어 보이던 것은 같은 줄에서 인용되는
구절만 바뀐 것).

**이 시험이 막는 것.** 되돌아가면 의문문 라벨의 한 갈래가 통째로 조용히 빠진다.
반대로 넓히면 사용자가 직접 확정한 교정(「남은 방법 하나」 → 「한 가지」)의 근거가
되는 수사 쓰임이 오탐으로 걸린다.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

#: 잡아야 하는 것 — 의문사가 서술어를 요구하므로 「하나」가 수사일 수 없다
QUESTIONS = [
    "누가 정하나",
    "무엇을 하나",
    "왜 제안하나",
    "어떻게 검증하나",
    "언제 무엇을 하나",
    "어디까지 컨테이너에서 수행하나",
    "2주 뒤에 무엇을 보고 정하나",
]

#: 통과해야 하는 것 — 수사 「하나」 · 관형사 뒤에는 수사가 올 수 있다
NUMERALS = [
    "남은 방법은 하나",
    "선행 확인 하나",
    "고칠 곳은 하나",
    "어느 하나",
    "몇 가지 중 하나",
    "얼마 안 되는 것 하나",
]


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QuestionLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not repo_paths.CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {repo_paths.CHECKER}")
        cls.checker = load_checker()
        cls.source = repo_paths.CHECKER.read_text(encoding="utf-8")

    def test_question_endings_are_caught(self) -> None:
        for text in QUESTIONS:
            with self.subTest(label=text):
                err, _ = self.checker.fragment(text)
                self.assertIsNotNone(err, f"의문문 라벨을 놓쳤습니다: {text}")
                self.assertIn("의문문", err)

    def test_numeral_hana_still_passes(self) -> None:
        """사용자가 직접 확정한 교정의 근거가 되는 쓰임이다 — 넓히면 여기가 깨진다."""
        for text in NUMERALS:
            with self.subTest(value=text):
                err, warn = self.checker.fragment(text)
                self.assertIsNone(err, f"수사 「하나」가 오류로 걸렸습니다: {text} — {err}")
                if warn:
                    self.assertNotIn("의문문", warn, f"수사 「하나」가 걸렸습니다: {text}")

    def test_the_determiners_stay_out_of_the_strong_set(self) -> None:
        """어느·몇·얼마 뒤에는 수사가 올 수 있다 — 여기 넣으면 위 시험이 깨진다."""
        strong = self.checker.QWORD_STRONG.pattern
        for word in ("어느", "몇", "얼마"):
            with self.subTest(word=word):
                self.assertNotIn(word, strong, f"관형사가 강한 의문사 목록에 들어갔습니다: {word}")

    def test_the_exempt_fixture_is_still_clean(self) -> None:
        """짝 시료에 수사 「하나」가 들어 있다 — 규칙을 넓히면 여기서 먼저 깨진다."""
        fixture = Path(__file__).resolve().parent / "fixtures" / "paired" / "exempt-fixture.md"
        if not fixture.is_file():
            self.skipTest(f"시료가 없습니다: {fixture}")
        err, warn, _ = self.checker.scan_md(str(fixture), False, None)
        self.assertEqual(([], []), (err, warn))


if __name__ == "__main__":
    unittest.main()
