"""2층 판정기가 모델을 부르는 최소 호출부 — `llm_playbook` 이 없는 PC(공개판을 받은 사람)용.

이 PC 의 정본은 `llm_playbook.backends`(비공개 저장소)다. 공개판을 받은 사람에게는 그것이 없어 판정기가
「백엔드 없음」(종료 코드 3)으로 끝났고, 이 저장소의 강점(문맥 판정)이 통째로 전달되지 않았다(2026-11-02 점검).
그래서 `llm_playbook` 을 못 불러올 때만 공개 패키지 `claude-agent-sdk` 로 설치된 Claude Code 를 부른다.

- **부르는 모양은 `llm_playbook.backends.claude_sdk.call_messages` 와 같게** — 판정기가 호출부를 바꿔 끼울 뿐
  프롬프트와 결과 처리는 그대로다(잰 것과 도는 것이 같아야 한다)
- **도구 없음, 한 턴, 설정 파일을 읽지 않음** — 판정은 파일을 읽을 일이 없다. 설정을 읽게 두면 부르는 사람의
  지시 문서(CLAUDE.md 등)가 매번 실려 입력이 몇 배로 늘고 캐시가 안 붙는다(llm_playbook 실측 2026-09-10)
- **긴 시스템 프롬프트는 파일로 넘김** — 명령줄 인자로 붙이면 Windows 의 명령줄 길이 제한에 걸린다
- **Codex 는 아직 없음** — 이 PC 의 Codex 호출부(ChatGPT 인증을 쓰는 패키지)는 옮길 만큼 작지 않다.
  Codex 만 쓰는 PC 는 지금처럼 세션이 규칙을 직접 읽고 판정한다
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

#: 이보다 긴 시스템 프롬프트는 파일로 넘긴다 — llm_playbook 과 같은 값
SYSTEM_PROMPT_INLINE_MAX = 8000
#: 이 환경 변수가 있으면 Claude Code 가 구독 대신 그 키로 과금한다 — llm_playbook 은 이때 호출을 거절한다
METERED_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
#: 과금 키가 있을 때 사용자가 고른 것 — subscription(판정 호출에서만 키를 숨겨 구독으로) · api(키로 과금)
CHOICE_ENV = "KOREAN_QA_API_KEY_USE"
CHOICES = ("subscription", "api")


def choice_file() -> Path:
    return Path(os.environ.get("KOREAN_QA_API_KEY_CHOICE_FILE")
                or Path.home() / ".claude" / "state" / "korean-qa-api-key-choice.json")


def metered_keys() -> list[str]:
    """환경에 있는 과금 키 이름 — 값은 보지 않는다."""
    return sorted(k for k in os.environ if k.upper() in METERED_ENV and os.environ.get(k))


def key_choice() -> str | None:
    """과금 키가 있을 때의 선택 — 환경 변수가 기록보다 앞선다. 고른 적이 없으면 None."""
    got = os.environ.get(CHOICE_ENV)
    if not got and choice_file().is_file():
        try:
            got = json.loads(choice_file().read_text(encoding="utf-8")).get("use")
        except (OSError, ValueError):
            got = None
    return got if got in CHOICES else None


def save_choice(use: str) -> Path:
    """사용자가 고른 것을 남긴다 — 다음부터 묻지 않는다."""
    if use not in CHOICES:
        raise ValueError(f"「{use}」 — subscription 또는 api")
    f = choice_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"use": use}, ensure_ascii=False), encoding="utf-8")
    return f


class ApiKeyChoiceNeeded(RuntimeError):
    """과금 키가 있는데 사용자가 아직 고르지 않음 — 판정기가 세션에 묻게 한다."""
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def available() -> tuple[bool, str]:
    """이 호출부로 부를 수 있나 — (가능 여부, 까닭). 판정기와 발행 게이트가 같은 것을 본다."""
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        return False, "claude-agent-sdk 없음(python -m pip install claude-agent-sdk)"
    if not (os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude")):
        return False, "Claude Code 명령(claude)이 PATH 에 없음"
    return True, ""


def _prompt(user: str | list[str]):
    """글 하나면 그대로, 글 목록이면 블록마다 나눈 사용자 메시지 하나 — 앞 블록이 같으면 캐시에서 읽는다."""
    if isinstance(user, str):
        return user

    async def gen():
        yield {"type": "user", "parent_tool_use_id": None, "session_id": "default",
               "message": {"role": "user", "content": [{"type": "text", "text": b} for b in user if b]}}
    return gen()


async def _call(model: str, system: str | None, user: str | list[str], timeout: float,
                effort: str | None = None) -> dict[str, Any]:
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage,
                                  TextBlock, query)
    system_file = None
    system_prompt: Any = system or None
    if system and len(system) > SYSTEM_PROMPT_INLINE_MAX:
        fd, system_file = tempfile.mkstemp(prefix="kwqa-system-", suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(system)
        system_prompt = {"type": "file", "path": system_file}
    cli = os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude")
    opts = ClaudeAgentOptions(model=model, system_prompt=system_prompt, permission_mode="dontAsk",
                              tools=[], allowed_tools=[], max_turns=1, setting_sources=[],
                              extra_args={"strict-mcp-config": None, "no-session-persistence": None},
                              **({"cli_path": cli} if cli else {}), **({"effort": effort} if effort else {}))
    chunks: list[str] = []
    result = None

    async def run() -> None:
        nonlocal result
        async for message in query(prompt=_prompt(user), options=opts):
            if isinstance(message, AssistantMessage):
                chunks.extend(b.text for b in message.content if isinstance(b, TextBlock))
            elif isinstance(message, ResultMessage):
                result = message
    keys = metered_keys()
    # 구독을 고른 사람 — CLI 가 뜨는 동안만 키를 이 프로세스 환경에서 뺀다(자식 프로세스가 물려받지 않게)
    hidden = {k: os.environ.pop(k) for k in keys} if keys and key_choice() == "subscription" else {}
    try:
        await asyncio.wait_for(run(), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(f"claude-agent-sdk {timeout:.0f}초 안에 답 없음") from e
    finally:
        os.environ.update(hidden)
        if system_file:
            try:
                os.remove(system_file)
            except OSError:
                pass
    if result is None:
        raise RuntimeError("claude-agent-sdk 가 결과 없이 끝남")
    if result.is_error:
        raise RuntimeError(f"Claude 호출 실패: {(result.result or '')[:200]}")
    usage = result.usage or {}
    return {"text": "".join(chunks) or (result.result or ""), "model": model,
            "cost_usd": result.total_cost_usd, "stop_reason": getattr(result, "stop_reason", None),
            "usage": {k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens",
                                                          "cache_creation_input_tokens", "cache_read_input_tokens")}}


def call_messages(*, model: str, system: str | None, user: str | list[str], max_tokens: int = 4096,
                  timeout: float = 300.0, effort: str | None = None, **_) -> dict[str, Any]:
    """한 턴 호출 — {"text", "model", "cost_usd", "stop_reason", "usage"}. `max_tokens` 는 CLI 가 정해 받기만 한다.

    `effort` 는 사고 깊이 — 검사 단계가 넘긴다(2026-11-04 전에는 받기만 하고 버려 공개판에서 단계가 모델만 바꿨다).
    """
    keys = metered_keys()
    if keys and key_choice() is None:
        raise ApiKeyChoiceNeeded(", ".join(keys))
    return asyncio.run(_call(model, system, user, timeout, effort))


def parse_json_from_text(text: str):
    """답에서 JSON 을 꺼낸다 — 그대로, 코드 울타리 안, 가장 바깥 괄호 순서로."""
    if not text:
        return None
    s = text.strip()
    candidates = [s] + [m.strip() for m in _FENCE.findall(s)]
    for opener, closer in (("{", "}"), ("[", "]")):
        a, b = s.find(opener), s.rfind(closer)
        if 0 <= a < b:
            candidates.append(s[a:b + 1])
    for c in candidates:
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None
