"""훅이 산문 판정을 스스로 하지 않는지 고정한다.

**왜.** 훅은 서술형 지적 수를 세어 개조식 부류를 접었다. 실측하니 문서 378건 중
44건에서 접혔고 **그중 40건이 산문이 아니었다** — 표와 라벨이 뼈대인 문서에 근거
문단이 붙은 형태다. 그 문서에서 맞는 지적 1,043건이 발행 직전에 가려졌다.

**고친 방향.** 접는 판정을 검사기 한 곳으로 모은다. 훅은 검사기가 「형식 미표기」로
물어볼 때만 산문으로 한 번 더 물어보고, 무엇을 뺄지는 검사기가 정한다.

**두 방향 다 지킨다** — 산문에서 쏟아지지 않아야 하고, 구조 문서에서 조용해지면
안 된다. 뒤쪽이 더 위험하다(안 보이므로).
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

HOOK = Path.home() / ".claude" / "hooks" / "doc-style-gate.py"

PROSE = """# 임베디드 검증 백서

소프트웨어가 안전을 좌우하게 되면서 검증의 무게가 달라졌다. 이 글은 자동화가 무엇을 바꾸는지 다룬다.

## 검증 비용

개발자가 코드를 한 줄 쓰면 검증에는 세 줄이 든다. 이 비율은 등급이 올라갈수록 가팔라진다.

비용의 대부분은 새로 만드는 데 들지 않는다. 이미 만든 것을 고치는 데 든다.

자동 생성 도구는 입력 조합을 기계적으로 늘려 준다. 그 숫자가 결함을 잡는다는 뜻은 아니다.

그래서 자동화의 값은 생성보다 유지에서 나온다. 요구사항을 잇는 일은 사람의 몫이다.
"""

# 표와 라벨이 뼈대인데 근거 문단이 붙은 문서 — 예전 훅이 잘못 접던 형태
MIXED = """# 검증 자동화 현황

**하반기 검증 범위 · 담당과 일정** — 한 장 조망

## 일정

| 단계 | 날짜 | 담당 |
|---|---|---|
| 개발 종료 | 10월 30일 | 개발팀 |
| 테스트 시작 | 11월 2일 | 검증팀 |
| 데모 확인 | 11월 9일 | 실장 |
| 최종 보고 | 11월 16일 | 파트장 |

## 대상 모듈

- **핵심 엔진**: 4개
- **연동 모듈**: 7개
- **화면**: 3개
- **배치**: 2개
- **외부 연계**: 1개
- **공통 라이브러리**: 5개

## 근거

측정값이 기준을 넘었다. 그래서 일정을 앞당겼다.

담당자가 한 명 늘었다. 손이 덜 간다.

되돌릴 수 있다. 지난 분기에 같은 방식으로 했다.
"""


def load_hook():
    spec = importlib.util.spec_from_file_location("doc_style_gate", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocStyleGateFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HOOK.is_file():
            raise unittest.SkipTest(f"훅이 없습니다: {HOOK}")
        cls.hook = load_hook()

    def gate(self, text: str, name: str = "doc.md", errors_only: bool = False) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / name
            path.write_text(text, encoding="utf-8")
            return self.hook.run_checker(str(path), errors_only)

    def test_the_hook_no_longer_counts_findings_to_guess_prose(self) -> None:
        """세는 방식이 남아 있으면 같은 오판이 되돌아온다."""
        source = HOOK.read_text(encoding="utf-8")
        self.assertNotIn("PROSE_MARK", source)

    def test_a_mixed_document_keeps_its_outline_findings(self) -> None:
        """가장 위험한 방향 — 구조 문서가 조용해지면 아무도 못 알아챈다."""
        out = self.gate(MIXED)

        self.assertIn("서술형 종결", out)
        self.assertNotIn("산문으로 보고", out)

    def test_an_undeclared_prose_document_is_folded_and_explained(self) -> None:
        out = self.gate(PROSE)

        self.assertNotIn("서술형 종결", out)
        self.assertIn("form: prose", out)

    def test_a_declared_prose_document_is_folded_without_the_note(self) -> None:
        out = self.gate("---\nform: prose\n---\n" + PROSE)

        self.assertNotIn("서술형 종결", out)
        self.assertNotIn("형식을 안 적어", out)

    def test_a_declared_structured_document_keeps_everything(self) -> None:
        """선언이 접기를 이긴다 — 사람이 개조식이라고 하면 개조식으로 본다."""
        out = self.gate("---\nform: structured\n---\n" + PROSE)

        self.assertIn("서술형 종결", out)

    def test_writing_time_still_shows_only_the_media_neutral_rules(self) -> None:
        """쓰는 순간의 소음 억제는 형식 축과 별개다 — 함께 지운 적이 있어 고정한다."""
        out = self.gate(MIXED, errors_only=True)

        self.assertNotIn("서술형 종결", out)


class CondenseTests(unittest.TestCase):
    """반복되는 지적을 접는지 본다.

    **왜.** 화면에 뜨는 것은 열두 줄뿐이다. 조언 문구가 매번 같은 지적이 안
    접히면 그 한 종류가 열두 칸을 다 먹는다 — 실측으로 발행 직전 화면의 46%가
    「값 안 굵게」 하나였고 문서 9%는 화면이 그것만으로 채워졌다.

    **접으면 안 되는 것도 있다** — 문장이 실리는 지적은 매번 다른 문장을
    가리키므로 접으면 어느 문장인지 사라진다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not HOOK.is_file():
            raise unittest.SkipTest(f"훅이 없습니다: {HOOK}")
        cls.hook = load_hook()

    def test_identical_advice_collapses_into_one_line(self) -> None:
        lines = [
            f"   ⚠️  [값 안 굵게] {n}행  굵게 1개 더 — 라벨이 굵으면 값에서 또 굵게 하지 않는다"
            for n in (21, 38, 44)
        ]
        out = self.hook.condense(lines)

        self.assertEqual(len(out), 1)
        self.assertIn("3곳", out[0])

    def test_different_sentences_stay_separate(self) -> None:
        """접으면 어느 문장이 문제인지 사라진다."""
        lines = [
            "   ❌ [서술형 종결] 39행  둘의 성격이 다르다",
            "   ❌ [서술형 종결] 48행  린터를 만들지 않는다.",
        ]
        out = self.hook.condense(lines)

        self.assertEqual(len(out), 2)

    def test_the_same_quoted_term_still_collapses(self) -> None:
        """예전부터 되던 것이 깨지지 않았는지 본다."""
        lines = [
            f"   ❌ [모호한 지칭] {n}행  「우리」 — 서로 다른 앞뒤 문장 {n}"
            for n in (11, 20, 33)
        ]
        out = self.hook.condense(lines)

        self.assertEqual(len(out), 1)
        self.assertIn("3곳", out[0])

    def test_a_line_that_does_not_parse_is_kept(self) -> None:
        """접기 규칙에 안 맞는 줄을 버리면 안내문이 사라진다."""
        note = "(형식을 안 적어 산문으로 보고 개조식 지적을 뺐다)"
        self.assertEqual(self.hook.condense([note]), [note])


if __name__ == "__main__":
    unittest.main()
