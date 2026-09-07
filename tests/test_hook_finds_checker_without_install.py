"""설치본이 없는 기계에서도 훅이 검사기를 찾는지 지킨다.

**어떻게 놓쳤나.** 정본을 저장소로 옮긴 뒤 「클론만 한 기계」를 흉내 내면서
`CLAUDE_HOME` 만 빈 디렉터리로 돌리고 초록을 확인했다. 훅은 그 변수를 안 보고
`$HOME/.claude` 를 직접 찾는다 — 그래서 흉내 내는 동안에도 작성자 기계의 진짜
설치본을 계속 쓰고 있었다. CI 가 실제로 빈 기계에서 돌려 시험 18건을 깨뜨렸다.

**규칙** — 재현 시험은 증상이 났던 그 모양으로 짠다. 여기서는 `HOME` 자체를
빈 디렉터리로 돌린다. 안 나는 모양으로 재고 「안 난다」고 적으면 맞는 진단을 지운다.

훅이 찾는 순서는 셋이다 — 환경 변수 · 설치본 · 훅 파일의 형제(`../assets/`).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HOOK = repo_paths.hook("doc-style-gate.py")

PROBE = (
    "import runpy, sys, json;"
    "mod = runpy.run_path(sys.argv[1]);"
    "print(json.dumps({'checker': str(mod['CHECKER']), 'skill': str(mod['KOREAN_CHECKER'])}))"
)


class HookResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HOOK.is_file():
            raise unittest.SkipTest(f"훅이 없습니다: {HOOK}")

    def resolve(self, **overrides) -> dict:
        """훅을 불러와 어느 경로를 골랐는지 본다."""
        env = dict(os.environ)
        env.pop("KOREAN_QA_CHECKER", None)
        env.pop("KOREAN_QA_SKILL_CHECK", None)
        env.update(overrides)
        done = subprocess.run(
            [sys.executable, "-X", "utf8", "-c", PROBE, str(HOOK)],
            capture_output=True, text=True, encoding="utf-8", env=env,
            stdin=subprocess.DEVNULL,
        )
        self.assertEqual(0, done.returncode, done.stderr)
        import json
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_falls_back_to_the_repo_when_nothing_is_installed(self) -> None:
        """설치본이 없으면 저장소 안의 정본을 쓴다 — CI 를 깨뜨렸던 그 상황이다."""
        with tempfile.TemporaryDirectory() as empty:
            got = self.resolve(HOME=empty, USERPROFILE=empty)
        for key in ("checker", "skill"):
            with self.subTest(what=key):
                self.assertTrue(Path(got[key]).is_file(), f"못 찾았습니다: {got[key]}")
                self.assertTrue(
                    str(Path(got[key])).startswith(str(repo_paths.REPO)),
                    f"저장소 밖을 가리킵니다: {got[key]}",
                )

    def test_environment_variable_wins(self) -> None:
        """다른 곳에 둔 사람이 지정할 수 있어야 한다."""
        with tempfile.TemporaryDirectory() as empty:
            elsewhere = Path(empty) / "somewhere-else.py"
            elsewhere.write_text("# 표본", encoding="utf-8")
            got = self.resolve(HOME=empty, USERPROFILE=empty,
                               KOREAN_QA_CHECKER=str(elsewhere))
        self.assertEqual(str(elsewhere), got["checker"])

    def test_installed_copy_is_preferred_when_present(self) -> None:
        """설치된 Claude Code 안에서는 설치본이 먼저다 — 그 기계의 판이 도는 판이다."""
        installed = repo_paths.installed("assets", "doc-style-check.py")
        if not installed.is_file():
            self.skipTest("설치본이 없습니다 — 저장소만 받은 기계입니다")
        got = self.resolve()
        self.assertEqual(str(installed), got["checker"])


if __name__ == "__main__":
    unittest.main()
