"""규칙 후보 판정표 — 「이 규칙을 넣을까요?」 표가 규칙 전용 카드로 나가고, 받은 답이 종류별로 바르게 묶이는지 본다.

(2026-10-29 사용자 — 규칙을 넣을 때도 판정표로 묻고, 모양은 「규칙 전용 칸을 더함」)

**지키는 것**
- 양식(`template`)이 규칙 후보 표로 읽히고, 카드에 잡을 문장과 잡으면 안 될 문장이 함께 나오나
- 답 단추가 공통 규칙, 개인 규칙, 넣지 않음, 보류이고 「직접」 입력칸이 없나
- 제출한 답이 표의 답 칸에 적히고 `read` 가 종류별로 묶나 · 대화 답(「의견대로, 단 …」)도 읽나
- 넷 가운데 하나가 아닌 답과 보류, 빈칸은 「끝난 것」으로 세지 않나(종료 코드 1)
- 사람 확인 표(고칠 문장 판정)는 그대로 고칠 문장 카드로 나가나
"""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ask_sheet_html as sheet_html  # noqa: E402
import rule_sheet  # noqa: E402

ROW2 = ("| 2 | 「업무 목록은 늘 있었다」류 상투 도입 | 업무 목록은 늘 있었습니다 | 목록을 매일 갱신합니다 |"
        " 실문서 600편 중 3편 | 주의 | 개인 규칙(사용자 취향) |  |\n")


def sheet_md() -> str:
    return rule_sheet.template("시험 회차") + ROW2


class RuleSheetTests(unittest.TestCase):
    def test_template_is_a_rule_sheet(self) -> None:
        sheet = sheet_html.parse(sheet_md())
        self.assertEqual("rule", sheet["kind"])
        self.assertEqual(["1", "2"], [r["id"] for r in sheet["groups"][0]["rows"]])
        self.assertEqual({"kind": "개인 규칙", "text": "", "note": "사용자 취향"},
                         sheet["groups"][0]["rows"][1]["op"])

    def test_rule_card_shows_both_sides_and_rule_answers(self) -> None:
        page = sheet_html.render(sheet_html.parse(sheet_md()))
        for label in ("잡을 문장", "잡으면 안 될 문장", "실문서 오탐", "등급", "이 규칙을 넣을까요?"):
            self.assertIn(label, page)
        for kind in sheet_html.RULE_KINDS:
            self.assertIn(f'data-pick="{kind}"', page)
        self.assertNotIn('data-pick="고침"', page)
        self.assertNotIn('<input class="direct"', page, "규칙 판정표에 「직접」 입력칸이 나왔습니다")
        self.assertIn('<mark class="hit">결함을 잡습니다</mark>', page)

    def test_fix_sheet_still_renders_fix_cards(self) -> None:
        md = ("# 판정\n\n## 문서\n\n| # | 원문 | 고친 말 | 고친 이유 | 제 의견 | 답 |\n|---|---|---|---|---|---|\n"
              "| 1 | 검사가 **꺼짐** | 비활성화됨 | 입말 | 고침 |  |\n")
        page = sheet_html.render(sheet_html.parse(md))
        self.assertIn('data-pick="고침"', page)
        self.assertNotIn('data-pick="공통 규칙"', page)

    def test_submitted_answers_are_grouped(self) -> None:
        md = sheet_html.fill_answers(sheet_md(), {"1": {"kind": "공통 규칙"}, "2": {"kind": "넣지 않음"}})
        out = rule_sheet.read(md)
        self.assertEqual(["1"], [i["id"] for i in out["공통 규칙"]])
        self.assertEqual(["2"], [i["id"] for i in out["넣지 않음"]])

    def test_chat_reply_as_opinion_with_exception(self) -> None:
        out = rule_sheet.read(sheet_md(), ["의견대로, 단 2 넣지 않음"])
        self.assertEqual(["1"], [i["id"] for i in out["공통 규칙"]])
        self.assertEqual(["2"], [i["id"] for i in out["넣지 않음"]])

    def test_open_answers_keep_exit_code_one(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rules.md"
            p.write_text(sheet_html.fill_answers(sheet_md(), {"1": {"kind": "보류"}}), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rc = rule_sheet.main(["read", str(p)])
            self.assertEqual(1, rc, buf.getvalue())
            self.assertIn("안 고름 1건", buf.getvalue())
            p.write_text(sheet_md().replace("| 개인 규칙(사용자 취향) |  |", "| 개인 규칙(사용자 취향) | 나중에 |"),
                         encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                self.assertEqual(1, rule_sheet.main(["read", str(p)]))
            self.assertIn("알 수 없는 답 1건", buf.getvalue())

    def test_a_fix_sheet_is_refused_by_read(self) -> None:
        md = ("# 판정\n\n## 문서\n\n| # | 원문 | 고친 말 | 고친 이유 | 제 의견 | 답 |\n|---|---|---|---|---|---|\n"
              "| 1 | 가 | 나 | 다 | 고침 |  |\n")
        with self.assertRaises(ValueError):
            rule_sheet.read(md)


if __name__ == "__main__":
    unittest.main()
