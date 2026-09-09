"""일일 점검이 「GitHub 까지 갔나」를 보는지 고정한다.

**왜 있나** — 2026-09-09 까지 이 시스템은 **설치본과 정본이 같은지만** 봤다.
저장소 전체에서 git 상태를 조회하는 곳이 한 군데도 없었다(`git status`·`rev-list`
0건). 그래서 고친 것이 GitHub 까지 가는 길에 끊길 지점 셋 중 하나만 막혀 있었다.

| 끊기는 지점 | 그때 | 지금 |
|---|---|---|
| 설치본만 고침 | 회귀 시험이 잡음 | 그대로 |
| 정본을 고치고 커밋 안 함 | 아무것도 안 봄 | `check_git` |
| 커밋하고 push 안 함 | 아무것도 안 봄 | `check_git` |

**실측이 말한 것** — 최근 커밋 중 `origin/main` 이동 기록이 남은 28건은 전부 지은
날 당일에 올라갔다. 즉 **관측된 사고가 아니라 구조적 구멍**이다. 그래서 이 시험이
지키는 것은 「사고를 막는다」가 아니라 **「보는 눈이 붙어 있다」**이다 — 눈을 떼면
사고가 나도 아무도 모른다.

**침묵 규칙이 여기서도 그대로다** — 판단이 안 서면(git 없음·저장소 아님·원격 없음)
아무 말도 안 한다. 오탐이 섞이면 아무도 안 읽는다.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install  # noqa: E402
import repo_paths  # noqa: E402

CHECK = repo_paths.hook("korean-gate-daily-check.py")


def load_check():
    spec = importlib.util.spec_from_file_location("korean_gate_daily_check", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True, encoding="utf-8")


class GitCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECK.is_file():
            raise unittest.SkipTest(f"점검 훅이 없습니다: {CHECK}")
        cls.check = load_check()

    # ── 무엇을 보는지 ────────────────────────────────────────────────────────

    def test_the_watched_folders_are_the_ones_install_copies(self) -> None:
        """정본 폴더가 넷째로 늘면 훅의 `CANONICAL` 도 같이 늘어야 한다.

        훅에 목록을 베껴 적었으므로, 새 폴더가 생겨도 훅은 조용히 그것만 안 본다.
        여기서 세서 그 조용한 누락을 막는다.
        """
        from_install = {
            src.relative_to(repo_paths.REPO).parts[0]
            for src, _ in install.pairs()
            if repo_paths.REPO in src.parents or src.is_relative_to(repo_paths.REPO)
        }
        self.assertEqual(
            from_install, set(self.check.CANONICAL),
            "`install.py` 가 옮기는 폴더와 훅이 보는 폴더가 어긋납니다 — "
            "`hooks/korean-gate-daily-check.py` 의 CANONICAL 을 맞추십시오",
        )

    # ── 잡아야 하는 것 둘 ────────────────────────────────────────────────────

    def test_it_names_a_canonical_file_left_uncommitted(self) -> None:
        """정본을 고치고 커밋을 안 하면 GitHub 에는 아무것도 안 간다.

        ⚠️ **경로를 글자 그대로 본다.** 「파일 이름이 들어 있나」로만 재면 앞이
        잘린 경로가 통과한다 — 실제로 `hooks/…` 가 `ooks/…` 로 나가던 것을 사람이
        화면에서 보고 찾았다(2026-09-09). 상태 두 글자를 자리로 잘랐는데 앞의
        빈칸이 이미 떼여 한 글자씩 밀린 탓이다.
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fresh_repo(Path(tmp))
            (repo / "assets" / "doc-style-check.py").write_text("고침\n", encoding="utf-8")
            (repo / "hooks" / "doc-style-gate.py").write_text("고침\n", encoding="utf-8")
            found = self.check.check_git(repo)
            self.assertTrue(found, "미커밋 정본을 놓쳤습니다")
            self.assertIn("정본 2개가 커밋 안 됨", found[0])
            self.assertIn("assets/doc-style-check.py", found[0])
            self.assertIn("hooks/doc-style-gate.py", found[0])

    def test_it_counts_commits_that_never_reached_the_remote(self) -> None:
        """커밋했다는 것은 그 단위가 끝났다는 뜻이라 로컬에만 있을 까닭이 없다."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fresh_repo(Path(tmp), with_remote=True)
            (repo / "assets" / "doc-style-check.py").write_text("고침\n", encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-m", "고침", "--no-gpg-sign")
            found = self.check.check_git(repo)
            self.assertTrue(found, "안 밀린 커밋을 놓쳤습니다")
            self.assertTrue(any("안 올라간 커밋 1개" in f for f in found), found)

    def test_a_clean_repo_says_nothing(self) -> None:
        """조용한 날에 화면에 무엇이든 뜨면 그 다음부터 아무도 안 읽는다."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fresh_repo(Path(tmp), with_remote=True)
            self.assertEqual([], self.check.check_git(repo))

    def test_untracked_scratch_files_are_not_a_problem(self) -> None:
        """실험 파일을 놔두는 것은 정상이다 — 그것까지 세면 매일 뜬다."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fresh_repo(Path(tmp), with_remote=True)
            (repo / "assets" / "메모.txt").write_text("실험\n", encoding="utf-8")
            self.assertEqual([], self.check.check_git(repo))

    # ── 판단이 안 설 때는 침묵 ───────────────────────────────────────────────

    def test_it_is_silent_where_there_is_no_repository(self) -> None:
        self.assertIsNone(self.check.check_git(Path(tempfile.gettempdir()) / "없는-것"))

    def test_a_repository_without_a_remote_still_reports_what_it_can_see(self) -> None:
        """원격이 없으면 push 쪽만 판단 불가다 — 미커밋 판정까지 버리지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fresh_repo(Path(tmp))          # 원격 없음
            self.assertEqual([], self.check.check_git(repo))
            (repo / "hooks" / "doc-style-gate.py").write_text("고침\n", encoding="utf-8")
            found = self.check.check_git(repo)
            self.assertTrue(found and "커밋 안 됨" in found[0], found)

    # ── 감시가 죽은 것 ───────────────────────────────────────────────────────

    def test_it_keeps_quiet_on_a_machine_that_never_ran_it(self) -> None:
        """저장소 없이 검사기만 받은 기계를 매일 찌르는 것은 오탐이다."""
        self.assertIsNone(self.check.stale_days({}, datetime(2026, 9, 9)))

    def test_it_speaks_up_once_the_silence_has_lasted(self) -> None:
        """하루치 침묵은 잠깐 못 본 것이고, 사흘치 침묵은 감시가 죽은 것이다."""
        now = datetime(2026, 9, 9)
        self.assertLess(self.check.stale_days({"last_checked_date": "2026-09-08"}, now),
                        self.check.STALE_DAYS)
        self.assertGreaterEqual(
            self.check.stale_days({"last_checked_date": "2026-09-06"}, now),
            self.check.STALE_DAYS)

    def test_the_dead_monitor_message_says_silence_is_not_a_pass(self) -> None:
        text = self.check.render_dead(5, "pytest 가 없다")
        self.assertIn("5일째", text)
        self.assertIn("침묵은 합격이 아니다", text)
        self.assertIn("pytest 가 없다", text)

    # ── 알림 문구 ────────────────────────────────────────────────────────────

    def test_the_message_separates_the_two_kinds_of_sameness(self) -> None:
        """「설치본과 같다」와 「GitHub 과 같다」를 읽는 사람이 헷갈리면 안 고친다."""
        text = self.check.render_git(["정본 1개가 커밋 안 됨 — assets/x.py"], Path("P:/x"))
        self.assertIn("설치본 대조가 통과해도", text)
        self.assertIn("git status", text)

    # ── 붙어 있나 — 조각이 맞아도 `main()` 이 안 부르면 없는 것과 같다 ───────

    def test_the_dead_monitor_notice_actually_reaches_the_screen(self) -> None:
        """`stale_days` 가 맞게 세도 `main()` 이 안 쓰면 아무 말도 안 나온다.

        조각을 따로 재고 통과로 넘긴 탓에, 잇는 줄을 지워도 시험이 초록이던 것을
        돌연변이로 잡았다(2026-09-09).
        """
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            state.write_text('{"last_checked_date": "2026-08-01"}', encoding="utf-8")
            out = self._run_hook(repo=Path(tmp) / "없는-저장소", state=state)
            self.assertIn("일째 못 돌았다", out)
            self.assertIn("침묵은 합격이 아니다", out)

    def test_a_short_silence_still_says_nothing(self) -> None:
        """어제 못 본 것은 사고가 아니다 — 그때도 뜨면 매일 뜨는 것과 같다."""
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            yesterday = datetime.now().date() - timedelta(days=1)
            state.write_text(json.dumps({"last_checked_date": yesterday.isoformat()}),
                             encoding="utf-8")
            self.assertEqual("", self._run_hook(repo=Path(tmp) / "없는-저장소", state=state))

    def test_the_github_notice_actually_reaches_the_screen(self) -> None:
        """`check_git` 이 문제를 찾아도 `main()` 이 안 부르면 화면에 안 뜬다."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fresh_repo(Path(tmp), with_remote=True, runnable=True)
            (repo / "assets" / "doc-style-check.py").write_text("고침\n", encoding="utf-8")
            state = Path(tmp) / "state.json"
            out = self._run_hook(repo=repo, state=state)
            self.assertIn("GitHub 에 안 갔다", out)
            self.assertIn("assets/doc-style-check.py", out)

    def test_the_git_check_runs_even_when_the_suite_cannot(self) -> None:
        """시험을 못 돌리는 기계에서도 GitHub 반영은 봐야 한다.

        처음 붙일 때는 시험이 판단 불가면 `main()` 이 곧장 돌아가서, **그런 기계
        에서는 git 확인이 한 번도 안 돌았다.** CI 가 그 상태였다(pytest 없음).
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fresh_repo(Path(tmp), with_remote=True)   # `tests/` 없음
            (repo / "assets" / "doc-style-check.py").write_text("고침\n", encoding="utf-8")
            out = self._run_hook(repo=repo, state=Path(tmp) / "state.json")
            self.assertIn("GitHub 에 안 갔다", out)

    def test_it_leans_on_nothing_outside_the_standard_library(self) -> None:
        """감시가 바깥 라이브러리를 몰래 요구하면 없는 기계에서 조용히 멈춘다.

        이 꾸러미가 파는 것이 「의존성 0」인데 훅이 `pytest` 를 부르고 있었고,
        어디에도 안 적혀 있어 CI 에조차 없었다(2026-09-09).
        """
        source = CHECK.read_text(encoding="utf-8")
        run_suite = source.split("def run_suite")[1].split("\ndef ")[0]
        self.assertIn('"unittest", "discover"', run_suite)
        for outsider in ("pytest", "nose", "tox"):
            self.assertNotIn(f'"{outsider}"', run_suite,
                             f"훅이 {outsider} 를 요구합니다 — 기본 모듈로 도십시오")

    def test_it_reads_the_stream_unittest_actually_writes_to(self) -> None:
        """`unittest` 는 결과를 stderr 로 낸다 — stdout 만 읽으면 요약이 빈다."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._fresh_repo(Path(tmp), with_remote=True, runnable=True)
            (repo / "tests" / "test_ok.py").write_text(
                "import unittest\n\n\n"
                "class Broken(unittest.TestCase):\n"
                "    def test_broken(self):\n        self.fail('일부러 깨뜨림')\n",
                encoding="utf-8")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "깨뜨림", "--no-gpg-sign")
            git(repo, "push", "-q", "origin", "main")
            out = self._run_hook(repo=repo, state=Path(tmp) / "state.json")
            self.assertIn("회귀 실패", out)
            self.assertIn("FAILED", out, "시험 요약이 비었습니다 — stderr 를 안 읽습니다")

    def _run_hook(self, repo: Path, state: Path) -> str:
        """훅을 그대로 돌려 화면에 나온 글을 낸다 — 아무 말도 없으면 빈 문자열."""
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(CHECK)],
            input="{}", capture_output=True, text=True, encoding="utf-8",
            env={**os.environ,
                 "KOREAN_WRITING_QA_HOME": str(repo),
                 "KOREAN_GATE_CHECK_STATE": str(state),
                 "CLAUDE_BATCH_MODE": "", "CLAUDE_SCHEDULED": ""},
            timeout=240)
        self.assertEqual(0, done.returncode, done.stderr[-400:])
        if not done.stdout.strip():
            return ""
        payload = json.loads(done.stdout)
        return payload["hookSpecificOutput"]["additionalContext"]

    # ── 짓는 법 ──────────────────────────────────────────────────────────────

    def _fresh_repo(self, root: Path, with_remote: bool = False,
                    runnable: bool = False) -> Path:
        """시늉만 낸 저장소. `runnable` 이면 훅이 돌릴 시험도 하나 둔다."""
        repo = root / "저장소"
        for name in self.check.CANONICAL:
            (repo / name).mkdir(parents=True)
            (repo / name / ".keep").write_text("", encoding="utf-8")
        (repo / "assets" / "doc-style-check.py").write_text("원본\n", encoding="utf-8")
        (repo / "hooks" / "doc-style-gate.py").write_text("원본\n", encoding="utf-8")
        (repo / "docs").mkdir()
        (repo / "docs" / "메모.md").write_text("원본\n", encoding="utf-8")
        if runnable:
            # `unittest` 는 맨 함수를 안 찾는다 — TestCase 여야 한다(pytest 와 다름).
            (repo / "tests").mkdir()
            (repo / "tests" / "test_ok.py").write_text(
                "import unittest\n\n\n"
                "class Ok(unittest.TestCase):\n"
                "    def test_ok(self):\n        self.assertTrue(True)\n",
                encoding="utf-8")
        env = {**os.environ, "GIT_CONFIG_GLOBAL": str(root / "gitconfig")}
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=env)
        for key, value in (("user.email", "t@t"), ("user.name", "시험"),
                           ("commit.gpgsign", "false")):
            git(repo, "config", key, value)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "처음", "--no-gpg-sign")
        if with_remote:
            bare = root / "원격.git"
            subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, env=env)
            git(repo, "remote", "add", "origin", str(bare))
            git(repo, "push", "-q", "-u", "origin", "main")
        return repo


if __name__ == "__main__":
    unittest.main()
