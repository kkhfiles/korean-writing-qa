"""발행 직전 — 2층 판정을 받은 문서에 판정기가 아직 안 본 한글 줄이 있으면 막는다.

**왜 있나.** Artifact · 노션 발행 게이트는 처리 안 된 고칠 지적과 사람 확인만 봤다. 판정 뒤에 고친
줄이 다시 판정됐는지는 안 봐서, 고친 문장이 판정 없이 나갈 수 있었다. push 게이트와 배포 게이트는
판정 안 된 줄을 본다 — 발행 경로만 빈틈이었다(2026-10-13 · 재판정을 몰아서 하게 하는 방안의 부작용을
검토하다 찾음 · 외부 검토도 같은 결론).

**범위 — 발행하는 문서 전부**(2026-10-13 사용자 결정 「요구」). 처음에는 판정 기록이 있는 문서와 설정의
발행 대상에만 걸었는데, 그러면 판정을 한 번도 안 받은 문서가 더 쉽게 나가는 역전이 생겼다(외부 검토).
**막힘이 풀리는 길** — 게이트가 권하는 판정 명령과 같은 기준으로 가른다. 판정 기록이 있거나 설정의 발행
대상인 git 문서는 `--since <ref>`, git 밖 문서는 `--since HEAD`, 판정을 한 번도 안 받은 git 문서는 전체
판정. 판정기가 없는 PC 는 손 판단 기록으로 연다(열쇠 없는 자물쇠 금지).
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import repo_paths  # noqa: E402
import layer2_coverage as coverage  # noqa: E402

GATE = ROOT / "hooks" / "doc-style-gate.py"
RECORDER = ROOT / "scripts" / "check_record.py"
DOC = ["# 정책 요약", "", "**라이선스 정책** — 한 장 조망", "",
       "- **판매 단위**: 사용자 수", "- **계약 기간**: 1년"]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          check=True, capture_output=True, text=True, encoding="utf-8").stdout


class PublishNeedsJudgingTests(unittest.TestCase):
    def setUp(self) -> None:
        # 게이트가 Temp · scratchpad 를 건너뛰므로 거기는 안 된다
        self.dir = Path(repo_paths.gate_scratch(".gate-publish-judged-"))
        self.log = self.dir / "judge.jsonl"
        self.env = dict(os.environ,
                        KOREAN_CHECK_RECORD=str(self.dir / "pass.jsonl"),
                        KOREAN_QA_JUDGE_LOG=str(self.log),
                        KOREAN_QA_RECORDER=str(RECORDER),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_QA_JUDGE=str(ROOT / "scripts" / "judge_layer2.py"),
                        KOREAN_QA_CHECKER=str(ROOT / "assets" / "doc-style-check.py"),
                        KOREAN_QA_MIDDOT_LEDGER=str(self.dir / "ledger.tsv"))
        self.doc = self.dir / "share.md"
        self.write(DOC)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, lines: list[str], path: Path | None = None) -> None:
        with io.open(path or self.doc, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")

    def judged(self, path: Path | None = None) -> None:
        """판정기가 지금 내용의 줄을 다 본 것처럼 기록한다."""
        path = path or self.doc
        lines = coverage.read_doc(path).splitlines()
        row = {"ok": True, "when": time.time(), "key": coverage.doc_key(path),
               "seen": coverage.seen_keys(lines)}
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def publish(self, path: Path | None = None, env: dict | None = None, command: str | None = None) -> str:
        path = path or self.doc
        if command is None:
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Artifact", "session_id": "pub-t",
                       "cwd": str(path.parent), "tool_input": {"file_path": str(path)}}
        else:
            payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "pub-t",
                       "cwd": str(path.parent), "tool_input": {"command": command}}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE)],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=240, env=env or self.env)
        return done.stdout + done.stderr

    def edit(self) -> None:
        self.write(DOC[:-1] + ["- **계약 기간**: 2년"])

    def test_a_doc_never_judged_needs_judging_too(self) -> None:
        """(2026-10-13 사용자 결정 「요구」) 판정을 한 번도 안 받은 문서가 더 쉽게 나가면 안 된다.
        git 밖 문서는 `--since HEAD` 를 권한다 — 판정기는 git 밖이면 판정 안 한 줄만 본다."""
        out = self.publish()
        self.assertIn('"deny"', out, f"판정을 한 번도 안 받은 문서를 그냥 내보냈습니다:\n{out[:400]}")
        self.assertIn("판정기가 아직 안 본", out)
        self.assertIn("--since HEAD", out)
        self.judged()
        self.assertNotIn('"deny"', self.publish(), "판정한 뒤에도 막았습니다")

    def test_a_git_doc_never_judged_gets_a_full_judgment_command(self) -> None:
        """⛔ 판정을 한 번도 안 받은 git 문서에 `--since` 를 권하면 판정기는 갈라진 지점 뒤 줄만 보고,
        게이트는 전부를 세어 판정을 돌려도 안 풀린다 — 전체 판정을 권한다."""
        repo = self.dir / "plain"
        repo.mkdir()
        doc = repo / "a.md"
        self.write(DOC, doc)
        git(repo, "init", "-b", "main")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "base")
        out = self.publish(doc)
        self.assertIn('"deny"', out)
        line = next(l for l in out.replace("\\n", "\n").splitlines() if "judge_layer2.py" in l)
        self.assertNotIn("--since", line, f"전체 판정이 아니라 --since 를 권했습니다: {line}")
        self.judged(doc)
        self.assertNotIn('"deny"', self.publish(doc))

    def test_an_edit_after_judging_blocks_publishing(self) -> None:
        self.judged()
        self.assertNotIn('"deny"', self.publish(), "다 판정한 문서의 발행을 막았습니다")
        self.edit()
        out = self.publish()
        self.assertIn('"deny"', out, f"판정 뒤 고친 줄이 있는데 발행을 안 막았습니다:\n{out[:400]}")
        self.assertIn("판정기가 아직 안 본", out)
        self.assertIn("judge_layer2.py", out, "푸는 명령을 안 알렸습니다")

    def test_judging_the_edit_opens_it_again(self) -> None:
        self.judged()
        self.edit()
        self.judged()
        self.assertNotIn('"deny"', self.publish())

    def test_without_a_judge_the_manual_record_opens_it(self) -> None:
        """판정기를 못 부르는 PC 에서는 손 판단 기록이 열쇠다."""
        env = dict(self.env, KOREAN_QA_JUDGE="-")
        self.judged()
        self.edit()
        out = self.publish(env=env)
        self.assertIn('"deny"', out)
        self.assertIn("judgment", out)
        subprocess.run([sys.executable, "-X", "utf8", str(RECORDER), "record", str(self.doc),
                        "--stage", "judgment", "--verdict", "pass", "--note", "고친 한 줄을 규칙대로 읽어 봄"],
                       check=True, capture_output=True, env=env)
        self.assertNotIn('"deny"', self.publish(env=env))

    def test_a_git_doc_counts_only_lines_after_the_base(self) -> None:
        """갈라진 지점에 있던 줄은 세지 않는다 — 판정기도 그 줄을 안 보므로(`--since`) 안 풀리는 막힘이 된다."""
        repo = self.dir / "site"
        (repo / "docs").mkdir(parents=True)
        (repo / "korean-qa.toml").write_text(
            '[publish]\nrequire = ["judgment"]\ntargets = ["docs/*.md"]\nbase = "main"\n', encoding="utf-8")
        doc = repo / "docs" / "a.md"
        self.write(DOC, doc)
        git(repo, "init", "-b", "main")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "base")
        git(repo, "switch", "-c", "work")
        self.write(DOC + ["- **갱신 주기**: 분기"], doc)
        # 새 줄만 판정한 기록 — 기준 판의 줄은 판정기가 본 적이 없다
        lines = coverage.read_doc(doc).splitlines()
        row = {"ok": True, "when": time.time(), "key": coverage.doc_key(doc),
               "seen": [coverage.line_key(lines[-1])]}
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.assertNotIn('"deny"', self.publish(doc), "기준 판의 줄을 판정 안 된 줄로 셌습니다")
        self.write(DOC + ["- **갱신 주기**: 반기"], doc)
        out = self.publish(doc)
        self.assertIn('"deny"', out)
        self.assertIn("--since main", out, "기준 커밋이 같은 판정 명령을 알려야 합니다")

    def test_an_old_judgment_of_unchanged_lines_still_counts(self) -> None:
        """판정 기록에 기한을 걸면 안 바뀐 문서를 14일마다 통째로 다시 판정해야 한다 — 배포 게이트와 같다."""
        lines = coverage.read_doc(self.doc).splitlines()
        old = {"ok": True, "when": time.time() - 20 * 86400, "key": coverage.doc_key(self.doc),
               "seen": coverage.seen_keys(lines)}
        # 오늘 새 줄 하나를 더하고 그 줄만 판정 — 나머지 줄은 20일 전 판정 그대로
        self.write(DOC + ["- **갱신 주기**: 분기"])
        new_line = coverage.read_doc(self.doc).splitlines()[-1]
        recent = {"ok": True, "when": time.time(), "key": coverage.doc_key(self.doc),
                  "seen": [coverage.line_key(new_line)]}
        with self.log.open("a", encoding="utf-8") as f:
            for row in (old, recent):
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        out = self.publish()
        self.assertNotIn('"deny"', out, f"20일 전 판정을 무시하고 안 바뀐 줄을 막았습니다:\n{out[:400]}")

    def test_a_broken_config_does_not_crash_the_gate(self) -> None:
        """⛔ 설정을 못 읽으면 문자열이 온다 — 사전으로 다루면 게이트가 오류로 죽어 모든 발행이 막힌다."""
        repo = self.dir / "broken"
        repo.mkdir()
        (repo / "korean-qa.toml").write_text("[publish\nbase = ", encoding="utf-8")
        doc = repo / "a.md"
        self.write(DOC, doc)
        git(repo, "init", "-b", "main")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "base")
        out = self.publish(doc)
        # 판정을 안 받은 문서라 막히는 것은 맞다 — 게이트가 오류로 죽어 막힌 것이면 안 된다
        self.assertNotIn("오류로 판정하지 못했습니다", out, f"설정이 깨지자 게이트가 오류로 죽었습니다:\n{out[:400]}")
        self.assertIn("판정기가 아직 안 본", out)
        self.judged(doc)
        self.assertNotIn('"deny"', self.publish(doc), "판정한 뒤에도 깨진 설정 때문에 막았습니다")

    def test_force_is_the_visible_way_out(self) -> None:
        self.judged()
        self.edit()
        cmd = f'KOREAN_PUBLISH_FORCE=1 python notion.py create "{self.doc}"'
        self.assertNotIn('"deny"', self.publish(command=cmd))


if __name__ == "__main__":
    unittest.main()
