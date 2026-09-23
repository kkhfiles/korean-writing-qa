"""Codex 가 Claude 와 **같은 훅**으로 검사하는지 고정한다.

**왜 열렸나** — 2026-09-04. 사용자 의도는 「이 PC 에서 AI 가 만드는 모든 문서 산출물이
검사 통과한 한글」인데, 실측하니 Codex 쪽이 절반만 덮여 있었다.

| | Claude Code | Codex(그때) |
|---|---|---|
| 스킬 검사기(확정 표현 8건) | 돎 | 돎 |
| **구조 검사기**(오류의 대부분) | 돎 | **안 돎** |
| **발행 직전 점검** | 돎 | **없음** |

**까닭은 사본이었다** — 어댑터가 확장자·제외 목록을 따로 들고 스킬 검사기만 직접
불렀다. 훅을 고쳐도 Codex 는 안 따라왔다(전날 고친 게이트 수정이 Codex 에 안 갔다).

**고친 방향** — 어댑터는 Codex 도구 이름을 훅이 읽는 모양으로 **옮기기만** 한다.
무엇을 검사할지는 훅 한 곳이 정한다. 이 프로젝트가 사본으로 세 번 당한 뒤의 처방이다.

**payload 모양은 운영 기록으로 확인했다**(2026-09-04) — Codex 세션 기록 3개에서 옛
어댑터의 출력(「한글 문서 최종화 검사 — …」)이 **74회** 나온다(8/24 · 9/2). 즉 훅이 실제로
불리고, 어댑터의 경로 뽑기가 진짜 payload 에서 동작한다. 이 시험이 넣는 필드
(`file_path`·`patch`)가 운영에서 쓰이는 그 필드다.

**⚠️ 아직 못 잰 것** — 새로 붙인 **발행 시점**(`PreToolUse` Bash). 그 경로로 실제 Codex
세션이 지나간 기록이 아직 없다. 다음에 Codex 로 노션 발행을 해 봐야 확인된다.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

#: 작성자 설정 저장소 안에 있다 — 경로는 저장소 밖에서 읽는다.
#: ⛔ 2026-09-07 발행 정리가 이 자리를 `<설정 저장소>` 로 가리면서 이 시험이
#:    **열흘 동안 조용히 건너뛰었다.** 건너뛸 때 돌리는 법을 함께 적는다.
ADAPTER = repo_paths.config_path("scripts", "codex-hook-adapter.py")
GATE = repo_paths.hook("doc-style-gate.py")
HOOKS_TEMPLATE = repo_paths.config_path("codex", "hooks.json")

# 훅이 건너뛰지 않는 자리여야 한다 — Temp·scratchpad 는 제외 대상이다
WORK = Path("P:/d/codex-gate-test")
DOC = ("# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"
       "- 산출물은 해당 폴더에\n")


def fresh_session() -> str:
    """세션마다 새 이름을 준다.

    훅은 「쓰는 순간」 검사를 **세션당 파일 하나에 한 번**만 낸다. 고정 이름을
    쓰면 시험이 첫 실행에만 통과하고 그다음부터 조용히 빈 결과를 받는다
    (실제로 겪었다 — 돌연변이 시험을 돌린 뒤 본 시험이 깨졌다).
    """
    return f"codex-gate-test-{uuid.uuid4().hex[:12]}"


def call_adapter(mode: str, event: str, payload: dict):
    """어댑터를 돌리고 `(종료 코드, 사람이 읽을 말, 막는 글)` 을 낸다.

    ⛔ **종료 코드와 `stderr` 를 같이 본다** — 막기는 그 둘로 온다. `stdout` 만
    읽으면 **막힌 것과 통과한 것이 똑같이 빈 문자열로 보인다**(2026-09-17 에
    실제로 그래서 구멍을 열흘 못 봤다).
    """
    done = subprocess.run(
        [sys.executable, "-X", "utf8", str(ADAPTER), mode, event],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8",
    )
    out = (done.stdout or "").strip()
    said = ""
    if out:
        try:
            said = str(json.loads(out)["hookSpecificOutput"]["additionalContext"])
        except (ValueError, KeyError, TypeError):
            said = out
    return done.returncode, said, (done.stderr or "").strip()


def run_adapter(mode: str, event: str, payload: dict) -> str:
    return call_adapter(mode, event, payload)[1]



def gate_module():
    """게이트를 읽어 온다 — 기대값의 정본은 게이트 한 곳이다."""
    spec = importlib.util.spec_from_file_location(
        "doc_style_gate", repo_paths.hook("doc-style-gate.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gate_notice_head() -> str:
    """게이트가 내는 발행 안내의 **첫 줄**."""
    return gate_module().NOTICE.splitlines()[0].strip()


class CodexUsesTheSameGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # ⛔ 설정 저장소가 없으면 경로가 `None` 이다 — 그대로 `.is_file()` 을 부르면
        #    건너뛰지 않고 터진다. CI 가 이것으로 2026-09-18 부터 닷새 빨강이었다.
        if ADAPTER is None or HOOKS_TEMPLATE is None:
            raise unittest.SkipTest(repo_paths.NO_CONFIG_REPO)
        for path in (ADAPTER, GATE, HOOKS_TEMPLATE):
            if not path.is_file():
                raise unittest.SkipTest(f"없습니다: {path}")
        WORK.mkdir(parents=True, exist_ok=True)
        cls.doc = WORK / "codex-doc.md"
        cls.doc.write_text(DOC, encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        import shutil
        shutil.rmtree(WORK, ignore_errors=True)

    def test_a_written_file_gets_the_structural_check(self) -> None:
        """구조 검사기가 Codex 에서도 돌아야 한다 — 오류의 대부분이 여기서 나온다."""
        said = run_adapter("korean-document-check", "PostToolUse", {
            "tool_name": "Write", "session_id": fresh_session(),
            "tool_input": {"file_path": str(self.doc)}})

        self.assertIn("절단형 종결", said)

    def test_a_patch_gets_the_same_check(self) -> None:
        """Codex 의 주 편집 도구는 `apply_patch` 다 — 파일 이름이 패치 본문에 있다."""
        patch = f"*** Update File: {self.doc}\n@@\n+- 산출물은 해당 폴더에\n"
        said = run_adapter("korean-document-check", "PostToolUse", {
            "tool_name": "apply_patch", "session_id": fresh_session(),
            "tool_input": {"patch": patch}})

        self.assertIn("절단형 종결", said)

    def test_publishing_is_blocked_too(self) -> None:
        """발행 직전에 통과 기록이 없으면 Codex 도 막혀야 한다.

        **무엇이 열려 있었나**(2026-09-17 확인 · 2026-09-18 고침). 게이트는 통과
        기록이 없으면 종료 코드 2 에 사람이 읽을 말을 `stderr` 로 내서 막는다.
        어댑터는 `stdout` 의 JSON 만 꺼내고 **종료 코드를 안 봤다.** 그래서
        Codex 쪽은 **발행이 막히는 순간에 아무 말도 못 받고 막히지도 않았다** —
        쓰기 경로(`PostToolUse`)는 stdout 으로 나와 잘 닿아 눈에 안 띄었다.

        **왜 열흘 동안 몰랐나** — 2026-09-07 발행 정리가 어댑터 경로를
        `<설정 저장소>` 로 가리면서 이 시험이 **건너뛰었다.** 실패가 아니라
        건너뛰기라 아무 데도 안 나타났다. 경로를 되살리자 바로 드러났다.

        ⛔ **종료 코드를 같이 본다** — 막는 글만 보면 「말은 하는데 안 막는」
        상태가 통과한다. 그게 바로 고치기 전 모습이다.
        """
        code, _said, stop = call_adapter("korean-document-check", "PreToolUse", {
            "tool_name": "Bash", "session_id": fresh_session(),
            "tool_input": {"command": f'python notion.py create --file "{self.doc}"'}})

        self.assertEqual(2, code, f"막지 않았습니다 — 낸 말: {stop[:120]}")
        self.assertIn("발행 보류", stop)

    def test_the_block_says_how_to_pass(self) -> None:
        """막는 글에 통과하는 길과 넘기는 길이 같이 적혀 있어야 한다.

        「열쇠 없는 자물쇠」를 안 만든다 — 푸는 길이 없으면 넘기기가 습관이 되고,
        그 뒤로는 어떤 게이트도 안 듣는다. 어댑터가 막는 글을 **잘라서** 넘기면
        Codex 쪽만 푸는 길을 모르게 된다.

        ⛔ 기대값은 게이트에서 가져온다 — 여기 또 적으면 문구가 두 곳이 된다.
        """
        _code, _said, stop = call_adapter("korean-document-check", "PreToolUse", {
            "tool_name": "Bash", "session_id": fresh_session(),
            "tool_input": {"command": f'python notion.py create --file "{self.doc}"'}})

        self.assertIn("finalize-korean-document", stop)
        self.assertIn(gate_module().FORCE, stop)

    def test_the_escape_hatch_actually_opens(self) -> None:
        """적어 둔 넘기기 표시가 Codex 경로에서도 실제로 먹어야 한다.

        막는 글에 푸는 길을 적어 놓고 그 길이 안 열리면 **적어 둔 것이 거짓말**이
        된다. 2026-09-16 에 발행 게이트가 통로를 하나만 두고 배포된 적이 있다.
        """
        command = (f"{gate_module().FORCE} python notion.py create "
                   f'--file "{self.doc}"')
        code, _said, stop = call_adapter("korean-document-check", "PreToolUse", {
            "tool_name": "Bash", "session_id": fresh_session(),
            "tool_input": {"command": command}})

        self.assertEqual(0, code, f"넘기기 표시를 붙였는데 막혔습니다: {stop[:120]}")

    def test_a_source_file_is_left_alone(self) -> None:
        """무엇을 볼지는 훅이 정한다 — 어댑터가 따로 거르지 않는다."""
        code = WORK / "sample.py"
        code.write_text("print('산출물은 해당 폴더에')\n", encoding="utf-8")
        said = run_adapter("korean-document-check", "PostToolUse", {
            "tool_name": "Write", "session_id": fresh_session(),
            "tool_input": {"file_path": str(code)}})

        self.assertEqual(said, "")

    def test_the_adapter_keeps_no_rule_list_of_its_own(self) -> None:
        """사본이 되돌아오면 두 실행기가 다시 갈린다."""
        source = ADAPTER.read_text(encoding="utf-8")

        self.assertNotIn("KOREAN_SOURCE_EXTENSIONS", source)
        self.assertNotIn("KOREAN_SOURCE_SKIP_RE", source)
        self.assertIn("DOC_STYLE_GATE", source)

    def test_both_events_are_wired_in_the_codex_template(self) -> None:
        """쓰는 순간만 걸고 발행을 안 걸면 공유 자료가 그대로 나간다."""
        data = json.loads(HOOKS_TEMPLATE.read_text(encoding="utf-8"))
        wired = {event for event, groups in data["hooks"].items()
                 for group in groups for hook in group.get("hooks", [])
                 if "korean-document-check" in hook.get("command", "")}

        self.assertEqual(wired, {"PreToolUse", "PostToolUse"})

    def test_a_missing_gate_is_announced(self) -> None:
        """훅이 없으면 조용히 넘어가지 않는다 — 어제 Claude 쪽에서 고친 그 실패다."""
        spec = importlib.util.spec_from_file_location("codex_adapter", ADAPTER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = module.DOC_STYLE_GATE
        module.DOC_STYLE_GATE = original.with_name("no-such-gate.py")
        try:
            with tempfile.TemporaryDirectory():
                import io
                import contextlib
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    module.run_korean_document_check("PostToolUse", {
                        "tool_name": "Write",
                        "tool_input": {"file_path": str(self.doc)}})
                said = buffer.getvalue()
        finally:
            module.DOC_STYLE_GATE = original

        self.assertIn("훅 없음", said)
