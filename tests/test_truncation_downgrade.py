"""줄바꿈으로 이어진 문단을 절단형 **오류**로 내지 않되, 없애지도 않는지 본다.

**왜 필요한가.** 마크다운은 한 문단을 여러 줄에 나눠 써도 렌더링하면 한 문단이다.
검사기는 줄 하나를 완결된 값으로 보므로, 문장 중간에서 끊긴 줄이 「조사로 끝나
서술어가 잘렸다」로 잡힌다. 실측으로 **절단형 지적 97건 중 49건(51%)**이 이 형태였다.

**고치는 방향을 잘못 잡을 뻔했다.** 처음 낸 안은 「이어진 줄을 붙여서 다시 판정」
이었다. 오탐은 사라지지만 붙인 안쪽의 진짜 절단형이 **영영 안 나온다** — 없앨 수
없는 미탐을 만드는 쪽이다. 사용자 지적으로 방향을 바꿨다.

| 안 | 오탐 | 미탐 |
|---|---|---|
| 줄을 붙여 다시 판정 | 사라짐 | **생김 · 되찾을 길 없음** |
| 등급을 「의심」으로 내림 | 발행을 안 막음 | **0 · 화면에 그대로 남음** |

그래서 이 시험이 지키는 것은 두 가지다 — 강등이 일어나는가, 그리고 **강등된 것이
사라지지 않는가**. 뒤엣것이 본체다.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"

HEAD = "# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"

# 조사로 끝나고 **다음 줄이 이어지는 본문** — 문단 줄바꿈이다
WRAPPED = HEAD + (
    "**여기 없는 의존 하나** — 식단 수집은 그룹웨어 로그인 세션으로\n"
    "아침 작업이 그 세션을 살려 둡니다.\n"
)

# 조사로 끝나고 다음 줄이 새 목록 항목 — 진짜 절단형이다
STANDALONE = HEAD + (
    "- 산출물은 해당 폴더에\n"
    "- **둘째 항목** — 처리 완료\n"
)


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TruncationSeverityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    def scan(self, text):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text(text, encoding="utf-8")
            errors, warnings, _ = self.checker.scan_md(str(target))
        kinds = lambda items: [i[1] if len(i) == 3 else i[0] for i in items]
        return kinds(errors), kinds(warnings)

    def test_a_wrapped_paragraph_is_not_an_error(self) -> None:
        self.assertNotIn("절단형 종결", self.scan(WRAPPED)[0])

    def test_a_wrapped_paragraph_is_still_reported(self) -> None:
        """이 시험이 본체다 — 오탐을 없애려다 지적 자체를 지우면 안 된다."""
        self.assertIn("절단형 의심", self.scan(WRAPPED)[1],
                      "강등이 아니라 삭제가 됐습니다 — 되찾을 수 없는 미탐입니다")

    def test_a_real_truncation_is_still_an_error(self) -> None:
        """다음 줄이 새 항목이면 이어지는 문단이 아니다 — 그대로 오류여야 한다."""
        self.assertIn("절단형 종결", self.scan(STANDALONE)[0])

    def test_nothing_is_lost_in_total(self) -> None:
        """두 문서 모두 절단형 지적이 정확히 하나씩 — 등급만 다르다."""
        for name, text in (("이어진 문단", WRAPPED), ("진짜 절단형", STANDALONE)):
            with self.subTest(document=name):
                errors, warnings = self.scan(text)
                total = errors.count("절단형 종결") + warnings.count("절단형 의심")
                self.assertEqual(total, 1, f"{name}: 절단형 지적이 {total}건입니다")

    def test_the_downgraded_message_says_why(self) -> None:
        """「의심」이라고만 하면 읽는 사람이 무엇을 볼지 모른다."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text(WRAPPED, encoding="utf-8")
            _, warnings, _ = self.checker.scan_md(str(target))
        messages = " ".join(w[2] if len(w) == 3 else w[1] for w in warnings)

        self.assertIn("다음 줄로 이어지는 문단", messages)


if __name__ == "__main__":
    unittest.main()
