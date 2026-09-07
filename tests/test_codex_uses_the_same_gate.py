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

ADAPTER = Path("<설정 저장소>/scripts/codex-hook-adapter.py")
GATE = repo_paths.hook("doc-style-gate.py")
HOOKS_TEMPLATE = Path("<설정 저장소>/codex/hooks.json")

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


def run_adapter(mode: str, event: str, payload: dict) -> str:
    done = subprocess.run(
        [sys.executable, "-X", "utf8", str(ADAPTER), mode, event],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True, text=True, encoding="utf-8",
    )
    out = (done.stdout or "").strip()
    if not out:
        return ""
    try:
        return str(json.loads(out)["hookSpecificOutput"]["additionalContext"])
    except (ValueError, KeyError, TypeError):
        return out


class CodexUsesTheSameGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
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

    def test_publishing_is_checked_too(self) -> None:
        """발행 직전 점검이 Codex 에는 아예 없었다."""
        said = run_adapter("korean-document-check", "PreToolUse", {
            "tool_name": "Bash", "session_id": fresh_session(),
            "tool_input": {"command": f'python notion.py create --file "{self.doc}"'}})

        self.assertIn("발행 전 점검", said)

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
