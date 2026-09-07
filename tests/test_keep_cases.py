"""판단 층에 「고치지 말라」 시료가 살아 있는지 지킨다.

**왜.** 회귀 시료 13건이 전부 「고쳐라」였다. 규칙에는 예외가 적혀 있어도
그것을 지킨 예가 하나도 없으니, 판단 층이 예외를 지켰는지 확인할 길이 없었다.
그 사이 「에이전틱」을 예외인데도 고치라고 낸 것이 사용자 판정에서 잡혔다.

**우연이 아니었다** — 자체 검사가 `expected_decision`을 FIX 로만 받고 있었다.
넣으려 해도 못 넣는 구조였다. 그래서 두 가지를 함께 고정한다.

1. KEEP 시료가 적어도 하나 있다
2. 자체 검사가 KEEP 을 받는다 — 그리고 아무 KEEP 이나 받지는 않는다
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

SKILL = repo_paths.SKILL
CASES = SKILL / "references" / "context-cases.jsonl"
SELF_TEST = SKILL / "scripts" / "self_test.py"


def load_cases() -> list[dict]:
    return [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]


class KeepCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CASES.is_file():
            raise unittest.SkipTest(f"시료가 없습니다: {CASES}")
        cls.cases = load_cases()

    def test_at_least_one_case_says_leave_it_alone(self) -> None:
        keeps = [c for c in self.cases if c.get("expected_decision") == "KEEP"]

        self.assertTrue(keeps, "「고치지 말라」 시료가 없습니다 — 예외를 지켰는지 확인할 길이 없습니다")

    def test_the_loanword_exemption_has_an_example(self) -> None:
        """규칙 문장만 있고 예가 없으면 그 규칙은 확인이 안 된다."""
        keeps = [c for c in self.cases
                 if c.get("expected_decision") == "KEEP"
                 and c.get("category") == "ENGLISH_OVERUSE"]

        self.assertTrue(keeps, "「불필요한 영어」 예외를 보이는 시료가 없습니다")
        for case in keeps:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(case["original"], case["revised"])
                self.assertTrue(case.get("keep_reason"), "왜 그대로 두는지가 없습니다")

    def test_every_keep_case_leaves_the_wording_alone(self) -> None:
        for case in self.cases:
            if case.get("expected_decision") != "KEEP":
                continue
            with self.subTest(case=case["case_id"]):
                self.assertEqual(case["original"], case["revised"])

    def test_skill_md_states_the_real_number_of_fixtures(self) -> None:
        """손으로 적은 개수는 시료를 더할 때 같이 안 고쳐진다 — 두 번 낡은 채 발견됐다.

        `SKILL.md` 는 「기준문 N쌍의 구조와 의미 보존을 확인한다」고 알린다. 시료를
        하나 더했는데 N 이 그대로면 읽는 쪽은 덜 확인된 줄 알거나, 빠진 시료가 있는
        줄 안다. 이번에 KEEP 시료를 넣으면서 13 이 14 가 됐는데 문장은 13 이었다.

        같은 낡음이 `core-rules.md` 의 원칙 개수에서도 났다. 글로 지키는 것으로는
        안 되는 종류라 양쪽 다 시험으로 옮긴다.
        """
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn(f"기준문 {len(self.cases)}쌍", text,
                      f"시료가 {len(self.cases)}건인데 SKILL.md 의 개수가 다릅니다")


class SelfTestAcceptsKeepTests(unittest.TestCase):
    """자체 검사가 KEEP 을 받는지 — 막고 있던 것이 되돌아오면 시료가 다시 못 들어간다."""

    @classmethod
    def setUpClass(cls) -> None:
        if not SELF_TEST.is_file():
            raise unittest.SkipTest(f"자체 검사가 없습니다: {SELF_TEST}")

    def run_self_test(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(SELF_TEST)],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_the_current_fixtures_pass(self) -> None:
        done = self.run_self_test()

        self.assertIn("PASSED", done.stdout, done.stdout[-600:])

    def test_a_keep_case_that_rewrites_is_rejected(self) -> None:
        """아무 KEEP 이나 받으면 「고치지 말라」 딱지만 붙이고 고치는 시료가 들어온다."""
        original = CASES.read_text(encoding="utf-8")
        broken = dict(next(c for c in load_cases() if c["expected_decision"] == "KEEP"))
        broken["case_id"] = "CTX-BROKEN-KEEP"
        broken["revised"] = broken["original"] + " 자율 수행"
        try:
            CASES.write_text(original + json.dumps(broken, ensure_ascii=False) + "\n",
                             encoding="utf-8")
            done = self.run_self_test()
        finally:
            CASES.write_text(original, encoding="utf-8")

        self.assertIn("FAILED", done.stdout, "고치는 KEEP 시료가 통과했습니다")
        self.assertIn("CTX-BROKEN-KEEP", done.stdout)

    def test_a_keep_case_without_a_reason_is_rejected(self) -> None:
        original = CASES.read_text(encoding="utf-8")
        broken = dict(next(c for c in load_cases() if c["expected_decision"] == "KEEP"))
        broken["case_id"] = "CTX-NOREASON-KEEP"
        broken.pop("keep_reason", None)
        try:
            CASES.write_text(original + json.dumps(broken, ensure_ascii=False) + "\n",
                             encoding="utf-8")
            done = self.run_self_test()
        finally:
            CASES.write_text(original, encoding="utf-8")

        self.assertIn("FAILED", done.stdout, "이유 없는 KEEP 시료가 통과했습니다")


class ConfirmedCorrectionTests(unittest.TestCase):
    """사용자 판정이 판단 층이 읽는 표에 실제로 실렸는지."""

    RULES = SKILL / "references" / "core-rules.md"

    @classmethod
    def setUpClass(cls) -> None:
        if not cls.RULES.is_file():
            raise unittest.SkipTest(f"규칙이 없습니다: {cls.RULES}")
        cls.text = cls.RULES.read_text(encoding="utf-8")

    def test_the_missed_findings_reached_the_table(self) -> None:
        """표에 안 실리면 판단 층이 그 교정을 못 본다 — 이 표가 유일한 통로다."""
        for phrase in ("로컬 실행 환경 구축 기능 추가", "에러", "인도", "재정립",
                       "시드", "AI 조립 라인"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.text)

    def test_each_correction_carries_its_condition(self) -> None:
        """조건 없이 실으면 낱말 대 낱말 치환이 되어 정상 문장까지 고친다."""
        rows = [l for l in self.text.splitlines()
                if l.startswith("| ") and l.count("|") >= 4 and "---" not in l]
        body = [r for r in rows if not r.startswith("| 수정 전")]

        self.assertGreaterEqual(len(body), 14)
        for row in body:
            with self.subTest(row=row[:40]):
                condition = row.split("|")[3].strip()
                self.assertTrue(condition, "적용 조건이 비었습니다")


if __name__ == "__main__":
    unittest.main()
