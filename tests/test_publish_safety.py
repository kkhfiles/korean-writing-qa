"""공개 안전 검사가 무엇을 막고 무엇을 안 막는지 지킨다.

**왜 이 검사가 생겼나.** 저장소를 공개하기 전에 사람이 전수로 훑었는데, 그 뒤에
들어온 파일은 아무도 안 봤다. 실제로 실행 기록의 측정 스크립트에 작성자 기계의
홈 경로가 박힌 채 올라갔다(2026-09-08). **일회성 점검은 그다음 커밋부터 무력하다.**

**막는 갈래는 오탐이 0이어야 한다.** CI 가 이것으로 발행을 막으므로, 정당한 쓰임이
하나라도 섞이면 사람이 검사를 꺼 버린다. 그래서 `~/.claude`(설치 경로 80군데)와
`P:/github/...`(기본 위치 29군데)는 **막는 갈래에서 뺐다** — `--all` 로 사람이 볼 때만
나온다.

**자리표시자를 가려야 한다.** 문서와 시료가 `C:\\Users\\name` 같은 예시를 쓴다. 그것을
계정 이름으로 잡으면 시료가 자기 검사에 걸린다.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_publish_safety.py"

#: 막아야 하는 것 — 갈래마다 하나씩
#
#   ⚠️ **시료를 이어 붙여서 만든다.** 그대로 적으면 이 시험 파일이 검사에 걸린다.
#      파일을 예외로 빼는 길도 있지만, 그러면 **그 파일에 진짜 열쇠가 들어와도
#      아무도 못 본다** — 예외를 넓게 잡으면 그 안의 미탐은 아무도 다시 안 본다.
MUST_BLOCK = [
    ("홈 경로", 'p = "C:/Users/' + 'somebody/.claude"'),
    ("리눅스 홈", 'p = "/home/' + 'somebody/work"'),
    ("맥 홈", 'p = "/Users/' + 'somebody/work"'),
    ("메일 주소", "문의는 someone" + "@example.co.kr 로"),
    ("OpenAI 열쇠", 'KEY = "sk-' + 'abcdefghijklmnopqrst"'),
    ("깃허브 토큰", 'TOKEN = "ghp_' + 'abcdefghijklmnopqrstuvwxyz01"'),
    ("사내 주소", "대시보드는 https://board" + ".corp 에 있다"),
    ("지라 키", "TEAMMANAGE" + "-417 하위로 넣는다"),
]

#: 통과해야 하는 것 — 문서와 시료가 실제로 쓰는 표기
MUST_PASS = [
    ("자리표시자 name", r'경로는 `C:\Users\name` 형태'),
    ("자리표시자 user", 'p = "/home/user/work"'),
    ("CI 러너", 'p = "/home/runner/.claude"'),
    ("꺾쇠 자리표시자", 'p = "C:/Users/<user>/.claude"'),
    ("환경 변수 표기", 'p = "C:/Users/%USERNAME%/.claude"'),
    ("말줄임표", "Git Bash 라 `/c/Users/...` 형태가 섞여 온다"),
    ("설치 경로", "python ~/.claude/assets/doc-style-check.py"),
    ("기본 위치", 'REPO = "P:/github/korean-writing-qa"'),
    ("공개 저장소 주소", "https://github.com/owner/korean-writing-qa.git"),
]


def run(*args, cwd=REPO):
    return subprocess.run([sys.executable, "-X", "utf8", str(SCRIPT), *args],
                          cwd=cwd, capture_output=True, text=True, encoding="utf-8")


class PublishSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SCRIPT.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {SCRIPT}")

    def test_the_repository_is_clean_right_now(self) -> None:
        """저장소가 지금 통과한다 — 안 그러면 CI 가 처음부터 빨갛다."""
        done = run()
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        self.assertIn("통과", done.stdout)

    def test_it_always_says_what_it_does_not_see(self) -> None:
        """★ 초록을 「개인 정보 없음」으로 읽으면 안 된다 — 사람 이름은 안 본다."""
        for args in ([], ["--all"]):
            with self.subTest(args=args):
                self.assertIn("사람이 읽습니다", run(*args).stdout)

    def test_each_blocked_kind_is_caught(self) -> None:
        for label, text in MUST_BLOCK:
            with self.subTest(case=label):
                self.assertTrue(self._caught(text), f"못 잡았습니다: {text}")

    def test_placeholders_and_documented_paths_pass(self) -> None:
        """시료와 문서가 쓰는 표기다 — 여기서 걸리면 사람이 검사를 끈다."""
        for label, text in MUST_PASS:
            with self.subTest(case=label):
                self.assertFalse(self._caught(text), f"잘못 잡았습니다: {text}")

    def test_the_note_kinds_do_not_fail_the_build(self) -> None:
        """작성자 기계 경로·회사 이름은 정당한 쓰임이 많아 막지 않는다."""
        done = run("--all")
        self.assertEqual(0, done.returncode)
        self.assertIn("막지 않는다", done.stdout)

    def _caught(self, text: str) -> bool:
        """임시 저장소를 만들어 그 한 줄만 넣고 돌린다 — 추적되는 것만 보므로 커밋한다."""
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            for cmd in (["git", "init", "-q"],
                        ["git", "config", "user.email", "t@t"],
                        ["git", "config", "user.name", "t"]):
                subprocess.run(cmd, cwd=work, capture_output=True, check=True)
            (work / "scripts").mkdir()
            (work / "scripts" / "check_publish_safety.py").write_text(
                SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            (work / "sample.md").write_text(text + "\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=work, capture_output=True, check=True)
            subprocess.run(["git", "commit", "-qm", "t"], cwd=work, capture_output=True)
            done = subprocess.run(
                [sys.executable, "-X", "utf8", "scripts/check_publish_safety.py"],
                cwd=work, capture_output=True, text=True, encoding="utf-8")
            return done.returncode == 1


if __name__ == "__main__":
    unittest.main()
