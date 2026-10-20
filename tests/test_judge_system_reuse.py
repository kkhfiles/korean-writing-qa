"""재판정이 그 문서의 직전 호출이 쓴 시스템 프롬프트를 다시 쓰고, 그 뒤 받은 사용자 답은 사용자 메시지 끝에 붙이는지 본다
— 모델은 안 부른다.

(2026-10-20 세션 흉내) 시스템 프롬프트 끝의 「사용자가 이미 답한 것」은 사람 확인에 답하면 바뀐다. 0회차 직후 답 하나로
첫 재판정이 캐시된 시스템 프롬프트(약 16k 토큰)를 처음부터 다시 써, 6회 중 4회가 호출당 약 0.08~0.10달러를 더 썼다.

**지키는 것**

- 답이 늘어도 4분 안의 재판정은 직전 시스템 프롬프트 그대로 · 새 답은 사용자 메시지 끝
- 직전 호출이 식었거나 규칙이 바뀌었으면 지금 시스템 프롬프트 · 덧붙임 없음
- 전체 판정은 늘 지금 시스템 프롬프트(사용자 메시지는 탐침과 같은 글)
- 재생이 같은 입력을 만든다(남겨 둔 답 글과 덧붙임)
- 오래된 기록은 지워진다(사용자 답 원문이 들어 있다)
"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import replay_rejudge as replay  # noqa: E402
from test_rejudge_cap import BASE, _Base  # noqa: E402
from test_rejudge_context import Scripted  # noqa: E402

EDITED = BASE[:4] + ["마감이 가까운 업무를 맨 위에 둡니다."]
ANSWER = {"category": "업무에서 쓰는 말로 쓰기", "phrase": "갱신됩니다", "fix": "바뀝니다", "answer": "그대로",
          "kind": "그대로"}


class SystemReuseTests(_Base):

    def full(self) -> Scripted:
        self.write(BASE)
        fake = Scripted([[]])
        judge.judge(self.doc, "opus", 10, fake.pair())
        return fake

    def answer(self) -> None:
        judge.coverage.DECISIONS.write_text(json.dumps(dict(ANSWER, when=time.time() + 1), ensure_ascii=False) + "\n",
                                            encoding="utf-8")

    def rejudge(self) -> Scripted:
        self.write(EDITED)
        fake = Scripted([[]])
        judge.judge(self.doc, "opus", 10, fake.pair(), [5], BASE)
        return fake

    def test_a_new_answer_keeps_the_system_and_rides_in_the_user_message(self) -> None:
        round0 = self.full()
        self.answer()
        fake = self.rejudge()
        self.assertEqual(round0.calls[0]["system"], fake.calls[0]["system"],
                         "답 하나로 시스템 프롬프트를 바꾸면 16k 를 처음부터 다시 씁니다")
        self.assertNotIn("갱신됩니다", fake.calls[0]["system"])
        self.assertIn("사용자가 새로 답한 것", fake.calls[0]["user"])
        self.assertIn("「갱신됩니다」 · 판정기 제안 「바뀝니다」 · 사용자: 그대로", fake.calls[0]["user"])

    def test_without_a_new_answer_nothing_is_added(self) -> None:
        round0 = self.full()
        fake = self.rejudge()
        self.assertEqual(round0.calls[0]["system"], fake.calls[0]["system"])
        self.assertNotIn("새로 답한 것", fake.calls[0]["user"])

    def test_a_stale_system_is_not_reused(self) -> None:
        self.full()
        self.answer()
        with mock.patch.object(judge, "SYSTEM_FRESH", -1):
            fake = self.rejudge()
        self.assertIn("갱신됩니다", fake.calls[0]["system"], "식은 시스템 프롬프트 대신 지금 것이어야 합니다")
        self.assertNotIn("새로 답한 것", fake.calls[0]["user"])

    def test_changed_rules_are_not_reused(self) -> None:
        self.full()
        self.answer()
        real = judge.probe.rules_for
        with mock.patch.object(judge.probe, "rules_for", lambda arm: real(arm) + "\n새 규칙"):
            fake = self.rejudge()
        self.assertIn("새 규칙", fake.calls[0]["system"], "규칙이 바뀌었는데 옛 시스템 프롬프트를 썼습니다")

    def test_a_full_judgment_always_uses_the_current_system(self) -> None:
        self.full()
        self.answer()
        fake = self.full()
        self.assertIn("갱신됩니다", fake.calls[0]["system"])
        self.assertEqual(judge.probe.USER.format(document=judge.probe.numbered("\n".join(BASE))),
                         fake.calls[0]["user"], "전체 판정의 사용자 메시지가 탐침과 달라졌습니다")

    def test_the_replay_builds_the_same_input(self) -> None:
        self.full()
        self.answer()
        live = self.rejudge()
        case = [c for c in replay.load_cases(judge.replay_dir())][-1]
        fake = Scripted([[]])
        replay.replay(case, case["context"], fake.pair(), "opus")
        self.assertEqual(live.calls[0]["system"], fake.calls[0]["system"])
        self.assertEqual(live.calls[0]["user"], fake.calls[0]["user"])

    def test_old_records_are_removed(self) -> None:
        self.full()
        stale = judge._system_file("다른 문서")
        stale.write_text("{}", encoding="utf-8")
        old = time.time() - judge.SYSTEM_KEEP - 10
        os.utime(stale, (old, old))
        self.full()
        self.assertFalse(stale.exists(), "오래된 기록이 남았습니다 — 사용자 답 원문이 오래 남습니다")


if __name__ == "__main__":
    unittest.main()
