"""발행 직전 — 확인 안 된 내용 표시가 남은 문서를 막는지 본다.

**왜**(2026-09-29 사용자) — 「이건 한국어 검사기가 고칠게 아니라 문서 만들고 배포하는
쪽에서 이런 불확실한 내용이 붙은 채로 배포하면 안됨」. 말을 다듬어 풀 문제가 아니라
확인하거나 지울 문제라서 문체 검사기가 아니라 발행 게이트가 막는다.

**두 방향 다 지킨다** — 표시가 있으면 막고, 표시처럼 생긴 정당한 쓰임은 안 막는다.
정당한 쓰임은 문서 2,816개 실측에서 실제로 걸린 것들이다(부정 · 조건 · 이름).
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_result  # noqa: E402  막힘을 종료 코드 2 와 deny JSON 둘 다로 읽는다

HOOK = repo_paths.hook("doc-style-gate.py")


def load():
    spec = importlib.util.spec_from_file_location("doc_style_gate_unverified", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GATE = load()

MARKED = [
    "- 기업 시범사업 중 실제 운영 도달 11~14% <em>(원문 미확인)</em>",
    "- 보고된 성공률 42%(진위 미확인)",
    "- 시장 규모는 3조 원(확인 필요)",
    "- 11~14%만 실제 운영에 도달(원문 미확인 — 방향 신호로만)",
    "- 회사 메일 서버 위치는 안 적음(확인 전)",
    "| 연동 대상 | TBD |",
    "- 출시 시점 [미검증]",
]
CLEAN = [
    "- 원본 자료를 찾았음(미확인 아님)",
    "### 명령어는 검증한 것만 (미검증이면 표기)",
    "## 전체 백로그 관리 원장 (TODO Ledger)",
    "- 고객 문의 3건(확인 중)",
    "- 딱지를 바꿔 다는 것(「(진위 미확인)」→「(검증되지 않은 수치)」)은 고친 것이 아님",
    "- 표시 예: `(확인 필요)` 는 발행 전에 지움",
]


class MarkTests(unittest.TestCase):

    def marks(self, lines: list[str]) -> list:
        d = Path(repo_paths.gate_scratch(".gate-probe-unverified-"))
        self.addCleanup(shutil.rmtree, d, True)
        p = d / "doc.md"
        p.write_text("# 문서\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
        return GATE.unverified_marks(str(p))

    def test_marked_lines_are_found(self) -> None:
        for line in MARKED:
            self.assertTrue(self.marks([line]), f"확인 안 된 표시를 못 찾았습니다 — {line}")

    def test_lookalikes_are_not_found(self) -> None:
        for line in CLEAN:
            self.assertEqual([], self.marks([line]), f"정당한 쓰임을 표시로 잡았습니다 — {line}")

    def test_fenced_code_is_skipped_and_line_numbers_hold(self) -> None:
        got = self.marks(["```", "(확인 필요)", "```", "- 규모 3조 원(확인 필요)"])
        self.assertEqual(1, len(got), "코드 펜스 안을 봤거나 밖을 놓쳤습니다")
        self.assertEqual(6, got[0][0], "코드 펜스를 지우며 줄 번호가 밀렸습니다")


class BlockTests(unittest.TestCase):

    def setUp(self) -> None:
        d = Path(repo_paths.gate_scratch(".gate-probe-unverified-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.doc = d / "page.md"
        self.doc.write_text("# 시장 조사\n\n**요점** — 한 줄\n\n- 성공률 42%(진위 미확인)\n",
                            encoding="utf-8")

    def payload(self, event="PreToolUse", tool="Artifact", command=None):
        inp = {"file_path": str(self.doc)}
        if command is not None:
            inp = {"command": command}
        return {"hook_event_name": event, "tool_name": tool, "tool_input": inp}

    def test_publishing_is_blocked(self) -> None:
        msg = GATE.unverified_block(self.payload(), [str(self.doc)])
        self.assertIn("발행 보류", msg)
        self.assertIn("(진위 미확인)", msg)

    def test_writing_is_not_blocked(self) -> None:
        """쓰는 순간에는 안 막는다 — 초안에는 확인 전 표시가 있는 것이 정상이다."""
        self.assertEqual("", GATE.unverified_block(self.payload(event="PostToolUse"), [str(self.doc)]))

    def test_force_in_the_command_opens_it(self) -> None:
        cmd = f"{GATE.FORCE} python notion.py create {self.doc}"
        self.assertEqual("", GATE.unverified_block(self.payload(tool="Bash", command=cmd),
                                                   [str(self.doc)]))

    def test_the_hook_exits_2_on_artifact_publish(self) -> None:
        """훅 전체를 돌려 실제로 막히는지 — 함수만 보면 main 에서 안 부르는 것을 못 잡는다."""
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(HOOK), "--probe"],
            input=json.dumps(self.payload(), ensure_ascii=False),
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        code, said = gate_result.read(done)
        self.assertEqual(2, code, said)
        self.assertIn("확인 안 된 내용 표시", said)


if __name__ == "__main__":
    unittest.main()
