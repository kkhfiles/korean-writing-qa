"""2층 이행률 측정기가 자기 자신에게 속지 않는지 확인한다.

**왜 시험이 필요한가.** 이 측정기는 두 번 틀렸다.

1. 「발행 직전」 넉 자만 찾아 **그 문구를 논의한 글까지** 셌다 — 발화율 208%
2. 이 시스템을 만드는 세션이 문구를 계속 인용하는데 그것도 셌다

둘 다 「측정기가 자기 활동을 성과로 센다」는 한 가지 실패다. 이 저장소는 같은
실패를 계기판 쪽에서도 겪었다(회수율 분모가 순환이던 것).

**침묵해야 하는 자리도 지킨다** — 붙인 뒤 표본이 적으면 판정 불가라고 말해야
한다. 0%를 결과로 내면 「안 먹혔다」로 읽힌다.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "measure_layer2_uptake.py"


def load():
    spec = importlib.util.spec_from_file_location("measure_layer2_uptake", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MarkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def test_the_marker_is_the_whole_line_the_hook_prints(self) -> None:
        """짧게 잡으면 그 문구를 논의한 글까지 세어 발화율이 100%를 넘는다."""
        self.assertGreater(len(self.mod.NOTICE_MARK), 20)
        self.assertIn("finalize-korean-document", self.mod.NOTICE_MARK)

    def test_the_marker_matches_what_the_hook_actually_prints(self) -> None:
        """훅 문구를 고치면 측정기가 조용히 0을 내기 시작한다."""
        hook = Path.home() / ".claude" / "hooks" / "doc-style-gate.py"
        if not hook.is_file():
            self.skipTest(f"훅이 없습니다: {hook}")

        self.assertIn(self.mod.NOTICE_MARK, hook.read_text(encoding="utf-8"),
                      "측정기가 찾는 문구가 훅에 없습니다")

    def test_this_project_is_left_out_of_the_count(self) -> None:
        """이 시스템을 만드는 세션은 문구를 계속 인용한다 — 성과가 아니다."""
        self.assertEqual(self.mod.SELF, "korean-writing-qa")


class VerdictTests(unittest.TestCase):
    """표본이 적을 때 침묵하는지 — 0%를 결과로 내면 「안 먹혔다」로 읽힌다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def test_a_small_sample_is_reported_as_undecidable(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("판정 불가", source)
        self.assertIn('after["발행 호출"] < 20', source)

    def test_the_two_stages_are_measured_apart(self) -> None:
        """어디서 새는지가 처방을 가른다 — 합치면 무엇을 고칠지 모른다."""
        result = self.mod.measure(days=1)

        for when in ("붙이기 전", "붙인 뒤"):
            with self.subTest(when=when):
                row = result["buckets"][when]
                for field in ("발행 호출", "안내 발화", "스킬 호출",
                              "안내 발화율", "안내 이행율"):
                    self.assertIn(field, row)


if __name__ == "__main__":
    unittest.main()
