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
#: 고친 글과 판정 기록을 두는 작업 폴더 안 이름 — `--out <이름>` 으로 바꿈(앞선 실행을 남긴 채 다시 돌릴 때)
OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "out"


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
    out = work / OUT
    out.mkdir(parents=True, exist_ok=True)
    src = (work / "docs" / "report.md").read_text(encoding="utf-8")
    after, cost = run.checker2(src, out / "work", "structured")
    (out / "result.md").write_text(after.rstrip() + "\n", encoding="utf-8")
    (out / "cost.json").write_text(json.dumps(cost, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(cost, ensure_ascii=False))


def row_notes(work: Path, src: str) -> list[tuple[str, str]]:
    """고친 이유 — (그 지적이 달린 줄의 글, 표시할 한 줄). 2층은 판정 기록, 1층은 원문을 검사기에 다시 돌린 지적.

    `--why` 같은 명령을 만들기 전에 화면에서 먼저 보이려는 것(사용자 2026-11-11 「비교 페이지에는 기능으로 만들기 전에
    볼 수 있게」). 판정 기록의 줄 번호는 그 회차 판의 번호라 원문 행과 안 맞으므로 줄 글로 행을 찾는다."""
    run = load("run", VALUE / "run.py")
    out = []
    log = work / OUT / "work" / "judge.jsonl"
    for n, raw in enumerate(log.read_text(encoding="utf-8").splitlines()):
        rec = json.loads(raw)
        again = "고친 줄 재판정 · " if n else ""     # 첫 기록만 원문 전체 판정, 그 뒤는 고친 줄을 다시 판정한 회차
        texts = {f.get("line_key"): f.get("text") for f in rec.get("fixes") or []}
        for f in rec.get("fixes") or []:
            fix = (f.get("fix") or "").replace("**", "").strip()
            act = f"→ 「{fix}」" if fix and fix != "(문장 삭제)" else "지움"
            why = f" — {f['why']}" if f.get("why") else ""
            out.append((f.get("text") or f.get("phrase") or "",
                        f"[{again}{f.get('category')}] 「{(f.get('phrase') or '').replace('**', '').strip()}」 {act}{why}"))
        for f in rec.get("asks") or []:
            out.append((texts.get(f.get("line_key")) or f.get("phrase") or "",
                        f"[{again}{f.get('category')}] 「{(f.get('phrase') or '').strip()}」 사람 확인으로 넘김(이 시연은 답하지 않음)"
                        + (f" — {f['why']}" if f.get("why") else "")))
    tmp = work / "_src.md"
    tmp.write_text("---\nform: structured\n---\n" + src, encoding="utf-8")
    lines = src.splitlines()
    for kind, msg in run.l1_errors(tmp):
        m = re.match(r"(\d+)행\s+(.*)$", msg)
        if m and 0 < int(m.group(1)) - 3 <= len(lines):
            q = re.match(r"「[^」]+」", m.group(2))
            out.append((lines[int(m.group(1)) - 4], f"[규칙 검사] {kind}" + (f" {q.group(0)}" if q else "")))
    tmp.unlink()
    return out


def assign(notes: list[tuple[str, str]], blocks: list[tuple[list[str], list[str]]]) -> dict[int, list[str]]:
    """지적마다 줄 글이 가장 닮은 바뀐 행 하나에 붙인다 — 닮은 정도 0.5 미만이면 버린다."""
    import difflib
    got: dict[int, list[str]] = {}
    for text, note in notes:
        t = text.replace("**", "").strip()
        best, score = None, 0.0
        for i, (left, right) in enumerate(blocks):
            for line in left + right:
                r = difflib.SequenceMatcher(None, t, line).ratio()
                if r > score:
                    best, score = i, r
        if best is not None and score >= 0.5 and note not in got.get(best, []):
            got.setdefault(best, []).append(note)
    return got


def page(work: Path) -> Path:
    show = load("showcase", VALUE / "showcase.py")
    items = planted(work)
    src = (work / "docs" / "report.md").read_text(encoding="utf-8")
    dst = (work / OUT / "result.md").read_text(encoding="utf-8")
    cost = json.loads((work / OUT / "cost.json").read_text(encoding="utf-8"))
    blocks: list[tuple[list[str], list[str]]] = []
    show.rows(src.splitlines(), dst.splitlines(), lambda i, l, r: blocks.append((l, r)) or "")
    placed = assign(row_notes(work, src), blocks)
    table, changed = show.rows(src.splitlines(), dst.splitlines(), lambda i, l, r: (
        '<ul class="rowwhy">' + "".join(f"<li>{html.escape(n)}</li>" for n in placed[i]) + "</ul>") if i in placed else "")
    n_notes = sum(len(v) for v in placed.values())
    notes_by_tools = [n for v in placed.values() for n in v]     # 판정기와 검사기가 쓴 글 — 원본으로 선언
    kept = [p for p, _, m in items if re.search(m, dst, re.M)]
    left = "\n".join(f"<tr><td>{html.escape(k)}</td><td>「{html.escape(p)}」</td>"
                     f"<td>{'남음' if p in kept else '없음'}</td></tr>" for p, k, _ in items)
    notes = json.loads((work / "docs" / "notes.json").read_text(encoding="utf-8"))
    notes_html = "\n".join(f"<li>{html.escape(n)}</li>" for n in notes)
    why = []
    for f in sorted((work / OUT / "work").glob("round*.json"), key=lambda p: int(p.stem[5:])):
        for x in json.loads(f.read_text(encoding="utf-8"))[0]["findings"]:
            if x.get("decide") == "fix" and x.get("phrase") and x.get("fix"):
                why.append(f"[{x.get('category')}] 「{x['phrase'].replace('**', '')}」 → 「{x['fix'].replace('**', '')}」")
    why = list(dict.fromkeys(why))
    why_html = "\n".join(f"<li>{html.escape(w)}</li>" for w in why) or "<li>판정기가 고칠 곳을 짚지 않음</li>"
    l1 = cost["1층"]
    origin = show.origin_lines(src.splitlines(), dst.splitlines()) + why + [p for p, _, _ in items] + notes_by_tools
    outdir = work / "page"
    outdir.mkdir(exist_ok=True)
    (outdir / "origin.txt").write_text("\n".join(dict.fromkeys(origin)) + "\n", encoding="utf-8")
    fill = {
        "{{TABLE}}": table, "{{N_NOTES}}": str(n_notes), "{{PLANTED}}": left, "{{WHY}}": why_html, "{{NOTES}}": notes_html, "{{N_PLANTED}}": str(len(items)),
        "{{N_CHANGED}}": str(len(items) - len(kept)), "{{N_KEPT}}": str(len(kept)), "{{BLOCKS}}": str(changed),
        "{{L1}}": f"{l1['처음']}건 → {l1['끝']}건", "{{CALLS}}": f"{cost['calls']}회, {cost['sec']}초",
    }
    text = (HERE / "demo-template.html").read_text(encoding="utf-8")
    # 실행 기록에서 채운 수(호출 수, 건수)가 든 줄도 원본으로 선언 — 다시 만들 때마다 수가 바뀌어 판정기가 같은 줄을
    #  거듭 판정하다 재판정 상한으로 사람 확인을 올렸다(2026-11-11)
    filled = []
    for line in text.splitlines():
        if "{{" in line and not any(k in line for k in ("{{TABLE}}", "{{PLANTED}}", "{{WHY}}", "{{NOTES}}")):
            for k, v in fill.items():
                line = line.replace(k, v)
            filled.append(re.sub(r"<[^>]+>", "", line).strip())
    with (outdir / "origin.txt").open("a", encoding="utf-8") as f:
        f.write("\n".join(x for x in filled if x) + "\n")
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
