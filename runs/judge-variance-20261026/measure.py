"""판정기 흔들림 — 같은 입력을 세 번 판정해 회수와 지적이 얼마나 갈리는지 잰다(결정용이 아니라 해석용 기준).

1회씩 돌린 실험의 「한두 건 차이」를 읽으려면 같은 입력에서 판정기가 얼마나 흔들리는지 알아야 한다.
지금 판정기와 같은 경로(`probe.run_arm`, guided, Opus, 드문 낱말 목록 포함)로 부른다. 모두 구독.

python -X utf8 runs/judge-variance-20261026/measure.py [--reps 3]
"""
import importlib.util
import itertools
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


def main():
    reps = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 3
    probe = load("probe", REPO / "scripts/probe_layer2_kinds.py")
    words = load("words", REPO / "runs/layer2-words-coverage-20261023/build.py")
    w_rows = words.items()
    samples = {
        "단어 점검 몫 33건": (words.document(w_rows), w_rows),
        "2층 운반 문서": (probe.CARRIER.read_text(encoding="utf-8"), probe.planted() + probe.held_out()),
    }
    report = {}
    for name, (doc, items) in samples.items():
        hits, said, cost = [], [], 0.0
        for rep in range(reps):
            out = probe.run_arm("guided", "opus", 600.0, doc, items)
            got = {r["flag_id"] for r in out["rows"] if r["tight"]}
            hits.append(got)
            said.append(out["said"])
            cost += out["cost_usd"]
            (HERE / f"raw-{'words' if '단어' in name else 'carrier'}-{rep}.json").write_text(
                json.dumps({"hits": sorted(got), "findings": out["findings"]}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{name} {rep}: 엄격 {len(got)}/{len(items)} · 지적 {out['said']} · {out['cost_usd']:.2f}달러", flush=True)
        always = set.intersection(*hits)
        ever = set.union(*hits)
        jac = [len(a & b) / len(a | b) for a, b in itertools.combinations(hits, 2)]
        report[name] = {"시료 수": len(items), "회차별 엄격 회수": [len(h) for h in hits], "회차별 지적 수": said,
                        "세 번 다 짚음": len(always), "한 번 이상 짚음": len(ever),
                        "회차마다 갈린 항목": sorted(ever - always), "짚은 항목 일치도(쌍별 자카드)": [round(j, 3) for j in jac],
                        "환산 달러": round(cost, 2)}
        print(json.dumps(report[name], ensure_ascii=False), flush=True)
    (HERE / "result-raw.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
