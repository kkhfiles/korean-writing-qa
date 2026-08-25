"""계기판의 세 값 판정을 고정한다.

이 판정을 두 번 틀렸다. 처음엔 같은 줄이라는 이유로 **다른 문제를 잡은 것**을
정탐으로 셌고(1건 과대), 고친 뒤에는 대상이 안 실린 지적을 미탐으로 밀었다
(1건 과소). 회수율이 그 판정 하나로 두 배까지 흔들리므로 시험으로 박아 둔다.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.eval_detectors import (
    concerns_label,
    llm_covers,
    load_llm_findings,
    locate_line,
    shares_run,
)


class ConcernsLabelTests(unittest.TestCase):
    def test_quoted_term_inside_label_is_a_hit(self) -> None:
        line = "- **강력한 `.claudeignore` 활용**: 대용량 데이터를 제외한다"
        message = "35행  「강력한」 — - **강력한 `.claudeignore` 활용**: 대용량"

        self.assertEqual(
            concerns_label(message, "강력한 `.claudeignore` 활용", line), "yes"
        )

    def test_quoted_term_outside_label_is_a_different_problem(self) -> None:
        line = "현재 우리 팀은 유기적 연동을 검토하고 있습니다"
        message = "12행  「우리」 — 현재 우리 팀은 유기적 연동을 검토하고 있습니다"

        self.assertEqual(concerns_label(message, "유기적 연동", line), "no")

    def test_unquoted_excerpt_overlapping_label_is_a_hit(self) -> None:
        line = "이러한 부분을 개선하기 위한 방안이 요구되고 있습니다."
        message = "8행  이러한 부분을 개선하기 위한 방안이 요구되고 있습니다. — 개조식으로"

        self.assertEqual(
            concerns_label(message, "이러한 부분을 개선하기 위한 방안이 요구되고 있습니다.", line),
            "yes",
        )

    def test_unquoted_excerpt_from_another_part_of_the_line_is_not_a_hit(self) -> None:
        line = "이러한 부분을 개선하기 위한 방안이 요구되고 있습니다. 또한 강력한 엔진을 도입한다"
        message = "8행  이러한 부분을 개선하기 위한 방안이 요구되고 있습니다. — 개조식으로"

        self.assertEqual(concerns_label(message, "강력한 엔진을 도입한다", line), "no")

    def test_advice_only_message_cannot_be_decided(self) -> None:
        """대상이 안 실린 지적 — 정탐도 미탐도 아니고 사람이 봐야 한다."""
        line = "- **VectorCAST 2026 SP3 정식 출시 (2026-07)** 소식을 정리한다"
        message = "25행  굵게 1개 더 — 라벨이 굵으면 값에서 또 굵게 하지 않는다"

        self.assertEqual(
            concerns_label(message, "**VectorCAST 2026 SP3 정식 출시 (2026-07)**", line),
            "unknown",
        )

    def test_undecidable_is_never_silently_merged_into_a_hit_or_a_miss(self) -> None:
        line = "- **굵은 값** 하나"
        advice_only = "3행  굵게 1개 더 — 라벨이 굵으면 값에서 또 굵게 하지 않는다"

        self.assertNotIn(
            concerns_label(advice_only, "**굵은 값**", line), {"yes", "no"}
        )


class SharesRunTests(unittest.TestCase):
    def test_short_incidental_overlap_does_not_count(self) -> None:
        self.assertFalse(shares_run("검증 자동화", "검증 결과를 정리한다"))

    def test_long_shared_run_counts(self) -> None:
        self.assertTrue(
            shares_run("반복해서 수행하는 작업이라", "앞부분 반복해서 수행하는 작업이라 뒷부분")
        )

    def test_string_shorter_than_the_window_never_matches(self) -> None:
        self.assertFalse(shares_run("짧다", "짧다"))


class LlmLayerScoringTests(unittest.TestCase):
    """2층 점수가 조작되지 않는지 본다.

    규칙 후보 12개를 실측한 결과 정밀도가 쓸 만한 것이 하나도 없었다. 남은 회수율은
    2층이 메워야 하므로 2층 점수가 곧 이 시스템의 성적이 된다. 그래서 **아무 지적이나
    내면 점수가 오르는 일**이 없어야 한다.
    """

    LABEL = "HTTPS URL을 통해 직접 플러그인 아카이브 패키지를 설치 및 관리하는 스펙 지원."

    def test_a_finding_that_quotes_the_labelled_text_counts(self) -> None:
        self.assertTrue(llm_covers(self.LABEL, self.LABEL))

    def test_a_partial_but_substantial_quote_counts(self) -> None:
        self.assertTrue(llm_covers(self.LABEL, "HTTPS URL을 통해 직접 플러그인"))

    def test_text_that_is_not_in_the_label_does_not_count(self) -> None:
        self.assertFalse(llm_covers(self.LABEL, "문서에 없는 아무 문장이나 지적해 본다"))

    def test_a_scrap_too_short_to_identify_anything_does_not_count(self) -> None:
        self.assertFalse(llm_covers(self.LABEL, "또"))
        self.assertFalse(llm_covers(self.LABEL, "URL"))

    def test_an_empty_report_does_not_count(self) -> None:
        self.assertFalse(llm_covers(self.LABEL, ""))
        self.assertFalse(llm_covers("", "무엇이든"))

    def test_findings_load_grouped_by_document(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "llm.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row, ensure_ascii=False)
                    for row in [
                        {"document_id": "doc-002", "original": "가"},
                        {"document_id": "doc-002", "original": "나"},
                        {"document_id": "doc-004", "original": "다"},
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            grouped = load_llm_findings(path)

        self.assertEqual(sorted(grouped), ["doc-002", "doc-004"])
        self.assertEqual(len(grouped["doc-002"]), 2)

    def test_no_findings_file_means_no_llm_credit(self) -> None:
        self.assertEqual(load_llm_findings(None), {})


class LocateLineTests(unittest.TestCase):
    def test_missing_text_returns_none_rather_than_a_wrong_line(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "doc.md"
            source.write_text("첫 줄\n둘째 줄\n", encoding="utf-8")

            self.assertIsNone(locate_line(source, "없는 문장"))
            self.assertEqual(locate_line(source, "둘째 줄"), 2)


if __name__ == "__main__":
    unittest.main()
