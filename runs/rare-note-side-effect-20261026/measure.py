"""드문 낱말 목록을 붙인 판과 뺀 판을 세 번씩 번갈아 판정해 목록이 더하거나 없앤 지적을 가린다 — 사전 기록은 plan.md.

지적 원문은 저장소 밖 작업 폴더에만 쓰고 저장소에는 집계(result-raw.json)만 둔다. 모두 구독.

python -X utf8 runs/rare-note-side-effect-20261026/measure.py <작업 폴더> <문서…> [--reps 3]
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[1]
os.environ["LLM_PLAYBOOK_BILLING"] = "subscription"
sys.path.insert(0, str(REPO / "scripts"))


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def same(a, b):
    pa, pb = str(a.get("phrase", "")).strip(), str(b.get("phrase", "")).strip()
    return a["doc"] == b["doc"] and str(a.get("line")) == str(b.get("line")) and pa and pb and (pa in pb or pb in pa)


def count_in(f, runs):
    return sum(any(same(f, g) for g in run) for run in runs)


def stable(runs):
    """두 번 이상 나온 지적 — 대표로 첫 회차의 것을 남긴다."""
    out = []
    for run in runs:
        for f in run:
            if count_in(f, runs) >= 2 and not any(same(f, g) for g in out):
                out.append(f)
    return out


def main():
    args = sys.argv[1:]
    reps = 3
    if "--reps" in args:
        i = args.index("--reps"); reps = int(args[i + 1]); del args[i:i + 2]
    work, docs = Path(args[0]), [Path(a) for a in args[1:]]
    work.mkdir(parents=True, exist_ok=True)
    probe = load("probe", REPO / "scripts/probe_layer2_kinds.py")
    real_note = probe.rare_note
    runs = {"붙임": [], "뺌": []}
    cost = 0.0
    for rep in range(reps):
        for arm in ("붙임", "뺌"):
            probe.rare_note = real_note if arm == "붙임" else (lambda _p: "")
            found = []
            for d in docs:
                out = probe.run_arm("guided", "opus", 600.0, d.read_text(encoding="utf-8"), [])
                cost += out["cost_usd"]
                found += [dict(f, doc=d.stem) for f in out["findings"] if isinstance(f, dict)]
            runs[arm].append(found)
            print(f"{arm} {rep}: 지적 {len(found)} · 누적 {cost:.2f}달러", flush=True)
    probe.rare_note = real_note
    st = {arm: stable(r) for arm, r in runs.items()}
    added = [f for f in st["붙임"] if count_in(f, runs["뺌"]) <= 1]
    removed = [f for f in st["뺌"] if count_in(f, runs["붙임"]) <= 1]
    (work / "added.json").write_text(json.dumps(added, ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "removed.json").write_text(json.dumps(removed, ensure_ascii=False, indent=1), encoding="utf-8")
    (work / "runs.json").write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")
    res = {"회차별 지적 수": {a: [len(r) for r in rs] for a, rs in runs.items()},
           "안정된 지적": {a: len(v) for a, v in st.items()},
           "목록이 더한 지적": len(added), "목록이 없앤 지적": len(removed), "환산 달러": round(cost, 2)}
    (HERE / "result-raw.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
