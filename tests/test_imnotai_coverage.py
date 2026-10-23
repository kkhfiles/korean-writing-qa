"""im-not-ai 기록본의 모든 번호가 대조표에 있는지, 비교가 바뀐 것을 잡는지 본다.

**왜.** 2026-10-23 에 「표본 0건이라 뺌」으로 패턴 여럿이 대조 없이 빠졌다. 기록본을 갱신하면
이 시험이 대조표에 새 번호의 행을 요구해서, 대조 없이 기록본만 올리는 길이 막힌다.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / "data" / "catalog" / "imnotai-snapshot.json"
TABLE = REPO / "docs" / "imnotai-coverage-20261023.md"


def load_tool():
    spec = importlib.util.spec_from_file_location("upstream", REPO / "scripts" / "check_imnotai_upstream.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CoverageTableTests(unittest.TestCase):
    def test_every_recorded_id_has_a_row(self) -> None:
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cells = set()
        for line in TABLE.read_text(encoding="utf-8").splitlines():
            if line.startswith("| "):
                first = line.split("|")[1].strip()
                cells |= {x.strip() for x in re.split(r",", first)}
                cells.add(first)
        missing = sorted(i for part in ("taxonomy", "candidates") for i in snap[part] if i not in cells)
        self.assertEqual([], missing, f"대조표에 행이 없는 번호: {missing} — 맡은 곳을 정해 행을 넣습니다")


class DiffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load_tool()

    TAX = ("### A-1. \"~에 대해\" 남발 [S1]\n- _quick: true · quick_pattern: 한 문단 3회+ · quick_fix: 조사로_\n"
           "### A-2. \"~를 통해\" 남발 [S2] · v2.6 신규\n- 패턴: 경로\n")

    def test_version_tail_is_not_part_of_the_title(self) -> None:
        got = self.tool.parse_taxonomy(self.TAX)
        self.assertEqual('"~를 통해" 남발 [S2]', got["A-2"]["title"])
        self.assertTrue(got["A-1"]["quick"])

    def test_added_changed_and_removed_are_reported(self) -> None:
        old = {"version": "1", "taxonomy": self.tool.parse_taxonomy(self.TAX), "candidates": {}}
        new_tax = self.TAX.replace("한 문단 3회+", "한 문단 2회+") + "### B-9. 새 패턴 [S2]\n"
        new = {"version": "2", "taxonomy": self.tool.parse_taxonomy(new_tax.replace("### A-2.", "### Z-2.")),
               "candidates": {}}
        text = " ".join(self.tool.diff(old, new))
        for word in ("판 1 → 2", "새 패턴", "B-9", "바뀐 패턴 A-1", "없어진 패턴 A-2"):
            self.assertIn(word, text)

    def test_example_only_edits_are_quiet(self) -> None:
        """예문과 처방만 바뀐 것은 세지 않는다 — 매주 알림이 오면 아무도 안 본다."""
        old = {"version": "1", "taxonomy": self.tool.parse_taxonomy(self.TAX), "candidates": {}}
        new = {"version": "1", "taxonomy": self.tool.parse_taxonomy(self.TAX.replace("- 패턴: 경로", "- 패턴: 경로와 수단")),
               "candidates": {}}
        self.assertEqual([], self.tool.diff(old, new))

    def test_candidate_status_change_is_reported(self) -> None:
        text = "## 후보 목록\n\n| 임시ID | 패턴 | 실증 | 상태 | 다음 |\n|---|---|---|---|---|\n| K-1 | 열거 | run | pending | 갭 |\n"
        old = {"version": "1", "taxonomy": {}, "candidates": self.tool.parse_candidates(text)}
        new = {"version": "1", "taxonomy": {}, "candidates": self.tool.parse_candidates(text.replace("pending", "promoted"))}
        self.assertEqual(["바뀐 후보 K-1"], self.tool.diff(old, new))


if __name__ == "__main__":
    unittest.main()
