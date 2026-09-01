"""2층이 실제로 도는 비율을 잰다 — 안내를 붙인 효과를 확인하는 자다.

**왜 필요한가.** 2층 회수율 0.771은 「돌았다면 잡았을 값」이다. 실측하니 한글
문서를 파일에 쓴 세션 55개 중 2개(3.6%)만 스킬을 불렀다. 그래서 운영 중 실제로
걸러지는 것은 1층이 잡는 것뿐이고, 그게 참 문제의 6% 남짓이다.

**두 군데를 따로 센다** — 어디서 새는지가 처방을 가른다.

| 단계 | 뜻 | 붙이기 전 실측(14일) |
|---|---|---|
| 안내 발화율 | 발행할 때 안내가 뜨나 | 발행 640회 중 59회 · 9.2% |
| 안내 이행율 | 떴을 때 스킬을 부르나 | 59회 중 2회 · 3.4% |

**안내를 발행 경로로 옮긴 날: 2026-08-31.** 그 앞뒤를 갈라 낸다.

    python -X utf8 scripts/measure_layer2_uptake.py [--days 14] [--json 경로]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TRANSCRIPTS = Path.home() / ".claude" / "projects"
# 경계는 **날짜가 아니라 그 순간**이다. 자정으로 잡았더니 같은 날 아침의 활동이
# 「붙인 뒤」로 세어져, 안내가 있을 수 없던 발행 8건을 「안내 0회」로 보고했다.
CHANGED = datetime(2026, 8, 31, 7, 56, 13, tzinfo=timezone.utc)   # 커밋 2037126
# 안내를 세는 표시는 **훅이 내는 그 줄 전체**여야 한다. 「발행 직전」만 찾으면
# 그 문구를 논의한 글까지 세어 발화율이 208%로 나온다(실측으로 걸렸다).
NOTICE_MARK = "★ 발행 직전 — 이 문서에 finalize-korean-document 스킬을 돌린다"
OLD_NOTICE_MARK = "한글 문서 최종화 검사 — 전달 전에 finalize-korean-document 스킬로 문맥까지 확인"
# 이 시스템을 만드는 세션은 문구를 계속 인용하므로 뺀다
SELF = "korean-writing-qa"
SKILL_NAME = "finalize-korean-document"
HOOK = Path.home() / ".claude" / "hooks" / "doc-style-gate.py"


def load_hook():
    """발행의 정의를 훅에서 그대로 가져온다 — 두 벌로 두면 어긋난다.

    처음에는 이 파일이 `notion\\.py|marp|\\.pptx` 라는 자기 나름의 정규식을 들고
    있었다. 그래서 `notion.py children`(조회)과 `grep ... notion.py`(소스 읽기)까지
    발행으로 셌다. 훅은 그 셋을 하나도 발행으로 보지 않는다. 분모가 부풀면
    발화율이 실제보다 낮게 나오고, 안 고쳐도 될 것을 고치게 된다.
    """
    spec = importlib.util.spec_from_file_location("doc_style_gate", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_publish(hook, block) -> bool:
    """훅이 이 호출에서 발행 게이트를 걸었을지 그대로 물어본다."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": block.get("name") or "",
        "tool_input": block.get("input") or {},
    }
    files, _, mode = hook.targets(payload)
    return bool(files) and mode == "always"


def bucket(stamp: str) -> str:
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return "붙인 뒤" if when >= CHANGED else "붙이기 전"


def measure(days: int) -> dict:
    cutoff = time.time() - days * 86400
    hook = load_hook()
    notices, skill_calls, publishes = Counter(), Counter(), Counter()
    sessions = {"붙이기 전": set(), "붙인 뒤": set()}

    for path in TRANSCRIPTS.rglob("*.jsonl"):
        if SELF in str(path.parent.name):
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
            when = bucket(item.get("timestamp") or "")
            if not when:
                continue
            blob = json.dumps(item, ensure_ascii=False)
            if NOTICE_MARK in blob or OLD_NOTICE_MARK in blob:
                notices[when] += 1
                sessions[when].add(path.stem)
            content = (item.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                args = json.dumps(block.get("input") or {}, ensure_ascii=False)
                if block.get("name") == "Skill" and SKILL_NAME in args:
                    skill_calls[when] += 1
                if is_publish(hook, block):
                    publishes[when] += 1

    out = {"days": days, "buckets": {}}
    for when in ("붙이기 전", "붙인 뒤"):
        out["buckets"][when] = {
            "발행 호출": publishes[when],
            "안내 발화": notices[when],
            "스킬 호출": skill_calls[when],
            "세션": len(sessions[when]),
            "안내 발화율": round(notices[when] / publishes[when], 3) if publishes[when] else None,
            "안내 이행율": round(skill_calls[when] / notices[when], 3) if notices[when] else None,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    result = measure(args.days)
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"최근 {args.days}일\n")
    print(f"{'구간':<10}{'발행':>7}{'안내':>7}{'스킬':>7}{'발화율':>9}{'이행율':>9}")
    print("-" * 50)
    for when, row in result["buckets"].items():
        rate = f"{row['안내 발화율']:.1%}" if row["안내 발화율"] is not None else "—"
        follow = f"{row['안내 이행율']:.1%}" if row["안내 이행율"] is not None else "—"
        print(f"{when:<10}{row['발행 호출']:>7}{row['안내 발화']:>7}"
              f"{row['스킬 호출']:>7}{rate:>9}{follow:>9}")
    print()
    after = result["buckets"]["붙인 뒤"]
    if after["발행 호출"] < 20:
        print("⛔ 판정 불가 — 붙인 뒤 발행이 적다. 며칠 더 지나야 잴 수 있다.")
    elif after["안내 발화율"] and after["안내 발화율"] < 0.5:
        print("안내가 아직 덜 뜬다 — 발행 경로 판정을 다시 볼 것")
    elif after["안내 이행율"] is not None and after["안내 이행율"] < 0.3:
        print("안내는 뜨는데 안 따른다 — 문구가 아니라 다른 장치가 필요하다")
    else:
        print("안내와 이행 둘 다 오름")


if __name__ == "__main__":
    main()
