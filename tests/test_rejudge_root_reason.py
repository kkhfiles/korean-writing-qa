"""재판정에 기준 판과 함께 **왜 고쳤는지**(앞선 판정의 지적)를 싣는지, 지적됐던 표현을 되살리는 수정안에
안내를 붙이는지 본다 — 모델은 안 부른다.

(2026-10-19 재생 · 사용자 판단) 기준 판만 보내자 판정기가 그것을 정답처럼 읽고 「뜻이 바뀌었다」며 사용자가
고치라고 했던 표현(「자동 수리」 · 「원문을 그대로 훑어」)으로 되돌리라고 냈다. 외부 검토(Argon · 10-20)가 기준
판에 0회차 지적 사유를 함께 보내고, 되돌리는 수정안은 지우지 말고 안내로 바꾸라고 권했다.

**지키는 것**

- 기준 판 줄에 앞서 낸 고칠 지적이 「고친 까닭」으로 재판정 입력에 실리나
- 앞선 지적이 없으면 입력이 예전과 같은가(고친 까닭 문구가 없음)
- 수정안이 지적됐던 표현을 되살리면 버리지 않고 `revives` 와 안내가 붙나 · 기록에도 남나
- 재생은 그 입력을 남긴 시각 앞의 판정만 쓰나
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402
from test_rejudge_cap import BASE, _Base  # noqa: E402

EDITED = BASE[:4] + ["마감이 가까운 업무를 맨 위에 둡니다."]
ROUND0 = {"line": 5, "phrase": "표시합니다", "category": "업무에서 쓰는 말로 쓰기", "fix": "둡니다",
          "why": "", "decide": "fix"}
REVERT = {"line": 5, "phrase": "맨 위에 둡니다", "category": judge.INTENT_ONLY, "fix": "맨 위에 표시합니다",
          "why": "기준 판의 뜻", "decide": "fix"}


class RootReasonTests(_Base):

    def round0(self) -> None:
        self.write(BASE)
        judge.judge(self.doc, "opus", 10, FakeBackend([ROUND0]).pair())

    def test_the_reason_rides_with_the_base_line(self) -> None:
        self.round0()
        _, fake = self.rejudge(EDITED, [5], [])
        user = fake.calls[-1]["user"]
        self.assertIn("5행 기준 판: 마감이 가까운 업무를 맨 위에 표시합니다.", user)
        self.assertIn("고친 까닭: 「표시합니다」→「둡니다」", user)
        self.assertIn("지적됐던 표현을 되살리는 수정안은 내지 않는다", user)

    def test_without_an_earlier_finding_the_input_is_unchanged(self) -> None:
        self.write(BASE)
        judge.judge(self.doc, "opus", 10, FakeBackend([]).pair())
        _, fake = self.rejudge(EDITED, [5], [])
        user = fake.calls[-1]["user"]
        self.assertIn("5행 기준 판:", user)
        self.assertNotIn("고친 까닭", user)
        self.assertNotIn("되살리는", user)

    def test_a_revert_is_kept_with_a_note(self) -> None:
        self.round0()
        result, _ = self.rejudge(EDITED, [5], [dict(REVERT)])
        [it] = result["findings"]
        self.assertEqual("표시합니다", it.get("revives"), "되살리는 수정안을 못 알아봤습니다")
        self.assertEqual("맨 위에 표시합니다", it["fix"], "수정안을 지우면 실제 뜻 바뀜 지적도 사라집니다")
        self.assertIn("다른 말로 씀", it["why"])
        [rec] = self.last_row()["fixes"]
        self.assertEqual("표시합니다", rec.get("revives"), "기록에 안 남으면 세션 흉내가 못 봅니다")

    def test_a_fix_that_keeps_the_flagged_word_out_is_plain(self) -> None:
        self.round0()
        other = dict(REVERT, fix="맨 위에 올려 둡니다")
        result, _ = self.rejudge(EDITED, [5], [other])
        self.assertNotIn("revives", result["findings"][0])

    def test_replay_only_uses_judgments_before_the_case(self) -> None:
        self.round0()
        cut = time.time() + 1
        info = {5: {"round": 1, "root": BASE[4]}}
        judge.root_findings(judge.coverage.doc_key(self.doc), info, before=cut - 3600)
        self.assertNotIn("root_found", info[5], "그때 없던 판정을 실었습니다")
        judge.root_findings(judge.coverage.doc_key(self.doc), info, before=cut)
        self.assertEqual("표시합니다", info[5]["root_found"][0]["phrase"])


if __name__ == "__main__":
    unittest.main()
