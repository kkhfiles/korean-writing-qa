"""판정 규칙 축약본 정확도 비교 — 2층 운반 문서(심은 지적)를 세 규칙 글로 판정해 회수를 견준다.

    python -X utf8 runs/judge-rules-slim-20261023/measure.py [--reps 2] [--model opus]

구독으로 돈다(청구액 없음 · 환산 금액은 기록). 7일 창 사용률이 STOP 을 넘으면 멈춘다.
판 순서는 번갈아 돌려(지금 → 경위 제거 → 공격적 → 지금 …) 캐시와 순서 효과를 섞는다.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STOP = 80


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(REPO / "scripts"))
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--start", type=int, default=0, help="이 회차부터 — 앞 회차 raw 파일은 그대로 둔다")
    a = ap.parse_args()
    probe = load("probe", REPO / "scripts" / "probe_layer2_kinds.py")
    bench = load("bench", REPO / "scripts" / "bench_loop.py")
    sl = load("slim", HERE / "slim.py")
    now = probe.rules_for("guided")
    arms = {"now": now, "slim": sl.slim(now)[0], "hard": sl.slim_hard(now)[0]}
    doc = probe.CARRIER.read_text(encoding="utf-8")
    items = probe.planted() + probe.held_out()
    results = []
    seen: list[dict] = []
    with bench.watch_limits(seen):
        for rep in range(a.start, a.reps):
            for name, rules in arms.items():
                t0 = time.time()
                out = probe.run_arm("guided", a.model, 600.0, doc, items, rules=rules)
                row = {"arm": name, "rep": rep, "rules_chars": len(rules), "calls": out["calls"],
                       "cost_usd": round(out["cost_usd"], 4), "sec": round(time.time() - t0),
                       "tight": out["tight"], "loose": out["loose"], "why": out["why"], "total": out["total"],
                       "said": out["said"], "extra": len(out["extra"]),
                       "cited": out["인용"], "uncited": out["비인용"],
                       "ledger_tight": sum(1 for r in out["rows"] if r["source"] == "대장" and r["tight"]),
                       "heldout_tight": sum(1 for r in out["rows"] if r["source"] == "예비" and r["tight"]),
                       "missed": [r["flag_id"] for r in out["rows"] if not (r["tight"] or r["loose"])],
                       "limits": seen[-1] if seen else None}
                results.append(row)
                (HERE / f"raw-{name}-{rep}.json").write_text(json.dumps(
                    {"row": row, "findings": out["findings"]}, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"{name:<5} {rep}  엄격 {row['tight']:>3}/{row['total']}  느슨 {row['loose']:>3}  까닭 {row['why']:>3}"
                      f"  대장 {row['ledger_tight']:>3}  예비 {row['heldout_tight']:>2}  밖 지적 {row['extra']:>3}"
                      f"  {row['cost_usd']:.2f}달러  {row['sec']}초  사용률 {row['limits']}", flush=True)
                lim = row["limits"] or {}
                if any(isinstance(v, (int, float)) and v * (100 if v <= 1 else 1) > STOP for v in lim.values()):
                    print(f"사용률이 {STOP}% 를 넘어 멈춤")
                    (HERE / "runs.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
                    return 2
    (HERE / f"runs-from-{a.start}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
