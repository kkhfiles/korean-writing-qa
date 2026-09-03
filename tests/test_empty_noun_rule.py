"""「관형형 + 빈 명사」를 시료로 고정한다 — 넣은 셋과 뺀 셋을 함께 못 박는다.

**왜 검사기로 옮겼나.** 같은 함정에 세 번 걸렸다(자리 → 판·창 → 값). 글로 적어 둔
규칙으로는 안 막힌 것이라 기계로 옮긴다 — 글로벌 CLAUDE.md 「같은 함정에 두 번
넘어가면 글이 아니라 기계로 옮긴다」.

**여섯 낱말이 같은 대접을 받지 않는다.** 실문서 1,161개로 따로 쟀다.

| 낱말 | 발화 | 정당 | 처리 | 근거 |
|---|---|---|---|---|
| 판·창 | 0 | — | 넣음 | 발화 0이라 넣는 값이 안 듦 · 「안 나온다」는 접을 근거가 아님 |
| 결 | 1(깨진 문자열) | 1 | 넣음 | 「같은 결」·「한 결」만 빼면 남는 오탐 없음 |
| 값 | 9 | 8 | **안 넣음** | 「코드가 계산하는 값」 — 값이 혼자 섬 |
| 축 | 4 | 4 | **안 넣음** | 「못 보는 축」 — 분류 축은 실물 |
| 층 | 2 | 2 | **안 넣음** | 「읽는 층」 — 두 층 구조의 그 층 |

**뺀 셋은 빈도가 아니라 정밀도로 잘랐다.** 「이 뭉치에 안 나와서」가 아니라 **나왔고
전부 정당해서**다. 두 관문은 다르다 — 채택은 항목으로, 정밀도는 실측으로.

**주의로만 낸다.** 「뜨는 창」은 진짜 창이고 「3판」은 책의 판본일 수 있다. 줄만 보고
안 갈리는 갈래는 발행을 막지 않고 읽는 층으로 내려보낸다.
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"
HEAD = "# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"
KIND = "지어낸 명사구"

# 뭉치에 없어서 **만든** 시료다. 앞 셋은 사용자가 실제로 고친 말이다.
POSITIVE = [
    ("모으는 창", "- 답을 모으는 창은 이틀"),
    ("무르는 창", "- 무르는 창이 지나면 확정"),
    ("앞 판 — 조사가 붙은 형태", "- 앞 판에서 잰 값과 대조"),
    ("같은 판 — 판에는 지시어 예외 없음", "- 같은 판에서 다시 잼"),
    ("차수 1판", "- 1판 결과는 폐기"),
    ("차수 2판 — 가운뎃점", "- 2판·3판 비교표"),
    ("다음 판", "- 다음 판 설계는 미정"),
    ("가르는 결", "- 셋을 가르는 결로 삼음"),
]

# 실문서에서 실제로 나온 정당한 문장이다 — 걸리면 그 문장이 오탐이 된다.
NEGATIVE = [
    ("같은 결 — 굳은 쓰임", "- 협업 톤과 같은 결"),
    ("한 결 — 굳은 쓰임", "- 앞 규칙과 한 결로 묶음"),
    ("뜨는 창 — 실물", "- 설치 중 뜨는 관리자 권한 창"),
    ("여는 창 — 실물", "- 설정을 여는 창에서 지정"),
    ("같은 창 — 이미 있는 것을 가리킴", "- 수동 실행이 같은 창에 떨어진다"),
    ("다른 창 — 이미 있는 것을 가리킴", "- 다른 창에서 돌린 결과"),
    ("보는 결과 — 낱말 안쪽", "- 나눠 보는 결과 표"),
    ("나오는 판단 — 낱말 안쪽", "- 판정에서 나오는 판단 근거"),
    ("하는 창구 — 낱말 안쪽", "- 접수하는 창구 일원화"),
    ("2023판 — 연도 판본", "- 시드 도구가 2023판 반영"),
    ("연결 — 낱말 안쪽", "- 끊긴 연결 복구"),
    # 실측으로 뺀 셋 — 되살아나면 여기서 막힌다
    ("계산하는 값 — 뺀 낱말", "- 코드가 계산하는 값"),
    ("못 보는 축 — 뺀 낱말", "- 감시기가 못 보는 축"),
    ("읽는 층 — 뺀 낱말", "- 줄만 봐선 안 갈려 읽는 층 소관"),
    ("나오는 값 — 뺀 낱말", "- 나오는 값을 그대로 적음"),
]


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EmptyNounTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()
        cls.source = CHECKER.read_text(encoding="utf-8")

    def findings(self, line: str):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text(HEAD + line + "\n", encoding="utf-8")
            errors, warnings, _ = self.checker.scan_md(str(target))
        kind = lambda item: item[1] if len(item) == 3 else item[0]  # noqa: E731
        return ([kind(i) for i in errors], [kind(i) for i in warnings])

    def test_each_coined_phrase_is_caught(self) -> None:
        for name, line in POSITIVE:
            with self.subTest(case=name):
                _, warnings = self.findings(line)
                self.assertIn(KIND, warnings)

    def test_normal_korean_is_left_alone(self) -> None:
        """굳은 쓰임·실물·낱말 안쪽, 그리고 실측으로 뺀 셋."""
        for name, line in NEGATIVE:
            with self.subTest(case=name):
                errors, warnings = self.findings(line)
                self.assertNotIn(KIND, errors + warnings)

    def test_it_only_warns(self) -> None:
        """「뜨는 창」이 진짜 창이고 「3판」이 판본일 수 있어 발행을 막지 않는다."""
        errors, warnings = self.findings("- 답을 모으는 창은 이틀")

        self.assertIn(KIND, warnings)
        self.assertNotIn(KIND, errors)

    def html_findings(self, value: str):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.html"
            target.write_text(
                "<h1>검토 결과</h1><p><b>하반기 검토 범위</b> — 한 장 조망</p>"
                f"<dl><dt>기한</dt><dd>{value}</dd></dl>",
                encoding="utf-8")
            errors, warnings, _ = self.checker.scan_html(str(target))
        kind = lambda item: item[1] if len(item) == 3 else item[0]  # noqa: E731
        return [kind(i) for i in (*errors, *warnings)]

    def test_html_path_sees_it_too(self) -> None:
        """규칙을 썼다 ≠ 규칙이 적용된다 — 제목 검사가 HTML 경로에만 빠졌던 전례가 있다."""
        self.assertIn(KIND, self.html_findings("답을 모으는 창은 이틀"))

    def test_html_path_keeps_the_same_exemptions(self) -> None:
        """두 경로가 같은 예외를 쓰는지도 본다 — 한쪽만 빠지는 것이 실제 실패 모양이다."""
        for name, value in (("같은 결", "협업 톤과 같은 결"),
                            ("뜨는 창", "설치 중 뜨는 관리자 권한 창")):
            with self.subTest(case=name):
                self.assertNotIn(KIND, self.html_findings(value))

    def test_the_three_measured_out_nouns_stay_out(self) -> None:
        """값·축·층을 되살리면 실문서 15건이 전부 오탐으로 돌아온다."""
        rule = re.search(r"EMPTY_NOUN = re\.compile\((.*?)\n\n", self.source, re.S)
        self.assertIsNotNone(rule, "EMPTY_NOUN 규칙을 못 찾았습니다")
        for noun in ("값", "축", "층"):
            with self.subTest(noun=noun):
                self.assertNotIn(noun, rule.group(1),
                                 f"「{noun}」이 규칙에 들어왔습니다 — 실측 오탐을 되살립니다")

    def test_the_reason_for_leaving_them_out_is_recorded(self) -> None:
        """빈도로 뺀 것이 아니라 정밀도로 뺐다는 것이 남아 있어야 다시 안 넣는다."""
        self.assertIn("혼자 서기 때문", self.source)
        self.assertIn("빈도가 아니라 정밀도로 잘랐다", self.source)

    def test_the_tail_is_defined_once(self) -> None:
        """꼬리를 두 벌로 두면 한쪽만 고쳐진다 — 실제로 겪은 실패다."""
        self.assertEqual(self.source.count("_NOUN_TAIL = "), 1)
        self.assertIn("_NOUN_TAIL", self.source.split("_NOUN_TAIL = ")[1])
