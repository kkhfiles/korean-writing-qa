"""우리가 처방한 수정문이 새 문제를 만들지 않는지 고정한다.

**왜.** 규칙에 따라 A를 고치면 B가 생긴다. 개조식으로 줄이다 서술어를 날리고,
영어를 한국어로 바꾸다 뜻이 달라진다. 코드로 치면 정적 검사 지적을 고치다
다른 지적을 만드는 것과 같다 — 그래서 회귀처럼 되돌려 확인해야 한다.

**두 겹으로 본다.**

| 시험 | 무엇을 막나 |
|---|---|
| 심어 넣은 연쇄를 잡는가 | 하네스가 눈이 없는데 통과하는 것 |
| 실제 처방이 연쇄를 만드는가 | 새로 넣은 처방이 다른 규칙을 어기는 것 |

앞의 시험이 없으면 뒤의 0건은 「깨끗하다」가 아니라 「안 봤다」가 된다.

**이 시험이 못 보는 것** — 뜻이 달라지는 연쇄. 「최초 실행이므로 대상이 없다」를
「대상 없음」으로 줄이면 인과가 사라지는데 검사기는 조용하다. 그쪽은
`check_meaning.py` 소관이다.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts import skill_bridge
from scripts.check_fix_cascade import kinds, load_global, pairs

GLOBAL_CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"

# (이름, 수정 전, 수정 후, 새로 생겨야 하는 지적)
INJECTED = [
    ("서술어를 날림", "고칠 것은 코멘트로 표시한다", "고칠 것은 코멘트로", "절단형 의심"),
    ("조사에서 끊음", "자료를 폴더에 저장한다", "자료를 폴더에", "절단형 종결"),
    ("주어를 지시어로", "개발팀이 검토한 결과", "우리가 검토한 결과", "모호한 지칭"),
]
CONTROL = ("제품화 경로를 검토한다", "제품화 단계를 검토한다")


class FixCascadeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not GLOBAL_CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {GLOBAL_CHECKER}")
        cls.check = skill_bridge.load("check")
        cls.rules = cls.check.load_rules()
        cls.global_checker = load_global()

    def new_kinds(self, before: str, after: str):
        return (
            kinds(self.check, self.rules, self.global_checker, after)
            - kinds(self.check, self.rules, self.global_checker, before)
        )

    def test_the_harness_sees_an_injected_cascade(self) -> None:
        """심어 넣은 연쇄를 못 잡으면 아래 0건은 아무 뜻이 없다."""
        for name, before, after, expected in INJECTED:
            with self.subTest(case=name):
                self.assertIn(expected, self.new_kinds(before, after))

    def test_the_harness_is_silent_when_nothing_new_appears(self) -> None:
        """무엇에나 반응하면 0건이 못 나온다 — 잡는 쪽만큼 침묵하는 쪽도 확인한다."""
        self.assertEqual(self.new_kinds(*CONTROL), {})

    def test_no_prescribed_fix_creates_a_new_finding(self) -> None:
        """확정 규칙·문맥 시료·2층 지적의 수정문이 다른 규칙을 어기면 안 된다."""
        offenders = []
        for pair in pairs():
            new = self.new_kinds(pair["before"], pair["after"])
            if new:
                offenders.append(f"{pair['source']} {pair['id']}: {dict(new)}")
        self.assertEqual(offenders, [], "처방이 새 지적을 만듭니다:\n" + "\n".join(offenders))

    def test_the_pair_set_is_not_empty(self) -> None:
        """쌍을 하나도 못 읽으면 위 시험이 조용히 통과한다."""
        collected = pairs()
        self.assertGreaterEqual(len(collected), 40)
        # 문구만 떼어 재면 문장이 아니라는 이유로 없는 연쇄가 잡힌다. 줄을 아는
        # 지적은 원문 줄에 넣어 재야 한다 — 실측 1건이 그 artifact 였다.
        self.assertTrue(any(p.get("whole_line") for p in collected))


if __name__ == "__main__":
    unittest.main()
