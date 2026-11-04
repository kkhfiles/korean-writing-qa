"""D4 — 이 저장소의 본래 영역(사용자가 짚은 업무 글 표현)에서 2층 판정기와 Claude 단순 요청을 견준다.

- **시료**: `tests/fixtures/layer2-kinds/carrier.md` — 대장(사용자가 짚은 표현) 2층 몫과 예비 문장을 심은 운반 문서
- **채점**: `scripts/probe_layer2_kinds.score` 그대로(엄격 — 지적 표현이 심은 표현을 품거나 그 안에 듦)
- **같은 조건**: 같은 모델(Opus), 같은 절 단위 묶음, 두 판 모두 2회. 단순 요청은 `systems.PLAIN_SYSTEM`
- **치우침 주의**: 대장 문장은 판정 규칙의 예문으로도 들어 있어(「인용」 칸) 2층에 유리함 — 인용 안 된 것만 따로 셈

    python -X utf8 runs/bench-external-20261031/bench_ledger.py [--reps 2]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "scripts"))
import systems  # noqa: E402
from common import DATA  # noqa: E402

OUT = DATA / "ledger"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def plain_arm(probe, doc: str, items: list[dict]) -> dict:
    lines = doc.splitlines()
    findings, cost, sec = [], 0.0, 0.0
    for a, b in probe.chunks(doc):
        part = "\n".join(f"{n}\t{line}" for n, line in enumerate(lines[a:b], a + 1))
        t = time.time()
        r = systems.call_model("claude", "opus", systems.PLAIN_SYSTEM, part)
        sec += time.time() - t
        cost += r.get("cost_usd") or 0
        findings += [{"line": f["line"], "phrase": f["quote"], "fix": f["fix"], "category": f["kind"]}
                     for f in systems.parse_findings(r["text"])]
    cited = {i["text"] for i in probe.planted() if i["text"] in probe.rules_for("guided").replace("*", "")}
    out = probe.score(items, findings, doc, cited)
    out.update({"cost_usd": cost, "sec": sec, "findings": findings})
    return out


def row(name: str, rep: int, out: dict, sec: float) -> dict:
    return {"arm": name, "rep": rep, "tight": out["tight"], "loose": out["loose"], "total": out["total"],
            "ledger_tight": sum(1 for r in out["rows"] if r["source"] == "대장" and r["tight"]),
            "ledger_total": sum(1 for r in out["rows"] if r["source"] == "대장"),
            "heldout_tight": sum(1 for r in out["rows"] if r["source"] == "예비" and r["tight"]),
            "heldout_total": sum(1 for r in out["rows"] if r["source"] == "예비"),
            "cited": out["인용"], "uncited": out["비인용"], "said": out["said"], "extra": len(out["extra"]),
            "cost_usd": round(out["cost_usd"], 4), "sec": round(sec),
            "calls": out.get("calls"), "truncated": out.get("truncated"), "max_tokens": out.get("max_tokens")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--max-tokens", type=int, default=8000,
                    help="2층 묶음마다 출력 한도 — 판정기 본체는 12000(8000 이 아니면 결과 파일 이름에 붙음)")
    ap.add_argument("--arms", default="l2,plain-claude",
                    help="l2-narrow 는 고친 말의 범위를 좁힌 판정기(2026-11-03 · probe_layer2_kinds.FIX_SCOPE_ENV)")
    a = ap.parse_args()
    probe = load("probe", REPO / "scripts" / "probe_layer2_kinds.py")
    doc = probe.CARRIER.read_text(encoding="utf-8")
    items = probe.planted() + probe.held_out()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for rep in range(a.reps):
        for name in a.arms.split(","):     # 번갈아 — 캐시와 시간대 차이를 섞음
            tag = "" if a.max_tokens == 8000 else f"-mt{a.max_tokens}"
            f = OUT / f"{name}{tag}-{rep}.json"
            if f.exists():
                rows.append(json.loads(f.read_text(encoding="utf-8"))["row"])
                continue
            t = time.time()
            # 11-03 부터 판정기 기본값이 좁힌 수정안 — `l2` 는 넣기 전 판정기로 다시 냄
            # `l2-sonnet`, `l2-haiku` 는 좁힌 판정기를 더 싼 모델로(2026-11-04 검사 단계 설정 측정)
            os.environ["KOREAN_QA_FIX_SCOPE"] = "wide" if name == "l2" else "narrow"
            # `l2-<모델>-<사고 깊이>` 는 사고 깊이를 명시한 칸(예: l2-opus-low)
            parts = name.split("-")
            model = {"l2-sonnet": "sonnet", "l2-haiku": "haiku"}.get(name, parts[1] if len(parts) == 3 else "opus")
            effort = parts[2] if len(parts) == 3 else None
            out = (plain_arm(probe, doc, items) if name == "plain-claude"
                   else probe.run_arm("guided", model, 600.0, doc, items, effort=effort, max_tokens=a.max_tokens))
            r = row(name, rep, out, time.time() - t)
            f.write_text(json.dumps({"row": r, "rows": out["rows"], "findings": out["findings"]},
                                    ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            rows.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    if a.arms == "l2,plain-claude":
        (HERE / "ledger.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
