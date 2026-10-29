"""사람 확인 표 — 판정기가 사용자에게 넘긴 지적을 md 표 한 장으로 만들고, 사용자가 적은 답을 읽는다.

**왜 표인가** (2026-10-07 사용자 — 「최소한 md 파일에 표 형태로 정리라도 해줘야 사람이 하나씩
본 뒤에 판단할 것 아닌가」) — 그 전에는 넘기는 모양이 정해져 있지 않아 세션마다 대화에
목록을 풀거나 확인 페이지를 손으로 만들었다. 한 번에 61건이 대화로 넘어가 사람이 하나씩
볼 수 없었다. 모양을 판정기가 정하면 어느 세션이 넘기든 같은 표가 나온다.

**한 줄 = 한 행** — 답은 줄에 묶인다(`layer2_coverage.py`). 같은 줄에 지적이 둘이면 한 행에
모으고 답도 하나만 받는다.

**표가 들고 있는 것** — 사람이 보는 칸(#, 원문, 고친 말, 고친 이유, 제 의견, 답)과,
맨 아래 주석 안의 행별 열쇠(문서 경로 · 줄 번호 · 줄 해시). 열쇠가 있어야 표를 만든 뒤 문서가
바뀌었을 때 엉뚱한 줄에 답이 적히지 않는다.

**칸을 이렇게 정한 까닭** (2026-10-28 사용자가 정한 판정 요청 형식) — 사람이 고르는 것은 「원문을
고칠까」 하나다. 줄 번호와 갈래 이름은 답을 고르는 데 안 쓰여 표에서 뺐다(줄 번호는 열쇠에 있다).
「제 의견」은 표를 넘기는 세션이 채운다. 의견이 있어야 「전부 의견대로」처럼 짧게 답할 수 있다.

**답 칸** — `고침` · `그대로` · `직접: …` · `보류` · 빈칸. 읽는 쪽(`judge_layer2.py --answers-from`)은
**`그대로`만 답 기록에 남긴다.** `고침`·`직접`을 답으로 적으면 고치기 전에 지적이 닫혀 고치지 않은
글이 배포를 통과한다 — 그래서 세션이 고칠 목록으로만 돌려주고, 고치면 지적이 저절로 사라진다.
첫 낱말이 넷 가운데 하나가 아닌 글(「이건 그냥 놔두자」)은 닫지 않고 따로 돌려준다 — 처음에는
고칠 것으로 묶었는데, 유지하라는 답이 「고칠 것」 목록에 실려 세션이 거꾸로 고칠 뻔했다(2026-10-07).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

#: 표 맨 아래 주석의 머리 — 읽는 쪽이 이것으로 열쇠 묶음을 찾는다
KEY_MARK = "ask-sheet-keys"
COLUMNS = ("#", "원문", "고친 말", "고친 이유", "제 의견", "답")
#: 2026-10-29 전에 만든 표의 칸 수(번호, 줄, 문장, 갈래, 판정기 제안, 넘긴 까닭, 답) — 사용자 손에
#: 가 있는 표의 답을 버리지 않으려고 읽기만 받는다
LEGACY_WIDTH = 7
#: 짧은 답의 머리 — 이 말로 시작하면 「제 의견」 칸을 답으로 쓴다
AS_OPINION = "의견대로"
#: 문장 칸에 줄을 통째로 넣으면 표가 읽히지 않는다 — 짚은 표현 앞뒤만 남긴다
CONTEXT = 60
KEEP, EDIT, HOLD, BLANK = "그대로", "고침", "보류", ""
DIRECT = "직접"
#: 첫 낱말이 넷 가운데 하나가 아닌 답 — 「이건 그냥 놔두자」는 유지이고 「빼는게 낫겠다」는 고침이다.
#: 낱말로 가르면 「놔두지 말고 고치자」가 유지로 닫힌다 — 그래서 닫지 않고 세션이 원문을 읽게 넘긴다.
FREE = "글"

HEAD = """# 사람 확인 표 — 판정기가 정하지 못한 표현

