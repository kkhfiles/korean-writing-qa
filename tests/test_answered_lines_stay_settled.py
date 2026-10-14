"""사용자가 사람 확인에 답한 줄이 **다시 묻지 않고 확정되는지** 본다 — 모델은 안 부른다.

(2026-10-14 lab-docs) 출처 소개 한 줄에서 사람 확인이 네 번 올라왔다. 상한을 넘은 줄은 그 뒤 지적이
모두 사람 확인으로 가는데, 답대로 고친 줄도 새 줄이라 다시 판정했고 판정기는 판정마다 다른 것을 짚었다.
같은 출처 주소를 담은 다른 줄과 한 계보로 묶여 상한에도 일찍 닿았다. 실사용 사람 확인 208건 중 101건이
상한 때문이었다(10/07~10/14).

**지키는 것**

- 사용자가 답한 지적은 물은 줄이 바뀌면 닫힌다 — 고른 문구에 물은 표현이 들어 있어도 다시 붙지 않는다
- 답이 없는 지적은 여전히 표현이 남은 줄에 붙는다(낱말 하나만 바꿔 묻지 않고 사라지던 빈틈)
- 「고침」 답은 판정기 제안대로 고친 글이 사람이 판정한 줄로 남아 다시 판정하지 않는다 · 다르게 고치면 판정한다
- 「직접」 답은 세션이 고친 뒤 `--answer` 로 확정한다 · 답도 지적도 없는 줄은 여전히 거절한다
- 확정 전에 다시 판정하면 그 줄에 사용자가 답한 것이 프롬프트에 실린다
- 줄이 이어지는지는 링크 주소를 빼고 가른다 — 같은 주소만 담은 다른 줄의 판정 횟수를 물려받지 않는다
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402

DOC = ["# 소개", "", "업무 목록은 매일 갱신됩니다.", "",
       "출처는 주제 문서입니다.", "",
       "마감이 가까운 업무를 맨 위에 표시합니다."]
# 고른 문구 안에 물은 표현이 그대로 든다 — 그래서 답대로 고쳐도 다시 붙던 지적
A = {"line": 5, "phrase": "주제 문서", "category": "원문 용어를 직역한 말",
     "fix": "주제 문서(Topic Paper)", "why": "시험", "decide": "ask"}
B = {"line": 7, "phrase": "표시합니다", "category": "업무에서 쓰는 말로 쓰기",
     "fix": "둡니다", "why": "시험", "decide": "ask"}
URL = "https://example.com/wp-content/uploads/2020/12/a-very-long-source-document-file-name-rev3.pdf"


class _Base(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS = self.dir / "answers.jsonl"
        coverage.DECISIONS = self.dir / "decisions.jsonl"
        coverage.DISMISSALS = self.dir / "dismissals.jsonl"
        self.doc = self.dir / "d.md"
        self.write(DOC)
        self.sheet = self.dir / "asks.md"
        rc, out = self.run_main([str(self.doc)], backend=FakeBackend([A, B]).pair())
        self.assertEqual(0, rc, out[-300:])
        rc, out = self.run_main([str(self.doc), "--sheet", str(self.sheet)])
        self.assertEqual(1, rc, out[-300:])

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = self.saved
        self.tmp.cleanup()

    def write(self, lines: list[str]) -> None:
        self.doc.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def edit(self, n: int, text: str) -> list[str]:
        lines = list(DOC)
        lines[n - 1] = text
        self.write(lines)
        return lines

    def run_main(self, argv, backend=None) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main(argv, backend=backend)
        return rc, out.getvalue()

    def reply(self, *answers: str) -> str:
        argv = ["--answers-from", str(self.sheet)]
        for a in answers:
            argv += ["--reply", a]
        return self.run_main(argv)[1]

    def key(self) -> str:
        return coverage.doc_key(self.doc)

    def open_asks(self) -> list[int]:
        lines = coverage.read_doc(self.doc).splitlines()
        return sorted({n for n, _ in coverage.open_asks(self.key(), lines, judge.LOG)})

    def to_judge(self) -> list[int]:
        lines = coverage.read_doc(self.doc).splitlines()
        return coverage.open_lines(lines, [], coverage.judged(self.key(), judge.LOG))


class AnsweredAskTests(_Base):

    def test_an_answered_ask_closes_even_if_the_chosen_text_keeps_the_phrase(self) -> None:
        # 「직접」 — 확정 기록 없이도 닫혀야 한다(「고침」은 확정 기록이 먼저 닫아 이 경로를 못 본다)
        self.reply("Q1 직접: 주제 문서(FAS Topic Paper)")
        self.assertIn(5, self.open_asks(), "고치기 전에 지적이 닫혔습니다")
        self.edit(5, "출처는 주제 문서(FAS Topic Paper)입니다.")
        self.assertNotIn(5, self.open_asks(), "답대로 고쳤는데 물은 표현이 남아 같은 지적이 다시 붙었습니다")

    def test_answering_an_unedited_line_is_a_plain_answer(self) -> None:
        self.reply("Q1 직접: 주제 문서(FAS Topic Paper)")
        rc, msg = self.run_main([str(self.doc), "--answer", "5", "--note", "사용자 답: 그대로 두기로 바꿈"])
        self.assertEqual(0, rc, msg)
        row = json.loads(coverage.ANSWERS.read_text(encoding="utf-8").splitlines()[-1])
        self.assertFalse(row.get("approved"), "고치지 않은 줄의 답을 답대로 고친 줄로 적었습니다")

    def test_an_ask_answered_with_answer_also_closes_after_the_line_changes(self) -> None:
        rc, msg = self.run_main([str(self.doc), "--answer", "5", "--note", "사용자 답: 그대로"])
        self.assertEqual(0, rc, msg)
        self.edit(5, "출처는 주제 문서이며 원문 이름은 뒤에 적습니다.")
        self.assertNotIn(5, self.open_asks(), "답을 받은 판의 지적이 바뀐 줄에 다시 붙었습니다")

    def test_an_old_answer_without_the_ask_list_still_closes(self) -> None:
        # 닫은 지적 목록을 적기 전의 답 기록 — 실제 기록에 남아 있다
        row = {"at": "2026-10-13T00:00:00", "when": time.time(), "doc": str(self.doc), "key": self.key(),
               "line": 5, "line_key": coverage.line_key(DOC[4]), "note": "사용자 답: 그대로"}
        coverage.ANSWERS.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        self.edit(5, "출처는 주제 문서이며 원문 이름은 뒤에 적습니다.")
        self.assertNotIn(5, self.open_asks(), "옛 답 기록으로 답한 판의 지적이 바뀐 줄에 다시 붙었습니다")

    def test_an_ask_answered_on_a_later_version_stays_closed(self) -> None:
        # 물은 판 → 고침(표현이 남아 지적이 따라옴) → 그 판에 답 → 또 고침
        self.edit(5, "출처는 주제 문서이고 판정기 지적을 받았습니다.")
        self.assertIn(5, self.open_asks())
        rc, msg = self.run_main([str(self.doc), "--answer", "5", "--note", "사용자 답: 그대로"])
        self.assertEqual(0, rc, msg)
        self.edit(5, "출처는 주제 문서이며 원문 이름은 뒤에 적습니다.")
        self.assertNotIn(5, self.open_asks(), "뒤 판에서 답한 지적이 줄이 또 바뀌자 다시 붙었습니다")

    def test_an_unanswered_ask_still_follows_its_phrase(self) -> None:
        self.edit(7, "마감이 임박한 업무를 맨 위에 표시합니다.")
        self.assertIn(7, self.open_asks(), "답 없는 지적이 다른 낱말 하나 바꾼 것으로 사라졌습니다")


class SettledLineTests(_Base):

    def test_the_suggested_fix_settles_the_line(self) -> None:
        out = self.reply("Q1 고침")
        self.assertIn("판정기 제안대로 고치면 다시 판정하지 않음", out)
        self.edit(5, "출처는 주제 문서(Topic Paper)입니다.")
        self.assertNotIn(5, self.to_judge(), "사용자가 고른 글을 판정기에 다시 보냅니다")

    def test_a_different_edit_is_judged_again(self) -> None:
        self.reply("Q1 고침")
        self.edit(5, "출처는 주제 문서(TP)입니다.")
        self.assertIn(5, self.to_judge(), "사용자가 고르지 않은 글을 판정 없이 통과시킵니다")

    def test_a_direct_answer_is_settled_by_the_session_after_editing(self) -> None:
        out = self.reply("Q1 직접: 주제 문서(FAS Topic Paper)")
        self.assertIn("--answer 5", out)
        self.edit(5, "출처는 주제 문서(FAS Topic Paper)입니다.")
        self.assertIn(5, self.to_judge(), "세션이 확정하기 전에 판정이 면제됐습니다")
        rc, msg = self.run_main([str(self.doc), "--answer", "5", "--note", "사용자 답: 직접: 주제 문서(FAS Topic Paper)"])
        self.assertEqual(0, rc, msg)
        self.assertNotIn(5, self.to_judge(), "확정한 줄을 판정기에 다시 보냅니다")
        row = json.loads(coverage.ANSWERS.read_text(encoding="utf-8").splitlines()[-1])
        self.assertTrue(row.get("approved"))
        self.assertEqual(coverage.line_key(DOC[4]), row["origin"], "확정 기록이 물은 줄을 가리키지 않습니다")

    def test_the_suggestion_is_not_settled_when_the_user_wrote_their_own(self) -> None:
        self.reply("Q1 직접: 원문 이름을 괄호로 붙임")
        self.edit(5, "출처는 주제 문서(Topic Paper)입니다.")
        self.assertIn(5, self.to_judge(), "사용자가 직접 적은 답과 다른 판정기 제안을 확정했습니다")

    def test_a_line_without_an_ask_or_an_answer_is_still_refused(self) -> None:
        rc, msg = self.run_main([str(self.doc), "--answer", "3", "--note", "사용자 답이 없는 줄"])
        self.assertNotEqual(0, rc, "묻지도 답하지도 않은 줄을 확정했습니다")


class PromptTests(_Base):

    def test_the_users_answer_reaches_the_rejudge(self) -> None:
        self.reply("Q2 직접: 맨 위에 둡니다")
        lines = self.edit(7, "마감이 가까운 업무를 목록 맨 위에 둡니다.")
        fake = FakeBackend([])
        judge.judge(self.doc, "opus", 10, fake.pair(), [7], DOC)
        user = fake.calls[0]["user"]
        self.assertIn("사용자가 답한 것", user)
        self.assertIn("사용자: 직접: 맨 위에 둡니다", user)
        self.assertEqual(lines[6], coverage.read_doc(self.doc).splitlines()[6])


class LineageTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = judge.LOG
        judge.LOG = Path(self.tmp.name) / "calls.jsonl"
        self.key = "doc-key"
        source = f"- [출처 자료]({URL}) — 도구 조건과 목표 수"
        row = {"ok": True, "key": self.key, "when": time.time(), "base_time": 100.0,
               "targeted": [{"key": coverage.line_key(source), "text": source, "round": 3, "root": None}]}
        judge.LOG.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG = self.saved
        self.tmp.cleanup()

    def round_of(self, text: str) -> int:
        return judge.lineage(self.key, [text], [1], None, 100.0)[1]["round"]

    def test_a_line_sharing_only_the_link_starts_its_own_count(self) -> None:
        self.assertEqual(1, self.round_of(f"- **할 일 요약**([출처 자료]({URL}))"),
                         "같은 출처 주소만 담은 다른 줄의 판정 횟수를 물려받았습니다")

    def test_a_line_with_only_its_link_changed_keeps_the_count(self) -> None:
        self.assertEqual(4, self.round_of("- [출처 자료](https://example.org/other.pdf) — 도구 조건과 목표 수"),
                         "주소만 바꾼 줄을 새 줄로 셌습니다 — 고칠 때마다 예산이 새로 생깁니다")


if __name__ == "__main__":
    unittest.main()
