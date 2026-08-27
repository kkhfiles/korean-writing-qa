"""`core-rules.md` 의 담당 표시가 실제 검사기와 맞는지 확인한다.

**왜 시험이 필요한가.** 스킬 작업 순서 8단계는 「검사기가 못 잡는 것을 직접 찾으라」고
지시하고, 무엇이 안 잡히는지는 이 표시가 알려 준다. 표시가 낡으면 두 방향으로 틀린다 —
이미 잡히는 것을 또 보거나, **안 잡히는 것을 잡힌 줄 알고 건너뛴다.** 뒤쪽이 위험하다.

규칙을 `[사람]` 에서 `[스킬]` 로 옮기는 것이 이 프로젝트의 본 작업이므로 표시는 자주
바뀐다. 바뀔 때 문서도 함께 고치도록 여기서 막는다.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from scripts import skill_bridge

GLOBAL_CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"
# 진입점·제목이 없으면 검사기가 뼈대를 지적해 본문 판정을 가린다. 본문은 늘 7행이다.
SKELETON = "# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n- {line}\n"
BODY_LINE = "7행"

# (원칙, 대표 문장, core-rules.md 에 적은 담당)
CASES = [
    ("압축한 명사구 풀기", "테스트를 만드는 구간에서 공수가 든다는 뜻", "사람"),
    ("막연한 비유 — 경로", "제품화 경로를 검토", "스킬"),
    ("막연한 비유 — 자리", "규칙을 넣을 자리를 정함", "전역"),
    ("실무 행위 밝히기", "이 문제를 AI로 푼다는 뜻", "사람"),
    ("계획과 결과 구분", "커버리지를 더 올린다는 뜻", "사람"),
    ("번역투", "검증 자동화에 대한 검토 결과", "사람"),
    ("불필요한 영어", "TEST 자동화 도입 검토", "사람"),
    ("기계적 병렬", "첫째 항목임. 둘째 항목임. 셋째 항목임", "사람"),
    ("장식 — 평가 수식어", "강력한 검증 엔진 도입", "전역"),
    ("장식 — 뜻 없는 이모지", "🟢 진행 중 · 🟡 검토 중", "사람"),
    ("군더더기 지우기", "또한 그리고 아울러 검토를 수행함", "사람"),
    ("소리 내어 읽기 — 절단형", "산출물은 해당 폴더에", "전역"),
]


def load_global_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", GLOBAL_CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CoreRulesMarkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not GLOBAL_CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {GLOBAL_CHECKER}")
        cls.check = skill_bridge.load("check")
        cls.rules = cls.check.load_rules()
        cls.global_checker = load_global_checker()
        cls.core_rules = (
            skill_bridge.skill_home() / "references" / "core-rules.md"
        ).read_text(encoding="utf-8")

    def responsible_layer(self, line: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text(SKELETON.format(line=line), encoding="utf-8")
            skill_hit = bool(
                self.check.scan_files(
                    [target], self.rules, "general_it_business", False, "general"
                )["findings"]
            )
            errors, warnings, _ = self.global_checker.scan_md(str(target))
            global_hit = any(
                message.startswith(BODY_LINE) for _, message in (*errors, *warnings)
            )
        if skill_hit:
            return "스킬"
        return "전역" if global_hit else "사람"

    def test_each_marker_matches_the_checkers(self) -> None:
        for name, line, claimed in CASES:
            with self.subTest(principle=name):
                self.assertEqual(
                    self.responsible_layer(line),
                    claimed,
                    f"{name}: core-rules.md 의 담당 표시가 실제 검사기와 다릅니다",
                )

    def test_the_english_rule_keeps_its_two_exemptions(self) -> None:
        """오탐 판정에서 나온 예외가 지워지면 같은 오탐이 되돌아온다.

        사용자 판정으로 「포지셔닝」은 업계에 굳은 말이라 대상이 아니고, 「에이전틱」은
        뜻이 같은 대체어가 없어 지적 자체가 성립하지 않는다고 갈렸다. 검사기가 보는
        규칙이 아니라 사람이 읽는 지침이므로 **지워지는 것만** 여기서 막는다 — 이
        시험은 지침이 실제로 지켜지는지는 재지 못한다.
        """
        for phrase in ("업계에 굳은 외래어", "뜻이 같은 대체어가 없는 말"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.core_rules)

    def test_the_exemptions_name_the_cases_they_came_from(self) -> None:
        """근거가 된 실제 표현이 없으면 다음 사람이 예외의 범위를 못 가른다."""
        for term in ("포지셔닝", "에이전틱"):
            with self.subTest(term=term):
                self.assertIn(term, self.core_rules)

    def test_core_rules_states_who_checks_each_principle(self) -> None:
        """표시 자체가 사라지면 8단계가 근거를 잃는다."""
        for marker in ("`[사람]`", "`[스킬: 경로]`", "`[전역: 자리]`"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.core_rules)


if __name__ == "__main__":
    unittest.main()
