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

호출 1회 · Sonnet · 0.03달러 안팎 · `claude-agent-sdk` OAuth(구독·크레딧 풀)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import repo_paths

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_DIR = Path("P:/github/claude-workflow")
SKILL = repo_paths.SKILL
RULES = SKILL / "references" / "core-rules.md"
DOCUMENT = REPO_ROOT / "data" / "raw" / "diagnostic-002" / "doc-002.md"

# 사용자 판정으로 「고치지 말라」가 된 말. 프롬프트에는 넣지 않는다.
EXEMPT_TERM = "에이전틱"
EXEMPT_LINE = 14

SYSTEM = """당신은 한글 업무 문서를 전달 전에 최종 점검한다.

아래 규칙을 읽고, 주어진 문서에서 고쳐야 할 표현을 찾는다.

{rules}

## 내는 형식

JSON 배열 하나만 낸다. 다른 말은 붙이지 않는다.

[{{"line": 줄번호, "phrase": "고칠 표현 원문 그대로", "category": "규칙 이름",
   "fix": "고친 말", "why": "한 줄 근거"}}]

고칠 것이 없으면 빈 배열 []을 낸다."""

USER = """다음 문서를 점검한다. 줄 번호는 1부터 센다.

```
{document}
```"""


def load_client():
    sys.path.insert(0, str(CLIENT_DIR))
    from mycelium.core.anthropic_client import call_messages, parse_json_from_text
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
        system=SYSTEM.format(rules=RULES.read_text(encoding="utf-8")),
        user=USER.format(document=numbered(document)),
        max_tokens=3000,
        temperature=0,
        timeout=args.timeout,
    )

    findings = parse_json(result.get("text") or "") or []
    if not isinstance(findings, list):
        findings = []

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
