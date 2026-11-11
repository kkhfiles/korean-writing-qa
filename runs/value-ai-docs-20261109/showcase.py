"""AI 초안 전후 비교 페이지 — 측정에서 나온 원문과 검사기(checker2)가 고친 글을 손대지 않고 나란히 싣는다.

사용자(2026-11-09) 「AI가 쓴 글 before를, 고친글 after를 봤을 때 확 공감이 될 경우에 받아서 써볼 것이다. 타 도구
비교자료와 성능 비교 자료는 객관성을 더해줄 뿐」. 여섯 편을 모두 싣는다 — 골라 보이면 홍보가 측정을 앞선다.

원문과 고친 글, 판정기가 적은 고친 까닭은 이 세션이 쓴 글이 아니므로 줄마다 같은 글을 원본 파일에 적고
`<meta name="origin">` 으로 선언한다(남이 쓴 줄은 발행 검사가 막지 않음).

    python -X utf8 runs/value-ai-docs-20261109/showcase.py <작업 폴더> <출력 폴더>
"""
from __future__ import annotations

import difflib
import html
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOCS = [("gpt-weekly", "GPT 6.1 Sol", "주간보고"), ("gemini-weekly", "Gemini 3.8 Flash", "주간보고"),
        ("claude-weekly", "Claude Opus 5.5", "주간보고"), ("gpt-notice", "GPT 6.1 Sol", "사내 공지"),
        ("gemini-notice", "Gemini 3.8 Flash", "사내 공지"), ("claude-notice", "Claude Opus 5.5", "사내 공지")]


def load(name: str, path: Path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def shown(line: str) -> tuple[str, str]:
    """마크다운 한 줄을 화면 글과 갈래로 — 굵게 표시를 빼고 제목 기호를 뗀다."""
    t = line.replace("**", "").rstrip()
    m = re.match(r"^(#{1,6})\s+(.*)$", t)
    if m:
        return m.group(2), "h"
    if re.match(r"^\s*\|?\s*:?-{3,}", t):
        return "", "skip"
    return t, "p"


def marks(a: str, b: str, side: str) -> str:
    """한쪽 줄을 다른 쪽과 견주어 달라진 글자만 표시 — 원문 쪽은 <del>, 고친 쪽은 <ins>. 화면 글은 그 줄 그대로."""
    # 어절 단위 — 글자 단위로 견주면 원문 쪽 표시가 조사와 어미마다 끊겨 읽기 어렵다(첫 화면 확인)
    a, b = re.findall(r"\S+|\s+", a), re.findall(r"\S+|\s+", b)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        seg = "".join(a[i1:i2] if side == "old" else b[j1:j2])
        if op == "equal":
            out.append(html.escape(seg))
        elif seg:
            tag = "del" if side == "old" else "ins"
            out.append(f"<{tag}>{html.escape(seg)}</{tag}>")
    return "".join(out)


def rows(src: list[str], dst: list[str], annotate=None) -> tuple[str, int]:
    """줄 짝을 표 행으로 — (HTML, 바뀐 줄 묶음 수).

    `annotate(번호, 원문 줄들, 고친 줄들)` 가 HTML 을 돌려주면 바뀐 행 아래에 한 행으로 붙인다(고친 이유 · 시연 페이지)."""
    a = [shown(l) for l in src]
    b = [shown(l) for l in dst]
    a = [x for x in a if x[1] != "skip" and x[0].strip()]
    b = [x for x in b if x[1] != "skip" and x[0].strip()]
    out, changed = [], 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [x[0] for x in a], [x[0] for x in b],
                                                       autojunk=False).get_opcodes():
        left, right = a[i1:i2], b[j1:j2]
        if op == "equal":
            for (t, k), _ in zip(left, right):
                cell = f'<div class="ln {k}">{html.escape(t)}</div>'
                out.append(f'<tr class="same"><td>\n{cell}\n</td><td>\n{cell}\n</td></tr>')
            continue
        changed += 1
        old_all, new_all = " ".join(t for t, _ in left), " ".join(t for t, _ in right)
        lc = "\n".join(f'<div class="ln {k}">{marks(t, new_all, "old")}</div>' for t, k in left)
        rc = "\n".join(f'<div class="ln {k}">{marks(old_all, t, "new")}</div>' for t, k in right)
        out.append(f'<tr class="diff"><td>\n{lc or "<div class=\'ln none\'>(없음)</div>"}\n</td>'
                   f'<td>\n{rc or "<div class=\'ln none\'>(지움)</div>"}\n</td></tr>')
        note = annotate(changed - 1, [t for t, _ in left], [t for t, _ in right]) if annotate else ""
        if note:
            out.append(f'<tr class="why-row"><td colspan="2">\n{note}\n</td></tr>')
    return "\n".join(out), changed


