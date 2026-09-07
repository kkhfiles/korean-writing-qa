#!/usr/bin/env python
"""AI 가 쓴 한글 문서 중 몇 %가 실제로 검사를 받았는지 센다.

**왜 필요한가.** 목표는 「이 PC 에서 AI 가 만드는 모든 문서 산출물이 검사 통과한
한글」인데, 그것을 재는 수단이 없었다. 2층 이행율은 재면서 1층 덮개는 안 쟀다.
붙였다는 사실과 실제로 걸린다는 사실은 다르다.

**세는 법** — 세션 기록에서 문서를 쓴 도구 호출을 세고(분모), 그중 훅이 검사 대상으로
고른 것을 센다(분자). 판정은 **훅에게 물어본다** — 여기서 다시 적으면 두 벌이 되고,
그 실패는 이 저장소가 이미 겪었다.

| 값 | 뜻 |
|---|---|
| 대상 | 훅이 검사하기로 **고르는** 호출 |
| 제외 | 훅이 건너뛰는 것 — 작업 문서·임시 디렉터리·소스 파일 |
| 덮개 | 대상 ÷ 한글 문서 쓰기 |

**⛔ 이 값은 「범위에 든다」이지 「실제로 돌았다」가 아니다.** 깨끗한 문서에서는 훅이
아무 말도 안 하므로, 기록만 봐서는 돌아서 조용한 것과 안 돈 것이 안 갈린다. 실제로
도는지는 시험이 지킨다(`tests/test_gate_reports_its_own_failure.py`·
`tests/test_codex_uses_the_same_gate.py`). 이 계기판이 답하는 것은 **범위**다.

**⛔ 실행기별로 따로 세지 못한다** — 세션 기록은 Claude Code 것만 남는다. Codex 쪽은
이 계기판이 못 본다(그쪽 덮개는 `tests/test_codex_uses_the_same_gate.py` 가 지킨다).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from collections import Counter
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

TRANSCRIPTS = repo_paths.installed("projects")
HOOK = repo_paths.hook("doc-style-gate.py")
WRITE_TOOLS = ("Write", "Edit", "MultiEdit")
# 사람이 읽을 문서 — 훅이 보는 것과 같은 확장자를 훅에서 가져온다
SELF = "korean-writing-qa"


def load_hook():
    """검사 대상의 정의를 훅에서 그대로 가져온다 — 두 벌로 두면 어긋난다."""
    spec = importlib.util.spec_from_file_location("doc_style_gate", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def written_path(block) -> str:
    args = block.get("input")
    if not isinstance(args, dict):
        return ""
    value = args.get("file_path")
    return value.strip() if isinstance(value, str) else ""


def measure(days: int, include_self: bool) -> dict:
    cutoff = time.time() - days * 86400
    hook = load_hook()
    counts = Counter()
    seen_docs: set[str] = set()

    for path in TRANSCRIPTS.rglob("*.jsonl"):
        if not include_self and SELF in str(path.parent.name):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for row in raw.splitlines():
            if not row.strip():
                continue
            try:
                item = json.loads(row)
            except ValueError:
                continue
            content = (item.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                if block.get("name") not in WRITE_TOOLS:
                    continue
                target = written_path(block)
                if not target:
                    continue
                counts["쓴 호출"] += 1
                # 한글 문서인지, 검사 대상인지 — 둘 다 훅의 정의로 가른다
                if not hook.KOREAN_DOC.search(target):
                    counts["문서 아님"] += 1
                    continue
                counts["한글 문서"] += 1
                seen_docs.add(target)
                skipped = hook.SKIP.search(target)
                if skipped:
                    counts["훅이 건너뜀"] += 1
                    counts[f"제외 사유: {skipped.group(0).strip()}"] += 1
                else:
                    counts["검사 대상"] += 1

    docs = counts["한글 문서"]
    return {
        "days": days,
        "counts": dict(counts),
        "문서 수": len(seen_docs),
        "덮개": round(counts["검사 대상"] / docs, 3) if docs else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="검사 덮개를 센다.")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--include-self", action="store_true",
                        help="이 저장소의 세션도 센다(기본은 뺀다 — 시험이 수치를 부풀린다)")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    result = measure(args.days, args.include_self)
    counts = result["counts"]
    print(f"최근 {args.days}일 · 서로 다른 문서 {result['문서 수']}개\n")
    for label in ("쓴 호출", "문서 아님", "한글 문서", "검사 대상", "훅이 건너뜀"):
        print(f"  {label:12} {counts.get(label, 0):6}")
    covered = result["덮개"]
    print()
    if covered is None:
        print("⛔ 판정 불가 — 그 기간에 한글 문서를 쓴 기록이 없다.")
    else:
        print(f"  덮개 {covered:.1%} — 한글 문서 쓰기 중 훅이 검사한 비율")
        if counts.get("훅이 건너뜀"):
            print("\n  건너뛴 것의 사유")
            for label, value in sorted(counts.items(), key=lambda kv: -kv[1]):
                if label.startswith("제외 사유: "):
                    print(f"    {label[6:]:22} {value:5}")
        print("\n  ⛔ 이 값은 「범위에 든다」이지 「실제로 돌았다」가 아니다 — "
              "깨끗한 문서에서는 훅이 조용하다.")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")


if __name__ == "__main__":
    main()
