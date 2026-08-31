"""피드백 고리가 만들어져만 있는지, 실제로 쓰이는지 본다.

**왜.** 기록기·승격기·스키마가 다 있는데도 사용자 판정 8건이 그 통로를 안 거쳤다.
손으로 주석 파일에 넣고 규칙 문서를 직접 고쳤다. 그러면 세 가지가 사라진다.

1. 후보 파일에 안 쌓여 다음 승격 때 안 보인다
2. `promote_feedback.py`가 못 본다
3. 스키마 검사가 안 걸려 문맥 없는 문맥 규칙이 그냥 들어간다

**만들어 둔 것과 쓰는 것은 다른 사실이다** — 이 저장소가 다른 데서 반복해 확인한
실패 모양(「규칙을 썼다 ≠ 규칙이 적용된다」)이 스스로에게 난 경우다.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = REPO_ROOT / "data" / "feedback" / "candidates.jsonl"
VERDICTS = REPO_ROOT / "data" / "annotations" / "eval-004-line-review.jsonl"


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class FeedbackReachesTheCandidateFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidates = load(CANDIDATES)
        cls.verdicts = load(VERDICTS)
        if not cls.verdicts:
            raise unittest.SkipTest(f"판정 기록이 없습니다: {VERDICTS}")

    def test_every_adjudicated_line_became_a_candidate(self) -> None:
        """판정이 후보 파일에 안 닿으면 그 판정은 다음 승격에서 안 보인다."""
        blob = json.dumps(self.candidates, ensure_ascii=False)
        for row in self.verdicts:
            ref = f"{row['document_id']}.md:{row['line_number']}"
            with self.subTest(ref=ref):
                self.assertIn(ref, blob, f"{ref} 판정이 후보로 안 들어갔습니다")

    def test_the_rejected_finding_is_recorded_as_a_false_positive(self) -> None:
        """오탐을 교정으로 기록하면 없는 규칙이 생긴다."""
        agentic = [c for c in self.candidates if c.get("original") == "에이전틱"]

        self.assertTrue(agentic, "「에이전틱」 오탐 기록이 없습니다")
        for c in agentic:
            with self.subTest(candidate=c["candidate_id"]):
                self.assertEqual(c["user_verdict"], "false_positive")

    def test_the_held_verdict_is_not_recorded_as_a_correction(self) -> None:
        """보류를 교정으로 적으면 사용자가 안 정한 것을 정한 것으로 만든다."""
        held = {(r["document_id"], r["line_number"]) for r in self.verdicts
                if r["verdict"] == "보류"}
        self.assertTrue(held, "보류 판정을 못 읽었습니다")

        for c in self.candidates:
            ref = c.get("source_ref", "")
            for document, line in held:
                if f"{document}.md:{line}" in ref:
                    with self.subTest(candidate=c["candidate_id"]):
                        self.assertEqual(c["user_verdict"], "observed")

    def test_context_dependent_candidates_carry_their_context(self) -> None:
        """문맥 없는 문맥 규칙은 다음에 못 쓴다 — 기록기가 막지만 여기서도 본다."""
        for c in self.candidates:
            level = c.get("context_level")
            if level in (None, "sentence"):
                continue
            with self.subTest(candidate=c["candidate_id"], level=level):
                if level == "window":
                    self.assertTrue(c.get("context_before") or c.get("context_after"))
                elif level == "block":
                    self.assertTrue(c.get("context_excerpt"))
                elif level == "document":
                    self.assertTrue(c.get("source_hash"))

    def test_a_correction_carries_the_wording_it_proposes(self) -> None:
        """고칠 말이 없는 교정은 다음 사람이 무엇을 하라는 것인지 모른다."""
        for c in self.candidates:
            if c.get("user_verdict") not in ("corrected", "accepted"):
                continue
            with self.subTest(candidate=c["candidate_id"]):
                self.assertTrue(c.get("revised"), "고칠 말이 비었습니다")

    def test_the_candidate_file_is_not_empty_of_this_round(self) -> None:
        """빼는 쪽만 보면 파일이 통째로 비어도 위 시험들이 통과한다."""
        this_round = [c for c in self.candidates
                      if str(c.get("candidate_id", "")).startswith("e004-")]

        self.assertGreaterEqual(len(this_round), len(self.verdicts))


if __name__ == "__main__":
    unittest.main()
