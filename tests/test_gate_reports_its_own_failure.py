"""훅이 검사를 **못 돌렸을 때** 그것을 알리는지 고정한다.

**왜 열렸나** — 2026-09-03 아키텍처 검토. 훅의 두 검사기가 실패할 때 정반대로
행동하고 있었다.

| 부순 것 | 그때 훅이 낸 것 |
|---|---|
| 스킬 검사기 없음 | 「검사기 없음」을 경로까지 찍어 알림 |
| 전역 검사기 없음 | **아무 말 없음** · 지적의 대부분을 내는 쪽이 조용히 죽음 |

발행하는 사람에게 「지적 없음」과 「검사 못 함」이 구별되지 않았다. `SKILL.md` 10단계
「검사 실패와 검사할 수 없음을 합격으로 처리하지 않는다」가 훅에서 깨져 있었다.

**둘째 결함 — 문서가 자기 지적을 지웠다.** 값 슬롯 미인식을 「출력 어딘가에 `검사
불가`라는 글자가 있나」로 판정해서, 문서 **본문**에 그 말이 든 줄이 지적으로 실리면
그 파일의 지적이 통째로 사라졌다. 이 저장소 문서 여럿이 그 말을 쓴다.

**침묵이 맞는 자리도 있다** — 아무도 안 거르는 감시 보고가 그렇다. 훅 보고는 사람이
읽으므로 알리는 쪽이다(`references/work-principles.md` 「검사·규칙을 설계할 때」).
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HOOK = repo_paths.hook("doc-style-gate.py")

# 값 슬롯이 잡히고 오류가 하나 나는 가장 단순한 문서
DOC = ("# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"
       "- 산출물은 해당 폴더에\n")
# 같은 문서인데 본문에 「검사 불가」가 지적으로 실린다 — 예전에는 이것이 전부를 지웠다
DOC_WITH_PHRASE = DOC + "- 그 판정은 검사 불가로\n"
# 값 슬롯이 안 잡히는 마크업 — 검사기가 「⛔ … 값 슬롯 미인식」을 실제로 낸다.
# 그러면서 잡을 수 있는 것(모호한 지칭)은 잡으므로 부분 검사 처리도 함께 볼 수 있다.
NO_SLOTS = ("<h1>검토 결과</h1>\n"
            "<div><span>산출물은 해당 폴더에</span></div>\n"
            "<div><span>우리 제품이 먼저 대응함</span></div>\n")


def load_hook():
    spec = importlib.util.spec_from_file_location("doc_style_gate", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GateReportsItsOwnFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HOOK.is_file():
            raise unittest.SkipTest(f"훅이 없습니다: {HOOK}")
        cls.hook = load_hook()

    def gate(self, text: str) -> str:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "doc.md"
            path.write_text(text, encoding="utf-8")
            return self.hook.run_checker(str(path), False)

    def test_a_missing_checker_is_announced(self) -> None:
        """전역 검사기 파일이 사라지면 그 사실이 발행 화면에 떠야 한다."""
        original = self.hook.CHECKER
        self.hook.CHECKER = original.with_name("no-such-checker.py")
        try:
            out = self.gate(DOC)
        finally:
            self.hook.CHECKER = original

        self.assertIn("못 돌렸다", out)
        self.assertIn("검사기 없음", out)

    def test_a_crashing_checker_is_announced(self) -> None:
        """실행이 안 되거나 시간이 넘으면 그것도 알린다 — 빈 결과로 바꾸지 않는다."""
        original = self.hook.call_checker
        self.hook.call_checker = lambda *a, **k: None
        try:
            out = self.gate(DOC)
        finally:
            self.hook.call_checker = original

        self.assertIn("못 돌렸다", out)

    def test_an_unexaminable_file_is_announced(self) -> None:
        """값 슬롯을 못 찾은 파일은 합격이 아니라 **안 본 것**이다.

        흉내가 아니라 **진짜 검사기 출력**으로 잰다. 흉내로 재면 내 흉내와 내
        정규식이 맞는 것만 증명되고, 검사기가 그 줄 모양을 바꾸면 훅이 조용히
        어긋난 채로 시험은 초록으로 남는다.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "noslots.html"
            path.write_text(NO_SLOTS, encoding="utf-8")
            out = self.hook.run_checker(str(path), False)

        self.assertIn("안 본 것", out)

    def test_a_partial_check_still_shows_what_it_did_find(self) -> None:
        """알림만 내고 지적을 버리면 실제로 잡은 오류가 사라진다."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "noslots.html"
            path.write_text(NO_SLOTS, encoding="utf-8")
            out = self.hook.run_checker(str(path), False)

        self.assertIn("안 본 것", out)
        self.assertIn("모호한 지칭", out)

    def test_the_phrase_in_a_document_does_not_erase_its_findings(self) -> None:
        """본문에 「검사 불가」가 있어도 그 파일의 지적은 그대로 나와야 한다."""
        plain = self.gate(DOC)
        with_phrase = self.gate(DOC_WITH_PHRASE)

        self.assertIn("절단형 종결", plain)
        self.assertIn("절단형 종결", with_phrase,
                      "본문의 낱말이 그 파일의 지적을 지웠습니다")

    def test_the_prose_retry_judges_by_the_line_shape_too(self) -> None:
        """같은 함수에 판정이 두 곳 있다 — 한 곳만 고치면 다른 곳이 남는다.

        산문 재검사도 「출력에 ⛔ 글자가 있나」로 보고 있었다. 그러면 본문에 그
        기호를 쓴 산문 문서는 접기가 조용히 멈춰 개조식 지적이 쏟아진다.
        """
        prose = ("# 임베디드 검증 백서\n\n"
                 "소프트웨어가 안전을 좌우하게 되면서 검증의 무게가 달라졌다. "
                 "이 글은 자동화가 무엇을 바꾸는지 다룬다.\n\n"
                 "## 검증 비용\n\n"
                 # ⛔ 가 **지적 줄에 실려야** 이 경로를 지난다 — 산문 모드에서도
                 # 남는 낱말 지적(모호한 지칭)과 같은 줄에 둔다.
                 "개발자가 코드를 한 줄 쓰면 검증에는 세 줄이 든다. "
                 "⛔ 우리 팀은 그 한계를 안다.\n\n"
                 "비용의 대부분은 새로 만드는 데 들지 않는다. 이미 만든 것을 고치는 데 든다.\n\n"
                 "자동 생성 도구는 입력 조합을 기계적으로 늘려 준다. "
                 "그 숫자가 결함을 잡는다는 뜻은 아니다.\n\n"
                 "그래서 자동화의 값은 생성보다 유지에서 나온다. "
                 "요구사항을 잇는 일은 사람의 몫이다.\n")
        out = self.gate(prose)

        # 「form: prose」 로 단정하면 안 갈린다 — 접기가 멈춘 쪽의 「형식 미표기」
        # 안내 줄에도 그 글자가 들어 있다. 갈리는 것은 개조식 지적이 남았는지다.
        self.assertNotIn("서술형 종결", out,
                         "본문의 ⛔ 기호가 산문 접기를 멈췄습니다")

    def test_the_marker_is_matched_on_the_line_shape(self) -> None:
        """글자 대조로 되돌리면 같은 함정이 되살아난다 — 줄 모양으로 봐야 한다."""
        source = HOOK.read_text(encoding="utf-8")

        self.assertIn("BLIND", source)
        self.assertNotIn('"검사 불가" in out', source)

    def test_a_clean_document_still_says_nothing(self) -> None:
        """알리기로 바꾼 것이 깨끗한 문서까지 시끄럽게 만들면 안 된다."""
        clean = ("# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"
                 "- **기한** 10월 30일\n")

        self.assertEqual(self.gate(clean), "")
