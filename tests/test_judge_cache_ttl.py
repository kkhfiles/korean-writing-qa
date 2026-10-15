"""판정 호출이 5분 캐시로 불리는지 본다 — 모델은 안 부른다.

(2026-10-15) 구독 로그인에서 Claude Code 는 프롬프트 캐시를 1시간으로 쓴다(쓰기 단가가 입력의 2배). 판정 호출의
93% 가 앞 호출 5분 안에 이어져, 5분(1.25배)이면 실사용 기록 기준 환산 비용이 20% 준다. 판정 결과와는 무관하다.

**지키는 것**

- 환경 변수가 없으면 판정 호출 전에 5분으로 정한다(CLI 는 이 프로세스의 환경을 물려받는다)
- 사용자가 이미 정한 값은 바꾸지 않는다
- 호출 기록에 어떤 유지 시간으로 불렀는지 남는다 — 적용 전후 비용을 기록으로 가른다
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402


class CacheTtlTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved_log, judge.LOG = judge.LOG, self.dir / "calls.jsonl"
        self.saved_env = os.environ.pop(judge.CACHE_TTL_ENV, None)
        self.doc = self.dir / "d.md"
        self.doc.write_text("# 소개\n\n업무 목록은 매일 갱신됩니다.\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG = self.saved_log
        os.environ.pop(judge.CACHE_TTL_ENV, None)
        if self.saved_env is not None:
            os.environ[judge.CACHE_TTL_ENV] = self.saved_env
        self.tmp.cleanup()

    def judge_once(self) -> dict:
        seen = {}
        fake = FakeBackend([])
        call = fake.call

        def spy(**kw):
            seen["ttl"] = os.environ.get(judge.CACHE_TTL_ENV)
            return call(**kw)
        judge.judge(self.doc, "opus", 10, (spy, fake.parse))
        row = json.loads(judge.LOG.read_text(encoding="utf-8").splitlines()[-1])
        return {"at_call": seen["ttl"], "logged": row.get("cache_ttl")}

    def test_the_call_runs_with_a_five_minute_cache(self) -> None:
        self.assertEqual({"at_call": "5m", "logged": "5m"}, self.judge_once())

    def test_a_value_the_user_set_is_kept(self) -> None:
        os.environ[judge.CACHE_TTL_ENV] = "1h"
        self.assertEqual({"at_call": "1h", "logged": "1h"}, self.judge_once())


if __name__ == "__main__":
    unittest.main()
