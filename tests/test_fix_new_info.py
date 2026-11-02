"""판정기 수정안이 **문서에 없는 정보를 들여오는지** 가르는 `coverage.new_info` 와, 검토 화면이 그런 지적을 일괄 반영에서
빼는지 본다 — 모델은 안 부른다.

(2026-11-02) 판정기 지적을 모델이 그대로 반영한 업무 문서가 고치지 않은 초안보다 낮게 평가됐고, 판정 사유에 가장 많이
나온 것이 「원문에 없던 조건, 정의, 계산값을 넣음」이다(`runs/bench-external-20261031/README.md` 「D3」). 판정기가
`check` 칸을 비우고 근거도 정해진 낱말을 피하면 새 숫자를 넣은 수정안이 「바로 반영」으로 일괄 반영에 들어갔다.

**지키는 것**

- 문서 어디에도 없는 수(단위 포함), 따옴표 안 이름, 영문 낱말을 들여오면 잡는다
- 원문의 수를 옮겨 쓰거나 표기만 바꾼 것(「3천만」과 「3,000만」, 「30퍼센트」와 「30%」), 숫자 없는 수정안은 안 잡는다
- 번호 목록의 번호, 줄을 가리키는 수, 문서 안 링크 주소, 「○○」 자리표시는 새 정보로 치지 않는다
- 검토 화면은 잡힌 지적을 「작성자 확인」으로 싣고 신뢰 설정 대상에서 뺀다
- 원문 수를 쓴 지적은 「바로 반영」 그대로 싣는다
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

DOC = """# 배포 안내

1. 대용량 트래픽(일 평균 320만 건) 처리 개선, 예산 3천만 원
2. 목표 응답 시간 30퍼센트 단축, 배포일 2026-10-30
3. 모놀리식 구조에서 MSA로 전환, 「주간 점검」 회의에서 보고, 지연 300ms
4. 담당 인원 12명, 자세한 내용은 [배포 절차](#배포-절차) 참고
"""


class NewInfoTests(unittest.TestCase):

    def test_numbers_names_and_latin_words_missing_from_the_document_are_caught(self) -> None:
        caught = {
            "일 평균 450만 건": "450만 건",
            "목표 응답 시간 40% 단축": "40%",
            "MSA 전환은 3일 안에 끝냄": "3일",              # 번호 목록의 「3.」 은 문서의 수가 아님
            "담당 인원 15명": "15명",
            "지연 500ms 이하": "500ms",
            "「월간 점검」 회의에서 보고": "「월간 점검」",
            "Kubernetes 로 전환": "Kubernetes",
            "예산 3천만 원, 그중 1.5억은 이월": "1.5억",
            "대상은 12개 팀": "12개",                         # 값이 같아도 단위가 다르면 다른 정보
        }
        for fix, token in caught.items():
            with self.subTest(fix=fix):
                self.assertIn(token, coverage.new_info(fix, DOC))

    def test_moved_or_reformatted_numbers_and_number_free_fixes_are_not_caught(self) -> None:
        clean = [
            "일 평균 주문 320만 건",                        # 원문 수 그대로
            "예산 3,000만 원",                              # 표기만 바꿈
            "목표 응답 시간 30% 단축",                       # 표기만 바꿈
            "10월 30일 배포",                               # 날짜에서 옮김
            "담당 12명이 MSA 전환을 맡음",                   # 같은 줄의 수를 재배치
            "처리 개선을 단계적으로 진행함",                  # 숫자 없음
            "모놀리식 구조를 MSA로 단계적으로 전환함",         # 원문 영문 낱말
            "「주간 점검」 회의에서 보고함",                   # 원문 이름
            "지연 300ms 유지",
            "[배포 절차](#배포-절차)를 참고",                 # 문서 안 링크 주소
            "(3행과 4행을 합침)",                            # 줄을 가리키는 수
            "(10~12행을 한 행으로 합침)",                    # 범위로 가리킨 줄
            "브런치 연재 「○○」 편",                         # 자리표시
            "",
        ]
        for fix in clean:
            with self.subTest(fix=fix):
                self.assertEqual([], coverage.new_info(fix, DOC))

    def test_man_read_as_a_particle_is_not_a_new_number(self) -> None:
        # 「숫자 8800만 나온 문서」의 「만」은 조사 — 8,800만으로만 읽어 새 수로 잡았다(실제 판정 기록)
        self.assertEqual([], coverage.new_info("숫자 8800만 나온 문서는 제외", "숫자 8800 단독 일치는 제외"))
        self.assertEqual(["8800만 건"], coverage.new_info("문서 8800만 건은 제외", "숫자 8800 단독 일치는 제외"))

    def test_the_whole_document_counts_not_only_the_line(self) -> None:
        self.assertEqual([], coverage.new_info("일정은 12명이 맡음", DOC))
        self.assertEqual(["12명"], coverage.new_info("일정은 12명이 맡음", "일정은 담당자가 맡음"))


class ReviewScreenTests(unittest.TestCase):

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

        def at(word):
            n = next(i for i, l in enumerate(lines, 1) if word in l)
            return {"line": n, "line_key": coverage.line_key(lines[n - 1]), "text": lines[n - 1]}
        row = {"ok": True, "key": coverage.doc_key(self.doc), "when": time.time(), "seen": coverage.seen_keys(lines),
               "fixes": [dict(at("트래픽"), phrase="처리 개선", fix="처리량 개선(일 450만 건 목표)",
                              why="무엇을 개선하는지 없음", category="판단 기준 누락", check=""),
                         dict(at("담당 인원"), phrase="담당 인원 12명", fix="담당 12명",
                              why="군더더기", category="군더더기 줄이기", check="")]}
        coverage.LOG.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        coverage.LOG, coverage.ANSWERS, coverage.DECISIONS, coverage.DISMISSALS, judge.LOG = self.saved
        self.tmp.cleanup()

    def test_a_fix_bringing_a_new_number_goes_to_the_author_without_a_check_field(self) -> None:
        two = {x["phrase"]: x for x in screen.collect(self.doc)["items"] if x["layer"] == "2층"}
        invented, plain = two["처리 개선"], two["담당 인원 12명"]
        self.assertEqual("info", invented["type"], "새 수를 들인 수정안이 「바로 반영」에 남음")
        self.assertEqual(["450만 건"], invented["new_info"])
        self.assertIn("450만 건", invented["check"], "작성자가 볼 확인할 사실이 비어 있음")
        self.assertEqual("replace", plain["type"], "원문 수를 쓴 수정안까지 작성자 확인으로 돌림")
        self.assertEqual([], plain["new_info"])
        self.assertFalse(coverage.needs_check({"check": "", "why": invented["why"]}),
                         "시료가 판정기 칸만으로 이미 사실 확인이면 이 시험이 새 조건을 안 잼")

    def test_trust_cannot_be_turned_on_for_a_category_whose_only_fix_brings_new_information(self) -> None:
        data = screen.collect(self.doc)
        screen.submit(self.doc, data, [], {"판단 기준 누락": True, "군더더기 줄이기": True})
        self.assertEqual(["군더더기 줄이기"], screen.load_trust())


if __name__ == "__main__":
    unittest.main()
