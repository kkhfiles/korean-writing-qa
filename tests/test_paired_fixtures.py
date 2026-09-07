"""겉모습이 같은 두 묶음을 함께 돌려 정밀도를 잰다.

**왜 짝으로 재나.** 위반을 잡는 능력만 재면 「전부 지적」이 만점이 된다. 통과시켜야
하는 쪽을 같이 재야 규칙이 쓸 만한지 갈린다.

| 시료 | 무엇이 들었나 | 기대 |
|---|---|---|
| `exempt-fixture.md` | 위반과 겉모습이 같은 **정당한** 표기 20종 | 지적 0 |
| `violation-fixture.md` | 같은 모양의 **진짜** 위반 15종 | 15건 전부 · 제 갈래로 |

**정당한 쪽이 하나라도 걸리면 규칙이 너무 넓다.** 그것이 이 시험의 본체이고,
위반 쪽 수는 규칙이 조용히 사라지지 않았는지 보는 보조 확인이다.

**이 시험이 없던 동안** — 두 시료는 스크래치패드에만 있었고, 사례집은 「회귀 시험에
넣어 규칙을 고칠 때마다 다시 돈다」고 적고 있었다(2026-09-07에 발견). 적어 둔 것과
도는 것이 달랐다 — 「규칙을 썼다 ≠ 규칙이 적용된다」가 이 저장소에 난 사례다.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

PAIRED = Path(__file__).resolve().parent / "fixtures" / "paired"
EXEMPT = PAIRED / "exempt-fixture.md"
VIOLATION = PAIRED / "violation-fixture.md"

#: 위반 시료가 내야 하는 갈래. 하나라도 빠지면 그 규칙이 조용히 사라진 것이다.
EXPECTED_KINDS = {
    "서술형 종결", "절단형 종결", "절단형 의심", "「~하는 자리」", "모호한 지칭",
    "「회기」", "이중 피동", "번역투 이중 조사", "지어낸 명사구", "평가 수식어",
    "스캔 가치 없는 라벨",
}


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PairedFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not repo_paths.CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {repo_paths.CHECKER}")
        cls.checker = load_checker()

    def scan(self, path: Path):
        err, warn, slots = self.checker.scan_md(str(path), False, None)
        kind = lambda i: i[1] if len(i) == 3 else i[0]  # noqa: E731
        return [kind(i) for i in err], [kind(i) for i in warn], slots

    def test_exempt_fixture_is_completely_clean(self) -> None:
        """정당한 표기가 하나라도 걸리면 규칙이 너무 넓다."""
        err, warn, slots = self.scan(EXEMPT)
        self.assertGreater(slots, 20, "값 슬롯을 못 찾았습니다 — 검사가 안 돈 것입니다")
        self.assertEqual([], err, f"정당한 표기가 오류로 걸렸습니다: {err}")
        self.assertEqual([], warn, f"정당한 표기가 주의로 걸렸습니다: {warn}")

    def test_violation_fixture_catches_everything(self) -> None:
        """위반 쪽 수가 줄면 규칙 하나가 조용히 사라진 것이다."""
        err, warn, slots = self.scan(VIOLATION)
        self.assertGreater(slots, 20)
        self.assertEqual(15, len(err) + len(warn), f"오류 {err}\n주의 {warn}")

    def test_every_expected_kind_still_fires(self) -> None:
        """수만 맞고 갈래가 바뀌었으면 규칙 하나가 다른 규칙에 가려진 것이다."""
        err, warn, _ = self.scan(VIOLATION)
        got = set(err) | set(warn)
        self.assertEqual(set(), EXPECTED_KINDS - got, f"안 난 갈래: {sorted(EXPECTED_KINDS - got)}")

    def test_the_fixtures_are_in_the_repo(self) -> None:
        """스크래치패드에만 있으면 규칙을 고칠 때 아무도 안 돌린다."""
        for path in (EXEMPT, VIOLATION):
            with self.subTest(fixture=path.name):
                self.assertTrue(path.is_file(), f"시료가 없습니다: {path}")


if __name__ == "__main__":
    unittest.main()
