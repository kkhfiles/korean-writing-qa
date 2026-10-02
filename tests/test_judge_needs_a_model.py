"""판정기는 Claude 가 없으면 Codex 를 부르고, 게이트는 부를 모델이 있을 때만 판정을 요구한다.

**왜 있나.** 2026-10-02 까지 판정기는 Claude 로만 불렀는데 게이트는 `llm_playbook` 만 있으면
판정 기록을 요구했다. Claude 가 없는 PC 에서는 push 가 막히고 판정을 돌릴 길이 없었다
(「열쇠 없는 자물쇠」). 판정기에 Codex 경로를 넣고, 게이트는 판정기와 같은 기준
(`llm_playbook.ladder.available`)으로 「부를 모델이 있나」를 본다.

사다리는 가짜 모듈로 바꿔 끼운다 — 이 PC 의 로그인 상태에 따라 결과가 바뀌면 안 된다.
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import judge_layer2 as judge  # noqa: E402

HOOK = ROOT / "hooks" / "doc-style-gate.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("doc_style_gate_model", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeLadder:
    """`llm_playbook` · `llm_playbook.ladder` 를 가짜로 — `ready` 에 든 백엔드만 쓸 수 있다."""

    def __init__(self, ready):
        self.ready = set(ready)
        self.saved = {}

    def __enter__(self):
        top = types.ModuleType("llm_playbook")
        top.__spec__ = importlib.machinery.ModuleSpec("llm_playbook", None)
        top.__path__ = []
        ladder = types.ModuleType("llm_playbook.ladder")
        ladder.__spec__ = importlib.machinery.ModuleSpec("llm_playbook.ladder", None)
        ladder.available = lambda name: (name in self.ready, "" if name in self.ready else "시험")
        top.ladder = ladder
        for name, mod in (("llm_playbook", top), ("llm_playbook.ladder", ladder)):
            self.saved[name] = sys.modules.get(name)
            sys.modules[name] = mod
        return self

    def __exit__(self, *exc):
        for name, mod in self.saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


class PickBackendTests(unittest.TestCase):
    def test_claude_first(self) -> None:
        with FakeLadder({"claude", "codex"}):
            self.assertEqual("claude", judge.pick_backend("auto"))

    def test_codex_when_claude_is_missing(self) -> None:
        with FakeLadder({"codex"}):
            self.assertEqual("codex", judge.pick_backend("auto"))

    def test_none_when_neither(self) -> None:
        with FakeLadder(set()):
            self.assertIsNone(judge.pick_backend("auto"))

    def test_explicit_choice_wins(self) -> None:
        with FakeLadder({"claude"}):
            self.assertEqual("codex", judge.pick_backend("codex"))


class CodexDefaultModelTests(unittest.TestCase):
    """Codex 로 부를 때 Claude 별칭(opus)을 넘기면 호출이 실패한다 — 기본 모델이 갈려야 한다."""

    def run_main(self, ready):
        seen = {}

        def call(**kw):
            seen.update(kw)
            return {"text": "[]", "model": kw["model"], "usage": {}}

        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "doc.md"
            doc.write_text("# 제목\n\n본문입니다.\n", encoding="utf-8")
            saved = judge.LOG
            judge.LOG = Path(tmp) / "log.jsonl"
            try:
                with FakeLadder(ready), redirect_stdout(io.StringIO()):
                    rc = judge.main([str(doc)], backend=(call, lambda t: []))
            finally:
                judge.LOG = saved
        return rc, seen.get("model")

    def test_codex_gets_its_own_model(self) -> None:
        self.assertEqual((0, judge.CODEX_MODEL), self.run_main({"codex"}))

    def test_claude_keeps_opus(self) -> None:
        self.assertEqual((0, judge.DEFAULT_MODEL), self.run_main({"claude", "codex"}))


class GateAsksOnlyWhenAModelExistsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = load_gate()
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.judge = tmp / "judge_layer2.py"
        self.judge.write_text("# 시험용\n", encoding="utf-8")
        skill = tmp / "SKILL.md"
        skill.write_text(f"python -X utf8 {self.judge.as_posix()} <수정문>\n", encoding="utf-8")
        self.gate.SKILL_MD = skill
        self.saved_env = self.gate.os.environ.pop("KOREAN_QA_JUDGE", None)

    def tearDown(self) -> None:
        if self.saved_env is not None:
            self.gate.os.environ["KOREAN_QA_JUDGE"] = self.saved_env
        self.tmp.cleanup()

    def test_no_model_means_no_demand(self) -> None:
        with FakeLadder(set()):
            self.assertIsNone(self.gate.judge_command())

    def test_codex_only_pc_is_asked(self) -> None:
        with FakeLadder({"codex"}):
            self.assertEqual(self.judge, self.gate.judge_command())

    def test_claude_only_pc_is_asked(self) -> None:
        with FakeLadder({"claude"}):
            self.assertEqual(self.judge, self.gate.judge_command())


if __name__ == "__main__":
    unittest.main()
