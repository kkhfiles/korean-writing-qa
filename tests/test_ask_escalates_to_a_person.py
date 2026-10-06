"""판정기가 정하지 못한 지적이 **사람에게 올라가고, 답을 받기 전에는 안 나가는지** 본다 — 모델은 안 부른다.

(2026-10-06 사용자 — 「궁극적으로는 규칙으로 잡고 llm 판단으로 잡고, 그래도 애매하면
사람한테 애스컬레이션하는 것이다」) 그 전에는 판정 값이 통과 · 실패뿐이라, 사람 몫인
지적도 세션이 까닭을 적고 스스로 통과시켰다.

**지키는 것**

- 판정 프롬프트가 `decide` 칸(fix · ask)을 요구하나
- `ask` 지적이 판정 기록에 줄 해시와 함께 남나
- 답은 **줄에 묶이나** — 다른 줄을 고쳐도 받은 답이 살아 있고, 짚은 표현을 고치면 지적이 사라지나
- 같은 줄의 다른 낱말만 바꿔서는 지적이 안 사라지나 — 묻지 않고 지우는 길
- 답 기록에 까닭이 없으면 거절하나
- 답을 못 받은 지적이 남은 문서는 발행 직전 검사가 막고, 답하거나 고치면 열리나
- 넘기는 길(`KOREAN_PUBLISH_FORCE=1`)이 있나 — 열쇠 없는 자물쇠를 만들지 않는다
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
import probe_layer2_kinds as probe  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402

GATE = ROOT / "hooks" / "doc-style-gate.py"

DOC = ("# 소개\n\n"
       "업무 목록은 매일 갱신됩니다.\n\n"
       "일주일이 지나면 작업 내용의 기억이 흐려집니다.\n\n"
       "마감이 가까운 업무를 맨 위에 표시합니다.\n")
ASK = {"line": 5, "phrase": "기억이 흐려집니다", "category": "업무에서 쓰는 말로 쓰기",
       "fix": "정확히 기억하기 어렵습니다", "why": "문맥에 따라 정상일 수 있음", "decide": "ask"}
FIX = {"line": 7, "phrase": "맨 위에 표시합니다", "category": "군더더기 지우기",
       "fix": "맨 위에 둡니다", "why": "시험", "decide": "fix"}


class PromptTests(unittest.TestCase):

    def test_the_prompt_asks_for_a_decision(self) -> None:
        self.assertIn('"decide"', probe.SYSTEM)
        self.assertIn('"ask"', probe.SYSTEM)
        self.assertIn("빼지 않는다", probe.SYSTEM,
                      "확신이 없다고 지적을 빼면 사람에게 올라갈 것이 조용히 사라집니다")


class AskRecordTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS = self.dir / "answers.jsonl"
        self.doc = self.dir / "d.md"
        self.doc.write_text(DOC, encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS = self.saved
        self.tmp.cleanup()

    def run_main(self, argv, backend=None) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main(argv, backend=backend)
        return rc, out.getvalue()

    def judged(self) -> str:
        rc, out = self.run_main([str(self.doc)], backend=FakeBackend([ASK, FIX]).pair())
        self.assertEqual(0, rc, out)
        return out

    def open_asks(self) -> list:
        lines = coverage.read_doc(self.doc).splitlines()
        return coverage.open_asks(coverage.doc_key(self.doc), lines, judge.LOG)

    def test_an_ask_is_logged_with_its_line(self) -> None:
        self.judged()
        row = json.loads(judge.LOG.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(1, len(row["asks"]), "fix 지적까지 사람 확인으로 남았거나 ask 가 빠졌습니다")
        self.assertEqual(coverage.line_key("일주일이 지나면 작업 내용의 기억이 흐려집니다."),
                         row["asks"][0]["line_key"])

    def test_the_report_puts_asks_apart(self) -> None:
        out = self.judged()
        self.assertIn("사람 확인", out)
        self.assertIn("--answer", out, "답을 적는 길을 안 알려 줍니다")
        self.assertLess(out.index("기억이 흐려집니다"), out.index("맨 위에 표시합니다"),
                        "사람 확인 지적이 고칠 지적 뒤에 묻힙니다")

    def test_an_answer_closes_the_ask(self) -> None:
        self.judged()
        self.assertEqual(1, len(self.open_asks()))
        rc, out = self.run_main([str(self.doc), "--asks"])
        self.assertEqual(1, rc, "답을 기다리는 지적이 남았는데 --asks 가 0 을 냈습니다")
        rc, out = self.run_main([str(self.doc), "--answer", "5", "--note", "사용자: 그대로 둠"])
        self.assertEqual(0, rc, out)
        self.assertEqual([], self.open_asks())
        rc, _ = self.run_main([str(self.doc), "--asks"])
        self.assertEqual(0, rc)

    def test_an_answer_needs_a_note(self) -> None:
        self.judged()
        rc, out = self.run_main([str(self.doc), "--answer", "5"])
        self.assertEqual(2, rc, "까닭 없는 답을 받았습니다")
        self.assertEqual(1, len(self.open_asks()))

    def test_an_answer_must_point_at_a_korean_line(self) -> None:
        rc, out = self.run_main([str(self.doc), "--answer", "2", "--note", "사용자: 그대로"])
        self.assertEqual(2, rc, "빈 줄에 답을 적었습니다")

    def test_editing_another_line_keeps_the_answer(self) -> None:
        """답은 문서가 아니라 줄에 묶인다 — 한 번 물은 것을 또 묻지 않는다."""
        self.judged()
        self.run_main([str(self.doc), "--answer", "5", "--note", "사용자: 그대로 둠"])
        self.doc.write_text(DOC.replace("매일 갱신됩니다", "매일 오전에 갱신됩니다"), encoding="utf-8")
        self.assertEqual([], self.open_asks(), "다른 줄을 고쳤는데 받은 답이 사라졌습니다")

    def test_fixing_the_phrase_drops_the_ask(self) -> None:
        """짚은 표현을 고치면 그 지적은 사라진다 — 고친 것이다."""
        self.judged()
        self.doc.write_text(DOC.replace("작업 내용의 기억이 흐려집니다",
                                        "작업 내용을 정확히 기억하기 어렵습니다"), encoding="utf-8")
        self.assertEqual([], self.open_asks())

    def test_touching_the_line_but_keeping_the_phrase_keeps_the_ask(self) -> None:
        """⛔ 같은 줄의 다른 낱말만 바꿔 묻지 않고 지적을 지우는 길을 막는다."""
        self.judged()
        self.doc.write_text(DOC.replace("일주일이 지나면", "열흘이 지나면"), encoding="utf-8")
        self.assertEqual([5], [n for n, _ in self.open_asks()],
                         "짚은 표현이 그대로인데 줄만 바뀌었다고 지적이 사라졌습니다")

    def test_an_ask_without_a_line_follows_its_phrase(self) -> None:
        stray = dict(ASK, line=None)
        judge.LOG.write_text(json.dumps({
            "ok": True, "key": coverage.doc_key(self.doc), "when": time.time(),
            "asks": [{"line_key": None, "phrase": stray["phrase"], "fix": stray["fix"]}],
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        left = self.open_asks()
        self.assertEqual([5], [n for n, _ in left], "줄 해시 없는 지적을 표현으로 못 찾았습니다")

    def test_old_asks_expire(self) -> None:
        judge.LOG.write_text(json.dumps({
            "ok": True, "key": coverage.doc_key(self.doc),
            "when": time.time() - (coverage.FRESH_DAYS + 1) * 86400,
            "asks": [{"line_key": coverage.line_key("일주일이 지나면 작업 내용의 기억이 흐려집니다."),
                      "phrase": ASK["phrase"]}],
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual([], self.open_asks())


class GateTests(unittest.TestCase):
    """발행 직전 검사가 답을 못 받은 지적을 막는다."""

    def setUp(self) -> None:
        # ⛔ 게이트가 Temp·scratchpad 를 건너뛰므로 거기는 안 된다
        self.dir = Path(repo_paths.gate_scratch(".ask-gate-"))
        self.doc = self.dir / "intro.md"
        self.doc.write_text(DOC, encoding="utf-8")
        self.log = self.dir / "calls.jsonl"
        self.answers = self.dir / "answers.jsonl"
        self.env = dict(os.environ, KOREAN_QA_JUDGE_LOG=str(self.log),
                        KOREAN_QA_ANSWER_LOG=str(self.answers),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_CHECK_RECORD=str(self.dir / "store.jsonl"),
                        KOREAN_PUBLISH_REQUIRE="structure")
        self.log.write_text(json.dumps({
            "ok": True, "key": coverage.doc_key(self.doc), "when": time.time(),
            "asks": [{"line_key": coverage.line_key("일주일이 지나면 작업 내용의 기억이 흐려집니다."),
                      "phrase": ASK["phrase"], "fix": ASK["fix"], "why": ASK["why"]}],
        }, ensure_ascii=False) + "\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def publish(self, prefix: str = "") -> tuple[int, str]:
        cmd = f"{prefix}python notion.py create --md {self.doc.as_posix()}".strip()
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "session_id": "ask-session", "tool_input": {"command": cmd}}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "--probe"],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=240, env=self.env)
        return gate_result.read(done)

    def test_an_open_ask_blocks(self) -> None:
        rc, out = self.publish()
        self.assertEqual(2, rc, f"답을 못 받은 지적이 있는데 발행이 통과했습니다: {out[:300]}")
        self.assertIn("기억이 흐려집니다", out)
        self.assertIn("--answer", out, "푸는 길을 안 알려 줍니다")

    def test_an_answer_opens_it(self) -> None:
        lines = coverage.read_doc(self.doc).splitlines()
        self.answers.write_text(json.dumps({
            "key": coverage.doc_key(self.doc), "when": time.time(),
            "line_key": coverage.line_key(lines[4]), "note": "사용자: 그대로 둠",
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        rc, out = self.publish()
        self.assertNotIn("사용자 답이 없습니다", out)

    def test_fixing_the_line_opens_it(self) -> None:
        self.doc.write_text(DOC.replace("작업 내용의 기억이 흐려집니다",
                                        "작업 내용을 정확히 기억하기 어렵습니다"), encoding="utf-8")
        rc, out = self.publish()
        self.assertNotIn("사용자 답이 없습니다", out)

    def test_the_escape_hatch_works(self) -> None:
        rc, out = self.publish(prefix="KOREAN_PUBLISH_FORCE=1 ")
        self.assertNotIn("사용자 답이 없습니다", out)


if __name__ == "__main__":
    unittest.main()
