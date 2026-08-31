"""줄 단위 판정 시트가 읽을 수 있고 원문과 어긋나지 않는지 확인한다.

**두 가지가 걸려 있다.**

1. **어긋나면 없는 문장을 판정하게 된다.** 그 판정이 라벨이 되어 회수율의
   분모로 들어가므로, 어긋난 채 지나가면 수치가 조용히 거짓이 된다.
2. **읽을 수 없으면 판정이 안 온다.** 예전 시트는 지적을 `ENGLISH_OVERUSE`
   같은 코드로만 적고 지적 없는 줄과 섞어 놓아, 받은 사람이 「지적이 없는데
   뭘 판정하라는 건지」 알 수 없었다. 그래서 갈래 이름과 표 구성도 고정한다.

표 안에 표를 넣는 줄(`| 도구 | 비고 |`)은 세로줄을 이스케이프해야 칸이 안
밀린다. 이스케이프를 안 하면 시트가 깨지고, 대조도 함께 어긋난다.
"""

from __future__ import annotations

import importlib.util
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
SECTION = re.compile(r"^## (①|②)")
# 이스케이프한 세로줄은 칸 구분이 아니다
CELL_SPLIT = re.compile(r"(?<!\\)\|")
CODE_LOOKING = re.compile(r"^[A-Z][A-Z_0-9-]{3,}$")

FINDING_COLUMNS = 7      # 행 · 갈래 · 구절 · 고칠 말 · 왜 · 누가 · 판정
CLEAN_COLUMNS = 3        # 행 · 원문 · 판정


