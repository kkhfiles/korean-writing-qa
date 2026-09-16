"""코드펜스 안은 안 보고, 밖은 본다.

**발단** — 2026-09-16 DevRel 제안서 세션에서 README 양식이 안에 세 겹 블록을 담게
되어 바깥을 **네 겹 백틱**으로 열었다(CommonMark·GitHub 정상). 그러자 양식 안의
`> [!NOTE]` 가 문서 본문으로 잡혀 「해설을 인용 부호로 씀」 주의가 났다.

**원인은 그 세션의 추정과 달랐다** — 「펜스 정규식이 백틱 세 개 고정」이라 적혀
있었는데, 재현해 보니 **세 겹에서도 났다.** 진짜 원인은 「출처 없는 인용 블록」
검사가 원문을 그대로 훑어 **펜스를 아예 안 본 것**이다. 네 겹 문제는 그와 별개로
`md_body` 에 있었다(안쪽 세 겹이 바깥 네 겹을 닫아 버림).

**둘 다 시험한다** — 안을 안 보는 것만 재면 「전부 안 봄」이 만점이 된다.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HEAD = "---\nform: structured\n---\n\n# 펜스 시험\n\n- **항목** — 값\n\n"
TAIL = "\n- **끝** — 값\n"


def check(text: str) -> str:
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "doc.md"
        target.write_text(text, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(target)],
            capture_output=True, text=True, encoding="utf-8")
        return done.stdout or ""


def fenced_lines(lines: list[str]):
    spec = importlib.util.spec_from_file_location("dsc", repo_paths.CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.fenced_lines(lines)


QUOTE_IN_CODE = ("> [!NOTE]\n"
                 "> 코드 블록 안이라 이것은 검사 대상이 아니다.\n")


class CodeFenceNestingTests(unittest.TestCase):
    def test_three_backtick_fence_hides_its_content(self) -> None:
        out = check(HEAD + "```markdown\n" + QUOTE_IN_CODE + "```\n" + TAIL)
        self.assertNotIn("해설을 인용 부호로 씀", out)

    def test_four_backtick_fence_survives_an_inner_three(self) -> None:
        """안쪽 세 겹이 바깥 네 겹을 닫으면 그 뒤가 통째로 새어 나온다."""
        body = ("````markdown\n" + QUOTE_IN_CODE
                + "```\n코드\n```\n"
                + "> 이 줄도 아직 코드 블록 안이라 검사 대상이 아니다.\n"
                + "````\n")
        out = check(HEAD + body + TAIL)
        self.assertNotIn("해설을 인용 부호로 씀", out)

    def test_tilde_fence_also_hides_its_content(self) -> None:
        out = check(HEAD + "~~~markdown\n" + QUOTE_IN_CODE + "~~~\n" + TAIL)
        self.assertNotIn("해설을 인용 부호로 씀", out)

    def test_a_real_quote_block_is_still_caught(self) -> None:
        """⛔ 펜스를 빼느라 **밖의 지적까지 사라지면** 고친 것이 아니다."""
        out = check(HEAD + "> 출처가 없으니 이것은 해설이고 값과 같은 규칙을 받는다.\n" + TAIL)
        self.assertIn("해설을 인용 부호로 씀", out)

    def test_a_tilde_does_not_close_a_backtick_fence(self) -> None:
        lines = ["```", "안", "~~~", "밖에서 닫히면 안 된다", "```", "여기는 밖"]
        inside = fenced_lines(lines)
        self.assertEqual({0, 1, 2, 3, 4}, inside)

    def test_a_shorter_run_does_not_close_a_longer_one(self) -> None:
        lines = ["````", "안", "```", "아직 안", "````", "밖"]
        self.assertEqual({0, 1, 2, 3, 4}, fenced_lines(lines))

    def test_a_longer_run_closes_a_shorter_one(self) -> None:
        """CommonMark — 닫는 표시는 여는 것 **이상**이면 된다."""
        lines = ["```", "안", "`````", "밖"]
        self.assertEqual({0, 1, 2}, fenced_lines(lines))


if __name__ == "__main__":
    unittest.main()
