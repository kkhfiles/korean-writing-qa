"""문장 사이의 관계(접속어 · 지시 대상 · 자료 비교 · 요약) 갈래를 2층이 잡는지, 같은 말을 쓴 정상 문장은 두는지 잰다.

**무엇을 가르나.** 2026-10-20 에 발표 원고 교정 사례에서 온 문장 사이 관계 갈래를 `core-rules.md` 와
`finalize-korean-document` 9단계에 넣었다. 접속어나 지시어는 정상 문장에 훨씬 많이 쓰이므로 **잡는 것만큼
안 잡는 것이 중요하다.** 그래서 사례마다 같은 말을 쓴 정상 짝을 함께 심는다.

**규칙 전후를 같은 문서로 견준다** — `--ref <커밋>` 이면 그 커밋의 규칙 글로 부른다(바꾸기 전).
없으면 작업 트리의 규칙 글이다(바꾼 뒤). 규칙 외의 프롬프트는 판정기와 같다(`probe_layer2_kinds`).

**운반 문서 둘**

| 이름 | 문서 | 재는 것 |
|---|---|---|
| `discourse` | `tests/fixtures/layer2-discourse/cases.jsonl` 로 조립한 발표 원고 | 사례 줄 회수 · 정상 짝 줄 지적 |
| `kinds` | `tests/fixtures/layer2-kinds/carrier.md` | 대장 2층 몫과 예비 회수 · 전체 지적 수(비악화 확인) |

**사례는 지어 쓴 것이다** — 원래 원고는 사내 문서라 같은 꼴로 새로 지었다. 사람이 짚은 원문이 아니므로
못 잡았을 때의 무게가 대장보다 가볍다.

    python -X utf8 scripts/probe_layer2_discourse.py [--ref <커밋>] [--carrier discourse|kinds|both]
                                                     [--repeat 2] [--model opus] --json <경로>
    python -X utf8 scripts/probe_layer2_discourse.py --from-json <경로>

호출은 운반 문서마다 회차당 1회 · `claude-agent-sdk` OAuth(구독 · 과금 키 아님)
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import probe_layer2_kinds as kinds  # noqa: E402

CASES = REPO_ROOT / "tests" / "fixtures" / "layer2-discourse" / "cases.jsonl"
TITLE = "# AI와 함께 일하는 팀 — 세미나 발표 원고"
ORDER_SEED = 20261020        # 짝이 붙어 나오지 않게 섞는 순서 — 고정해야 회차끼리 같은 문서다


def load_cases() -> list[dict]:
    return [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]


def document(cases: list[dict] | None = None) -> str:
    """사례마다 절 하나 · 앞 문맥과 대상 문장을 한 문단(한 줄)에 둔다 — 줄 하나가 사례 하나다."""
    cases = load_cases() if cases is None else cases
    order = sorted(cases, key=lambda c: c["id"])
    random.Random(ORDER_SEED).shuffle(order)
    parts = [TITLE]
    for c in order:
        parts.append(f"## {c['heading']}\n\n{c['context']} {c['sentence']}".rstrip())
    return "\n\n".join(parts) + "\n"


def discourse_kinds(skill_text: str) -> list[str]:
    """9단계의 문장 사이 관계 항목 이름 — 규칙 글에서 읽는다(여기 적으면 두 곳이 된다)."""
    import re
    body = kinds.step_body(skill_text, kinds.STEP_TITLE)
    titles = re.findall(r"^   - \*\*(.+?)\*\*", body, re.M)
    names = {c["kind"] for c in load_cases()}
    return [t for t in titles if t in names]


def score_discourse(cases: list[dict], findings: list, doc: str, names: list[str]) -> dict:
    said = [f for f in findings if isinstance(f, dict)]

    def on_line(n):
        out = []
        for f in said:
            try:
                if int(f.get("line", -1)) == n:
                    out.append(f)
            except (TypeError, ValueError):
                continue
        return out

    rows = []
    for c in cases:
        n = kinds.line_of(doc, c["sentence"])
        here = on_line(n) if n is not None else []
        tight = [f for f in here if str(f.get("phrase", "")).strip()
                 and (c["text"] in str(f["phrase"]) or str(f["phrase"]).strip() in c["text"])]
        named = [f for f in here if any(k[:8] in str(f.get("category", "")) for k in names)
                 or "문장 사이" in str(f.get("category", ""))]
        rows.append({"id": c["id"], "expect": c["expect"], "line": n, "hits": len(here),
                     "tight": bool(tight), "named": len(named),
                     "found": [[f.get("phrase"), f.get("category"), f.get("fix"), f.get("decide")] for f in here]})
    fx = [r for r in rows if r["expect"] == "finding"]
    ok = [r for r in rows if r["expect"] == "clean"]
    return {"rows": rows, "said": len(said),
            "회수(줄)": sum(1 for r in fx if r["hits"]), "회수(표현)": sum(1 for r in fx if r["tight"]),
            "사례 수": len(fx),
            "정상 짝 지적 줄": sum(1 for r in ok if r["hits"]),
            "정상 짝 관계 갈래 지적": sum(r["named"] for r in ok), "정상 짝 수": len(ok)}


def rules_at(ref: str | None) -> tuple[str, str]:
    """그 커밋의 규칙 글 둘 — `None` 이면 작업 트리."""
    if ref is None:
        return kinds.RULES.read_text(encoding="utf-8"), kinds.SKILL_MD.read_text(encoding="utf-8")

    def show(path: Path) -> str:
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        return subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=REPO_ROOT, capture_output=True,
                              text=True, encoding="utf-8", check=True).stdout
    return show(kinds.RULES), show(kinds.SKILL_MD)


def call(rules: str, doc: str, model: str, timeout: float) -> dict:
    call_messages, parse_json = kinds.load_client("claude")
    r = call_messages(model=model, system=kinds.system_prompt().format(rules=rules),
                      user=kinds.USER.format(document=kinds.numbered(doc)),
                      max_tokens=12000, temperature=0, timeout=timeout)       # 판정기와 같은 상한
    raw = parse_json(r.get("text") or "") or []
    return {"findings": kinds.as_findings(raw), "malformed": kinds.malformed(raw),
            "cost_usd": r.get("cost_usd"), "usage": r.get("usage"), "model": r.get("model")}


def score_run(run: dict, names: list[str]) -> dict:
    if run["carrier"] == "discourse":
        return score_discourse(load_cases(), run["findings"], document(), names)
    doc = kinds.CARRIER.read_text(encoding="utf-8")
    items = kinds.planted() + kinds.held_out()
    s = kinds.score(items, run["findings"], doc, set())
    return {"said": s["said"], "대장 회수(줄)": sum(1 for r in s["rows"] if r["source"] == "대장" and (r["tight"] or r["loose"])),
            "대장 회수(표현)": sum(1 for r in s["rows"] if r["source"] == "대장" and r["tight"]),
            "예비 회수(표현)": sum(1 for r in s["rows"] if r["source"] == "예비" and r["tight"]),
            "심은 수": s["total"], "심지 않은 곳 지적": len(s["extra"])}


def report(out: dict) -> None:
    names = out["names"]
    cost = 0.0
    for run in out["runs"]:
        s = score_run(run, names)
        cost += run.get("cost_usd") or 0
        brief = {k: v for k, v in s.items() if k != "rows"}
        print(f"── {run['carrier']} · 회차 {run['repeat']} · {run.get('cost_usd') or 0:.3f}달러 · "
              f"칸 어긋남 {run.get('malformed')} · {json.dumps(brief, ensure_ascii=False)}")
        for r in s.get("rows", []):
            mark = ("○" if r["hits"] else "✕") if r["expect"] == "finding" else ("✕" if r["hits"] else "○")
            print(f"   {mark} {r['id']} {r['expect']:7} {r['line']}행 지적 {r['hits']}"
                  + "".join(f"\n        「{p}」 [{c}] → {fx} ({d})" for p, c, fx, d in r["found"]))
    print(f"규칙 {out['ref'] or '작업 트리'} · 합계 {cost:.3f}달러")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", help="이 커밋의 규칙 글로 부른다(없으면 작업 트리)")
    ap.add_argument("--carrier", choices=("discourse", "kinds", "both"), default="both")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--from-json", type=Path, dest="from_json")
    a = ap.parse_args()
    if a.from_json:
        report(json.loads(a.from_json.read_text(encoding="utf-8")))
        return
    core, skill = rules_at(a.ref)
    rules = kinds.rules_for("guided", core, skill)
    names = discourse_kinds(kinds.SKILL_MD.read_text(encoding="utf-8"))
    carriers = ["discourse", "kinds"] if a.carrier == "both" else [a.carrier]
    out = {"ref": a.ref, "model": a.model, "names": names, "rules_chars": len(rules),
           "carrier_sha": kinds.carrier_sha(), "runs": []}
    for k in range(a.repeat):
        for name in carriers:
            doc = document() if name == "discourse" else kinds.CARRIER.read_text(encoding="utf-8")
            run = call(rules, doc, a.model, a.timeout)
            run.update({"carrier": name, "repeat": k + 1})
            out["runs"].append(run)
            if a.json:      # 회차마다 남긴다 — 중간에 끊겨도 낸 호출을 잃지 않게
                a.json.parent.mkdir(parents=True, exist_ok=True)
                a.json.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    report(out)


if __name__ == "__main__":
    main()
