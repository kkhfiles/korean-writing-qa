"""설치본이 정본과 어긋나면 깨진다.

**왜 이 시험이 필요한가.** 2026-09-07 이전에는 정본이 `~/.claude/` 에 있었고 이
저장소는 그것을 불러다 썼다. 사본을 안 두는 대신 저장소만 받은 사람은 아무것도
못 돌렸다. 이제 정본이 저장소 안에 있고 `~/.claude/` 가 설치본이다.

방향을 뒤집으면 예전에 없던 실패가 하나 생긴다 — **설치본만 고치는 것**이다.
`~/.claude/assets/doc-style-check.py` 를 직접 편집하면 저장소는 그대로이고,
다음 `install.py` 가 그 편집을 조용히 지운다. 이 시험이 그것을 먼저 잡는다.

**설치 안 한 기계에서는 건너뛴다** — 남이 저장소만 받아 시험을 돌리는 것이
정상이므로, 설치본이 없다고 실패로 내지 않는다. 다만 **일부만 설치된 상태는
실패**다. 그건 설치가 도중에 멈춘 것이지 안 한 것이 아니다.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install  # noqa: E402
import repo_paths  # noqa: E402


class InstalledCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pairs = install.pairs()
        cls.present = [(s, d) for s, d in cls.pairs if d.exists()]

    def test_canonical_files_are_all_in_the_repo(self) -> None:
        """정본이 저장소 안에 있다 — 없으면 받은 사람이 못 돌린다."""
        for src, _ in self.pairs:
            with self.subTest(file=src.name):
                self.assertTrue(src.is_file(), f"정본이 없습니다: {src}")
                self.assertTrue(
                    str(src).startswith(str(repo_paths.REPO)),
                    f"정본이 저장소 밖을 가리킵니다: {src}",
                )

    def test_partial_install_is_a_failure(self) -> None:
        """설치를 하다 만 상태는 안 한 상태와 다르다."""
        if not self.present:
            self.skipTest("설치본이 없습니다 — 저장소만 받은 기계입니다")
        missing = [d for _, d in self.pairs if not d.exists()]
        self.assertEqual([], missing, f"설치가 도중에 멈췄습니다: {missing[:3]}")

    def test_installed_copy_is_identical(self) -> None:
        """설치본을 직접 고쳤으면 여기서 걸린다."""
        if not self.present:
            self.skipTest("설치본이 없습니다 — 저장소만 받은 기계입니다")
        for src, dst in self.present:
            with self.subTest(file=dst.name):
                self.assertEqual(
                    install.digest(src),
                    install.digest(dst),
                    f"설치본이 정본과 다릅니다: {dst}\n"
                    f"설치본을 직접 고쳤으면 그 변경을 {src} 로 옮긴 뒤 install.py 를 다시 돌립니다.",
                )

    def test_check_mode_agrees(self) -> None:
        """`install.py --check` 의 판정이 이 시험과 같아야 한다."""
        if not self.present:
            self.skipTest("설치본이 없습니다 — 저장소만 받은 기계입니다")
        self.assertEqual(0, install.do_check())


if __name__ == "__main__":
    unittest.main()
