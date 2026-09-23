"""작업 트리(`<저장소>/.claude/worktrees/<이름>/`) 안의 문서는 설정이 아니라 문서다.

**왜 있나** — 검사기와 게이트가 경로에 `.claude/` 가 들어 있으면 **설정 자리**로 보고
뺐다. 작업 트리도 그 글자를 품고 있어서 두 가지가 조용히 빠졌다(2026-09-23 다른 세션
제보 · 이 세션에서 재현).

- 검사기 — 작업 트리 안 문서를 「Claude 전용 지시 파일」로 분류해 반말을 안 봤다.
  같은 문서가 기본 체크아웃에서는 반말 34건, 작업 트리 사본에서는 0건이었다.
- 게이트 — 작업 트리 세션의 쓰기가 전부 검사에서 빠졌다. 오류 11건짜리 HTML 을
  고치는 동안 훅이 아무 말도 없었다.

작업 트리로만 고치는 저장소(전역 규칙 「같은 저장소를 쓰는 독립 세션의 Git worktree
분리」)에서는 둘 다 **없는 것과 같았다.**
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

GATE = repo_paths.hook("doc-style-gate.py")
REPO = "P:/work/repo"
TREE = f"{REPO}/.claude/worktrees/fix-a"
# 홈 경로는 돌 때 만든다 — 파일에 `C:/Users/<이름>` 을 적으면 공개 저장소 검사가 계정
# 이름으로 본다(자리표시 이름이어도 가를 수 없다).
HOME = Path.home().as_posix() + "/.claude"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorktreePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = load("doc_style_check", repo_paths.CHECKER)
        cls.gate = load("doc_style_gate", GATE)

    # ── 검사기 — 지시 파일인가 ───────────────────────────────────────────────

    def test_a_document_in_a_worktree_is_a_document(self) -> None:
        self.assertFalse(self.checker.is_instruction_file(f"{TREE}/docs/dev.md"))
        self.assertFalse(self.checker.is_instruction_file(f"{TREE}/lab/pages/value.html"))

    def test_instruction_files_inside_a_worktree_stay_instructions(self) -> None:
        """작업 트리 안이라도 저장소의 지시 파일은 지시 파일이다."""
        self.assertTrue(self.checker.is_instruction_file(f"{TREE}/CLAUDE.md"))
        self.assertTrue(self.checker.is_instruction_file(f"{TREE}/.claude/agents/helper.md"))
        self.assertTrue(self.checker.is_instruction_file(f"{TREE}/skills/x/references/rules.md"))

    def test_the_home_config_is_still_config(self) -> None:
        self.assertTrue(self.checker.is_instruction_file(f"{HOME}/references/work-principles.md"))
        self.assertTrue(self.checker.is_instruction_file(f"{REPO}/.claude/agents/helper.md"))

    # ── 게이트 — 뺄 작업 문서인가 ───────────────────────────────────────────

    def test_the_gate_checks_writes_inside_a_worktree(self) -> None:
        self.assertFalse(self.gate.skipped(f"{TREE}/docs/dev.md"))

    def test_the_gate_still_skips_config_and_scratch(self) -> None:
        self.assertTrue(self.gate.skipped(f"{HOME}/plans/today.md"))
        self.assertTrue(self.gate.skipped(f"{REPO}/.claude/agents/helper.md"))
        self.assertTrue(self.gate.skipped(f"{TREE}/node_modules/pkg/README.md"))
        self.assertTrue(self.gate.skipped(f"{TREE}/.claude/settings.md"))

    # ── 붙어 있나 — 판정 함수가 맞아도 훅이 안 부르면 없는 것과 같다 ─────────

    def test_the_hook_speaks_up_for_a_worktree_write(self) -> None:
        """같은 반말 문서를 작업 트리 모양 경로에 쓰면 훅이 말해야 한다."""
        base = Path(repo_paths.gate_scratch(".gate-probe-worktree-"))
        try:
            doc = base / "repo" / ".claude" / "worktrees" / "fix-a" / "docs" / "dev.md"
            doc.parent.mkdir(parents=True)
            doc.write_text("# 점검\n\n점검 결과 · 한 장\n\n본문은 반말로 끝난다.\n",
                           encoding="utf-8")
            payload = {"hook_event_name": "PostToolUse", "tool_name": "Write",
                       "session_id": "worktree-probe",
                       "tool_input": {"file_path": str(doc)},
                       "tool_response": {"filePath": str(doc)}}
            done = subprocess.run(
                [sys.executable, "-X", "utf8", str(GATE), "--probe"],
                input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                text=True, encoding="utf-8", timeout=180,
                env={**os.environ, "KOREAN_QA_CHECKER": str(repo_paths.CHECKER)})
            self.assertIn("반말 서술형", done.stdout + done.stderr,
                          "작업 트리의 쓰기에 훅이 아무 말도 안 합니다")
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
