"""재판정 문맥 옵션(`--context chunk|fixed|block`)이 구조를 지키며 줄이고, 못 담으면 지금 방식으로 돌아가는지 본다.

(2026-10-16) 재판정 비용의 대부분이 호출마다 새로 쓰는 180줄 묶음이다. 대상 주변만 보내는 실험을 옵션으로 두되,
외부 검토 조건을 지킨다 — 구조 단위(표 · 목록 · 코드 울타리)를 자르지 않고 못 담으면 chunk 로 복귀, HTML 은 chunk,
판정기가 「문맥 부족」을 내면 그 줄은 chunk 로 다시 판정, 같은 입력 재생을 위해 재판정 입력을 남긴다. 모델은 안 부른다.

**지키는 것**

- 기본(chunk)은 예전과 같은 묶음을 같은 순서로 보낸다
- block 은 대상의 블록 · 제목 사슬 · 앞뒤 블록을 보내고, 대상 블록이 예산을 넘으면 chunk 로 돌아간다
- 묶음 둘에 걸친 대상도 창이면 한 번에 부른다 · 판정기가 본 줄(seen)은 보낸 줄뿐이다
- HTML 은 창을 쓰지 않는다
- 「문맥 부족」 지적은 처리할 지적으로 남기지 않고 그 줄만 chunk 로 다시 판정한다
- 재판정 입력이 판정 기록 옆에 남는다
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402


def doc_lines() -> list[str]:
    """제목 · 문단 · 표 · 코드 울타리가 있고 180줄을 넘는 문서."""
    out = ["# 안내", "", "## 일정", "", "배포는 매주 화요일에 합니다.", "다음 주부터 적용합니다.", "",
           "| 항목 | 값 |", "|---|---|", "| 주기 | 매주 |", "| 담당 | 운영팀 |", "",
           "```", "코드 첫 줄", "", "코드 셋째 줄", "```", ""]
    out += [f"채움 문단 {i}번입니다." for i in range(1, 200)]
    out += ["", "## 마무리", "", "마지막 문단은 끝에 둡니다."]
    return out


class Scripted:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def call(self, **kw):
        self.calls.append(kw)
        reply = self.replies.pop(0) if self.replies else []
        return {"text": json.dumps(reply, ensure_ascii=False), "model": "fake",
                "usage": {"output_tokens": 10}, "cost_usd": 0.01}

    def pair(self):
        return self.call, json.loads


class WindowRuleTests(unittest.TestCase):

    def setUp(self) -> None:
        self.lines = doc_lines()

    def test_a_code_fence_with_blank_lines_is_one_block(self) -> None:
        self.assertIn((13, 17), judge.blocks(self.lines))

    def test_the_heading_chain_climbs_levels(self) -> None:
        self.assertEqual([3, 1], judge.heading_chain(self.lines, 5))

    def test_a_sibling_heading_above_is_not_in_the_chain(self) -> None:
        lines = ["# 문서", "## 앞 절", "앞 절 본문입니다.", "## 이 절", "이 절 본문입니다."]
        self.assertEqual([4, 1], judge.heading_chain(lines, 5), "같은 수준의 앞 절 제목까지 사슬에 넣었습니다")

    def test_a_table_cell_brings_the_whole_table_and_its_headings(self) -> None:
        got = judge.window_lines(self.lines, 10, "block")
        self.assertTrue({8, 9, 10, 11} <= got, "표 머리 행이 빠졌습니다")
        self.assertTrue({1, 3} <= got, "제목 사슬이 빠졌습니다")
        self.assertTrue({5, 6} <= got, "앞 블록이 빠졌습니다")

    def test_a_block_over_budget_falls_back(self) -> None:
        long = ["# 제목", ""] + [f"한 문단 안의 {i}번째 줄입니다." for i in range(judge.BLOCK_BUDGET + 5)]
        self.assertIsNone(judge.window_lines(long, 50, "block"), "구조 단위를 잘라 보냈습니다")

    def test_a_long_list_keeps_the_item_its_parent_and_the_intro(self) -> None:
        items = []
        for i in range(80):
            items += [f"- 상위 항목 {i}입니다.", f"  - 하위 항목 {i}입니다."]
        long = ["# 제목", "", "아래는 긴 목록입니다:"] + items
        n = long.index("  - 하위 항목 40입니다.") + 1
        got = judge.window_lines(long, n, "block")
        self.assertIsNotNone(got, "긴 목록을 구조 단위로 못 담고 복귀했습니다")
        self.assertTrue({1, 3, n, n - 1} <= got, "제목 · 도입문 · 상위 항목이 빠졌습니다")
        self.assertLess(len(got), 20)

    def test_a_long_table_keeps_the_header_rows(self) -> None:
        long = ["# 표", "", "| 항목 | 값 |", "|---|---|"] + [f"| 항목 {i} | 값 {i} |" for i in range(150)]
        got = judge.window_lines(long, 100, "block")
        self.assertTrue({3, 4, 98, 99, 100, 101, 102} <= got, "표 머리나 이웃 행이 빠졌습니다")
        self.assertLess(len(got), 20)

    def test_fixed_keeps_a_fixed_span_and_the_headings(self) -> None:
        got = judge.window_lines(self.lines, 100, "fixed")
        self.assertEqual(set(range(80, 121)) | {3, 1}, got)

    def test_fixed_edges_widen_to_a_nearby_block_end(self) -> None:
        """(외부 검토 Argon · 2026-10-20) 창 끝이 블록 중간을 자르면 그 블록 끝까지 — 멀면 그대로."""
        paras = [f"문단 줄 {i}입니다." for i in range(60)]
        lines = paras[:15] + [""] + paras[15:45] + [""] + paras[45:]      # 블록 1-15 · 17-46 · 48-62
        got = judge.window_lines(lines, 30, "fixed")       # 창 10-50 · 앞 블록 첫 줄은 9줄 · 뒤 블록 끝은 12줄 밖
        self.assertIn(1, got, "가까운 블록 첫 줄까지 넓히지 않았습니다")
        self.assertEqual(set(range(1, 51)), got, "먼 블록 끝(12줄)까지 넓혔거나 창을 잘못 잡았습니다")

    def test_fixed_cut_table_keeps_its_header(self) -> None:
        long = ["# 표", "", "| 항목 | 값 |", "|---|---|"] + [f"| 항목 {i} | 값 {i} |" for i in range(150)]
        got = judge.window_lines(long, 100, "fixed")
        self.assertTrue({3, 4} <= got, "창이 자른 표의 머리 행이 빠졌습니다")
        self.assertTrue(set(range(80, 121)) <= got)
        self.assertLess(len(got), 50)

    def test_the_excerpt_keeps_original_numbers_and_marks_gaps(self) -> None:
        text = judge.excerpt(self.lines, [1, 5, 6])
        self.assertIn("  5 | 배포는 매주 화요일에 합니다.", text)
        self.assertIn("…(3줄 생략)…", text)
        self.assertTrue(text.rstrip().endswith("줄 생략)…"))


class PartsTests(unittest.TestCase):

    def setUp(self) -> None:
        self.lines = doc_lines()
        self.md = Path("d.md")

    def test_chunk_is_the_old_way(self) -> None:
        old = [(first, part) for first, part in judge.chunks(self.lines) if any(first <= n < first + len(part) for n in {5})]
        got = judge.parts_for(self.lines, {5}, "chunk", self.md)
        self.assertEqual([judge.numbered(p, f) for f, p in old], [g["document"] for g in got])
        self.assertEqual("chunk", got[0]["mode"])

    def test_targets_in_two_chunks_go_in_one_window(self) -> None:
        far = len(self.lines)
        chunked = judge.parts_for(self.lines, {5, far}, "chunk", self.md)
        windowed = judge.parts_for(self.lines, {5, far}, "block", self.md)
        self.assertEqual(2, len(chunked))
        self.assertEqual(1, len(windowed), "묶음이 둘이라고 창을 둘로 나눠 불렀습니다")
        self.assertLess(len(windowed[0]["seen"]), sum(len(p["seen"]) for p in chunked))

    def test_html_never_uses_a_window(self) -> None:
        got = judge.parts_for(self.lines, {5}, "block", Path("d.html"))
        self.assertEqual("chunk←block", got[0]["mode"])
        with mock.patch.object(judge, "WINDOW_HTML", False):    # 끄면 예전처럼 묶음
            got = judge.parts_for(self.lines, {5}, "fixed", Path("d.html"))
        self.assertEqual("chunk←fixed", got[0]["mode"])

    def test_no_target_means_no_piece_in_every_mode(self) -> None:
        """(2026-10-19) 대상 0줄 입력을 창 방식으로 재생하다 IndexError 로 멈췄다."""
        for mode in judge.CONTEXT_MODES:
            self.assertEqual([], judge.parts_for(self.lines, set(), mode, self.md), mode)

    def test_a_window_over_the_chunk_size_falls_back(self) -> None:
        many = set(range(20, 210, 12))      # 고정 창 41줄씩이 흩어져 180줄을 넘는다
        got = judge.parts_for(self.lines, many, "fixed", self.md)
        self.assertTrue(all(p["mode"] == "chunk←fixed" for p in got))


class HtmlWindowTests(unittest.TestCase):
    """(2026-10-20) HTML 은 보이는 글만 보내는데 창을 못 써 재판정 비용의 62% 였다 — 제목은 <h1>~<h6> 줄로 잡는다."""

    HTML = ("<html><head><style>p{}</style></head><body><h1>안내</h1>"
            + "".join(f"<p>앞 문단 {i}번입니다.</p>" for i in range(30))
            + "<h2>일정</h2>" + "".join(f"<p>일정 문단 {i}번입니다.</p>" for i in range(60))
            + "<h2>마무리</h2><p>끝 문단입니다.</p></body></html>")

    def test_heading_lines_are_found_and_the_text_is_unchanged(self) -> None:
        import layer2_coverage as cov
        lines, heads = cov.visible_lines(self.HTML)
        self.assertEqual("\n".join(lines), cov.visible_text(self.HTML, ".html"))
        self.assertEqual({1: 1, 32: 2, 93: 2}, heads)
        self.assertEqual("일정", lines[31])
        self.assertNotIn(cov.HEAD_MARK, "".join(lines))

    def test_the_fixed_window_carries_the_heading_chain(self) -> None:
        import tempfile
        import layer2_coverage as cov
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "d.html"
            path.write_text(self.HTML, encoding="utf-8")
            lines = cov.read_doc(path).splitlines()
            with mock.patch.object(judge, "WINDOW_HTML", True):
                [piece] = judge.parts_for(lines, {80}, "fixed", path)
                [given] = judge.parts_for(lines, {80}, "fixed", Path(d) / "gone.html", {1: 1, 32: 2})
        self.assertEqual("fixed", piece["mode"])
        self.assertTrue({1, 32} <= {lines.index(l) + 1 for l in piece["seen"]}, "제목 사슬이 빠졌습니다")
        self.assertLess(len(piece["seen"]), 50)
        self.assertEqual(piece["seen"], given["seen"], "남겨 둔 제목 줄로도 같은 창이어야 합니다")


class JudgeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS = self.dir / "a.jsonl"
        coverage.DECISIONS = self.dir / "d.jsonl"
        coverage.DISMISSALS = self.dir / "x.jsonl"
        self.doc = self.dir / "d.md"
        self.lines = doc_lines()
        self.doc.write_text("\n".join(self.lines) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = self.saved
        self.tmp.cleanup()

    def rows(self) -> list[dict]:
        return [json.loads(l) for l in judge.LOG.read_text(encoding="utf-8").splitlines()]

    def test_block_sends_one_call_with_the_window_note(self) -> None:
        fake = Scripted([[]])
        judge.judge(self.doc, "opus", 10, fake.pair(), [5, len(self.lines)], self.lines, context="block")
        self.assertEqual(1, len(fake.calls))
        self.assertIn("줄 생략)…", fake.calls[0]["user"])
        self.assertIn(judge.CONTEXT_SHORT, fake.calls[0]["user"])
        row = self.rows()[-1]
        self.assertEqual("block", row["context"])
        self.assertLess(len(row["seen"]), 100, "보내지 않은 줄까지 판정기가 본 줄로 적었습니다")

    def test_context_short_reruns_that_line_in_chunk(self) -> None:
        short = {"line": 5, "phrase": "배포는", "category": judge.CONTEXT_SHORT, "fix": "", "why": "정의가 생략됨",
                 "decide": "fix"}
        fake = Scripted([[short], []])
        got = judge.judge(self.doc, "opus", 10, fake.pair(), [5], self.lines, context="block")
        self.assertEqual(2, len(fake.calls), "문맥 부족인 줄을 다시 판정하지 않았습니다")
        self.assertNotIn("줄 생략)…", fake.calls[1]["user"])
        self.assertEqual([], got["findings"])
        rows = self.rows()
        self.assertEqual([5], rows[0]["context_short"])
        self.assertEqual("chunk←문맥 부족", rows[1]["context"])
        self.assertEqual([], [f for r in rows for f in r.get("fixes") or []], "문맥 부족을 처리할 지적으로 남겼습니다")

    def test_context_short_in_chunk_mode_is_an_ordinary_finding(self) -> None:
        short = {"line": 5, "phrase": "배포는", "category": judge.CONTEXT_SHORT, "fix": "배포는", "why": "시험",
                 "decide": "fix"}
        got = judge.judge(self.doc, "opus", 10, Scripted([[short]]).pair(), [5], self.lines, context="chunk")
        self.assertEqual(1, len(got["findings"]))

    def test_the_rejudge_input_is_saved_next_to_the_log(self) -> None:
        judge.judge(self.doc, "opus", 10, Scripted([[]]).pair(), [5], self.lines, context="fixed")
        saved = list((self.dir / "korean-replay").glob("*.json"))
        self.assertEqual(1, len(saved))
        case = json.loads(saved[0].read_text(encoding="utf-8"))
        self.assertEqual(([5], "fixed"), (case["targets"], case["context"]))
        self.assertEqual("\n".join(self.lines) + "\n", case["text"])

    def test_a_full_judgment_saves_nothing(self) -> None:
        judge.judge(self.doc, "opus", 10, Scripted([[], []]).pair())
        self.assertFalse((self.dir / "korean-replay").exists())


if __name__ == "__main__":
    unittest.main()
