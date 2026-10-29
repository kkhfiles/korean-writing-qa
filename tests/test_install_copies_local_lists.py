"""설치가 검사기가 읽는 `local-` 목록을 빠짐없이 옮기는지 본다.

**왜 있나** — 검사기는 개인 목록을 `~/.claude/data/catalog/` 에서 먼저 찾고, README 는 저장소
`data/catalog/` 에 두라고 안내한다. 둘을 잇는 것이 `install.py` 인데 개인 낱말 목록을 안 옮겨서,
다른 프로젝트에서 도는 설치본 검사기는 개인 목록을 못 봤다(2026-10-29 재현 · 저장소 검사기
주의 1, 설치본 0). 검사기에 목록을 새로 더할 때 설치가 빠지지 않도록 이름을 검사기 원문에서 읽는다.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install  # noqa: E402
import repo_paths  # noqa: E402


def checker_local_lists() -> list[str]:
    """검사기가 `local-` 이름으로 읽는 목록 파일 이름."""
    text = repo_paths.CHECKER.read_text(encoding="utf-8")
    return sorted(set(re.findall(r"^\w+_FILE = '(local-[^']+)'", text, re.M)))


class InstallCopiesLocalListsTests(unittest.TestCase):
    def test_checker_names_are_found(self) -> None:
        names = checker_local_lists()
        self.assertIn("local-personal-words.tsv", names)
        self.assertIn("local-brand-names.txt", names)

    def test_every_local_list_is_installed(self) -> None:
        names = checker_local_lists()
        with tempfile.TemporaryDirectory() as d:
            catalog = Path(d) / "data" / "catalog"
            catalog.mkdir(parents=True)
            for name in names:
                (catalog / name).write_text("# 시험\n", encoding="utf-8")
            with mock.patch.object(repo_paths, "REPO", Path(d)):
                sources = {src.name for src, _ in install.pairs() if src.parent == catalog}
        missing = [n for n in names if n not in sources]
        self.assertEqual([], missing, "검사기가 읽는데 install.py 가 안 옮기는 목록")


if __name__ == "__main__":
    unittest.main()
