"""줄 단위 판정 시트가 원문과 어긋나지 않는지 확인한다.

옮겨 적는 사이 어긋나면 **없는 문장을 판정하게 된다.** 그 판정은 라벨이 되어
회수율의 분모로 들어가므로, 어긋난 채로 지나가면 수치가 조용히 거짓이 된다.

표 안에 표를 넣는 줄(`| 도구 | 비고 |`)은 세로줄을 이스케이프해야 칸이 안
밀린다. 이스케이프를 안 하면 시트가 깨지고, 대조도 함께 어긋난다.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPO_ROOT / "scripts" / "build_line_review_sheet.py"
SOURCE_DIR = REPO_ROOT / "data" / "raw" / "diagnostic-002"
SHEET_DIR = REPO_ROOT / "runs" / "eval-004"
SHEETS = sorted(SHEET_DIR.glob("line-review-doc-*.md"))

DOCUMENT = re.compile(r"^# 줄 단위 판정 — (doc-\d+)")
# 이스케이프한 세로줄은 칸 구분이 아니다
CELL_SPLIT = re.compile(r"(?<!\\)\|")


def rows(text: str):
    document = None
    for line in text.splitlines():
        match = DOCUMENT.match(line)
        if match:
            document = match.group(1)
            continue
        if not line.startswith("| ") or document is None:
            continue
        cells = [c.strip() for c in CELL_SPLIT.split(line)]
        if len(cells) < 5 or not cells[1].isdigit():
            continue
        yield document, int(cells[1]), cells[2], cells[3], cells[4]


class LineReviewSheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SHEETS:
            raise unittest.SkipTest(f"시트가 없습니다: {SHEET_DIR}")
        cls.rows = [r for s in SHEETS for r in rows(s.read_text(encoding="utf-8"))]

    def test_every_quoted_line_matches_the_source(self) -> None:
        """빈 인용도 함께 막는다.

        세로줄을 이스케이프 안 하면 원문의 표 행에서 칸이 밀려 인용 칸이 빈다.
        빈 문자열은 무엇으로도 시작하므로 대조만으로는 통과한다 — 실제로 그
        돌연변이가 안 잡혔다.
        """
        for document, number, shown, _marks, _verdict in self.rows:
            with self.subTest(document=document, line=number):
                source = (SOURCE_DIR / f"{document}.md").read_text(encoding="utf-8")
                actual = source.splitlines()[number - 1].strip()
                quoted = shown.replace("\\|", "|").rstrip("…")

                self.assertTrue(quoted, f"{number}행 인용이 비었습니다 — 칸이 밀렸습니다")
                self.assertGreaterEqual(
                    len(quoted), min(len(actual), 20),
                    f"{number}행 인용이 잘렸습니다: {quoted[:40]}",
                )
                self.assertTrue(
                    actual.startswith(quoted[:40]),
                    f"시트: {quoted[:60]}\n원문: {actual[:60]}",
                )

    def test_the_sheet_is_not_empty(self) -> None:
        """행을 하나도 못 읽으면 위 시험이 조용히 통과한다."""
        self.assertGreaterEqual(len(self.rows), 60)

    def test_lines_that_cannot_carry_a_writing_problem_are_left_out(self) -> None:
        """머리말·빈 줄·표 구분선까지 판정하게 하면 사람이 안 한다."""
        numbers = {(d, n) for d, n, *_ in self.rows}
        source = (SOURCE_DIR / "doc-002.md").read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(source, 1):
            if line.strip() in ("", "---") and ("doc-002", number) in numbers:
                self.fail(f"판정 대상에 빈 줄이나 머리말이 들어갔습니다: {number}행")

    def test_the_builder_reproduces_the_sheet(self) -> None:
        """시트를 손으로 고치면 다음 생성 때 조용히 되돌아간다."""
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            done = subprocess.run(
                [sys.executable, "-X", "utf8", str(BUILDER), "--out-dir", str(out)],
                capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
            )
            self.assertEqual(done.returncode, 0, done.stderr[:400])
            rebuilt = [r for s in sorted(out.glob("line-review-doc-*.md"))
                       for r in rows(s.read_text(encoding="utf-8"))]

        # 판정 칸은 사람이 채우므로 뺀다 — 원문과 지적만 대조한다
        self.assertEqual(
            [(d, n, s, m) for d, n, s, m, _ in rebuilt],
            [(d, n, s, m) for d, n, s, m, _ in self.rows],
        )


if __name__ == "__main__":
    unittest.main()
