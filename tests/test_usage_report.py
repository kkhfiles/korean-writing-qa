"""실사용 주간 집계(`usage_report.py`)가 판정 기록을 맞게 세는지 본다 — 합성 기록만 쓴다(실제 기록은 안 읽는다).

**지키는 것**

- 전체 판정과 재판정의 비용 비중 · 금액 없는 행(Codex)은 0으로 더하지 않고 건수와 토큰으로 따로
- 캐시를 못 읽은 재판정의 수와 비용 비중
- 호출 간격 칸 — 앞 호출은 기간 밖에서도 찾고, 같은 문서 간격으로 5분 캐시 손익 분기점을 넘는지 가름
- 첫 재판정의 `open_elsewhere` 분포 · 필드가 없는 옛 행은 「기록 없음」
- 실패 수는 모델별 · 재판정이 적으면 맨 위에 표본 부족
- 판정기가 대신 적은 줄을 넣고 따로 표시 · 본 기록과 겹치는 줄은 한 번만
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

import layer2_coverage as coverage  # noqa: E402
import usage_report as report  # noqa: E402

T0 = 1_700_000_000.0        # 기준 시각 — 기간은 T0 부터


def row(t: float, key: str = "A", *, targets=None, cost=0.1, ok=True, model="claude-opus-5-5", **kw) -> dict:
    r = {"at": "2023-11-15T00:00:00", "when": t, "doc": f"/x/{key}.md", "key": key, "model": model, "ok": ok}
    if targets is not None:
        r["targets"] = targets
    if ok:
        r.update(cost_usd=cost, input_tokens=2, cache_write=100, cache_read=50, output_tokens=10)
    r.update(kw)
    return r


class KindsTests(unittest.TestCase):

    def setUp(self) -> None:
        self.rows = [row(T0, cost=1.0), row(T0 + 10, cost=1.0),
                     row(T0 + 20, cost=None, model="gpt-6.1-sol", input_tokens=100, cache_write=0, cache_read=0,
                         output_tokens=50),
                     row(T0 + 30, targets=1, cost=0.5),
                     row(T0 + 40, targets=2, cost=1.5, cache_read=0),
                     row(T0 + 50, targets=1, ok=False, model="opus")]
        self.d = report.summarize(self.rows, T0, T0 + 1000)

    def test_cost_shares_leave_unpriced_rows_out(self) -> None:
        full, rej = self.d["kinds"]["full"], self.d["kinds"]["rejudge"]
        self.assertEqual((3, 2.0, 0.5), (full["calls"], full["cost_usd"], full["cost_share"]))
        self.assertEqual({"calls": 1, "tokens": 150}, full["unpriced"])
        self.assertEqual((3, 1, 2.0, 0.5), (rej["calls"], rej["failed"], rej["cost_usd"], rej["cost_share"]))
        self.assertEqual({"calls": 0, "tokens": 0}, rej["unpriced"])

    def test_cold_rejudges_are_counted_with_their_cost_share(self) -> None:
        c = self.d["cold_rejudge"]
        self.assertEqual((1, 2, 0.5, 1.5, 0.75), (c["calls"], c["of"], c["share"], c["cost_usd"], c["cost_share"]))

    def test_failures_are_counted_by_model(self) -> None:
        self.assertEqual({"opus": 1}, self.d["failures"])

    def test_rows_outside_the_period_are_left_out(self) -> None:
        d = report.summarize(self.rows + [row(T0 - 10 * 86400, cost=9.0)], T0, T0 + 1000)
        self.assertEqual(2.0, d["kinds"]["full"]["cost_usd"])

    def test_a_row_without_when_uses_at(self) -> None:
        r = row(0, cost=1.0)
        del r["when"]
        r["at"] = "2023-11-15T09:00:00"
        t = report.stamp(r)
        self.assertEqual(1, report.summarize([r], t - 1, t + 1)["kinds"]["full"]["calls"])


class GapTests(unittest.TestCase):

    def test_buckets_for_any_call_and_for_the_same_document(self) -> None:
        rows = [row(T0, "A", cache_ttl="5m"),                # A 처음 · 앞 호출 없음
                row(T0 + 60, "B", cache_ttl="5m"),           # B 처음 · 앞 호출(A) 1분
                row(T0 + 120, "A", cache_ttl="5m"),          # A 2분 · 앞 호출(B) 1분
                row(T0 + 1320, "A", cache_ttl="5m"),         # A 20분
                row(T0 + 5320, "A", cache_ttl="5m")]         # A 66분
        g = report.summarize(rows, T0, T0 + 9999)["gaps"]
        self.assertEqual({"≤5분": 2, "5~60분": 1, "60분 초과": 1, "앞 호출 없음": 1}, g["any"]["5m"])
        self.assertEqual({"≤5분": 1, "5~60분": 1, "60분 초과": 1, "앞 호출 없음": 2}, g["same_doc"]["5m"])
        # 1시간이라면 쓰는 호출 셋(앞 호출 없음 둘 · 60분 초과 하나)에 5~60분 다시 읽기 하나
        self.assertAlmostEqual(1 / 3, g["same_doc_reread_per_write"]["5m"])
        self.assertEqual([], g["over"])

    def test_breakeven_comes_from_the_unit_prices(self) -> None:
        self.assertAlmostEqual((7.94 - 5.00) / (5.00 - 0.20), report.BREAKEVEN)
        self.assertAlmostEqual(0.6125, report.BREAKEVEN, places=4)

    def test_rereads_past_the_breakeven_are_flagged(self) -> None:
        rows = [row(T0, "A"), row(T0 + 600, "A"), row(T0 + 1200, "A")]     # 쓰기 하나에 10분 간격 다시 읽기 둘
        d = report.summarize(rows, T0, T0 + 9999)
        self.assertEqual(2.0, d["gaps"]["same_doc_reread_per_write"][report.NO_TTL])
        self.assertEqual([report.NO_TTL], d["gaps"]["over"])
        self.assertIn("분기점을 넘음", report.render(d))

    def test_the_previous_call_is_found_before_the_period(self) -> None:
        rows = [row(T0 - 120, "A"), row(T0, "A")]
        g = report.summarize(rows, T0, T0 + 10)["gaps"]
        self.assertEqual(1, g["same_doc"][report.NO_TTL]["≤5분"])
        self.assertEqual(0, g["same_doc"][report.NO_TTL]["앞 호출 없음"])

    def test_unpriced_and_failed_calls_stay_out_of_the_gaps(self) -> None:
        rows = [row(T0, "A"), row(T0 + 60, "A", cost=None), row(T0 + 90, "A", ok=False), row(T0 + 600, "A")]
        g = report.summarize(rows, T0, T0 + 9999)["gaps"]
        self.assertEqual({"≤5분": 0, "5~60분": 1, "60분 초과": 0, "앞 호출 없음": 1}, g["same_doc"][report.NO_TTL])


class OpenElsewhereTests(unittest.TestCase):

    def test_first_rejudges_only_and_old_rows_apart(self) -> None:
        rows = [row(T0, targets=1, open_elsewhere=0, rejudge_only=False),
                row(T0 + 1, targets=1, open_elsewhere=0, rejudge_only=False),
                row(T0 + 2, targets=1, open_elsewhere=3, rejudge_only=False),
                row(T0 + 3, targets=1, open_elsewhere=12, rejudge_only=True),     # 두 번째 이상 — 뺌
                row(T0 + 4, targets=1),                                           # 필드 없는 옛 행
                row(T0 + 5, open_elsewhere=0)]                                    # 전체 판정 — 뺌
        o = report.summarize(rows, T0, T0 + 100)["open_elsewhere"]
        self.assertEqual((4, 3, 1, 2), (o["rows"], o["recorded"], o["missing"], o["zero"]))
        self.assertAlmostEqual(2 / 3, o["zero_share"])
        self.assertEqual({"0": 2, "1~2": 0, "3~9": 1, "10 이상": 0}, o["buckets"])


class SampleTests(unittest.TestCase):

    def test_few_rejudges_put_a_warning_on_top(self) -> None:
        d = report.summarize([row(T0, targets=1)], T0, T0 + 10)
        self.assertTrue(d["small_sample"])
        self.assertTrue(report.render(d).splitlines()[0].startswith("⚠️ 표본 부족 — 결론 내지 말 것"))

    def test_enough_rejudges_drop_the_warning(self) -> None:
        d = report.summarize([row(T0 + i, targets=1) for i in range(report.MIN_REJUDGES)], T0, T0 + 100)
        self.assertFalse(d["small_sample"])
        self.assertNotIn("표본 부족", report.render(d))


class SpareFileTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "tmp").mkdir()
        self.saved, tempfile.tempdir = tempfile.tempdir, str(self.dir / "tmp")
        self.log = self.dir / "calls.jsonl"

    def tearDown(self) -> None:
        tempfile.tempdir = self.saved
        self.tmp.cleanup()

    def write(self, p: Path, rows: list[dict]) -> None:
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def test_spare_rows_are_included_once_and_marked(self) -> None:
        both = row(T0, cost=1.0)
        self.write(self.log, [both])
        self.write(coverage.fallback_log(self.log), [both, row(T0 + 5, ok=False, model="sol-high")])
        rows, spare = report.load(self.log)
        self.assertEqual(coverage.fallback_log(self.log), spare)
        self.assertEqual([False, True], [bool(r.get("_spare")) for r in rows])
        d = report.summarize(rows, T0, T0 + 10)
        self.assertEqual((2, 1, {"sol-high": 1}), (d["rows"], d["spare_rows"], d["failures"]))
        self.assertIn("대신 적은 줄 1행", report.render(d, spare))

    def test_the_command_line_prints_tables_and_json(self) -> None:
        self.write(self.log, [row(T0, cost=1.0), row(T0 + 60, targets=1, cost=0.5)])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = report.main(["--log", str(self.log), "--since", "2020-01-01"])
        self.assertEqual(0, rc)
        self.assertIn("전체 판정과 재판정", out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            report.main(["--log", str(self.log), "--since", "2020-01-01", "--json", "-"])
        self.assertEqual(2, json.loads(out.getvalue())["rows"])

    def test_a_missing_log_is_reported_not_crashed(self) -> None:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = report.main(["--log", str(self.dir / "none.jsonl")])
        self.assertEqual(0, rc)
        self.assertIn("기록 없음", out.getvalue())


if __name__ == "__main__":
    unittest.main()
