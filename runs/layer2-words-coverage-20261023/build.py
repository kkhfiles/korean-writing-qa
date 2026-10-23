"""대장의 단어 점검 몫 33건을 업무 문서 꼴 하나로 모으고 판정기를 한 번 부른다 — 사전 기록은 plan.md.

python -X utf8 runs/layer2-words-coverage-20261023/build.py [--with-rare]
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[1]
os.environ["LLM_PLAYBOOK_BILLING"] = "subscription"


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def items():
    rows = [json.loads(l) for l in (REPO / "data/cases/flagged-rounds.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return [dict(r, source="대장") for r in rows if r["owner"] == "단어 점검"]


def document(rows):
    """한 절에 다섯 줄씩 — 운반 문서처럼 어느 줄이 심은 것인지 알리지 않는다."""
    out = ["# 업무 도구 운영 현황", "", "**운영 현황과 다음 계획** — 도구별 진행 상황 정리", ""]
    for i in range(0, len(rows), 5):
        out += [f"## 진행 현황 {i // 5 + 1}", ""]
        out += [f"- {r['sentence']}" for r in rows[i:i + 5]]
        out.append("")
    return "\n".join(out)


RARE_HEAD = ("\n\n## 이 문서에서 업무 글에 드문 낱말\n\n"
             "단어 점검(사람이 쓴 업무 한국어 4,790만 자에서 40회 이하)이 고른 낱말이다. 드물다고 틀린 것은 "
             "아니다 — 제품 이름, 전문 용어, 그 분야에서 굳은 말은 정상이다. 업무 글에서 같은 뜻으로 더 흔히 "
             "쓰는 말이 있으면 「업무에서 쓰는 말로 쓰기」로 짚는다.\n\n")


def rare_block(doc_path):
    """단어 점검이 내는 목록 줄(「낱말/품사 이 문서 N회 … 문장」)만 떼어 온다."""
    import subprocess
    p = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "scripts/rare_words.py"), str(doc_path)],
                       capture_output=True, text=True, encoding="utf-8")
    lines = [" ".join(l.split()) for l in p.stdout.splitlines() if "이 문서" in l and "/" in l]
    return RARE_HEAD + "\n".join(f"- {l}" for l in lines)


def main():
    with_rare = "--with-rare" in sys.argv
    sys.path.insert(0, str(REPO / "scripts"))
    probe = load("probe", REPO / "scripts/probe_layer2_kinds.py")
    rows = items()
    doc = document(rows)
    (HERE / "doc.md").write_text(doc, encoding="utf-8")
    rules = probe.rules_for("guided")
    if with_rare:
        rules += rare_block(HERE / "doc.md")
        (HERE / "rare-block.md").write_text(rules[rules.index(RARE_HEAD):], encoding="utf-8")
    out = probe.run_arm("guided", "opus", 600.0, doc, rows, rules=rules if with_rare else None)
    flat = rules.replace("*", "")
    cited = {r["text"] for r in rows if r["text"] in flat}
    sc = probe.score(rows, out["findings"], doc, cited=cited)
    res = {"arm": "with-rare" if with_rare else "plain", "cost_usd": round(out["cost_usd"], 3), "calls": out["calls"],
           "인용": sc["인용"], "비인용": sc["비인용"], "said": sc["said"],
           "missed": [{"flag_id": r["flag_id"], "text": r["text"], "cited": r["cited"]} for r in sc["rows"] if not r["tight"]]}
    (HERE / f"raw-{res['arm']}.json").write_text(json.dumps({"result": res, "findings": out["findings"]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
