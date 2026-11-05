"""공개판 최소 호출부 — `llm_playbook` 이 없는 PC 에서 2층 판정기와 발행 게이트가 Claude 를 부를 수 있게.

2026-11-02 점검: 판정기가 비공개 `llm_playbook` 에만 기대어, 공개판을 받은 사람에게는 「백엔드 없음」으로 끝났다.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import judge_layer2 as judge  # noqa: E402
import layer2_client  # noqa: E402

_find = importlib.util.find_spec


def no_playbook(name, *a, **k):
    return None if name.split(".")[0] == "llm_playbook" else _find(name, *a, **k)


class FallbackTests(unittest.TestCase):

    def test_without_playbook_the_judge_uses_the_bundled_client(self) -> None:
        def missing(_which):
            raise ModuleNotFoundError("No module named 'llm_playbook'")
        with unittest.mock.patch.object(judge.probe, "load_client", missing), \
                unittest.mock.patch.object(layer2_client, "available", lambda: (True, "")):
            call, parse = judge.load_backend("claude")
            self.assertIs(layer2_client.call_messages, call)
            self.assertIs(layer2_client.parse_json_from_text, parse)
            self.assertIsNone(judge.load_backend("codex"), "Codex 는 아직 최소 호출부가 없음")
        with unittest.mock.patch.object(judge.probe, "load_client", missing), \
                unittest.mock.patch.object(layer2_client, "available", lambda: (False, "없음")):
            self.assertIsNone(judge.load_backend("claude"), "부를 수 없으면 백엔드 없음(세션이 직접 판정)")

    def test_auto_picks_claude_only_when_the_bundled_client_can_run(self) -> None:
        with unittest.mock.patch.object(importlib.util, "find_spec", no_playbook):
            with unittest.mock.patch.object(layer2_client, "available", lambda: (True, "")):
                self.assertEqual("claude", judge.pick_backend("auto"))
            with unittest.mock.patch.object(layer2_client, "available", lambda: (False, "없음")):
                self.assertIsNone(judge.pick_backend("auto"))

    def test_the_gate_asks_for_a_judgment_only_when_the_judge_can_run(self) -> None:
        spec = importlib.util.spec_from_file_location("gate_for_client", ROOT / "hooks" / "doc-style-gate.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)

        def find(name, *a, **k):
            if name.split(".")[0] in ("llm_playbook",):
                return None
            return object() if name == "claude_agent_sdk" else _find(name, *a, **k)
        with unittest.mock.patch.object(importlib.util, "find_spec", find), \
                unittest.mock.patch("shutil.which", lambda _n: "C:/bin/claude.exe"):
            self.assertTrue(gate.judge_backend_ready())
        with unittest.mock.patch.object(importlib.util, "find_spec", find), \
                unittest.mock.patch("shutil.which", lambda _n: None), \
                unittest.mock.patch.dict("os.environ", {"CLAUDE_CLI_PATH": ""}):
            self.assertFalse(gate.judge_backend_ready(), "claude 가 없으면 열쇠 없는 자물쇠")

    def test_json_is_found_in_fences_and_prose(self) -> None:
        self.assertEqual({"a": 1}, layer2_client.parse_json_from_text('앞말 ```json\n{"a": 1}\n``` 뒷말'))
        self.assertEqual([1, 2], layer2_client.parse_json_from_text("결과: [1, 2] 끝"))
        self.assertIsNone(layer2_client.parse_json_from_text("JSON 없음"))

    def test_a_long_system_prompt_goes_through_a_file(self) -> None:
        """Windows 명령줄 길이 제한 — 판정 시스템 프롬프트는 수만 자다."""
        seen = {}

        class Opts:
            def __init__(self, **kw):
                seen.update(kw)

        class Result:
            is_error, result, usage, total_cost_usd = False, "{}", {}, 0.0

        async def query(prompt, options):
            seen["file_text"] = Path(seen["system_prompt"]["path"]).read_text(encoding="utf-8")
            yield Result()
        fake = unittest.mock.MagicMock(ClaudeAgentOptions=Opts, query=query, ResultMessage=Result,
                                       AssistantMessage=type("A", (), {}), TextBlock=type("T", (), {}))
        with unittest.mock.patch.dict(sys.modules, {"claude_agent_sdk": fake}):
            layer2_client.call_messages(model="opus", system="가" * 9000, user="문서")
        self.assertEqual("file", seen["system_prompt"]["type"])
        self.assertEqual("가" * 9000, seen["file_text"])
        self.assertFalse(Path(seen["system_prompt"]["path"]).exists(), "임시 파일을 지움")
        self.assertEqual([], seen["setting_sources"], "부르는 사람의 지시 문서를 싣지 않음")
        self.assertEqual([], seen["tools"])


class Fake:
    """claude_agent_sdk 흉내 — 옵션과 호출 순간의 환경 변수를 남긴다."""

    def __init__(self, stop="end_turn"):
        self.seen = {}
        seen = self.seen

        class Opts:
            def __init__(self, **kw):
                seen["opts"] = kw

        class Result:
            is_error, result, usage, total_cost_usd, stop_reason = False, "[]", {}, 0.0, stop

        async def query(prompt, options):
            import os
            seen["key_at_call"] = os.environ.get("ANTHROPIC_API_KEY")
            yield Result()
        self.module = unittest.mock.MagicMock(ClaudeAgentOptions=Opts, query=query, ResultMessage=Result,
                                              AssistantMessage=type("A", (), {}), TextBlock=type("T", (), {}))

    def call(self, **kw):
        with unittest.mock.patch.dict(sys.modules, {"claude_agent_sdk": self.module}):
            return layer2_client.call_messages(model="opus", system="s", user="문서", **kw)


class LevelAndKeyTests(unittest.TestCase):
    """2026-11-04 — 공개판이 사고 깊이를 버려 검사 단계가 모델만 바꿨고, API 키 환경 변수가 있으면 묻지 않고
    그 키로 과금될 수 있었다(사용자 결정 「물어보게」)."""

    def setUp(self) -> None:
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.env = unittest.mock.patch.dict("os.environ", {
            "KOREAN_QA_API_KEY_CHOICE_FILE": str(Path(self.tmp.name) / "choice.json")}, clear=False)
        self.env.start()
        import os
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", layer2_client.CHOICE_ENV):
            os.environ.pop(k, None)

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def test_effort_reaches_the_cli_and_stop_reason_comes_back(self) -> None:
        f = Fake(stop="max_tokens")
        r = f.call(effort="low")
        self.assertEqual("low", f.seen["opts"].get("effort"), "사고 깊이를 CLI 에 넘기지 않았습니다")
        self.assertEqual("max_tokens", r["stop_reason"], "잘림 신호를 돌려주지 않았습니다")
        f.call()
        self.assertNotIn("effort", f.seen["opts"], "단계가 사고 깊이를 안 줬는데 넘겼습니다")

    def test_an_api_key_without_a_choice_is_not_used(self) -> None:
        import os
        os.environ["ANTHROPIC_API_KEY"] = "dummy-value"
        with self.assertRaises(layer2_client.ApiKeyChoiceNeeded):
            Fake().call()

    def test_subscription_hides_the_key_only_during_the_call(self) -> None:
        import os
        os.environ["ANTHROPIC_API_KEY"] = "dummy-value"
        layer2_client.save_choice("subscription")
        f = Fake()
        f.call()
        self.assertIsNone(f.seen["key_at_call"], "구독을 골랐는데 키가 CLI 로 넘어갔습니다")
        self.assertEqual("dummy-value", os.environ.get("ANTHROPIC_API_KEY"), "호출 뒤 키를 되돌리지 않았습니다")

    def test_api_choice_keeps_the_key(self) -> None:
        import os
        os.environ["ANTHROPIC_API_KEY"] = "dummy-value"
        layer2_client.save_choice("api")
        f = Fake()
        f.call()
        self.assertEqual("dummy-value", f.seen["key_at_call"])

    def test_the_judge_stops_and_asks_once(self) -> None:
        import contextlib
        import io
        import os
        import tempfile
        os.environ["ANTHROPIC_API_KEY"] = "dummy-value"
        doc = Path(self.tmp.name) / "d.md"
        doc.write_text("원인을 알 수 없었습니다.\n", encoding="utf-8")
        f = Fake()
        saved = judge.LOG
        judge.LOG = Path(tempfile.mkdtemp()) / "calls.jsonl"
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out), unittest.mock.patch.dict(sys.modules, {"claude_agent_sdk": f.module}):
                rc = judge.main([str(doc)], backend=(layer2_client.call_messages, layer2_client.parse_json_from_text))
            self.assertEqual(7, rc, out.getvalue())
            self.assertIn("--api-key-use", out.getvalue())
            with contextlib.redirect_stdout(io.StringIO()), \
                    unittest.mock.patch.dict(sys.modules, {"claude_agent_sdk": f.module}):
                rc = judge.main([str(doc), "--api-key-use", "subscription"],
                                backend=(layer2_client.call_messages, layer2_client.parse_json_from_text))
                self.assertEqual(0, rc)
                rc = judge.main([str(doc), "--since"],
                                backend=(layer2_client.call_messages, layer2_client.parse_json_from_text))
            self.assertEqual(0, rc, "한 번 고른 뒤에도 다시 물었습니다")
        finally:
            judge.LOG = saved


if __name__ == "__main__":
    unittest.main()