**묻는 것**: 원문을 고칠까요?

- **만든 시각**: {at}
- **대상 문서**: {docs}
- **건수**: 줄 {lines}개, 지적 {asks}건
- **답 고르는 법**: 행마다 맨 오른쪽 「답」 칸에 아래 가운데 하나를 적음
  - `고침` — 원문이 결함이고 고친 말도 좋음
  - `그대로` — 원문이 정상, 뒤에 까닭을 붙여도 됨(예: `그대로 — 정해진 이름`)
  - `직접: <원하는 문구나 지시>` — 원문은 결함인데 고친 말이 별로임
  - `보류` — 아직 못 정함
- **「제 의견」 칸**: 표를 넘기는 세션이 채움, 비어 있으면 세션이 아직 의견을 적지 않은 것
- **짧게 답해도 됨**: 「전부 의견대로」, 「의견대로, 단 3 그대로, 7 직접: …」, 「고침 2, 3」 — 대화로 답하면 세션이 `--reply` 로 읽음
- **다 적은 뒤**: 세션에 알리면 `judge_layer2.py --answers-from <이 파일>` 로 읽음
  - `그대로` — 답 기록에 남음 · 이 줄은 다시 묻지 않음
  - `고침` · `직접` — 세션이 고친 뒤 고친 줄을 다시 판정함
  - `보류` · 빈칸 — 답이 없는 것으로 남아 발행과 배포가 막힘
  - 그 밖의 글 — 세션이 원문을 읽고 고칠지 유지할지 가름 · 유지하는 뜻이면 원문을 답 기록에 남김
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


def row_cells(items: list[dict]) -> tuple[str, str, str]:
    """(고친 말, 고친 이유, 제 의견) 칸 — 한 줄에 지적이 둘 이상이면 표현을 앞에 붙여 줄을 나눈다.

    「제 의견」은 지적에 `opinion` 이 있을 때만 채운다 — 판정기는 정하지 못해 넘긴 것이라 의견이 없고,
    세션이 표를 넘기기 전에 칸을 채운다.
    """
    phrases = [str(a.get("phrase") or "").strip() for a in items]
    opinion = "<br>".join(dict.fromkeys(cell(a.get("opinion")) for a in items if a.get("opinion")))
    if len(items) == 1:
        return cell(items[0].get("fix")), cell(items[0].get("why")), opinion
    fix = "<br>".join(f"「{cell(p)}」 → {cell(a.get('fix'))}" for p, a in zip(phrases, items))
    why = "<br>".join(f"「{cell(p)}」 {cell(a.get('why'))}" for p, a in zip(phrases, items))
    return fix, why, opinion


def table_head() -> list[str]:
    return ["| " + " | ".join(COLUMNS) + " |", "|" + "---|" * len(COLUMNS)]


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
        body += ["", f"## {path.name}", ""] + table_head()
        for n, items in rows:
            k += 1
            total_lines += 1
            total_asks += len(items)
            fix, why, opinion = row_cells(items)
            phrases = [str(a.get("phrase") or "").strip() for a in items]
            body.append(f"| {k} | {excerpt(lines[n - 1], phrases)} | {fix} | {why} | {opinion} |  |")
            keys[f"Q{k}"] = {"doc": path.resolve().as_posix(), "line": n,
                             "line_key": line_key(lines[n - 1])}
    head = HEAD.format(at=now.strftime("%Y-%m-%d %H:%M"),
                       docs=" · ".join(p.name for p, _, a in docs if a) or "없음",
                       lines=total_lines, asks=total_asks)
    tail = ["", f"<!-- {KEY_MARK}", json.dumps(keys, ensure_ascii=False, indent=0), "-->", ""]
    return head + "\n".join(body + tail)


