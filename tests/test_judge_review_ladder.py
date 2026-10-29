"""판정 호출은 사다리 `review` 한 칸으로 — 막히면 다른 모델로 넘기지 않고 바로 실패한다(2026-10-19).

**왜 있나.** 판정기는 점검표로 잰 모델이어야 그 값이 산다(`docs/calibration-20260929.md`). 그래서 엔진이
막혔을 때 다른 모델로 넘기면 안 되고, 그렇다고 막힌 엔진을 매번 두드려서도 안 된다. 사다리 `review` 는
폴백 없이 엔진 상태만 본다 — 막힌 엔진은 부르지 않고 「limited」로 바로 올리며, 한도로 실패하면 막힘을
적고, 답하면 지운다. 모델 이름과 부르는 길(탐침과 같은 클라이언트)은 그대로다.

모델은 부르지 않는다 — 클라이언트는 가짜이고 엔진 상태 함수는 바꿔 끼운다.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import judge_layer2 as judge  # noqa: E402

try:
    from llm_playbook import credits as lp_credits, engine_state, models as lp_models  # noqa: E402
    HAS_REVIEW = "review" in lp_models.ladders()
except Exception:  # noqa: BLE001 — 사다리가 없는 PC 에서는 이 시험을 건너뛴다
    HAS_REVIEW = False


class FakeClient:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    def call(self, **kw):
        self.calls.append(kw)
        if self.error is not None:
            raise self.error
        return self.answer


@unittest.skipUnless(HAS_REVIEW, "llm_playbook 에 사다리 review 가 없음 — 감싸지 않는 길")
class JudgeReviewLadderTests(unittest.TestCase):
    def setUp(self):
        self.blocks, self.oks = [], []
        self.blocked = {}
        p = [patch.dict(os.environ, {"LLM_PLAYBOOK_EVENT_LOG": "off"}),
             patch.object(engine_state, "is_blocked", lambda e, now=None: e in self.blocked),
             patch.object(engine_state, "blocked", lambda e: self.blocked.get(e)),
             patch.object(engine_state, "record_block",
                          lambda e, kind, **kw: self.blocks.append((e, kind)) or None),
             # 크레딧 키가 있는 PC 에서는 구독이 막혀도 API 로 부른다(llm_playbook 2026-10-22) — 이 시험은
             # 「크레딧 없음」을 고정해 막힌 엔진을 안 부르는지 본다
             patch.object(lp_credits, "pick", lambda *a, **kw: None),
             patch.object(engine_state, "record_ok", lambda e: self.oks.append(e)),
             # GPT 5시간 통이 가득 — review 는 GPT 몫 남기기(reserve)를 안 받으므로 그래도 codex 를 부른다
             patch.object(engine_state, "util", lambda e: {"five_hour": 0.99, "at": __import__("time").time()})]
        for x in p:
            x.start()
            self.addCleanup(x.stop)

    def wrap(self, which, fake):
        call, parse = judge.via_review(which, (fake.call, "파서"))
        self.assertEqual(parse, "파서")
        return call

    def test_답하면_모델과_인자를_그대로_넘기고_막힘을_지운다(self):
        fake = FakeClient({"text": "[]", "model": "claude-opus-x", "cost_usd": 0.5, "usage": {"input_tokens": 3}})
        r = self.wrap("claude", fake)(model="opus", system="규칙", user="문서", max_tokens=12000,
                                       temperature=0, timeout=900)
        self.assertEqual(r, {"text": "[]", "model": "claude-opus-x", "cost_usd": 0.5,
                             "usage": {"input_tokens": 3}})
        self.assertEqual(fake.calls, [{"model": "opus", "system": "규칙", "user": "문서", "max_tokens": 12000,
                                       "timeout": 900, "temperature": 0}])
        self.assertEqual(self.oks, ["claude"])

    def test_막힌_엔진은_부르지_않고_limited_로_바로_실패(self):
        self.blocked["claude"] = {"kind": "usage", "until": 1_900_000_000}
        fake = FakeClient({"text": "[]"})
        with self.assertRaisesRegex(RuntimeError, "claude limited"):
            self.wrap("claude", fake)(model="opus", system="s", user="u", timeout=10)
        self.assertEqual(fake.calls, [])

    def test_한도로_실패하면_막힘을_적고_실패(self):
        fake = FakeClient(error=RuntimeError("You've hit your weekly limit · resets 10am"))
        with self.assertRaisesRegex(RuntimeError, "limited"):
            self.wrap("claude", fake)(model="opus", system="s", user="u", timeout=10)
        self.assertEqual(self.blocks, [("claude", "usage")])
        self.assertEqual(len(fake.calls), 1)     # 다른 모델로 안 넘김 — 한 번만 불렀다

    def test_빈_답은_지적_0건이_아니라_실패(self):
        fake = FakeClient({"text": "  ", "model": "m"})
        with self.assertRaises(RuntimeError):
            self.wrap("claude", fake)(model="opus", system="s", user="u", timeout=10)

    def test_Codex_는_금액_없음(self):
        fake = FakeClient({"text": "[]", "model": "gpt-sol-high", "cost_usd": None, "usage": {}})
        r = self.wrap("codex", fake)(model="sol-high", system="s", user="u", timeout=10)
        self.assertIsNone(r["cost_usd"])
        self.assertEqual(fake.calls[0]["model"], "sol-high")
        self.assertEqual(self.oks, ["codex"])


    def test_사용량_보류는_실제로_부르는_모델의_칸으로_가른다(self):
        """(2026-10-20) 첫 등급 칸(astra)을 골라 sol-high 를 부르면서 GPT 5시간 사용률 보류로 막혔다."""
        fake = FakeClient({"text": "[]", "model": "gpt-astra", "cost_usd": None, "usage": {}})
        with self.assertRaisesRegex(RuntimeError, "codex"):
            self.wrap("codex", fake)(model="astra-medium", system="s", user="u", timeout=10)
        self.assertEqual(fake.calls, [], "보류할 모델(astra)인데 불렀습니다")

    def test_판정기가_고른_클라이언트를_감싼다(self):
        client = (FakeClient({"text": "[]"}).call, "파서")
        with patch.object(judge.probe, "load_client", lambda which: client):
            got = judge.load_backend("claude")
        self.assertIsNot(got[0], client[0])
        self.assertEqual(got[1], "파서")

    def test_사다리_표에_review_가_없으면_감싸지_않는다(self):
        client = (lambda **kw: kw, "파서")
        with patch.object(lp_models, "ladders", lambda cfg=None: {}):
            self.assertIs(judge.via_review("claude", client), client)


class OldPlaybookTests(unittest.TestCase):
    def test_llm_playbook_이_없으면_감싸지_않는다(self):
        client = (lambda **kw: kw, "파서")
        with patch.dict(sys.modules, {"llm_playbook": None}):
            self.assertIs(judge.via_review("claude", client), client)


if __name__ == "__main__":
    unittest.main()
