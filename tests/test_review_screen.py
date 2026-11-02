"""검토 화면(`review_screen.py`)이 판정 기록과 1층 검사기에서 지적을 모아 화면 자료로 만드는지 본다 — 모델은 안 부른다.

**지키는 것**

- 2층 고칠 지적은 「바로 반영」, 확인할 사실이 걸린 고칠 지적과 사람 확인은 「작성자 확인」으로 나눈다
- 1층 서술형 종결 계열은 「문체 규칙」, 그 밖의 1층 지적은 수정안 없는 「바로 반영」으로 싣는다
- 지적마다 줄 해시를 붙인다(2단계가 답을 그 줄에 단다)
- 원문에 든 `</script>` 가 화면 스크립트를 끊지 않는다
- 화면 HTML 은 판정 기록 옆(저장소 밖)에 쓴다
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
sys.path.insert(0, str(HERE.parent / "scripts"))

import layer2_coverage as coverage  # noqa: E402
import review_screen as screen  # noqa: E402

DOC = """---
form: structured
---
# 배포 안내

**배포 일정과 담당** — 이번 주 배포 순서

- **일정**: 대용량 트래픽(일 평균 320만 건) 처리 개선을 금요일에 배포함
- **담당**: 모놀리식 구조에서 MSA로의 단계적 전환 참여 인원이 맡음
- **비고**: 배포 뒤 결과를 공유한다
"""


class CollectTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = (coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS)
        coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = (
            self.dir / f for f in ("calls.jsonl", "a.jsonl", "d.jsonl", "x.jsonl"))
        self.doc = self.dir / "notice.md"
        self.doc.write_text(DOC, encoding="utf-8")
        lines = coverage.read_doc(self.doc).splitlines()
        n_traffic = next(i for i, l in enumerate(lines, 1) if "320만" in l)
        n_msa = next(i for i, l in enumerate(lines, 1) if "MSA" in l)

        def at(n):
            return {"line": n, "line_key": coverage.line_key(lines[n - 1]), "text": lines[n - 1]}
        row = {"ok": True, "key": coverage.doc_key(self.doc), "when": time.time(), "seen": coverage.seen_keys(lines),
               "fixes": [dict(at(n_msa), phrase="모놀리식 구조에서 MSA로의 단계적 전환 참여",
                              fix="모놀리식 구조를 MSA로 단계적으로 전환하는 작업 참여", why="번역투", category="번역투 줄이기"),
                         dict(at(n_traffic), phrase="일 평균 320만 건", fix="일 평균 주문 320만 건",
                              why="무엇의 건수인지 없음", category="요약하다 맥락이 빠진 명사구",
                              check="320만 건이 주문 수인지 요청 수인지")],
               "asks": [dict(at(n_traffic), phrase="대용량 트래픽", fix="", why="</script><b>x</b> 기준이 없음",
                             category="판단어의 기준 누락")]}
        coverage.LOG.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = self.saved
        self.tmp.cleanup()

    def test_findings_are_sorted_into_three_kinds(self) -> None:
        items = screen.collect(self.doc)["items"]
        two = [x for x in items if x["layer"] == "2층"]
        self.assertEqual(["info", "info", "replace"], sorted(x["type"] for x in two))
        msa = next(x for x in two if "MSA" in x["phrase"])
        self.assertEqual("replace", msa["type"])
        self.assertIn("사람 확인", {x["level"] for x in two})
        one = [x for x in items if x["layer"] == "1층"]
        self.assertTrue(any(x["type"] == "style" for x in one), "반말 서술형 줄이 문체 규칙으로 안 실림")

    def test_every_item_carries_its_line_key_and_a_sequential_id(self) -> None:
        data = screen.collect(self.doc)
        self.assertEqual(list(range(1, len(data["items"]) + 1)), [x["id"] for x in data["items"]])
        for x in data["items"]:
            self.assertEqual(coverage.line_key(data["lines"][x["line"] - 1]), x["line_key"])

    def test_script_close_in_the_text_does_not_break_the_page(self) -> None:
        html = screen.render(screen.collect(self.doc))
        self.assertNotIn("</script><b>x</b>", html)
        self.assertIn("<\\/script><b>x<\\/b>", html)

    def test_the_page_is_written_next_to_the_judge_log(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, screen.main([str(self.doc)]))
        pages = list((self.dir / "korean-review").glob("notice-*.html"))
        self.assertEqual(1, len(pages))
        self.assertIn("검토 화면", pages[0].read_text(encoding="utf-8"))

    def test_a_missing_file_is_refused(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(2, screen.main([str(self.dir / "none.md")]))


class TemplateTests(unittest.TestCase):

    def test_the_data_slot_appears_once(self) -> None:
        self.assertEqual(1, screen.TEMPLATE.read_text(encoding="utf-8").count("/*DATA*/null"))


if __name__ == "__main__":
    unittest.main()
