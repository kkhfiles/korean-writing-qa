"""README 의 「나와야 하는 값」이 실제 값과 같은지 본다.

**왜 이 시험이 필요한가.** 2026-09-16 에 그 표가 조용히 낡아 있는 것을 발견했다.
`오류 10 · 주의 5` 로 적혀 있었는데 실제는 `오류 11 · 주의 6` 이었고, 건너뛰기도
`14건` 이라 적혀 있었는데 실제는 2건이었다. 언제부터인지 아무도 모른다 —
**그 숫자를 지키는 장치가 없었다.**

이 표는 저장소를 처음 받은 사람이 「설치가 됐나」를 가르는 유일한 기준이다.
값이 틀리면 **제대로 설치한 사람이 깨진 줄 안다.** 반대로 검사기를 고쳐 값이
바뀌었는데 표를 안 고치면 그 뒤로는 아무도 이 표를 믿지 않는다.

**표에서 값을 읽어 온다** — 시험에 숫자를 따로 적으면 고칠 곳이 두 곳이 되고,
두 곳이 되면 한쪽이 낡는다(이 저장소가 이미 겪은 실패).
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

README = repo_paths.REPO / "README.md"
FIXTURES = repo_paths.REPO / "tests" / "fixtures" / "paired"

#: README 표의 한 줄 — 「| `<이름>.md` 검사 | `오류 N · 주의 M` |」
ROW = re.compile(r"\|\s*`([\w-]+\.md)`\s*검사\s*\|\s*`오류\s*(\d+)\s*·\s*주의\s*(\d+)`\s*\|")
#: 「| `install.py --check` | `같음 N · 다름 0 · 없음 0` |」
INSTALL_ROW = re.compile(r"`install\.py --check`\s*\|\s*`같음\s*(\d+)\s*·")
TOTAL = re.compile(r"합계\s*—\s*오류\s*(\d+)\s*·\s*주의\s*(\d+)")


def run_checker(path: Path) -> tuple[int, int]:
    done = subprocess.run(
        [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(path)],
        capture_output=True, text=True, encoding="utf-8")
    m = TOTAL.search(done.stdout or "")
    if not m:                      # 위반이 하나도 없으면 합계 줄 대신 ✅ 만 나온다
        return (0, 0)
    return int(m.group(1)), int(m.group(2))


class ReadmeExpectedValueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")

    def test_the_table_is_still_there(self) -> None:
        """표가 사라지면 아래 시험이 조용히 0건을 돌게 된다 — 통과로 읽히면 안 된다."""
        self.assertEqual(2, len(ROW.findall(self.text)),
                         "README 의 시료 검사 줄 둘을 못 찾았다")

    def test_fixture_counts_match(self) -> None:
        for name, want_err, want_warn in ROW.findall(self.text):
            with self.subTest(name):
                got = run_checker(FIXTURES / name)
                self.assertEqual((int(want_err), int(want_warn)), got,
                                 f"{name} — README 와 실제가 다르다")

    def test_install_check_count_matches(self) -> None:
        m = INSTALL_ROW.search(self.text)
        self.assertIsNotNone(m, "README 의 `install.py --check` 줄을 못 찾았다")
        import install  # noqa: PLC0415 — 저장소 루트를 sys.path 에 넣은 뒤라야 한다
        same = sum(1 for src, dst in install.pairs()
                   if dst.exists() and install.digest(src) == install.digest(dst))
        missing = sum(1 for _src, dst in install.pairs() if not dst.exists())
        if missing:
            self.skipTest("설치 안 한 기계 — 남이 저장소만 받아 돌리는 것이 정상이다")
        self.assertEqual(int(m.group(1)), same)


if __name__ == "__main__":
    unittest.main()
