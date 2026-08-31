"""줄 단위 판정 시트가 읽을 수 있고 원문과 어긋나지 않는지 확인한다.

**세 가지가 걸려 있다.**

1. **어긋나면 없는 문장을 판정하게 된다.** 그 판정이 라벨이 되어 회수율의
   분모로 들어가므로, 어긋난 채 지나가면 수치가 조용히 거짓이 된다.
2. **읽을 수 없으면 판정이 안 온다.** 예전 시트는 지적을 `ENGLISH_OVERUSE`
   같은 코드로만 적고 지적 없는 줄과 섞어 놓아, 받은 사람이 「지적이 없는데
   뭘 판정하라는 건지」 알 수 없었다.
3. **채운 시트를 덮어쓰면 판정이 사라진다.** 실제로 한 번 날렸다.

**시험이 두 갈래인 이유** — 저장된 시트는 사람이 채운 **기록**이고, 갓 만든
시트는 **빈 양식**이다. 판정 칸이 비어야 한다는 것은 양식에만 해당한다.
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

DOCUMENT = re.compile(r"^# 줄 단위 판정 — (doc-\d+)")
SECTION = re.compile(r"^## (①|②|③)")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
CODE_LOOKING = re.compile(r"^[A-Z][A-Z_0-9-]{3,}$")

FINDING_COLUMNS = 7      # 행 · 갈래 · 구절 · 고칠 말 · 왜 · 누가 · 판정
CLEAN_COLUMNS = 3        # 행 · 원문 · 판정
ALLOWED_COLUMNS = 4      # 행 · 갈래 · 구절 · 판정


def load_builder():
    spec = importlib.util.spec_from_file_location("build_line_review_sheet", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unquote(cell: str) -> str:
    return cell.strip().strip("「」").replace("\\|", "|")


def parse(text: str) -> dict:
    """섹션별 표를 갈라 낸다."""
    document, section = None, None
    out = {"document": None, "①": [], "②": [], "③": []}
    widths = {"①": FINDING_COLUMNS, "②": CLEAN_COLUMNS, "③": ALLOWED_COLUMNS}
    for line in text.splitlines():
        head = DOCUMENT.match(line)
        if head:
            document = out["document"] = head.group(1)
            continue
        mark = SECTION.match(line)
        if mark:
            section = mark.group(1)
            continue
        if not line.startswith("| ") or document is None or section is None:
            continue
        cells = [c.strip() for c in CELL_SPLIT.split(line)][1:-1]
        if cells and cells[0].isdigit() and len(cells) == widths[section]:
            out[section].append(cells)
    return out


def source_lines(document: str) -> list[str]:
    return (SOURCE_DIR / f"{document}.md").read_text(encoding="utf-8").splitlines()


class SheetShapeChecks:
    """저장된 시트와 갓 만든 시트에 똑같이 걸리는 것들."""

    def sheets(self) -> list[dict]:
        raise NotImplementedError

    def test_the_tables_are_populated(self) -> None:
        """한쪽이 비면 아래 시험들이 조용히 통과한다."""
        found = sum(len(s["①"]) for s in self.sheets())
        quiet = sum(len(s["②"]) for s in self.sheets())

        self.assertGreaterEqual(found, 20, "① 지적 확인 표를 못 읽었습니다")
        self.assertGreaterEqual(quiet, 30, "② 빠진 것 찾기 표를 못 읽었습니다")

    def test_every_judgeable_line_appears_exactly_once(self) -> None:
        """분모가 참이 되려면 판정 대상 줄이 하나도 빠지면 안 된다.

        두 표에 같은 줄이 함께 들어가도 안 된다 — 사람이 같은 줄을 두 번
        판정하게 되고, 한 번은 「지적 확인」 다른 한 번은 「빠진 것 찾기」라
        답이 서로 다른 뜻이 된다.
        """
        judgeable = load_builder().judgeable
        for sheet in self.sheets():
            document = sheet["document"]
            with self.subTest(document=document):
                expected = set(judgeable(source_lines(document)))
                flagged = {int(r[0]) for r in sheet["①"]} | {int(r[0]) for r in sheet["③"]}
                quiet = {int(r[0]) for r in sheet["②"]}

                self.assertEqual(flagged & quiet, set(), "같은 줄이 두 표에 다 있습니다")
                self.assertEqual(flagged | quiet, expected, "빠지거나 더 붙은 줄이 있습니다")

    def test_every_quoted_line_matches_the_source_exactly(self) -> None:
        """② 는 자르지 않는다 — 잘린 줄은 판정할 수 없다."""
        for sheet in self.sheets():
            lines = source_lines(sheet["document"])
            for number, shown, _verdict in sheet["②"]:
                with self.subTest(document=sheet["document"], line=number):
                    quoted = unquote(shown)

                    self.assertTrue(quoted, f"{number}행 인용이 비었습니다 — 칸이 밀렸습니다")
                    self.assertNotIn("…", quoted, f"{number}행 인용이 잘렸습니다")
                    self.assertEqual(quoted, lines[int(number) - 1].strip())

    def test_every_flagged_phrase_is_in_its_line(self) -> None:
        """엉뚱한 줄에 붙은 지적을 판정하면 그 판정이 그대로 라벨이 된다."""
        for sheet in self.sheets():
            lines = source_lines(sheet["document"])
            for row in sheet["①"] + sheet["③"]:
                number, phrase = int(row[0]), unquote(row[2])
                if phrase == "—":
                    continue
                with self.subTest(document=sheet["document"], line=number):
                    self.assertIn(phrase, lines[number - 1])

    def test_the_category_is_written_in_korean(self) -> None:
        """코드를 그대로 두면 받은 사람이 해독부터 해야 한다."""
        for sheet in self.sheets():
            for row in sheet["①"] + sheet["③"]:
                with self.subTest(document=sheet["document"], line=row[0]):
                    self.assertFalse(CODE_LOOKING.match(row[1]),
                                     f"갈래가 코드로 남았습니다: {row[1]}")

    def test_the_same_finding_is_not_listed_twice(self) -> None:
        """층마다 부르는 이름이 달라 같은 지적이 두 줄로 남은 적이 있다."""
        for sheet in self.sheets():
            seen = [(r[0], r[1], unquote(r[2])) for r in sheet["①"]]
            with self.subTest(document=sheet["document"]):
                self.assertEqual(len(seen), len(set(seen)), "겹치는 지적이 있습니다")

    def test_settled_findings_are_kept_out_of_the_first_table(self) -> None:
        """섞으면 빈 칸이 정반대 두 뜻을 갖는다 — 회수율이 한 건을 반대로 셌다."""
        for sheet in self.sheets():
            with self.subTest(document=sheet["document"]):
                self.assertNotIn("사람이 괜찮다 함", {r[5] for r in sheet["①"]})


class AnsweredSheetTests(SheetShapeChecks, unittest.TestCase):
    """사람이 채워 저장한 시트 — 판정이 들어 있는 것이 정상이다."""

    @classmethod
    def setUpClass(cls) -> None:
        paths = sorted(SHEET_DIR.glob("line-review-doc-*.md"))
        if not paths:
            raise unittest.SkipTest(f"시트가 없습니다: {SHEET_DIR}")
        cls.parsed = [parse(p.read_text(encoding="utf-8")) for p in paths]

    def sheets(self) -> list[dict]:
        return self.parsed

    def test_lines_that_cannot_carry_a_writing_problem_are_left_out(self) -> None:
        """머리말·빈 줄·표 구분선까지 판정하게 하면 사람이 안 한다."""
        for sheet in self.sheets():
            numbers = {int(r[0]) for group in ("①", "②", "③") for r in sheet[group]}
            for number, line in enumerate(source_lines(sheet["document"]), 1):
                if line.strip() in ("", "---"):
                    with self.subTest(document=sheet["document"], line=number):
                        self.assertNotIn(number, numbers)


class FreshSheetTests(SheetShapeChecks, unittest.TestCase):
    """갓 만든 빈 양식 — 판정 칸이 비어 있어야 한다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.TemporaryDirectory()
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(BUILDER), "--out-dir", cls.directory.name],
            capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
        )
        if done.returncode != 0:
            raise AssertionError(done.stderr[:600])
        cls.parsed = [parse(p.read_text(encoding="utf-8"))
                      for p in sorted(Path(cls.directory.name).glob("line-review-doc-*.md"))]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.directory.cleanup()

    def sheets(self) -> list[dict]:
        return self.parsed

    def test_the_verdict_column_starts_empty(self) -> None:
        """미리 채워 두면 판정이 아니라 확인이 된다."""
        for sheet in self.sheets():
            verdicts = {r[-1] for group in ("①", "②", "③") for r in sheet[group]}
            with self.subTest(document=sheet["document"]):
                self.assertEqual(verdicts, {""})


