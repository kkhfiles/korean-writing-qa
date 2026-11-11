"""재판정이 「고치다 뜻이 바뀐 곳」을 얼마나 잡는지 — 답을 알고 만든 고친 줄 30개(뜻 그대로 5, 뜻 바뀜 25)로 잰다.

사용자(2026-11-11) 지시 「다 하시죠」 중 「뜻바뀜측정」. AI 말투 시연에서 첫 판정이 문장을 통째로 다시 쓰며 「자동으로」를
넣고 출처 「(QA팀)」을 주체로 바꿨는데, 기준 판과 대조하는 재판정이 둘 다 못 잡았다. 기계 경고(원문 줄에 없던 낱말)는
네 어절 이상 수정안 382건 중 250건에 걸려 잡음이 커서 넣지 않았다.

기준 판(main)에 고치기 전 줄, 작업 가지에 고친 줄을 두고 `judge_layer2 --since main` 으로 판정한다(실사용과 같은
기준 판 대조 경로). 판정 기록은 실행 폴더 안에만 남긴다(`bench_loop.isolated`). 모델 호출은 구독이다.

    python -X utf8 runs/meaning-drift-20261111/run.py <작업 폴더> [회차 수]
"""
from __future__ import annotations

import collections
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
os.environ["LLM_PLAYBOOK_BILLING"] = "subscription"

import bench_loop  # noqa: E402
import judge_layer2 as judge  # noqa: E402

HEAD = ["---", "form: structured", "---", "", "# 주간 보고", "", "**고친 내용 점검** — 지난 판에서 고친 줄", ""]


class Scripted:
    """앞 회차 판정을 흉내 — 줄마다 「고치기 전 → 고친 뒤」를 판정기 수정안으로 기록한다(모델 안 부름)."""

    def __init__(self, items: list[dict]):
        self.items = items

    def pair(self):
        def call(**_):
            return {"text": json.dumps(self.items, ensure_ascii=False), "usage": {}, "model": "scripted"}
        return call, json.loads


def alone(cases: list[dict]) -> tuple[list[str], list[str], list[int]]:
    """고친 줄만 모은 문서 — 기준 판, 고친 판, 고친 줄 번호."""
    first = len(HEAD) + 1
    return (HEAD + [c["before"] for c in cases], HEAD + [c["after"] for c in cases],
            [first + i for i in range(len(cases))])


def mixed(cases: list[dict], before_doc: Path, after_doc: Path) -> tuple[list[str], list[str], list[int]]:
    """AI 말투 시연 문서(원문과 첫 판정으로 고친 판)의 하위 항목 사이사이에 고친 줄을 끼움 — 재판정이 다른 결함과
    다른 고친 줄 수십 개를 한 번에 본다. 사례는 차례대로 하위 항목마다 돌아가며 나눠 종류가 한곳에 몰리지 않게 함."""
    head = ["---", "form: structured", "---", ""]
    old, new = before_doc.read_text(encoding="utf-8").splitlines(), after_doc.read_text(encoding="utf-8").splitlines()
    slots = [i for i, s in enumerate(old) if s.startswith("  * ")]
    if sum(s.startswith("  * ") for s in new) != len(slots):
        raise SystemExit("두 판의 하위 항목 수가 다름")
    groups = [cases[k::len(slots)] for k in range(len(slots))]

    def build(lines: list[str], side: str) -> tuple[list[str], list[int]]:
        out, marks, k = list(head), [], 0
        for s in lines:
            out.append(s)
            if s.startswith("  * "):
                for c in groups[k]:
                    out.append("  * " + c[side][2:])
                    marks.append((cases.index(c), len(out)))
                k += 1
        return out, [n for _, n in sorted(marks)]
    base, _ = build(old, "before")
    fixed, lines = build(new, "after")
    return base, fixed, lines


def one(work: Path, cases: list[dict], own: bool, layout=None) -> dict:
    """`own` — 고친 줄이 판정기 자신의 수정안이었다는 기록을 먼저 남김(재판정 프롬프트에 「고친 까닭」이 실림).
    `layout` — 문서 짜는 법(기본은 고친 줄만 모은 `alone`)."""
    work.mkdir(parents=True, exist_ok=True)
    doc = work / "doc.md"
    base, fixed, where = (layout or alone)(cases)

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@localhost", "-C", str(work), *args],
                       capture_output=True, check=True)
    doc.write_text("\n".join(base) + "\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "doc.md")
    git("commit", "-q", "-m", "base")
    git("switch", "-q", "-c", "work")
    out = work / "judge.json"
    said = io.StringIO()
    with bench_loop.isolated(work), contextlib.redirect_stdout(said):
        if own:
            prior = [{"line": n, "phrase": c["before"][2:], "category": "번역투 줄이기", "fix": c["after"][2:],
                      "why": "", "decide": "fix"} for n, c in zip(where, cases)]
            judge.judge(doc, "opus", 60, Scripted(prior).pair())
        doc.write_text("\n".join(fixed) + "\n", encoding="utf-8")
        rc = judge.main([str(doc), "--since", "main", "--json", str(out), "--backend", "claude"])
    (work / "judge-output.txt").write_text(said.getvalue(), encoding="utf-8")
    if not out.is_file():
        raise SystemExit(f"판정 실패 rc={rc} — {work / 'judge-output.txt'}")
    findings = json.loads(out.read_text(encoding="utf-8"))[0]["findings"]
    rows = []
    for n, c in zip(where, cases):
        mine = [f for f in findings if f.get("line") == n]
        drift = [f for f in mine if "뜻이 바뀐" in str(f.get("category") or "")]
        rows.append({"kind": c["kind"], "line": n, "drift_flagged": bool(drift), "any_flagged": bool(mine),
                     "categories": [f.get("category") for f in mine],
                     "why": [str(f.get("why") or "")[:120] for f in drift]})
    return {"rc": rc, "rows": rows}


def main() -> int:
    work = Path(sys.argv[1])
    times = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    own = "--own" in sys.argv          # 판정기 자신의 수정안으로 고친 줄 조건
    name = sys.argv[sys.argv.index("--cases") + 1] if "--cases" in sys.argv else "cases"   # cases-multi: 여러 곳을 함께 고친 줄
    cases = json.loads((HERE / f"{name}.json").read_text(encoding="utf-8"))
    layout = None
    if "--mixed" in sys.argv:          # --mixed <시연 원문> <첫 판정으로 고친 판>: 다른 결함과 섞어 한 번에 판정
        at = sys.argv.index("--mixed")
        before_doc, after_doc = Path(sys.argv[at + 1]), Path(sys.argv[at + 2])
        layout = lambda cs: mixed(cs, before_doc, after_doc)  # noqa: E731
    tag = ("own" if own else "run") + ("" if name == "cases" else "-" + name.split("-", 1)[1]) + \
        ("-mixed" if layout else "") + ("-" + sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "")
    runs = [one(work / f"{tag}{k}", cases, own, layout) for k in range(1, times + 1)]
    summary = {}
    for kind in dict.fromkeys(c["kind"] for c in cases):
        got = [r["drift_flagged"] for run in runs for r in run["rows"] if r["kind"] == kind]
        anyf = [r["any_flagged"] for run in runs for r in run["rows"] if r["kind"] == kind]
        summary[kind] = {"뜻 바뀜으로 짚음": f"{sum(got)}/{len(got)}", "어떤 지적이든": f"{sum(anyf)}/{len(anyf)}"}
    result = {"cases": len(cases), "runs": len(runs), "summary": summary,
              "rows": [r for run in runs for r in run["rows"]]}
    (HERE / f"result-{tag}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8",
                                            newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
