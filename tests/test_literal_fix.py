"""글자 그대로 넣을 수 없는 수정안이 문서에 들어가지 않는지 본다.

(2026-11-11 AI 말투 시연) 판정기 수정안 「바뀐 업무 방식(구체적으로 무엇이 바뀌었는지 기재)」와
「온보딩 문서 미완료 ↵ 시험 데이터 관리 체계 재정립 필요」가 「고침」 답과 재현 일감의 반영으로 문서에 글자 그대로
들어갔다. 사용자가 사람 확인 표에 「고침」이나 「전부 의견대로」로 답하는 실사용 경로에서도 같은 일이 난다.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import judge_layer2 as judge  # noqa: E402

PLACEHOLDER = "핵심은 도구 도입 자체가 아니라 바뀐 업무 방식(구체적으로 무엇이 바뀌었는지 기재)"
SPLIT = "신규 입사자 온보딩 문서 미완료 ↵ 시험 데이터 관리 체계 재정립 필요"


class LiteralFixTests(unittest.TestCase):

    def test_instructions_and_markers_are_not_literal(self) -> None:
        for fix in (PLACEHOLDER, SPLIT, "○○팀과 협의", "(문장 삭제)", "첫 줄\n둘째 줄", "",
                    "원인 정리(작성자 확인 필요)", "담당자 [이름 기재]"):
            self.assertFalse(judge.literal_fix(fix), fix)

    def test_ordinary_text_with_brackets_stays_literal(self) -> None:
        for fix in ("보유한 컴퓨터로 구성하는", "빌드 속도가 약 5.4배로 빨라짐(QA팀 측정)", "입력값 검증 추가",
                    "회귀 시험 범위 확대(「회귀 시험 운영」 항목 참조)", "의존성 충돌로 인한 빌드 오류 (심각도: 중)"):
            self.assertTrue(judge.literal_fix(fix), fix)

    def test_answer_edit_refuses_the_placeholder_seen_in_the_demo(self) -> None:
        line = "* 핵심은 도구가 아니라 일하는 방식"
        asks = [{"phrase": "핵심은 도구가 아니라 일하는 방식", "fix": PLACEHOLDER, "category": "근거 없는 전제"}]
        self.assertIsNone(judge.edited_by_answer(line, asks), "자리 표시가 든 수정안을 「고침」 답으로 넣었습니다")
        asks[0]["fix"] = "핵심은 바뀐 업무 방식"
        self.assertEqual("* 핵심은 바뀐 업무 방식", judge.edited_by_answer(line, asks))

    def test_answer_edit_refuses_the_split_marker(self) -> None:
        line = "  * 신규 입사자 온보딩 문서 미완료, 시험 데이터 관리 체계 재정립 필요."
        asks = [{"phrase": "신규 입사자 온보딩 문서 미완료, 시험 데이터 관리 체계 재정립 필요", "fix": SPLIT,
                 "category": "나열의 관계와 적용 범위 밝히기"}]
        self.assertIsNone(judge.edited_by_answer(line, asks), "「↵」 표시를 글자 그대로 넣었습니다")

    def test_fix_notes_warn_the_person_who_reads_the_list(self) -> None:
        for fix in (PLACEHOLDER, SPLIT):
            notes = judge.fix_notes(fix, "원문", set(), None)
            self.assertTrue(any("그대로 넣을 글이 아님" in n for n in notes), (fix, notes))
        self.assertFalse(any("그대로 넣을 글이 아님" in n for n in judge.fix_notes("(문장 삭제)", "원문", set(), None)))

    def test_the_judge_is_told_not_to_write_instructions_into_fix(self) -> None:
        prompt = judge.probe.system_prompt() if hasattr(judge, "probe") else __import__("probe_layer2_kinds").system_prompt()
        self.assertIn("작성자가 채울 지시", prompt)
        self.assertIn("적용 조건이 맞을 때만", prompt)


if __name__ == "__main__":
    unittest.main()
