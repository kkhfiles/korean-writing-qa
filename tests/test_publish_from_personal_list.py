"""push 직전 2층 판정을 **개인 목록**으로 켜는지 본다.

**왜 있나.** 여럿이 쓰는 저장소의 `korean-qa.toml` 에 `[publish]` 를 두면 이 훅을 설치한
다른 사람의 push 까지 막는다(2026-10-30 사용자 결정 · dynamic-docs). 그래서 그런 저장소는
이 PC 의 개인 목록에 원격 주소로 적고, 저장소에는 설정을 두지 않는다.
- 목록에 있는 저장소 → 저장소에 설정이 없어도 막는다
- 목록에 없는 저장소 → 안 막는다
- 같은 저장소를 https 와 ssh 주소로 적어도 같게 본다
- 목록을 못 읽으면 조용히 넘기지 않는다
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "doc-style-gate.py"
RECORDER = ROOT / "scripts" / "check_record.py"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_result  # noqa: E402  막힘을 종료 코드 2 와 deny JSON 둘 다로 읽는다

LISTED = """[[repo]]
origin = "https://github.com/Example/shared-docs.git"
require = ["judgment"]
targets = ["*/docs/*.md"]
base = "main"
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          check=True, capture_output=True, text=True, encoding="utf-8").stdout


class PersonalPublishListTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.repo = t / "site"
        (self.repo / "dyn" / "docs").mkdir(parents=True)
        self.listing = t / "local-publish-repos.toml"
        self.listing.write_text(LISTED, encoding="utf-8")
        self.env = dict(os.environ, KOREAN_CHECK_RECORD=str(t / "pass.jsonl"),
                        KOREAN_QA_JUDGE_LOG=str(t / "judge.jsonl"), KOREAN_QA_RECORDER=str(RECORDER),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_QA_JUDGE=str(ROOT / "scripts" / "judge_layer2.py"),
                        KOREAN_QA_PUBLISH_REPOS=str(self.listing))
        self.doc = self.repo / "dyn" / "docs" / "a.md"
        self.doc.write_text("# 진행 현황\n\n- **상태**: 진행 중\n", encoding="utf-8")
        git(self.repo, "init", "-b", "main")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "switch", "-c", "kkh/work")
        self.doc.write_text("# 진행 현황\n\n- **상태**: 진행 중\n- **위험**: 일정 지연 가능성\n",
                            encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "edit")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def origin(self, url: str) -> None:
        git(self.repo, "remote", "add", "origin", url)

    def push(self) -> tuple[int, str]:
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "personal-t",
                   "cwd": str(self.repo), "tool_input": {"command": "git push -u origin HEAD"}}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "--probe"],
                              input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120, env=self.env)
        return gate_result.read(done)

    def test_a_listed_repo_is_gated_without_repo_config(self) -> None:
        self.origin("https://github.com/Example/shared-docs.git")
        self.assertFalse((self.repo / "korean-qa.toml").exists())
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("dyn/docs/a.md", out)
        self.assertIn("개인 목록", out, "어디서 켠 게이트인지 안 알립니다")

    def test_an_unlisted_repo_is_not_gated(self) -> None:
        self.origin("https://github.com/Example/other-docs.git")
        self.assertEqual(0, self.push()[0])

    def test_a_repo_without_origin_is_not_gated(self) -> None:
        self.assertEqual(0, self.push()[0])

    def test_ssh_and_https_are_the_same_repo(self) -> None:
        user = "git"                     # scp 꼴 ssh 주소 — 원문에 메일 주소 꼴을 남기지 않게 조립한다
        self.origin(f"{user}@github.com:example/shared-docs")
        self.assertEqual(2, self.push()[0], "ssh 주소로 클론한 저장소를 목록의 https 주소와 다르게 봤습니다")

    def test_an_unreadable_list_does_not_pass_silently(self) -> None:
        self.origin("https://github.com/Example/shared-docs.git")
        self.listing.write_text("[[repo]\norigin = ", encoding="utf-8")
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("못 읽었습니다", out)

    def test_the_repo_config_comes_first(self) -> None:
        self.origin("https://github.com/Example/shared-docs.git")
        (self.repo / "korean-qa.toml").write_text(
            '[publish]\nrequire = ["judgment"]\ntargets = ["README.md"]\nbase = "main"\n', encoding="utf-8")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "config")
        self.assertEqual(0, self.push()[0], "저장소 설정의 대상(README)이 아닌 문서를 막았습니다")


if __name__ == "__main__":
    unittest.main()
