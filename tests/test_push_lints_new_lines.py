"""push 판정 설정의 `require` 에 `"lint"` 를 두면 **이번 브랜치에서 새로 쓰거나 고친 줄의 1층 오류**를 막는지 본다.

(2026-10-30 사용자 결정 「A」) dynamic-docs 빌드에서 문체 검사기를 빼자 동료 원고는 풀렸지만 사용자 본인
원고의 1층 오류를 막던 장치도 함께 사라졌다 — 쓰기 훅은 알리기만 하고 push 게이트는 2층 판정만 봤다.
**남의 줄은 안 본다** — 기준 판(갈라진 지점)에 이미 있던 줄과 원본 선언(`origin:`)의 줄은 빼고 센다.
`"lint"` 를 안 둔 저장소는 지금과 같다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "doc-style-gate.py"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import layer2_coverage as coverage  # noqa: E402
import gate_result  # noqa: E402

LISTED = """[[repo]]
origin = "https://github.com/Example/shared-docs.git"
require = ["judgment"{lint}]
targets = ["docs/*.md"]
base = "main"
"""
#: 동료가 쓴 줄 — 반말이 있지만 이번 브랜치가 쓴 줄이 아니다
BASE = "# 진행 현황\n\n- **상태**: 진행 중이다.\n"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          check=True, capture_output=True, text=True, encoding="utf-8").stdout


class PushLintTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.repo = t / "site"
        (self.repo / "docs").mkdir(parents=True)
        self.listing = t / "local-publish-repos.toml"
        self.listing.write_text(LISTED.format(lint=', "lint"'), encoding="utf-8")
        self.log = t / "judge.jsonl"
        self.env = dict(os.environ, KOREAN_CHECK_RECORD=str(t / "pass.jsonl"),
                        KOREAN_QA_JUDGE_LOG=str(self.log), KOREAN_QA_RECORDER=str(ROOT / "scripts" / "check_record.py"),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_QA_JUDGE=str(ROOT / "scripts" / "judge_layer2.py"),
                        KOREAN_QA_CHECKER=str(ROOT / "assets" / "doc-style-check.py"),
                        KOREAN_QA_PUBLISH_REPOS=str(self.listing))
        self.doc = self.repo / "docs" / "a.md"
        self.doc.write_text(BASE, encoding="utf-8")
        git(self.repo, "init", "-b", "main")
        git(self.repo, "remote", "add", "origin", "https://github.com/Example/shared-docs.git")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "switch", "-c", "kkh/work")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def commit(self, text: str) -> None:
        self.doc.write_text(text, encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "edit")
        # 판정은 마친 것으로 둔다 — 막는 까닭이 1층 오류 하나만 남게 한다
        lines = coverage.read_doc(self.doc).splitlines()
        self.log.write_text(json.dumps({"ok": True, "key": coverage.doc_key(self.doc), "when": time.time(),
                                        "seen": coverage.seen_keys(lines)}, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    def push(self) -> tuple[int, str]:
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "lint-t",
                   "cwd": str(self.repo), "tool_input": {"command": "git push -u origin HEAD"}}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "--probe"],
                              input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=180, env=self.env)
        return gate_result.read(done)

    def test_an_error_on_a_new_line_blocks(self) -> None:
        self.commit(BASE + "- **다음**: 검토 회의를 연다.\n")
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("1층 오류", out)
        self.assertIn("4행", out, "새로 쓴 줄(4행)의 오류를 짚지 않았습니다")
        self.assertNotIn("3행", out.split("고치는 법")[0], "동료가 쓴 줄(3행)의 오류까지 셌습니다")

    def test_an_error_on_a_line_already_on_main_does_not_block(self) -> None:
        """동료가 쓴 줄(갈라진 지점에 있던 「진행 중이다.」)은 이번 브랜치의 몫이 아니다."""
        self.commit(BASE + "- **다음**: 검토 회의\n")
        rc, out = self.push()
        self.assertEqual(0, rc, out)

    def test_a_repo_without_lint_is_unchanged(self) -> None:
        self.listing.write_text(LISTED.format(lint=""), encoding="utf-8")
        self.commit(BASE + "- **다음**: 검토 회의를 연다.\n")
        rc, out = self.push()
        self.assertEqual(0, rc, out)

    def test_lint_is_not_a_record_to_ask_for(self) -> None:
        """`lint` 는 게이트가 직접 보는 것이라 「lint 기록 없음」을 요구하지 않는다(열쇠 없는 자물쇠 금지)."""
        self.commit(BASE + "- **다음**: 검토 회의\n")
        _, out = self.push()
        self.assertNotIn("lint 기록 없음", out)

    def test_lines_from_a_declared_origin_are_not_linted(self) -> None:
        (self.repo / "docs" / "from-colleague.md").write_text("- **일정**: 11월에 마친다.\n", encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "colleague original")
        git(self.repo, "switch", "-q", "main")
        git(self.repo, "merge", "-q", "kkh/work")
        git(self.repo, "switch", "-q", "kkh/work")
        self.commit("---\norigin: from-colleague.md\n---\n\n" + BASE + "- **일정**: 11월에 마친다.\n")
        rc, out = self.push()
        self.assertEqual(0, rc, f"원본 선언의 줄(남이 쓴 줄)을 1층 오류로 막았습니다: {out[:400]}")


if __name__ == "__main__":
    unittest.main()
