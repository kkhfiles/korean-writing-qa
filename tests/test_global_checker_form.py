"""전역 문서 검사기의 형식 축이 실제로 그렇게 도는지 고정한다.

**왜 필요한가.** 개조식을 전제한 검사가 산문 문서에서 쏟아진다. 사용자가 쓴 부서
안내 메일에서 「안녕하세요 …입니다.」와 「감사합니다.」까지 오류로 잡혀 아홉 건
전부 오탐이었다(`runs/diagnostic-004`).

**무엇을 지키나.** 두 방향으로 틀릴 수 있고 위험도가 다르다.

| 틀리는 방향 | 결과 |
|---|---|
| 구조 문서를 산문으로 봄 | 정당한 오류의 절반이 조용히 사라짐 — 보이지 않아 더 위험 |
| 산문 문서를 구조로 봄 | 쏟아짐 — 눈에 보이고 표시 한 줄로 고쳐짐 |

그래서 형식은 **선언으로만** 정해지고 산문 비율로 짐작하지 않는다. 여기서는 그
선언 경로와 「형식을 안 적었을 때 물어보는」 경로를 함께 고정한다.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"

PROSE = """# 임베디드 검증 백서

소프트웨어가 안전을 좌우하게 되면서 검증의 무게가 달라졌다. 이 글은 자동화가 무엇을 바꾸는지 다룬다.

## 검증 비용

개발자가 코드를 한 줄 쓰면 검증에는 세 줄이 든다. 이 비율은 등급이 올라갈수록 가팔라진다.

비용의 대부분은 새로 만드는 데 들지 않는다. 이미 만든 것을 고치는 데 든다.

자동 생성 도구는 입력 조합을 기계적으로 늘려 준다. 그 숫자가 결함을 잡는다는 뜻은 아니다.

그래서 자동화의 값은 생성보다 유지에서 나온다. 요구사항을 잇는 일은 사람의 몫이다.
"""

STRUCTURED = """# 검증 자동화 현황

**하반기 검증 범위 · 담당과 일정** — 한 장 조망

## 진행

- **개발 종료**: 10월 30일
- **테스트 시작**: 11월 2일
- **중간 확인**: 6회
"""

# 형식과 무관한 지적이 산문에서도 그대로 나오는지 볼 시료
FORM_NEUTRAL = """# 산출물 정리

**정리 대상과 위치** — 한 장 조망

| 대상 | 비고 |
|---|---|
| 보고서 | 없음 |

- 새 자료는 해당 폴더에
- 우리 팀이 맡는다
"""


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GlobalCheckerFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    def scan(self, text: str, form: str | None = None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "doc.md"
            path.write_text(text, encoding="utf-8")
            errors, warnings, _ = self.checker.scan_md(str(path), False, form)
        return [k for k, _ in errors], [k for k, _ in warnings]

    def test_prose_form_drops_the_structure_only_findings(self) -> None:
        plain, _ = self.scan(PROSE)
        prose, _ = self.scan(PROSE, "prose")

        self.assertIn("서술형 종결", plain)
        self.assertNotIn("서술형 종결", prose)

    def test_prose_form_keeps_the_findings_that_do_not_depend_on_form(self) -> None:
        """산문이라고 다 봐주면 절단형·모호한 지칭까지 사라진다 — 그건 산문에서도 잘못이다."""
        plain, plain_warn = self.scan(FORM_NEUTRAL)
        prose, prose_warn = self.scan(FORM_NEUTRAL, "prose")

        for kind in ("절단형 종결", "모호한 지칭", "스캔 가치 없는 라벨"):
            with self.subTest(kind=kind):
                self.assertIn(kind, plain, f"시료가 {kind} 를 안 냅니다")
                self.assertIn(kind, prose, f"{kind} 는 형식과 무관한데 사라졌습니다")

    def test_the_default_is_unchanged(self) -> None:
        """기본값이 바뀌면 이 검사기를 쓰는 모든 문서의 판정이 조용히 달라진다."""
        self.assertEqual(self.scan(STRUCTURED)[0], self.scan(STRUCTURED, "structured")[0])
        self.assertEqual(self.scan(PROSE)[0], self.scan(PROSE, "structured")[0])

    def test_the_frontmatter_declares_the_form(self) -> None:
        declared = "---\nform: prose\n---\n" + PROSE
        self.assertNotIn("서술형 종결", self.scan(declared)[0])

    def test_a_structured_declaration_keeps_the_full_check(self) -> None:
        declared = "---\nform: structured\n---\n" + PROSE
        self.assertIn("서술형 종결", self.scan(declared)[0])

    def test_an_unknown_frontmatter_value_is_not_trusted(self) -> None:
        """모르는 값을 산문으로 읽으면 오타 한 번에 검사가 통째로 꺼진다.

        영문 오타(`proze`)와 번역어(`산문`)는 걸리는 지점이 다르다 — 앞은 값 확인,
        뒤는 값을 읽는 정규식이다. 둘 다 두지 않으면 한쪽만 지켜진다.
        """
        for value in ("proze", "narrative", "산문"):
            with self.subTest(value=value):
                errors, warnings = self.scan(f"---\nform: {value}\n---\n" + PROSE)

                self.assertIn("서술형 종결", errors)
                # 오타를 선언으로 세면 묻는 줄까지 사라져서 오타를 영영 모른다
                self.assertIn("형식 미표기", warnings)


class UndeclaredFormTests(unittest.TestCase):
    """형식을 안 적었을 때 짐작하지 않고 물어보는지 본다."""

    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    scan = GlobalCheckerFormTests.scan

    def test_a_prose_looking_document_is_asked_about(self) -> None:
        self.assertIn("형식 미표기", self.scan(PROSE)[1])

    def test_a_structured_document_is_not_asked_about(self) -> None:
        """묻는 줄이 흔해지면 아무도 안 읽는다 — 실측 378건에서 1.9%만 걸렸다."""
        self.assertNotIn("형식 미표기", self.scan(STRUCTURED)[1])

    def test_a_declared_document_is_never_asked_about(self) -> None:
        for value in ("prose", "structured"):
            with self.subTest(form=value):
                declared = f"---\nform: {value}\n---\n" + PROSE
                self.assertNotIn("형식 미표기", self.scan(declared)[1])

    def test_the_question_is_a_warning_not_an_error(self) -> None:
        """물어보는 줄이 오류로 나가면 훅이 산문 문서마다 실패한다."""
        errors, warnings = self.scan(PROSE)
        self.assertIn("형식 미표기", warnings)
        self.assertNotIn("형식 미표기", errors)


if __name__ == "__main__":
    unittest.main()
