"""「자리」 예외를 실제 좌석으로 좁힌 것을 못 박는다.

**무엇을 뒤집었나.** 예전 예외 목록은 「사람이 모이는 상황」까지 통과시켰다 —
`받는`·`묻는`·`말하는`·`듣는`·`나누는`·`모이는`·`이야기하는`·`보고하는`·`배우는`·
`가르치는` 열 개. 2026-09-04 사용자 판단으로 열 개를 다 뺐다.

**까닭 둘.**

| 번호 | 무엇 | 근거 |
|---|---|---|
| ① | 모임을 「자리」로 부르는 것 자체가 권할 말이 아님 | 「의견을 받는 자리」보다 「의견을 수렴하는 회의」가 무엇인지를 밝힘 |
| ② | 모임 뜻을 넣으려다 은유까지 통과시킴 | 실문서 2,551개에서 통과 28건 중 은유 7건 · 화면의 입력 칸을 가리키는 「묻는 자리」가 미탐 |

**좁혀도 오류는 안 는다.** `JARI_OK` 는 `JARI`(오류)가 아니라 `JARI_ANY`(주의)만
막는다. 실측으로도 오류 18건 그대로 · 새로 주의가 되는 것 9건.

**이 시험이 막는 것.** 「오탐이 났다」는 신고 한 건에 열 개를 도로 넣는 일. 되살리려면
이 시험을 먼저 고쳐야 하고, 그때 위 실측을 다시 봐야 한다.
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
import unittest
from pathlib import Path

CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"
HEAD = "# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"
WARN = "「~하는 자리」 의심"
ERROR = "「~하는 자리」"

# 뺀 열 개 — 실문서에서 실제로 나온 문장 모양이다.
NOW_WARNED = [
    ("묻는 자리 — 화면의 입력 칸(예전 미탐)", "- 무엇이 있나를 묻는 자리라 한 칸에 못 둠"),
    ("받는 자리 — 은유", "- 낱말로 가르면 정작 못 받는 자리가 생김"),
    ("말하는 자리 — 대화방 은유", "- 봇끼리만 말하는 자리에서는 묻힘"),
    ("모이는 자리 — 모이는 곳", "- 시험 결과가 모이는 자리"),
    ("듣는 자리 — 모임", "- 연구소장이 처음 듣는 자리라 층 구조부터 설명"),
    ("보고하는 자리 — 모임", "- 보고하는 자리에서 결정함"),
    ("나누는 자리 — 모임", "- 의견을 나누는 자리"),
    ("이야기하는 자리 — 모임", "- 편하게 이야기하는 자리로 잡음"),
    ("배우는 자리 — 모임", "- 새로 배우는 자리를 마련"),
    ("가르치는 자리 — 모임", "- 가르치는 자리는 따로 둠"),
]

# 남긴 것 — 실제 좌석과 굳은 쓰임. 걸리면 그 문장이 오탐이 된다.
STILL_EXEMPT = [
    ("앞자리", "- 앞자리에 앉은 사람부터 확인"),
    ("빈자리", "- 빈자리 두 개를 채움"),
    ("옆 자리", "- 옆 자리로 옮김"),
    ("같은 자리 — 굳은 쓰임", "- 같은 자리에 같은 라벨"),
    ("제자리", "- 제자리로 되돌림"),
    ("자기 자리", "- 자기 자리를 지킴"),
    ("첫 자리", "- 첫 자리를 비워 둠"),
    ("뒷자리", "- 뒷자리에서 화면이 안 보임"),
    ("윗 자리", "- 윗 자리로 올림"),
    ("아랫 자리", "- 아랫 자리로 내림"),
    ("앉는 자리", "- 앉는 자리를 미리 정함"),
    ("드나드는 자리", "- 드나드는 자리라 문을 열어 둠"),
]

# 예전에도 오류였던 것 — 좁히기가 이 판정을 건드리면 안 된다.
STILL_ERROR = [
    ("넣을 자리", "- 규칙을 넣을 자리"),
    ("새는 자리", "- 표 칸이 특히 새는 자리"),
    ("걸리는 자리", "- 실패 모드가 그대로 걸리는 자리"),
]

DROPPED_STEMS = ["받는", "묻는", "말하는", "듣는", "나누는",
                 "모이는", "이야기하는", "보고하는", "배우는", "가르치는"]


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SeatExemptionTests(unittest.TestCase):
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

    def test_gathering_and_metaphor_now_surface(self) -> None:
        for name, line in NOW_WARNED:
            with self.subTest(case=name):
                _, warnings = self.findings(line)
                self.assertIn(WARN, warnings)

    def test_it_only_warns(self) -> None:
        """모임 뜻인지 은유인지는 줄만 봐서 안 갈린다 — 발행을 막지 않는다."""
        for name, line in NOW_WARNED:
            with self.subTest(case=name):
                errors, _ = self.findings(line)
                self.assertNotIn(WARN, errors)
                self.assertNotIn(ERROR, errors)

    def test_real_seats_stay_exempt(self) -> None:
        for name, line in STILL_EXEMPT:
            with self.subTest(case=name):
                errors, warnings = self.findings(line)
                self.assertNotIn(WARN, errors + warnings)
                self.assertNotIn(ERROR, errors + warnings)

    def test_document_metaphors_stay_errors(self) -> None:
        """좁히기가 오류 판정을 건드리지 않았는지 — 실측 18건이 그대로여야 한다."""
        for name, line in STILL_ERROR:
            with self.subTest(case=name):
                errors, _ = self.findings(line)
                self.assertIn(ERROR, errors)

    def test_the_ten_stems_stay_out(self) -> None:
        """오탐 신고 한 건에 열 개를 도로 넣지 못하게 목록 자체를 못 박는다."""
        rule = re.search(r"JARI_OK = re\.compile\((.*?)\)\n", self.source, re.S)
        self.assertIsNotNone(rule, "JARI_OK 규칙을 못 찾았습니다")
        for stem in DROPPED_STEMS:
            with self.subTest(stem=stem):
                self.assertNotIn(
                    stem, rule.group(1),
                    f"「{stem} 자리」를 예외로 되살리려면 실문서 재측정이 먼저입니다")

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

    def test_html_path_moved_too(self) -> None:
        """규칙을 썼다 ≠ 규칙이 적용된다 — 두 경로가 같은 목록을 쓰는지 본다."""
        self.assertIn(WARN, self.html_findings("무엇이 있나를 묻는 자리라 한 칸에 못 둠"))
        self.assertNotIn(WARN, self.html_findings("같은 자리에 같은 라벨"))

    def test_the_written_rule_matches_the_checker(self) -> None:
        """글로벌 규칙이 아직 「사람이 모이는 상황」을 정당하다고 적어 두면 안 된다."""
        rules = Path.home() / ".claude" / "CLAUDE.md"
        if not rules.is_file():
            self.skipTest(f"글로벌 규칙 파일이 없습니다: {rules}")
        text = rules.read_text(encoding="utf-8")
        self.assertNotIn("정당한 쓰임 — 사람이 모이는 상황과 실제 좌석", text)
        self.assertIn("모임을 「자리」로 부르지 않음", text)


if __name__ == "__main__":
    unittest.main()
