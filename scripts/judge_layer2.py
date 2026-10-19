"""2층 판정 — 문서를 판단 규칙 전문과 함께 모델 단발 호출에 넘겨 지적 목록을 받는다(지시 파일은 싣지 않음 · 모델은 이 스크립트가 고름).

**왜 호출로 빼나.** 2층은 세션이 `core-rules.md` 와 9단계를 읽고 직접 본다. 그런데
세션은 긴 대화와 다른 일에 주의를 나눠 쓰고, 그 판정은 어디에도 안 남는다.
점검표(2026-09-29 · `docs/calibration-20260929.md`)에서 판정문만 고쳐도 회수가
32/48 에서 47/48 로 올랐다 — **판정문이 같으면 판정도 같게 돌아야** 그 값이 산다.
그래서 같은 판정을 매번 같은 모양으로 부른다. **세션은 이 목록을 검토한다** —
그대로 반영하지 않는다(헛짚음이 섞인다 · 점검표 「그대로」 줄 2/9).

**프롬프트는 2층 탐침과 같다** — `probe_layer2_kinds.py` 의 `guided` 갈래와 같은
규칙 글·같은 틀을 그 모듈에서 불러 쓴다. 잰 것과 도는 것이 다르면 잰 값이 뜻을
잃는다. 규칙 파일을 고치면 둘이 함께 바뀐다.

**비용 기록** — 호출마다 한 줄을 남긴다: 시각 · 문서 · 내용 해시 · 모델 · 소요 ·
토큰 · SDK 가 낸 금액. 구독(`claude-agent-sdk` OAuth)이라 **청구액이 아니라 API
단가로 환산한 값**이고, 구독 사용량을 얼마나 먹는지 가늠하는 데 쓴다.
기록 위치는 저장소 밖(`~/.claude/state/`)이다 — 문서 경로가 들어가서 공개
저장소에 두면 안 된다. `KOREAN_QA_JUDGE_LOG` 로 바꾼다(시험이 쓴다).

**Codex 만 쓰는 PC 에서도 돈다** — `--backend auto`(기본)는 Claude 를 먼저, 없으면 Codex 를
부른다. Codex 는 모델만 부르는 `codex_http` 로 `sol-high` 를 쓴다. 대장 탐침 · 점검표를 Opus 와
나란히 세 번씩 재서 회수 · 헛짚음이 같은 수준임을 보고 넣었다(2026-10-02 · 점검표 문서).
Codex 쪽은 토큰 수만 남고 금액은 「금액 없음」으로 찍힌다.
**막히면 바로 실패한다**(2026-10-19) — 호출은 사다리 `review`(폴백 없음) 한 칸으로 감싼다(`via_review`).
잰 모델이 아닌 것으로 넘기지 않고, 막힌 엔진(엔진 상태 파일)은 부르지도 않고 「limited」로 올린다.

**새 줄만 판정** — `--since origin/main` 이면 그 가지와 갈라진 뒤 새로 생겼고 판정기가
아직 안 본 줄이 든 묶음만 부르고, 그 줄에 달린 지적만 보여 준다. 호출마다 본 줄의
해시를 기록에 남기므로(`layer2_coverage.py`) 고친 줄만 다시 판정된다. 발행 게이트가
push 직전에 같은 기록으로 「새 줄을 다 봤나」를 가른다.
고친 줄은 기준 판(갈라진 지점의 원래 줄)과 근처에서 지운 줄을 함께 보내 뜻이 바뀌었는지
대조하게 하고, 같은 줄은 `REJUDGE_CAP` 번까지만 자동 수정 대상으로 둔다 — 넘으면 사람
확인으로 올린다(`lineage` · 2026-10-12 고리 재현 시험).

**사람 확인** (2026-10-06 사용자 결정) — 판정기는 지적마다 `decide` 를 낸다. 분명하면
`fix`, 문맥에 따라 정상일 수 있거나 규칙에 기준이 없거나 고치면 뜻이 바뀔 수 있으면
`ask` 다. `ask` 는 **세션이 정하지 않고 사용자에게 묻는다.** 판정 기록에 줄 해시와 함께
남고, 사용자가 답하면 `--answer` 로 그 줄에 답을 적는다. 답을 못 받은 지적이 남은
문서는 발행 직전 검사가 막는다(`hooks/doc-style-gate.py`).

**사용자 답을 따른다** (2026-10-07 사용자 — 「내 기본 답변을 기반으로 판단했으면 좋겠는데,
현재 AI가 애스컬레이션한 항목이 너무 많다」) — 처음 사이트 다섯 쪽에서 61건을 넘겼는데
사용자는 52건을 판정기 제안대로 고치라고 답했다. 그래서 표에서 읽은 답을 모두
`layer2_coverage.DECISIONS` 에 남기고 다음 판정이 프롬프트 끝의 「사용자가 이미 답한 것」(갈래별
답 수 · 그대로 둔 것과 글로 적은 답 원문)으로 읽는다.
⛔ **갈래별 고침 횟수로 사람 확인을 고칠 지적으로 바꾸던 코드는 뺐다**(2026-10-12) — 바뀐 5건이
모두 문서만으로는 맞는지 갈리지 않는 사실(지원 버전 · 측정 문서 수 · 훅 실행 시점 · 담당자)이었다.
사용자의 고침 답은 낱말을 고친 것이라 사실 확인의 근거가 못 되고, 고칠 지적은 그때 발행을 안
막아 그 질문이 사용자에게 안 갔다(고리 재현 시험 · 외부 검토 「학습한 대상과 적용 대상이 다름」).

    python -X utf8 scripts/judge_layer2.py <문서…> [--since REF] [--backend auto|claude|codex]
                                           [--model 별칭] [--json 경로]
    python -X utf8 scripts/judge_layer2.py <문서…> --sheet <저장소 밖 경로>.md
    python -X utf8 scripts/judge_layer2.py --answers-from <그 표>
    python -X utf8 scripts/judge_layer2.py <문서> --answer <행> [--answer <행>…] --note "사용자가 정한 것"
    python -X utf8 scripts/judge_layer2.py <문서…> --asks
    python -X utf8 scripts/judge_layer2.py <문서…> --fixes
    python -X utf8 scripts/judge_layer2.py <문서> --dismiss <행> --reason <사유> --note "근거" [--phrase 표현]
    python -X utf8 scripts/judge_layer2.py <문서> --escalate <행> --note "까닭" [--phrase 표현]
    python -X utf8 scripts/judge_layer2.py --cost [--by day|month|doc]

**고칠 지적도 처리해야 발행된다** (2026-10-12) — 고치거나 · 지적마다 사유 코드와 근거를 적어
받지 않거나(`--dismiss`) · 세션이 정할 수 없으면 사람 확인으로 올린다(`--escalate`). 근거에 「확인
필요」가 걸린 지적(`[사실 확인]`)은 자료를 적은 「확인함」이나 사람 확인으로만 닫힌다. 규칙과 까닭은
`layer2_coverage.py` 머리말.

**사용자에게 넘기는 형식은 표 한 장** (2026-10-07 사용자) — `--sheet` 가 md 표를 쓰고 사용자가
「답」 칸을 채우면 `--answers-from` 이 읽는다. 형식과 답 처리는 `ask_sheet.py` 에 있다.

종료 코드 — 0 돌았음(지적은 사람이 본다) · 1 `--asks` · `--sheet` · `--answers-from` 에서 답을 기다리는 지적이 남음 ·
2 사용법 · 표를 못 읽음 · 3 호출 백엔드 없음(세션이 규칙을 직접 읽는다) · 4 호출 실패
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ask_sheet  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
import probe_layer2_kinds as probe  # noqa: E402

LOG = coverage.LOG
read_doc = coverage.read_doc
#: 한 번에 넘기는 줄 수 — 탐침에서 문서가 길어지면 회수가 흔들렸다(17 → 29건).
#: 넘으면 제목 경계에서 나눈다.
CHUNK_LINES = 180
DEFAULT_MODEL = "opus"      # 점검표에서 Sonnet 은 일상 동사 묶음 4/7 · Opus 6/7
#: Codex 쪽 기본 — 2026-10-02 대장 탐침 · 점검표를 Opus 와 나란히 잰 값(`docs/calibration-20260929.md`)
#: astra-high 와 회수 · 헛짚음이 같고 5시간 한도는 4분의 1(탐침 1회 1~2% · astra 6~7%)
CODEX_MODEL = "sol-high"
#: Claude Code 프롬프트 캐시 유지 시간 — 구독 로그인 기본은 1시간(쓰기 단가가 입력의 2배)이고 5분은 1.25배다.
#: 판정 호출의 93% 가 앞 호출 5분 안에 이어져, 실사용 기록 796회에 단가만 바꾸면 환산 비용이 20% 준다
#: (2026-10-15 · 판정 결과와 무관 · 사용자 결정 「적용」). 환경 변수를 이미 정했으면 그 값을 따른다.
CACHE_TTL_ENV, CACHE_TTL = "CLAUDE_CODE_PROMPT_CACHE_TTL", "5m"


def chunks(lines: list[str], limit: int = CHUNK_LINES) -> list[tuple[int, list[str]]]:
    """(시작 줄 번호, 줄들) 묶음. 넘치면 가장 가까운 앞 제목에서 자른다."""
    out, start = [], 0
    while start < len(lines):
        end = min(start + limit, len(lines))
        if end < len(lines):
            cut = next((i for i in range(end - 1, start + limit // 2, -1)
                        if lines[i].lstrip().startswith("#")), end)
            end = cut
        out.append((start + 1, lines[start:end]))
        start = end
    return out


def numbered(lines: list[str], first: int) -> str:
    """탐침의 `numbered` 와 같은 모양 — 첫 묶음이면 글자까지 같다."""
    return "\n".join(f"{n:>3} | {l}" for n, l in enumerate(lines, first))


#: 재판정 문맥 — chunk = 대상이 든 180줄 묶음 전부(기본) · fixed = 대상 앞뒤 고정 줄 · block = 대상의 구조 단위와
#: 제목 사슬, 앞뒤 블록. 재판정 비용의 대부분이 호출마다 새로 쓰는 문서 묶음이라(180줄 묶음 중앙값 약 8,700토큰
#: · 2026-10-15) 문맥을 줄이는 실험을 옵션으로 둔다. 기본값은 같은 입력 재생으로 지적 차이를 본 뒤에 바꾼다
#: (외부 검토 — 구조를 자르지 말고 못 담으면 chunk 로 복귀 · HTML 은 chunk · 판단 불가를 따로 받음).
CONTEXT_MODES = ("chunk", "fixed", "block")
FIXED_LINES = 20
#: block 에서 대상의 구조 단위와 제목 사슬이 이보다 길면 자르지 않고 chunk 로 복귀한다
BLOCK_BUDGET = 120
#: 판정기가 생략된 곳 때문에 판단하지 못한 줄에 다는 갈래 — 그 줄은 chunk 로 다시 판정한다
CONTEXT_SHORT = "문맥 부족"
WINDOWABLE = (".md", ".markdown")
WINDOW_NOTE = ("\n\n이번에는 문서의 일부만 보낸다. 줄 번호는 원래 문서의 번호이고 「…(N줄 생략)…」 자리에는 보내지 "
               "않은 줄이 있다. 대상 줄을 판단하는 데 필요한 내용(용어 정의 · 선행사 · 앞서 나온 수치 · 표나 목록의 "
               f"머리)이 생략된 곳에 있어 판단할 수 없으면 그 줄에 갈래 「{CONTEXT_SHORT}」로 지적을 하나만 내고 다른 "
               "지적은 내지 않는다. 생략된 곳에 없을 것이라 짐작해 「선행사 없음」 같은 지적을 내지 않는다.")


def blocks(lines: list[str]) -> list[tuple[int, int]]:
    """빈 줄로 나뉜 블록 — (첫 줄, 끝 줄) 1부터. 코드 울타리 안은 빈 줄이 있어도 한 블록이다."""
    out, start, fence = [], None, False
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        if not line.strip() and not fence:
            if start is not None:
                out.append((start, n - 1))
                start = None
        elif start is None:
            start = n
    if start is not None:
        out.append((start, len(lines)))
    return out


def heading_chain(lines: list[str], n: int) -> list[int]:
    """n행 위의 제목 사슬 — 가까운 제목부터 더 높은 수준의 제목을 거슬러 올라간다."""
    out, level = [], 7
    for i in range(n - 1, 0, -1):
        m = re.match(r"(#{1,6})\s", lines[i - 1])
        if m and len(m.group(1)) < level:
            out.append(i)
            level = len(m.group(1))
            if level == 1:
                break
    return out


LIST_ITEM = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def list_unit(lines: list[str], a: int, b: int, n: int) -> set[int]:
    """긴 목록에서 n행의 구조 단위 — 그 항목과 하위 줄, 상위 항목 사슬, 목록 도입문(첫 줄이 항목이 아니면)."""
    start = n
    while start > a and not LIST_ITEM.match(lines[start - 1]):
        start -= 1
    ind = _indent(lines[start - 1])
    end = start
    while end < b and not (LIST_ITEM.match(lines[end]) and _indent(lines[end]) <= ind):
        end += 1
    keep = set(range(start, end + 1))
    cur = ind
    for i in range(start - 1, a - 1, -1):
        if LIST_ITEM.match(lines[i - 1]) and _indent(lines[i - 1]) < cur:
            keep.add(i)
            cur = _indent(lines[i - 1])
    if not LIST_ITEM.match(lines[a - 1]):
        keep.add(a)
    return keep


def table_unit(lines: list[str], a: int, b: int, n: int) -> set[int]:
    """긴 표에서 n행의 구조 단위 — 머리 두 줄과 그 행 앞뒤 두 행."""
    return set(range(a, min(b, a + 1) + 1)) | set(range(max(a, n - 2), min(b, n + 2) + 1))


def window_lines(lines: list[str], n: int, mode: str) -> set[int] | None:
    """n행을 판정할 때 보낼 줄 — 구조 단위를 담지 못하면 None(chunk 로 복귀)."""
    heads = set(heading_chain(lines, n))
    if mode == "fixed":
        return set(range(max(1, n - FIXED_LINES), min(len(lines), n + FIXED_LINES) + 1)) | heads
    bl = blocks(lines)
    i = next((k for k, (a, b) in enumerate(bl) if a <= n <= b), None)
    if i is None:                       # 빈 줄 자체 — 앞뒤 블록으로
        return set(range(max(1, n - 1), min(len(lines), n + 1) + 1)) | heads
    a, b = bl[i]
    keep = set(range(a, b + 1)) | heads
    if len(keep) > BLOCK_BUDGET:
        # 블록이 길면 구조 단위로 — 목록은 항목 · 상위 항목 · 도입문, 표는 머리와 이웃 행. 그 밖(긴 문단 ·
        # 코드)은 자르지 않고 chunk 로 돌아간다(외부 검토 「구조를 자르지 말 것」)
        body = lines[a - 1:b]
        if sum(1 for l in body if LIST_ITEM.match(l)) * 2 >= len(body):
            keep = list_unit(lines, a, b, n) | heads
        elif all(l.lstrip().startswith("|") for l in body):
            keep = table_unit(lines, a, b, n) | heads
        else:
            return None
        if len(keep) > BLOCK_BUDGET:
            return None
    for j in (i - 1, i + 1):            # 앞뒤 블록은 예산이 남을 때만
        if 0 <= j < len(bl):
            extra = set(range(bl[j][0], bl[j][1] + 1))
            if len(keep | extra) <= BLOCK_BUDGET:
                keep |= extra
    return keep


def excerpt(lines: list[str], keep: list[int]) -> str:
    """원래 줄 번호를 붙인 발췌 — 빠진 구간은 「…(N줄 생략)…」 한 줄."""
    out, prev = [], 0
    for n in keep:
        if n > prev + 1:
            out.append(f"…({n - prev - 1}줄 생략)…")
        out.append(f"{n:>3} | {lines[n - 1]}")
        prev = n
    if prev < len(lines):
        out.append(f"…({len(lines) - prev}줄 생략)…")
    return "\n".join(out)


def parts_for(lines: list[str], want: set[int] | None, mode: str, path: Path) -> list[dict]:
    """이번에 부를 조각 — {"mine": 대상 줄, "document": 프롬프트에 넣을 글, "seen": 판정기가 본 줄, "label", "mode"}."""
    def by_chunk(used: str) -> list[dict]:
        out = []
        for first, part in chunks(lines):
            mine = sorted(n for n in (want or ()) if first <= n < first + len(part))
            if want is not None and not mine:
                continue
            out.append({"mine": mine, "document": numbered(part, first), "seen": part,
                        "label": f"{first}-{first + len(part) - 1}", "mode": used})
        return out
    if want is None or mode == "chunk":
        return by_chunk("chunk")
    if path.suffix.lower() not in WINDOWABLE:
        return by_chunk(f"chunk←{mode}")
    keep: set[int] = set()
    for n in sorted(want):
        got = window_lines(lines, n, mode)
        if got is None:
            return by_chunk(f"chunk←{mode}")
        keep |= got
    if len(keep) > CHUNK_LINES:
        return by_chunk(f"chunk←{mode}")
    ordered = sorted(keep)
    runs, start = [], ordered[0]
    for a, b in zip(ordered, ordered[1:] + [None]):
        if b != a + 1:
            runs.append(f"{start}-{a}")
            start = b
    return [{"mine": sorted(want), "document": excerpt(lines, ordered), "seen": [lines[n - 1] for n in ordered],
             "label": ",".join(runs), "mode": mode}]


def relocate(lines: list[str], hint, phrase: str) -> int | None:
    """모델이 낸 줄 번호를 믿지 않고 **표현이 실제로 있는 줄**을 찾는다."""
    phrase = (phrase or "").strip()
    try:
        hint = int(hint)
    except (TypeError, ValueError):
        hint = None
    if not phrase:
        return hint
    hits = [i + 1 for i, l in enumerate(lines) if phrase in l]
    if not hits:
        return hint
    return min(hits, key=lambda n: abs(n - hint)) if hint else hits[0]


def is_ask(item: dict) -> bool:
    """판정기가 사람에게 넘긴 지적인가 — `decide: ask`."""
    return str(item.get("decide") or "").strip().lower() == "ask"


def answer(path: Path, line_nos: list[int], note: str) -> list[str]:
    """사용자가 사람 확인 지적에 답했다고 줄마다 적는다 — 적은 줄의 앞머리 목록.

    ⛔ **세션이 대신 답하지 않는다** — 이 기록은 사용자가 정한 것을 옮겨 적는 곳이다.
       까닭(`note`)에는 사용자가 무엇을 골랐는지를 적는다. 까닭이 없으면 받지 않는다 —
       판정 기록(`check_record.py`)의 검토 단계와 같은 이유다.
    """
    if not note.strip():
        raise ValueError("답 기록에는 --note 로 사용자가 정한 것을 적어야 합니다")
    lines = read_doc(path).splitlines()
    key = coverage.doc_key(path)
    # ⛔ 물은 줄에만 받는다 — 미리 적어 둔 답이 나중에 그 줄에 생길 지적을 묻기 전에 닫는다
    pending = coverage.open_asks(key, lines, LOG)
    waiting = {n for n, _ in pending}
    rows = []
    for n in line_nos:
        if not 0 < n <= len(lines) or not coverage.line_key(lines[n - 1]):
            raise ValueError(f"{n}행은 한글이 든 줄이 아닙니다 — 판정 결과의 줄 번호를 적습니다")
        # 「직접」 답대로 고친 줄 — 물은 줄은 사라졌고 이 줄이 그 줄을 이어 받았다. 확정하면 다시 판정하지 않는다
        origin = answered_origin(key, lines, n)
        if n not in waiting and origin is None:
            raise ValueError(f"{n}행에는 답을 기다리는 사람 확인 지적이 없습니다 — "
                             "--asks 로 줄 번호를 확인합니다")
        row = {"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(),
               "doc": str(path), "key": key, "line": n,
               "line_key": coverage.line_key(lines[n - 1]), "note": note.strip(),
               # 이 답이 닫은 지적 — 앞 판에서 물어 이 줄로 따라온 지적은 줄 해시로는 못 잇는다
               "asks": [[a.get("line_key"), a.get("phrase")] for m, a in pending if m == n]}
        if origin is not None:
            row.update(approved=True, origin=origin, text=lines[n - 1])
        rows.append(row)
    coverage.ANSWERS.parent.mkdir(parents=True, exist_ok=True)
    with coverage.ANSWERS.open("a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return [lines[r["line"] - 1].strip()[:40] for r in rows]


def answered_origin(key: str, lines: list[str], n: int) -> str | None:
    """n행이 사용자가 고침 · 직접으로 답한 물은 줄을 이어 받은 줄이면 그 물은 줄의 해시 · 아니면 None.

    물은 줄이 그대로 남아 있으면 아직 안 고친 것이다. 이어 받았는지는 글자로 가른다(재판정 계보와 같은 기준).
    """
    now = {k for k in map(coverage.line_key, lines) if k}
    for d in reversed(load_decisions()):
        if not coverage.key_matches(d.get("key"), key) or d.get("kind") not in (ask_sheet.EDIT, ask_sheet.FREE):
            continue
        if d.get("line_key") in now or not d.get("text"):
            continue
        if coverage._similar(lines[n - 1], d["text"]) >= coverage.SUCCESSOR:
            return d["line_key"]
    return None


def edited_by_answer(line: str, asks: list[dict]) -> str | None:
    """「고침」 답 — 물은 줄에 판정기 수정안을 그대로 넣은 글. 글자로 넣을 수 없는 수정안이 있으면 None."""
    out = line
    for a in asks:
        if a.get("category") == "재판정 상한":
            continue                # 줄 전체를 짚은 것 — 같은 줄의 다른 지적에 대한 답이 곧 이 줄의 답이다
        phrase, fix = str(a.get("phrase") or ""), str(a.get("fix") or "")
        if not phrase or not fix or fix.startswith("(") or "\n" in fix or "○○" in fix or phrase not in out:
            return None
        out = out.replace(phrase, fix, 1)
    return out if out != line else None


def approve(path: Path, text: str, note: str, origin: str) -> None:
    """사용자가 답한 대로 고친 글을 사람이 판정한 줄로 적는다 — 그 글로 고치면 판정기가 다시 보지 않는다."""
    row = {"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(), "doc": str(path),
           "key": coverage.doc_key(path), "line_key": coverage.line_key(text), "text": text,
           "origin": origin, "note": note, "approved": True}
    coverage.ANSWERS.parent.mkdir(parents=True, exist_ok=True)
    with coverage.ANSWERS.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


#: 프롬프트에 원문 그대로 싣는 답의 수 — 그대로 둔 것과 글로 적은 답만, 최근 것부터
PROMPT_ANSWERS = 40


def asks_on(path: Path, line_key: str) -> list[dict]:
    """판정 기록에서 그 줄(줄 해시)에 넘긴 사람 확인 지적 — 표현이 겹치면 한 번."""
    out, seen = [], set()
    for ask in coverage.ask_rows(coverage.doc_key(path), LOG):
        if ask.get("line_key") == line_key and ask.get("phrase") not in seen:
            seen.add(ask.get("phrase"))
            out.append(ask)
    return out


def record_decision(path: Path, line_key: str, raw: str, kind: str, source: str,
                    text: str | None = None) -> int:
    """사용자가 표에 적은 답을 그 줄의 지적마다 남긴다 — 남긴 수. 같은 답을 두 번 적지 않는다.

    ⛔ 지적을 닫지 않는다 — 닫는 것은 `answer`(그대로만)다. 이것은 다음 판정이 따를 기록이다.
    `text` 는 사용자가 본 줄 — 그 줄을 고친 뒤의 판정에 이 답을 싣고(`decided_on`), 답대로 고친 줄을
    확정할 때(`answered_origin`) 글자로 잇는다.
    """
    have = set()
    if coverage.DECISIONS.is_file():
        for line in coverage.DECISIONS.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            have.add((d.get("line_key"), d.get("phrase"), d.get("answer")))
    rows = []
    for ask in asks_on(path, line_key):
        if (line_key, ask.get("phrase"), raw) in have:
            continue
        rows.append({"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(),
                     "key": coverage.doc_key(path), "line_key": line_key, "source": source,
                     "category": str(ask.get("category") or "").strip(), "phrase": ask.get("phrase"),
                     "fix": ask.get("fix"), "answer": raw, "kind": kind,
                     **({"text": text} if text else {})})
    if rows:
        coverage.DECISIONS.parent.mkdir(parents=True, exist_ok=True)
        with coverage.DECISIONS.open("a", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def load_decisions() -> list[dict]:
    if not coverage.DECISIONS.is_file():
        return []
    out = []
    for line in coverage.DECISIONS.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def category_stats(decisions: list[dict]) -> dict[str, dict[str, int]]:
    """갈래 → {답 종류: 수}."""
    stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d in decisions:
        stats[d.get("category") or ""][d.get("kind") or ""] += 1
    return stats


def decisions_prompt(decisions: list[dict]) -> str:
    """판정기 프롬프트 끝에 붙이는 「사용자가 이미 답한 것」 — 답이 없으면 빈 글."""
    if not decisions:
        return ""
    stats = category_stats(decisions)
    out = ["", "## 사용자가 이미 답한 것", "",
           "사람 확인으로 넘긴 지적에 사용자가 답한 기록이다. 같은 갈래 · 같은 경우는 다시 묻지 않고 "
           "이 답을 따른다. 고침이 많은 갈래는 \"fix\" 로 내고, 그대로 둔 경우와 같은 문맥이면 지적하지 않는다. "
           "단 고침 답은 표현을 고친 것이다 — 문서만으로 맞는지 갈리지 않는 사실은 갈래가 같아도 이 답을 근거로 삼지 않는다.",
           "", "갈래별 답"]
    for cat, c in sorted(stats.items(), key=lambda x: -sum(x[1].values())):
        parts = [f"{k} {n}" for k, n in sorted(c.items(), key=lambda x: -x[1]) if k]
        out.append(f"- {cat or '(갈래 없음)'} — {' · '.join(parts)}")
    shown = [d for d in decisions if d.get("kind") in (ask_sheet.KEEP, ask_sheet.FREE)][-PROMPT_ANSWERS:]
    if shown:
        out += ["", "그대로 둔 것과 사용자가 글로 적은 답 — 원문 그대로"]
        for d in shown:
            out.append(f"- [{d.get('category')}] 「{d.get('phrase')}」 · 판정기 제안 「{d.get('fix')}」 "
                       f"· 사용자: {d.get('answer')}")
    return "\n".join(out)


def show_open_asks(path: Path) -> int:
    """아직 답을 못 받은 사람 확인 지적을 보이고 그 수를 낸다."""
    lines = read_doc(path).splitlines()
    left = coverage.open_asks(coverage.doc_key(path), lines, LOG)
    if not left:
        print(f"  {path.name} — 답을 기다리는 사람 확인 지적 없음")
        return 0
    print(f"  {path.name} — 사용자 답을 기다리는 지적 {len(left)}건")
    for n, ask in left:
        print(f"  {n:>4}행  「{ask.get('phrase')}」 → {ask.get('fix')}")
        if ask.get("why"):
            print(f"         {ask['why']}")
    return len(left)


#: 고칠 지적을 받지 않는 사유 — 이 밖의 까닭(번거로움 · 상한에 닿음 · 예전에도 허용 · 아마 맞음)
#: 으로는 닫지 않는다(외부 검토 · 2026-10-12). 값은 근거 칸에 적어야 할 것이다.
REASONS = {
    "대상아님": "규칙의 적용 대상이 아님 — 규칙의 적용 조건과 이 문맥이 어떻게 다른지",
    "오독": "판정기가 원문을 잘못 읽음 — 반증하는 문장이나 자료",
    "충족": "문서 안에서 이미 충족함 — 충족하는 줄(「N행」)",
    "규칙충돌": "다른 규칙을 우선함 — 우선하는 규칙과 그 근거",
    "확인함": "사실을 자료로 확인함 — 자료 경로 · 명령 · 버전",
    "지시반영": "사용자 · 검토자 지시로 일부러 바꾼 뜻 — 지시 원문 인용(「…」)과 누가 · 언제",
}
#: 「지시반영」으로만 닫을 수 있는 갈래 — 지시는 편집 의도의 근거이지 사실의 근거가 아니다(외부 검토
#: 2026-10-13). 실사용 문서 1건에서 「고치다 뜻이 바뀐 곳」 닫기 46건 중 40건이 지시 근거였는데
#: 모두 「확인함」으로 닫혀, 감사할 때 사실 확인과 갈리지 않았다.
INTENT_ONLY = "뜻이 바뀐"
QUOTE = re.compile(r"「[^」]{4,}」")
#: 근거에 자료가 적혔나 — 경로 · 명령 · 주소 · 줄 번호 가운데 하나
EVIDENCE = re.compile(r"[/\\]|`[^`]+`|https?://|\b[\w-]+\.(?:py|md|html|json|toml|txt|js|ts|yml|yaml)\b|\d+\s?행")
LINE_REF = re.compile(r"\d+\s?행")
NOTE_MIN = 10
#: 근거에 적은 파일 경로 — 확장자가 붙은 것만 본다(폴더 · 확장자 없는 이름은 짐작하지 않는다)
PATH_REF = re.compile(r"(?<![\w.])(?:~|[A-Za-z]:)?[\w./\\~-]*[\w-]\.(?:py|md|html|jsonl?|toml|txt|js|ts|ya?ml)\b")
#: 경로 바로 뒤의 「인용」 — 그 파일에서 옮겼다는 뜻으로 읽고 글자를 대조한다
QUOTE_AFTER = re.compile(r"\s*(?:의|에서|:)?\s*「([^」]{4,})」")


def _resolve(ref: str, doc: Path) -> Path | None:
    """근거에 적은 경로를 이 PC 의 파일로 — 절대 · `~` · 문서 저장소 뿌리 · 문서 폴더 · 저장소 안 같은 이름."""
    raw = Path(os.path.expanduser(ref.replace("\\", "/")))
    found = coverage.repo_of(doc)
    tries = [raw] if raw.is_absolute() else [*(([found[0] / raw]) if found else []), doc.parent / raw]
    for t in tries:
        if t.is_file():
            return t
    if found and "/" not in ref.replace("\\", "/"):
        got = coverage._git(found[0], "ls-files", "--", f"*/{ref}", ref)
        hits = got.stdout.decode("utf-8", "replace").split()
        if len(hits) == 1:
            return found[0] / hits[0]
    return None


def evidence_problems(doc: Path, note: str, lines: list[str]) -> list[str]:
    """근거를 기계로 대조한다 — 없는 파일 · 그 파일에 없는 인용 · 문서 밖 줄 번호.

    ⛔ 근거의 모양(경로 · 「N행」)만 보면 지어낸 근거도 받는다(외부 검토 「근거의 형식과 타당성은
       다르다」 · 2026-10-13). 이것은 존재만 본다 — 그 근거가 주장을 뒷받침하는지는 못 본다.
    ⛔ 경로 뒤에 붙지 않은 인용(대화로 받은 지시 등)은 대조하지 않는다 — 대조할 파일이 없다.
    """
    out, files = [], []          # files — (경로가 끝나는 곳, 파일 이름, 줄 수)
    norm = lambda t: re.sub(r"\s+", " ", t).strip()
    for m in PATH_REF.finditer(note):
        target = _resolve(m.group(0), doc)
        if target is None:
            out.append(f"근거의 파일이 없습니다 — {m.group(0)} · 이 PC 의 경로(절대 경로나 저장소 기준)로 적습니다")
            continue
        try:
            raw = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        files.append((m.end(), target.name, len(raw.splitlines())))
        q = QUOTE_AFTER.match(note, m.end())
        if q:
            body = norm(raw)
            parts = [norm(x) for x in q.group(1).split("…") if len(norm(x)) >= 4]
            if not all(x in body for x in parts):
                out.append(f"인용 「{q.group(1)[:30]}」 이 {target.name} 에 글자 그대로 없습니다 — 원문을 옮겨 적습니다")
    # 「N행」이 가리키는 곳 — 「문서 N행」이면 이 문서, 아니면 앞에 나온 마지막 경로의 파일, 경로가 없으면 이 문서.
    # ⛔ 전에는 경로 바로 뒤만 그 파일 줄로 봐서, 「<경로> 「인용」 — 원문 965행 6.2 절 안」을 이 문서(363행)의
    #    없는 줄로 거절했다(2026-10-14 lab-docs). 귀속만 바로잡고 줄이 있는지는 계속 대조한다.
    for m in re.finditer(r"(\d+)\s?행", note):
        n = int(m.group(1))
        before = [f for f in files if f[0] <= m.start()]
        if "문서" in note[max(0, m.start() - 6):m.start()] or not before:
            if not 0 < n <= len(lines):
                out.append(f"「{m.group(0)}」 은 이 문서({len(lines)}행)에 없는 줄입니다")
        elif not 0 < n <= before[-1][2]:
            out.append(f"「{m.group(0)}」 은 {before[-1][1]}({before[-1][2]}행)에 없는 줄입니다")
    return out


def show_open_fixes(path: Path) -> int:
    """아직 처리 안 된 고칠 지적을 보이고 그 수를 낸다."""
    lines = read_doc(path).splitlines()
    left = coverage.open_fixes(coverage.doc_key(path), lines, LOG)
    if not left:
        print(f"  {path.name} — 처리 안 된 고칠 지적 없음")
        return 0
    print(f"  {path.name} — 처리 안 된 고칠 지적 {len(left)}건")
    for n, fx in left:
        tag = " [사실 확인]" if coverage.needs_check(fx) else ""
        print(f"  {n:>4}행{tag}  「{fx.get('phrase')}」 — {fx.get('category')} → {fx.get('fix')}")
        if fx.get("check"):
            print(f"         확인할 사실: {fx['check']}")
        if fx.get("why"):
            print(f"         {fx['why']}")
    return len(left)


def _pick_fix(path: Path, n: int, phrase: str | None) -> tuple[list[str], dict]:
    """그 줄의 열린 고칠 지적 하나 — 둘 이상이면 표현으로 고른다. 못 고르면 ValueError."""
    lines = read_doc(path).splitlines()
    mine = [fx for m, fx in coverage.open_fixes(coverage.doc_key(path), lines, LOG) if m == n]
    if not mine:
        raise ValueError(f"{n}행에는 처리 안 된 고칠 지적이 없습니다 — --fixes 로 줄 번호를 확인합니다")
    if phrase:
        exact = [fx for fx in mine if str(fx.get("phrase") or "") == phrase]
        # 표현 일부만 적어도 하나로 정해지면 받는다 — 링크 주소까지 든 긴 표현을 통째로 옮기게 하던 불편(2026-10-14)
        part = [fx for fx in mine if phrase in str(fx.get("phrase") or "")]
        mine = exact or (part if len(part) == 1 else [])
        if not mine:
            many = " · ".join(f"「{fx.get('phrase')}」" for fx in part)
            raise ValueError(f"{n}행에 「{phrase}」 지적이 없습니다 — --fixes 의 표현을 적습니다"
                             + (f"(일부가 맞는 지적이 여럿: {many})" if many else ""))
    if len(mine) > 1:
        raise ValueError(f"{n}행에 고칠 지적이 {len(mine)}건입니다 — --phrase 로 하나를 고릅니다: "
                         + " · ".join(f"「{fx.get('phrase')}」" for fx in mine))
    return lines, mine[0]


def _close_fix(path: Path, lines: list[str], n: int, fx: dict, extra: dict) -> None:
    row = {"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(),
           "doc": str(path), "key": coverage.doc_key(path), "line": n, "text": lines[n - 1],
           "line_key": coverage.line_key(lines[n - 1]), "phrase": fx.get("phrase"),
           "fix": fx.get("fix"), "why": fx.get("why"), "category": fx.get("category"),
           "check": fx.get("check") or ""}
    row.update(extra)
    coverage.DISMISSALS.parent.mkdir(parents=True, exist_ok=True)
    with coverage.DISMISSALS.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def dismiss(path: Path, n: int, reason: str, note: str, phrase: str | None = None) -> str:
    """고칠 지적 하나를 받지 않기로 적는다 — 닫은 지적의 표현. 규칙에 안 맞으면 ValueError.

    ⛔ 지적 하나에만 듣는다 — 갈래 전체나 앞으로 올 지적을 닫지 않는다. 그 줄이 바뀌면 다시 열린다.
    ⛔ 사실 확인이 걸린 지적은 「확인함」(자료를 적음)이나 사람 확인으로 올리는 것만 받는다 —
       「아마 맞음」으로 닫으면 확인 안 된 사실이 나간다.
    """
    if reason not in REASONS:
        raise ValueError("사유는 다음 가운데 하나입니다 — "
                         + " · ".join(f"{k}({v})" for k, v in REASONS.items()))
    note = note.strip()
    if len(note) < NOTE_MIN:
        raise ValueError(f"--note 에 근거를 적습니다 — {REASONS[reason]}")
    lines, fx = _pick_fix(path, n, phrase)
    intent = INTENT_ONLY in str(fx.get("category") or "")
    if reason == "지시반영":
        if not intent:
            raise ValueError("「지시반영」은 「고치다 뜻이 바뀐 곳」 지적에만 씁니다 — 지시는 편집 의도의 근거이지 "
                             "사실의 근거가 아닙니다")
        if not QUOTE.search(note):
            raise ValueError("「지시반영」은 근거에 지시 원문을 「」로 옮겨 적어야 받습니다(누가 · 언제와 함께)")
    elif coverage.needs_check(fx) and reason != "확인함":
        raise ValueError("사실 확인이 걸린 지적입니다 — 자료로 확인해 「확인함」으로 닫거나(근거에 자료 경로 · "
                         "명령), 일부러 바꾼 뜻이면 「지시반영」, 세션이 확인할 수 없으면 --escalate 로 "
                         "사람 확인에 올립니다")
    if reason == "확인함" and not EVIDENCE.search(note):
        raise ValueError("「확인함」은 근거에 확인한 자료(경로 · 명령 · 주소)를 적어야 받습니다")
    if reason == "충족" and not LINE_REF.search(note):
        raise ValueError("「충족」은 근거에 충족하는 줄(「N행」)을 적어야 받습니다")
    problems = evidence_problems(path, note, lines)
    if problems:
        raise ValueError(" · ".join(problems))
    _close_fix(path, lines, n, fx, {"reason": reason, "note": note})
    return str(fx.get("phrase"))


def escalate(path: Path, n: int, note: str, phrase: str | None = None) -> str:
    """고칠 지적 하나를 사람 확인으로 올린다 — 사용자 답이 있어야 발행된다(세션이 정할 수 없을 때)."""
    note = note.strip()
    if len(note) < NOTE_MIN:
        raise ValueError("--note 에 세션이 정할 수 없는 까닭을 적습니다(무엇을 누가 확인해야 하는지)")
    lines, fx = _pick_fix(path, n, phrase)
    why = "; ".join(x for x in (str(fx.get("why") or ""), f"세션이 올림: {note}") if x)
    _close_fix(path, lines, n, fx, {"reason": "사람확인", "escalate": True, "note": note, "why": why})
    return str(fx.get("phrase"))


def write_sheet(paths: list[Path], out: Path) -> tuple[int, int, str]:
    """열린 사람 확인을 md 표 한 장으로 쓴다 — (줄 수, 지적 수, 화면 목록). 형식은 `ask_sheet.py`.

    화면 목록은 표와 같은 번호를 쓴다 — 지적이 적으면 그것을 대화로 보이고 답을 `--reply` 로 받는다.
    """
    docs = []
    for p in paths:
        lines = read_doc(p).splitlines()
        docs.append((p, lines, coverage.open_asks(coverage.doc_key(p), lines, LOG)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ask_sheet.render(docs, coverage.line_key), encoding="utf-8", newline="\n")
    asks = sum(len(a) for _, _, a in docs)
    rows = sum(len({n for n, _ in a}) for _, _, a in docs)
    return rows, asks, ask_sheet.screen(docs)


def read_answers(sheet: Path, replies: list[str] | None = None) -> int:
    """사용자가 표에 적은 답을 읽는다 — `그대로`는 답 기록에 남기고, 고칠 것은 목록으로 돌려준다.

    `replies` 는 대화로 받은 답(`Q1 그대로`) — 표의 답 칸 대신 쓰고, 줄 해시 대조는 표의 것을 그대로
    쓴다. ⛔ 세션은 사용자가 한 말을 옮겨 적기만 한다 — 묻지 않은 행에 답을 지어 넣지 않는다.

    ⛔ `고침`·`직접`은 답으로 적지 않는다 — 적으면 고치기 전에 지적이 닫혀 고치지 않은 글이
       발행·배포를 통과한다. 고치면 짚은 표현이 사라져 지적이 저절로 닫힌다.
    ⛔ 표를 만든 뒤 바뀐 줄의 답은 받지 않는다 — 사용자가 본 문장과 지금 문장이 다르다.
    종료 코드 — 0 남은 사람 확인 없음 · 1 남음(고칠 것 · 보류 · 빈칸) · 2 표를 못 읽음
    """
    try:
        keys, answers = ask_sheet.parse(sheet.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"⛔ {e}")
        return 2
    said: dict[str, str] = {}
    if replies:
        try:
            said = ask_sheet.parse_replies(replies)
        except ValueError as e:
            print(f"⛔ {e}")
            return 2
        unknown = sorted(set(said) - set(keys))
        if unknown:
            print(f"⛔ 표에 없는 번호 — {' '.join(unknown)} · 표를 다시 만들었으면 새 번호로 묻습니다")
            return 2
        answers.update(said)
    kept, edits, free, waiting, refused = [], [], [], [], []
    learned = 0
    docs: dict[str, Path] = {}
    for qid, key in keys.items():
        raw = answers.get(qid, "")
        kind = ask_sheet.kind_of(raw)
        p = docs.setdefault(key["doc"], Path(key["doc"]))
        if kind in (ask_sheet.BLANK, ask_sheet.HOLD):
            waiting.append(qid)
            continue
        if not p.is_file():
            refused.append(f"{qid} — 문서가 없습니다: {p}")
            continue
        # 다음 판정이 따를 기록 — 사용자가 본 줄(표의 줄 해시)에 단다. 그 뒤 문서가 바뀌어도
        # 사용자가 그 문장을 보고 정한 것은 그대로다.
        src = f"{sheet.name} {qid}" + (" · 대화로 받음" if qid in said else "")
        lines = read_doc(p).splitlines()
        # 표를 만든 뒤 위에 줄이 늘거나 줄었으면 같은 글의 줄을 찾아간다
        now = next((i for i, l in enumerate(lines, 1) if coverage.line_key(l) == key["line_key"]), None)
        learned += record_decision(p, key["line_key"], raw, kind, src, lines[now - 1] if now else None)
        if now is None:
            refused.append(f"{qid} {p.name} {key['line']}행 — 표를 만든 뒤 그 줄이 바뀌었습니다 · "
                           "표를 다시 만들어 다시 묻습니다")
            continue
        if kind in (ask_sheet.EDIT, ask_sheet.FREE):
            asks = [a for n, a in coverage.open_asks(coverage.doc_key(p), lines, LOG) if n == now]
            phrases = [str(a.get("phrase") or "") for a in asks]
            settled = None
            if kind == ask_sheet.EDIT and not raw.strip().strip("`").strip().startswith(ask_sheet.DIRECT):
                settled = edited_by_answer(lines[now - 1], asks)
                if settled:
                    approve(p, settled, f"사용자 답(사람 확인 표 {src}): {raw}", key["line_key"])
            tail = (" · 판정기 제안대로 고치면 다시 판정하지 않음" if settled
                    else f" · 고친 뒤 --answer {now} --note \"<사용자 답 원문>\" 으로 확정")
            (edits if kind == ask_sheet.EDIT else free).append(
                f"{qid} {p.name} {now}행 「{' · '.join(phrases)}」 — 사용자 답: {raw}{tail}")
            continue
        try:
            answer(p, [now], f"사용자 답(사람 확인 표 {src}): {raw}")
            kept.append(qid)
        except ValueError as e:
            refused.append(f"{qid} {p.name} {now}행 — {e}")
    print(f"사람 확인 표 읽음 — {sheet.name} · 행 {len(keys)}개")
    print(f"  다음 판정이 따를 답 기록 {learned}건 추가 — 판정기 프롬프트에 「사용자가 이미 답한 것」으로 실림")
    print(f"  그대로 — 답 기록에 남김 {len(kept)}건" + (f" ({' '.join(kept)})" if kept else ""))
    if edits:
        print(f"  고칠 것 {len(edits)}건 — 세션이 모두 고친 뒤 --since 로 한 번에 다시 판정합니다")
        for e in edits:
            print(f"    {e}")
    if free:
        print(f"  글로 적은 답 {len(free)}건 — 세션이 원문을 읽고 가립니다 · 고칠 뜻이면 고친 뒤, 유지하는 뜻이면 "
              "바로 --answer <행> --note \"<원문>\" 으로 남깁니다(답대로 고쳐 확정한 줄은 다시 판정하지 않음)")
        for e in free:
            print(f"    {e}")
    if waiting:
        print(f"  보류 · 빈칸 {len(waiting)}건 — 답이 없는 것으로 남아 발행과 배포가 막힙니다: {' '.join(waiting)}")
    for r in refused:
        print(f"  ⛔ {r}")
    left = sum(len(coverage.open_asks(coverage.doc_key(p), read_doc(p).splitlines(), LOG))
               for p in docs.values() if p.is_file())
    print(f"  남은 사람 확인 {left}건")
    return 1 if left else 0


#: 고친 말 점검 — 판정 호출이 낸 **수정안 자체**가 새 문제를 들여오는지 본다(모델을 더 부르지
#: 않는다). 2026-09-30 실문서 검토에서 지적 40건은 모두 맞았는데 수정안 여덟이 되돌아왔다 —
#: 드문 말로 바꿈(「소급」·「이날」·「간이로」) · 지시어(「이 기간」) · 개조식 값을 서술형으로 바꿈.
FREQ_PATH = HERE.parent / "data" / "catalog" / "work-korean-freq.json"
RARE_FLOOR = 40                 # 단어 점검(`rare_words.py`)과 같은 문턱
FIX_TAGS = ("NNG", "VV", "VA", "MAG", "XR")
DEMONSTRATIVE = re.compile(r"(?<![가-힣])(?:이날|그날|(?:이|그|저)\s?(?:날|때|기간|구간|곳|항목|경우|단계|시점|부분))(?![가-힣])")
PROSE_END = re.compile(r"(?:니다|다)[.。]?\s*$")
_kiwi = None


def _lemmas(text: str) -> list[str]:
    global _kiwi
    if _kiwi is None:
        # 검사기와 같은 한 벌을 쓴다 — 따로 띄우면 한 프로세스에 약 490MB 씩 쌓인다(2026-10-06)
        import kiwipiepy
        _kiwi = getattr(kiwipiepy, "_korean_qa_shared", None)
        if _kiwi is None:
            _kiwi = kiwipiepy._korean_qa_shared = kiwipiepy.Kiwi()
    return [f"{t.form}/{t.tag}" for t in _kiwi.tokenize(text) if t.tag in FIX_TAGS and len(t.form) > 1]


def fix_notes(fix: str, phrase: str, doc_lemmas: set, freq: dict | None) -> list[str]:
    """수정안이 들여온 문제 — 사람이 볼 한 줄씩. 형태소 분석기가 없으면 드문 낱말은 건너뛴다."""
    notes = []
    if freq is not None and fix:
        rare = [w for w in dict.fromkeys(_lemmas(fix)) if freq.get(w, 0) <= RARE_FLOOR]
        # 원문에 있던 드문 낱말을 그대로 둔 것도 짚는다 — 「소급」은 원문 낱말이었는데 사용자가
        # 「잘 쓰지 않으므로 바꾸면 좋을듯」으로 되돌렸다(2026-09-30). 새로 들여온 것과 갈라 적는다.
        new = [w.split("/")[0] for w in rare if w not in doc_lemmas]
        kept = [w.split("/")[0] for w in rare if w in doc_lemmas]
        if new:
            notes.append("고친 말에 드문 낱말 — " + " · ".join(new)
                         + f"(사람 업무 글 {RARE_FLOOR}회 이하) · 흔한 말로")
        if kept:
            notes.append("원문의 드문 낱말을 그대로 둠 — " + " · ".join(kept)
                         + f"(사람 업무 글 {RARE_FLOOR}회 이하) · 바꿀지 볼 것")
    for m in DEMONSTRATIVE.finditer(fix or ""):
        if m.group(0) not in (phrase or ""):
            notes.append(f"고친 말에 지시어 「{m.group(0)}」 — 가리키는 것을 이름으로")
    if fix and phrase and PROSE_END.search(fix) and not PROSE_END.search(phrase):
        notes.append("원문은 개조식인데 고친 말은 서술형 — 값 칸이면 개조식 유지")
    return notes


def load_freq():
    try:
        import kiwipiepy  # noqa: F401
        return json.loads(FREQ_PATH.read_text(encoding="utf-8"))["freq"]
    except Exception:
        return None


def pick_backend(which: str = "auto") -> str | None:
    """부를 백엔드 이름 · `auto` 면 이 PC 에서 쓸 수 있는 쪽을 Claude → Codex 순서로.

    설치·로그인 여부는 `llm_playbook.ladder.available` 이 가른다(게이트도 같은 것을 본다).
    Codex 만 쓰는 PC 에서도 판정기가 돌아야 발행 게이트가 판정을 요구할 수 있다.
    """
    if which != "auto":
        return which
    try:
        from llm_playbook.ladder import available
    except Exception:
        return "claude"         # 사다리가 없는 옛 llm_playbook — 전처럼 Claude 를 부른다
    return next((name for name in ("claude", "codex") if available(name)[0]), None)


def load_backend(which: str = "claude"):
    """정본은 `llm_playbook.backends` 하나다 — 없으면 None(세션이 직접 읽는다).

    부르는 길은 2층 탐침과 같은 것을 쓴다 — 잰 것과 도는 것이 같아야 한다.
    엔진 상태를 아는 사다리가 있으면 그 길을 사다리 `review` 한 칸으로 감싼다(`via_review`).
    """
    try:
        client = probe.load_client(which)
    except Exception:
        return None
    return via_review(which, client)


def via_review(which: str, client):
    """판정 호출을 사다리 `review`(폴백 없음) 한 칸으로 감싼다 — 모델과 부르는 길은 그대로.

    판정기는 점검표로 잰 모델(Claude `DEFAULT_MODEL` · Codex `CODEX_MODEL`)이어야 그 값이 산다.
    그래서 막혔을 때 다른 모델로 넘기지 않고 **바로 실패한다** — 막힌 엔진(슬랙 봇과 같은 엔진 상태
    파일)은 부르지도 않고 「limited · 풀리는 시각」을 사유로 올린다. 한도로 실패하면 막힘을 적고 답하면
    지운다. 빈 답도 실패로 올린다(예전에는 지적 0건으로 지나갔다).
    사다리에 `review` 가 없는 옛 llm_playbook 이면 감싸지 않는다(예전과 같다).
    """
    try:
        from llm_playbook import models as lp_models
        from llm_playbook.ladder import ask
        if "review" not in lp_models.ladders():
            return client
    except Exception:
        return client
    call, parse = client

    def call_review(*, model, system, user, max_tokens=4096, timeout=300.0, **kw):
        def adapter(_alias, system_, user_, timeout_, _effort, max_tokens_, **_):
            r = call(model=model, system=system_, user=user_, max_tokens=max_tokens_, timeout=timeout_, **kw)
            return r.get("text") or "", r.get("model") or model, {"cost_usd": r.get("cost_usd"),
                                                                    "usage": r.get("usage")}
        # 등급은 칸을 고르는 데만 쓴다 — 실제 모델은 위 `model` 이고 칸 별칭은 안 쓴다
        r = ask(next(iter(lp_models.tiers())), user, system=system, vendors=(which,), ladder="review",
                max_tokens=max_tokens,
                timeout=timeout, label="2층 판정", adapters={which: adapter}, ready=lambda _b: (True, ""))
        if not r["ok"]:
            until = r.get("until")
            when = time.strftime(" · %m-%d %H:%M 풀림", time.localtime(until)) if until else ""
            why = "; ".join(f"{s['backend']} 막힘" for s in r.get("skipped") or [] if s.get("why") == "blocked")
            why = why or "; ".join(str(a.get("why")) for a in r.get("attempts") or [])
            raise RuntimeError(f"{which} {r.get('outcome')}{when} — {why}"[:300])
        return {"text": r["text"], "model": r.get("model") or model,
                "cost_usd": r.get("cost_usd") if which == "claude" else None, "usage": r.get("usage")}
    return call_review, parse


def input_total(row: dict) -> int:
    """입력 토큰 전부 — 캐시에 쓴 것·읽은 것까지."""
    return sum(int(row.get(k) or 0) for k in ("input_tokens", "cache_write", "cache_read"))


def log_call(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


#: 재판정 입력을 남기는 날수 — 문맥 방식을 같은 입력으로 재생해 지적 차이를 보려고 둔다(외부 검토 2026-10-16)
REPLAY_DAYS = 30


def replay_dir() -> Path:
    """판정 기록 옆 폴더 — 시험 · 재현 도구가 기록 경로를 돌리면 함께 따라간다(실사용 저장소에 안 섞인다).

    ⛔ 사내 문서 원문이 들어간다 — 이 PC 밖으로 내보내지 않고 저장소에 넣지 않는다.
    """
    return LOG.parent / "korean-replay"


def rejudge_user(piece: dict, info: dict, closed: list, decided: list, instructed: list = ()) -> str:
    """재판정 한 조각의 사용자 메시지 — 판정과 재생(`replay_rejudge.py`)이 같이 쓴다(같은 입력이어야 견준다)."""
    mine = piece["mine"]
    plain = {n for n in mine if not info[n].get("anchor")}
    windowed = piece["mode"] in ("fixed", "block")
    return (probe.USER.format(document=piece["document"]) + (WINDOW_NOTE if windowed else "")
            + "\n\n이번에는 아래 줄만 점검한다 — 나머지 줄은 문맥으로만 읽고 지적하지 않는다.\n"
            + ", ".join(map(str, mine))
            + before_after(mine, info, [(n, r) for n, r in closed if n in plain],
                           [(n, d) for n, d in decided if n in plain],
                           [(n, r) for n, r in instructed if n in plain]))


def save_case(path: Path, key: str, text: str, want: set[int], anchors: dict, base, info: dict,
              rules_sha: str, system: str, model: str, context: str, closed: list, decided: list,
              instructed: list = ()) -> None:
    """재판정 한 번의 입력 — 그때 문서 · 대상 · 기준 판 · 계보 · 닫은 지적 · 사용자 답 · 시스템 프롬프트."""
    folder = replay_dir()
    folder.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - REPLAY_DAYS * 86400
    for old in folder.glob("*.json"):
        if old.stat().st_mtime < cutoff:
            old.unlink(missing_ok=True)
    case = {"at": datetime.now().isoformat(timespec="seconds"), "doc": str(path), "key": key, "text": text,
            "targets": sorted(want), "anchors": {str(n): g for n, g in anchors.items()}, "base": base,
            "info": {str(n): v for n, v in info.items()}, "rules": rules_sha, "model": model, "context": context,
            "system_sha": hashlib.sha256(system.encode("utf-8")).hexdigest()[:12],
            "decisions_prompt": decisions_prompt(load_decisions()),
            "closed": [[n, r] for n, r in closed], "decided": [[n, d] for n, d in decided],
            "instructed": [[n, r] for n, r in instructed]}
    name = f"{datetime.now():%Y%m%d-%H%M%S}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}.json"
    (folder / name).write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")


def open_for(path: Path, since: str) -> tuple[list[int], bool]:
    """`--since` 로 판정할 줄 — (줄 번호, git 안인가). ref 를 못 풀면 ValueError.

    갈라진 지점에 있던 줄과 판정기가 이미 본 줄은 뺀다. 고친 줄은 해시가 바뀌므로
    다시 판정 대상이 된다 — 고친 말이 새 문제를 들여오는지 보는 것이 재판정의 몫이다.
    """
    lines = read_doc(path).splitlines()
    base = coverage.base_lines(path, since)
    seen = coverage.judged(coverage.doc_key(path), LOG)
    return coverage.open_lines(lines, base, seen), base is not None


#: 같은 줄(계보)을 판정하는 상한 — 넘으면 그 줄의 지적을 고칠 지적으로 두지 않고 사람 확인으로
#: 올리고, 그 줄 자체도 기준 판과 함께 사람 확인에 올린다. 상한에 닿았다고 통과시키지 않는다 —
#: README 고리 시험에서 5회차에야 원문의 실제 논리 결함을 짚었다(외부 검토 「상한 도달은 보류 ·
#: 남은 지적만 넘기면 아직 못 찾은 결함은 아무에게도 안 간다」 · 2026-10-12).
REJUDGE_CAP = 3
#: 프롬프트에 싣는 지운 줄 — 대상 줄마다 이만큼까지
DELETED_PER_LINE = 3


def lineage(key: str, lines: list[str], targets: list[int], base: list[str] | None,
            since: float | None = None) -> dict[int, dict]:
    """대상 줄마다 {"round": 몇 번째 판정인가, "root": 기준 판 글 | None, "deleted": [지운 기준 판 줄]}.

    **자손 찾기** — 앞선 판정이 남긴 대상 줄 글 가운데 글자가 절반 이상 같은 것을 부모로 본다.
    고치는 것은 세션의 편집 도구라 판정기가 수정 시점을 못 본다 — 그래서 글자로 잇는다. 한 줄을
    둘로 나눠도 둘 다 부모를 찾아 판정 횟수를 물려받는다(나눈다고 예산이 새로 생기지 않는다).
    부모가 없으면 기준 판(갈라진 지점)의 비슷한 줄을 뿌리로, 그것도 없으면 새 줄이다.
    ⛔ 예전 판으로 되돌린 줄은 이미 본 줄이라 대상이 안 된다 — 그때 남은 고칠 지적이 다시 열려
       게이트가 막는다(`open_fixes` · 순환을 따로 안 세는 까닭).
    """
    prev = []
    for row in coverage._rows(key, LOG, None):
        # ⛔ 같은 갈라진 지점에서 한 판정만 센다 — 앞선 지점의 판정은 이미 합쳐진 작업이다. 그때 센
        #    횟수를 이어 세면 상한에 걸렸던 줄은 합쳐진 뒤 정당하게 고쳐도 매번 사람 확인으로 올라간다
        #    (2026-10-13 README 113행 · 전날 4회차로 합쳐진 줄을 고치자 5회차로 셈). 시각으로 거르면
        #    지점이 바뀐 뒤 옛 계보로 잘못 센 기록이 남아 이어진다 — 판정할 때의 지점을 기록에 적고 대조한다.
        #    지점을 안 적은 옛 기록은 횟수를 믿을 수 없어 세지 않는다.
        if row.get("ok") and row.get("base_time") == since:
            prev += [e for e in row.get("targeted") or [] if e.get("text")]
    ops = []
    if base:
        import difflib
        ops = difflib.SequenceMatcher(None, base, lines, autojunk=False).get_opcodes()
    out = {}
    for n in targets:
        text = lines[n - 1]
        # 글자가 절반 이상 같은 앞선 판 가운데 **가장 많이 판정된 것** — 가장 비슷한 것을 고르면
        # 나눈 줄 한쪽이 더 옛 판을 부모로 잡아 횟수가 줄었다(시험). 틀려도 일찍 멈추는 쪽이다.
        # ⛔ 횟수는 **가장 비슷한 것과 같은 계보 안에서만** 고른다(2026-10-19 재현 시험). 문서 전체의 앞선
        #    판 가운데 횟수가 큰 것을 고르자, 유사도 0.5 로 겨우 걸린 무관한 줄(「한 줄만 입력하면 됩니다」)이
        #    「자료 저장 위치입니다」의 부모가 되어 기준 판이 「한 줄로 던집니다」로 잡혔고, 판정기가 없는
        #    「뜻 바뀜」을 짚어 엉뚱한 수정안을 냈다. 계보는 뿌리(없으면 그 판 글)로 가른다.
        sims = [(e, coverage._similar(text, e["text"])) for e in prev]
        near = [(e, s) for e, s in sims if s >= coverage.SUCCESSOR]
        cand = None
        if base:
            cand = max((b for b in base if coverage.line_key(b)),
                       key=lambda b: coverage._similar(text, b), default=None)
            if cand is None or cand == text or coverage._similar(text, cand) < coverage.SUCCESSOR:
                cand = None
        pred = None
        if near:
            best, best_sim = max(near, key=lambda x: x[1])
            chain = best.get("root") or best["text"]
            pred = max(((e, s) for e, s in near if (e.get("root") or e["text"]) == chain),
                       key=lambda x: (int(x[0].get("round") or 1), x[1]))[0]
            # 기준 판에 그 계보 밖의 더 비슷한 줄이 있으면 앞선 판정은 다른 줄의 것이다
            if cand is not None and cand != chain and coverage._similar(text, cand) > best_sim:
                pred = None
        if pred is not None:
            info = {"round": int(pred.get("round") or 1) + 1, "root": pred.get("root") or pred["text"]}
        else:
            info = {"round": 1, "root": cand}
        gone = []
        for tag, i1, i2, j1, j2 in ops:
            if tag not in ("delete", "replace") or not (j1 - 1 <= n - 1 <= j2):
                continue
            for b in base[i1:i2]:
                if coverage.line_key(b) and not any(coverage._similar(b, l) >= coverage.SUCCESSOR
                                                    for l in lines[max(0, j1 - 2):j2 + 2]):
                    gone.append(b)
        info["deleted"] = gone[:DELETED_PER_LINE]
        info["deleted_keys"] = [coverage.line_key(b) for b in gone]
        out[n] = info
    return out


def closed_on(key: str, lines: list[str], mine: list[int]) -> list[tuple[int, dict]]:
    """대상 줄(또는 그 앞 판)에서 세션이 이미 닫은 고칠 지적 — (줄, 기록). 줄마다 최근 것 셋까지."""
    rows = [r for r in coverage._rows(key, coverage.DISMISSALS, None, fresh=False)
            if r.get("text") and not r.get("escalate")]
    out = []
    for n in mine:
        near = [r for r in rows if coverage._similar(lines[n - 1], r["text"]) >= coverage.SUCCESSOR]
        out += [(n, r) for r in near[-3:]]
    return out


def instruct(path: Path, n: int, note: str) -> str:
    """사용자 지시로 n행의 뜻을 일부러 바꿨다고 적는다 — 지시 원문을 옮긴다. 규칙에 안 맞으면 ValueError.

    ⛔ 세션이 지시를 지어내지 않는다 — 사용자가 한 말을 옮긴다. 「지시반영」 닫기(`dismiss`)는 판정기가 짚은
       뒤에 하나씩 닫는 길이고, 이것은 재판정 전에 지시를 알려 짚지 않게 하는 길이다(사내 문서 1건에서 「뜻이
       바뀐 곳」 닫기 46건 중 40건이 지시로 바꾼 것이었다 · 2026-10-13).
    """
    note = note.strip()
    if len(note) < NOTE_MIN or not QUOTE.search(note):
        raise ValueError("--note 에 사용자 지시 원문을 「」로 옮겨 적습니다(누가 · 언제와 함께)")
    lines = read_doc(path).splitlines()
    if not 0 < n <= len(lines) or not coverage.line_key(lines[n - 1]):
        raise ValueError(f"{n}행은 한글이 든 줄이 아닙니다")
    row = {"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(), "doc": str(path),
           "key": coverage.doc_key(path), "line": n, "line_key": coverage.line_key(lines[n - 1]),
           "text": lines[n - 1], "instruction": note}
    coverage.INSTRUCTIONS.parent.mkdir(parents=True, exist_ok=True)
    with coverage.INSTRUCTIONS.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return lines[n - 1].strip()[:40]


def instructed_on(key: str, lines: list[str], mine: list[int]) -> list[tuple[int, dict]]:
    """대상 줄(또는 그 앞 판)에 적힌 사용자 지시 — (줄, 기록). 줄마다 최근 것 둘까지."""
    rows = [r for r in coverage._rows(key, coverage.INSTRUCTIONS, None, fresh=False) if r.get("text")]
    out = []
    for n in mine:
        k = coverage.line_key(lines[n - 1])
        near = [r for r in rows if r.get("line_key") == k
                or coverage._similar(lines[n - 1], r["text"]) >= coverage.SUCCESSOR]
        out += [(n, r) for r in near[-2:]]
    return out


def decided_on(key: str, lines: list[str], mine: list[int]) -> list[tuple[int, dict]]:
    """대상 줄(또는 그 앞 판)에 사용자가 사람 확인으로 답한 것 — (줄, 결정 기록). 줄마다 최근 것 셋까지.

    ⛔ 전에는 세션의 처리 기록만 실어서, 판정기가 사용자가 고른 표현을 모른 채 다음 판정에서 그 괄호를
       다시 빼자 · 다시 넣자를 오갔다(2026-10-14 lab-docs). 줄 글이 없는 옛 기록은 잇지 못해 뺀다.
    """
    rows = [d for d in load_decisions() if coverage.key_matches(d.get("key"), key) and d.get("text")]
    out = []
    for n in mine:
        near = [d for d in rows if coverage._similar(lines[n - 1], d["text"]) >= coverage.SUCCESSOR]
        out += [(n, d) for d in near[-3:]]
    return out


def before_after(mine: list[int], info: dict[int, dict], closed: list[tuple[int, dict]] = (),
                 decided: list[tuple[int, dict]] = (), instructed: list[tuple[int, dict]] = ()) -> str:
    """대상 줄의 기준 판과 지운 줄 — 고친 말이 뜻을 바꿨는지 판정기가 대조하게 하는 글.

    세션이 자료로 확인하거나 까닭을 적어 닫은 지적도 함께 싣는다 — 줄이 바뀌면 판정기가 같은 의문을
    그대로 다시 냈다(2026-10-12 README 재판정 · 확인함으로 닫은 「조건이 빠짐」을 다음 회차에 또 냄).
    ⛔ 거르개가 아니다 — 판정기가 그래도 내면 게이트는 그대로 막는다(프롬프트로만 억제하지 않는다).
    """
    roots = [(n, info[n]["root"]) for n in mine if info.get(n, {}).get("root")]
    gone = [(n, d) for n in mine if not info.get(n, {}).get("anchor")
            for d in info.get(n, {}).get("deleted") or []]
    anchored = [n for n in mine if info.get(n, {}).get("anchor")]
    out = []
    if roots or gone:
        out += ["", "", "아래 줄은 기준 판(고치기 전 글)에서 바뀐 줄이다. 기준 판과 대조해 숫자 · 주체 · 부정 · "
                "조건 · 범위 · 확실성이 달라졌거나 필요한 정보가 빠졌으면 그것도 지적한다 — 갈래는 「고치다 뜻이 "
                "바뀐 곳」, 고친 말은 기준 판의 뜻을 살린 글이다. 기준 판에 있던 문제를 다시 짚지는 않는다."]
        out += [f"- {n}행 기준 판: {r}" for n, r in roots]
        if gone:
            out += ["지운 줄(기준 판에만 있고 지금 글에 없음) — 그 정보가 필요하면 가까운 대상 줄에 지적한다."]
            out += [f"- {n}행 가까이에서 지움: {d}" for n, d in gone]
    if anchored:
        out += ["", "", "아래 줄은 고치지 않았다. 바로 가까이에서 줄을 지웠다 — 지운 줄 때문에 남은 글에서 필요한 "
                "정보가 빠졌거나 뜻이 바뀌었는지만 본다. 그렇다면 갈래 「고치다 뜻이 바뀐 곳」으로 그 줄에 "
                "지적하고, 그 밖의 문제는 짚지 않는다."]
        for n in anchored:
            out += [f"- {n}행 가까이에서 지움: {d}" for d in info[n]["deleted"]]
            if info[n].get("more", 0) > 0:
                out.append(f"- {n}행 가까이에서 지움: (그 밖 {info[n]['more']}줄)")
    if closed:
        out += ["", "앞서 이 줄에서 확인하거나 까닭을 적어 닫은 지적이다. 지금 글에서 그 근거가 달라지지 않았으면 "
                "같은 지적을 다시 내지 않는다."]
        out += [f"- {n}행 「{r.get('phrase')}」 — {r.get('reason')}: {r.get('note')}" for n, r in closed]
    if decided:
        out += ["", "앞서 이 줄(고치기 전 판)에서 사람 확인으로 넘긴 지적에 사용자가 답한 것이다. 사용자가 고르거나 "
                "적은 표현을 되돌리거나 다시 바꾸자는 지적은 내지 않는다. 사실이 틀렸으면 그것만 짚는다."]
        out += [f"- {n}행 「{d.get('phrase')}」 · 판정기 제안 「{d.get('fix')}」 · 사용자: {d.get('answer')}"
                for n, d in decided]
    if instructed:
        # 지시 안의 뜻 변경만 덜 짚는다 — 지시는 편집 의도의 근거이지 새 주장이 참이라는 근거가 아니다(외부 검토)
        out += ["", "아래 줄은 사용자 지시에 따라 뜻을 일부러 바꾼 줄이다. 지시가 말한 변경은 「고치다 뜻이 바뀐 곳」으로 "
                "짚지 않는다. 지시가 말하지 않은 변경(수치 · 주체 · 범위 · 조건 · 시점), 확인이 필요한 새 주장, 다른 "
                "규칙 위반은 그대로 짚는다."]
        out += [f"- {n}행 지시: {r.get('instruction')}" for n, r in instructed]
    return "\n".join(out)


def held_ask(n: int, line: str, info: dict) -> dict:
    """상한을 넘은 줄을 사람 확인으로 — 짚은 표현은 줄 전체(그 줄이 그대로인 동안 열림)."""
    why = (f"같은 줄을 {info['round']}번째 판정 — 자동 수정 · 재판정 상한 {REJUDGE_CAP}회를 넘음 · "
           "기준 판과 대조해 뜻이 맞는지 사람이 확인")
    return {"line": n, "phrase": line.strip(), "category": "재판정 상한",
            # 표의 「고침」은 판정기 제안대로라는 뜻이라, 제안 칸을 「되돌림」으로 적어 뜻을 분명히 한다
            "fix": f"기준 판으로 되돌림 — {info['root']}" if info.get("root") else "(새로 쓴 줄 · 기준 판 없음)",
            "why": why, "decide": "ask", "held": True}


def judge(path: Path, model: str, timeout: float, backend, targets: list[int] | None = None,
          base: list[str] | None = None, anchors: dict[int, list[str]] | None = None,
          base_time: float | None = None, context: str = "chunk") -> dict:
    """`targets` 가 있으면 그 줄이 든 묶음만 부르고 그 줄에 달린 지적만 낸다.

    ⛔ **지적을 거르는 까닭** — 판정기는 같은 글을 다시 판정해도 지적 수가 평균 16%
       달랐다(`docs/calibration-20260929.md` · 2026-10-12 고정 문서 두 번은 7% 차이 ·
       일대일 겹침 87% · 겹친 105건의 fix/ask 는 모두 같음). 고친 줄 하나 때문에 묶음을 다시 보내면
       안 고친 줄에서 새 지적이 나오고, 그것을 고치면 또 다시 판정하게 된다. 프롬프트는
       탐침과 같게 두고 **결과만** 거른다 — 잰 것과 도는 것이 같아야 한다.
    """
    call_messages, parse_json = backend
    # CLI 는 이 프로세스의 환경 변수를 물려받는다 — 판정 호출에만 걸고 다른 세션 설정은 안 바꾼다
    ttl = os.environ.setdefault(CACHE_TTL_ENV, CACHE_TTL)
    text = read_doc(path)
    lines = text.splitlines()
    key = coverage.doc_key(path)
    want = set(targets) if targets is not None else None
    # 지우기만 한 자리의 대표 줄 — 그 줄은 그대로라 뜻 바뀜만 보고 판정 횟수에도 안 센다
    anchors = {n: g for n, g in (anchors or {}).items() if want is None or n not in want}
    if anchors:
        want = (want or set()) | set(anchors)
    # 사용자가 이미 답한 것 — 탐침과 다른 단 하나의 차이다(답은 사용자마다 다르다)
    decisions = load_decisions()
    rules = probe.rules_for("guided")
    system = probe.SYSTEM.format(rules=rules) + decisions_prompt(decisions)
    # 규칙 글의 판 — 규칙이 바뀐 뒤의 판정과 앞의 판정을 가르는 최소 식별자(외부 검토 · 2026-10-12)
    rules_sha = hashlib.sha256(rules.encode("utf-8")).hexdigest()[:12]
    info = lineage(key, lines, sorted(want - set(anchors)), base, base_time) if want else {}
    for n, gone in anchors.items():
        info[n] = {"round": 0, "root": None, "deleted": gone[:DELETED_PER_LINE], "more": len(gone) - DELETED_PER_LINE,
                   "deleted_keys": [coverage.line_key(g) for g in gone], "anchor": True}
    # 묶음 경고(2026-10-13) — 이번 대상이 모두 다시 판정하는 줄인데 다른 줄에 처리 안 된 고칠 지적이
    # 남았으면, 지적 하나 고칠 때마다 부르는 것이다(한 문서 58회 중 29회가 대상 3줄 이하). 막지는 않는다 —
    # 막으면 사실 주장을 좁힌 줄의 중간 판정 · 어려운 지적 하나에 문서 전체가 묶이는 부작용이 있다(외부
    # 검토). 얼마나 자주 이러는지 기록에 남겨 차단이 필요한지 나중에 정한다. 사람 확인은 세지 않는다 —
    # 세션이 못 푸는 것이다.
    edited = [n for n in (want or ()) if n not in anchors]
    rejudge_only = bool(edited) and all(info[n]["round"] >= 2 for n in edited)
    pending = (sum(1 for n, _ in coverage.open_fixes(key, lines, LOG) if n not in want)
               if rejudge_only else 0)
    found, calls, hidden, foreign, held = [], [], 0, 0, 0
    held_done: set[int] = set()
    queue = parts_for(lines, want, context, path)
    closed_all, decided_all, instructed_all = [], [], []
    if want is not None:
        plain = [n for n in sorted(want) if not info[n].get("anchor")]
        closed_all, decided_all = closed_on(key, lines, plain), decided_on(key, lines, plain)
        instructed_all = instructed_on(key, lines, plain)
        save_case(path, key, text, want, anchors, base, info, rules_sha, system, model, context,
                  closed_all, decided_all, instructed_all)
    while queue:
        piece = queue.pop(0)
        mine, windowed = piece["mine"], piece["mode"] in ("fixed", "block")
        short: set[int] = set()
        started = time.time()
        row = {"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(),
               "doc": str(path), "key": key,
               "sha256": hashlib.sha256("\n".join(piece["seen"]).encode("utf-8")).hexdigest()[:16],
               "lines": piece["label"], "model": model, "rules": rules_sha,
               "cache_ttl": ttl,       # 적용 전후 비용을 기록으로 가른다
               "context": piece["mode"],
               # 게이트가 「이번 가지의 새 줄을 판정기가 다 봤나」를 이것으로 가른다 — 창이면 보낸 줄만
               "seen": coverage.seen_keys(piece["seen"])}
        user = rejudge_user(piece, info, closed_all, decided_all, instructed_all) if want is not None \
            else probe.USER.format(document=piece["document"])
        if want is not None:
            # 묶음은 문맥으로 통째로 보내되 지적은 새 줄에만 받는다. 전에는 묶음 전체에
            # 지적을 써 오게 하고 새 줄 밖의 것을 버렸다 — 출력 토큰이 곧 시간이고(상관 0.97)
            # 지적 하나가 약 206토큰이라, 버리는 지적만큼 시간과 한도를 썼다(2026-10-07 실측).
            row["targets"] = len(mine)
            row["rejudge_only"] = rejudge_only  # 묶음 경고의 근거 — 얼마나 자주 이러는지 센다
            row["pending_fixes"] = pending
            row["base_time"] = base_time       # 이 판정을 센 갈라진 지점 — 다음 판정이 같은 지점 것만 센다
            # 다음 판정이 이 줄의 자손을 찾고 판정 횟수를 이어 세는 데 쓴다(저장소 밖 기록)
            row["targeted"] = [{"key": coverage.line_key(lines[n - 1]), "text": lines[n - 1],
                                "round": info[n]["round"], "root": info[n]["root"]}
                               for n in mine if not info[n].get("anchor")]
            # 게이트가 「지운 자리를 판정기가 봤나」를 이것으로 가른다
            row["deleted_seen"] = sorted({k for n in mine for k in info[n].get("deleted_keys") or [] if k})
            over = [n for n in mine if info[n]["round"] > REJUDGE_CAP]
        try:
            r = call_messages(model=model, system=system, user=user,
                              max_tokens=12000, temperature=0, timeout=timeout)
        except Exception as e:          # 실패도 기록한다 — 시간은 들었다
            row.update(ok=False, error=f"{type(e).__name__}: {e}"[:200],
                       seconds=round(time.time() - started, 1))
            log_call(row)
            calls.append(row)
            raise
        items = parse_json(r.get("text") or "") or []
        if not isinstance(items, list):
            items = []
        usage = r.get("usage") or {}
        row.update(ok=True, model=r.get("model") or model,
                   seconds=round(time.time() - started, 1),
                   # ⛔ 입력은 셋으로 나뉘어 온다 — 캐시에 쓴 것·읽은 것을 빼면 입력이
                   #    2 토큰으로 찍힌다(첫 실측 2026-09-29). 합계는 `input_total` 로 센다.
                   input_tokens=usage.get("input_tokens", 0),
                   cache_write=usage.get("cache_creation_input_tokens", 0),
                   cache_read=usage.get("cache_read_input_tokens", 0),
                   output_tokens=usage.get("output_tokens", 0),
                   cost_usd=r.get("cost_usd"), findings=len(items))
        asks, fixes = [], []
        hidden_before = hidden
        if want is not None:
            # 상한을 처음 넘은 줄은 지적이 없어도 사람에게 — 아직 못 찾은 결함도 그 줄에 있을 수 있다
            fresh_held = [n for n in over if info[n]["round"] == REJUDGE_CAP + 1 and n not in held_done]
            held_done.update(fresh_held)
            items = list(items) + [held_ask(n, lines[n - 1], info[n]) for n in fresh_held]
        for it in items:
            if isinstance(it, dict):
                it["line"] = relocate(lines, it.get("line"), str(it.get("phrase") or ""))
                # 줄을 못 찾은 지적은 남긴다 — 새 줄 것인지 모르면 보이는 쪽으로
                if want is not None and it["line"] is not None and it["line"] not in want:
                    hidden += 1
                    continue
                # 대표 줄은 그대로인 줄이다 — 지운 줄 때문에 뜻이 바뀐 것만 받는다(안 고친 줄의 새 지적은
                # 고리를 만든다)
                if it["line"] in anchors and "뜻이 바뀐" not in str(it.get("category") or ""):
                    hidden += 1
                    continue
                # 창에서 생략된 곳 때문에 판단하지 못한 줄 — 처리할 지적이 아니라 chunk 로 다시 판정할 줄이다
                if windowed and it.get("category") == CONTEXT_SHORT and it["line"] in (want or ()):
                    short.add(it["line"])
                    continue
                # ⛔ 한글이 없는 줄의 지적은 뺀다 — 이 판정기는 한글을 본다. 영문 페이지에서
                #    영어 문장을 사람 확인으로 냈는데 답 기록은 한글 줄만 받아, 배포가 풀 길
                #    없이 막힐 뻔했다(2026-10-06 사이트 첫 전수 판정).
                n = it["line"]
                if isinstance(n, int) and 0 < n <= len(lines) and not coverage.line_key(lines[n - 1]):
                    foreign += 1
                    continue
                if want is not None and n in over and not is_ask(it):
                    it["decide"] = "ask"
                    it["why"] = (f"{it.get('why') or ''} · 같은 줄을 {info[n]['round']}번째 판정 — "
                                 f"상한 {REJUDGE_CAP}회를 넘어 사람 확인으로 올림").lstrip(" ·")
                    it["held"] = True
                if it.get("held"):
                    held += 1
                found.append(it)
                ok_line = isinstance(n, int) and 0 < n <= len(lines)
                rec = {"line_key": coverage.line_key(lines[n - 1]) if ok_line else None,
                       "line": n, "phrase": it.get("phrase"), "fix": it.get("fix"),
                       "why": it.get("why"), "category": it.get("category")}
                if is_ask(it):
                    asks.append(rec)
                else:
                    # 고친 줄을 이 줄의 자손으로 찾으려면 그때 글이 있어야 한다(저장소 밖 기록)
                    fixes.append(dict(rec, check=it.get("check") or "", text=lines[n - 1] if ok_line else ""))
        # 발행 직전 검사가 「사용자 답을 아직 못 받은 지적」 · 「처리 안 된 고칠 지적」을 이것으로 가른다
        row["asks"] = asks
        row["fixes"] = fixes
        if want is not None:
            row["hidden"] = hidden - hidden_before   # 새 줄 밖에 달려 버린 지적 — 0 에 가까워야 한다
        if short:
            row["context_short"] = sorted(short)    # 창이 모자랐던 줄 — 그 비용도 창 방식의 비용이다
            queue += [dict(p, mode=f"chunk←{CONTEXT_SHORT}") for p in parts_for(lines, short, "chunk", path)]
        log_call(row)
        calls.append(row)
    freq = load_freq()
    doc_lemmas = set(_lemmas(text)) if freq is not None else set()
    for it in found:
        # 상한을 넘은 줄의 사람 확인은 수정안이 아니라 기준 판을 보여 준다 — 점검할 고친 말이 없다
        if it.get("category") == "재판정 상한":
            continue
        it["fix_notes"] = fix_notes(str(it.get("fix") or ""), str(it.get("phrase") or ""),
                                    doc_lemmas, freq)
    return {"doc": str(path), "findings": found, "calls": calls, "fix_checked": freq is not None,
            "targets": None if want is None else len(want), "hidden": hidden, "foreign": foreign,
            "held": held, "pending_fixes": pending}


def show(result: dict) -> None:
    calls = result["calls"]
    secs = sum(c.get("seconds") or 0 for c in calls)
    cost = sum(c.get("cost_usd") or 0 for c in calls)
    tin = sum(input_total(c) for c in calls)
    tout = sum(c.get("output_tokens") or 0 for c in calls)
    # Codex 는 금액을 안 준다 — 0.00달러로 찍으면 공짜로 읽힌다
    priced = any(c.get("cost_usd") is not None for c in calls)
    money = (f"환산 {cost:.2f}달러(구독 · 청구액 아님)" if priced
             else "금액 없음(Codex 구독 · 토큰만 기록)" if calls else "호출 없음")
    print(f"── 2층 판정 · {Path(result['doc']).name} · 지적 {len(result['findings'])}건 · "
          f"호출 {len(calls)}회 · {secs:.0f}초 · 토큰 입력 {tin:,} · 출력 {tout:,} · {money}")
    if result.get("targets") is not None:
        if not result["targets"]:
            print("  판정할 새 줄 없음 — 갈라진 지점 뒤 새 줄을 판정기가 모두 봤습니다")
        else:
            print(f"  새 줄 {result['targets']}개만 판정 · 그 밖의 줄에 달린 지적 "
                  f"{result.get('hidden', 0)}건은 숨김(이미 판정했거나 갈라진 지점에 있던 줄)")
    if result.get("pending_fixes"):
        print(f"  ⚠️ 다른 줄에 처리 안 된 고칠 지적 {result['pending_fixes']}건이 남은 채 다시 판정했습니다 — "
              "다 처리한 뒤 한 번에 다시 판정하면 호출이 줄어듭니다(방향 확인용 중간 판정이면 그대로 둡니다)")
    if result.get("held"):
        print(f"  같은 줄을 {REJUDGE_CAP}번 넘게 판정한 줄의 지적 {result['held']}건은 사람 확인으로 올림 — "
              "자동 수정을 멈추고 사용자가 기준 판과 대조합니다")
    if result.get("foreign"):
        print(f"  한글이 없는 줄에 달린 지적 {result['foreign']}건은 뺌 — 이 판정기는 한글을 봄")
    asks = [f for f in result["findings"] if is_ask(f)]
    fixes = [f for f in result["findings"] if not is_ask(f)]
    for title, group in (("사람 확인 — 판정기가 정하지 못해 사용자에게 넘긴 지적", asks),
                         ("고칠 지적", fixes)):
        if not group:
            continue
        print(f"  ── {title} {len(group)}건")
        for f in sorted(group, key=lambda f: (f.get("line") or 0)):
            tag = " [사실 확인]" if not is_ask(f) and coverage.needs_check(f) else ""
            print(f"  {str(f.get('line') or '?'):>4}행{tag}  「{f.get('phrase')}」 — "
                  f"{f.get('category')} → {f.get('fix')}")
            if f.get("check"):
                print(f"         확인할 사실: {f['check']}")
            if f.get("why"):
                print(f"         {f['why']}")
            for note in f.get("fix_notes") or []:
                print(f"         ⚠️ {note}")
    if not result.get("fix_checked", True):
        print("  ⚠️ 형태소 분석기가 없어 고친 말의 드문 낱말을 안 봤습니다(지시어·형식은 봄)")
    # 판정기가 칸을 비우면 고칠 지적으로 센다 — 조용히 그렇게 세면 사람에게 갈 것이 묻힌다
    blank = sum(1 for f in result["findings"] if not str(f.get("decide") or "").strip())
    if blank:
        print(f"  ⚠️ 판정기가 고침·사람 확인을 안 가른 지적 {blank}건 — 고칠 지적으로 셈")
    print("  ⚠️ 지적마다 맞는지 판단한다 — 헛짚음이 섞인다.")
    if fixes:
        me = Path(__file__).as_posix()
        print("  ⛔ 고칠 지적은 처리해야 발행된다 — 고치거나(다 처리한 뒤 --since 로 한 번에 다시 판정), 지적마다 까닭을 적는다:")
        print(f"     python -X utf8 {me} <문서> --dismiss <행> --reason <{'|'.join(REASONS)}> --note \"근거\"")
        print(f"     python -X utf8 {me} <문서> --escalate <행> --note \"세션이 정할 수 없는 까닭\"")
        print("     「[사실 확인]」 지적은 자료로 확인해 「확인함」으로 닫거나 사람 확인으로 올린다.")
    if asks:
        print("  ⛔ 사람 확인 지적은 세션이 정하지 않는다 — 표로 만들어 사용자에게 넘기고, 적은 답을 읽는다:")
        print(f"     python -X utf8 {Path(__file__).as_posix()} \"{Path(result['doc']).as_posix()}\" "
              "--sheet <저장소 밖 경로>.md")
        print(f"     python -X utf8 {Path(__file__).as_posix()} --answers-from <그 표>")
        print("     답을 못 받은 지적이 남으면 발행 직전 검사가 막는다.")


def cost_report(by: str) -> None:
    if not LOG.is_file():
        print(f"기록 없음 — {LOG}")
        return
    rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]
    key = {"day": lambda r: r["at"][:10], "month": lambda r: r["at"][:7],
           "doc": lambda r: Path(r["doc"]).name}[by]
    agg = defaultdict(lambda: [0, 0, 0.0, 0, 0, 0.0])
    for r in rows:
        a = agg[key(r)]
        a[0] += 1
        a[1] += 0 if r.get("ok") else 1
        a[2] += r.get("seconds") or 0
        a[3] += input_total(r)
        a[4] += r.get("output_tokens") or 0
        a[5] += r.get("cost_usd") or 0
    print(f"2층 판정 호출 비용 · {LOG}")
    print("  환산 금액은 API 단가 기준 — 구독이라 청구액이 아님")
    unpriced = sum(1 for r in rows if r.get("ok") and r.get("cost_usd") is None)
    if unpriced:
        print(f"  ⚠️ 금액 없는 호출 {unpriced}회(Codex)는 환산에 안 들어감 — 토큰만 셈")
    print(f"  {'묶음':<24}{'호출':>5}{'실패':>5}{'소요(분)':>9}{'입력 토큰':>12}{'출력 토큰':>11}{'환산(달러)':>11}")
    tot = [0, 0, 0.0, 0, 0, 0.0]
    for k in sorted(agg):
        a = agg[k]
        tot = [x + y for x, y in zip(tot, a)]
        print(f"  {k:<24}{a[0]:>5}{a[1]:>5}{a[2] / 60:>9.1f}{a[3]:>12,}{a[4]:>11,}{a[5]:>11.2f}")
    print(f"  {'합계':<24}{tot[0]:>5}{tot[1]:>5}{tot[2] / 60:>9.1f}{tot[3]:>12,}{tot[4]:>11,}{tot[5]:>11.2f}")


def main(argv=None, backend=None) -> int:
    ap = argparse.ArgumentParser(description="2층 판정 호출 · 비용 기록")
    ap.add_argument("docs", nargs="*")
    ap.add_argument("--backend", choices=("auto", "claude", "codex"), default="auto",
                    help="auto 면 Claude → Codex 순서로 이 PC 에서 쓸 수 있는 쪽")
    ap.add_argument("--model", help=f"기본 — Claude {DEFAULT_MODEL} · Codex {CODEX_MODEL}")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--json", help="지적을 JSON 으로도 씀")
    ap.add_argument("--since", metavar="REF",
                    help="REF 와 갈라진 뒤 새로 생겼고 아직 판정 안 한 줄만 판정 — 예: origin/main")
    ap.add_argument("--context", choices=CONTEXT_MODES, default="chunk",
                    help="--since 재판정에 보낼 문맥 — chunk(기본 · 180줄 묶음) · fixed · block(실험)")
    ap.add_argument("--cost", action="store_true", help="누적 비용 보기")
    ap.add_argument("--by", choices=("day", "month", "doc"), default="day")
    ap.add_argument("--answer", type=int, action="append", metavar="행",
                    help="사람 확인 지적에 사용자가 답한 줄 — 여러 번 줄 수 있음 · --note 필수")
    ap.add_argument("--note", default="", help="--answer 와 함께 · 사용자가 정한 것")
    ap.add_argument("--asks", action="store_true",
                    help="모델을 부르지 않고 답을 기다리는 사람 확인 지적만 보기")
    ap.add_argument("--sheet", metavar="경로.md",
                    help="답을 기다리는 사람 확인을 md 표로 씀 — 사용자에게 넘기는 형식 · 모델 안 부름")
    ap.add_argument("--answers-from", metavar="경로.md",
                    help="사용자가 답을 적은 사람 확인 표를 읽음 — 그대로만 답 기록에 남김")
    ap.add_argument("--reply", action="append", metavar="'Q번호 답'",
                    help="--answers-from 과 함께 · 대화로 받은 답을 사용자 원문 그대로 — 여러 번 줄 수 있음")
    ap.add_argument("--fixes", action="store_true",
                    help="모델을 부르지 않고 처리 안 된 고칠 지적만 보기")
    ap.add_argument("--dismiss", type=int, metavar="행",
                    help="고칠 지적 하나를 받지 않기로 적음 — --reason · --note 필수")
    ap.add_argument("--reason", choices=tuple(REASONS), help="--dismiss 의 사유")
    ap.add_argument("--escalate", type=int, metavar="행",
                    help="고칠 지적 하나를 사람 확인으로 올림 — --note 필수")
    ap.add_argument("--phrase", help="--dismiss · --escalate 에서 그 줄의 지적이 둘 이상일 때 고르는 표현")
    ap.add_argument("--instructed", type=int, action="append", metavar="행",
                    help="사용자 지시로 뜻을 일부러 바꾼 줄 — --note 에 지시 원문(「」) · 재판정이 지시 안의 뜻 변경은 안 짚음")
    a = ap.parse_args(argv)
    if a.cost:
        cost_report(a.by)
        return 0
    if a.answers_from:
        return read_answers(Path(a.answers_from), a.reply)
    if not a.docs:
        ap.print_usage()
        return 2
    if a.instructed:
        if len(a.docs) != 1:
            print("⛔ --instructed 는 문서 하나에만 씁니다 — 줄 번호가 문서마다 다릅니다")
            return 2
        try:
            for n in a.instructed:
                print(f"  지시 기록 — {n}행 「{instruct(Path(a.docs[0]), n, a.note)}」 · 재판정이 지시 안의 뜻 변경은 안 짚음")
        except ValueError as e:
            print(f"⛔ {e}")
            return 2
        return 0
    if a.sheet:
        missing = [d for d in a.docs if not Path(d).is_file()]
        if missing:
            print(f"⛔ 파일 없음 — {missing[0]}")
            return 2
        out = Path(a.sheet)
        rows, asks, listing = write_sheet([Path(d) for d in a.docs], out)
        print(f"사람 확인 표 — 줄 {rows}개 · 지적 {asks}건 · {out.resolve().as_uri()}")
        if 0 < asks <= ask_sheet.SCREEN_MAX:
            print(f"  지적이 {ask_sheet.SCREEN_MAX}건 이하라 화면으로 묻습니다 — 아래 목록을 사용자에게 그대로 보이고,")
            print("  받은 답을 사용자 원문 그대로 옮겨 읽습니다(답: 그대로 · 고침 · 직접: … · 보류):")
            print(f"    python -X utf8 {Path(__file__).resolve().as_posix()} --answers-from {out.resolve().as_posix()} "
                  "--reply 'Q1 그대로' --reply 'Q2 직접: …'")
            print()
            print(listing)
        elif asks:
            print(f"  지적이 {ask_sheet.SCREEN_MAX}건을 넘어 표 파일로 묻습니다 — "
                  "위 경로를 사용자에게 주고 「답」 칸을 채우게 합니다")
        if coverage.repo_of(out) is not None:
            print("  ⚠️ 표가 git 저장소 안에 있습니다 — 문서 글이 들어 있으니 커밋하지 않습니다")
        return 1 if asks else 0
    if a.answer or a.asks:
        missing = [d for d in a.docs if not Path(d).is_file()]
        if missing:
            print(f"⛔ 파일 없음 — {missing[0]}")
            return 2
        if a.answer:
            if len(a.docs) != 1:
                print("⛔ --answer 는 문서 하나에만 씁니다 — 줄 번호가 문서마다 다릅니다")
                return 2
            try:
                done = answer(Path(a.docs[0]), a.answer, a.note)
            except ValueError as e:
                print(f"⛔ {e}")
                return 2
            for head in done:
                print(f"  답 기록 — 「{head}」")
        left = sum(show_open_asks(Path(d)) for d in a.docs)
        return 1 if left and a.asks else 0
    if a.fixes or a.dismiss is not None or a.escalate is not None:
        missing = [d for d in a.docs if not Path(d).is_file()]
        if missing:
            print(f"⛔ 파일 없음 — {missing[0]}")
            return 2
        if a.dismiss is not None or a.escalate is not None:
            if len(a.docs) != 1:
                print("⛔ --dismiss · --escalate 는 문서 하나에만 씁니다 — 줄 번호가 문서마다 다릅니다")
                return 2
            try:
                if a.dismiss is not None:
                    got = dismiss(Path(a.docs[0]), a.dismiss, a.reason or "", a.note, a.phrase)
                    print(f"  처리 기록 — 「{got}」 · {a.reason}")
                else:
                    got = escalate(Path(a.docs[0]), a.escalate, a.note, a.phrase)
                    print(f"  사람 확인으로 올림 — 「{got}」 · --sheet 로 표를 만들어 사용자에게 넘깁니다")
            except ValueError as e:
                print(f"⛔ {e}")
                return 2
        left = sum(show_open_fixes(Path(d)) for d in a.docs)
        return 1 if left and a.fixes else 0
    name = pick_backend(a.backend)
    model = a.model or (CODEX_MODEL if name == "codex" else DEFAULT_MODEL)
    backend = backend or (load_backend(name) if name else None)
    if backend is None:
        print("⛔ 2층 판정 호출을 못 합니다 — llm_playbook 이 없거나 Claude Code · Codex 둘 다 "
              "설치·로그인이 안 돼 있습니다. 판단 규칙과 9단계를 세션이 직접 읽고 판정합니다.")
        return 3
    results = []
    for d in a.docs:
        p = Path(d)
        if not p.is_file():
            print(f"⛔ 파일 없음 — {d}")
            return 2
        targets, base, anchors, base_t = None, None, None, None
        if a.since:
            try:
                targets, in_git = open_for(p, a.since)
                base = coverage.base_lines(p, a.since) if in_git else None
            except ValueError as e:
                print(f"⛔ {e}")
                return 2
            base_t = coverage.base_time(p, a.since) if in_git else None
            if base:
                key = coverage.doc_key(p)
                anchors = dict(coverage.open_deletions(read_doc(p).splitlines(), base,
                                                       coverage.deleted_seen(key, LOG)))
            if not in_git:
                print(f"  {p.name} — git 밖 문서라 갈라진 지점이 없습니다 · 아직 판정 안 한 한글 줄을 모두 봅니다")
        try:
            results.append(judge(p, model, a.timeout, backend, targets, base, anchors, base_t, a.context))
        except Exception as e:
            print(f"⛔ 호출 실패 — {p.name}: {type(e).__name__}: {e}"[:300])
            print("   검사되지 않았습니다 — 세션이 규칙을 직접 읽고 판정합니다.")
            return 4
        show(results[-1])
    if a.json:
        Path(a.json).write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