class OverwriteGuardTests(unittest.TestCase):
    """채운 시트를 덮어쓰지 않는지 — 한 번 날린 뒤에 붙인 안전장치다."""

    def build(self, directory: Path, force: bool = False) -> str:
        command = [sys.executable, "-X", "utf8", str(BUILDER), "--out-dir", str(directory)]
        done = subprocess.run(command + (["--force"] if force else []),
                              capture_output=True, text=True, encoding="utf-8",
                              cwd=str(REPO_ROOT))
        self.assertEqual(done.returncode, 0, done.stderr[:400])
        return done.stdout

    def test_a_filled_sheet_is_not_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.build(out)
            sheet = out / "line-review-doc-002.md"
            filled = sheet.read_text(encoding="utf-8").replace(
                "| 「자율 수행」 | 제품 이름이 아니라 일반 설명 | 2층 읽기 | |",
                "| 「자율 수행」 | 제품 이름이 아니라 일반 설명 | 2층 읽기 | 고치면 안됨 |")
            self.assertNotEqual(filled, sheet.read_text(encoding="utf-8"), "시료를 못 채웠습니다")
            sheet.write_text(filled, encoding="utf-8")

            self.build(out)

            self.assertIn("고치면 안됨", sheet.read_text(encoding="utf-8"))

    def test_force_rebuilds_it(self) -> None:
        """건너뛰기가 영영 못 고치는 상태가 되면 안 된다."""
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            self.build(out)
            sheet = out / "line-review-doc-002.md"
            sheet.write_text(sheet.read_text(encoding="utf-8").replace(
                "| 「자율 수행」 | 제품 이름이 아니라 일반 설명 | 2층 읽기 | |",
                "| 「자율 수행」 | 제품 이름이 아니라 일반 설명 | 2층 읽기 | 고치면 안됨 |"),
                encoding="utf-8")

            self.build(out, force=True)

            self.assertNotIn("고치면 안됨", sheet.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