def load_builder():
    spec = importlib.util.spec_from_file_location("build_line_review_sheet", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unquote(cell: str) -> str:
    return cell.strip().strip("「」").replace("\\|", "|")


def parse(text: str):
    """(문서, 지적 행 목록, 인용 행 목록)을 낸다."""
    document, section, findings, clean = None, None, [], []
    for line in text.splitlines():
        head = DOCUMENT.match(line)
        if head:
            document = head.group(1)
            continue
        mark = SECTION.match(line)
        if mark:
            section = mark.group(1)
            continue
        if not line.startswith("| ") or document is None:
            continue
        cells = [c.strip() for c in CELL_SPLIT.split(line)][1:-1]
        if not cells or not cells[0].isdigit():
            continue
        if section == "①" and len(cells) == FINDING_COLUMNS:
            findings.append(cells)
        elif section == "②" and len(cells) == CLEAN_COLUMNS:
            clean.append(cells)
    return document, findings, clean


def sheets():
    for path in SHEETS:
        yield (path,) + parse(path.read_text(encoding="utf-8"))


class LineReviewSheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SHEETS:
            raise unittest.SkipTest(f"시트가 없습니다: {SHEET_DIR}")
        cls.sheets = list(sheets())

    def source(self, document: str) -> list[str]:
        return (SOURCE_DIR / f"{document}.md").read_text(encoding="utf-8").splitlines()

    def test_both_tables_are_populated(self) -> None:
        """한쪽이 비면 아래 시험들이 조용히 통과한다."""
        total_findings = sum(len(f) for _, _, f, _ in self.sheets)
        total_clean = sum(len(c) for _, _, _, c in self.sheets)

        self.assertGreaterEqual(total_findings, 20, "① 지적 확인 표를 못 읽었습니다")
        self.assertGreaterEqual(total_clean, 30, "② 빠진 것 찾기 표를 못 읽었습니다")

    def test_every_judgeable_line_appears_exactly_once(self) -> None:
        """분모가 참이 되려면 판정 대상 줄이 하나도 빠지면 안 된다.

        두 표에 같은 줄이 함께 들어가도 안 된다 — 사람이 같은 줄을 두 번
        판정하게 되고, 한 번은 「지적 확인」 다른 한 번은 「빠진 것 찾기」라
        답이 서로 다른 뜻이 된다.
        """
        judgeable = load_builder().judgeable
        for path, document, findings, clean in self.sheets:
            with self.subTest(document=document):
                expected = set(judgeable(self.source(document)))
                flagged = {int(r[0]) for r in findings}
                quiet = {int(r[0]) for r in clean}

                self.assertEqual(flagged & quiet, set(), "같은 줄이 두 표에 다 있습니다")
                self.assertEqual(flagged | quiet, expected,
                                 f"빠지거나 더 붙은 줄이 있습니다: {path.name}")

    def test_every_quoted_line_matches_the_source_exactly(self) -> None:
        """② 는 자르지 않는다 — 잘린 줄은 판정할 수 없다."""
        for _path, document, _findings, clean in self.sheets:
            lines = self.source(document)
            for number, shown, _verdict in clean:
                with self.subTest(document=document, line=number):
                    quoted = unquote(shown)

                    self.assertTrue(quoted, f"{number}행 인용이 비었습니다 — 칸이 밀렸습니다")
                    self.assertNotIn("…", quoted, f"{number}행 인용이 잘렸습니다")
                    self.assertEqual(quoted, lines[int(number) - 1].strip())

    def test_every_flagged_phrase_is_in_its_line(self) -> None:
        """엉뚱한 줄에 붙은 지적을 판정하면 그 판정이 그대로 라벨이 된다."""
        for _path, document, findings, _clean in self.sheets:
            lines = self.source(document)
            for row in findings:
                number, phrase = int(row[0]), unquote(row[2])
                if phrase == "—":
                    continue
                with self.subTest(document=document, line=number):
                    self.assertIn(phrase, lines[number - 1])

    def test_the_category_is_written_in_korean(self) -> None:
        """코드를 그대로 두면 받은 사람이 해독부터 해야 한다."""
        for _path, document, findings, _clean in self.sheets:
            for row in findings:
                with self.subTest(document=document, line=row[0]):
                    self.assertFalse(CODE_LOOKING.match(row[1]),
                                     f"갈래가 코드로 남았습니다: {row[1]}")

    def test_the_same_finding_is_not_listed_twice(self) -> None:
        """층마다 부르는 이름이 달라 같은 지적이 두 줄로 남은 적이 있다."""
        for _path, document, findings, _clean in self.sheets:
            seen = [(r[0], r[1], unquote(r[2])) for r in findings]
            with self.subTest(document=document):
                self.assertEqual(len(seen), len(set(seen)), f"겹치는 지적: {document}")

    def test_the_verdict_column_is_left_empty(self) -> None:
        """사람이 채울 칸이다 — 미리 채워 두면 판정이 아니라 확인이 된다."""
        for _path, document, findings, clean in self.sheets:
            with self.subTest(document=document):
                self.assertEqual({r[-1] for r in findings} | {r[-1] for r in clean}, {""})

    def test_lines_that_cannot_carry_a_writing_problem_are_left_out(self) -> None:
        """머리말·빈 줄·표 구분선까지 판정하게 하면 사람이 안 한다."""
        for _path, document, findings, clean in self.sheets:
            numbers = {int(r[0]) for r in findings} | {int(r[0]) for r in clean}
            for number, line in enumerate(self.source(document), 1):
                if line.strip() in ("", "---"):
                    with self.subTest(document=document, line=number):
                        self.assertNotIn(number, numbers)

    def test_the_builder_reproduces_the_sheet(self) -> None:
        """시트를 손으로 고치면 다음 생성 때 조용히 되돌아간다."""
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            done = subprocess.run(
                [sys.executable, "-X", "utf8", str(BUILDER), "--out-dir", str(out)],
                capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
            )
            self.assertEqual(done.returncode, 0, done.stderr[:400])
            rebuilt = [parse(p.read_text(encoding="utf-8"))
                       for p in sorted(out.glob("line-review-doc-*.md"))]

        self.assertEqual(rebuilt, [(d, f, c) for _p, d, f, c in self.sheets])


if __name__ == "__main__":
    unittest.main()