#: 지적이 이 수 이하면 표 파일을 넘기지 않고 대화 화면에서 묻는다 — 표는 줄 해시를 지키려고
#: 그대로 만든다(2026-10-13 사용자 「10개 이하일 경우에는 그냥 화면에서 보여줘도 될 듯」).
#: 많을 때 파일로 넘기는 까닭은 그대로다 — 61건을 대화로 넘겼다가 하나씩 볼 수 없었다(2026-10-07).
SCREEN_MAX = 10


def screen(docs: list[tuple[Path, list[str], list[tuple[int, dict]]]]) -> str:
    """대화 화면에 그대로 보일 표 — 파일 표와 같은 칸, 같은 번호를 같은 순서로 붙인다.

    대화에서도 표로 묻는다(2026-10-28 사용자가 정한 판정 요청 형식). 세션은 「제 의견」 칸을 채워 보인다.
    """
    out: list[str] = ["**묻는 것**: 원문을 고칠까요?"]
    k = 0
    for path, lines, asks in docs:
        rows = group(lines, asks)
        if not rows:
            continue
        out += ["", f"**{path.name}**", ""] + table_head()
        for n, items in rows:
            k += 1
            fix, why, opinion = row_cells(items)
            phrases = [str(a.get("phrase") or "").strip() for a in items]
            out.append(f"| {k} | {excerpt(lines[n - 1], phrases)} | {fix} | {why} | {opinion} |  |")
    return "\n".join(out)


#: 짧은 답에서 한 행의 답이 시작하는 곳 — 「3 그대로」, 「7 직접: …」. 번호 바로 뒤에 네 답 가운데
#: 하나가 와야 나눈다 — 「직접:」 뒤 글 안의 숫자(「2개 표」)에서 잘리지 않게
ITEM = re.compile(r"(?:^|,\s*|\s+)(Q?\d+)\s*[:.]?\s*(?=고침|그대로|보류|직접)")
#: 「고침 2, 3」처럼 답 하나에 번호를 묶은 줄
GROUPED = re.compile(r"(고침|그대로|보류)\s+((?:Q?\d+[\s,]*)+)$")
#: 답을 안 고른 번호를 알리는 줄 — 읽을 답이 없다
NOT_YET = "아직 안 고름"


def qid_of(token: str) -> str:
    return "Q" + token.lstrip("Qq")


def parse_replies(replies: list[str], opinions: dict[str, str] | None = None) -> dict[str, str]:
    """대화로 받은 답 — 번호별 답 원문. 알아들을 수 없는 줄은 ValueError(줄을 짐작하지 않는다).

    받는 꼴:
    - `Q1 그대로 — 까닭` — 번호 뒤 글 전체가 답(첫 낱말이 넷 가운데 하나가 아닌 글도 받는다)
    - `전부 의견대로` · `의견대로, 단 3 그대로, 7 직접: …` — 「제 의견」 칸을 답으로 쓰고 뒤에 적은 번호만 바꿈
    - `고침 2, 3` — 답 하나에 번호를 묶음
    - `3 그대로, 7 직접: …` — 번호와 답을 잇달아 적음

    의견대로 채운 답에는 「(의견대로)」를 붙인다 — 답 기록에서 사용자가 적은 말과 세션 의견을 가른다.
    ⛔ 「제 의견」 칸이 빈 번호에 의견대로를 쓰면 ValueError — 그 행의 답을 지어 넣지 않는다.
    """
    out: dict[str, str] = {}
    for line in "\n".join(replies).splitlines():
        line = line.strip().strip("「」").strip()
        if not line or line.startswith(NOT_YET):
            continue
        m = re.match(r"(Q\d+)\s*[:.]?\s*(.*)$", line, re.S)
        if m:
            out[m.group(1)] = m.group(2).strip()
            continue
        rest = line
        if rest.startswith(("전부 " + AS_OPINION, AS_OPINION)):
            ops = opinions or {}
            blank = sorted((q for q, op in ops.items() if not op.strip()), key=lambda q: int(q[1:]))
            if blank or not ops:
                raise ValueError(f"「제 의견」 칸이 빈 번호가 있어 의견대로로 답할 수 없음 — "
                                 f"{', '.join(q[1:] for q in blank) or '표에 의견 없음'}")
            out.update({q: f"{op} ({AS_OPINION})" for q, op in ops.items()})
            rest = re.sub(rf"^(전부\s+)?{AS_OPINION}\s*,?\s*(단\s*)?", "", rest)
            if not rest:
                continue
        g = GROUPED.match(rest)
        if g:
            for token in re.findall(r"Q?\d+", g.group(2)):
                out[qid_of(token)] = g.group(1)
            continue
        found = list(ITEM.finditer(rest))
        if not found or rest[:found[0].start()].strip(" ,"):
            raise ValueError(f"알아들을 수 없는 답 — 「{line[:40]}」 · 「3 그대로」나 「Q3 그대로」 꼴로 적습니다")
        for i, it in enumerate(found):
            end = found[i + 1].start() if i + 1 < len(found) else len(rest)
            out[qid_of(it.group(1))] = rest[it.end():end].strip().rstrip(",").strip()
    return out


