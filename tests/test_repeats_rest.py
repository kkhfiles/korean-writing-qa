"""수정안이 짚은 표현 밖의 글을 다시 담으면 그대로 넣지 않는지 본다 — 모델은 안 부른다.

(2026-11-12 다른 세션 인계 B4) 판정기가 한 줄의 첫 문장만 짚고 수정안에 뒷문장까지 다시 써서, 검토 화면 제출이 짚은
자리에 수정안을 넣자 같은 문장이 한 줄에 두 번 들어갔다. 세션이 손으로 지웠다.

**지키는 것**

- 겹침을 찾음(`repeats_rest`) — 수정안이 들여오는 글이 그 줄의 짚지 않은 부분에 이미 있으면 그 글을 돌려줌
- 보통 수정안(짚은 표현만 바꿈, 짧은 덧붙임)은 겹침이 아님
- 「고침」 답으로 자동 확정하지 않고(`edited_by_answer`), 고친 말 점검(`fix_notes`)이 경고함
- 검토 화면 — 수정안을 미리 넣지 않고 작성자 확인으로 싣고, 제출해도 파일에 넣지 않고 세션에 넘김
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
import review_screen as screen  # noqa: E402

LINE = "- **쓰는 법** — 공식 양식이 없어 팀 의견을 모은 목록. 앞 절에서 다룬 항목은 그 절에 두고 여기에는 둘만 적음"
PHRASE = "공식 양식이 없어 팀 의견을 모은 목록"
FIX = "공식 양식이 없어 팀 의견을 모은 목록. 앞 절에서 다룬 항목은 그 절에 두고 여기에는 둘만 적음"


class RepeatsRestTests(unittest.TestCase):

    def test_the_reported_case_is_caught(self) -> None:
        twice = judge.repeats_rest(LINE, PHRASE, FIX)
        self.assertIsNotNone(twice)
        self.assertIn("앞절에서다룬항목은", twice)

    def test_a_slightly_reworded_repeat_is_caught(self) -> None:
        line = LINE.replace("앞 절에서 다룬", "의견 가운데 앞 절에서 다룬")
        self.assertIsNotNone(judge.repeats_rest(line, PHRASE, FIX))

    def test_ordinary_fixes_are_not_repeats(self) -> None:
        for line, phrase, fix in (
                ("- 근거 문장이 같이 남고, 남의 일은 따로 둬요", "따로 둬요", "별도로 분류해요"),
                ("- 생성 규칙에 대한 전면적인 재검토 진행", "생성 규칙에 대한 전면적인 재검토 진행", "생성 규칙 전체 재검토"),
                (LINE, "참고로 모은 항목", "참고용으로 모은 항목"),
                ("- 빌드 오류 3건 중 2건 해결", "2건 해결", "2건을 해결함, 1건은 다음 주에 처리"),
        ):
            with self.subTest(phrase=phrase):
                self.assertIsNone(judge.repeats_rest(line, phrase, fix))

    def test_answer_edit_is_not_settled_and_the_note_warns(self) -> None:
        asks = [{"phrase": PHRASE, "fix": FIX, "category": "고치다 뜻이 바뀐 곳"}]
        self.assertIsNone(judge.edited_by_answer(LINE, asks))
        notes = judge.fix_notes(FIX, PHRASE, set(), None, LINE)
        self.assertTrue(any("두 번" in n for n in notes), notes)


class ReviewScreenTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = (coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, judge.LOG)
        coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = (
            self.dir / f for f in ("calls.jsonl", "a.jsonl", "d.jsonl", "x.jsonl"))
        judge.LOG = coverage.LOG
        self.text = f"---\nform: structured\n---\n# 참고 항목\n\n**참고 항목** — 회의 준비\n\n{LINE}\n"
        self.doc = self.dir / "advice.md"
        self.doc.write_text(self.text, encoding="utf-8")
        lines = coverage.read_doc(self.doc).splitlines()
        n = next(i for i, l in enumerate(lines, 1) if PHRASE in l)
        row = {"ok": True, "key": coverage.doc_key(self.doc), "when": time.time(), "seen": coverage.seen_keys(lines),
               "fixes": [{"line": n, "line_key": coverage.line_key(lines[n - 1]), "text": lines[n - 1],
                          "phrase": PHRASE, "fix": FIX, "why": "기준 판의 까닭이 빠짐", "category": "고치다 뜻이 바뀐 곳"}],
               "asks": []}
        coverage.LOG.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, judge.LOG = self.saved
        self.tmp.cleanup()

    def test_the_fix_is_shown_as_an_author_check(self) -> None:
        item = next(x for x in screen.collect(self.doc)["items"] if x["layer"] == "2층")
        self.assertEqual("info", item["type"])
        self.assertIn("두 번", item["check"])

    @unittest.skipUnless(judge.load_freq(), "형태소 분석기가 없으면 드문 낱말을 안 봄")
    def test_a_fix_that_brings_a_rare_word_is_not_prefilled(self) -> None:
        # (다른 세션 인계 B7) 판정기가 「약한 부분」을 「약점」으로 제안했고 단어 점검이 「약점」을 드문 낱말로 짚었다
        row = json.loads(coverage.LOG.read_text(encoding="utf-8"))
        line = "- **보완할 곳** — 보안 설계의 약한 부분을 발표 전에 정리함"
        self.doc.write_text(self.text + line + "\n", encoding="utf-8")
        lines = coverage.read_doc(self.doc).splitlines()
        n = len(lines)
        row["seen"] = coverage.seen_keys(lines)
        row["fixes"].append({"line": n, "line_key": coverage.line_key(lines[n - 1]), "text": lines[n - 1],
                             "phrase": "약한 부분", "fix": "약점", "why": "짧게", "category": "군더더기 지우기"})
        coverage.LOG.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        item = next(x for x in screen.collect(self.doc)["items"] if x["phrase"] == "약한 부분")
        self.assertEqual("info", item["type"])
        self.assertIn("드문 낱말", item["check"])

    def test_submitting_it_does_not_write_the_repeat(self) -> None:
        data = screen.collect(self.doc)
        item = next(x for x in data["items"] if x["layer"] == "2층")
        screen.submit(self.doc, data, [{"id": item["id"], "dec": "accept"}])
        self.assertEqual(self.text, self.doc.read_text(encoding="utf-8"), "같은 문장이 두 번 들어가면 안 됨")


if __name__ == "__main__":
    unittest.main()
