"""덮개 계기판이 훅의 정의를 그대로 쓰는지, 값을 부풀리지 않는지 고정한다.

**왜 열렸나** — 2026-09-04. 목표가 「이 PC 에서 AI 가 만드는 모든 문서가 검사 통과한
한글」인데 그것을 재는 수단이 없었다. 2층 이행율은 재면서 1층 덮개는 안 쟀다.

**두 벌 두면 안 되는 값** — 무엇이 문서이고 무엇을 건너뛰는지. 계기판이 제 목록을
가지면 훅을 고쳐도 계기판은 옛 기준으로 세고, 그 숫자를 보고 「덮였다」고 읽는다.
같은 실패를 이 저장소가 이미 겪었다(발행 정의 사본 · 추출 논리 사본).

**이 계기판이 답하지 못하는 것** — 「실제로 돌았나」. 깨끗한 문서에서는 훅이 조용해서
기록만으로는 돌아서 조용한 것과 안 돈 것이 안 갈린다. 답하는 것은 **범위**뿐이고,
문서열에도 그렇게 적혀 있어야 한다.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

METER = Path(__file__).resolve().parent.parent / "scripts" / "measure_gate_coverage.py"
HOOK = Path.home() / ".claude" / "hooks" / "doc-style-gate.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GateCoverageMeterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HOOK.is_file():
            raise unittest.SkipTest(f"훅이 없습니다: {HOOK}")
        cls.meter = load(METER, "measure_gate_coverage")
        cls.source = METER.read_text(encoding="utf-8")

    def test_it_asks_the_hook_what_counts(self) -> None:
        """문서 판정과 제외 판정을 훅에서 가져와야 한다."""
        hook = self.meter.load_hook()

        self.assertTrue(hook.KOREAN_DOC.search("a.md"))
        self.assertTrue(hook.SKIP.search("x/scratchpad/a.md"))

    def test_it_keeps_no_list_of_its_own(self) -> None:
        """사본을 두면 훅을 고쳐도 계기판은 옛 기준으로 센다."""
        for banned in ("KOREAN_SOURCE_EXTENSIONS", '".md", ".html"', "scratchpad|"):
            with self.subTest(pattern=banned):
                self.assertNotIn(banned, self.source)

    def test_it_says_what_it_cannot_answer(self) -> None:
        """「범위」를 「돌았다」로 읽으면 안 돈 것이 통과로 보인다."""
        self.assertIn("「범위에 든다」이지 「실제로 돌았다」가 아니다", self.source)

    def test_no_documents_gives_no_verdict(self) -> None:
        """0건일 때 100%나 0%를 내면 안 된다 — 판정 불가다."""
        result = self.meter.measure(0, False)

        self.assertIsNone(result["덮개"])

    def test_its_own_sessions_are_left_out_by_default(self) -> None:
        """이 저장소의 시험이 수치를 부풀리지 않게 한다."""
        self.assertIn("include_self", self.source)
        self.assertIn('SELF = "korean-writing-qa"', self.source)
