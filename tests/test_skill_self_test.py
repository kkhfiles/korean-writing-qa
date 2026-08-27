"""배포된 스킬의 자체 시험을 이 저장소 시험에서도 돌린다.

**왜.** 지금까지 `pytest` 는 스킬을 불러다 쓰기만 하고 스킬이 들고 다니는 자체
시험은 안 돌렸다. 그래서 스킬 쪽 회귀는 사람이 손으로 한 번 더 돌려야 잡혔고,
그 손이 빠지면 아무도 안 본다.

**무엇을 확인하나** — 통과 여부와 함께 단언 수가 줄지 않았는지 본다. 시험을
지우면서 통과시키는 것이 가장 조용한 회귀다.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest

from scripts import skill_bridge

# 지금까지 쌓인 단언 수 — 줄어들면 무언가 지워진 것이다
MINIMUM = {
    "detector": 68,
    "meaning": 24,
    "meaning_markers": 13,
    "feedback_workflow": 12,
    "detector_format": 24,
}


class SkillSelfTestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        script = skill_bridge.skill_home() / "scripts" / "self_test.py"
        if not script.is_file():
            raise unittest.SkipTest(f"자체 시험이 없습니다: {script}")
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(script), "--format", "json"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(script.parent),
        )
        cls.stdout = done.stdout
        try:
            cls.result = json.loads(done.stdout)
        except json.JSONDecodeError:
            cls.result = None

    def test_the_skill_self_test_passes(self) -> None:
        self.assertIsNotNone(self.result, f"자체 시험이 JSON 을 안 냈습니다:\n{self.stdout[:400]}")
        self.assertEqual(self.result["status"], "PASSED", self.stdout[:800])

    def test_no_assertion_group_shrank(self) -> None:
        """단언을 지우면서 통과시키는 것이 가장 조용한 회귀다."""
        self.assertIsNotNone(self.result)
        for group, floor in MINIMUM.items():
            with self.subTest(group=group):
                self.assertIn(group, self.result, f"{group} 묶음이 사라졌습니다")
                self.assertGreaterEqual(
                    self.result[group]["assertions"], floor,
                    f"{group} 단언이 {floor} 아래로 줄었습니다",
                )


if __name__ == "__main__":
    unittest.main()
