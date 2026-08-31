"""회수율 계산이 판정을 제대로 읽는지 확인한다.

**왜 시험이 필요한가.** 이 계산은 한 번 틀렸다. ① 표에 「이미 문제 아님으로
판정된 것」이 섞여 있었는데 빈 칸을 전부 「이 지적이 맞다」로 읽어, 참 문제
집합에 있지도 않은 문제를 한 건 넣고 그것을 「아무도 못 잡은 것」으로 셌다.

**세는 규칙**
- 참 문제 = ①에서 동의한 것 + ②에서 새로 나온 것
- 보류·오탐은 분모에서 뺀다 — 참인지 안 정해진 것을 참으로 세면 가정이 된다
- 사람 라벨은 탐지기가 아니다 — 예전 회수율을 부풀린 출처라 층으로 안 센다
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "measure_recall.py"
VERDICTS = REPO_ROOT / "data" / "annotations" / "eval-004-line-review.jsonl"

HEADER = "# 줄 단위 판정 — doc-002\n"
FINDING_HEAD = "\n## ① 지적 확인 — n건\n\n| 행 | 갈래 | 구절 | 고칠 말 | 왜 | 누가 | 판정 |\n|---|---|---|---|---|---|---|\n"
CLEAN_HEAD = "\n## ② 빠진 것 찾기 — n행\n\n| 행 | 원문 | 판정 |\n|---|---|---|\n"


def load():
    spec = importlib.util.spec_from_file_location("measure_recall", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def sheet(self, findings: list[str], clean: list[str]) -> tuple:
        text = HEADER + FINDING_HEAD + "".join(findings) + CLEAN_HEAD + "".join(clean)
        return self.mod.parse_sheet(text)

    def test_the_two_tables_are_told_apart(self) -> None:
        """칸 수가 같아 보이면 한쪽이 다른 쪽으로 새어 들어간다."""
        document, findings, clean = self.sheet(
            ["| 14 | 불필요한 영어 | 「에이전틱」 | 「자율 수행」 | 설명 | 2층 읽기 | |\n"],
            ["| 22 | 「원문 한 줄」 | |\n"],
        )

        self.assertEqual(document, "doc-002")
        self.assertEqual(len(findings), 1)
        self.assertEqual(len(clean), 1)

    def test_an_escaped_pipe_does_not_split_a_cell(self) -> None:
        """원문에 표가 들어 있으면 칸이 밀려 엉뚱한 값을 센다."""
        _document, _findings, clean = self.sheet(
            [], ["| 39 | 「\\| 도구 \\| 비고 \\|」 | |\n"])

        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0][2], "")


class MeasureTests(unittest.TestCase):
    """실제 저장된 판정으로 센 값이 손으로 센 것과 맞는지 본다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = load().measure()

    def test_the_denominator_is_what_was_actually_judged(self) -> None:
        result = self.result

        self.assertEqual(result["참 문제"],
                         result["확인된 지적"] + result["아무도 못 잡은 것"])
        self.assertGreaterEqual(result["참 문제"], 30, "판정을 거의 못 읽었습니다")

    def test_the_verdicts_are_counted_as_recorded(self) -> None:
        """판정 기록과 센 값이 어긋나면 어느 쪽이 맞는지 아무도 모른다.

        갈래를 하나라도 다른 통에 넣으면 여기서 걸린다 — 오탐을 보류로 세거나
        보류를 참 문제로 세는 것 모두.
        """
        recorded = [json.loads(l) for l in
                    VERDICTS.read_text(encoding="utf-8").splitlines() if l.strip()]
        expected = Counter(r["verdict"] for r in recorded)

        self.assertEqual(self.result["오탐"], expected["오탐"])
        self.assertEqual(self.result["보류"], expected["보류"])
        self.assertEqual(self.result["아무도 못 잡은 것"], expected["미탐"])

    def test_the_held_verdict_stays_out_of_the_denominator(self) -> None:
        """참인지 안 정해진 것을 참으로도 거짓으로도 세면 안 된다."""
        result = self.result
        held = {i["line_number"] for i in result["보류 목록"]}

        self.assertEqual(held & {i["line_number"] for i in result["미탐 목록"]}, set())
        self.assertEqual(result["참 문제"],
                         result["확인된 지적"] + result["아무도 못 잡은 것"])

    def test_the_human_label_is_not_counted_as_a_detector(self) -> None:
        """사람 라벨을 층으로 세면 예전의 부풀린 회수율로 되돌아간다."""
        self.assertNotIn("사람이 고치라 함", load().DETECTORS)
        self.assertLess(self.result["회수율"]["둘 중 하나"], 1.0)

    def test_the_first_layer_is_measured_separately(self) -> None:
        """층을 합쳐서만 내면 어느 쪽이 일하는지 안 보인다."""
        rates = self.result["회수율"]

        for layer in ("1층", "2층", "둘 중 하나"):
            self.assertIn(layer, rates)
        self.assertLessEqual(rates["1층"], rates["둘 중 하나"])
        self.assertLessEqual(rates["2층"], rates["둘 중 하나"])


class SettledFindingTests(unittest.TestCase):
    """① 표에 「이미 문제 아님」 행이 섞여 있어도 참 문제로 세지 않는지.

    지금 저장된 시트는 그런 행을 ③으로 갈라 놓아 이 경로가 안 밟힌다. 옛
    형식 시트에서는 밟히므로 시료로 만들어 확인한다 — 실제로 그 형식에서
    한 건을 반대로 셌다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def measure_with(self, who: str) -> dict:
        sheet = (
            HEADER
            + FINDING_HEAD
            + f"| 52 | 「경로」를 그대로 씀 | 「스캔 경로 정리」 | 「스캔 대상 경로 정리」 | — | {who} | |\n"
            + CLEAN_HEAD
            + "| 60 | 「원문 한 줄」 | |\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "line-review-doc-002.md"
            path.write_text(sheet, encoding="utf-8")
            return self.mod.measure(sheet_dir=Path(directory),
                                    verdict_file=Path(directory) / "none.jsonl")

    def test_a_settled_non_problem_is_left_out(self) -> None:
        self.assertEqual(self.measure_with("사람이 괜찮다 함")["참 문제"], 0)

    def test_an_ordinary_finding_is_still_counted(self) -> None:
        """빼는 쪽만 시험하면 통째로 안 세도 통과한다."""
        self.assertEqual(self.measure_with("2층 읽기")["참 문제"], 1)


if __name__ == "__main__":
    unittest.main()
