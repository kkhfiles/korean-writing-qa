#!/usr/bin/env python
"""사용자가 짚어 준 지적이 지금 무엇에 덮여 있는지 낸다.

    python -X utf8 scripts/coverage_report.py [--round N] [--owner 대기]

**왜 스크립트인가.** 2026-09-15 에 「짚어 준 것을 다 고칠 수 있게 됐나」를 답하려고
회차별 지적 38건을 **대화 기억으로 손수 복원**했다. 그렇게 한 번 재고 마는 수치는
다음에 또 손으로 재야 한다. 대장(`data/cases/flagged-rounds.jsonl`)을 읽어 같은
수치를 아무 때나 낸다.

**이 수치가 뜻하는 것.** 「덮였다」는 **지적이 난다**는 뜻이지 **고쳐진다**는 뜻이
아니다. 고치는 것은 사람이나 모델이고, 발행을 막는 것은 오류 등급뿐이다.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "..", "data", "cases", "flagged-rounds.jsonl")

#: 주인마다 「그래서 무엇이 보장되나」 — 등급이 다르다는 것을 숨기지 않는다
MEANS = {
    "규칙": "검사기가 지적함 · 오류 등급이면 발행이 막힘",
    "훑개": "훑개를 돌려야 보임 · 사람이 목록을 읽어야 함",
    "사람": "기계 밖 · 스킬을 불러야 봄",
    "대기": "**아무 장치도 안 짚음** · 사례집에 open 으로만 박혀 있음",
}
ORDER = ["규칙", "훑개", "사람", "대기"]


def load():
    if not os.path.exists(LEDGER):
        sys.exit(f"대장이 없습니다: {os.path.normpath(LEDGER)}")
    with open(LEDGER, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser(description="짚어 준 지적이 무엇에 덮여 있는지 본다")
    ap.add_argument("--round", type=int, help="그 회차만")
    ap.add_argument("--owner", choices=ORDER, help="그 주인만")
    args = ap.parse_args()

    rows = load()
    if args.round:
        rows = [r for r in rows if r["round"] == args.round]
    if args.owner:
        rows = [r for r in rows if r["owner"] == args.owner]
    if not rows:
        sys.exit("고른 조건에 맞는 지적이 없습니다")

    by_owner = collections.Counter(r["owner"] for r in rows)
    by_round = collections.defaultdict(collections.Counter)
    for r in rows:
        by_round[r["round"]][r["owner"]] += 1

    total = len(rows)
    machine = by_owner["규칙"] + by_owner["훑개"]
    print(f"짚어 준 지적 {total}건 · 기계가 짚는 것 {machine}건 "
          f"({machine * 100 // total}%)\n")

    for owner in ORDER:
        n = by_owner[owner]
        if n:
            print(f"  {owner} {n:3d}건 — {MEANS[owner]}")

    print("\n회차별")
    for rnd in sorted(by_round):
        cells = " · ".join(f"{o} {by_round[rnd][o]}" for o in ORDER if by_round[rnd][o])
        print(f"  {rnd}회차  {sum(by_round[rnd].values()):2d}건 — {cells}")

    waiting = [r for r in rows if r["owner"] == "대기"]
    if waiting:
        print(f"\n아직 아무 장치도 안 짚는 것 {len(waiting)}건")
        for r in waiting:
            print(f"  {r['flag_id']}  {r['round']}회차  {r['text']:22s} {r['note']}")

    print("\n⚠️ 「덮였다」는 지적이 난다는 뜻입니다 — 고치는 것은 사람이나 모델입니다.")


if __name__ == "__main__":
    main()
