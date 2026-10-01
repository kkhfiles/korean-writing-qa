"""게이트가 훅으로 불렸을 때 **deny JSON 으로** 막는지 고정한다 — 종료 코드 2 로 되돌아가면 깨진다.

**왜 있나.** Codex 0.159.1 은 PreToolUse 훅의 종료 코드 2 를 막음이 아니라 「Failed」로 받고 명령을
그대로 실행했다(2026-10-01 실측 · 공식 문서는 막는다고 적었다). 같은 훅이 `permissionDecision: deny`
JSON 으로 답하자 막혔고, Claude Code 도 그 JSON 으로 막았다. 다른 시험들은 두 모양을 다 「막힘」으로
읽으므로(`gate_result`) 모양 자체는 여기서 따로 본다.

**스크립트 호출은 종료 코드 그대로** — `sync.sh` 가 `public-push-gate.py --repo` 의 종료 코드를 읽는다.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
DOC_GATE = ROOT / "hooks" / "doc-style-gate.py"
PUSH_GATE = ROOT / "hooks" / "public-push-gate.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def deny_reason(stdout: str) -> str | None:
    try:
        spec = json.loads(stdout.strip())["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return None
    if spec.get("hookEventName") == "PreToolUse" and spec.get("permissionDecision") == "deny":
        return spec.get("permissionDecisionReason")
    return None


class GatesDenyAsJson(unittest.TestCase):

    def test_the_doc_gate_denies_a_push_with_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "r"
            (repo / "d" / "docs").mkdir(parents=True)
            (repo / "korean-qa.toml").write_text(
                '[publish]\nrequire = ["judgment"]\ntargets = ["*/docs/*.md"]\nbase = "main"\n', encoding="utf-8")
            doc = repo / "d" / "docs" / "a.md"
            doc.write_text("# 제목\n", encoding="utf-8")
            g = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(repo)]
            for args in (["init", "-b", "main"], ["add", "."], ["commit", "-m", "b"], ["switch", "-c", "w"]):
                subprocess.run(g + args, check=True, capture_output=True)
            doc.write_text("# 제목\n\n새로 쓴 문장입니다.\n", encoding="utf-8")
            subprocess.run(g + ["commit", "-am", "e"], check=True, capture_output=True)
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "j",
                       "cwd": str(repo), "tool_input": {"command": "git push"}}
            env = dict(os.environ, KOREAN_QA_JUDGE="-",
                       KOREAN_CHECK_RECORD=str(Path(tmp) / "store.jsonl"))
            done = subprocess.run([sys.executable, "-X", "utf8", str(DOC_GATE), "--probe"],
                                  input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
        self.assertEqual(0, done.returncode, "종료 코드 2 로 막으면 Codex 가 명령을 실행한다")
        reason = deny_reason(done.stdout)
        self.assertIsNotNone(reason, f"deny JSON 이 아닙니다: {done.stdout[:200]}")
        self.assertIn("push 보류", reason)

    def test_the_public_push_hook_denies_with_json(self) -> None:
        mod = load(PUSH_GATE, "public_push_gate_deny_t")
        payload = json.dumps({"tool_input": {"command": "git push"}, "cwd": str(ROOT)})
        out = io.StringIO()
        with mock.patch.object(mod, "gate", return_value=(2, "공개 저장소라 푸시를 멈췄습니다")), \
                mock.patch.object(mod.sys, "stdin", io.StringIO(payload)), \
                contextlib.redirect_stdout(out):
            rc = mod.main([])
        self.assertEqual(0, rc)
        self.assertIn("멈췄습니다", deny_reason(out.getvalue()) or "")

    def test_the_script_mode_still_answers_with_the_exit_code(self) -> None:
        """`sync.sh` 가 이 종료 코드를 읽는다 — JSON 으로 바꾸면 sync 가 공개 저장소로 그냥 민다."""
        mod = load(PUSH_GATE, "public_push_gate_cli_t")
        with mock.patch.object(mod, "gate", return_value=(2, "멈춤")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, mod.main(["--repo", str(ROOT)]))


if __name__ == "__main__":
    unittest.main()
