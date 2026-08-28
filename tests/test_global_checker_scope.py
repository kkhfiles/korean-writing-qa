"""전역 검사기가 「낱말과 문장」 밖으로 나가지 않는지 고정한다.

**왜.** 이 검사기의 목적은 한글이 똑바로 써졌는지 보는 것이다. 굵게 개수·묶음
행 수 같은 **시각 서식**은 그 축이 아닌데도 검사에 들어 있었고, 실측하니 문서
380건에서 주의 2,546건 중 2,239건(88%)이 그 셋이었다. 훅은 열두 줄만 보여 주므로
그 셋이 화면을 먹으면 정작 봐야 할 낱말 지적이 안 뜬다.

**되돌아오기 쉬운 변경이다** — 규칙 하나 추가는 세 줄이면 되고, 추가한 사람은
그것이 목적 밖인지 모른다. 그래서 이름으로 못 박는다.

**함께 고정하는 것 — 「스캔 가치 없는 라벨」의 등급.** 이건 서식이 아니라 낱말
선택이라 남겼지만 **주의**다. 걸린 것의 57%가 표 머리 「비고」인데 공문서 표의
표준 관례라 발행을 막을 근거가 못 된다.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"

# 뺀 검사 셋 — 이름이 되살아나면 목적 밖으로 나간 것이다
VISUAL_KINDS = ("값 안 굵게", "강조 과다", "묶음 과대")

# 굵게가 줄마다 여럿 · 한 묶음 열두 행 — 예전 검사기가 세 종류를 다 내던 시료
HEAVY = """---
form: structured
---
# 검증 자동화 현황

**하반기 검증 범위 · 담당과 일정** — 한 장 조망

## 대상

- **핵심 엔진**: 4개 · **연동 모듈** 7개
- **화면**: 3개 · **배치** 2개
- **외부 연계**: 1개 · **공통 라이브러리** 5개
- **회귀 시료**: 12벌 · **성능 시료** 3벌
- **담당**: 검증팀 · **확인** 실장
- **개발 종료**: 10월 30일 · **테스트 시작** 11월 2일
- **데모 확인**: 11월 9일 · **최종 보고** 11월 16일
- **되돌리기**: 지난 분기 방식 · **근거** 실측
- **위험**: 인력 · **완화** 한 명 증원
- **도구**: 내부 하네스 · **버전** 3.2
- **보고 주기**: 주 1회 · **경로** 실장 보고
- **미결**: 외부 연계 일정 · **기한** 9월 5일
"""

# 표 머리 「비고」 하나만 있는 문서 — 이제 발행을 막으면 안 된다
REMARK_TABLE = """---
form: structured
---
# 도구 조사 결과

**조사한 도구 · 직전 대비 변화** — 한 장 조망

| 도구 | 직전 확인 상태 | 비고 |
|---|---|---|
| 도구 가 | 2026-03 출시 | 신규 발표 없음 |
| 도구 나 | 2026-02 통합 | 웹세미나 예정 |
"""

# 목록 라벨 경로 — 표 머리와 코드가 갈라져 있어 따로 밟아야 한다(돌연변이로 확인)
REMARK_LIST = """---
form: structured
---
# 도구 조사 결과

**조사한 도구 · 직전 대비 변화** — 한 장 조망

- **도구 가**: 2026-03 출시
- **참고**: 제품 페이지와 릴리즈 노트
"""


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckerScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    def scan_md(self, text: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "doc.md"
            path.write_text(text, encoding="utf-8")
            err, warn, _ = self.checker.scan_md(str(path))
        return [kind_of(i) for i in err], [kind_of(i) for i in warn]

    def scan_html(self, text: str):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "doc.html"
            path.write_text(text, encoding="utf-8")
            err, warn, _ = self.checker.scan_html(str(path))
        return [kind_of(i) for i in err], [kind_of(i) for i in warn]

    def test_markdown_no_longer_measures_visual_formatting(self) -> None:
        err, warn = self.scan_md(HEAVY)

        for kind in VISUAL_KINDS:
            with self.subTest(kind=kind):
                self.assertNotIn(kind, err)
                self.assertNotIn(kind, warn)

    def test_html_no_longer_measures_visual_formatting(self) -> None:
        """마크다운만 빼면 아티팩트 경로로 같은 소음이 되돌아온다."""
        body = ("<dl>" + "".join(
            f"<dt>라벨 {n}</dt><dd><b>값</b> · <b>덧붙임</b></dd>" for n in range(12)
        ) + "</dl>" + "".join(
            f"<li><b>머리 {n}</b> — <b>또 굵게</b></li>" for n in range(4)
        ))
        err, warn = self.scan_html(body)

        for kind in VISUAL_KINDS:
            with self.subTest(kind=kind):
                self.assertNotIn(kind, err)
                self.assertNotIn(kind, warn)

    def test_the_wording_checks_still_run(self) -> None:
        """서식을 빼면서 함께 지우면 검사기가 통째로 조용해진다 — 반대 방향을 잡는다."""
        err, _ = self.scan_md(
            "---\nform: structured\n---\n"
            "# 점검 결과\n\n"
            "**점검 대상 · 결과** — 한 장 조망\n\n"
            "- **판정**: 우리 쪽 기준으로는 통과한다.\n"
        )

        self.assertIn("서술형 종결", err)
        self.assertIn("모호한 지칭", err)

    def test_a_remarks_column_no_longer_blocks_publishing(self) -> None:
        """「비고」는 공문서 표의 표준 관례다 — 주의로는 보이되 오류는 아니다."""
        for name, text in (("표 머리", REMARK_TABLE), ("목록 라벨", REMARK_LIST)):
            with self.subTest(경로=name):
                err, warn = self.scan_md(text)

                self.assertNotIn("스캔 가치 없는 라벨", err)
                self.assertIn("스캔 가치 없는 라벨", warn)
                self.assertEqual(err, [], f"이 문서는 발행 기준을 통과해야 합니다: {err}")

    def test_the_label_check_is_still_a_warning_in_html(self) -> None:
        err, warn = self.scan_html('<dl><dt>비고</dt><dd>값</dd></dl>')

        self.assertNotIn("스캔 가치 없는 라벨", err)
        self.assertIn("스캔 가치 없는 라벨", warn)


def kind_of(item):
    """md 는 (행, 종류, 사유) · html 은 (종류, 사유) 로 낸다."""
    return item[1] if len(item) == 3 else item[0]


if __name__ == "__main__":
    unittest.main()
