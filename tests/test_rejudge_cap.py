"""같은 줄을 거듭 다시 판정할 때 **상한에서 멈추고 사람에게 올리는지**, 고친 줄을 **기준 판과 대조하게
하는지** 본다 — 모델은 안 부른다.

(2026-10-12 고리 재현 시험) README 를 수정안대로 고치고 고친 줄만 다시 판정하자 6회차까지 지적이
0 이 안 됐고, 후반 지적은 긴 줄 셋에 몰렸다. 그중에는 5회차에야 짚은 원문의 실제 결함도 있었다 —
그래서 상한에서 통과시키지 않고 사람에게 올린다. 수정안이 경위 문장을 다른 주장으로 바꾼 사례도
있었다 — 그래서 고친 줄을 기준 판과 함께 보낸다.

**지키는 것**

- 고친 줄이 앞 판정의 자손으로 이어져 판정 횟수가 1 · 2 · 3 … 으로 세지나 · 뿌리는 기준 판 그대로인가
- 한 줄을 둘로 나눠도 둘 다 횟수를 물려받나 — 나눈다고 예산이 새로 생기지 않는다
- 상한을 넘은 줄의 고칠 지적은 사람 확인으로 바뀌고, 처음 넘을 때 그 줄 자체도 사람 확인에 오르나
- 고친 줄의 기준 판과 근처에서 지운 줄이 판정 프롬프트에 실리나
- 예전 판으로 되돌리면 그때 남은 고칠 지적이 다시 열리나 — 순환을 게이트가 잡는 길
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402

BASE = ["# 소개", "", "업무 목록은 매일 오전 아홉 시에 갱신됩니다.", "",
        "마감이 가까운 업무를 맨 위에 표시합니다."]
VERSIONS = ["마감이 가까운 업무를 맨 위에 둡니다.",
            "마감이 임박한 업무를 맨 위에 둡니다.",
            "마감이 임박한 업무를 목록 맨 위에 둡니다.",
            "마감이 사흘 남은 업무를 목록 맨 위에 둡니다.",
            "마감이 사흘 남은 업무를 목록의 맨 위에 둡니다."]


def fix_on(line: str, n: int) -> dict:
    word = line.split()[1]
    return {"line": n, "phrase": word, "category": "업무에서 쓰는 말로 쓰기", "fix": word + "한",
            "why": "시험", "decide": "fix"}


class _Base(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS
        judge.LOG = self.dir / "calls.jsonl"
        coverage.ANSWERS = self.dir / "answers.jsonl"
        coverage.DISMISSALS = self.dir / "dismissals.jsonl"
        coverage.DECISIONS = self.dir / "decisions.jsonl"
        self.doc = self.dir / "d.md"

    def tearDown(self) -> None:
        judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS = self.saved
        self.tmp.cleanup()

    def write(self, lines: list[str]) -> None:
        self.doc.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def rejudge(self, lines: list[str], targets: list[int], reply=None) -> tuple[dict, FakeBackend]:
        self.write(lines)
        fake = FakeBackend(reply if reply is not None else [fix_on(lines[targets[0] - 1], targets[0])])
        return judge.judge(self.doc, "opus", 10, fake.pair(), targets, BASE), fake

    def last_row(self) -> dict:
        return json.loads(judge.LOG.read_text(encoding="utf-8").splitlines()[-1])


class LineageTests(_Base):

    def test_rounds_count_up_and_keep_the_base_root(self) -> None:
        for k, v in enumerate(VERSIONS[:4], 1):
            self.rejudge(BASE[:4] + [v], [5])
            entry = self.last_row()["targeted"][0]
            self.assertEqual(k, entry["round"], f"{k}번째 판정을 {entry['round']}번째로 셌습니다")
            self.assertEqual(BASE[4], entry["root"], "뿌리가 기준 판 줄이 아닙니다")

    def test_a_split_line_inherits_the_count(self) -> None:
        for v in VERSIONS[:3]:
            self.rejudge(BASE[:4] + [v], [5])
            self.write(BASE[:4] + [v])
        split = BASE[:4] + ["마감이 임박한 업무를 먼저 고릅니다.", "고른 업무를 목록 맨 위에 둡니다."]
        self.rejudge(split, [5, 6])
        rounds = [e["round"] for e in self.last_row()["targeted"]]
        self.assertEqual([4, 4], rounds, "줄을 나누자 판정 횟수가 처음부터 다시 셌습니다")

    def test_the_count_restarts_after_the_line_is_merged(self) -> None:
        """(2026-10-13 README 113행) 전날 4회차로 상한에 걸려 합쳐진 줄을 고치자 5회차로 세어 지적이
        곧장 사람 확인으로 갔다 — 갈라진 지점 커밋보다 앞선 판정은 이미 합쳐진 작업이다."""
        import time as _time
        for v in VERSIONS[:4]:
            self.rejudge(BASE[:4] + [v], [5])
        merged_at = _time.time() + 1          # 그 뒤에 합쳐짐 — 새 기준 판에 4번째 판이 들어감
        new_base = BASE[:4] + [VERSIONS[3]]
        self.write(BASE[:4] + [VERSIONS[4]])
        fake = FakeBackend([fix_on(VERSIONS[4], 5)])
        result = judge.judge(self.doc, "opus", 10, fake.pair(), [5], new_base, None, merged_at)
        entry = self.last_row()["targeted"][0]
        self.assertEqual((1, VERSIONS[3]), (entry["round"], entry["root"]),
                         "합쳐지기 전의 판정 횟수를 이어 셌습니다")
        self.assertEqual(0, result["held"])

    def test_rounds_count_within_the_same_base(self) -> None:
        for k, v in enumerate(VERSIONS[:3], 1):
            self.write(BASE[:4] + [v])
            judge.judge(self.doc, "opus", 10, FakeBackend([fix_on(v, 5)]).pair(), [5], BASE, None, 1234.0)
            self.assertEqual(k, self.last_row()["targeted"][0]["round"], "같은 갈라진 지점의 판정을 못 이어 셌습니다")

    def test_a_new_line_starts_at_one_without_a_root(self) -> None:
        self.rejudge(BASE + ["", "새로 쓴 안내 문장입니다."], [7])
        entry = self.last_row()["targeted"][0]
        self.assertEqual((1, None), (entry["round"], entry["root"]))


class CapTests(_Base):

    def run_rounds(self, upto: int) -> list[dict]:
        out = []
        for v in VERSIONS[:upto]:
            result, _ = self.rejudge(BASE[:4] + [v], [5])
            out.append(result)
        return out

    def test_up_to_the_cap_findings_stay_fixes(self) -> None:
        results = self.run_rounds(judge.REJUDGE_CAP)
        for r in results:
            self.assertEqual(["fix"], [f["decide"] for f in r["findings"]])
        self.assertEqual(0, results[-1]["held"])

    def test_over_the_cap_findings_go_to_a_person_with_the_line(self) -> None:
        results = self.run_rounds(judge.REJUDGE_CAP + 1)
        last = results[-1]
        self.assertTrue(all(f["decide"] == "ask" for f in last["findings"]),
                        "상한을 넘었는데 고칠 지적으로 남겨 자동 수정이 이어집니다")
        held_line = [f for f in last["findings"] if f.get("category") == "재판정 상한"]
        self.assertEqual(1, len(held_line), "상한을 처음 넘은 줄 자체를 사람 확인에 안 올렸습니다")
        self.assertIn(BASE[4], held_line[0]["fix"], "사람이 대조할 기준 판이 없습니다")
        lines = coverage.read_doc(self.doc).splitlines()
        asks = coverage.open_asks(coverage.doc_key(self.doc), lines, judge.LOG)
        self.assertEqual({5}, {n for n, _ in asks})

    def test_the_line_is_held_only_once(self) -> None:
        results = self.run_rounds(judge.REJUDGE_CAP + 2)
        self.assertEqual([], [f for f in results[-1]["findings"] if f.get("category") == "재판정 상한"],
                         "상한을 넘을 때마다 같은 줄을 또 올렸습니다")

    def test_the_cap_holds_even_without_findings(self) -> None:
        for v in VERSIONS[:judge.REJUDGE_CAP]:
            self.rejudge(BASE[:4] + [v], [5])
        result, _ = self.rejudge(BASE[:4] + [VERSIONS[judge.REJUDGE_CAP]], [5], reply=[])
        self.assertEqual(["재판정 상한"], [f["category"] for f in result["findings"]],
                         "지적이 없다고 상한을 넘은 줄을 그냥 통과시켰습니다")

    def test_a_full_judgment_does_not_count(self) -> None:
        self.write(BASE[:4] + [VERSIONS[0]])
        judge.judge(self.doc, "opus", 10, FakeBackend([]).pair())
        self.assertNotIn("targeted", self.last_row())


class PromptTests(_Base):

    def test_the_base_version_is_sent(self) -> None:
        _, fake = self.rejudge(BASE[:4] + [VERSIONS[0]], [5])
        user = fake.calls[-1]["user"]
        self.assertIn("5행 기준 판: " + BASE[4], user)
        self.assertIn("고치다 뜻이 바뀐 곳", user)

    def test_a_deleted_neighbour_is_sent(self) -> None:
        _, fake = self.rejudge(BASE[:2] + [VERSIONS[0]], [3])
        self.assertIn("지움: " + BASE[2], fake.calls[-1]["user"], "근처에서 지운 줄을 판정기가 못 봅니다")

    def test_a_closed_fix_on_the_line_is_sent(self) -> None:
        # 2026-10-12 README 재판정 — 확인함으로 닫은 의문을 줄이 바뀌자 판정기가 또 냈다
        self.rejudge(BASE[:4] + [VERSIONS[0]], [5])
        judge.dismiss(self.doc, 5, "대상아님", "제품 화면의 정해진 문구라 규칙 대상이 아님")
        _, fake = self.rejudge(BASE[:4] + [VERSIONS[1]], [5])
        user = fake.calls[-1]["user"]
        self.assertIn("앞서 이 줄에서 확인하거나 까닭을 적어 닫은 지적", user)
        self.assertIn("제품 화면의 정해진 문구라", user)

    def test_an_unchanged_base_adds_nothing(self) -> None:
        _, fake = self.rejudge(BASE + ["", "새로 쓴 안내 문장입니다."], [7])
        self.assertNotIn("기준 판", fake.calls[-1]["user"])


class DeletionTests(_Base):
    """지우기만 한 자리 — 바로 다음 줄을 대표로 판정기에 보이고 뜻 바뀜만 받는다(2026-10-13)."""

    CUT = BASE[:2] + BASE[4:]          # 업무 목록 줄을 지움 · 다음 한글 줄은 3행

    def judge_cut(self, reply) -> tuple[dict, FakeBackend]:
        self.write(self.CUT)
        lines = coverage.read_doc(self.doc).splitlines()
        anchors = dict(coverage.open_deletions(lines, BASE, set()))
        self.assertEqual({3: [BASE[2]]}, anchors)
        fake = FakeBackend(reply)
        return judge.judge(self.doc, "opus", 10, fake.pair(), [], BASE, anchors), fake

    def test_the_deleted_line_is_shown_at_the_anchor(self) -> None:
        _, fake = self.judge_cut([])
        user = fake.calls[-1]["user"]
        self.assertIn("3행 가까이에서 지움: " + BASE[2], user)
        self.assertIn("고치지 않았다", user)
        row = self.last_row()
        self.assertIn(coverage.line_key(BASE[2]), row["deleted_seen"])
        self.assertEqual([], row.get("targeted"), "대표 줄을 재판정 횟수에 셌습니다 — 안 고친 줄입니다")
        lines = coverage.read_doc(self.doc).splitlines()
        self.assertEqual([], coverage.open_deletions(lines, BASE, coverage.deleted_seen(
            coverage.doc_key(self.doc), judge.LOG)), "판정기가 본 지운 자리를 또 요구합니다")

    def test_the_anchor_takes_only_meaning_changes(self) -> None:
        meaning = {"line": 3, "phrase": "마감이 가까운", "category": "고치다 뜻이 바뀐 곳",
                   "fix": "x", "why": "갱신 시각이 빠짐", "decide": "fix"}
        other = {"line": 3, "phrase": "표시합니다", "category": "군더더기 지우기",
                 "fix": "y", "why": "시험", "decide": "fix"}
        result, _ = self.judge_cut([meaning, other])
        self.assertEqual(["고치다 뜻이 바뀐 곳"], [f["category"] for f in result["findings"]],
                         "안 고친 대표 줄에서 다른 지적을 받았습니다 — 고리를 만듭니다")


class CycleTests(_Base):

    def test_reverting_reopens_the_old_fix(self) -> None:
        self.write(BASE)
        judge.judge(self.doc, "opus", 10, FakeBackend([fix_on(BASE[4], 5)]).pair())
        open_now = lambda: [n for n, _ in coverage.open_fixes(
            coverage.doc_key(self.doc), coverage.read_doc(self.doc).splitlines(), judge.LOG)]
        self.assertEqual([5], open_now())
        self.write(BASE[:4] + ["마감이 임박한 업무를 맨 위에 표시합니다."])
        self.assertEqual([], open_now())
        self.write(BASE)
        self.assertEqual([5], open_now(), "예전 판으로 되돌렸는데 그때 남은 지적이 다시 안 열렸습니다")


class BatchWarningTests(_Base):
    """(2026-10-13) 지적 하나 고칠 때마다 다시 판정하면 호출이 늘고 같은 줄의 횟수가 빨리 쌓인다 —
    한 문서 58회 중 29회가 대상 3줄 이하였다. 막지 않고 알리며, 얼마나 자주 그러는지 기록에 남긴다."""

    NEW = "새로 넣은 문장도 다듬습니다."

    def first(self) -> list[str]:
        lines = BASE[:4] + [VERSIONS[0], "", self.NEW]
        self.write(lines)
        judge.judge(self.doc, "opus", 10, FakeBackend([fix_on(lines[4], 5), fix_on(self.NEW, 7)]).pair(),
                    [5, 7], BASE)
        return lines

    def test_the_first_judgment_does_not_warn(self) -> None:
        self.first()
        row = self.last_row()
        self.assertFalse(row["rejudge_only"])
        self.assertEqual(0, row["pending_fixes"])

    def test_rejudging_one_fix_while_others_are_open_warns_and_is_recorded(self) -> None:
        lines = self.first()
        lines[4] = VERSIONS[1]                       # 5행 지적만 고침 — 7행 지적은 남음
        self.write(lines)
        result = judge.judge(self.doc, "opus", 10, FakeBackend([]).pair(), [5], BASE)
        self.assertEqual(1, result["pending_fixes"], "다른 줄에 남은 고칠 지적을 안 셌습니다")
        row = self.last_row()
        self.assertTrue(row["rejudge_only"])
        self.assertEqual(1, row["pending_fixes"])
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            judge.show(result)
        self.assertIn("처리 안 된 고칠 지적 1건", out.getvalue())

    def test_no_warning_once_everything_is_handled(self) -> None:
        lines = self.first()
        lines[4] = VERSIONS[1]
        lines[6] = "새로 쓴 문장도 다듬습니다."           # 두 지적을 다 고친 뒤 한 번에
        self.write(lines)
        result = judge.judge(self.doc, "opus", 10, FakeBackend([]).pair(), [5, 7], BASE)
        self.assertEqual(0, result["pending_fixes"])

    def test_asks_waiting_for_the_user_are_not_counted(self) -> None:
        """사람 확인은 세션이 못 푼다 — 그것 때문에 경고하면 할 수 있는 일이 없다."""
        lines = BASE[:4] + [VERSIONS[0], "", self.NEW]
        self.write(lines)
        ask = dict(fix_on(self.NEW, 7), decide="ask")
        judge.judge(self.doc, "opus", 10, FakeBackend([fix_on(lines[4], 5), ask]).pair(), [5, 7], BASE)
        lines[4] = VERSIONS[1]
        self.write(lines)
        result = judge.judge(self.doc, "opus", 10, FakeBackend([]).pair(), [5], BASE)
        self.assertEqual(0, result["pending_fixes"])


if __name__ == "__main__":
    unittest.main()
