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
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import judge_layer2 as judge  # noqa: E402
import probe_layer2_kinds as probe  # noqa: E402


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
        judge.load_backend = lambda: None
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


if __name__ == "__main__":
    unittest.main()
