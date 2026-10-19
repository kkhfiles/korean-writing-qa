"""판단 층이 규칙에 적힌 예외를 실제로 지키는지 호출 한 번으로 확인한다.

**무엇을 가르나.** 「에이전틱」은 2층이 고치라고 냈고, 사용자가 아니라 했고, 그래서
2026-08-27 에 `core-rules.md` 의 「뜻이 같은 대체어가 없는 말」 예외에 이름이 올랐다.
**그 예외가 실제로 판정을 바꾸는지는 그 뒤로 한 번도 확인하지 않았다.**

이 저장소가 되풀이해 걸린 실패가 「규칙을 썼다 ≠ 규칙이 적용된다」다. 1층 쪽은
시험으로 막았지만 판단 층에는 그 확인이 없었다.

**순환을 끊는 장치**

- 프롬프트에 들어가는 것은 **문서 원문과 규칙 문서뿐**이다
- 어느 줄이 시험 대상인지, 몇 건을 찾아야 하는지 알려 주지 않는다
- 시험이라는 사실도 알려 주지 않는다 — 발행 직전 호출과 같은 모양으로 부른다

**판정은 기계가 한다** — 나온 지적 목록에 「에이전틱」이 들었는지만 본다.

    python -X utf8 scripts/probe_layer2_exemption.py [--model sonnet] [--json 경로]

호출 1회 · Sonnet · 0.24달러 안팎(2026-09-17 실측 · 처음 적은 0.03달러는
여덟 배 낡아 있었다) · `claude-agent-sdk` OAuth(구독·크레딧 풀 · 과금 키 아님)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import repo_paths  # noqa: E402
import probe_layer2_kinds as kinds  # noqa: E402
SKILL = repo_paths.SKILL
RULES = SKILL / "references" / "core-rules.md"
DOCUMENT = REPO_ROOT / "data" / "raw" / "diagnostic-002" / "doc-002.md"

# 사용자 판정으로 「고치지 말라」가 된 말. 프롬프트에는 넣지 않는다.
EXEMPT_TERM = "에이전틱"
EXEMPT_LINE = 14

# 프롬프트 틀은 판정기와 같은 것을 쓴다 — 여기 따로 둔 사본이 판정기 형식(decide · check · 행 형식)과
# 어긋나 있었다(2026-10-20 행 형식을 기본으로 바꾸며 맞춤). 「발행 직전 호출과 같은 모양」이어야 시험이다.
USER = kinds.USER


def load_client():
    """정본은 `llm_playbook.backends` 하나다 — 옛 경로는 위임 shim 이다.

    처음에는 설정 저장소의 절대 경로를 박아 두고 거기서 shim 을 가져왔다.
    발행 정리(2026-09-07 · a802d7c)가 그 경로를 가리면서 **이 탐침이 안 돌게
    됐다.** 가린 것이 곧 죽인 것이었고 열흘 동안 아무도 몰랐다 — 판단 층이
    규칙대로 판정하는지 확인하는 유일한 장치인데도.

    설치되는 꾸러미에서 가져오면 **가릴 경로가 없다.** 없는 꾸러미는 이름을
    대며 멈추므로 실패가 읽히지만, 없는 경로는 「없는 파일」로만 멈춘다.
    """
    from llm_playbook.backends.claude_sdk import (
        call_messages, parse_json_from_text)
    return call_messages, parse_json_from_text


def numbered(text: str) -> str:
    return "\n".join(f"{n:>3} | {line}"
                     for n, line in enumerate(text.splitlines(), 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--json", type=Path)
    # 기본 120초로는 모자랐다 — SDK 가 Claude Code 를 띄우는 첫 회차가 느리다
    parser.add_argument("--timeout", type=float, default=420.0)
    args = parser.parse_args()

    for path in (RULES, DOCUMENT):
        if not path.is_file():
            sys.exit(f"없는 파일: {path}")

    call_messages, parse_json = load_client()
    document = DOCUMENT.read_text(encoding="utf-8")

    result = call_messages(
        model=args.model,
        system=kinds.system_prompt().format(rules=RULES.read_text(encoding="utf-8")),
        user=USER.format(document=numbered(document)),
        max_tokens=3000,
        temperature=0,
        timeout=args.timeout,
    )

    findings = kinds.as_findings(parse_json(result.get("text") or "") or [])

    hit = [f for f in findings
           if isinstance(f, dict)
           and (EXEMPT_TERM in str(f.get("phrase", ""))
                or f.get("line") == EXEMPT_LINE)]

    print(f"모델 {result.get('model')} · 지적 {len(findings)}건 "
          f"· {result.get('cost_usd', 0):.4f}달러\n")
    for f in findings:
        if isinstance(f, dict):
            print(f"  {str(f.get('line')):>4}행  {str(f.get('phrase'))[:40]:<42}"
                  f"→ {str(f.get('fix'))[:34]}")

    print()
    if hit:
        print(f"★ 예외 어김 — 「{EXEMPT_TERM}」을 고치라고 냈다")
        for f in hit:
            print(f"    {f}")
        print("\n  규칙 문서에 예외를 적는 방식이 행동을 안 바꾼다는 뜻이다.")
        print("  하네스를 짓기 전에 이것부터 고쳐야 한다.")
    else:
        print(f"✅ 예외 지킴 — 「{EXEMPT_TERM}」을 안 건드렸다")
        print("\n  되먹임이 규칙에서 행동까지 닿는다. 전수 판정 3건으로 넓힐 수 있다.")

    if args.json:
        args.json.write_text(json.dumps(
            {"model": result.get("model"), "cost_usd": result.get("cost_usd"),
             "usage": result.get("usage"), "findings": findings,
             "exemption_respected": not hit},
            ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
