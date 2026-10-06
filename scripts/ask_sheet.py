"""사람 확인 표 — 판정기가 사용자에게 넘긴 지적을 md 표 한 장으로 만들고, 사용자가 적은 답을 읽는다.

**왜 표인가** (2026-10-07 사용자 — 「최소한 md 파일에 표 형태로 정리라도 해줘야 사람이 하나씩
본 뒤에 판단할 것 아닌가」) — 그 전에는 넘기는 모양이 정해져 있지 않아 세션마다 대화에
목록을 풀거나 확인 페이지를 손으로 만들었다. 한 번에 61건이 대화로 넘어가 사람이 하나씩
볼 수 없었다. 모양을 판정기가 정하면 어느 세션이 넘기든 같은 표가 나온다.

**한 줄 = 한 행** — 답은 줄에 묶인다(`layer2_coverage.py`). 같은 줄에 지적이 둘이면 한 행에
모으고 답도 하나만 받는다.

**표가 들고 있는 것** — 사람이 보는 칸(번호 · 줄 · 문장 · 갈래 · 판정기 제안 · 넘긴 까닭 · 답)과,
맨 아래 주석 안의 행별 열쇠(문서 경로 · 줄 번호 · 줄 해시). 열쇠가 있어야 표를 만든 뒤 문서가
바뀌었을 때 엉뚱한 줄에 답이 적히지 않는다.

**답 칸** — `고침` · `그대로` · `직접: …` · `보류` · 빈칸. 읽는 쪽(`judge_layer2.py --answers-from`)은
**`그대로`만 답 기록에 남긴다.** `고침`·`직접`을 답으로 적으면 고치기 전에 지적이 닫혀 고치지 않은
글이 배포를 통과한다 — 그래서 세션이 고칠 목록으로만 돌려주고, 고치면 지적이 저절로 사라진다.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

#: 표 맨 아래 주석의 머리 — 읽는 쪽이 이것으로 열쇠 묶음을 찾는다
KEY_MARK = "ask-sheet-keys"
COLUMNS = ("번호", "줄", "문장", "갈래", "판정기 제안", "넘긴 까닭", "답")
#: 문장 칸에 줄을 통째로 넣으면 표가 읽히지 않는다 — 짚은 표현 앞뒤만 남긴다
CONTEXT = 60
KEEP, EDIT, HOLD, BLANK = "그대로", "고침", "보류", ""

HEAD = """# 사람 확인 표 — 판정기가 정하지 못한 표현

- **만든 시각**: {at}
- **대상 문서**: {docs}
- **건수**: 줄 {lines}개 · 지적 {asks}건
- **답하는 법**: 행마다 맨 오른쪽 「답」 칸에 아래 가운데 하나를 적음
  - `고침` — 판정기 제안대로 고침
  - `그대로` — 지금 표현 유지 · 뒤에 까닭을 붙여도 됨(예: `그대로 — 정해진 이름`)
  - `직접: <원하는 문구나 지시>` — 제안과 다르게 고침
  - `보류` — 아직 못 정함
- **다 적은 뒤**: 세션에 알리면 `judge_layer2.py --answers-from <이 파일>` 로 읽음
  - `그대로` — 답 기록에 남음 · 이 줄은 다시 묻지 않음
  - `고침` · `직접` — 세션이 고친 뒤 고친 줄을 다시 판정함
  - `보류` · 빈칸 — 답이 없는 것으로 남아 발행과 배포가 막힘
