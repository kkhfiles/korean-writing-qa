"""추출 논리의 사본이 저장소로 되돌아오지 못하게 막는다.

**왜 열렸나** — 2026-09-03 아키텍처 검토. `source_text.py` 가 스킬과 이 저장소에
**byte 단위로 같은** 사본으로 있었다(12,174바이트 · 해시 동일). README 가 「사본을
두지 않는다」고 적어 놓은 바로 그것이다.

**아직 안 갈라졌던 까닭** — 8월 24일 이후 양쪽 다 안 고쳤다. 위험은 잠복이었다.

**앞서 실제로 갈라진 적이 있다** — 그때는 회귀 시험이 저장소 사본을 지키는데
사용자에게 도는 것은 스킬 사본이라, **스킬을 망가뜨려도 시험이 초록으로 남았다.**
게이트에서 가장 나쁜 실패다.

**섞여 있던 두 방식** — 탐지 논리는 `skill_bridge` 로 다리를 놓고(4개 파일), 추출
논리만 사본을 직접 불렀다(2개 파일). 이제 둘 다 다리를 쓴다.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
TESTS = REPO / "tests"


class NoExtractorCopyTests(unittest.TestCase):
    def test_the_repo_keeps_no_extractor_of_its_own(self) -> None:
        """사본이 되돌아오면 다시 갈라지고, 그때는 시험이 통과해서 아무도 모른다."""
        self.assertFalse(
            (SCRIPTS / "source_text.py").exists(),
            "추출 논리 사본이 되돌아왔습니다 — 정본은 배포된 스킬입니다")

    def test_nothing_imports_a_local_extractor(self) -> None:
        """파일만 지우고 import 를 남기면 다음 사람이 사본을 되살린다."""
        pattern = re.compile(r"^\s*(?:from\s+(?:scripts\.)?source_text\s+import"
                             r"|import\s+source_text)\b", re.M)
        for path in sorted([*SCRIPTS.glob("*.py"), *TESTS.glob("*.py")]):
            with self.subTest(file=path.name):
                self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")),
                                  f"{path.name} 이 저장소 사본을 부릅니다")

    def test_the_bridge_serves_the_extractor(self) -> None:
        """다리가 추출 논리도 실어 나르는지 — 못 나르면 위 둘이 무의미하다."""
        from scripts import skill_bridge

        module = skill_bridge.load("source_text")

        self.assertTrue(callable(module.extract_source_text))
        self.assertIn(".md", module.TEXT_EXTENSIONS)

    def test_the_provenance_hash_points_at_the_deployed_file(self) -> None:
        """실행 기록에 적히는 해시가 실제로 돈 파일의 것이어야 한다."""
        source = (SCRIPTS / "scan_path_metaphor.py").read_text(encoding="utf-8")

        self.assertIn("skill_bridge.skill_home()", source)
        self.assertNotIn('with_name("source_text.py")', source)
