"""`[publish]` 를 켠 저장소에서 push 직전에 **새 줄의 2층 판정**을 요구하는지 본다.

**왜 있나.** lab-docs 는 가지 push → PR → 병합으로 나가는데, 발행 게이트는 이 길을 안
봤다. 14일 동안 문서 62개가 나갔고 2층 판정 기록은 1건이었다(2026-10-01 실측).

**막는 것과 여는 것을 짝으로 본다** — 열 길이 없는 자물쇠는 넘기기를 습관으로 만든다.
- 판정기가 새 줄을 다 봤고 판단 기록(까닭 포함)이 있으면 연다
- 판정기를 못 부르는 PC 에서는 판단 기록만으로 연다
- 이미 있던 줄 · 지우기만 한 문서 · 대상 밖 파일은 안 본다
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
RECORDER = ROOT / "scripts" / "check_record.py"
sys.path.insert(0, str(ROOT / "scripts"))

import layer2_coverage as coverage  # noqa: E402

CONFIG = """[rules]
on = ["반말 서술형"]

[publish]
require = ["judgment"]
targets = ["*/docs/*.md", "README.md"]
base = "main"
"""


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          check=True, capture_output=True, text=True, encoding="utf-8").stdout


class PushGateTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.repo = t / "site"
        (self.repo / "dyn" / "docs").mkdir(parents=True)
        self.store = t / "pass.jsonl"
        self.log = t / "judge.jsonl"
        self.env = dict(os.environ, KOREAN_CHECK_RECORD=str(self.store),
                        KOREAN_QA_JUDGE_LOG=str(self.log), KOREAN_QA_RECORDER=str(RECORDER),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_QA_JUDGE=str(ROOT / "scripts" / "judge_layer2.py"))
        self.doc = self.repo / "dyn" / "docs" / "a.md"
        (self.repo / "korean-qa.toml").write_text(CONFIG, encoding="utf-8")
        self.write(["# 진행 현황", "", "- **상태**: 진행 중", "- **다음**: 검토 회의"])
        git(self.repo, "init", "-b", "main")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "switch", "-c", "kkh/work")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, lines: list[str], path: Path | None = None) -> None:
        (path or self.doc).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def commit(self, lines: list[str], path: Path | None = None) -> None:
        self.write(lines, path)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "edit")

    def add_line(self) -> None:
        self.commit(["# 진행 현황", "", "- **상태**: 진행 중", "- **다음**: 검토 회의",
                     "- **위험**: 일정 지연 가능성"])

    def push(self, cmd: str = "git push -u origin HEAD", cwd: Path | None = None,
             env: dict | None = None, tool: str = "Bash") -> tuple[int, str]:
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "session_id": "push-t",
                   "cwd": str(cwd or self.repo), "tool_input": {"command": cmd}}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "--probe"],
                              input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120,
                              env=env or self.env)
        return done.returncode, done.stdout + done.stderr

    def judged(self, path: Path | None = None) -> None:
        """판정기가 지금 내용의 줄을 다 본 것처럼 기록한다."""
        path = path or self.doc
        lines = coverage.read_doc(path).splitlines()
        row = {"ok": True, "when": time.time(), "key": coverage.doc_key(path),
               "seen": coverage.seen_keys(lines)}
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def recorded(self, path: Path | None = None) -> None:
        subprocess.run([sys.executable, "-X", "utf8", str(RECORDER), "record", str(path or self.doc),
                        "--stage", "judgment", "--verdict", "pass", "--note", "남은 1건은 굳은 용어"],
                       check=True, capture_output=True, env=self.env)

    def test_a_repo_without_publish_is_not_gated(self) -> None:
        (self.repo / "korean-qa.toml").write_text('[rules]\non = ["반말 서술형"]\n', encoding="utf-8")
        self.add_line()
        self.assertEqual(0, self.push()[0])

    def test_a_new_line_without_judgment_blocks(self) -> None:
        self.add_line()
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("dyn/docs/a.md", out)
        self.assertIn("판정기가 아직 안 본 새 줄 1개", out)
        self.assertIn("judgment 기록 없음", out)
        self.assertIn("--since main", out, "고치는 법에 새 줄만 판정하는 명령이 없습니다")

    def test_judged_and_recorded_lets_it_through(self) -> None:
        self.add_line()
        self.judged()
        self.recorded()
        rc, out = self.push()
        self.assertEqual(0, rc, out)

    def test_a_record_without_judging_still_blocks(self) -> None:
        """판정기를 부를 수 있는 PC 에서는 판정기가 새 줄을 실제로 봤어야 한다."""
        self.add_line()
        self.recorded()
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("판정기가 아직 안 본 새 줄", out)
        self.assertNotIn("judgment 기록 없음", out)

    def test_judging_without_a_record_still_blocks(self) -> None:
        self.add_line()
        self.judged()
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("judgment 기록 없음", out)
        self.assertNotIn("안 본 새 줄", out)

    def test_without_a_judge_the_record_alone_opens_it(self) -> None:
        """⛔ 열쇠 없는 자물쇠 금지 — 판정기를 못 부르는 PC 에 판정기 기록을 요구하지 않는다."""
        env = dict(self.env, KOREAN_QA_JUDGE="-")
        self.add_line()
        rc, out = self.push(env=env)
        self.assertEqual(2, rc, out)
        self.assertIn("직접 읽고", out)
        self.assertNotIn("안 본 새 줄", out)
        self.recorded()
        self.assertEqual(0, self.push(env=env)[0])

    def test_the_committed_content_is_what_counts(self) -> None:
        self.add_line()
        self.judged()
        self.recorded()
        self.write(["# 진행 현황", "커밋 안 한 줄입니다."])      # 커밋 안 한 수정은 나가지 않는다
        self.assertEqual(0, self.push()[0])
        self.commit(["# 진행 현황", "", "- **상태**: 진행 중", "- **다음**: 검토 회의",
                     "- **위험**: 일정 지연 가능성", "- **대응**: 범위 축소"])
        rc, out = self.push()
        self.assertEqual(2, rc, "판정 뒤 커밋한 새 줄이 그대로 나갔습니다")
        self.assertIn("안 본 새 줄 1개", out, "이미 판정한 줄까지 다시 요구했습니다")

    def test_deleting_lines_needs_nothing(self) -> None:
        self.commit(["# 진행 현황", "", "- **상태**: 진행 중"])
        self.assertEqual(0, self.push()[0])

    def test_files_outside_the_targets_are_not_gated(self) -> None:
        (self.repo / "dyn" / "docs" / "drafts").mkdir()
        self.commit(["# 초안", "새로 쓴 초안 문장입니다."], self.repo / "dyn" / "docs" / "drafts" / "x.md")
        self.commit(["print('빌드')"], self.repo / "build.py")
        self.assertEqual(0, self.push()[0], "하위 폴더 초안이나 대상 밖 파일까지 막았습니다")

    def test_a_new_file_is_all_new(self) -> None:
        self.commit(["# 새 문서", "처음 쓴 문장입니다."], self.repo / "README.md")
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("README.md", out)
        self.assertIn("새 줄 2개", out)

    def test_force_is_the_visible_way_out(self) -> None:
        self.add_line()
        self.assertEqual(0, self.push("KOREAN_PUBLISH_FORCE=1 git push -u origin HEAD")[0])

    def test_push_inside_quotes_is_not_a_push(self) -> None:
        self.add_line()
        self.assertEqual(0, self.push('git commit -m "git push 뒤에 고침"')[0])

    def test_git_dash_c_points_at_the_repo(self) -> None:
        self.add_line()
        rc, _ = self.push(f'git -C "{self.repo}" push', cwd=Path(self.tmp.name))
        self.assertEqual(2, rc, "-C 로 가리킨 저장소를 안 봤습니다")

    def test_cd_before_push_points_at_the_repo(self) -> None:
        """훅 payload 의 cwd 는 명령 전 폴더다 — `cd 저장소 && git push` 를 놓치면 엉뚱한 저장소를 본다."""
        self.add_line()
        rc, _ = self.push(f'cd "{self.repo}" && git push -u origin HEAD', cwd=Path(self.tmp.name))
        self.assertEqual(2, rc, "cd 로 옮긴 저장소를 안 봤습니다")

    def test_set_location_before_push_in_powershell(self) -> None:
        self.add_line()
        rc, _ = self.push(f"Set-Location -LiteralPath '{self.repo}'; git push", cwd=Path(self.tmp.name),
                          tool="PowerShell")
        self.assertEqual(2, rc, "Set-Location 으로 옮긴 저장소를 안 봤습니다")

    @unittest.skipUnless(os.name == "nt", "Git Bash 경로 꼴은 Windows 전용")
    def test_git_bash_style_paths_are_resolved(self) -> None:
        """Bash 도구 명령은 `/c/Users/…` 꼴을 흔히 쓴다 — 못 풀면 게이트가 조용히 통과한다."""
        self.add_line()
        drive, rest = str(self.repo.resolve()).split(":", 1)
        bash_path = "/" + drive.lower() + rest.replace(os.sep, "/")
        rc, _ = self.push(f"git -C {bash_path} push", cwd=Path(self.tmp.name))
        self.assertEqual(2, rc, f"{bash_path} 를 못 풀었습니다")

    def test_an_unknown_base_blocks_with_a_way_out(self) -> None:
        (self.repo / "korean-qa.toml").write_text(CONFIG.replace('base = "main"', 'base = "origin/main"'),
                                                  encoding="utf-8")
        self.add_line()
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("갈라진 지점을 못 찾았습니다", out)
        self.assertIn("git fetch", out)

    def test_target_patterns_count_folders(self) -> None:
        gate = _load_gate()
        self.assertTrue(gate.matches("dynamic/docs/a.md", ["*/docs/*.md"]))
        self.assertFalse(gate.matches("dynamic/docs/sub/a.md", ["*/docs/*.md"]))
        self.assertFalse(gate.matches("x/dynamic/docs/a.md", ["*/docs/*.md"]))
        self.assertTrue(gate.matches("README.md", ["README.md"]))


def _load_gate():
    import importlib.util
    spec = importlib.util.spec_from_file_location("doc_style_gate_push_t", GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    unittest.main()
