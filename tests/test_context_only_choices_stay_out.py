"""맥락 한정 선택이 **일반 규칙으로 새지 않는지** 본다.

**왜 있나**(2026-09-17). 대장 F-022 의 고친 문장을 사용자가 골라 주면서 단서를
달았다 — 「한국어 검사기가 일반적으로 지켜야 할 항목이 아니라 특정 제품 홍보
맥락에서 고른 것」이다. 고른 문장은 원문의 병렬 구조만 고친 것이 아니라
**기록을 별도 작업으로 세우는 틀**이고, 그 틀은 그 맥락에서만 근거가 있다.

`core-rules.md` 의 「사용자가 확정한 대표 수정」 표는 2층이 **모든 문서에서**
읽는다. 거기 들어가면 상관없는 문서에 걸린다. 문서 종류에도 홍보 맥락을 담을
값이 없어(가장 가까운 `general` 이 일반 업무 문서다) 좁혀 넣을 자리가 없다.

**글로 적어 두는 것으로는 안 지켜진다** — 이 저장소가 여섯 차례 겪었다. 대장에
`general_rule: false` 를 달고, 그 표시가 붙은 것이 일반 규칙 파일에 나타나면
여기서 멈춘다.

⛔ 맥락은 **갈래로만** 적는다. 공개 저장소라 제품 이름은 어디에도 안 적는다.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

LEDGER = repo_paths.REPO / "data" / "cases" / "flagged-rounds.jsonl"

#: 일반 규칙이 사는 곳 — 맥락 한정 선택이 여기 있으면 안 된다
GENERAL_RULE_FILES = (
    repo_paths.SKILL / "references" / "core-rules.md",
    repo_paths.SKILL / "references" / "confirmed-rules.jsonl",
    repo_paths.REPO / "data" / "annotations" / "user-confirmed-phrases.jsonl",
)


def ledger() -> list[dict]:
    return [json.loads(line)
            for line in LEDGER.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def context_only() -> list[dict]:
    return [r for r in ledger() if r.get("general_rule") is False]


class ContextOnlyChoiceTests(unittest.TestCase):

    def test_the_marker_is_used(self) -> None:
        """표시가 하나도 없으면 이 시험이 아무것도 안 지킨다."""
        rows = context_only()
        if not rows:
            self.skipTest("맥락 한정으로 표시한 것이 없다")
        for r in rows:
            self.assertTrue(
                (r.get("note") or "").strip(),
                f"{r['flag_id']}: 왜 일반 규칙이 아닌지 note 에 적습니다")

    def test_context_only_choices_are_not_in_the_general_rules(self) -> None:
        """고른 문장도 원문도 일반 규칙 파일에 나타나면 안 된다."""
        rows = context_only()
        if not rows:
            self.skipTest("맥락 한정으로 표시한 것이 없다")
        for path in GENERAL_RULE_FILES:
            text = path.read_text(encoding="utf-8")
            for r in rows:
                for field in ("sentence", "revised"):
                    phrase = (r.get(field) or "").strip()
                    if not phrase:
                        continue
                    self.assertNotIn(
                        phrase, text,
                        f"{r['flag_id']} 의 「{field}」 가 {path.name} 에 "
                        "들어갔습니다 — 맥락 한정 선택이라 2층이 모든 문서에서 "
                        "읽으면 안 됩니다.\n   정말 일반 규칙으로 올릴 거면 "
                        "대장의 `general_rule` 을 먼저 지웁니다")

    def test_context_only_choices_keep_their_chosen_text(self) -> None:
        """고른 문장을 안 적으면 다음에 또 고르게 된다."""
        for r in context_only():
            self.assertTrue(
                (r.get("revised") or "").strip(),
                f"{r['flag_id']}: 고른 문장을 `revised` 에 남깁니다")


if __name__ == "__main__":
    unittest.main()
