"""띄어 쓴 가운뎃점(「A · B」) 이음 — **새로 쓰거나 고친 줄만** 오류로 낸다.

**왜 있나.** 2026-10-12 · 13 이틀 연속 공유본에 「A 의 B · C 는 세지 않음」 꼴이 나갔다.
「B 와 C 를 모두 세지 않음」으로 읽힌다(원문은 사내 자료라 같은 꼴로 지어 적음). 10/12 에 전역 지시
파일 「형식」 절에 「가운뎃점은 같은 대상의 짧은 사실에만」을 적었는데 다음 날 또 나갔다 —
글 규칙으로는 안 지켜져 기계로 옮긴다.

**사용자 결정(2026-10-13)**
- 띄어 쓴 가운뎃점은 전면 금지 — 꼴만 고르는 판별은 실문서 표본 25건에서 두 갈래로 읽히는
  것 4 · 여지 8 · 아님 13 이라 주의 등급밖에 못 됐다
- 이미 발행한 문서는 고치지 않음 — 그래서 「새 줄」을 가르는 장치가 필요하다
- 붙여 쓴 「작성·수정」은 2층이 본다(`core-rules.md` 「and/or로 갈려 읽히는 나열」)

**새 줄을 가르는 법** — 공유본이 있던 폴더는 git 저장소가 아니라 git 기준으로는 못 가른다.
AI 세션이 문서를 처음 고치기 직전에 그 문서의 가운뎃점 줄을 **기존 줄 대장**에 적고(훅),
대장에 오른 문서에서 대장에 없는 줄만 오류로 낸다. 대장에 없는 문서는 건수만 알린다 —
그래서 손대지 않은 문서와 lab-docs 빌드는 멈추지 않는다.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import repo_paths  # noqa: E402

CHECKER = repo_paths.CHECKER
GATE = ROOT / "hooks" / "doc-style-gate.py"
KIND = "가운뎃점 이음"

MD_HEAD = "---\nform: structured\n---\n\n# 정책 요약\n\n**라이선스 정책** — 한 장 조망\n\n"
HTML_HEAD = '<h1>정책 요약</h1>\n<p class="lede">라이선스 정책 — 한 장 조망</p>\n'

#: 실제로 나간 문장 셋(2026-10-12 · 13)과 같은 꼴 — 원문은 사내 자료라 낱말을 바꿔 지었다.
#: 셋 다 앞 조각이 뒤 조각의 주어와 묶여 「둘 다」로 읽힌다.
INCIDENTS = (
    "집계 기준 — 운영 서버가 받은 접속 수 · 시험 서버는 세지 않음",
    "제공 방식 — 사내 서버에 설치하는 판 · 개인판은 체험용",
    "요금 — 사용자 수 · 사용 시간에는 요금을 매기지 않음",
)


def load_checker(ledger: Path):
    spec = importlib.util.spec_from_file_location("doc_style_check_middot", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MIDDOT_LEDGER = ledger
    return module


def names(items) -> list[str]:
    return [i[1] if len(i) == 3 else i[0] for i in items]


class CheckerRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="middot-"))
        self.ledger = self.dir / "ledger.tsv"
        self.checker = load_checker(self.ledger)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name: str, text: str) -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def scan(self, p: Path, form: str = "structured"):
        scan = self.checker.scan_md if p.suffix == ".md" else self.checker.scan_html
        errors, warnings, _ = scan(str(p), False, form)
        return errors, warnings

    def middot_errors(self, p: Path, form: str = "structured") -> list:
        errors, _ = self.scan(p, form)
        return [e for e in errors if names([e])[0] == KIND]

    def test_only_new_lines_of_a_tracked_doc_are_errors(self) -> None:
        """기존 줄은 그대로 두고, 대장에 오른 뒤 생긴 줄만 짚는다 — 마크다운과 HTML 둘 다."""
        cases = {
            ".md": (MD_HEAD + "- **기존** — 개발 종료 · 시험 시작\n",
                    "- **새 값** — 초안 · 최종본은 공유 폴더\n"),
            ".html": (HTML_HEAD + "<dl><div><dt>기존</dt><dd>개발 종료 · 시험 시작</dd></div>\n",
                      "<div><dt>새 값</dt><dd>초안 · 최종본은 공유 폴더</dd></div></dl>\n"),
        }
        for suffix, (old, new) in cases.items():
            with self.subTest(suffix):
                p = self.write(f"doc{suffix}", old)
                self.assertTrue(self.checker.middot_baseline(str(p)))
                p.write_text(old + new, encoding="utf-8")
                hits = self.middot_errors(p)
                self.assertEqual(1, len(hits), f"새 줄 하나만 짚어야 합니다: {hits}")
                self.assertIn("최종본은", str(hits[0]))
                self.assertNotIn("시험 시작", str(hits[0]), "기존 줄을 짚었습니다")

    def test_an_untracked_doc_is_counted_not_flagged(self) -> None:
        """손대지 않은 문서는 오류로 세지 않고 건수만 남긴다 — 기존 문서를 고치지 않는다."""
        p = self.write("old.md", MD_HEAD + "- **값** — 초안 · 최종본은 공유 폴더\n")
        before = self.checker.MIDDOT_UNTRACKED[0]
        self.assertEqual([], self.middot_errors(p))
        self.assertEqual(before + 1, self.checker.MIDDOT_UNTRACKED[0])

    def test_a_brand_new_doc_flags_every_dot_line(self) -> None:
        """없는 파일을 대장에 올리면 기존 줄이 없다 — 새로 쓴 가운뎃점 줄은 모두 짚는다."""
        p = self.dir / "new.md"
        self.checker.middot_baseline(str(p))
        p.write_text(MD_HEAD + "- **가** — 하나 · 둘\n- **나** — 셋 · 넷\n", encoding="utf-8")
        self.assertEqual(2, len(self.middot_errors(p)))

    def test_the_baseline_is_taken_once(self) -> None:
        """⛔ 두 번째 기록이 그 사이 쓴 새 줄을 기존 줄로 덮으면 안 된다."""
        p = self.write("once.md", MD_HEAD + "- **가** — 하나\n")
        self.assertTrue(self.checker.middot_baseline(str(p)))
        p.write_text(MD_HEAD + "- **가** — 하나 · 둘은 따로\n", encoding="utf-8")
        self.assertFalse(self.checker.middot_baseline(str(p)), "이미 오른 문서를 다시 적었습니다")
        self.assertEqual(1, len(self.middot_errors(p)))

    def test_touching_a_legacy_line_makes_it_new(self) -> None:
        """기존 줄이라도 손대면 그 줄은 새 줄이다 — 고친 줄은 규칙을 따른다."""
        p = self.write("touch.md", MD_HEAD + "- **가** — 개발 종료 · 시험 시작\n")
        self.checker.middot_baseline(str(p))
        p.write_text(MD_HEAD + "- **가** — 개발 종료 · 시험 착수\n", encoding="utf-8")
        self.assertEqual(1, len(self.middot_errors(p)))

    def test_quotes_code_examples_and_tight_dots_are_spared(self) -> None:
        """인용 · 코드 · 대조 예시 · 출처 있는 원문 · 붙여 쓴 가운뎃점은 짚지 않는다."""
        p = self.dir / "spared.md"
        self.checker.middot_baseline(str(p))
        body = (MD_HEAD
                + "- **원문** — 「A · B」 그대로 인용\n"
                + "- **명령** — `합계 — 오류 0 · 주의 0` 출력\n"
                + "- ❌ 「접속 수 · 시험 서버는 세지 않음」 → ✅ 「운영 서버 접속 수만 셈」\n"
                # 인용 없이 쓴 대조 예시 — 인용 가림이 아니라 예시 제외가 빼야 한다(돌연변이로 찾음)
                + "- ❌ 접속 수 · 시험 서버는 세지 않음 → ✅ 운영 서버 접속 수만 셈\n"
                + "- **붙여 씀** — 개발·운영 담당\n"
                + "> 이 표현은 A · B 로 둔다 (10/13 회의)\n"
                + "```\n하나 · 둘\n```\n")
        p.write_text(body, encoding="utf-8")
        self.assertEqual([], self.middot_errors(p))

    def test_other_dot_characters_and_html_entities(self) -> None:
        """가운뎃점 모양 글자와 HTML 개체도 같다 — 글자만 바꿔 빠져나가지 않는다."""
        for name, text in (("katakana.md", MD_HEAD + "- **가** — 하나 ・ 둘은 따로\n"),
                           ("araea.md", MD_HEAD + "- **가** — 하나 ㆍ 둘은 따로\n"),
                           ("entity.html", HTML_HEAD + "<dl><div><dt>가</dt><dd>하나 &middot; 둘은 따로</dd></div></dl>\n")):
            with self.subTest(name):
                p = self.dir / name
                self.checker.middot_baseline(str(p))
                p.write_text(text, encoding="utf-8")
                self.assertEqual(1, len(self.middot_errors(p)))

    def test_instruction_files_are_spared(self) -> None:
        """Claude 만 읽는 지시 파일은 사람이 읽는 문서가 아니다 — 반말 갈래와 같은 선."""
        sub = self.dir / "proj"
        sub.mkdir()
        p = sub / "CLAUDE.md"
        self.checker.middot_baseline(str(p))
        p.write_text("# 규칙\n\n- **값** — 하나 · 둘은 따로\n", encoding="utf-8")
        self.assertEqual([], self.middot_errors(p))

    def test_the_incident_sentences_are_caught(self) -> None:
        p = self.dir / "incident.md"
        self.checker.middot_baseline(str(p))
        p.write_text(MD_HEAD + "".join(f"- {s}\n" for s in INCIDENTS), encoding="utf-8")
        self.assertEqual(len(INCIDENTS), len(self.middot_errors(p)))

    def test_prose_form_keeps_the_rule(self) -> None:
        """오독은 개조식만의 문제가 아니다 — 산문 형식에서도 낸다."""
        p = self.dir / "prose.md"
        self.checker.middot_baseline(str(p))
        p.write_text("---\nform: prose\n---\n\n# 안내\n\n초안 · 최종본은 공유 폴더에 둡니다.\n",
                     encoding="utf-8")
        self.assertEqual(1, len(self.middot_errors(p, form="prose")))


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="middot-cli-"))
        self.env = dict(os.environ, KOREAN_QA_MIDDOT_LEDGER=str(self.dir / "ledger.tsv"))
        self.doc = self.dir / "doc.md"
        self.doc.write_text(MD_HEAD + "- **값** — 초안 · 최종본은 공유 폴더\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_checker(self, *args: str) -> str:
        return subprocess.run([sys.executable, "-X", "utf8", str(CHECKER), *args],
                              capture_output=True, text=True, encoding="utf-8",
                              env=self.env).stdout

    def test_an_untracked_doc_says_how_many_lines_it_skipped(self) -> None:
        """⛔ 안 본 것을 말하지 않으면 「오류 0」이 통과인지 안 본 것인지 갈리지 않는다."""
        out = self.run_checker(str(self.doc), "--no-rules")
        self.assertIn("합계 — 오류 0", out)
        self.assertIn(KIND, out, f"대장 밖이라 안 본 줄을 알리지 않았습니다:\n{out[-400:]}")

    def test_new_doc_flag_treats_every_line_as_new(self) -> None:
        """새 문서와 시험 문서는 대장 없이도 본다 — `--new-doc`."""
        out = self.run_checker(str(self.doc), "--no-rules", "--new-doc")
        self.assertIn(f"[{KIND}]", out)
        self.assertNotIn("합계 — 오류 0", out)

    def test_baseline_flag_records_the_doc(self) -> None:
        self.run_checker("--middot-baseline", str(self.doc))
        rows = [l.split("\t") for l in (self.dir / "ledger.tsv").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, len(rows))
        self.assertEqual(1, len([h for h in rows[0][2].split(",") if h]))
        out = self.run_checker(str(self.doc), "--no-rules")
        self.assertIn("합계 — 오류 0", out, "기존 줄을 오류로 셌습니다")


class HookTests(unittest.TestCase):
    """쓰기 직전에 기존 줄을 적고, 쓴 뒤에는 새 줄을 매번 알린다."""

    def setUp(self) -> None:
        # 게이트가 Temp·scratchpad 를 건너뛰므로 거기는 안 된다
        self.dir = repo_paths.gate_scratch(".gate-middot-")
        self.env = dict(os.environ,
                        KOREAN_CHECK_RECORD=os.path.join(self.dir, "store.jsonl"),
                        KOREAN_QA_MIDDOT_LEDGER=os.path.join(self.dir, "ledger.tsv"),
                        # 훅은 설치본 검사기를 먼저 쓴다 — 시험은 저장소 판을 잰다
                        KOREAN_QA_CHECKER=str(ROOT / "assets" / "doc-style-check.py"))

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def doc(self, name: str, body: str) -> str:
        p = os.path.join(self.dir, name)
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        return p

    def fire(self, event: str, tool: str, tool_input: dict, session: str = "middot-t") -> str:
        payload = {"hook_event_name": event, "tool_name": tool, "session_id": session,
                   "cwd": self.dir, "tool_input": tool_input}
        done = subprocess.run([sys.executable, "-X", "utf8", str(GATE)],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=240, env=self.env)
        return done.stdout + done.stderr

    def ledger_docs(self) -> list[str]:
        path = Path(self.dir) / "ledger.tsv"
        if not path.is_file():
            return []
        return [l.split("\t")[0] for l in path.read_text(encoding="utf-8").splitlines()]

    def test_pre_write_records_and_post_write_reports_new_lines_every_time(self) -> None:
        p = self.doc("plan.md", MD_HEAD + "- **기존** — 개발 종료 · 시험 시작\n")
        self.fire("PreToolUse", "Edit", {"file_path": p})
        self.assertEqual(1, len(self.ledger_docs()), "쓰기 직전에 기존 줄을 안 적었습니다")
        for n, line in enumerate(("- **새 값** — 초안 · 최종본은 공유 폴더\n",
                                  "- **또 새 값** — 사용자 수 · 사용 시간에는 요금을 매기지 않음\n")):
            with self.subTest(n):
                with io.open(p, "a", encoding="utf-8", newline="\n") as f:
                    f.write(line)
                self.fire("PreToolUse", "Edit", {"file_path": p})
                out = self.fire("PostToolUse", "Edit", {"file_path": p})
                self.assertIn(KIND, out, f"{n + 1}번째 쓰기에서 새 가운뎃점 줄을 안 알렸습니다:\n{out[:500]}")
                self.assertNotIn("시험 시작", out, "기존 줄을 알렸습니다")
        self.assertEqual(1, len(self.ledger_docs()), "쓸 때마다 대장을 다시 적었습니다")

    def test_writing_a_new_file_tracks_it_from_the_first_line(self) -> None:
        p = os.path.join(self.dir, "fresh.md")
        self.fire("PreToolUse", "Write", {"file_path": p, "content": "x"})
        self.doc("fresh.md", MD_HEAD + "- **값** — 하나 · 둘은 따로\n")
        out = self.fire("PostToolUse", "Write", {"file_path": p})
        self.assertIn(KIND, out)

    def test_a_codex_patch_that_adds_a_file_is_tracked(self) -> None:
        patch = "*** Begin Patch\n*** Add File: added.md\n+# 문서\n*** End Patch"
        self.fire("PreToolUse", "apply_patch", {"command": patch})
        docs = self.ledger_docs()
        self.assertEqual(1, len(docs), "Codex 가 새로 만든 문서를 대장에 안 올렸습니다")
        self.assertTrue(docs[0].endswith("added.md"))

    def test_an_untracked_doc_is_quiet_about_dots(self) -> None:
        """대장 밖 문서(손댄 적 없는 문서)는 쓰는 순간에도 가운뎃점을 짚지 않는다."""
        p = self.doc("old.md", MD_HEAD + "- **값** — 초안 · 최종본은 공유 폴더\n")
        out = self.fire("PostToolUse", "Write", {"file_path": p})
        self.assertNotIn(f"[{KIND}]", out)

    def test_publishing_a_new_dot_line_is_blocked(self) -> None:
        p = self.doc("share.md", MD_HEAD + "- **기존** — 개발 종료 · 시험 시작\n")
        self.fire("PreToolUse", "Edit", {"file_path": p})
        # 대조 — 기존 줄만 있으면 발행이 열린다(다른 까닭으로 막혀 아래 단언이 헛도는 것을 막음)
        out = self.fire("PreToolUse", "Artifact", {"file_path": p})
        self.assertNotIn('"deny"', out, f"기존 줄만 있는 문서의 발행을 막았습니다:\n{out[:500]}")
        with io.open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write("- **새 값** — 초안 · 최종본은 공유 폴더\n")
        out = self.fire("PreToolUse", "Artifact", {"file_path": p})
        self.assertIn('"deny"', out, f"새 가운뎃점 줄이 있는 문서의 발행을 안 막았습니다:\n{out[:500]}")


if __name__ == "__main__":
    unittest.main()
