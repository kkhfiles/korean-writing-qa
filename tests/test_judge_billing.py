"""이 저장소의 Claude 판정과 측정이 API 크레딧이 아니라 구독으로 나가는지 본다 — 모델은 안 부른다.

(2026-11-05 사용자 「여기선 api 쓰지 말고 구독 쓰고」) `llm_playbook` 기본값은 크레딧 먼저라, 판정기와 측정
도구가 기본값으로 부르면 크레딧에서 나간다. 그 전 측정 약 38달러가 그렇게 나갔다.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import probe_layer2_kinds as probe  # noqa: E402


@unittest.skipIf(importlib.util.find_spec("llm_playbook") is None, "llm_playbook 없음(공개판)")
class SubscriptionBillingTests(unittest.TestCase):

    def test_the_claude_client_always_asks_for_the_subscription(self) -> None:
        from llm_playbook.backends import claude_sdk
        seen = {}
        real = claude_sdk.call_messages

        def fake(**kw):
            seen.update(kw)
            return {"text": "[]"}

        claude_sdk.call_messages = fake
        try:
            call, _ = probe.load_client("claude")
            call(model="opus", system="s", user="u", max_tokens=10, timeout=1)
        finally:
            claude_sdk.call_messages = real
        self.assertEqual("subscription", seen.get("billing"), "판정기와 측정 도구가 모두 이 입구로 부릅니다(judge.load_backend)")


if __name__ == "__main__":
    unittest.main()