def origin_lines(src: list[str], dst: list[str]) -> list[str]:
    return [t for t, k in (shown(l) for l in src + dst) if k != "skip" and t.strip()]


def reasons(work: Path, name: str) -> list[str]:
    """판정기가 낸 고칠 지적(갈래, 짚은 표현, 수정안)과 1층 지적 갈래 — 같은 것은 한 번."""
    out = []
    folder = work / "out" / name / "checker2" / "work"
    for f in sorted(folder.glob("round*.json"), key=lambda p: int(p.stem[5:])):
        for x in json.loads(f.read_text(encoding="utf-8"))[0]["findings"]:
            if x.get("decide") == "fix" and x.get("phrase") and x.get("fix"):
                out.append(f"[{x.get('category')}] 「{x['phrase'].replace('**', '')}」 → 「{x['fix'].replace('**', '')}」")
    return list(dict.fromkeys(out))


def main() -> int:
    work, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    run = load("run", HERE / "run.py")
    tabs, panels, origin = [], [], []
    for i, (name, model, kind) in enumerate(DOCS):
        src = (work / "docs" / f"{name}.md").read_text(encoding="utf-8").splitlines()
        dst = (work / "out" / name / "checker2" / "result.md").read_text(encoding="utf-8").splitlines()
        cost = json.loads((work / "out" / name / "checker2" / "cost.json").read_text(encoding="utf-8"))
        tmp = outdir / "_src.md"
        tmp.write_text(f"---\nform: {run.form_of(name)}\n---\n" + "\n".join(src) + "\n", encoding="utf-8")
        l1 = {}
        for k, _ in run.l1_errors(tmp):
            l1[k] = l1.get(k, 0) + 1
        tmp.unlink()
        table, changed = rows(src, dst)
        why = reasons(work, name)
        origin += origin_lines(src, dst) + why
        l1_text = ", ".join(f"{k} {v}건" for k, v in l1.items()) or "없음"
        why_html = "\n".join(f"<li>{html.escape(w)}</li>" for w in why) or "<li>판정기가 고칠 곳을 짚지 않음</li>"
        tabs.append(f'<button type="button" role="tab" aria-selected="{str(i == 0).lower()}" data-i="{i}">'
                    f'{kind}<span>{model}</span></button>')
        panels.append(f"""<section class="panel" data-i="{i}"{'' if i == 0 else ' hidden'}>
<dl class="facts">
<div><dt>쓴 모델</dt><dd>{model}</dd></div>
<div><dt>바뀐 묶음</dt><dd>{changed}곳</dd></div>
<div><dt>고친 1층 지적</dt><dd>{html.escape(l1_text)}</dd></div>
<div><dt>판정 호출</dt><dd>{cost['calls']}회, {cost['sec']}초</dd></div>
</dl>
<div class="scroll"><table class="pair"><thead><tr><th>AI가 쓴 원문</th><th>검사기로 고친 글</th></tr></thead>
<tbody>
{table}
</tbody></table></div>
<details><summary>판정기가 짚은 표현 {len(why)}건</summary><ul class="why">
{why_html}
</ul></details>
</section>""")
    (outdir / "origin.txt").write_text("\n".join(dict.fromkeys(origin)) + "\n", encoding="utf-8")
    page = (HERE / "showcase-template.html").read_text(encoding="utf-8")
    page = page.replace("{{TABS}}", "\n".join(tabs)).replace("{{PANELS}}", "\n".join(panels))
    (outdir / "ai-before-after.html").write_text(page, encoding="utf-8")
    print(outdir / "ai-before-after.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
