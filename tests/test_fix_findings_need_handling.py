"""판정기가 낸 **고칠 지적도 처리 기록이 있어야 나가는지** 본다 — 모델은 안 부른다.

(2026-10-12) 전에는 고칠 지적이 남아도 발행이 됐다. 고리 재현 시험(사용 안내 · README)에서
갈래별 자동 전환 5건과 근거에 「확인 필요」를 적은 고칠 지적 10건이 그 틈으로 사용자에게 안 갔다.

**지키는 것**

- 고칠 지적이 판정 기록에 줄 해시 · 그때 줄 글과 함께 남나
- 짚은 표현을 고치면 닫히고, 같은 줄의 다른 낱말만 바꿔서는 안 닫히나
- 판정기가 강조 표시를 빼고 옮긴 표현도 그 줄에서 찾나 — 못 찾고 닫으면 안 고친 지적이 사라진다
- 받지 않음은 정해진 사유 · 근거가 있어야 받고, 지적 하나에만 듣고, 그 줄이 바뀌면 다시 열리나
- 사실 확인이 걸린 지적은 자료를 적은 「확인함」이나 사람 확인으로만 닫히나
- 사람 확인으로 올리면 고칠 지적은 닫히고 사람 확인이 열리나 · 사용자 답으로 닫히나
- 발행 직전 · push 직전 검사가 처리 안 된 고칠 지적을 막고, 처리하면 열리나 · 넘기는 길이 있나
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

coverage.DECISIONS = Path(tempfile.mkdtemp()) / "decisions.jsonl"
from test_judge_layer2 import FakeBackend  # noqa: E402

GATE = ROOT / "hooks" / "doc-style-gate.py"

DOC = ("# 소개\n\n"
       "업무 목록은 매일 갱신됩니다.\n\n"
       "일주일이 지나면 작업 내용의 기억이 흐려집니다.\n\n"
       "마감이 가까운 업무를 맨 위에 표시합니다.\n")
FIX = {"line": 7, "phrase": "맨 위에 표시합니다", "category": "군더더기 지우기",
       "fix": "맨 위에 둡니다", "why": "시험", "decide": "fix"}
FACT = {"line": 3, "phrase": "매일 갱신됩니다", "category": "계획과 결과 구분하기",
        "fix": "매일 오전에 갱신됩니다", "why": "갱신 시각은 원문에서 확인 필요", "decide": "fix"}
SECOND = {"line": 7, "phrase": "마감이 가까운", "category": "판단어의 기준 누락",
          "fix": "마감이 사흘 안인", "why": "기준이 없음", "decide": "fix"}


class _Base(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DISMISSALS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS = self.dir / "answers.jsonl"
        coverage.DISMISSALS = self.dir / "dismissals.jsonl"
        self.doc = self.dir / "d.md"
        self.doc.write_text(DOC, encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DISMISSALS = self.saved
        self.tmp.cleanup()

    def run_main(self, argv, backend=None) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main(argv, backend=backend)
        return rc, out.getvalue()

    def judged(self, *items) -> str:
        rc, out = self.run_main([str(self.doc)], backend=FakeBackend(list(items) or [FIX]).pair())
        self.assertEqual(0, rc, out)
        return out

    def open_fixes(self) -> list[int]:
        lines = coverage.read_doc(self.doc).splitlines()
        return [n for n, _ in coverage.open_fixes(coverage.doc_key(self.doc), lines, judge.LOG)]

    def open_asks(self) -> list[int]:
        lines = coverage.read_doc(self.doc).splitlines()
        return [n for n, _ in coverage.open_asks(coverage.doc_key(self.doc), lines, judge.LOG)]


class RecordTests(_Base):

    def test_a_fix_is_logged_with_its_line_and_text(self) -> None:
        self.judged()
        row = json.loads(judge.LOG.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(1, len(row["fixes"]))
        fx = row["fixes"][0]
        self.assertEqual("마감이 가까운 업무를 맨 위에 표시합니다.", fx["text"],
                         "그때 줄 글이 없으면 고친 줄을 그 줄의 자손으로 못 찾습니다")
        self.assertEqual(coverage.line_key(fx["text"]), fx["line_key"])
        self.assertTrue(row.get("rules"), "규칙 글의 판이 기록에 없습니다")

    def test_the_report_says_how_to_close_a_fix(self) -> None:
        out = self.judged()
        self.assertIn("--dismiss", out)
        self.assertIn("--escalate", out)

    def test_a_fact_fix_is_marked(self) -> None:
        out = self.judged(FACT)
        self.assertIn("[사실 확인]", out)


class OpenTests(_Base):

    def test_fixing_the_phrase_closes_it(self) -> None:
        self.judged()
        self.assertEqual([7], self.open_fixes())
        self.doc.write_text(DOC.replace("맨 위에 표시합니다", "맨 위에 둡니다"), encoding="utf-8")
        self.assertEqual([], self.open_fixes())

    def test_touching_the_line_but_keeping_the_phrase_keeps_it(self) -> None:
        self.judged()
        self.doc.write_text(DOC.replace("마감이 가까운", "마감이 사흘 안인"), encoding="utf-8")
        self.assertEqual([7], self.open_fixes(), "짚은 표현이 남았는데 줄만 바뀌었다고 지적이 닫혔습니다")

    def test_the_phrase_is_found_through_emphasis(self) -> None:
        # 2026-10-12 고리 시험 — 판정기가 「**지우지 않고**」를 「지우지 않고」로 옮겨 적었다
        self.doc.write_text(DOC.replace("맨 위에 표시합니다", "맨 위에 **표시합니다**"), encoding="utf-8")
        self.judged()
        self.doc.write_text(DOC.replace("마감이 가까운", "마감이 곧 오는").replace(
            "맨 위에 표시합니다", "맨 위에 **표시합니다**"), encoding="utf-8")
        self.assertEqual([7], self.open_fixes(), "강조 표시 때문에 표현을 못 찾아 지적을 닫았습니다")

    def test_an_unchanged_line_stays_open_even_if_the_phrase_was_misquoted(self) -> None:
        self.judged(dict(FIX, phrase="맨위에표시"))
        self.assertEqual([7], self.open_fixes(), "표현이 글자로 안 맞는다고 아무도 안 고친 지적을 닫았습니다")

    def test_the_same_phrase_on_an_unrelated_line_does_not_keep_it_open(self) -> None:
        self.doc.write_text(DOC + "\n별도 절에서도 맨 위에 표시합니다 — 다른 문장입니다.\n", encoding="utf-8")
        self.judged()
        self.doc.write_text((DOC + "\n별도 절에서도 맨 위에 표시합니다 — 다른 문장입니다.\n").replace(
            "업무를 맨 위에 표시합니다.", "업무를 맨 위에 둡니다."), encoding="utf-8")
        self.assertEqual([], self.open_fixes(), "같은 표현이 다른 문장에 있다고 고친 지적을 다시 열었습니다")

    def test_the_fixes_command_reports_open_ones(self) -> None:
        self.judged()
        rc, out = self.run_main([str(self.doc), "--fixes"])
        self.assertEqual(1, rc, out)
        self.assertIn("맨 위에 표시합니다", out)


class DismissTests(_Base):

    def dismiss(self, *extra) -> tuple[int, str]:
        return self.run_main([str(self.doc), "--dismiss", "7", *extra])

    def test_a_reason_and_a_note_close_one_fix(self) -> None:
        self.judged()
        rc, out = self.dismiss("--reason", "대상아님", "--note", "제목 줄의 정해진 문구라 규칙의 적용 대상이 아님")
        self.assertEqual(0, rc, out)
        self.assertEqual([], self.open_fixes())

    def test_no_reason_or_a_short_note_is_refused(self) -> None:
        self.judged()
        self.assertEqual(2, self.dismiss("--note", "제목 줄의 정해진 문구라 대상 아님")[0])
        self.assertEqual(2, self.dismiss("--reason", "대상아님", "--note", "번거로움")[0])
        self.assertEqual([7], self.open_fixes())

    def test_two_fixes_on_a_line_need_a_phrase(self) -> None:
        self.judged(FIX, SECOND)
        rc, out = self.dismiss("--reason", "대상아님", "--note", "제목 줄의 정해진 문구라 대상 아님")
        self.assertEqual(2, rc, "어느 지적인지 안 고르고 한 줄의 지적을 한꺼번에 닫았습니다")
        rc, out = self.dismiss("--reason", "대상아님", "--note", "제목 줄의 정해진 문구라 대상 아님",
                               "--phrase", "마감이 가까운")
        self.assertEqual(0, rc, out)
        lines = coverage.read_doc(self.doc).splitlines()
        left = coverage.open_fixes(coverage.doc_key(self.doc), lines, judge.LOG)
        self.assertEqual(["맨 위에 표시합니다"], [fx["phrase"] for _, fx in left], "지적 하나에만 들어야 합니다")

    def test_a_dismissal_reopens_when_the_line_changes(self) -> None:
        self.judged()
        self.dismiss("--reason", "대상아님", "--note", "제목 줄의 정해진 문구라 대상 아님")
        self.doc.write_text(DOC.replace("마감이 가까운", "마감이 곧 오는"), encoding="utf-8")
        self.assertEqual([7], self.open_fixes(), "줄이 바뀌었는데 예전 근거로 닫힌 채 남았습니다")

    def test_satisfied_needs_a_line_reference(self) -> None:
        self.judged()
        self.assertEqual(2, self.dismiss("--reason", "충족", "--note", "앞 문단에서 이미 충족하고 있음")[0])
        self.assertEqual(0, self.dismiss("--reason", "충족", "--note", "3행에서 이미 같은 내용을 밝힘")[0])


class FactTests(_Base):

    def setUp(self) -> None:
        super().setUp()
        self.judged(FACT)
        # 「확인함」 근거로 적는 자료 — 근거의 파일은 실제로 있어야 받는다(2026-10-13)
        (self.dir / "scheduler").mkdir()
        (self.dir / "scheduler" / "cron.toml").write_text(
            '[update]\nschedule = "매일 06:00"\nrun = "월요일 실행"\n', encoding="utf-8")

    def test_evidence_files_must_exist(self) -> None:
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "확인함",
                                 "--note", "scheduler/no-such.toml 의 갱신 시각 설정으로 확인"])
        self.assertEqual(2, rc, "없는 파일을 근거로 받았습니다")
        self.assertIn("근거의 파일이 없습니다", out)
        self.assertEqual([3], self.open_fixes())

    def test_a_quote_after_a_path_must_be_in_that_file(self) -> None:
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "확인함",
                                 "--note", "scheduler/cron.toml 「schedule = \"매주 금요일\"」 로 확인"])
        self.assertEqual(2, rc, "그 파일에 없는 인용을 근거로 받았습니다")
        self.assertIn("글자 그대로 없습니다", out)
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "확인함",
                                 "--note", "scheduler/cron.toml 「schedule = \"매일 06:00\"」 로 확인"])
        self.assertEqual(0, rc, out)

    def test_a_quote_without_a_file_is_not_checked(self) -> None:
        """대화로 받은 지시처럼 대조할 파일이 없는 인용은 받는다 — 막으면 정당한 처리 기록이 막힌다."""
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "확인함",
                                 "--note", "운영 담당 10/13 「매일 갱신 맞음」 · scheduler/cron.toml 로 확인"])
        self.assertEqual(0, rc, out)

    def test_a_line_reference_must_be_in_the_document(self) -> None:
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "확인함",
                                 "--note", "scheduler/cron.toml 과 99행으로 확인"])
        self.assertEqual(2, rc)
        self.assertIn("없는 줄입니다", out)

    def test_a_fact_fix_cannot_be_waved_off(self) -> None:
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "대상아님",
                                 "--note", "아마 맞을 것이므로 대상이 아님"])
        self.assertEqual(2, rc, "사실 확인이 걸린 지적을 자료 없이 닫았습니다")
        self.assertIn("--escalate", out)
        self.assertEqual([3], self.open_fixes())

    def test_checked_needs_evidence(self) -> None:
        rc, _ = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "확인함",
                               "--note", "담당자에게 들은 바로는 맞음"])
        self.assertEqual(2, rc, "자료 없는 「확인함」을 받았습니다")
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "확인함",
                                 "--note", "scheduler/cron.toml 의 갱신 시각 설정으로 확인"])
        self.assertEqual(0, rc, out)
        self.assertEqual([], self.open_fixes())

    def test_escalation_moves_it_to_a_person(self) -> None:
        rc, out = self.run_main([str(self.doc), "--escalate", "3", "--note", "갱신 시각은 운영 담당자만 압니다"])
        self.assertEqual(0, rc, out)
        self.assertEqual([], self.open_fixes())
        self.assertEqual([3], self.open_asks(), "올린 지적이 사람 확인으로 안 열렸습니다")
        rc, out = self.run_main([str(self.doc), "--answer", "3", "--note", "사용자: 그대로 — 매일 맞음"])
        self.assertEqual(0, rc, out)
        self.assertEqual([], self.open_asks())

    def test_editing_a_fact_does_not_close_it(self) -> None:
        # ⛔ 확인 없이 다른 수치로 바꿔도 표현은 사라진다 — 고친 줄에 붙어 확인을 기다린다
        self.doc.write_text(DOC.replace("매일 갱신됩니다", "매주 월요일에 갱신됩니다"), encoding="utf-8")
        self.assertEqual([3], self.open_fixes(), "사실 확인 지적이 확인 없이 고친 것만으로 닫혔습니다")
        rc, out = self.run_main([str(self.doc), "--dismiss", "3", "--reason", "확인함",
                                 "--note", "scheduler/cron.toml 의 월요일 실행 설정으로 확인"])
        self.assertEqual(0, rc, out)
        self.assertEqual([], self.open_fixes())

    def test_deleting_the_claim_closes_it(self) -> None:
        self.doc.write_text(DOC.replace("업무 목록은 매일 갱신됩니다.\n\n", ""), encoding="utf-8")
        self.assertEqual([], self.open_fixes(), "확인 안 된 주장을 지웠는데 지적이 엉뚱한 줄에 붙었습니다")

    def test_a_deleted_claim_does_not_stick_to_a_lookalike_line(self) -> None:
        """(2026-10-13 게이트 부정 시험) 주장 줄을 지우자 사실 확인 지적이 글자가 비슷할 뿐인
        다른 줄(유사도 0.588)에 붙었다 — 판정 때와 지금의 줄 순서를 맞대어 바뀐 자리 안에서만 찾는다."""
        lookalike = "업무 일지는 매주 오전 열 시에 갱신됩니다."
        self.assertGreaterEqual(coverage._similar(lookalike, "업무 목록은 매일 갱신됩니다."), coverage.SUCCESSOR,
                                "시험 문장이 옛 기준을 넘지 않아 이 시험이 아무것도 못 지킵니다")
        self.doc.write_text(DOC.replace("업무 목록은 매일 갱신됩니다.\n\n", "")
                            + "\n" + lookalike + "\n", encoding="utf-8")
        self.assertEqual([], self.open_fixes(), "지운 주장의 지적이 다른 줄에 붙었습니다")

    def test_a_split_claim_keeps_the_check(self) -> None:
        self.doc.write_text(DOC.replace("업무 목록은 매일 갱신됩니다.",
                                        "업무 목록은 매일 아침에 바뀝니다.\n\n바뀐 목록은 메일로도 보냅니다."),
                            encoding="utf-8")
        self.assertEqual([3], self.open_fixes(), "주장 줄을 나누자 사실 확인 지적이 확인 없이 닫혔습니다")

    def test_the_prompt_asks_for_the_fact_to_check(self) -> None:
        import probe_layer2_kinds as probe
        self.assertIn('"check"', probe.SYSTEM)
        self.assertIn("`check` 에 확인할 사실을 적는다", probe.SYSTEM)

    def test_a_filled_check_marks_a_fact_without_hedging_words(self) -> None:
        self.assertTrue(coverage.needs_check({"why": "시험", "check": "실제 갱신 시각"}))
        self.assertFalse(coverage.needs_check({"why": "짧은 부정", "check": ""}))

    def test_escalation_needs_a_note(self) -> None:
        rc, _ = self.run_main([str(self.doc), "--escalate", "3"])
        self.assertEqual(2, rc)
        self.assertEqual([3], self.open_fixes())


def _fix_row(doc: Path) -> str:
    lines = coverage.read_doc(doc).splitlines()
    return json.dumps({
        "ok": True, "key": coverage.doc_key(doc), "when": time.time(), "seen": coverage.seen_keys(lines),
        "fixes": [{"line_key": coverage.line_key(lines[6]), "line": 7, "phrase": FIX["phrase"],
                   "fix": FIX["fix"], "why": FIX["why"], "text": lines[6]}],
    }, ensure_ascii=False) + "\n"


class GateTests(unittest.TestCase):
    """발행 직전 검사가 처리 안 된 고칠 지적을 막는다."""

    def setUp(self) -> None:
        # ⛔ 게이트가 Temp·scratchpad 를 건너뛰므로 거기는 안 된다
        self.dir = Path(repo_paths.gate_scratch(".fix-gate-"))
        self.doc = self.dir / "intro.md"
        self.doc.write_text(DOC, encoding="utf-8")
        self.log, self.dismissals = self.dir / "calls.jsonl", self.dir / "dismissals.jsonl"
        self.env = dict(os.environ, KOREAN_QA_JUDGE_LOG=str(self.log),
                        KOREAN_QA_ANSWER_LOG=str(self.dir / "answers.jsonl"),
                        KOREAN_QA_DISMISS_LOG=str(self.dismissals),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_CHECK_RECORD=str(self.dir / "store.jsonl"),
                        KOREAN_PUBLISH_REQUIRE="structure")
        self.log.write_text(_fix_row(self.doc), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def publish(self, prefix: str = "") -> tuple[int, str]:
        cmd = f"{prefix}python notion.py create --md {self.doc.as_posix()}".strip()
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "session_id": "fix-session", "tool_input": {"command": cmd}}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "--probe"],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=240, env=self.env)
        return gate_result.read(done)

    def test_an_open_fix_blocks(self) -> None:
        rc, out = self.publish()
        self.assertEqual(2, rc, f"처리 안 된 고칠 지적이 있는데 발행이 통과했습니다: {out[:300]}")
        self.assertIn("맨 위에 표시합니다", out)
        self.assertIn("--dismiss", out, "받지 않는 길을 안 알려 줍니다")
        self.assertIn("--escalate", out, "사람에게 올리는 길을 안 알려 줍니다")

    def test_a_dismissal_opens_it(self) -> None:
        lines = coverage.read_doc(self.doc).splitlines()
        self.dismissals.write_text(json.dumps({
            "key": coverage.doc_key(self.doc), "when": time.time(), "line_key": coverage.line_key(lines[6]),
            "phrase": FIX["phrase"], "reason": "대상아님", "note": "시험 — 정해진 문구",
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        rc, out = self.publish()
        self.assertNotIn("고칠 지적에 처리 기록이 없습니다", out)

    def test_fixing_the_phrase_opens_it(self) -> None:
        self.doc.write_text(DOC.replace("맨 위에 표시합니다", "맨 위에 둡니다"), encoding="utf-8")
        rc, out = self.publish()
        self.assertNotIn("고칠 지적에 처리 기록이 없습니다", out)

    def test_the_escape_hatch_works(self) -> None:
        rc, out = self.publish(prefix="KOREAN_PUBLISH_FORCE=1 ")
        self.assertNotIn("고칠 지적에 처리 기록이 없습니다", out)

    def test_an_old_judgment_without_fixes_does_not_block(self) -> None:
        """이 기록이 생기기 전의 판정은 고칠 지적을 안 남겼다 — 거슬러 막지 않는다."""
        self.log.write_text(json.dumps({"ok": True, "key": coverage.doc_key(self.doc),
                                        "when": time.time(), "asks": []}) + "\n", encoding="utf-8")
        rc, out = self.publish()
        self.assertNotIn("고칠 지적에 처리 기록이 없습니다", out)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                          check=True, capture_output=True, text=True, encoding="utf-8").stdout


class PushFixTests(unittest.TestCase):
    """`[publish]` 를 켠 저장소의 push 직전 게이트도 처리 안 된 고칠 지적을 막는다."""

    CONFIG = '[publish]\nrequire = ["judgment"]\ntargets = ["docs/*.md"]\nbase = "main"\n'

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.repo = t / "site"
        (self.repo / "docs").mkdir(parents=True)
        self.log, self.dismissals = t / "judge.jsonl", t / "dismissals.jsonl"
        self.env = dict(os.environ, KOREAN_CHECK_RECORD=str(t / "pass.jsonl"),
                        KOREAN_QA_JUDGE_LOG=str(self.log), KOREAN_QA_ANSWER_LOG=str(t / "answers.jsonl"),
                        KOREAN_QA_DISMISS_LOG=str(self.dismissals),
                        KOREAN_QA_RECORDER=str(ROOT / "scripts" / "check_record.py"),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_QA_JUDGE=str(ROOT / "scripts" / "judge_layer2.py"))
        (self.repo / "korean-qa.toml").write_text(self.CONFIG, encoding="utf-8")
        self.doc = self.repo / "docs" / "a.md"
        self.doc.write_text("# 소개\n\n업무 목록은 매일 갱신됩니다.\n", encoding="utf-8")
        git(self.repo, "init", "-b", "main")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "switch", "-c", "work")
        self.doc.write_text(DOC, encoding="utf-8")
        git(self.repo, "commit", "-am", "edit")
        self.log.write_text(_fix_row(self.doc), encoding="utf-8")
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "check_record.py"), "record",
                        str(self.doc), "--stage", "judgment", "--verdict", "pass", "--note", "시험"],
                       check=True, capture_output=True, env=self.env)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def push(self) -> tuple[int, str]:
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "push-fix",
                   "cwd": str(self.repo), "tool_input": {"command": "git push -u origin HEAD"}}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "--probe"],
                              input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120, env=self.env)
        return gate_result.read(done)

    def test_an_open_fix_blocks_the_push(self) -> None:
        rc, out = self.push()
        self.assertEqual(2, rc, out)
        self.assertIn("고칠 지적 1개", out)

    def test_a_dismissal_lets_the_push_through(self) -> None:
        lines = coverage.read_doc(self.doc).splitlines()
        self.dismissals.write_text(json.dumps({
            "key": coverage.doc_key(self.doc), "when": time.time(), "line_key": coverage.line_key(lines[6]),
            "phrase": FIX["phrase"], "reason": "대상아님", "note": "시험 — 정해진 문구",
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        rc, out = self.push()
        self.assertEqual(0, rc, out)

    def dismissal_in(self, doc: Path) -> None:
        lines = coverage.read_doc(doc).splitlines()
        with self.dismissals.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "key": coverage.doc_key(doc), "when": time.time(), "line_key": coverage.line_key(lines[6]),
                "phrase": FIX["phrase"], "reason": "대상아님", "note": "다른 저장소의 화면 문구",
            }, ensure_ascii=False) + "\n")

    def test_a_dismissal_in_another_repo_does_not_open_it(self) -> None:
        """(2026-10-13 게이트 부정 시험) 열쇠가 뿌리 기준 경로뿐이라 다른 저장소의 같은 이름
        문서에 남긴 처리 기록이 이 저장소의 같은 글줄 지적을 닫았다."""
        other = Path(self.tmp.name) / "other"
        (other / "docs").mkdir(parents=True)
        (other / "docs" / "a.md").write_text(DOC, encoding="utf-8")
        git(other, "init", "-b", "main")
        self.assertNotEqual(coverage.doc_key(other / "docs" / "a.md"), coverage.doc_key(self.doc))
        self.dismissal_in(other / "docs" / "a.md")
        rc, out = self.push()
        self.assertEqual(2, rc, "다른 저장소의 처리 기록으로 이 저장소의 지적이 닫혔습니다")

    def test_a_worktree_shares_the_key(self) -> None:
        """작업 트리에서 판정 · 처리하고 기본 checkout 에서 밀어도 같은 문서로 읽힌다."""
        wt = Path(self.tmp.name) / "wt"
        git(self.repo, "worktree", "add", "-q", str(wt), "-b", "wt-branch")
        self.assertEqual(coverage.doc_key(self.doc), coverage.doc_key(wt / "docs" / "a.md"))
        self.dismissal_in(wt / "docs" / "a.md")
        self.assertEqual(0, self.push()[0])

    def test_records_without_a_repo_id_still_count(self) -> None:
        """열쇠에 저장소 식별자를 넣기 전 기록 — 버리면 같은 줄을 다시 판정하고 다시 닫아야 한다."""
        lines = coverage.read_doc(self.doc).splitlines()
        legacy = coverage.doc_key(self.doc).split(coverage.KEY_SEP)[0]
        self.log.write_text(_fix_row(self.doc).replace(coverage.doc_key(self.doc), legacy), encoding="utf-8")
        self.dismissals.write_text(json.dumps({
            "key": legacy, "when": time.time(), "line_key": coverage.line_key(lines[6]),
            "phrase": FIX["phrase"], "reason": "대상아님", "note": "시험 — 정해진 문구",
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(0, self.push()[0], "옛 열쇠의 판정 · 처리 기록을 못 읽었습니다")


if __name__ == "__main__":
    unittest.main()
