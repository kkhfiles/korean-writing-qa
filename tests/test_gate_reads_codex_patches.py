"""게이트가 Codex 의 `apply_patch` 쓰기를 **직접** 읽는지 본다.

**왜 있나.** Codex 는 파일을 `apply_patch` 로 쓰고, 경로는 패치의 파일 머리
(`*** Update File: …`)에 세션 작업 폴더 기준으로 적힌다. 전에는 설정 거울의 Codex 어댑터가
이것을 Claude 모양(`Write`)으로 옮겨 넣었는데, 옮기는 사본이 따로 있으면 한쪽만 고쳐진다
(push 판별에서 실제로 그렇게 됐다 · 2026-10-01). 게이트가 직접 읽으면 Codex 를 설치하는
PC 는 어댑터 없이 이 훅을 그대로 걸면 된다.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import repo_paths  # noqa: E402

GATE = ROOT / "hooks" / "doc-style-gate.py"
DIRTY = "# 계획\n\n- **언제 도나** — 매일\n- 새 자료는 해당 폴더에\n"


class CodexPatchTests(unittest.TestCase):

    def setUp(self) -> None:
        # 게이트가 Temp·scratchpad 를 건너뛰므로 거기는 안 된다
        self.dir = repo_paths.gate_scratch(".gate-codex-")
        self.env = dict(os.environ, KOREAN_CHECK_RECORD=os.path.join(self.dir, "store.jsonl"))

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def doc(self, name: str, body: str) -> str:
        p = os.path.join(self.dir, name)
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        return p

    def fire(self, tool_input: dict) -> str:
        payload = {"hook_event_name": "PostToolUse", "tool_name": "apply_patch",
                   "session_id": "codex-t", "cwd": self.dir, "tool_input": tool_input}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "--probe"],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=240, env=self.env)
        return done.stdout + done.stderr

    def test_a_patched_document_is_checked(self) -> None:
        self.doc("plan.md", DIRTY)
        patch = "*** Begin Patch\n*** Update File: plan.md\n@@\n+- 새 자료는 해당 폴더에\n*** End Patch"
        for field in ("command", "patch"):          # Codex 문서는 command · 운영 기록은 patch
            with self.subTest(field=field):
                out = self.fire({field: patch})
                self.assertIn("plan.md", out, f"패치로 쓴 문서를 안 봤습니다: {out[:300]}")
                self.assertIn("해당 폴더에", out)

    def test_code_files_in_a_patch_are_not_documents(self) -> None:
        self.doc("tool.py", "print('새 자료는 해당 폴더에')\n")
        out = self.fire({"command": "*** Begin Patch\n*** Add File: tool.py\n+x\n*** End Patch"})
        self.assertNotIn("tool.py", out)

    def test_paths_resolve_against_the_session_cwd(self) -> None:
        sub = os.path.join(self.dir, "docs")
        os.makedirs(sub)
        with io.open(os.path.join(sub, "a.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(DIRTY)
        out = self.fire({"command": "*** Begin Patch\n*** Update File: docs/a.md\n+x\n*** End Patch"})
        self.assertIn("a.md", out, "세션 작업 폴더 기준 상대 경로를 못 풀었습니다")


if __name__ == "__main__":
    unittest.main()
