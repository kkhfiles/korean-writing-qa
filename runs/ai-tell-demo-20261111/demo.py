"""AI 말투 시연 — AI 말투를 일부러 모아 쓴 가상 주간보고를 실사용 흐름(checker2)으로 고치고 전후를 줄마다 견준 페이지를 만든다.

사용자(2026-11-11) 「가장 효과를 직접적으로 느낄 수 있는건 못쓴 글과 고쳐진 글을 바로 볼 수 있을때이다. … 모든 AI말투를
넣어서 업무 보고서를 하나 만든다음에 그걸 고친걸로 비교하면 극명하게 보일 듯」. 측정이 아니라 시연이다 — 원문은 세션이
말투 목록을 보고 지은 글이고, 측정 결과는 value-ai-docs-20261109 와 bench-external-20261031 에 있다.

원문(docs/report.md)과 심은 말투 목록(docs/planted.json), 고친 글은 저장소 밖 작업 폴더에 둔다. 모델 호출은 구독이다.

    python -X utf8 runs/ai-tell-demo-20261111/demo.py <작업 폴더> fix     # 실사용 흐름으로 고침(판정기 호출)
    python -X utf8 runs/ai-tell-demo-20261111/demo.py <작업 폴더> page    # 전후 비교 페이지
"""
from __future__ import annotations

import html
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALUE = HERE.parent / "value-ai-docs-20261109"


def load(name: str, path: Path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def planted(work: Path) -> list[tuple[str, str, str]]:
    """심은 말투 (원문 구절, 갈래, 말투 표지 정규식) — 구절이 원문에 없거나 표지가 원문에서 안 잡히면 멈춘다.

    남았는지는 구절이 아니라 표지로 본다 — 구절로 보면 「시점입니다」가 「시점이며」로 바뀐 것을 고친 것으로 셌다(첫 실행)."""
    src = (work / "docs" / "report.md").read_text(encoding="utf-8")
    items = [tuple(x) for x in json.loads((work / "docs" / "planted.json").read_text(encoding="utf-8"))]
    bad = [p for p, _, m in items if p not in src or not re.search(m, src, re.M)]
    if bad:
        raise SystemExit(f"원문에 없는 구절이나 표지: {bad}")
    return items


def fix(work: Path) -> None:
    planted(work)
    run = load("run", VALUE / "run.py")
    out = work / "out"
    out.mkdir(parents=True, exist_ok=True)
    src = (work / "docs" / "report.md").read_text(encoding="utf-8")
    after, cost = run.checker2(src, out / "work", "structured")
    (out / "result.md").write_text(after.rstrip() + "\n", encoding="utf-8")
    (out / "cost.json").write_text(json.dumps(cost, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(cost, ensure_ascii=False))


def page(work: Path) -> Path:
    show = load("showcase", VALUE / "showcase.py")
    items = planted(work)
    src = (work / "docs" / "report.md").read_text(encoding="utf-8")
    dst = (work / "out" / "result.md").read_text(encoding="utf-8")
    cost = json.loads((work / "out" / "cost.json").read_text(encoding="utf-8"))
    table, changed = show.rows(src.splitlines(), dst.splitlines())
    kept = [p for p, _, m in items if re.search(m, dst, re.M)]
    left = "\n".join(f"<tr><td>{html.escape(k)}</td><td>「{html.escape(p)}」</td>"
                     f"<td>{'남음' if p in kept else '없음'}</td></tr>" for p, k, _ in items)
    notes = json.loads((work / "docs" / "notes.json").read_text(encoding="utf-8"))
    notes_html = "\n".join(f"<li>{html.escape(n)}</li>" for n in notes)
    why = []
    for f in sorted((work / "out" / "work").glob("round*.json"), key=lambda p: int(p.stem[5:])):
        for x in json.loads(f.read_text(encoding="utf-8"))[0]["findings"]:
            if x.get("decide") == "fix" and x.get("phrase") and x.get("fix"):
                why.append(f"[{x.get('category')}] 「{x['phrase'].replace('**', '')}」 → 「{x['fix'].replace('**', '')}」")
    why = list(dict.fromkeys(why))
    why_html = "\n".join(f"<li>{html.escape(w)}</li>" for w in why) or "<li>판정기가 고칠 곳을 짚지 않음</li>"
    l1 = cost["1층"]
    origin = show.origin_lines(src.splitlines(), dst.splitlines()) + why + [p for p, _, _ in items]
    outdir = work / "page"
    outdir.mkdir(exist_ok=True)
    (outdir / "origin.txt").write_text("\n".join(dict.fromkeys(origin)) + "\n", encoding="utf-8")
    fill = {
        "{{TABLE}}": table, "{{PLANTED}}": left, "{{WHY}}": why_html, "{{NOTES}}": notes_html, "{{N_PLANTED}}": str(len(items)),
        "{{N_CHANGED}}": str(len(items) - len(kept)), "{{N_KEPT}}": str(len(kept)), "{{BLOCKS}}": str(changed),
        "{{L1}}": f"{l1['처음']}건 → {l1['끝']}건", "{{CALLS}}": f"{cost['calls']}회, {cost['sec']}초",
    }
    text = (HERE / "demo-template.html").read_text(encoding="utf-8")
    for k, v in fill.items():
        text = text.replace(k, v)
    dest = outdir / "ai-tell-demo.html"
    dest.write_text(text, encoding="utf-8")
    return dest


def main() -> int:
    work, cmd = Path(sys.argv[1]), sys.argv[2]
    if cmd == "fix":
        fix(work)
    elif cmd == "page":
        print(page(work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
