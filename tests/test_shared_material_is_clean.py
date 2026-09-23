"""CI 의 「공유 자료는 오류 0」 단계를 로컬 시험에서도 돌린다.

**왜 있나** — 그 단계는 워크플로 파일에만 있어서 로컬 시험은 초록인데 푸시하면
빨개졌다(2026-09-23). 검사기 구멍(꼬리 괄호 뒤 마침표)을 막자 사례집에 숨어 있던
반말 한 문장이 새로 걸렸는데, 영향을 잴 때 사례집을 빠뜨렸고 로컬 시험도 그 파일을
안 봤다.

**대상은 워크플로에서 읽는다** — 여기에 목록을 베껴 적으면 한쪽만 늘어난다.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

WORKFLOW = repo_paths.REPO / ".github" / "workflows" / "tests.yml"
STEP = "공유 자료는 오류 0"


def shared_files() -> list[str]:
    """워크플로의 그 단계 `run:` 에 적힌 문서 경로."""
    text = WORKFLOW.read_text(encoding="utf-8")
    start = text.index(f"name: {STEP}")
    nxt = text.find("\n      - name:", start + 1)
    step = text[start:nxt if nxt > 0 else len(text)]
    return re.findall(r"[\w./-]+\.(?:md|html)\b", step)


class SharedMaterialTests(unittest.TestCase):
    def test_the_step_names_its_files(self) -> None:
        """단계를 못 읽으면 아래 시험이 빈 목록으로 초록이 된다 — 그걸 막는다."""
        files = shared_files()
        self.assertIn("docs/showcase.html", files)
        self.assertIn("README.md", files)

    def test_shared_material_has_no_errors(self) -> None:
        files = shared_files()
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), *files, "--no-rules"],
            cwd=str(repo_paths.REPO), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=240)
        found = re.search(r"합계 — 오류 (\d+)", done.stdout)
        self.assertIsNotNone(found, done.stdout[-400:] + done.stderr[-400:])
        errors = [l for l in done.stdout.splitlines() if "❌" in l]
        self.assertEqual("0", found.group(1),
                         "공유 자료에 오류가 있습니다 — CI 에서 빨개집니다\n" + "\n".join(errors[:8]))


if __name__ == "__main__":
    unittest.main()
