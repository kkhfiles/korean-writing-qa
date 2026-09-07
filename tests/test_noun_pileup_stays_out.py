"""「명사로 굳힌 서술」이 결정 규칙으로 되돌아오지 않게 막고, 실험을 재현 가능하게 둔다.

**무엇을 지키나.** 이 갈래는 참 문제 4건인데 1층이 0건 잡는다 — 그래서 규칙을 만들고
싶어진다. 실제로 만들어 재 봤고 못 쓴다는 결론이 났다(`runs/diagnostic-009`).

| 임계 | 회수 | 정밀도 |
|---|---|---|
| 덩어리 4 · 행위 2 | 참 3/3 | 표본 30건에서 15% |
| 덩어리 6 · 행위 3 | 참 1/3 | 22건 중 12건 · 55% |

**구조적인 이유** — 개조식 라벨이 곧 명사 나열이다. 「버그 수정 반영 확인」은 정상
값이고 「로컬 실행 환경 구축 기능 추가」는 잘못인데 표면이 같다. 이 검사기가 강제하는
문체가 바로 그 모양이라, 문체를 유지하는 한 표면으로는 안 갈린다.

**그래서 두 가지를 함께 고정한다.**

1. 실험이 재현된다 — 임계를 다시 재 보려는 사람이 처음부터 만들지 않는다
2. 규칙이 전역 검사기로 새어 들어가지 않는다 — 들어가면 정상 라벨이 무더기로 걸린다
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "detect_noun_pileup.py"
CHECKER = repo_paths.CHECKER


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExperimentStillReproducesTests(unittest.TestCase):
    """실험이 재현돼야 임계를 다시 재 볼 수 있다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load(SCRIPT, "detect_noun_pileup")

    def test_the_loose_threshold_catches_every_true_case(self) -> None:
        for case in self.mod.TRUE_CASES:
            with self.subTest(case=case[:24]):
                self.assertIsNotNone(self.mod.fires(case, 4, 2))

    def test_the_loose_threshold_spares_the_clean_cases(self) -> None:
        """이 열 건을 놓치기 시작하면 임계가 아니라 토큰 나누기가 깨진 것이다."""
        for case in self.mod.CLEAN_CASES:
            with self.subTest(case=case[:24]):
                self.assertIsNone(self.mod.fires(case, 4, 2))

    def test_tightening_trades_recall_away(self) -> None:
        """좁히면 정밀도는 오르지만 참 3건 중 1건만 남는다 — 그게 닫은 이유다."""
        tight = [c for c in self.mod.TRUE_CASES if self.mod.fires(c, 6, 3)]

        self.assertEqual(len(tight), 1)

    def test_the_normal_label_shape_is_the_collision(self) -> None:
        """정상 라벨과 참 문제가 같은 임계에 걸린다 — 결론의 근거다."""
        self.assertIsNotNone(self.mod.fires("버그 수정 반영 확인", 4, 2))
        self.assertIsNotNone(self.mod.fires("로컬 실행 환경 구축 기능 추가", 4, 2))


class RuleStaysOutOfTheCheckerTests(unittest.TestCase):
    """전역 검사기로 새어 들어가면 정상 라벨이 무더기로 걸린다."""

    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load(CHECKER, "doc_style_check")

    def test_a_normal_outline_label_is_not_flagged(self) -> None:
        head = "# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text(head + "- 버그 수정 반영 확인\n", encoding="utf-8")
            errors, warnings, _ = self.checker.scan_md(str(target))

        self.assertEqual([], list(errors))
        self.assertEqual([], list(warnings))

    def test_the_checker_has_no_action_noun_list(self) -> None:
        """행위 명사 목록이 전역 검사기에 생기면 이 규칙이 들어간 것이다."""
        source = CHECKER.read_text(encoding="utf-8")

        self.assertNotIn("ACTION_NOUN", source)

    def test_the_reason_is_written_down(self) -> None:
        """근거 없이 닫으면 다음 사람이 같은 실험을 다시 한다."""
        record = REPO_ROOT / "runs" / "diagnostic-009" / "README.md"

        self.assertTrue(record.is_file(), "판정 기록이 없습니다")
        text = record.read_text(encoding="utf-8")
        for phrase in ("개조식 라벨이 곧 명사 나열", "판단 층"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_entry_point_carries_the_reason_too(self) -> None:
        """맨 앞 줄이 「잘 안 됨」이면 훑어보는 사람은 까닭을 못 얻는다.

        이 문서의 값은 「같은 실험을 다시 하지 않게 하는 것」이고, 그 값은 진입점에서
        나온다. 본문에만 있으면 끝까지 읽은 사람만 얻는다.
        """
        record = REPO_ROOT / "runs" / "diagnostic-009" / "README.md"
        head = "\n".join(record.read_text(encoding="utf-8").splitlines()[:10])

        self.assertIn("개조식 라벨이 곧 명사 나열", head)


if __name__ == "__main__":
    unittest.main()
