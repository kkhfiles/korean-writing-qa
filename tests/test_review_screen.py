"""검토 화면(`review_screen.py`)이 판정 기록과 1층 검사기에서 지적을 모아 화면 자료로 만드는지 본다 — 모델은 안 부른다.

**지키는 것**

- 2층 고칠 지적은 「바로 반영」, 확인할 사실이 걸린 고칠 지적과 사람 확인은 「작성자 확인」으로 나눈다
- 1층 서술형 종결 계열은 「문체 규칙」, 그 밖의 1층 지적은 수정안 없는 「바로 반영」으로 싣는다
- 지적마다 줄 해시를 붙인다(2단계가 답을 그 줄에 단다)
- 원문에 든 `</script>` 가 화면 스크립트를 끊지 않는다
- 화면 HTML 은 판정 기록 옆(저장소 밖)에 쓴다
- 제출(2단계) — 반영과 직접 고침은 답 기록과 확정 줄로, 그대로는 지적을 닫는 기록으로 남긴다.
  화면을 연 뒤 바뀐 줄, 판정기가 본 적 없는 줄은 확정하지 않는다
- 제출은 화면 주소의 토큰과 이 PC 주소(Host)가 맞아야 받는다
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import judge_layer2 as judge  # noqa: E402
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
        self.saved = (coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, judge.LOG)
        coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS = (
            self.dir / f for f in ("calls.jsonl", "a.jsonl", "d.jsonl", "x.jsonl"))
        judge.LOG = coverage.LOG
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
        self.row, self.lines = row, lines

    def tearDown(self) -> None:
        coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, judge.LOG = self.saved
        self.tmp.cleanup()

    def pick(self, data: dict, test, dec: str, own: str = "") -> dict:
        it = next(x for x in data["items"] if test(x))
        return {"id": it["id"], "dec": dec, **({"own": own} if own else {})}

    def rows(self, path: Path) -> list[dict]:
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []

    def open_fix_phrases(self) -> set[str]:
        lines = coverage.read_doc(self.doc).splitlines()
        return {fx["phrase"] for _, fx in coverage.open_fixes(coverage.doc_key(self.doc), lines)}

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

    # 2단계 — 제출

    def test_accepting_a_fix_records_the_answer_and_settles_the_edited_line(self) -> None:
        data = screen.collect(self.doc)
        code, out = screen.submit(self.doc, data, [self.pick(data, lambda x: "MSA" in x["phrase"], "accept")])
        self.assertEqual(1, code, "고치기 전에는 그 지적이 아직 열려 있음")
        self.assertIn("「모놀리식 구조에서 MSA로의 단계적 전환 참여」 → 「모놀리식 구조를 MSA로", out)
        self.assertEqual(["고침"], [d["answer"] for d in self.rows(coverage.DECISIONS)])
        # 세션이 화면에서 고른 글자 그대로 고치면 그 줄은 판정기가 다시 보지 않고, 지적은 표현이 사라져 닫힌다
        src = self.doc.read_text(encoding="utf-8")
        self.doc.write_text(src.replace("모놀리식 구조에서 MSA로의 단계적 전환 참여",
                                        "모놀리식 구조를 MSA로 단계적으로 전환하는 작업 참여"), encoding="utf-8")
        new = next(l for l in coverage.read_doc(self.doc).splitlines() if "MSA" in l)
        self.assertIn(coverage.line_key(new), coverage.approved(coverage.doc_key(self.doc)))
        self.assertNotIn("모놀리식 구조에서 MSA로의 단계적 전환 참여", self.open_fix_phrases())

    def test_keeping_a_fix_closes_it_with_the_user_answer_reason(self) -> None:
        data = screen.collect(self.doc)
        screen.submit(self.doc, data, [self.pick(data, lambda x: "MSA" in x["phrase"], "keep")])
        self.assertNotIn("모놀리식 구조에서 MSA로의 단계적 전환 참여", self.open_fix_phrases())
        self.assertEqual(["사용자답"], [r["reason"] for r in self.rows(coverage.DISMISSALS)])
        self.assertEqual(["그대로"], [d["answer"] for d in self.rows(coverage.DECISIONS)])

    def test_keeping_every_ask_on_a_line_answers_it_but_leaves_the_fact_check_open(self) -> None:
        data = screen.collect(self.doc)
        screen.submit(self.doc, data, [self.pick(data, lambda x: x["level"] == "사람 확인", "keep")])
        lines = coverage.read_doc(self.doc).splitlines()
        self.assertEqual([], coverage.open_asks(coverage.doc_key(self.doc), lines))
        self.assertIn("일 평균 320만 건", self.open_fix_phrases(), "같은 줄의 사실 확인 지적은 답하지 않았음")

    def test_own_text_for_an_ask_is_settled_without_a_later_answer_call(self) -> None:
        data = screen.collect(self.doc)
        screen.submit(self.doc, data, [self.pick(data, lambda x: x["level"] == "사람 확인", "own", "초당 최대 9천 건 트래픽")])
        self.assertEqual(["직접: 초당 최대 9천 건 트래픽"], [d["answer"] for d in self.rows(coverage.DECISIONS)])
        settled = [r for r in self.rows(coverage.ANSWERS) if r.get("approved")]
        self.assertEqual(1, len(settled))
        self.assertIn("초당 최대 9천 건 트래픽(일 평균 320만 건)", settled[0]["text"])

    def test_a_line_changed_after_the_screen_opened_is_refused(self) -> None:
        data = screen.collect(self.doc)
        self.doc.write_text(self.doc.read_text(encoding="utf-8").replace("MSA로의", "MSA 로의"), encoding="utf-8")
        _, out = screen.submit(self.doc, data, [self.pick(data, lambda x: "MSA" in x["phrase"], "accept")])
        self.assertIn("화면을 연 뒤 그 줄이 바뀌었습니다", out)
        self.assertEqual([], self.rows(coverage.DECISIONS))
        self.assertEqual([], self.rows(coverage.ANSWERS))

    def test_delegated_items_are_reported_but_not_recorded(self) -> None:
        data = screen.collect(self.doc)
        _, out = screen.submit(self.doc, data, [self.pick(data, lambda x: "MSA" in x["phrase"], "delegate")])
        self.assertIn("세션에 맡김 1건", out)
        self.assertEqual([], self.rows(coverage.DECISIONS) + self.rows(coverage.DISMISSALS) + self.rows(coverage.ANSWERS))

    def test_a_line_the_judge_never_saw_is_not_settled(self) -> None:
        notice = next(l for l in self.lines if "비고" in l)
        self.row["seen"] = [k for k in self.row["seen"] if k != coverage.line_key(notice)]
        coverage.LOG.write_text(json.dumps(self.row, ensure_ascii=False) + "\n", encoding="utf-8")
        data = screen.collect(self.doc)
        _, out = screen.submit(self.doc, data, [self.pick(data, lambda x: x["type"] == "style", "own", "공유함")])
        self.assertIn("고칠 것 1건", out)
        self.assertEqual([], self.rows(coverage.ANSWERS), "판정기가 안 본 줄을 확정하면 판정을 건너뜀")

    def test_submit_needs_the_page_token_and_the_local_host(self) -> None:
        page, data = screen.write_html(self.doc)
        got: dict = {}
        ready = threading.Event()

        def on_ready(url: str) -> None:
            got["url"] = url
            ready.set()
        t = threading.Thread(target=lambda: got.update(code=screen.serve(
            page, 20, False, on_ready, lambda picks: screen.submit(self.doc, data, picks))))
        with contextlib.redirect_stdout(io.StringIO()):
            t.start()
            self.assertTrue(ready.wait(10))
            base, token = got["url"].split("/?t=")
            with urllib.request.urlopen(got["url"], timeout=10) as r:
                self.assertIn("검토 화면", r.read().decode("utf-8"), "화면을 내주는 GET 이 살아 있어야 함")
            pick = self.pick(data, lambda x: "MSA" in x["phrase"], "keep")

            def post(body: dict, host: str | None = None) -> int:
                req = urllib.request.Request(base + "/submit", json.dumps(body).encode("utf-8"), method="POST",
                                             headers={"Content-Type": "application/json", **({"Host": host} if host else {})})
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        return r.status
                except urllib.error.HTTPError as e:
                    return e.code
            self.assertEqual(403, post({"t": "wrong", "picks": [pick]}))
            self.assertEqual(404, post({"t": token, "picks": [pick]}, host="evil.example"))
            self.assertEqual([], self.rows(coverage.DISMISSALS), "거절한 제출은 아무것도 기록하지 않음")
            self.assertEqual(200, post({"t": token, "picks": [pick]}))
            t.join(10)
        self.assertFalse(t.is_alive(), "제출을 받으면 화면 서버가 끝남")
        self.assertEqual(["사용자답"], [r["reason"] for r in self.rows(coverage.DISMISSALS)])


class TemplateTests(unittest.TestCase):

    def test_the_data_slot_appears_once(self) -> None:
        self.assertEqual(1, screen.TEMPLATE.read_text(encoding="utf-8").count("/*DATA*/null"))


if __name__ == "__main__":
    unittest.main()