def _cells(row: str) -> list[str]:
    inner = row.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return [c.strip() for c in re.split(r"(?<!\\)\|", inner)]


def _table(text: str) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """(행별 열쇠, 행별 칸). ⛔ 열쇠 묶음이 없으면 ValueError — 줄을 짐작해 답을 적지 않는다."""
    m = re.search(rf"<!--\s*{KEY_MARK}\s*(.*?)-->", text, re.S)
    if not m:
        raise ValueError("사람 확인 표가 아닙니다 — 맨 아래 열쇠 주석이 없습니다 · "
                         "judge_layer2.py --sheet 로 만든 표를 줍니다")
    keys = json.loads(m.group(1))
    rows: dict[str, list[str]] = {}
    for raw in text[:m.start()].splitlines():
        if not re.match(r"\s*\|\s*Q?\d+\s*\|", raw):
            continue
        cells = _cells(raw)
        if len(cells) not in (len(COLUMNS), LEGACY_WIDTH):
            raise ValueError(f"칸 수가 맞지 않는 행 — {cells[0]} · 칸 안의 `|` 는 `\\|` 로 적습니다")
        rows[qid_of(cells[0])] = [c.replace("\\|", "|").strip() for c in cells]
    return keys, rows


def parse(text: str) -> tuple[dict[str, dict], dict[str, str]]:
    """(행별 열쇠, 행별 답 원문). ⛔ 열쇠 묶음이 없으면 ValueError — 줄을 짐작해 답을 적지 않는다."""
    keys, rows = _table(text)
    answers = {}
    for q, cells in rows.items():
        # 답 칸에 「의견대로」만 적은 행 — 의견 칸이 차 있을 때만 의견을 답으로 쓴다(비었으면 글로 적은 답으로 남음)
        if cells[-1] == AS_OPINION and len(cells) == len(COLUMNS) and cells[-2]:
            answers[q] = f"{cells[-2]} ({AS_OPINION})"
        else:
            answers[q] = cells[-1]
    return keys, answers


def opinions(text: str) -> dict[str, str]:
    """행별 「제 의견」 칸 — 옛 표(의견 칸 없음)는 빈 dict."""
    _, rows = _table(text)
    return {q: cells[-2] for q, cells in rows.items() if len(cells) == len(COLUMNS)}


def kind_of(answer: str) -> str:
    """답 원문을 다섯으로 — 그대로 · 고침(제안대로든 직접이든) · 보류 · 빈칸 · 글로 적은 답."""
    a = answer.strip().strip("`").strip()
    if not a:
        return BLANK
    if a.startswith(KEEP):
        return KEEP
    if a.startswith(HOLD):
        return HOLD
    if a.startswith((EDIT, DIRECT)):
        return EDIT
    return FREE
