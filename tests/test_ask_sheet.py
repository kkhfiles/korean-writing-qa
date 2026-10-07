"""사람 확인 표 — 판정기가 넘긴 지적이 **사람이 하나씩 볼 수 있는 표**로 나가고, 적은 답이 바르게 돌아오는지 본다.

(2026-10-07 사용자 — 「최소한 md 파일에 표 형태로 정리라도 해줘야 사람이 하나씩 본 뒤에
판단할 것 아닌가」) 모델은 안 부른다.

**지키는 것**

- 한 줄이 한 행이고, 같은 줄의 지적 둘은 한 행에 모이나 — 답이 줄에 묶이므로
- 짚은 표현이 굵게 나오고 판정기 제안 · 넘긴 까닭 · 빈 답 칸이 있나
- 칸 안의 `|` 가 표를 깨지 않나
- `그대로`만 답 기록에 남나 — ⛔ `고침`을 답으로 적으면 고치기 전에 지적이 닫힌다
- 보류 · 빈칸은 열린 채 남나
- 넷 가운데 하나로 시작하지 않는 글은 닫지도 고칠 목록에 넣지도 않고 따로 돌려주나
- 표를 만든 뒤 바뀐 줄의 답은 거절하나 · 위에 줄이 늘어도 같은 글의 줄을 찾아가나
- 열쇠 주석이 없는 표는 거절하나 — 줄을 짐작해 답을 적지 않는다
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))

import ask_sheet  # noqa: E402
import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402

DOC = ("# 소개\n\n"
       "업무 목록은 매일 갱신됩니다.\n\n"
       "일주일이 지나면 작업 내용의 기억이 흐려집니다.\n\n"
       "마감이 가까운 업무를 맨 위에 표시합니다 | 표 기호가 든 줄.\n")
A1 = {"line": 5, "phrase": "기억이 흐려집니다", "category": "업무에서 쓰는 말로 쓰기",
      "fix": "정확히 기억하기 어렵습니다", "why": "문맥에 따라 정상일 수 있음", "decide": "ask"}
A2 = {"line": 5, "phrase": "일주일이 지나면", "category": "판단어의 기준 누락",
      "fix": "7일이 지나면", "why": "기간 기준이 불분명", "decide": "ask"}
A3 = {"line": 7, "phrase": "맨 위에 표시합니다", "category": "군더더기 지우기",
      "fix": "맨 위에 | 둡니다", "why": "시험", "decide": "ask"}


class SheetTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS = self.dir / "answers.jsonl"
        self.doc = self.dir / "d.md"
        self.doc.write_text(DOC, encoding="utf-8")
        self.sheet = self.dir / "asks.md"
        rc, out = self.run_main([str(self.doc)], backend=FakeBackend([A1, A2, A3]).pair())
        self.assertEqual(0, rc, f"판정 단계가 실패해 시험할 사람 확인이 없습니다: {out[-300:]}")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS = self.saved
        self.tmp.cleanup()

    def run_main(self, argv, backend=None) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main(argv, backend=backend)
        return rc, out.getvalue()

    def make_sheet(self) -> str:
        rc, out = self.run_main([str(self.doc), "--sheet", str(self.sheet)])
        self.assertEqual(1, rc, out)
        return self.sheet.read_text(encoding="utf-8")

    def fill(self, answers: dict[str, str]) -> None:
        """사람이 하듯 답 칸(맨 오른쪽 빈칸)에 적는다."""
        rows = []
        for raw in self.sheet.read_text(encoding="utf-8").splitlines():
            for qid, ans in answers.items():
                if raw.startswith(f"| {qid} |") and raw.endswith("|  |"):
                    raw = raw[:-len("|  |")] + f"| {ans} |"
            rows.append(raw)
        self.sheet.write_text("\n".join(rows), encoding="utf-8")

    def open_lines(self) -> list[int]:
        lines = coverage.read_doc(self.doc).splitlines()
        return sorted({n for n, _ in coverage.open_asks(coverage.doc_key(self.doc), lines, judge.LOG)})

    def test_one_row_per_line(self) -> None:
        text = self.make_sheet()
        rows = [l for l in text.splitlines() if l.startswith("| Q")]
        self.assertEqual(2, len(rows), "같은 줄의 지적 둘이 한 행에 안 모였습니다 — 답은 줄에 묶입니다")
        self.assertIn("**기억이 흐려집니다**", rows[0])
        self.assertIn("**일주일이 지나면**", rows[0])
        self.assertIn("7일이 지나면", rows[0])
        self.assertIn("기간 기준이 불분명", rows[0])

    def test_columns_hold_and_answer_cell_is_empty(self) -> None:
        keys, answers = ask_sheet.parse(self.make_sheet())
        self.assertEqual({"Q1", "Q2"}, set(keys))
        self.assertEqual({"Q1": "", "Q2": ""}, answers, "칸 안의 `|` 가 표를 깨 답 칸이 밀렸습니다")
        self.assertEqual(7, keys["Q2"]["line"])

    def test_keep_is_recorded_and_edit_is_not(self) -> None:
        self.make_sheet()
        self.fill({"Q1": "그대로 — 정해진 문구", "Q2": "고침"})
        rc, out = self.run_main(["--answers-from", str(self.sheet)])
        self.assertEqual(1, rc, out)
        self.assertEqual([7], self.open_lines(),
                         "「고침」을 답으로 적어 고치기 전에 지적이 닫혔거나 「그대로」가 안 적혔습니다")
        self.assertIn("고칠 것 1건", out)
        self.assertIn("맨 위에 표시합니다", out)
        note = json.loads(coverage.ANSWERS.read_text(encoding="utf-8").splitlines()[-1])["note"]
        self.assertIn("그대로 — 정해진 문구", note, "사용자가 적은 답이 기록에 안 남았습니다")

    def test_free_text_is_neither_recorded_nor_listed_as_a_fix(self) -> None:
        # 2026-10-07 실제 답 — 「이건 그냥 놔두자」가 「고칠 것」 목록에 실렸다
        self.make_sheet()
        self.fill({"Q1": "이건 그냥 놔두자", "Q2": "고침"})
        rc, out = self.run_main(["--answers-from", str(self.sheet)])
        self.assertEqual(1, rc, out)
        self.assertEqual([5, 7], self.open_lines(), "글로 적은 답을 낱말로 짐작해 닫았습니다")
        self.assertIn("고칠 것 1건", out, "유지하라는 글이 고칠 목록에 섞였습니다")
        self.assertIn("글로 적은 답 1건", out)
        self.assertIn("이건 그냥 놔두자", out)

    def test_hold_and_blank_stay_open(self) -> None:
        self.make_sheet()
        self.fill({"Q1": "보류"})
        rc, out = self.run_main(["--answers-from", str(self.sheet)])
        self.assertEqual(1, rc, out)
        self.assertEqual([5, 7], self.open_lines())
        self.assertIn("보류 · 빈칸 2건", out)

    def test_all_kept_closes_everything(self) -> None:
        self.make_sheet()
        self.fill({"Q1": "그대로", "Q2": "그대로"})
        rc, out = self.run_main(["--answers-from", str(self.sheet)])
        self.assertEqual(0, rc, out)
        self.assertEqual([], self.open_lines())

    def test_changed_line_is_refused(self) -> None:
        self.make_sheet()
        self.doc.write_text(DOC.replace("일주일이 지나면", "열흘이 지나면"), encoding="utf-8")
        self.fill({"Q1": "그대로"})
        rc, out = self.run_main(["--answers-from", str(self.sheet)])
        self.assertIn("그 줄이 바뀌었습니다", out)
        self.assertFalse(coverage.ANSWERS.exists(), "사용자가 본 문장과 다른 줄에 답을 적었습니다")

    def test_shifted_line_is_followed(self) -> None:
        self.make_sheet()
        self.doc.write_text(DOC.replace("# 소개\n", "# 소개\n\n새로 넣은 첫 문단입니다.\n"), encoding="utf-8")
        self.fill({"Q1": "그대로"})
        rc, out = self.run_main(["--answers-from", str(self.sheet)])
        self.assertEqual([9], self.open_lines(), "위에 줄이 늘자 같은 글의 줄을 못 찾았습니다")

    def test_a_sheet_without_keys_is_refused(self) -> None:
        text = self.make_sheet()
        self.sheet.write_text(text.split("<!--")[0], encoding="utf-8")
        rc, out = self.run_main(["--answers-from", str(self.sheet)])
        self.assertEqual(2, rc, out)
        self.assertFalse(coverage.ANSWERS.exists())


class KindTests(unittest.TestCase):

    def test_kinds(self) -> None:
        for raw, want in (("", ask_sheet.BLANK), ("보류", ask_sheet.HOLD), ("`그대로`", ask_sheet.KEEP),
                          ("그대로 — 이름", ask_sheet.KEEP), ("고침", ask_sheet.EDIT),
                          ("직접: 정확히 기억하기 어렵습니다", ask_sheet.EDIT),
                          ("고침, 인데 회기라는 말이 틀렸다", ask_sheet.EDIT),
                          ("삭제", ask_sheet.FREE), ("이건 그냥 놔두자", ask_sheet.FREE),
                          ("놔두지 말고 고치자", ask_sheet.FREE)):
            self.assertEqual(want, ask_sheet.kind_of(raw), raw)


if __name__ == "__main__":
    unittest.main()
