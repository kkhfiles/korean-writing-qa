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


    def test_a_quoted_frontmatter_value_still_counts(self) -> None:
        """YAML 도구가 따옴표를 붙인다. 안 받아 주면 선언한 사람은 왜 계속 묻는지 모른다."""
        for quote in ('"', "'"):
            with self.subTest(quote=quote):
                declared = f"---\nform: {quote}prose{quote}\n---\n" + PROSE
                errors, warnings = self.scan(declared)

                self.assertNotIn("서술형 종결", errors)
                self.assertNotIn("형식 미표기", warnings)


class CommandLineFormTests(unittest.TestCase):
    """`--form` 이 뒤에 오는 파일 이름을 삼키지 않는지 본다.

    값을 이름으로 걸러 내면 `--form prose` 뒤의 `prose.md` 같은 이름이 조용히
    검사 목록에서 빠진다. 빠진 파일은 통과로 보이므로 눈에 안 띈다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")

    def run_cli(self, *argv: str, cwd: str | None = None) -> str:
        import subprocess
        import sys

        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(CHECKER), *argv],
            capture_output=True, text=True, encoding="utf-8", cwd=cwd,
        )
        return done.stdout

    def test_the_file_after_the_flag_is_still_scanned(self) -> None:
        """이름이 플래그 값과 같아도 검사한다. 빠진 파일은 통과처럼 보인다."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "structured.md"
            path.write_text(PROSE, encoding="utf-8")

            out = self.run_cli("--form", "structured", str(path))

        self.assertIn("structured.md", out)
        # 실제로 본문까지 봤다는 증거 — 이름만 찍고 넘어간 것이 아니다
        self.assertIn("서술형 종결", out)

    def test_a_target_named_exactly_like_the_value_is_still_scanned(self) -> None:
        """값을 이름으로 걸러 내면 같은 이름의 대상이 통째로 빠진다.

        플래그 값을 지우는 방법은 두 가지다 — 그 자리를 빼거나, 그 글자를 빼거나.
        뒤쪽은 `--form prose` 로 `prose` 디렉터리를 검사할 때 대상이 사라진다.
        """
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "prose"
            target.mkdir()
            (target / "doc.md").write_text(PROSE, encoding="utf-8")

            out = self.run_cli("--form", "prose", "prose", cwd=directory)

        self.assertIn("doc.md", out)

    def test_an_unknown_flag_value_is_refused(self) -> None:
        self.assertIn("--form 은", self.run_cli("--form", "narrative", "x.md"))


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


class SkillWiringTests(unittest.TestCase):
    """형식 축을 쓰라는 지시가 스킬에 실제로 닿는지 본다.

    검사기에 플래그를 만들어 놓고 스킬이 안 부르면 규칙은 존재만 하고 효력이 0이다.
    실제로 이 세션이 그렇게 만들었다가 재검토에서 잡았다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from scripts import skill_bridge

        cls.home = skill_bridge.skill_home()
        cls.check = skill_bridge.load("check")
        cls.types = (cls.home / "references" / "document-types.md").read_text(encoding="utf-8")
        cls.skill = (cls.home / "SKILL.md").read_text(encoding="utf-8")

    def test_every_profile_declares_a_form(self) -> None:
        """새 문서 종류가 형식 없이 들어오면 어느 쪽으로 검사할지 아무도 모른다."""
        for profile in self.check.PROFILE_SCOPES:
            with self.subTest(profile=profile):
                row = next(
                    (l for l in self.types.splitlines() if l.startswith(f"| `{profile}`")),
                    None,
                )
                self.assertIsNotNone(row, f"{profile} 가 document-types.md 표에 없습니다")
                self.assertTrue(
                    "구조형" in row or "산문형" in row,
                    f"{profile} 행에 형식이 없습니다: {row}",
                )

    def test_the_skill_tells_you_to_pass_the_form(self) -> None:
        self.assertIn("--form prose", self.skill)

    def test_the_document_types_page_shows_the_command(self) -> None:
        self.assertIn("--form prose", self.types)

    def test_prose_documents_without_a_profile_are_routed(self) -> None:
        """백서·설명문에는 전용 값이 없다. 어디로 갈지 안 적으면 찾다가 못 찾는다."""
        for word in ("백서", "설명문"):
            with self.subTest(word=word):
                self.assertIn(word, self.types)
        self.assertIn("form: prose", self.types)


if __name__ == "__main__":
    unittest.main()
