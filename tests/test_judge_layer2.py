"""2층 판정 호출이 **잰 것과 같은 모양으로 돌고, 호출마다 비용을 남기는지** 본다 — 모델은 안 부른다.

- 프롬프트가 2층 탐침(`guided`)과 같은가 — 다르면 탐침으로 잰 값이 뜻을 잃는다
- 호출마다 비용 한 줄이 남는가 · 실패한 호출도 남는가(시간은 들었다)
- `--cost` 합계가 기록과 맞는가
- 백엔드가 없으면 **통과처럼 조용하지 않고** 종료 코드 3 으로 알리는가
- 긴 문서를 나눌 때 줄 번호가 원문과 맞는가
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
import probe_layer2_kinds as probe  # noqa: E402

# 실제 사용자 답 기록을 읽으면 시험 결과가 그날 기록에 따라 갈린다 — 빈 기록으로 고정
coverage.DECISIONS = Path(tempfile.mkdtemp()) / "decisions.jsonl"


class FakeBackend:
    def __init__(self, reply=None, fail=False):
        self.calls = []
        self.reply = reply if reply is not None else []
        self.fail = fail

    def call(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise TimeoutError("시험용 실패")
        # 입력은 셋으로 나뉘어 온다 — 캐시 쓴 것 · 읽은 것 · 나머지
        return {"text": json.dumps(self.reply, ensure_ascii=False), "model": "claude-opus-5-5",
                "usage": {"input_tokens": 2, "cache_creation_input_tokens": 900,
                          "cache_read_input_tokens": 98, "output_tokens": 200},
                "cost_usd": 0.25}

    @staticmethod
    def parse(text):
        return json.loads(text)

    def pair(self):
        return self.call, self.parse


class JudgeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG
        judge.LOG = self.dir / "calls.jsonl"

    def tearDown(self) -> None:
        judge.LOG = self.saved
        self.tmp.cleanup()

    def doc(self, text: str, name: str = "d.md") -> Path:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return p

    def run_main(self, argv, backend=None) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main(argv, backend=backend)
        return rc, out.getvalue()

    def log_rows(self) -> list[dict]:
        return [json.loads(l) for l in judge.LOG.read_text(encoding="utf-8").splitlines()]

    def test_the_prompt_is_the_probe_prompt(self) -> None:
        """잰 것과 도는 것이 같아야 한다 — 규칙 글과 틀을 탐침에서 그대로 받는다."""
        fake = FakeBackend()
        text = "# 제목\n\n원인을 알 수 없었습니다.\n"
        rc, _ = self.run_main([str(self.doc(text))], backend=fake.pair())
        self.assertEqual(0, rc)
        sent = fake.calls[0]
        self.assertEqual(probe.SYSTEM.format(rules=probe.rules_for("guided")), sent["system"])
        self.assertEqual(probe.USER.format(document=probe.numbered(text)), sent["user"])

    def test_every_call_leaves_a_cost_line(self) -> None:
        fake = FakeBackend(reply=[{"line": 3, "phrase": "알 수", "category": "c", "fix": "파악할 수"}])
        rc, out = self.run_main([str(self.doc("# 제목\n\n원인을 알 수 없었습니다.\n"))],
                                backend=fake.pair())
        self.assertEqual(0, rc)
        rows = self.log_rows()
        self.assertEqual(1, len(rows))
        for field in ("at", "doc", "sha256", "model", "seconds", "input_tokens",
                      "output_tokens", "cost_usd", "findings", "ok"):
            self.assertIn(field, rows[0], f"비용 기록에 「{field}」 가 없습니다")
        self.assertTrue(rows[0]["ok"])
        self.assertEqual(0.25, rows[0]["cost_usd"])
        self.assertIn("청구액 아님", out, "환산 금액이 청구액이 아니라고 밝혀야 합니다")

    def test_a_failed_call_is_logged_and_reported(self) -> None:
        """실패한 호출도 남긴다 — 시간은 들었다. 통과처럼 조용하지 않다."""
        rc, out = self.run_main([str(self.doc("본문입니다.\n"))], backend=FakeBackend(fail=True).pair())
        self.assertEqual(4, rc)
        self.assertIn("검사되지 않았습니다", out)
        rows = self.log_rows()
        self.assertEqual(1, len(rows))
        self.assertFalse(rows[0]["ok"])

    def test_missing_backend_is_not_silent(self) -> None:
        saved = judge.load_backend
        judge.load_backend = lambda *_: None
        try:
            rc, out = self.run_main([str(self.doc("본문입니다.\n"))])
        finally:
            judge.load_backend = saved
        self.assertEqual(3, rc)
        self.assertIn("직접 읽고", out)

    def test_cost_report_sums_the_log(self) -> None:
        fake = FakeBackend()
        for name in ("a.md", "b.md"):
            self.run_main([str(self.doc("본문입니다.\n", name))], backend=fake.pair())
        rc, out = self.run_main(["--cost", "--by", "doc"])
        self.assertEqual(0, rc)
        total = [l for l in out.splitlines() if l.strip().startswith("합계")][0]
        self.assertIn("0.50", total, f"두 호출 0.25 + 0.25 가 합계에 안 맞습니다 — {total}")
        self.assertIn("2,000", total, "입력 토큰은 캐시에 쓴 것·읽은 것까지 합쳐야 합니다 "
                                      "(빼면 첫 실측처럼 2 토큰으로 찍힘)")

    def test_long_documents_are_split_at_headings_with_true_line_numbers(self) -> None:
        lines = []
        for s in range(5):
            lines.append(f"## 절 {s}")
            lines += [f"문장 {s}-{i}입니다." for i in range(79)]
        parts = judge.chunks(lines)
        self.assertGreater(len(parts), 1)
        self.assertEqual(lines, [l for _, part in parts for l in part], "나누다 줄이 빠지거나 겹쳤습니다")
        for first, part in parts:
            self.assertEqual(lines[first - 1], part[0], "묶음의 첫 줄 번호가 원문과 다릅니다")
            self.assertLessEqual(len(part), judge.CHUNK_LINES)
        self.assertTrue(all(part[0].startswith("## ") for _, part in parts[1:]),
                        "제목 경계에서 나눠야 합니다")

    def test_line_numbers_follow_the_phrase_not_the_model(self) -> None:
        lines = ["첫 줄", "둘째 줄", "원인을 알 수 없었습니다.", "넷째 줄"]
        self.assertEqual(3, judge.relocate(lines, 1, "알 수"))
        self.assertEqual(2, judge.relocate(lines, 2, "없는 표현"),
                         "표현을 못 찾으면 모델이 낸 번호를 그대로 둡니다")

    def test_fix_notes_catch_what_the_user_sent_back(self) -> None:
        """2026-09-30 실문서 검토에서 되돌아온 수정안 모양 — 드문 말 · 지시어 · 서술형으로 바뀜."""
        freq = judge.load_freq()
        if freq is None:
            self.skipTest("형태소 분석기가 없다")
        doc = set(judge._lemmas("9월 11일 몫의 소급 · 둘만 최종 값"))
        rare = judge.fix_notes("9월 11일 판정 항목 소급 확인", "9월 11일 몫의 소급", set(), freq)
        self.assertTrue(any("소급" in n for n in rare), f"드문 낱말을 못 짚었습니다 — {rare}")
        kept = judge.fix_notes("9월 11일 판정 항목 소급 확인", "9월 11일 몫의 소급", doc, freq)
        self.assertTrue(any("그대로 둠" in n and "소급" in n for n in kept),
                        f"원문의 드문 낱말을 그대로 둔 것은 새로 들여온 것과 갈라 짚어야 합니다 — {kept}")
        demo = judge.fix_notes("이 기간", "이 구간", set(), freq)
        self.assertTrue(any("지시어" in n for n in demo), f"지시어를 못 짚었습니다 — {demo}")
        prose = judge.fix_notes("확인하지 않았다는 뜻입니다.", "관측 자체가 없음", set(), freq)
        self.assertTrue(any("서술형" in n for n in prose), f"형식 바뀜을 못 짚었습니다 — {prose}")
        self.assertEqual([], judge.fix_notes("분석 실행과 결과 확인", "분석 돌리고 결과 읽기",
                                             set(), freq), "좋다고 판정된 수정안까지 짚었습니다")

    def test_html_is_judged_on_visible_text(self) -> None:
        p = self.doc("<html><style>p{x:y}</style><body><h1>제목</h1><p>원인을 알 수 없었습니다.</p>"
                     "<script>var a='숨은 글';</script></body></html>", "d.html")
        text = judge.read_doc(p)
        self.assertIn("원인을 알 수 없었습니다.", text)
        self.assertNotIn("숨은 글", text)
        self.assertNotIn("x:y", text)

    def test_button_label_is_not_glued_to_the_sentence(self) -> None:
        # 2026-10-07 — 「실제로 걸린 문장 넷멈춤」을 작업 흔적으로 읽고 사람에게 넘겼다
        p = self.doc('<p class="demo-head">실제로 걸린 문장 넷<span class="dots"></span>'
                     '<button type="button" hidden>멈춤</button></p>', "d.html")
        lines = judge.read_doc(p).splitlines()
        self.assertIn("실제로 걸린 문장 넷", lines)
        self.assertIn("멈춤", lines)


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(cwd), *args],
                   check=True, capture_output=True)


class SinceTests(unittest.TestCase):
    """`--since` — 갈라진 뒤 새로 생겼고 아직 판정 안 한 줄만 판정하고, 그 줄의 지적만 낸다.

    발행 게이트가 같은 기록으로 「새 줄을 다 봤나」를 가르므로, 여기가 틀리면 게이트가
    판정한 문서를 막거나 안 한 문서를 통과시킨다.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.saved = judge.LOG
        judge.LOG = Path(self.tmp.name) / "calls.jsonl"
        # 묶음 둘 — 「## 둘」(101행)에서 나뉜다
        self.lines = (["## 하나"] + [f"하나 {i}번 문장입니다." for i in range(99)]
                      + ["## 둘"] + [f"둘 {i}번 문장입니다." for i in range(99)])
        self.doc = self.repo / "d.md"
        self.write(self.lines)
        git(self.repo, "init", "-b", "main")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "switch", "-c", "work")

    def tearDown(self) -> None:
        judge.LOG = self.saved
        self.tmp.cleanup()

    def write(self, lines: list[str], path: Path | None = None) -> None:
        (path or self.doc).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def edit(self, old: str, new: str) -> None:
        self.write([new if l == old else l for l in self.doc.read_text(encoding="utf-8").splitlines()])

    def run_since(self, fake: FakeBackend, path: Path | None = None, ref: str = "main") -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main([str(path or self.doc), "--since", ref], backend=fake.pair())
        return rc, out.getvalue()

    def test_only_the_chunk_with_a_new_line_is_sent(self) -> None:
        self.edit("둘 5번 문장입니다.", "둘 5번 문장을 새로 썼습니다.")
        fake = FakeBackend()
        rc, _ = self.run_since(fake)
        self.assertEqual(0, rc)
        self.assertEqual(1, len(fake.calls), "새 줄이 없는 묶음까지 보냈습니다")
        self.assertIn("101 | ## 둘", fake.calls[0]["user"])
        self.assertIn("새로 썼습니다", fake.calls[0]["user"])

    def test_the_model_is_told_which_lines_to_check(self) -> None:
        # 묶음 전체에 지적을 써 오게 하고 버리면 버린 만큼 출력 토큰과 시간이 든다(2026-10-07)
        self.edit("둘 5번 문장입니다.", "둘 5번 문장을 새로 썼습니다.")
        fake = FakeBackend()
        self.run_since(fake)
        self.assertTrue(fake.calls[0]["user"].rstrip().endswith("\n107"),
                        "새 줄만 점검하라고 알리지 않았습니다")
        full = FakeBackend()
        with contextlib.redirect_stdout(io.StringIO()):
            judge.main([str(self.doc)], backend=full.pair())
        self.assertNotIn("이번에는 아래 줄만 점검한다", full.calls[0]["user"])

    def test_findings_on_other_lines_are_hidden(self) -> None:
        """재판정이 끝나지 않는 것을 막는다 — 안 고친 줄의 새 지적은 보이지 않는다."""
        self.edit("둘 5번 문장입니다.", "둘 5번 문장을 새로 썼습니다.")
        fake = FakeBackend(reply=[
            {"line": 108, "phrase": "둘 7번", "category": "c", "fix": "옛 줄 지적"},
            {"line": 107, "phrase": "새로 썼습니다", "category": "c", "fix": "새 줄 지적"}])
        rc, out = self.run_since(fake)
        self.assertEqual(0, rc)
        self.assertIn("새 줄 지적", out)
        self.assertNotIn("옛 줄 지적", out)
        self.assertIn("1건은 숨김", out)

    def test_a_second_run_without_changes_calls_nothing(self) -> None:
        self.edit("둘 5번 문장입니다.", "둘 5번 문장을 새로 썼습니다.")
        fake = FakeBackend()
        self.run_since(fake)
        rc, out = self.run_since(fake)
        self.assertEqual(0, rc)
        self.assertEqual(1, len(fake.calls), "이미 판정한 줄을 다시 보냈습니다")
        self.assertIn("판정할 새 줄 없음", out)

    def test_a_line_fixed_after_judging_is_judged_again(self) -> None:
        """고친 말이 새 문제를 들여오는지 보는 것이 재판정의 몫이다(되돌린 수정안 8/40)."""
        self.edit("둘 5번 문장입니다.", "둘 5번 문장을 새로 썼습니다.")
        fake = FakeBackend(reply=[{"line": 107, "phrase": "다시 고쳤습니다", "category": "c", "fix": "f"}])
        self.run_since(fake)
        self.edit("둘 5번 문장을 새로 썼습니다.", "둘 5번 문장을 다시 고쳤습니다.")
        rc, out = self.run_since(fake)
        self.assertEqual(0, rc)
        self.assertEqual(2, len(fake.calls))
        self.assertIn("새 줄 1개만 판정", out)
        self.assertIn("다시 고쳤습니다", out)

    def test_a_file_new_in_the_branch_is_all_new(self) -> None:
        new = self.repo / "n.md"
        self.write(["# 새 문서", "", "처음 쓴 문장입니다."], new)
        fake = FakeBackend()
        rc, out = self.run_since(fake, new)
        self.assertEqual(0, rc)
        self.assertEqual(1, len(fake.calls))
        self.assertIn("새 줄 2개만 판정", out)

    def test_an_unknown_ref_is_a_usage_error(self) -> None:
        rc, out = self.run_since(FakeBackend(), ref="no-such-branch")
        self.assertEqual(2, rc)
        self.assertIn("갈라진 지점", out)

    def test_each_call_records_the_lines_it_saw(self) -> None:
        self.write(self.lines + ["---", "덧붙인 문장입니다."])
        self.run_since(FakeBackend())
        row = [json.loads(l) for l in judge.LOG.read_text(encoding="utf-8").splitlines()][0]
        self.assertEqual("d.md", row["key"], "저장소 뿌리 기준 경로여야 작업 트리와 기본 checkout 이 같은 문서로 읽힙니다")
        self.assertIn(coverage.line_key("## 둘"), row["seen"])
        self.assertIsNone(coverage.line_key("---"), "한글 없는 줄은 판정 대상이 아닙니다")

    def test_old_records_are_not_trusted(self) -> None:
        log = Path(self.tmp.name) / "old.jsonl"
        k = coverage.line_key("하나 0번 문장입니다.")
        stale = {"ok": True, "key": "d.md", "seen": [k], "when": time.time() - 15 * 86400}
        failed = {"ok": False, "key": "d.md", "seen": ["x"], "when": time.time()}
        log.write_text(json.dumps(stale) + "\n" + json.dumps(failed) + "\n", encoding="utf-8")
        self.assertEqual(set(), coverage.judged("d.md", log),
                         "14일 지난 기록이나 실패한 호출을 판정한 것으로 셌습니다")


if __name__ == "__main__":
    unittest.main()
