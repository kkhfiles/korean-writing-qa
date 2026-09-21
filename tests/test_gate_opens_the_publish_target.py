"""발행 대상의 **경로를 끝까지 푸는지** 본다 — 못 열면 게이트가 통째로 조용하다.

**왜 있나.** 게이트는 검사·막기·안내·기록을 모두 `os.path.exists(fp)` 뒤에 둔다.
그래서 경로를 못 풀면 **위반이 있어도 아무 말 없이 지나간다.** 발행 명령은 거의
늘 `cd <빌드 폴더> && <도구> <상대 경로>` 이거나 `SP="..." <도구> $SP/문서.md`
꼴인데, 훅은 세션 작업 디렉터리에서 도므로 그 상대 경로가 훅 쪽에서 안 열렸다.

실측 2026-09-21 — 스물한 날치 발행 대상 35개 중 **32개가 안 열렸다.** 마침 전부
작업 폴더 파일이라 결과는 맞았지만, 건너뛸 것이라 건너뛴 것이 아니라 **못 찾아서
건너뛴 것**이다. 건너뛸지 가르는 `SKIP` 도 상대 경로에는 안 걸린다 —
`scratchpad/데모.md` 가 `데모.md` 로 뽑히면 작업 문서가 검사 대상으로 올라온다.
"""
import importlib.util
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HOOK = repo_paths.hook("doc-style-gate.py")


def load():
    spec = importlib.util.spec_from_file_location("doc_style_gate", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def publish(cmd):
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": cmd}}


MARP = 'node "/c/npm/@marp-team/marp-cli/marp-cli.js" --no-stdin '

# ⛔ 훅은 `Temp`·`scratchpad` 를 건너뛴다. 임시 폴더에서 재면 대상이 0으로
#    나오고 그것을 「못 푼다」로 읽게 된다 — 증상이 안 나는 자리에서 재는 것이다.
WORK = Path("P:/d/gate-target-test")


def fresh_dir():
    d = WORK / uuid.uuid4().hex[:10]
    d.mkdir(parents=True, exist_ok=True)
    return d


class ResolveTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mod = load()
        cls.dir = fresh_dir()
        (cls.dir / "deck.md").write_text("# 제목\n", encoding="utf-8")

    def targets(self, cmd):
        return self.mod.targets(publish(cmd))[0]

    def test_a_relative_path_resolves_against_the_cd_in_the_command(self):
        """훅은 세션 폴더에서 돈다 — 기준은 명령이 옮겨 간 곳이다."""
        cmd = f'cd "{self.dir.as_posix()}" && {MARP} deck.md'

        got = self.targets(cmd)

        self.assertEqual([p.replace(chr(92), "/") for p in got],
                         [(self.dir / "deck.md").as_posix()])
        self.assertTrue(os.path.exists(got[0]), "푼 경로가 열려야 검사가 돈다")

    def test_a_shell_variable_set_in_the_same_command_resolves(self):
        """`SP="..." 도구 $SP/문서.md` — 실측에서 다섯 건이 이 꼴이었다."""
        cmd = f'SP="{self.dir.as_posix()}" {MARP} $SP/deck.md'

        got = self.targets(cmd)

        self.assertTrue(got and os.path.exists(got[0]), f"못 풀었다: {got}")

    def test_a_work_file_is_skipped_by_its_resolved_path(self):
        """상대 경로로는 `scratchpad` 가 안 보인다 — 푼 뒤에 걸러야 한다."""
        work = self.dir / "scratchpad"
        work.mkdir(exist_ok=True)
        (work / "draft.md").write_text("# 초안\n", encoding="utf-8")
        cmd = f'cd "{work.as_posix()}" && {MARP} draft.md'

        self.assertEqual(self.targets(cmd), [],
                         "작업 문서가 발행 검사 대상으로 올라왔다")

    def test_an_unresolvable_variable_is_dropped_not_guessed(self):
        """앞선 호출에서 내보낸 변수는 못 푼다 — 짐작하면 엉뚱한 파일을 연다."""
        self.assertEqual(self.mod.in_command(f"{MARP} $NOPE/deck.md",
                                             "$NOPE/deck.md"), "")

    def test_an_absolute_path_is_left_alone(self):
        """이미 열리는 경로에 `cd` 를 덧붙이면 망가진다."""
        cmd = (f'cd "{self.dir.as_posix()}" && {MARP} '
               f'"{(self.dir / "deck.md").as_posix()}"')

        got = self.targets(cmd)

        self.assertTrue(os.path.exists(got[0]))


class HoldTests(unittest.TestCase):
    """못 연 발행을 어떻게 다루나 — 막는 조건이 좁아야 한다."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load()
        cls.dir = fresh_dir()
        cls.doc = cls.dir / "deck.md"
        cls.doc.write_text("# 제목\n", encoding="utf-8")

    def test_nothing_opened_holds_the_publish(self):
        """한 장도 못 열었으면 그 발행은 검사된 적이 없다."""
        out = self.mod.publish_block(publish(f"{MARP} 없는파일.md"),
                                     [str(self.dir / "없는파일.md")])

        self.assertIn("발행 보류", out)
        self.assertIn(self.mod.FORCE, out, "푸는 길을 적지 않으면 자물쇠만 남는다")

    def test_a_missing_output_beside_an_opened_source_does_not_hold(self):
        """발행 도구는 `.md` 를 읽어 `.html` 을 **만들면서** 부른다.

        그 산출물은 이 시점에 아직 없다. 거기까지 막으면 정상 빌드마다 보류가
        떠 넘기기가 습관이 된다 — 자물쇠가 없는 것보다 나쁘다.
        """
        out = self.mod.publish_block(
            publish(f"{MARP} deck.md -o deck.html"),
            [str(self.doc), str(self.dir / "deck.html")])

        self.assertNotIn("한 장도 못 열었", out)


def tearDownModule():
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