- **표를 다시 만들 때**: 문서를 고친 뒤에는 표를 새로 만듦 · 바뀐 줄의 답은 받지 않음
"""


def cell(text: str) -> str:
    """표 칸에 넣을 글 — 칸 경계(`|`)와 강조 · 태그로 읽힐 글자를 막는다."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    for ch in ("\\", "|", "*", "`"):
        text = text.replace(ch, "\\" + ch)
    return text.replace("<", "&lt;")


def excerpt(line: str, phrases: list[str]) -> str:
    """짚은 표현을 굵게 한 문장 칸 — 줄이 길면 첫 표현 앞뒤만."""
    line = re.sub(r"\s+", " ", line).strip()
    found = [p for p in phrases if p and p in line]
    # 한 표현이 다른 표현 안에 들면 긴 쪽만 굵게 — 겹쳐 씌우면 강조 기호가 엇갈린다
    found = [p for p in found if not any(p != q and p in q for q in found)]
    if not found:
        # 판정기가 낸 표현이 줄에 글자 그대로 없을 때 — 표현과 줄을 따로 보인다
        lead = " · ".join(f"「{cell(p)}」" for p in phrases if p)
        return f"{lead} — {cell(line[:CONTEXT * 2])}{'…' if len(line) > CONTEXT * 2 else ''}"
    first = min(line.index(p) for p in found)
    last = max(line.index(p) + len(p) for p in found)
    a, b = max(0, first - CONTEXT), min(len(line), last + CONTEXT)
    piece = line[a:b]
    # 굵게는 칸 글로 바꾼 뒤에 씌운다 — 표현 안의 `*` 가 강조를 깨지 않게
    out = cell(piece)
    for p in sorted(set(found), key=len, reverse=True):
        out = out.replace(cell(p), f"**{cell(p)}**", 1)
    return ("…" if a else "") + out + ("…" if b < len(line) else "")


def group(lines: list[str], asks: list[tuple[int, dict]]) -> list[tuple[int, list[dict]]]:
    """(줄 번호, 그 줄의 지적들) — 줄 순서."""
    by: dict[int, list[dict]] = {}
    for n, ask in asks:
        by.setdefault(n, []).append(ask)
    return sorted(by.items())


def render(docs: list[tuple[Path, list[str], list[tuple[int, dict]]]],
           line_key, now: datetime | None = None) -> str:
    """표 한 장 — `docs` 는 (문서 경로, 보이는 글 줄들, 열린 사람 확인) 묶음.

    `line_key` 는 `layer2_coverage.line_key` 를 받는다(시험이 같은 함수를 쓴다).
    """
    now = now or datetime.now()
    keys: dict[str, dict] = {}
    body: list[str] = []
    k = 0
    total_lines = total_asks = 0
    for path, lines, asks in docs:
        rows = group(lines, asks)
        if not rows:
            continue
        body += ["", f"## {path.name}", "",
                 "| " + " | ".join(COLUMNS) + " |",
                 "|" + "---|" * len(COLUMNS)]
        for n, items in rows:
            k += 1
            total_lines += 1
            total_asks += len(items)
            qid = f"Q{k}"
            phrases = [str(a.get("phrase") or "").strip() for a in items]
            if len(items) == 1:
                kind, fix, why = (cell(items[0].get(f)) for f in ("category", "fix", "why"))
            else:
                kind = "<br>".join(dict.fromkeys(cell(a.get("category")) for a in items))
                fix = "<br>".join(f"「{cell(p)}」 → {cell(a.get('fix'))}" for p, a in zip(phrases, items))
                why = "<br>".join(f"「{cell(p)}」 {cell(a.get('why'))}" for p, a in zip(phrases, items))
            body.append(f"| {qid} | {n} | {excerpt(lines[n - 1], phrases)} | {kind} | {fix} | {why} |  |")
            keys[qid] = {"doc": path.resolve().as_posix(), "line": n,
                         "line_key": line_key(lines[n - 1])}
    head = HEAD.format(at=now.strftime("%Y-%m-%d %H:%M"),
                       docs=" · ".join(p.name for p, _, a in docs if a) or "없음",
                       lines=total_lines, asks=total_asks)
    tail = ["", f"<!-- {KEY_MARK}", json.dumps(keys, ensure_ascii=False, indent=0), "-->", ""]
    return head + "\n".join(body + tail)


def _cells(row: str) -> list[str]:
    inner = row.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return [c.strip() for c in re.split(r"(?<!\\)\|", inner)]


def parse(text: str) -> tuple[dict[str, dict], dict[str, str]]:
    """(행별 열쇠, 행별 답 원문). ⛔ 열쇠 묶음이 없으면 ValueError — 줄을 짐작해 답을 적지 않는다."""
    m = re.search(rf"<!--\s*{KEY_MARK}\s*(.*?)-->", text, re.S)
    if not m:
        raise ValueError("사람 확인 표가 아닙니다 — 맨 아래 열쇠 주석이 없습니다 · "
                         "judge_layer2.py --sheet 로 만든 표를 줍니다")
    keys = json.loads(m.group(1))
    answers: dict[str, str] = {}
    for raw in text[:m.start()].splitlines():
        if not re.match(r"\s*\|\s*Q\d+\s*\|", raw):
            continue
        cells = _cells(raw)
        if len(cells) != len(COLUMNS):
            raise ValueError(f"칸 수가 맞지 않는 행 — {cells[0]} · 칸 안의 `|` 는 `\\|` 로 적습니다")
        answers[cells[0]] = cells[-1].replace("\\|", "|").strip()
    return keys, answers


def kind_of(answer: str) -> str:
    """답 원문을 넷으로 — 그대로 · 보류 · 빈칸 · 나머지는 모두 고침(제안대로든 직접이든)."""
    a = answer.strip().strip("`").strip()
    if not a:
        return BLANK
    if a.startswith(KEEP):
        return KEEP
    if a.startswith(HOLD):
        return HOLD
    return EDIT
