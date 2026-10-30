"""원본을 선언한 문서에서 **원본과 같은 줄(남이 쓴 줄)은 막지 않고, 고친 줄은 그대로 보는지** 본다.

(2026-10-30 사용자 결정 — 「내가 스스로 사용하는 한국어 검사기 기준을 다른 사람에게 강요할 순 없다」)
남의 초안을 고쳐 내보내면 발행 게이트가 남의 줄까지 판정하고 오류 0 을 요구해, 남의 글을 고치거나
게이트를 넘기는 길밖에 없었다(시험 실행에서 다섯 줄 전부 판정 요구 · 쓰기 훅도 남의 반말 줄을 오류로 냄).

**지키는 것**
- 머리말 `origin:`(마크다운)과 `<meta name="origin">`(HTML)을 읽나 · 선언이 없으면 지금처럼 문서 전체
- 판정기가 원본과 다른 줄만 판정 대상으로 고르나
- 쓰기 훅이 원본 줄의 1층 지적을 빼고 고친 줄의 지적은 남기나
- 발행 게이트가 고친 줄만 판정을 요구하고 `--since @origin` 을 권하나
- 선언한 원본 파일이 없으면 그 사실을 알리고 문서 전체를 보나
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))

import repo_paths  # noqa: E402
import gate_result  # noqa: E402
import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402

GATE = ROOT / "hooks" / "doc-style-gate.py"

ORIGINAL = ("# 하반기 검증 계획\n\n"
            "**목표** — 회귀 시험 자동화\n\n"
            "- **담당**: 품질팀\n"
            "- **일정**: 11월 말까지 1차 적용한다.\n"
            "- **위험**: 시험 환경 확보\n")
HEAD = "---\norigin: original.md\n---\n\n"
#: 원본의 마지막 줄만 고쳤다 — 고친 줄에도 반말이 있다(사용자가 쓴 줄이니 잡혀야 한다)
EDITED = HEAD + ORIGINAL.replace("- **위험**: 시험 환경 확보\n", "- **위험**: 시험 환경 확보가 늦어질 수 있다.\n")


class _Base(unittest.TestCase):

    def setUp(self) -> None:
        # ⛔ 게이트가 Temp·scratchpad 를 건너뛰므로 거기는 안 된다
        self.dir = Path(repo_paths.gate_scratch(".origin-gate-"))
        (self.dir / "original.md").write_text(ORIGINAL, encoding="utf-8")
        self.doc = self.dir / "edited.md"
        self.doc.write_text(EDITED, encoding="utf-8")
        self.log = self.dir / "calls.jsonl"
        self.env = dict(os.environ, KOREAN_QA_JUDGE_LOG=str(self.log),
                        KOREAN_QA_ANSWER_LOG=str(self.dir / "answers.jsonl"),
                        KOREAN_QA_DISMISS_LOG=str(self.dir / "dismissals.jsonl"),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_CHECK_RECORD=str(self.dir / "store.jsonl"),
                        KOREAN_QA_PUBLISH_REPOS=str(self.dir / "no-list.toml"))
        self.saved_log = judge.LOG
        judge.LOG = self.log

    def tearDown(self) -> None:
        judge.LOG = self.saved_log
        shutil.rmtree(self.dir, ignore_errors=True)

    def hook(self, payload: dict) -> tuple[int, str]:
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "--probe"],
                              input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=240, env=self.env)
        try:
            spec = json.loads(done.stdout)["hookSpecificOutput"]
            if spec.get("additionalContext"):
                return 0, spec["additionalContext"]
        except (ValueError, KeyError, TypeError):
            pass
        return gate_result.read(done)

    def written(self) -> tuple[int, str]:
        return self.hook({"hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "origin-t",
                          "tool_input": {"file_path": str(self.doc), "content": ""}})

    def published(self) -> tuple[int, str]:
        return self.hook({"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "origin-t",
                          "cwd": str(self.dir),
                          "tool_input": {"command": f"python notion.py create --md {self.doc.as_posix()}"}})


class DeclarationTests(_Base):

    def test_markdown_front_matter_names_the_origin(self) -> None:
        self.assertEqual((self.dir / "original.md").resolve(), coverage.origin_of(self.doc))

    def test_html_meta_names_the_origin(self) -> None:
        page = self.dir / "page.html"
        page.write_text('<html><head><meta name="origin" content="original.md"></head><body><p>글</p></body></html>',
                        encoding="utf-8")
        self.assertEqual((self.dir / "original.md").resolve(), coverage.origin_of(page))

    def test_no_declaration_means_the_whole_document(self) -> None:
        self.doc.write_text(ORIGINAL, encoding="utf-8")
        self.assertIsNone(coverage.origin_of(self.doc))
        self.assertIsNone(coverage.origin_base(self.doc))

    def test_origin_key_outside_the_front_matter_is_not_a_declaration(self) -> None:
        self.doc.write_text(ORIGINAL + "\norigin: original.md\n", encoding="utf-8")
        self.assertIsNone(coverage.origin_of(self.doc))

    def test_a_missing_origin_file_is_an_error_not_silence(self) -> None:
        (self.dir / "original.md").unlink()
        with self.assertRaises(ValueError):
            coverage.base_lines(self.doc, coverage.ORIGIN_REF)


class JudgeTests(_Base):

    def test_the_judge_picks_only_lines_that_differ_from_the_origin(self) -> None:
        targets, has_base = judge.open_for(self.doc, coverage.ORIGIN_REF)
        lines = coverage.read_doc(self.doc).splitlines()
        self.assertTrue(has_base)
        self.assertEqual(["- **위험**: 시험 환경 확보가 늦어질 수 있다."], [lines[n - 1] for n in targets])


class GateTests(_Base):

    def test_write_hook_drops_theirs_and_keeps_mine(self) -> None:
        _, out = self.written()
        self.assertNotIn("1차 적용한다", out, "원본(남의 줄)의 지적을 냈습니다")
        self.assertIn("늦어질 수 있다", out, "사용자가 고친 줄의 지적이 사라졌습니다")
        self.assertIn("원본(original.md)과 같은 줄의 지적 1건은 뺐다", out)

    def test_publish_asks_to_judge_only_the_changed_line(self) -> None:
        rc, out = self.published()
        self.assertEqual(2, rc, out)
        self.assertIn("판정 안 한 줄 1개", out, "남이 쓴 줄까지 판정을 요구했습니다")
        self.assertIn("--since @origin", out)

    def test_an_unchanged_copy_needs_no_judging(self) -> None:
        self.doc.write_text(HEAD + ORIGINAL, encoding="utf-8")
        _, out = self.published()
        self.assertNotIn("판정기가 아직 안 본 한글 줄", out, "고친 줄이 없는데 판정을 요구했습니다")

    def test_without_a_declaration_every_line_is_checked(self) -> None:
        """선언이 없으면 지금처럼 문서 전부 — 2026-10-13 사용자 결정 「발행하는 문서 전부」."""
        self.doc.write_text(EDITED.replace(HEAD, ""), encoding="utf-8")
        _, out = self.written()
        self.assertIn("1차 적용한다", out)
        rc, out = self.published()
        self.assertEqual(2, rc, out)
        self.assertIn("판정 안 한 줄 5개", out)

    def test_a_missing_origin_file_is_reported_and_everything_is_checked(self) -> None:
        (self.dir / "original.md").unlink()
        _, out = self.written()
        self.assertIn("원본 선언의 파일이 없어", out)
        self.assertIn("1차 적용한다", out, "원본이 없는데 줄을 뺐습니다")


if __name__ == "__main__":
    unittest.main()
