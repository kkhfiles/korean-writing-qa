"""훅 실행 결과를 「막혔나 · 사람이 읽을 말」로 읽는다 — 게이트를 부르는 시험이 함께 쓴다.

게이트는 PreToolUse 에서 `permissionDecision: deny` JSON(종료 코드 0)으로 막는다. Codex 0.159.1 이
종료 코드 2 를 막음으로 안 받고 명령을 실행했기 때문이다(2026-10-01 실측). 시험은 막힘을 종료
코드 2 로 읽어 왔으므로 여기서 두 모양을 하나로 맞춘다 — 막혔으면 2, 말은 거부 사유와 stderr.
"""
from __future__ import annotations

import json


def read(done) -> tuple[int, str]:
    """`subprocess.CompletedProcess`(text 모드) → (막혔으면 2 · 아니면 종료 코드, 사람이 읽을 말)."""
    out, err = (done.stdout or ""), (done.stderr or "")
    text = out.strip()
    if text.startswith("{"):
        try:
            spec = json.loads(text).get("hookSpecificOutput") or {}
        except (ValueError, AttributeError):
            spec = {}
        if spec.get("permissionDecision") == "deny":
            return 2, str(spec.get("permissionDecisionReason") or "") + ("\n" + err if err else "")
    return done.returncode, out + err
