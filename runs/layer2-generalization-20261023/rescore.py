"""2층 판정기가 규칙에 인용되지 않은 같은 갈래 문장도 잡나 — 같은 날 판정 규칙 축약본 측정의 원자료를 다시 센다.

모델을 다시 부르지 않는다. `runs/judge-rules-slim-20261023/raw-{now,hard}-{0,1}.json` 의 지적을
그 측정 때의 규칙 글과 운반 문서(커밋 45ed831)에 대고, 대장과 예비 문장을 넷으로 나눠 엄격 기준으로 센다.

python -X utf8 runs/layer2-generalization-20261023/rescore.py
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SLIM = REPO / "runs/judge-rules-slim-20261023"
AT = "45ed831"
sys.path.insert(0, str(REPO / "scripts"))


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def show(path):
    return subprocess.run(["git", "show", f"{AT}:{path}"], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8", check=True).stdout


def main():
    probe = load("probe", REPO / "scripts/probe_layer2_kinds.py")
    slim = load("slim", SLIM / "slim.py")
    now = probe.rules_for("guided", core=show("skills/finalize-korean-document/references/core-rules.md"),
                          skill=show("skills/finalize-korean-document/SKILL.md"))
    hard = slim.slim_hard(now)[0]
    doc = show("tests/fixtures/layer2-kinds/carrier.md")
    # 그 측정 뒤에 대장에 오른 것은 운반 문서에 없었다
    planted_then = {json.loads(l)["flag_id"] for l in show("data/cases/flagged-rounds.jsonl").splitlines() if l.strip()}
    items = [i for i in probe.planted() + probe.held_out() if i["source"] == "예비" or i["flag_id"] in planted_then]
    c_now = {i["text"] for i in items if i["text"] in now.replace("*", "")}
    c_hard = {i["text"] for i in items if i["text"] in hard.replace("*", "")}
    groups = {
        "둘 다 인용": lambda r: r["text"] in c_now and r["text"] in c_hard,
        "지금 판만 인용(축약본에서 예문이 빠짐)": lambda r: r["text"] in c_now and r["text"] not in c_hard,
        "대장 비인용": lambda r: r["source"] == "대장" and r["text"] not in c_now,
        "예비(지어낸 비인용)": lambda r: r["source"] == "예비",
    }
    out = {}
    for arm in ("now", "hard"):
        for rep in (0, 1):
            f = json.loads((SLIM / f"raw-{arm}-{rep}.json").read_text(encoding="utf-8"))["findings"]
            rows = probe.score(items, f, doc, cited=c_now if arm == "now" else c_hard)["rows"]
            out[f"{arm}-{rep}"] = {k: f"{sum(1 for r in rows if g(r) and r['tight'])}/{sum(1 for r in rows if g(r))}"
                                  for k, g in groups.items()}
            print(arm, rep, " | ".join(f"{k} {v}" for k, v in out[f"{arm}-{rep}"].items()))
    return out


if __name__ == "__main__":
    main()
