"""Codex 판정 호출이 실패하면 무엇 때문인지(네트워크 · 한도 · 인증)가 오류 글에 남는지 본다 — 모델은 안 부른다.

(2026-10-14~10-20) Codex 에이전트 세션(샌드박스 workspace-write · network_access false)에서 `--backend codex` 판정이
아홉 번 모두 「모든 모델 시도 실패」 한 줄로 끝났다. `codex_http` 는 마지막 실패 글(`detail`)과 갈래(`kind`)를 돌려주는데
판정기가 `error` 만 옮겨, 같은 세션의 다른 접속이 연결 거부(WinError 10061)로 막힌 것을 보고서야 네트워크 차단으로 짐작했다.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import probe_layer2_kinds as probe  # noqa: E402

FAIL = "모든 모델 시도 실패 (all models in fallback chain failed)"


def failing(detail: str, kind=None):
    return lambda *a, **k: {"text": "", "error": FAIL, "kind": kind, "detail": detail, "attempts": []}


# llm_playbook 은 비공개 조직 저장소라 CI 가 설치하지 못한다 — 없으면 건너뛴다(로컬 전체 시험이 본다).
# 안 건너뛰면 CI 가 ModuleNotFoundError 로 붉었다(2026-10-30 확인).
HAS_PLAYBOOK = importlib.util.find_spec("llm_playbook") is not None


@unittest.skipUnless(HAS_PLAYBOOK, "llm_playbook 이 없는 PC — Codex 클라이언트 경로를 못 부른다")
class CodexErrorDetailTests(unittest.TestCase):

    def call(self, fake):
        from llm_playbook.backends import codex_http
        call, _ = probe.load_client("codex")
        with patch.object(codex_http, "call", fake):
            with self.assertRaises(RuntimeError) as cm:
                call(model="sol-high", system="s", user="u", timeout=10)
        return str(cm.exception)

    def test_네트워크_오류는_까닭과_샌드박스_안내가_남는다(self):
        msg = self.call(failing("Network error connecting to Codex backend: [WinError 10061] 연결 거부"))
        self.assertIn("WinError 10061", msg)
        self.assertLess(msg.index("샌드박스"), 60, "사다리가 250자에서 자르므로 안내가 앞에 있어야 합니다")

    def test_한도는_갈래와_글이_남고_샌드박스_안내는_없다(self):
        msg = self.call(failing("Rate limit exceeded (HTTP 429). resets_in_seconds=2946", kind="usage"))
        self.assertIn("usage", msg)
        self.assertIn("HTTP 429", msg)
        self.assertNotIn("샌드박스", msg)

    def test_자세한_글이_없으면_예전과_같다(self):
        self.assertEqual(self.call(failing("")), f"Codex 호출 실패(sol-high): {FAIL}")


if __name__ == "__main__":
    unittest.main()
