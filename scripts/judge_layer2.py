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
import collections
import contextlib
import difflib
import hashlib
import importlib
import json
import math
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
THINKING_ENV = "KOREAN_QA_JUDGE_THINKING"   # low · medium · high — 비우면 모델 기본값
#: 검사 단계(2026-11-04 사용자 「최소비용 검사 - 최적 검사(가성비) - 최대 검사」) — 첫 판정과 재판정의
#: (모델, 사고 깊이), 다른 줄 지적을 남긴 채 부르는 재판정을 막을지, 문서 한 건의 비용 한도(API 단가 환산 원).
#: 근거 측정은 runs/judge-effort-levels-20261104 — 사고 깊이 high 는 세 모델 모두 medium 보다 낫지 않았다
#: **한도는 과금 방식별** (2026-11-05 사용자 「대부분은 크레딧을 사용하지 않을 것이다」) — 공개판은 Claude Code 로그인
#: (구독)으로 부르고 이 PC 도 구독만 쓴다. 구독 호출은 같은 판정에 출력 토큰을 약 2.5배 써 환산 비용이 크레딧
#: 호출의 약 1.8배였다(가성비 흐름 시험). 그래서 구독 한도는 크레딧 한도 × 1.8 로 멈추는 지점을 맞추고, 각 단계의
#: 정상 비용(90번째 백분위수)의 약 2배에서 헛도는 반복을 막는다. 크레딧 호출은 실제 돈이라 「문서 한 편 1,000원」을
#: 그대로 지킨다. 최대 단계는 1.8 배율을 가정한 추정이라 실사용 기록이 쌓이면 단계별로 다시 정한다
LEVEL_ENV = "KOREAN_QA_LEVEL"
LEVELS = {
    # 최대는 사고 깊이를 넘기지 않는다 — Opus 5.5 기본값(medium)으로 예전 판정기와 같은 호출
    "max": {"first": ("opus", None), "rejudge": ("opus", None), "batch": False,
            "budget_won": {"subscription": 4500, "api": 2500}},
    "balanced": {"first": ("opus", "low"), "rejudge": ("sonnet", "medium"), "batch": True,
                 "budget_won": {"subscription": 1800, "api": 1000}},
    "min": {"first": ("sonnet", "medium"), "rejudge": ("sonnet", "medium"), "batch": True,
            "budget_won": {"subscription": 900, "api": 500}},
}
LEVEL_ALIASES = {"최대": "max", "가성비": "balanced", "최소": "min"}
DEFAULT_LEVEL = "max"
WON_PER_USD = 1400
#: 같은 문서의 판정 사이가 이만큼 넘게 비면 다른 작업으로 보고 비용을 새로 센다
WORK_GAP_S = 3 * 3600
#: 판정 기록 한 줄에 함께 남길 것 — main 이 검사 단계와 한도 넘김 승인을 넣는다
RUN_NOTES: dict = {}
DEFAULT_MODEL = "opus"      # 점검표에서 Sonnet 은 일상 동사 묶음 4/7 · Opus 6/7
#: Codex 쪽 기본 — 2026-10-02 대장 탐침 · 점검표를 Opus 와 나란히 잰 값(`docs/calibration-20260929.md`)
#: astra-high 와 회수 · 헛짚음이 같고 5시간 한도는 4분의 1(탐침 1회 1~2% · astra 6~7%)
CODEX_MODEL = "sol-high"
#: Claude Code 프롬프트 캐시 유지 시간 — 구독 로그인 기본은 1시간(쓰기 단가가 입력의 2배)이고 5분은 1.25배다.
#: 판정 호출의 93% 가 앞 호출 5분 안에 이어진다(2026-10-15 · 판정 결과와 무관 · 사용자 결정 「적용」). 그때 적은
#: 「환산 비용 20% 감소」는 과대였다 — 시스템 프롬프트는 문서 사이에, 문서 묶음은 같은 문서끼리만 캐시를 나눈다고 보고
#: 다시 계산하면 약 −9%(가정에 따라 −17%~+3% · 2026-10-21 회고 검토). 5분이 손해로 돌아서는 것은 캐시를 쓴 뒤 5~60분
#: 간격으로 다시 읽는 비율이 약 61% 를 넘을 때이고 그 비율은 4~10% 였다. 환경 변수를 이미 정했으면 그 값을 따른다.
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
#: 재판정 기본 문맥 — fixed(2026-10-20). 같은 입력 재생(Markdown 27건 · 두 번씩)에서 chunk 와 지적 일치 0.828(chunk
#: 끼리 0.811). 두 번 다 같은 쪽으로 갈린 줄을 사용자가 판단해 fixed 놓침 1 · 헛짚음 1 · chunk 가 놓친 2줄을 잡음,
#: chunk 놓침 2. block 은 헛짚음 5라 안 골랐다. 그때 적은 비용 「−46%」는 과대였다 — 먼저 부른 쪽이 캐시를 쓴 순서
#: 효과와 두 방식이 같은 입력이던 사례가 섞였다. 세션 흉내의 재판정 단계로 다시 보면 행 형식 뒤 chunk 대비 중앙값
#: 0.42 → 0.35달러(−16% · 셋 대 셋 단측 p 0.05 · 2026-10-21 `bench_loop.py compare --rule rejudge`).
#: HTML 은 창을 못 잡아 chunk 로 간다(`WINDOWABLE`).
DEFAULT_CONTEXT = "fixed"
FIXED_LINES = 20
#: fixed 창 끝이 문단 · 목록 · 표 · 코드 블록 안에 걸리면 블록 끝까지 넓히는 최대 줄 수 — 넘으면 그대로 자른다
#: (외부 검토 Argon · 2026-10-20 「창 경계가 표나 코드 블록 중간을 자름」)
FIXED_SNAP = 10
#: block 에서 대상의 구조 단위와 제목 사슬이 이보다 길면 자르지 않고 chunk 로 복귀한다
BLOCK_BUDGET = 120
#: 판정기가 생략된 곳 때문에 판단하지 못한 줄에 다는 갈래 — 그 줄은 chunk 로 다시 판정한다
CONTEXT_SHORT = "문맥 부족"
WINDOWABLE = (".md", ".markdown")
#: HTML 에도 fixed 창을 쓴다(실험 · 2026-10-20) — HTML 은 보이는 글만 보내는데도 창을 못 써 늘 180줄 묶음을 다시 보내,
#: 재판정 비용의 62% 가 HTML 이었다. 보이는 글에는 `#` 과 빈 줄이 없어 제목은 `<h1>`~`<h6>` 줄로 잡는다. 표는 칸마다
#: 한 줄이라 창이 머리 칸을 자를 수 있어 재생으로 잰 뒤 켰다(2026-10-20 · 공개 HTML 6쪽 앞 360줄을 실제로 0회차
#: 판정하고 수정안을 넣어 만든 입력 · 두 번씩): 대상 2줄 재판정은 처음 부를 때 쓰기 36.8k → 21.6k(−41%) · 환산
#: −18%(출력이 조금 늘어서), 두 번 다 한쪽만 짚은 줄은 fixed 쪽 1줄(정당한 지적)뿐. 대상 15~29줄은 창이 180줄을 넘어
#: 전부 chunk 로 복귀해 차이 없음. 표본이 작다(대상 12줄) — 판정 기록의 `context` 로 계속 본다.
WINDOW_HTML = True
WINDOW_NOTE = ("\n\n이번에는 문서의 일부만 보낸다. 줄 번호는 원래 문서의 번호이고 「…(N줄 생략)…」 자리에는 보내지 "
               "않은 줄이 있다. 대상 줄을 판단하는 데 필요한 내용(용어 정의 · 선행사 · 앞서 나온 수치 · 표나 목록의 "
               f"머리)이 생략된 곳에 있어 판단할 수 없으면 그 줄에 갈래 「{CONTEXT_SHORT}」로 지적을 하나만 내고 다른 "
               "지적은 내지 않는다. 생략된 곳에 없을 것이라 짐작해 「선행사 없음」 같은 지적을 내지 않는다.")

#: (2026-10-20) 창 옆에 문서 전체에서 뽑은 목적, 독자, 용어를 붙여 보는 실험은 폐기했다 — 시료 문서에서는 놓친 줄을
#: 살렸지만(「지적 대상 모음」이라는 힌트가 됨) 실제 문서 8건 × 2회에서 붙인 쪽에만 나온 맞는 지적이 1건 이하였다.


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


def heading_chain(lines: list[str], n: int, heads: dict[int, int] | None = None) -> list[int]:
    """n행 위의 제목 사슬 — 가까운 제목부터 더 높은 수준의 제목을 거슬러 올라간다.

    `heads` 는 HTML 의 제목 줄(줄 번호 → 수준) — 보이는 글에는 `#` 이 없어 따로 받는다.
    """
    out, level = [], 7
    for i in range(n - 1, 0, -1):
        if heads is not None:
            got = heads.get(i)
        else:
            m = re.match(r"(#{1,6})\s", lines[i - 1])
            got = len(m.group(1)) if m else None
        if got and got < level:
            out.append(i)
            level = got
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


def fixed_lines(lines: list[str], n: int) -> set[int]:
    """n행 앞뒤 `FIXED_LINES` 줄 — 끝이 블록 안에 걸리면 `FIXED_SNAP` 줄 안에서 블록 끝까지 넓힌다.

    표를 넓혀도 못 담으면 표 머리 두 줄을 따로 싣는다 — 머리 없는 표 행은 칸이 무엇인지 안 읽힌다.
    """
    lo, hi = max(1, n - FIXED_LINES), min(len(lines), n + FIXED_LINES)
    extra: set[int] = set()
    for a, b in blocks(lines):
        if a < lo <= b and lo - a <= FIXED_SNAP:
            lo = a
        if a <= hi < b and b - hi <= FIXED_SNAP:
            hi = b
    for a, b in blocks(lines):
        if a < lo <= b and all(l.lstrip().startswith("|") for l in lines[a - 1:b]):
            extra |= set(range(a, min(b, a + 1) + 1))
    return set(range(lo, hi + 1)) | extra


def window_lines(lines: list[str], n: int, mode: str, html_heads: dict[int, int] | None = None) -> set[int] | None:
    """n행을 판정할 때 보낼 줄 — 구조 단위를 담지 못하면 None(chunk 로 복귀). HTML 은 `html_heads` 로 제목을 안다."""
    heads = set(heading_chain(lines, n, html_heads))
    if mode == "fixed":
        return fixed_lines(lines, n) | heads
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


#: 창 밖에서 함께 보낼 줄 — 대상 줄과 낱말 두 글자 묶음과 수치가 가장 많이 겹치는 줄. (2026-11-02) 요약 줄의 「낮음」을
#: 재판정하며 38줄 떨어진 신뢰구간을 못 보고 「문서만으로 확인할 수 없음」을 냈다. 그 README 에서 이 점수로 상위
#: 여섯 줄에 근거 줄 셋(106~108행)이 들었다.
SUPPORT_MAX = 6
SUPPORT_MIN = 0.18
_NUM = re.compile(r"\d+(?:\.\d+)+%?|\d+(?:,\d{3})+|\d+%")
SUPPORT_NOTE = ("\n\n아래는 생략된 곳에서 대상 줄과 같은 낱말이나 수치가 많이 나오는 줄이다. 대상 줄의 근거나 정의가 "
                "여기 있으면 그것으로 판단한다. 이 줄들은 지적하지 않는다.\n")
#: HTML 은 보이는 글만 판정기에 가서 링크가 안 보인다 — 링크가 걸린 「(영업기회 크기별 표)」를 「참조는 링크로 걸기」로
#: 다섯 번 연속 짚었다(2026-11-02 현장 보고). 줄 해시는 보이는 글로 매기므로 글에는 손대지 않고 목록만 덧붙인다
LINK_NOTE = "\n\n이 조각에서 링크가 걸린 글(HTML 원본의 <a href>) — 여기 있는 글은 이미 링크로 걸려 있다.\n"
LINKS_MAX = 40


def html_links(path: Path) -> list[tuple[str, str]]:
    """HTML 의 링크 — (보이는 글, 주소). 글이 빈 링크와 스크립트 안은 뺀다."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out, self.stack, self.skip = [], [], 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip += 1
            elif tag == "a" and dict(attrs).get("href"):
                self.stack.append([dict(attrs)["href"], ""])

        def handle_endtag(self, tag):
            if tag in ("script", "style") and self.skip:
                self.skip -= 1
            elif tag == "a" and self.stack:
                href, text = self.stack.pop()
                text = " ".join(text.split())
                if text:
                    self.out.append((text, href))

        def handle_data(self, data):
            if not self.skip:
                for a in self.stack:
                    a[1] += data
    p = P()
    try:
        p.feed(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    return p.out


def link_note(links: list[tuple[str, str]], seen: list[str]) -> str:
    """조각에 든 줄에 나오는 링크만 — 없으면 빈 글."""
    body = "\n".join(seen)
    got = list(dict.fromkeys(f"「{t[:60]}」 → {h[:80]}" for t, h in links if t in body))[:LINKS_MAX]
    return LINK_NOTE + "\n".join(got) if got else ""


def _grams(s: str) -> collections.Counter:
    out: collections.Counter = collections.Counter()
    s = s.replace("−", "-")
    for w in re.findall(r"[가-힣]+|[A-Za-z][\w-]*", s):
        out.update(w[i:i + 2] for i in range(len(w) - 1))
    for n in _NUM.findall(s):
        out["#" + n] += 2
    return out


def support_lines(lines: list[str], want: list[int], keep: set[int]) -> list[int]:
    """창 밖 줄 가운데 대상 줄과 가장 닮은 줄 — 문서 안 희소도로 무게를 단 두 글자 묶음 코사인."""
    grams = [_grams(l) for l in lines]
    df = collections.Counter(g for c in grams for g in c)
    total = len(lines)

    def vec(c):
        return {g: v * math.log(total / df[g]) for g, v in c.items()}

    def cos(a, b):
        dot = sum(v * b.get(g, 0.0) for g, v in a.items())
        na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0
    cands = [i for i in range(1, total + 1) if i not in keep and coverage.HANGUL.search(lines[i - 1])]
    best: dict[int, float] = {}
    for n in want:
        t = vec(grams[n - 1])
        for i in cands:
            s = cos(t, vec(grams[i - 1]))
            if s >= SUPPORT_MIN:
                best[i] = max(best.get(i, 0.0), s)
    return sorted(sorted(best, key=lambda i: -best[i])[:SUPPORT_MAX])


#: 출력이 이만큼 넘으면 잘린 것으로 본다 — 호출 경로의 한도(크레딧 경로 16,000)에 닿으면 답이 끊긴다
TRUNCATED_OUTPUT = 15_900
#: 이보다 짧은 묶음은 더 나누지 않고 실패로 알린다
SPLIT_MIN_LINES = 20


def truncated(r: dict) -> bool:
    """답이 출력 한도에서 끊겼나 — 멈춘 까닭이 한도이거나, 출력이 한도 가까이 찼으면.

    지적을 몇 건 읽었어도 잘린 것으로 본다 — 끊긴 답에서 앞 행만 읽혀 나머지가 조용히 빠질 수 있다.
    한도가 없는 경로에서 정상으로 길게 나온 답도 나눠 다시 부르게 되지만, 그 값은 호출이 늘 뿐 빠지는 것은 없다.
    **구독 경로라고 밝힌 답은 멈춘 까닭만 본다** — 출력 길이 기준은 크레딧 경로의 16,000 한도에 맞춘 것이다. 구독
    경로에서는 같은 묶음이 17,000~22,000토큰으로 끝까지 나오고(멈춘 까닭 end_turn) 그것을 잘림으로 보아 나눠 다시
    부르느라 측정 한 회에 0.4~0.6달러(환산)를 더 썼다(2026-11-05).
    """
    out = int((r.get("usage") or {}).get("output_tokens") or 0)
    if r.get("stop_reason") == "max_tokens":
        return True
    return r.get("billing") != "subscription" and out >= TRUNCATED_OUTPUT


def split_piece(piece: dict) -> list[dict]:
    """잘린 묶음을 앞뒤 반으로 — 줄 번호와 대상 줄은 그대로 이어 간다. 너무 짧으면 빈 목록."""
    seen = piece["seen"]
    first = int(str(piece["label"]).split("-")[0])
    if len(seen) < SPLIT_MIN_LINES or piece.get("mode", "").startswith("window"):
        return []
    half = len(seen) // 2
    out = []
    for start, part in ((first, seen[:half]), (first + half, seen[half:])):
        mine = [n for n in piece.get("mine") or [] if start <= n < start + len(part)]
        if piece.get("mine") and not mine:
            continue
        out.append({"mine": mine, "document": numbered(part, start), "seen": part,
                    "label": f"{start}-{start + len(part) - 1}", "mode": f"{piece.get('mode', 'chunk')}←잘림"})
    return out


def parts_for(lines: list[str], want: set[int] | None, mode: str, path: Path,
              html_heads: dict[int, int] | None = None) -> list[dict]:
    """이번에 부를 조각 — {"mine": 대상 줄, "document": 프롬프트에 넣을 글, "seen": 판정기가 본 줄, "label", "mode"}.

    `html_heads` 는 HTML 의 제목 줄 — 안 주면 그 파일에서 읽는다(재생은 남겨 둔 것을 준다).
    HTML 이면 조각마다 그 안에 든 링크 목록을 붙인다(`link_note`).
    """
    pieces = _parts_for(lines, want, mode, path, html_heads)
    if path.suffix.lower() in coverage.HTML_SUFFIXES and path.is_file():
        links = html_links(path)
        for piece in pieces:
            piece["document"] += link_note(links, piece["seen"])
    return pieces


def _parts_for(lines: list[str], want: set[int] | None, mode: str, path: Path,
               html_heads: dict[int, int] | None = None) -> list[dict]:
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
    if not want:        # 지운 줄만 있는 판 등 — 창을 잡을 줄이 없다(2026-10-19 재생이 여기서 멈춤)
        return []
    html = path.suffix.lower() in coverage.HTML_SUFFIXES and mode == "fixed" and WINDOW_HTML
    if path.suffix.lower() not in WINDOWABLE and not html:
        return by_chunk(f"chunk←{mode}")
    if html and html_heads is None:
        html_heads = coverage.html_heads(path, lines)
    keep: set[int] = set()
    for n in sorted(want):
        got = window_lines(lines, n, mode, html_heads if html else None)
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
    # 창 밖 근거 줄은 글에만 붙이고 「판정기가 본 줄」에는 넣지 않는다 — 대상 아닌 먼 줄이 판정을 마친 것으로 잡히면
    # 게이트가 그 줄의 새 글을 안 막는다
    support = support_lines(lines, sorted(want), keep)
    document = excerpt(lines, ordered) + (
        SUPPORT_NOTE + "\n".join(f"{n:>3} | {lines[n - 1]}" for n in support) if support else "")
    return [{"mine": sorted(want), "document": document, "seen": [lines[n - 1] for n in ordered],
             "label": ",".join(runs), "mode": mode}]


#: 시스템 프롬프트 재사용(2026-10-20) — 시스템 프롬프트 끝의 「사용자가 이미 답한 것」은 어느 문서든 사람 확인에
#: 답하면 바뀌어, 다음 호출이 캐시된 시스템 프롬프트(약 16k 토큰)를 처음부터 다시 쓴다. 세션 흉내 6회 중 4회에서 0회차
#: 직후 답 하나로 첫 재판정이 캐시를 하나도 못 읽었다(호출당 약 0.08~0.10달러 더 · 실행 하나의 약 10%). 그래서 재판정은
#: 그 문서의 직전 호출이 쓴 시스템 프롬프트를 캐시 유지 시간 안쪽이면 그대로 쓰고, 그 뒤 받은 답은 사용자 메시지 끝에
#: 붙인다. 대상 줄에 받은 답은 원래 사용자 메시지에 실린다(`decided_on`).
#: (같은 날 앞 묶음을 캐시에 두고 바뀐 줄만 붙이는 prefix 문맥도 쟀으나 세션 흉내 3회 대 3회에서 이득이 없어 걷어냈다 —
#:  캐시 항목은 호출의 마지막 블록 끝에만 생겨 앞 묶음이 전체 판정에서만 나오고, 큰 재판정은 기준 판 글이 몫을 차지했다.)
SYSTEM_FRESH = 240          # 초 — 직전 호출이 이보다 전이면 캐시가 식었을 수 있어 지금 것으로 새로 쓴다
SYSTEM_KEEP = 3600          # 초 — 이보다 오래된 기록은 지운다(사용자 답 원문이 들어 있다)


def _system_file(key: str) -> Path:
    """문서별 직전 시스템 프롬프트 — 판정 기록 옆. ⛔ 사용자 답 원문이 들어간다 — 이 PC 밖으로 내보내지 않는다."""
    return LOG.parent / "korean-system" / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:16] + ".json")


def save_system(key: str, system: str, rules_sha: str, made: float, used: float) -> None:
    """이 문서의 직전 호출이 쓴 시스템 프롬프트 — `made` 는 그 프롬프트의 사용자 답을 읽은 시각.

    못 쓰면(Codex 샌드박스 등) 건너뛴다 — 다음 재판정이 캐시를 덜 읽을 뿐이고, 여기서 죽으면 받은 판정과
    그 기록 줄을 잃는다.
    """
    p = _system_file(key)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        for old in p.parent.glob("*.json"):
            if old != p and old.stat().st_mtime < time.time() - SYSTEM_KEEP:
                old.unlink(missing_ok=True)
        p.write_text(json.dumps({"system": system, "rules": rules_sha, "made": made, "used": used},
                                ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def system_for(key: str, current: str, rules_sha: str) -> tuple[str, float] | None:
    """재판정에 다시 쓸 직전 시스템 프롬프트와 그 답 시각 — 없거나 · 식었거나 · 규칙이 바뀌었거나 · 같으면 None."""
    try:
        got = json.loads(_system_file(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if got.get("rules") != rules_sha or time.time() - float(got.get("used") or 0) > SYSTEM_FRESH \
            or got.get("system") == current:
        return None
    return got["system"], float(got["made"])


def new_answers(since: float) -> str:
    """`since` 뒤에 받은 사람 확인 답 — 다시 쓰는 시스템 프롬프트에 없는 것."""
    rows = [d for d in load_decisions() if float(d.get("when") or 0) > since][-PROMPT_ANSWERS:]
    if not rows:
        return ""
    return ("\n\n사람 확인에 사용자가 새로 답한 것이다(위 「사용자가 이미 답한 것」 뒤에 받음). 같은 갈래 · 같은 경우는 "
            "이 답을 따른다.\n"
            + "\n".join(f"- [{d.get('category')}] 「{d.get('phrase')}」 · 판정기 제안 「{d.get('fix')}」 · "
                        f"사용자: {d.get('answer')}" for d in rows))


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


#: 글자 그대로 넣을 수 없는 수정안 — 하위 항목 표시, 자리 표시, 작성자가 채울 괄호 지시.
#   (2026-11-11 AI 말투 시연) 「바뀐 업무 방식(구체적으로 무엇이 바뀌었는지 기재)」와 「미완료 ↵ 시험 데이터 …」가
#   「고침」 답과 재현 일감의 반영으로 문서에 글자 그대로 들어갔다. 세 곳이 따로 거르던 것을 `literal_fix` 하나로 모음.
NOT_LITERAL = re.compile(r"↵|○○|[(\[][^()\[\]\n]*?(?:기재|기입|작성 필요|작성할 것|입력 필요|채울 것|채워 넣|적을 것|"
                         r"넣을 것|확인 필요|확인 후 수정)[^()\[\]\n]*?[)\]]")


def literal_fix(fix: str) -> bool:
    """수정안을 짚은 표현 자리에 글자 그대로 넣을 수 있나 — 지움 표시(「(문장 삭제)」), 여러 줄, 지시와 자리 표시는 아님."""
    return bool(fix) and not fix.startswith("(") and "\n" not in fix and not NOT_LITERAL.search(fix)


def edited_by_answer(line: str, asks: list[dict]) -> str | None:
    """「고침」 답 — 물은 줄에 판정기 수정안을 그대로 넣은 글. 글자로 넣을 수 없는 수정안이 있으면 None."""
    out = line
    for a in asks:
        if a.get("category") == "재판정 상한":
            continue                # 줄 전체를 짚은 것 — 같은 줄의 다른 지적에 대한 답이 곧 이 줄의 답이다
        phrase, fix = str(a.get("phrase") or ""), str(a.get("fix") or "")
        if not phrase or not literal_fix(fix) or phrase not in out:
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
                    text: str | None = None, items: list[dict] | None = None) -> int:
    """사용자가 표에 적은 답을 그 줄의 지적마다 남긴다 — 남긴 수. 같은 답을 두 번 적지 않는다.

    ⛔ 지적을 닫지 않는다 — 닫는 것은 `answer`(그대로만)다. 이것은 다음 판정이 따를 기록이다.
    `text` 는 사용자가 본 줄 — 그 줄을 고친 뒤의 판정에 이 답을 싣고(`decided_on`), 답대로 고친 줄을
    확정할 때(`answered_origin`) 글자로 잇는다.
    `items` 를 주면 그 줄의 사람 확인 전부 대신 그 지적에만 단다 — 검토 화면은 지적 하나씩 답을 받는다.
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
    for ask in asks_on(path, line_key) if items is None else items:
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


def why_changed(path: Path, only: int | None = None) -> list[dict]:
    """이 문서에 판정기가 낸 지적과 지금 글에서의 처리 — 모델을 부르지 않고 판정 기록만 읽는다.

    (2026-11-11 사용자 「이유 표시하는건 기본으로 넣지 않아도 AI한테 요청하면 해줄텐데 구현으로 만들지 말고 명령으로
    두는건 쉽지 않나?」) 「왜 고쳤나」를 물으면 세션이 이 명령으로 답한다. 판정 기록의 줄 번호는 그 회차 판의 번호라
    지금 글과 안 맞는다 — 수정안이 글자로 든 줄(반영), 짚은 표현이 남은 줄(남음), 지적한 줄과 가장 닮은 줄(다르게
    고침) 순으로 찾는다.
    """
    key = coverage.doc_key(path)
    lines = read_doc(path).splitlines()
    rows = sorted((r for r in coverage._rows(key, LOG, None, fresh=False) if r.get("ok")),
                  key=lambda r: float(r.get("when") or 0))
    dismissed = {}
    for d in coverage._rows(key, coverage.DISMISSALS, None, fresh=False):
        dismissed[str(d.get("phrase") or "")] = f"받지 않음({d.get('reason') or ''})"
    out, seen = [], set()
    for r in rows:
        for kind in ("fixes", "asks"):
            for f in r.get(kind) or []:
                if f.get("category") == "재판정 상한":
                    continue
                phrase, fix = str(f.get("phrase") or ""), str(f.get("fix") or "")
                mark = (f.get("category"), phrase, fix)
                if mark in seen:
                    continue
                seen.add(mark)
                plain_fix, plain_phrase = coverage._plain(fix), coverage._plain(phrase)
                n, status = None, "지금 글에 없음"
                if noop_fix(f) and any(plain_phrase in coverage._plain(l) for l in lines):
                    n = next(i for i, l in enumerate(lines, 1) if plain_phrase in coverage._plain(l))
                    status = "고칠 것 없음(수정안이 원문과 같음)"
                elif literal_fix(fix) and any(plain_fix in coverage._plain(l) for l in lines):
                    n = next(i for i, l in enumerate(lines, 1) if plain_fix in coverage._plain(l))
                    status = "반영"
                elif plain_phrase and any(plain_phrase in coverage._plain(l) for l in lines):
                    n = next(i for i, l in enumerate(lines, 1) if plain_phrase in coverage._plain(l))
                    status = dismissed.get(phrase) or ("사람 확인" if kind == "asks" else "안 고침")
                else:
                    text = str(f.get("text") or phrase)
                    best = max(((difflib.SequenceMatcher(None, text, l).ratio(), i) for i, l in enumerate(lines, 1)
                                if l.strip()), default=(0, None))
                    if best[0] >= 0.5:
                        n, status = best[1], "다르게 고침"
                if only is not None and n != only:
                    continue
                out.append({"line": n, "status": status, "category": f.get("category"), "phrase": phrase,
                            "fix": fix, "why": f.get("why") or "", "at": r.get("at")})
    return sorted(out, key=lambda e: (e["line"] is None, e["line"] or 0))


def show_why(path: Path, only: int | None = None) -> int:
    got = why_changed(path, only)
    where = f" {only}행" if only is not None else ""
    if not got:
        print(f"  {path.name}{where} — 판정 기록에 지적이 없습니다(판정 전이거나 지적 없이 통과)")
        return 0
    print(f"  {path.name}{where} — 판정기가 낸 지적 {len(got)}건(판정 기록 기준 · 모델 안 부름)")
    for e in got:
        at = f"{e['line']:>4}행" if e["line"] else "   — "
        fix = f" → 「{e['fix']}」" if e["fix"] else " → 지움"
        why = f" — {e['why']}" if e["why"] else ""
        print(f"  {at}  [{e['category']}] 「{e['phrase']}」{fix} · {e['status']}{why}")
    print("  1층 규칙 검사 지적은 기록하지 않음 — 고치기 전 판에 doc-style-check.py 를 다시 돌려 봄")
    return 0


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
        new = [] if tag else coverage.new_info(str(fx.get("fix") or ""), "\n".join(lines))
        if new:
            # 세션이 이 목록을 보고 직접 고치는 길에도 같은 표시를 단다 — 검토 화면만 막으면 이 길로 지어낸 수가
            # 들어간다(2026-11-02 · 판정기 지적을 그대로 반영한 문서가 초안에 진 까닭 1위가 「원문에 없던 값」)
            print(f"         [새 정보] 수정안에 원문에 없는 정보가 있음: {', '.join(new)} — 그대로 넣지 말고 "
                  "원자료나 작성자에게 확인한 뒤 고침")
        if tag and coverage._plain(str(fx.get("phrase") or "")) not in coverage._plain(lines[n - 1]):
            # 고쳐서 표현이 사라졌는데도 남은 까닭을 알린다 — 「이미 고쳤는데 열려 있다」로 읽혔다(2026-11-02 현장 보고)
            print(f"         짚은 표현은 고쳐서 없어졌지만 사실 확인 지적은 고쳐도 닫히지 않음 — 지금 {n}행의 사실을 "
                  "확인했으면 「확인함」, 확인할 수 없으면 --escalate")
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
        text = sheet.read_text(encoding="utf-8")
        keys, answers = ask_sheet.parse(text)
    except (OSError, ValueError) as e:
        print(f"⛔ {e}")
        return 2
    said: dict[str, str] = {}
    if replies:
        try:
            said = ask_sheet.parse_replies(replies, ask_sheet.opinions(text))
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
            _kiwi = kiwipiepy._korean_qa_shared = kiwipiepy.Kiwi(load_multi_dict=False)  # 검사기와 같은 설정
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
    if fix and not fix.startswith("(") and NOT_LITERAL.search(fix):
        notes.append("고친 말이 그대로 넣을 글이 아님(하위 항목 표시, 자리 표시, 작성자가 채울 지시) — "
                     "「고침」으로 답해도 자동으로 안 넣음 · 직접 고침")
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
    import importlib.util
    if importlib.util.find_spec("llm_playbook") is None:
        # 공개판을 받은 PC — 저장소 안의 최소 호출부(Claude 만)로 부를 수 있으면 Claude(`layer2_client`)
        import layer2_client
        return "claude" if layer2_client.available()[0] else None
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
    except ImportError:
        # `llm_playbook` 이 없는 PC(공개판) — 저장소 안의 최소 호출부로 Claude 를 부른다(`layer2_client`)
        import layer2_client
        if which != "claude" or not layer2_client.available()[0]:
            return None
        return layer2_client.call_messages, layer2_client.parse_json_from_text
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
        # 사다리는 멈춘 까닭과 과금 경로를 돌려주지 않는다 — 잘림 판정(`truncated`)이 그 둘을 봐야 해서 따로 들고 나온다
        raw: dict = {}

        def adapter(_alias, system_, user_, timeout_, _effort, max_tokens_, **_):
            r = call(model=model, system=system_, user=user_, max_tokens=max_tokens_, timeout=timeout_, **kw)
            raw.update({k: r[k] for k in ("stop_reason", "billing") if r.get(k)})
            return r.get("text") or "", r.get("model") or model, {"cost_usd": r.get("cost_usd"),
                                                                    "usage": r.get("usage")}
        # 등급은 칸을 고르는 데만 쓴다 — 실제 모델은 위 `model` 이고 칸 별칭은 안 쓴다. 다만 칸의 별칭으로 사용량
        # 보류(reserve · astra 칸만 GPT 5시간 사용률을 봄)를 가르므로, 부를 모델이 든 등급의 칸을 고른다 — 첫 등급을
        # 고르면 sol-high 를 부르면서 astra 칸으로 막혔다(2026-10-20 llm-playbook c4ded67 뒤 시험이 깨짐)
        tier = model if lp_models.tier_of(model) else next(iter(lp_models.tiers()))
        r = ask(tier, user, system=system, vendors=(which,), ladder="review",
                max_tokens=max_tokens,
                timeout=timeout, label="2층 판정", adapters={which: adapter}, ready=lambda _b: (True, ""))
        if not r["ok"]:
            until = r.get("until")
            when = time.strftime(" · %m-%d %H:%M 풀림", time.localtime(until)) if until else ""
            why = "; ".join(f"{s['backend']} 막힘" for s in r.get("skipped") or [] if s.get("why") == "blocked")
            why = why or "; ".join(str(a.get("why")) for a in r.get("attempts") or [])
            raise RuntimeError(f"{which} {r.get('outcome')}{when} — {why}"[:300])
        return {"text": r["text"], "model": r.get("model") or model,
                "cost_usd": r.get("cost_usd") if which == "claude" else None, "usage": r.get("usage"), **raw}
    return call_review, parse


def input_total(row: dict) -> int:
    """입력 토큰 전부 — 캐시에 쓴 것·읽은 것까지."""
    return sum(int(row.get(k) or 0) for k in ("input_tokens", "cache_write", "cache_read"))


def log_call(row: dict) -> None:
    """판정 기록에 한 줄 — 못 쓰면 임시 폴더에 대신 적고 알린다(`coverage.fallback_log`).

    ⛔ 예외를 그대로 올리면 안 된다 — 실패 줄을 적다 나면 원래 실패 사유가 권한 오류로 덮이고 줄도 사라진다
       (Codex 샌드박스 · 2026-10-14~20 실패 0건으로 남음). 쓸 수 있을 때 대신 적은 줄을 먼저 합친다.
    """
    line = json.dumps(row, ensure_ascii=False) + "\n"
    spare = coverage.fallback_log(LOG)
    merging = spare.is_file()
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        earlier = merge_spare(spare) if merging else ""
        with LOG.open("a", encoding="utf-8", newline="\n") as f:
            f.write(earlier + line)
    except OSError as e:
        try:
            with spare.open("a", encoding="utf-8", newline="\n") as f:
                f.write(line)
        except OSError as e2:
            print(f"⚠️ 판정 기록을 못 썼습니다 — {LOG}: {type(e).__name__} · 대신 적을 곳 {spare}: {type(e2).__name__}")
            return
        print(f"⚠️ 판정 기록을 못 써({type(e).__name__}) {spare} 에 대신 적었습니다 — 다음에 기록을 쓸 수 있을 때 합칩니다")
        return
    if merging:
        try:
            spare.unlink(missing_ok=True)
        except OSError:
            pass    # 남아도 다음에 합칠 때 이미 있는 줄은 건너뛴다


def merge_spare(spare: Path) -> str:
    """대신 적은 줄 중 본 기록에 아직 없는 것 — 합치다 지우기 전에 끊겨도 두 번 들어가지 않게 줄 글자로 가린다."""
    have = set(LOG.read_text(encoding="utf-8").splitlines()) if LOG.is_file() else set()
    new = [l for l in dict.fromkeys(spare.read_text(encoding="utf-8").splitlines()) if l.strip() and l not in have]
    return "".join(l + "\n" for l in new)


#: 재판정 입력을 남기는 날수 — 문맥 방식을 같은 입력으로 재생해 지적 차이를 보려고 둔다(외부 검토 2026-10-16)
REPLAY_DAYS = 30


def replay_dir() -> Path:
    """판정 기록 옆 폴더 — 시험 · 재현 도구가 기록 경로를 돌리면 함께 따라간다(실사용 저장소에 안 섞인다).

    ⛔ 사내 문서 원문이 들어간다 — 이 PC 밖으로 내보내지 않고 저장소에 넣지 않는다.
    """
    return LOG.parent / "korean-replay"


def rejudge_user(piece: dict, info: dict, closed: list, decided: list, instructed: list = (), extra: str = "",
                 evidenced: list = ()) -> str:
    """재판정 한 조각의 사용자 메시지 — 판정과 재생(`replay_rejudge.py`)이 같이 쓴다(같은 입력이어야 견준다)."""
    mine = piece["mine"]
    plain = {n for n in mine if not info[n].get("anchor")}
    windowed = piece["mode"] in ("fixed", "block")
    rest = ("\n\n이번에는 아래 줄만 점검한다 — 나머지 줄은 문맥으로만 읽고 지적하지 않는다.\n"
            + ", ".join(map(str, mine))
            + before_after(mine, info, [(n, r) for n, r in closed if n in plain],
                           [(n, d) for n, d in decided if n in plain],
                           [(n, r) for n, r in instructed if n in plain],
                           [(n, r) for n, r in evidenced if n in plain])
            + extra)        # 다시 쓰는 시스템 프롬프트 뒤에 받은 답(`new_answers`)
    return probe.USER.format(document=piece["document"]) + (WINDOW_NOTE if windowed else "") + rest


def save_case(path: Path, key: str, text: str, want: set[int], anchors: dict, base, info: dict,
              rules_sha: str, system: str, model: str, context: str, closed: list, decided: list,
              instructed: list = (), heads: dict | None = None, decisions_text: str | None = None,
              extra: str = "", evidenced: list = ()) -> None:
    """재판정 한 번의 입력 — 그때 문서 · 대상 · 기준 판 · 계보 · 닫은 지적 · 사용자 답 · 시스템 프롬프트.

    못 쓰면(Codex 샌드박스 등) 알리고 건너뛴다 — 재생 자료 하나를 잃을 뿐이고, 여기서 죽으면 모델을 부르기도
    전에 재판정이 끝난다.
    """
    folder = replay_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - REPLAY_DAYS * 86400
        for old in folder.glob("*.json"):
            if old.stat().st_mtime < cutoff:
                old.unlink(missing_ok=True)
    except OSError as e:
        print(f"⚠️ 재생 입력을 못 써({type(e).__name__}) 건너뜁니다 — {folder}")
        return
    case = {"at": datetime.now().isoformat(timespec="seconds"), "doc": str(path), "key": key, "text": text,
            "targets": sorted(want), "anchors": {str(n): g for n, g in anchors.items()}, "base": base,
            "info": {str(n): v for n, v in info.items()}, "rules": rules_sha, "model": model, "context": context,
            "system_sha": hashlib.sha256(system.encode("utf-8")).hexdigest()[:12],
            "decisions_prompt": decisions_prompt(load_decisions()) if decisions_text is None else decisions_text,
            "extra": extra,
            "closed": [[n, r] for n, r in closed], "decided": [[n, d] for n, d in decided],
            "instructed": [[n, r] for n, r in instructed],
            "evidenced": [[n, r] for n, r in evidenced],
            # HTML 제목 줄 — 재생 때 파일이 바뀌어 있어도 같은 창을 잡게
            "heads": {str(n): v for n, v in (heads or {}).items()}}
    name = f"{datetime.now():%Y%m%d-%H%M%S}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]}.json"
    try:
        (folder / name).write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        print(f"⚠️ 재생 입력을 못 써({type(e).__name__}) 건너뜁니다 — {folder}")


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
#: ⛔ 단 상한을 넘긴 판정이 그 줄에서 고칠 것을 못 찾았으면 사람에게 안 올리고 지금 문장으로 둔다 — 그 판정도
#:   판정기가 줄을 다시 읽은 결과라, 처음 판정에서 지적이 없던 줄과 같게 다룬다. 수정안이 원문과 글자가 같은
#:   지적(「7회, 112초」→「7회, 112초」)은 고칠 것이 아니다 — 확인할 사실이 있으면 세션이 자료로 닫는다.
#:   (2026-11-11 사용자 「뭔소리야. 지금 표현이 나은데, 이걸 왜 애스컬레이션한거지?」 · 멘토링 문서에서 사람
#:   확인 8줄이 전부 이 까닭이었고 마지막 판정에 새 고칠 지적이 없었음 · chungbuk 세션이 전달)
REJUDGE_CAP = 3


def noop_fix(item: dict) -> bool:
    """수정안이 짚은 표현과 글자가 같은 지적 — 고칠 것이 없다(굵게와 빈칸 차이는 같다고 봄)."""
    plain = lambda s: re.sub(r"\s+", "", coverage._plain(str(s or "")))  # noqa: E731
    return bool(item.get("phrase")) and plain(item.get("fix")) == plain(item.get("phrase"))
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
    found: dict[int, tuple] = {}
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
        pred, chain = None, None
        if near:
            best, best_sim = max(near, key=lambda x: x[1])
            chain = best.get("root") or best["text"]
            pred = max(((e, s) for e, s in near if (e.get("root") or e["text"]) == chain),
                       key=lambda x: (int(x[0].get("round") or 1), x[1]))[0]
            # 기준 판에 그 계보 밖의 더 비슷한 줄이 있으면 앞선 판정은 다른 줄의 것이다
            if cand is not None and cand != chain and coverage._similar(text, cand) > best_sim:
                pred = None
        found[n] = (pred, chain if pred is not None else None, cand)
    # ⛔ 한 계보(또는 기준 판 줄)를 여러 줄이 함께 잡으면 나눈 줄만 이어 받는다 · 그 줄이 지금 글에 그대로 남았으면
    #    아무도 못 받는다(2026-11-03 git 밖 Marp 덱 — 표를 다시 짜자 새 행 넷이 같은 옛 행의 판정 횟수와 기준 판을
    #    함께 물려받아 곧장 사람 확인에 올랐다 · `coverage.heirs`). 계보는 마지막 판 글과 대조한다 — 고치기 직전의
    #    글이고, 줄마다 가장 비슷한 판으로 묶으면 같은 계보의 다른 판을 잡은 새 줄끼리 서로를 못 본다(기록 재생).
    #    앞선 판정 계보를 먼저 가르고, 못 받은 줄은 기준 판 줄로 가른다.
    latest = {}
    for e in prev:
        latest[e.get("root") or e["text"]] = e["text"]
    where: dict[str, list[int]] = {}
    for i, l in enumerate(lines, 1):
        k = coverage.line_key(l)
        if k:
            where.setdefault(k, []).append(i)

    def settle(parent_of) -> set[int]:
        groups: dict[str, list[int]] = {}
        for n in targets:
            p = parent_of(n)
            if p is not None:
                groups.setdefault(p, []).append(n)
        lost = set()
        for p, ns in groups.items():
            held = any(m not in ns for m in where.get(coverage.line_key(p) or "", []))
            ns.sort(key=lambda n: -coverage._similar(lines[n - 1], p))
            lost |= {n for n, ok in zip(ns, coverage.heirs(p, [lines[n - 1] for n in ns], held)) if not ok}
        return lost

    orphans = settle(lambda n: latest[found[n][1]] if found[n][1] is not None else None)
    unrooted = settle(lambda n: found[n][2] if found[n][0] is None or n in orphans else None)
    out = {}
    for n in targets:
        pred, _, cand = found[n]
        if pred is not None and n not in orphans:
            info = {"round": int(pred.get("round") or 1) + 1, "root": pred.get("root") or pred["text"]}
        else:
            info = {"round": 1, "root": None if n in unrooted else cand}
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


#: 기준 판에 붙여 보내는 앞선 판정의 지적 — 줄마다 이만큼까지. 규칙 이름은 안 싣는다 — 재생(2026-10-20 · 25건 두 번씩)에서
#: 대상 20줄 미만 재판정의 환산 비용이 14% 늘어(쓰기 호출당 약 1,100토큰) 판정기가 실제로 쓴 표현과 고친 말만 남겼다.
#: ⚠️ 그 14% 는 대부분 순서 효과였다 — 늘 첨부 쪽을 먼저 불렀고, 캐시가 찬 2회차는 0.401 대 0.401달러, 캐시와 뗀 비용은
#: +2.5%(2026-10-21 회고 검토 · `replay_rejudge.py rescore`). 둘로 줄인 판은 정확도를 재지 않았다 — 재판정 함정
#: (`bench_loop.py --traps`)으로 잰 뒤에 이 값을 다시 정한다.
ROOT_FINDINGS_PER_LINE = 2


def root_findings(key: str, info: dict[int, dict], before: float | None = None, log: Path | None = None) -> None:
    """기준 판 줄에 앞서 낸 고칠 지적을 `info[n]["root_found"]` 에 붙인다 — 「왜 고쳤나」를 재판정에 알린다.

    ⛔ 기준 판만 보내면 판정기가 그것을 정답처럼 읽고 「뜻이 바뀌었다」며 지적됐던 표현으로 되돌리라고 냈다
       (2026-10-19 재생 · 사용자가 짚은 헛짚음 다섯 중 대부분이 「자동 수리」 · 「원문을 그대로 훑어」로 되돌림).
       사용자 지시를 알려 주자 지시 안 수정을 짚은 줄이 6→0 이 된 것과 같은 원리다(외부 검토 Argon · 10-20).
    `before` 가 있으면 그 시각 앞의 판정만 본다(재생이 그때 입력을 되살릴 때). `log` 는 판정 기록(기본 `LOG`).
    근처에서 지운 줄의 고칠 지적은 `info[n]["gone_found"]` 에 따로 붙인다 — 줄을 크게 고치면 기준 판과 이어지지
    않고 옛 줄이 지운 줄로 잡힌다. 재판정 입력에는 안 싣고 고친 줄에 남은 표현을 대조하는 데만 쓴다(`kept_flagged`).
    """
    by_key: dict[str, list[int]] = {}
    gone_key: dict[str, list[int]] = {}
    for n, v in info.items():
        if v.get("root") and not v.get("anchor"):
            by_key.setdefault(coverage.line_key(v["root"]), []).append(n)
        if not v.get("anchor"):
            for k in v.get("deleted_keys") or []:
                if k:
                    gone_key.setdefault(k, []).append(n)
    if not by_key and not gone_key:
        return
    found: dict[str, list[dict]] = {}
    for row in coverage._rows(key, log or LOG, None, fresh=False):
        if not row.get("ok") or (before is not None and float(row.get("when") or 0) >= before):
            continue
        for fx in row.get("fixes") or []:
            k = fx.get("line_key")
            phrase = str(fx.get("phrase") or "").strip()
            if (k in by_key or k in gone_key) and phrase \
                    and phrase not in {f["phrase"] for f in found.get(k, [])}:
                found.setdefault(k, []).append({"phrase": phrase, "fix": fx.get("fix") or "",
                                                "category": fx.get("category") or "", "line_key": k,
                                                "text": fx.get("text") or ""})
    for k, ns in by_key.items():
        for n in ns:
            if found.get(k):
                info[n]["root_found"] = found[k][:ROOT_FINDINGS_PER_LINE]
    for k, ns in gone_key.items():
        for n in ns:
            if found.get(k):
                info[n].setdefault("gone_found", []).extend(found[k][:ROOT_FINDINGS_PER_LINE])


def revived(item: dict, info: dict) -> str | None:
    """수정안이 기준 판에서 지적됐던 표현을 되살리면 그 표현 — 아니면 None."""
    fix = str(item.get("fix") or "")
    for f in info.get("root_found") or []:
        p = f["phrase"]
        if len(p) >= 2 and p in fix and p not in str(item.get("phrase") or ""):
            return p
    return None


_GATE: list = []


def internal_doc(path: Path) -> bool:
    """작성자만 보는 저장소 내부 문서인가 — 판정하지 않을 문서.

    ⛔ 2026-11-05 세션이 발행 대상이 아닌 내부 기록(decisions-pending, runs/ 측정 기록)을 손으로 판정하고 지적을
       조금씩 고쳐 다시 판정하다 재판정 상한을 넘겨 사용자에게 사람 확인을 넘겼다. 사용자 「내가 직접 보거나
       공유하거나 문서화하거나 발표용으로 만들거나 게시하는게 아닌 문서를 쓸데없이 검사 안하도록 뭔가 장치를」.
       훅은 이미 그 문서를 작성자용(`me`)으로 갈랐는데 판정기는 그것을 안 봤다.
    가르는 것은 발행 게이트 훅과 같은 판정이다(`hooks/doc-style-gate.py` 의 `audience`). 셋 다 맞을 때만 내부 문서다.
    - 이 PC 개인 목록이 `check_scope = "shared"`(작성자가 고른 개인 설정 — 다른 설치본은 그대로)
    - 문서가 `[publish]` 대상을 밝힌 저장소 안에 있고 그 대상이 아님
    - 머리말 `audience: share`(HTML 은 meta)가 없음
    저장소 밖 파일(아티팩트 원고 등)은 해당하지 않는다 — 발행 직전 검사가 판정을 요구한다. 못 가르면 판정한다.
    """
    try:
        if not _GATE:
            import importlib.util
            spec = importlib.util.spec_from_file_location("korean_qa_gate", HERE.parent / "hooks" / "doc-style-gate.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _GATE.append(module)
        gate = _GATE[0]
        if gate.check_scope() != "shared" or gate.audience(str(path)) != "me":
            return False
        top = gate._git(path.resolve().parent, "rev-parse", "--show-toplevel")
        if top.returncode != 0:
            return False
        conf = gate.publish_config(Path(top.stdout.decode("utf-8", "replace").strip()))
        return isinstance(conf, dict) and bool(conf.get("targets"))
    except Exception:
        return False


def kept_stems(text: str) -> dict[str, str]:
    """어간 → 그 어간이 든 어절. 용언은 한 음절도, 명사와 부사는 두 음절부터(「빌드」의 「드」 같은 조각을 뺀다)."""
    _lemmas("")                         # 형태소 분석기를 검사기와 같은 한 벌로 띄운다
    out: dict[str, str] = {}
    for t in _kiwi.tokenize(text):
        if t.tag in FIX_TAGS and (t.tag in ("VV", "VA") or len(t.form) > 1):
            a = text.rfind(" ", 0, t.start) + 1
            b = text.find(" ", t.start + t.len)
            out.setdefault(f"{t.form}/{t.tag}", text[a:b if b >= 0 else len(text)])
    return out


def kept_flagged(lines: list[str], mine, info: dict, items, closed: list[dict],
                 freq: dict | None = None) -> list[dict]:
    """고친 줄에 기준 판에서 고치라고 한 표현이 그대로 있는데 이번 판정이 안 짚었으면 그 지적을 붙인다.

    ⛔ 판정 모델만 믿으면 놓친다 — 가성비 단계(재판정 Sonnet)가 짚힌 표현을 고친 줄에 다시 넣은 함정 둘
       (「공수 넣기」, 「훑어」와 「펜스」)을 세 번 중 두 번 놓쳤다(runs/judge-effort-levels-20261104).
       줄을 크게 고치면 발행 게이트도 다른 줄로 보아(`coverage.open_fixes` 의 글자 절반 기준) 놓친다.
       줄 이력은 판정기가 이미 알므로 글자로 대조한다. 모델을 부르지 않는다.
    두 가지를 본다.
    - **짚은 표현이 글자 그대로 남음** — 수정안이 그 표현을 품은 지적(「고르게」→「고르게 배치」처럼 덧붙이기만
      한 것)은 표현이 남는 것이 맞아 뺀다. 이 PC 실사용 재판정 2,899줄에서 14줄이 해당했다(2026-11-05).
    - **수정안이 뺀 드문 어간이 남음**(`freq` 가 있을 때) — 「훑어 펜스를 안 본」을 「훑어서 펜스를 보지 않은」으로
      바꿔 넣으면 글자로는 안 맞는다. 사람 업무 글에서 드문 어간(`RARE_FLOOR` 이하)만 본다 — 흔한 어간까지 보면
      실사용 2,899줄에서 103줄이 걸렸고 대부분 상관없는 줄이었다. 드문 어간만 보면 7줄이었다.
    받지 않음으로 닫은 표현(`closed` 의 같은 줄 이력)은 일부러 남긴 것이라 붙이지 않는다.
    """
    flagged = []
    for it in items:
        if isinstance(it, dict):
            p = str(it.get("phrase") or "")
            flagged.append((relocate(lines, it.get("line"), p), coverage._plain(p)))
    out = []
    for n in mine:
        v = info.get(n) or {}
        earlier = (v.get("root_found") or []) + (v.get("gone_found") or [])
        if v.get("anchor") or not earlier:
            continue
        line, seen = lines[n - 1], set()
        here = kept_stems(line) if freq is not None else {}

        def taken(word: str, f: dict) -> bool:
            """모델이 이미 짚었거나 받지 않음으로 닫은 표현인가."""
            w = coverage._plain(word)
            if w in seen or any(m == n and q and (w in q or q in w) for m, q in flagged):
                return True
            fp = coverage._plain(f["phrase"])
            return any(coverage._plain(str(r.get("phrase") or "")) == fp
                       and (r.get("line_key") == f.get("line_key")
                            or coverage._similar(str(r.get("text") or ""), line) >= coverage.SUCCESSOR)
                       for r in closed)

        for f in earlier:
            p, fix = coverage._plain(f["phrase"]), str(f.get("fix") or "")
            if len(p) >= 2 and p in coverage._plain(line) and p not in coverage._plain(fix):
                if not taken(f["phrase"], f):
                    seen.add(p)
                    out.append(_kept_item(n, f["phrase"], f, f["phrase"]))
                continue
            if not here:
                continue
            # 꼴로 견준다 — 같은 「민감」을 한 문장에서는 XR, 다른 문장에서는 NNG 로 나눠, 수정안에 그대로 있는 말을
            # 뺀 말로 보고 짚었다(2026-11-05 측정 v8 · 「가장 민감한 글에 듭니다」→「가장 민감한 문서에 속합니다」)
            gone = {s.split("/")[0] for s in kept_stems(f["phrase"])} - {s.split("/")[0] for s in kept_stems(fix)}
            # 원래 줄의 짚지 않은 부분에 이미 있던 어절은 뺀다 — 굵은 라벨 「헛짚음」이 「짚음」을 고치라는 지적에
            # 걸렸다(2026-11-05 측정 기록 README 89행)
            rest = coverage._plain(str(f.get("text") or "").replace(f["phrase"], " ", 1))
            for stem in sorted(s for s in here if s.split("/")[0] in gone):
                if coverage._plain(here[stem]) in rest:
                    continue
                if freq.get(stem, 0) <= RARE_FLOOR and not taken(here[stem], f):
                    seen.add(coverage._plain(here[stem]))
                    out.append(_kept_item(n, here[stem], f, stem.split("/")[0]))
    return out


def _kept_item(n: int, phrase: str, f: dict, what: str) -> dict:
    """`kept_flagged` 가 붙이는 고칠 지적 — 앞선 지적의 수정안을 그대로 보여 준다."""
    return {"line": n, "phrase": phrase, "fix": f.get("fix") or "", "decide": "fix", "kept": True,
            "category": f.get("category") or "고친 줄에 남은 표현",
            "why": f"앞선 판정이 「{f['phrase']}」을(를) 고치라고 했는데 고친 줄에 「{what}」이(가) 남음"
                   "(이번 판정이 짚지 않아 줄 이력으로 붙임)"}


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


def record_evidence(path: Path, n: int, note: str) -> str:
    """n행의 사실 주장을 자료로 확인하고 고쳤다고 적는다 — 근거는 경로와 그 파일 원문 인용, 또는 이 문서의 「N행」.

    (2026-11-02) 사람 확인 2건이 모두 문서 안이나 저장소 자료에 근거가 있는 줄이었다. 재판정은 대상 앞뒤 20줄만
    받아 38줄 떨어진 신뢰구간을 못 보고 「문서만으로 확인할 수 없음」을 냈다. 「확인함」 닫기는 짚인 뒤에 하나씩
    닫는 길이고, 이것은 고칠 때 근거를 함께 적어 재판정이 받게 하는 길이다. 규칙에 안 맞으면 ValueError.
    """
    note = note.strip()
    lines = read_doc(path).splitlines()
    if not 0 < n <= len(lines) or not coverage.line_key(lines[n - 1]):
        raise ValueError(f"{n}행은 한글이 든 줄이 아닙니다")
    quoted = any(QUOTE_AFTER.match(note, m.end()) for m in PATH_REF.finditer(note))
    if len(note) < NOTE_MIN or not (quoted or LINE_REF.search(note)):
        raise ValueError("--note 에 근거를 적습니다 — 「<경로> 「그 파일 원문」」 또는 이 문서의 「N행」")
    problems = evidence_problems(path, note, lines)
    if problems:
        raise ValueError(problems[0])
    row = {"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(), "doc": str(path),
           "key": coverage.doc_key(path), "line": n, "line_key": coverage.line_key(lines[n - 1]),
           "text": lines[n - 1], "evidence": note}
    coverage.EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    with coverage.EVIDENCE.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return lines[n - 1].strip()[:40]


def evidenced_on(key: str, lines: list[str], mine: list[int]) -> list[tuple[int, dict]]:
    """대상 줄(또는 그 앞 판)에 적힌 근거 — (줄, 기록). 줄마다 최근 것 둘까지. 근거가 가리키는 이 문서의 줄을 붙인다."""
    rows = [r for r in coverage._rows(key, coverage.EVIDENCE, None, fresh=False) if r.get("text")]
    out = []
    for n in mine:
        k = coverage.line_key(lines[n - 1])
        near = [r for r in rows if r.get("line_key") == k
                or coverage._similar(lines[n - 1], r["text"]) >= coverage.SUCCESSOR]
        for r in near[-2:]:
            r = dict(r)
            note = r.get("evidence") or ""
            files = [m.end() for m in PATH_REF.finditer(note)]
            # 이 문서의 「N행」만 붙인다 — 경로 뒤의 「N행」은 그 파일의 줄이다(`evidence_problems` 와 같은 귀속)
            r["doc_lines"] = [(int(m.group(1)), lines[int(m.group(1)) - 1]) for m in re.finditer(r"(\d+)\s?행", note)
                              if (not any(e <= m.start() for e in files) or "문서" in note[max(0, m.start() - 6):m.start()])
                              and 0 < int(m.group(1)) <= len(lines)]
            out.append((n, r))
    return out


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
                 decided: list[tuple[int, dict]] = (), instructed: list[tuple[int, dict]] = (),
                 evidenced: list[tuple[int, dict]] = ()) -> str:
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
        for n, r in roots:
            out.append(f"- {n}행 기준 판: {r}")
            found = info[n].get("root_found") or []
            if found:
                out.append("  고친 까닭: " + " · ".join(f"「{f['phrase']}」→「{f['fix']}」" for f in found))
        if any(info[n].get("root_found") for n, _ in roots):
            out.append("기준 판은 「고친 까닭」의 지적을 받아 고친 글이다. 지적됐던 표현을 되살리는 수정안은 내지 "
                       "않는다 — 빠진 뜻을 되살려야 하면 다른 말로 쓴다.")
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
    if evidenced:
        # 근거가 받치는 사실만 덜 짚는다 — 근거 밖의 새 주장과 근거와 다른 값은 그대로 짚는다(지시와 같은 선)
        out += ["", "아래 줄은 세션이 자료로 확인하고 쓴 사실 주장이다. 근거가 받치는 수치와 사실은 「확인 필요」나 "
                "「고치다 뜻이 바뀐 곳」으로 짚지 않는다. 근거와 다른 값, 근거가 말하지 않는 새 주장, 다른 규칙 위반은 "
                "그대로 짚는다."]
        for n, r in evidenced:
            out.append(f"- {n}행 근거: {r.get('evidence')}")
            out += [f"  (문서 {m}행: {t.strip()})" for m, t in r.get("doc_lines") or []]
    return "\n".join(out)


#: 사람 확인 표에 싣는 판정 이력 — 최근 것부터 이만큼. 표 한 칸이라 길면 못 읽는다
HISTORY_STEPS = 6


def line_history(key: str, root: str | None, log: Path | None = None) -> list[str]:
    """기준 판부터 지금까지 그 줄에 낸 고칠 지적 — 「[갈래] 「짚은 표현」 → 「제안」(반영 여부)」 목록.

    (2026-11-09 사용자 「무슨 소린지 모르겠다. 뭐라고 써있었는데 어떻게 고쳤는데 왜 해결이 안되어 나에게 보고한
    것인지」) 상한 항목의 「고친 이유」에 판정 횟수만 적혀 있어 무엇을 정해야 하는지 알 수 없었다. 같은 줄을
    판정기가 앞서 제안한 문구를 다시 짚은 것(자기 모순)이나 세션이 제안과 다르게 고친 것이 이력에서 보인다.
    """
    if not root:
        return []
    rows = sorted((r for r in coverage._rows(key, log or LOG, None, fresh=False) if r.get("ok")),
                  key=lambda r: float(r.get("when") or 0))
    texts = {root}
    for r in rows:
        texts |= {e["text"] for e in r.get("targeted") or [] if (e.get("root") or e.get("text")) == root}
    steps, seen = [], set()
    for r in rows:
        for fx in r.get("fixes") or []:
            text, phrase, fix = fx.get("text"), str(fx.get("phrase") or ""), str(fx.get("fix") or "")
            if text not in texts or (text, phrase) in seen:
                continue
            seen.add((text, phrase))
            done = "반영" if fix and any(fix in t for t in texts if t != text) else "제안과 다르게 고침"
            steps.append(f"[{fx.get('category') or '지적'}] 「{phrase}」 → 「{fix}」({done})")
    return steps[-HISTORY_STEPS:]


def held_ask(n: int, line: str, info: dict, history: list[str] | None = None) -> dict:
    """상한을 넘은 줄을 사람 확인으로 — 짚은 표현은 줄 전체(그 줄이 그대로인 동안 열림)."""
    why = (f"같은 줄을 {info['round']}번째 판정해 자동 수정을 멈춤(상한 {REJUDGE_CAP}회) · "
           "「그대로」는 지금 문장으로 확정, 「고침」은 기준 판으로 되돌림")
    if history:
        why += " · 판정 이력: " + " / ".join(history)
    return {"line": n, "phrase": line.strip(), "category": "재판정 상한",
            # 표의 「고침」은 판정기 제안대로라는 뜻이라, 제안 칸을 「되돌림」으로 적어 뜻을 분명히 한다
            "fix": f"기준 판으로 되돌림 — {info['root']}" if info.get("root") else "(새로 쓴 줄 · 기준 판 없음)",
            "why": why, "decide": "ask", "held": True}


def judge(path: Path, model: str, timeout: float, backend, targets: list[int] | None = None,
          base: list[str] | None = None, anchors: dict[int, list[str]] | None = None,
          base_time: float | None = None, context: str = DEFAULT_CONTEXT) -> dict:
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
    system = probe.system_prompt().format(rules=rules) + decisions_prompt(decisions)
    # 규칙 글의 판 — 규칙이 바뀐 뒤의 판정과 앞의 판정을 가르는 최소 식별자(외부 검토 · 2026-10-12)
    rules_sha = hashlib.sha256(rules.encode("utf-8")).hexdigest()[:12]
    base_system = probe.system_prompt().format(rules=rules)
    made, extra = time.time(), ""
    if want is not None:        # 재판정 — 직전 호출의 시스템 프롬프트를 캐시에서 읽게(`system_for`)
        reused = system_for(key, system, rules_sha)
        if reused:
            system, made = reused
            extra = new_answers(made)
    # 드문 낱말 목록 — 단어 점검 기록을 따로 요구하는 대신 판정기가 후보로 함께 읽는다(`probe.rare_note`)
    note = probe.rare_note(path)
    extra += note
    info = lineage(key, lines, sorted(want - set(anchors)), base, base_time) if want else {}
    root_findings(key, info)
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
    # 다른 줄에 남은 고칠 지적은 첫 재판정에도 센다(2026-10-20) — 경고는 두 번째 이상만 내지만, 첫 재판정이
    # 지적을 모아 고친 뒤인지 하나씩 고친 뒤인지는 이 수가 있어야 실사용 기록으로 가른다.
    open_elsewhere = (sum(1 for n, _ in coverage.open_fixes(key, lines, LOG) if n not in want)
                      if want is not None else 0)
    pending = open_elsewhere if rejudge_only else 0
    found, calls, hidden, foreign, held = [], [], 0, 0, 0
    held_done: set[int] = set()
    queue = parts_for(lines, want, context, path)
    closed_all, decided_all, instructed_all, evidenced_all = [], [], [], []
    # 받지 않음으로 닫은 기록 — 고친 줄에 남은 표현을 줄 이력으로 붙일 때 일부러 남긴 것을 거른다(`kept_flagged`)
    closed_rows = list(coverage._rows(key, coverage.DISMISSALS, None, fresh=False)) if want is not None else []
    freq = load_freq()
    if want is not None:
        plain = [n for n in sorted(want) if not info[n].get("anchor")]
        closed_all, decided_all = closed_on(key, lines, plain), decided_on(key, lines, plain)
        instructed_all, evidenced_all = instructed_on(key, lines, plain), evidenced_on(key, lines, plain)
        save_case(path, key, text, want, anchors, base, info, rules_sha, system, model, context,
                  closed_all, decided_all, instructed_all,
                  coverage.html_heads(path, lines) if path.suffix.lower() in coverage.HTML_SUFFIXES else None,
                  system[len(base_system):] if system.startswith(base_system) else None, extra, evidenced_all)
    while queue:
        piece = queue.pop(0)
        mine, windowed = piece["mine"], piece["mode"] in ("fixed", "block")
        short: set[int] = set()
        started = time.time()
        row = {"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(),
               "doc": str(path), "key": key,
               "sha256": hashlib.sha256("\n".join(piece["seen"]).encode("utf-8")).hexdigest()[:16],
               "lines": piece["label"], "model": model, "rules": rules_sha,
               **RUN_NOTES,            # 검사 단계 · 비용 한도를 넘긴 승인(main 이 채움)
               "cache_ttl": ttl,       # 적용 전후 비용을 기록으로 가른다
               "format": probe.output_format(),   # 출력 형식을 기록으로 가른다(행 형식 기본 · 2026-10-20)
               "context": piece["mode"],
               # 게이트가 「이번 가지의 새 줄을 판정기가 다 봤나」를 이것으로 가른다 — 창이면 보낸 줄만
               "seen": coverage.seen_keys(piece["seen"])}
        user = rejudge_user(piece, info, closed_all, decided_all, instructed_all, extra, evidenced_all) \
            if want is not None \
            else probe.USER.format(document=piece["document"]) + note
        if want is not None:
            # 묶음은 문맥으로 통째로 보내되 지적은 새 줄에만 받는다. 전에는 묶음 전체에
            # 지적을 써 오게 하고 새 줄 밖의 것을 버렸다 — 출력 토큰이 곧 시간이고(상관 0.97)
            # 지적 하나가 약 206토큰이라, 버리는 지적만큼 시간과 한도를 썼다(2026-10-07 실측).
            row["targets"] = len(mine)
            row["rejudge_only"] = rejudge_only  # 묶음 경고의 근거 — 얼마나 자주 이러는지 센다
            row["pending_fixes"] = pending
            row["open_elsewhere"] = open_elsewhere  # 첫 재판정 포함 — 처리 묶음 실사용 몫을 센다
            row["base_time"] = base_time       # 이 판정을 센 갈라진 지점 — 다음 판정이 같은 지점 것만 센다
            # 다음 판정이 이 줄의 자손을 찾고 판정 횟수를 이어 세는 데 쓴다(저장소 밖 기록)
            row["targeted"] = [{"key": coverage.line_key(lines[n - 1]), "text": lines[n - 1],
                                "round": info[n]["round"], "root": info[n]["root"]}
                               for n in mine if not info[n].get("anchor")]
            # 게이트가 「지운 자리를 판정기가 봤나」를 이것으로 가른다
            row["deleted_seen"] = sorted({k for n in mine for k in info[n].get("deleted_keys") or [] if k})
            over = [n for n in mine if info[n]["round"] > REJUDGE_CAP]
        # 사고 깊이 — 비우면 모델 기본값. 검사 단계 설정 측정(runs/judge-effort-levels-20261104)이 쓴다
        thinking = os.environ.get(THINKING_ENV) or None
        row["effort"] = thinking
        try:
            with watch_usage():
                r = call_messages(model=model, system=system, user=user,
                                  max_tokens=12000, temperature=0, timeout=timeout,
                                  **({"effort": thinking} if thinking else {}))
        except Exception as e:          # 실패도 기록한다 — 시간은 들었다
            row.update(ok=False, error=f"{type(e).__name__}: {e}"[:200],
                       seconds=round(time.time() - started, 1))
            log_call(row)
            calls.append(row)
            raise
        raw = parse_json(r.get("text") or "") or []
        items = probe.as_findings(raw)
        usage = r.get("usage") or {}
        row.update(ok=True, model=r.get("model") or model,
                   seconds=round(time.time() - started, 1),
                   # ⛔ 입력은 셋으로 나뉘어 온다 — 캐시에 쓴 것·읽은 것을 빼면 입력이
                   #    2 토큰으로 찍힌다(첫 실측 2026-09-29). 합계는 `input_total` 로 센다.
                   input_tokens=usage.get("input_tokens", 0),
                   cache_write=usage.get("cache_creation_input_tokens", 0),
                   cache_read=usage.get("cache_read_input_tokens", 0),
                   output_tokens=usage.get("output_tokens", 0),
                   cost_usd=r.get("cost_usd"), findings=len(items),
                   # 과금 방식과 구독 사용률 — 단계별 한도를 실사용 기록으로 다시 정할 때 쓴다(2026-11-05)
                   billing=r.get("billing") or RUN_NOTES.get("billing"),
                   **({"five_hour": _USAGE[-1].get("five_hour")} if _USAGE else {}),
                   # 칸이 어긋난 행 — 늘면 행 형식을 `json` 으로 되돌린다(특히 Codex 백엔드는 안 쟀다)
                   malformed=probe.malformed(raw))
        save_system(key, system, rules_sha, made, started)
        # 잘린 답 — 지적을 받지 않고 묶음을 나눠 다시 부른다. 못 나누면 실패로 알린다(조용히 넘기면 그 줄들이
        # 판정된 것으로 남는다 · 2026-11-04 측정 문서의 첫 180줄이 지적 0건으로 기록됨)
        if truncated(r):
            # ok=False — 성공한 호출의 「본 줄」만 판정된 것으로 센다(`coverage.judged`). 비용은 그대로 남긴다
            row.update(ok=False, truncated=True, error="출력 한도에 닿아 답이 잘림")
            halves = split_piece(piece)
            log_call(row)
            calls.append(row)
            if not halves:
                raise RuntimeError(f"출력 한도에 닿아 {piece['label']}행 판정이 잘렸고 더 나눌 수 없습니다")
            queue = halves + queue
            continue
        asks, fixes = [], []
        hidden_before = hidden
        fresh_held, real_lines = [], set()
        if want is not None:
            # 상한을 처음 넘은 줄 — 이번 판정이 그 줄에서 고칠 것을 찾았을 때만 줄 자체도 사람에게(아래 고리 뒤).
            # 못 찾았으면 지금 문장으로 둔다(REJUDGE_CAP 주석 · 2026-11-11 사용자 결정)
            fresh_held = [n for n in over if info[n]["round"] == REJUDGE_CAP + 1 and n not in held_done]
            held_done.update(fresh_held)
            items = list(items) + kept_flagged(lines, mine, info, items, closed_rows, freq)
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
                if want is not None and n in over and noop_fix(it):
                    # 고칠 것이 없는 지적 — 확인할 사실만 있으면 세션이 자료로 닫고(고칠 지적으로 둠), 없으면 버린다
                    if not str(it.get("check") or "").strip():
                        continue
                    it["decide"] = "fix"
                elif want is not None and n in over and not is_ask(it):
                    it["decide"] = "ask"
                    it["why"] = (f"{it.get('why') or ''} · 같은 줄을 {info[n]['round']}번째 판정 — "
                                 f"상한 {REJUDGE_CAP}회를 넘어 사람 확인으로 올림").lstrip(" ·")
                    it["held"] = True
                if it.get("held"):
                    held += 1
                # 지적됐던 표현을 되살리는 수정안 — 버리지 않고 안내를 붙인다. 버리면 실제 뜻 바뀜 지적도 함께
                # 사라지고, 그대로 두면 세션이 되돌려 같은 지적이 다시 난다(외부 검토 Argon · 2026-10-20)
                back = revived(it, info.get(n) or {}) if want is not None and not is_ask(it) else None
                if back:
                    it["revives"] = back
                    it["why"] = (f"{it.get('why') or ''} · 수정안이 앞선 판정에서 고치라고 한 「{back}」을 "
                                 f"되살림 — 빠진 뜻만 살리고 다른 말로 씀").lstrip(" ·")
                found.append(it)
                ok_line = isinstance(n, int) and 0 < n <= len(lines)
                rec = {"line_key": coverage.line_key(lines[n - 1]) if ok_line else None,
                       "line": n, "phrase": it.get("phrase"), "fix": it.get("fix"),
                       "why": it.get("why"), "category": it.get("category")}
                if it.get("revives"):
                    rec["revives"] = it["revives"]
                if is_ask(it):
                    asks.append(rec)
                else:
                    # 고친 줄을 이 줄의 자손으로 찾으려면 그때 글이 있어야 한다(저장소 밖 기록)
                    fixes.append(dict(rec, check=it.get("check") or "", text=lines[n - 1] if ok_line else ""))
                if not noop_fix(it):
                    real_lines.add(n)
        # 상한을 처음 넘은 줄 가운데 이번 판정이 고칠 것을 찾은 줄만 줄 자체를 사람 확인에 올린다
        for n in fresh_held:
            if n not in real_lines:
                continue
            it = held_ask(n, lines[n - 1], info[n], line_history(key, info[n].get("root")))
            found.append(it)
            held += 1
            asks.append({"line_key": coverage.line_key(lines[n - 1]), "line": n, "phrase": it["phrase"],
                         "fix": it["fix"], "why": it["why"], "category": it["category"]})
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
    bad = sum(c.get("malformed") or 0 for c in calls)
    if bad:
        print(f"  ⚠️ 칸이 어긋난 지적 {bad}건 — 줄 번호 · 고친 말 · 확인할 사실이 엉뚱한 칸에서 왔을 수 있으니 "
              f"원문과 대조합니다. 되풀이되면 {probe.FORMAT_ENV}=json 으로 예전 형식을 씁니다")
    asks =[f for f in result["findings"] if is_ask(f)]
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


def personal_level() -> str | None:
    """개인 설정 파일(발행 게이트가 읽는 개인 목록)의 `check_level` — 없거나 못 읽으면 None."""
    p = Path(os.environ.get("KOREAN_QA_PUBLISH_REPOS")
             or Path.home() / ".claude" / "data" / "catalog" / "local-publish-repos.toml")
    if not p.is_file():
        return None
    try:
        import tomllib
        got = tomllib.loads(p.read_text(encoding="utf-8")).get("check_level")
    except Exception:
        return None
    return str(got) if got else None


def resolve_level(arg: str | None) -> str:
    """명령 인자 → 환경 변수 → 개인 설정 → 기본값. 모르는 이름이면 ValueError."""
    raw = arg or os.environ.get(LEVEL_ENV) or personal_level() or DEFAULT_LEVEL
    name = LEVEL_ALIASES.get(raw, raw)
    if name not in LEVELS:
        raise ValueError(f"검사 단계 「{raw}」 를 모릅니다 — min(최소) · balanced(가성비) · max(최대)")
    return name


def billing_of(name: str | None, backend) -> str | None:
    """이 판정이 나가는 과금 방식 — `subscription` · `api` · None(Codex: 금액을 안 줘 한도 밖)."""
    if name == "codex":
        return None
    if getattr(backend[0], "__module__", "") == "layer2_client":
        import layer2_client
        return "api" if layer2_client.metered_keys() and layer2_client.key_choice() == "api" else "subscription"
    return probe.BILLING


#: SDK 가 호출마다 주는 구독 사용률(5시간 · 7일) — `watch_usage` 가 모은다
_USAGE: list[dict] = []


@contextlib.contextmanager
def watch_usage():
    """판정 호출 동안 SDK 의 질의 함수를 감싸 구독 사용률을 `_USAGE` 에 모은다 — 판정 기록과 한도 안내에 쓴다.

    두 호출 길(이 PC 의 `llm_playbook` 과 공개판의 `layer2_client`)이 모두 SDK 의 `query` 를 쓴다. 측정 도구의
    `bench_loop.watch_limits` 와 같은 방식이다. 못 감싸면 아무것도 안 모은다(판정은 그대로).
    """
    patched = []

    def spy_of(real):
        async def spy(*a, **kw):
            async for m in real(*a, **kw):
                info = getattr(m, "rate_limit_info", None)
                raw = getattr(info, "raw", None) if info is not None else None
                if isinstance(raw, dict):
                    wins = raw.get("unifiedWindows") or {}
                    _USAGE.append({k: v.get("utilization") for k, v in wins.items() if isinstance(v, dict)})
                yield m
        return spy

    for name in ("llm_playbook.backends.claude_sdk", "claude_agent_sdk"):
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        real = getattr(mod, "query", None)
        if real is not None:
            mod.query = spy_of(real)
            patched.append((mod, real))
    try:
        yield
    finally:
        for mod, real in reversed(patched):
            mod.query = real


def last_five_hour(key: str) -> float | None:
    """이 문서의 판정 기록에 남은 마지막 5시간 사용률 — 없으면 None."""
    got = None
    if LOG.is_file():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("key") == key and r.get("five_hour") is not None:
                got = r["five_hour"]
    return got


def work_spent(key: str, now: float | None = None) -> float:
    """이 문서의 지금 작업 묶음에 쓴 판정 비용(달러) — 판정 사이가 `WORK_GAP_S` 넘게 비면 거기서 끊는다."""
    now = now or time.time()
    whens = []
    if LOG.is_file():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("key") == key and r.get("when"):
                whens.append((float(r["when"]), float(r.get("cost_usd") or 0)))
    spent, last = 0.0, now
    for when, cost in sorted(whens, reverse=True):
        if last - when > WORK_GAP_S:
            break
        spent, last = spent + cost, when
    return spent


def main(argv=None, backend=None) -> int:
    ap = argparse.ArgumentParser(description="2층 판정 호출 · 비용 기록")
    ap.add_argument("docs", nargs="*")
    ap.add_argument("--backend", choices=("auto", "claude", "codex"), default="auto",
                    help="auto 면 Claude → Codex 순서로 이 PC 에서 쓸 수 있는 쪽")
    ap.add_argument("--model", help=f"기본 — Claude {DEFAULT_MODEL} · Codex {CODEX_MODEL} · 주면 검사 단계의 모델 선택을 덮음")
    ap.add_argument("--level", help="검사 단계 — min(최소) · balanced(가성비) · max(최대). 비우면 환경 변수 "
                                    f"{LEVEL_ENV}, 개인 설정 check_level, 기본값 {DEFAULT_LEVEL} 순")
    ap.add_argument("--internal", action="store_true",
                    help="발행 대상이 아닌 저장소 내부 문서(작성자만 봄)도 판정 — 기본은 건너뜀(internal_doc)")
    ap.add_argument("--now", action="store_true",
                    help="다른 줄에 처리 안 된 고칠 지적이 남아도 재판정 — 고치는 방향을 먼저 보는 중간 판정")
    ap.add_argument("--over-budget", action="store_true",
                    help="문서 비용 한도를 넘겨 판정 — --note 에 사용자 승인 원문 필수")
    ap.add_argument("--api-key-use", choices=("subscription", "api"),
                    help="공개판에서 API 키 환경 변수가 있을 때 사용자가 고른 것을 남김 — subscription(판정 호출에서 "
                         "키를 숨겨 구독으로) · api(키로 과금). 한 번 남기면 다시 묻지 않음")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--json", help="지적을 JSON 으로도 씀")
    ap.add_argument("--since", metavar="REF", nargs="?", const="HEAD",
                    help="REF 와 갈라진 뒤 새로 생겼고 아직 판정 안 한 줄만 판정 — 예: origin/main. "
                         "REF 없이 주면 HEAD(git 밖 문서는 아직 판정 안 한 줄만)")
    ap.add_argument("--context", choices=CONTEXT_MODES, default=DEFAULT_CONTEXT,
                    help="--since 재판정에 보낼 문맥 — fixed(기본 · 앞뒤 20줄 + 제목 사슬) · chunk(180줄 묶음) · block(실험)")
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
    ap.add_argument("--reply", action="append", metavar="'번호 답'",
                    help="--answers-from 과 함께 · 대화로 받은 답을 사용자 원문 그대로 — 여러 번 줄 수 있음")
    ap.add_argument("--fixes", action="store_true",
                    help="모델을 부르지 않고 처리 안 된 고칠 지적만 보기")
    ap.add_argument("--why", action="store_true",
                    help="왜 고쳤나 — 판정 기록의 지적과 지금 글에서의 처리(반영 · 남음 · 다르게 고침)를 줄마다 보기")
    ap.add_argument("--line", type=int, metavar="행", help="--why 와 함께 · 그 줄만")
    ap.add_argument("--dismiss", type=int, metavar="행",
                    help="고칠 지적 하나를 받지 않기로 적음 — --reason · --note 필수")
    ap.add_argument("--reason", choices=tuple(REASONS), help="--dismiss 의 사유")
    ap.add_argument("--escalate", type=int, metavar="행",
                    help="고칠 지적 하나를 사람 확인으로 올림 — --note 필수")
    ap.add_argument("--phrase", help="--dismiss · --escalate 에서 그 줄의 지적이 둘 이상일 때 고르는 표현")
    ap.add_argument("--instructed", type=int, action="append", metavar="행",
                    help="사용자 지시로 뜻을 일부러 바꾼 줄 — --note 에 지시 원문(「」) · 재판정이 지시 안의 뜻 변경은 안 짚음")
    ap.add_argument("--evidence", type=int, action="append", metavar="행",
                    help="자료로 확인하고 고친 사실 주장 — --note 에 「<경로> 「원문」」 또는 이 문서의 「N행」 · "
                         "재판정이 근거가 받치는 사실은 「확인 필요」로 안 짚음")
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
    if a.evidence:
        if len(a.docs) != 1 or not a.note:
            print("⛔ --evidence 는 문서 하나에 --note 와 함께 씁니다 — 줄 번호가 문서마다 다릅니다")
            return 2
        try:
            for n in a.evidence:
                print(f"  근거 기록 — {n}행 「{record_evidence(Path(a.docs[0]), n, a.note)}」 · "
                      "재판정이 근거가 받치는 사실은 안 짚음")
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
            print(f"  지적이 {ask_sheet.SCREEN_MAX}건 이하라 화면으로 묻습니다 — 아래 표의 「제 의견」 칸을 채워 사용자에게 보이고,")
            print("  위 표 파일의 같은 칸에도 같은 의견을 적습니다(「전부 의견대로」 같은 짧은 답을 그 칸으로 풉니다).")
            print("  받은 답은 사용자 원문 그대로 옮겨 읽습니다(답: 고침, 그대로, 직접: …, 보류):")
            print(f"    python -X utf8 {Path(__file__).resolve().as_posix()} --answers-from {out.resolve().as_posix()} "
                  "--reply '의견대로, 단 3 그대로'")
            print()
            print(listing)
        elif asks and len(a.docs) == 1:
            # 2026-11-02 사용자 결정 — 검토 화면이 판정표를 대신한다. 답을 화면이 판정 기록에 바로 남기므로
            # 표의 「답」 칸과 --answers-from 을 거치지 않는다
            print(f"  지적이 {ask_sheet.SCREEN_MAX}건을 넘어 검토 화면으로 묻습니다 — 백그라운드로 띄웁니다(사용자가 "
                  "「제출」을 누르면 답을 판정 기록에 남기고 고른 글로 파일을 고친 뒤 요약을 내고 끝남):")
            print(f"    python -X utf8 {(Path(__file__).parent / 'review_screen.py').resolve().as_posix()} "
                  f"{Path(a.docs[0]).resolve().as_posix()} --serve")
            print("  끝나면 요약의 「세션이 고칠 것」과 「세션에 맡김」을 고치고 「다시 판정할 줄」과 함께 --since 로 다시 판정합니다")
        elif asks:
            print(f"  지적이 {ask_sheet.SCREEN_MAX}건을 넘고 문서가 여럿이라 판정표로 묻습니다 — 「제 의견」 칸을 채운 뒤 "
                  "카드형 판정표를 백그라운드로 띄웁니다(사용자가 「제출」을 누르면 답이 표에 적히고 명령이 끝남):")
            print(f"    python -X utf8 {(Path(__file__).parent / 'ask_sheet_html.py').resolve().as_posix()} "
                  f"{out.resolve().as_posix()} --serve")
            print(f"  끝나면: python -X utf8 {Path(__file__).resolve().as_posix()} --answers-from {out.resolve().as_posix()}")
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
    if a.why:
        missing = [d for d in a.docs if not Path(d).is_file()]
        if missing or not a.docs:
            print(f"⛔ 파일 없음 — {missing[0] if missing else '문서를 줍니다'}")
            return 2
        for d in a.docs:
            show_why(Path(d), a.line)
        return 0
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
    # 작성자만 보는 저장소 내부 문서는 판정하지 않는다 — 꼭 판정하려면 --internal(`internal_doc`)
    inside = [] if a.internal else [d for d in a.docs if internal_doc(Path(d))]
    for d in inside:
        print(f"⏭ {Path(d).name} — 발행 대상이 아닌 저장소 내부 문서(작성자만 봄)라 판정하지 않았습니다. "
              "공유할 문서면 머리말에 audience: share 를 적고, 그래도 판정하려면 --internal")
    a.docs = [d for d in a.docs if d not in inside]
    if inside and not a.docs:
        return 0
    name = pick_backend(a.backend)
    model = a.model or (CODEX_MODEL if name == "codex" else DEFAULT_MODEL)
    try:
        level = resolve_level(a.level)
    except ValueError as e:
        print(f"⛔ {e}")
        return 2
    if a.over_budget and not a.note.strip():
        print("⛔ --over-budget 은 --note 에 사용자 승인 원문이 있어야 합니다 — 한도를 넘긴 까닭이 기록에 남게")
        return 2
    if a.api_key_use:
        import layer2_client
        print(f"  API 키가 있을 때의 선택을 남김 — {a.api_key_use} · {layer2_client.save_choice(a.api_key_use)}")
    lv = LEVELS[level]
    # --model 이나 사고 깊이 환경 변수를 직접 주면(측정 도구) 단계의 모델 선택을 쓰지 않는다 · Codex 는 단계 밖
    by_level = not a.model and name == "claude" and not os.environ.get(THINKING_ENV)
    RUN_NOTES.clear()
    RUN_NOTES["level"] = level
    if a.over_budget:
        RUN_NOTES["over_budget"] = a.note.strip()[:300]
    backend = backend or (load_backend(name) if name else None)
    if backend is None:
        print("⛔ 2층 판정 호출을 못 합니다 — llm_playbook 이 없거나 Claude Code · Codex 둘 다 "
              "설치·로그인이 안 돼 있습니다. 판단 규칙과 9단계를 세션이 직접 읽고 판정합니다.")
        return 3
    # 공개판 호출부 + API 키 환경 변수 — Claude Code 가 구독 대신 그 키로 과금하므로 사용자에게 먼저 묻는다
    # (llm_playbook 이 있는 PC 는 그쪽이 키가 있으면 호출을 거절해 여기 오지 않는다 · 2026-11-04 사용자 결정)
    if getattr(backend[0], "__module__", "") == "layer2_client":
        import layer2_client
        keys = layer2_client.metered_keys()
        if keys and layer2_client.key_choice() is None:
            print(f"⛔ 환경 변수 {', '.join(keys)} 가 있어 판정 호출이 구독이 아니라 그 API 키로 과금될 수 있습니다 — "
                  "판정하지 않았습니다")
            print("   사용자에게 묻고 답대로 한 번만 남깁니다(다음부터 묻지 않음):")
            print("     구독으로 — 판정 호출에서만 키를 숨김: --api-key-use subscription")
            print("     API 키로 과금 — --api-key-use api")
            return 7
    billing = billing_of(name, backend)
    RUN_NOTES["billing"] = billing
    results = []
    for d in a.docs:
        p = Path(d)
        if not p.is_file():
            print(f"⛔ 파일 없음 — {d}")
            return 2
        targets, base, anchors, base_t = None, None, None, None
        # 이미 판정한 문서를 --since 없이 다시 부르면 고치지 않은 줄까지 다시 판정한다 — 회차마다 새 지적이
        # 조금씩 나와 끝나지 않는다(2026-11-02 현장 보고 · git 밖 문서 둘을 전체로 일곱 번씩 판정함)
        rerun = not a.since and bool(coverage.judged(coverage.doc_key(p), LOG))
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
        key = coverage.doc_key(p)
        # 비용 한도 — 닿으면 판정하지 않고 「검사 미완료」로 남긴다(통과가 아니다 · 2026-11-04 astra 검토)
        budget = (lv["budget_won"] or {}).get(billing) if billing else None
        if budget and not a.over_budget:
            spent = work_spent(key) * WON_PER_USD
            if spent >= budget:
                if billing == "api":
                    print(f"⛔ {p.name} — 이 문서 작업에 판정 비용 {spent:,.0f}원(API 크레딧에서 나감)을 써 「{level}」 "
                          f"단계 한도 {budget:,}원에 닿았습니다 · 검사 미완료")
                else:
                    five = last_five_hour(key)
                    usage = f" · 5시간 사용률 {five:.0%}" if isinstance(five, (int, float)) else ""
                    print(f"⛔ {p.name} — 이 문서 작업의 구독 사용량이 「{level}」 단계 한도를 넘었습니다"
                          f"(API 단가 환산 {spent:,.0f}원 · 한도 {budget:,}원{usage}) · 검사 미완료")
                print("   남은 줄은 판정하지 않았습니다(발행과 push 게이트가 계속 막습니다) — 사람이 확인하거나, "
                      "사용자가 승인하면 --over-budget --note \"승인 원문\"")
                return 5
        # 모아서 판정 — 다른 줄에 처리 안 된 고칠 지적이 남았으면 재판정을 미룬다(사람 확인은 세지 않음)
        if lv["batch"] and targets is not None and not a.now:
            want = set(targets)
            left = [n for n, _ in coverage.open_fixes(key, read_doc(p).splitlines(), LOG) if n not in want]
            if left:
                print(f"⛔ {p.name} — 다른 줄에 처리 안 된 고칠 지적 {len(left)}건(행 {', '.join(map(str, left[:8]))}"
                      f"{' …' if len(left) > 8 else ''})이 남아 재판정을 미뤘습니다")
                print("   지적을 모두 고치거나 --dismiss · --escalate 로 처리한 뒤 한 번에 다시 판정합니다 — "
                      "고치는 방향을 먼저 볼 중간 판정이면 --now")
                return 6
        use_model = model
        if by_level:
            # 첫 판정인지는 「이 문서를 판정한 적이 있나」로 가른다 — 가지에서 새로 만든 문서는 처음부터
            # --since origin/main 으로 불려 대상이 있어도 첫 판정이다(재판정 모델은 첫 판정 기준을 못 넘었다)
            first = targets is None or not coverage.judged(key, LOG)
            use_model, thinking = lv["first" if first else "rejudge"]
            if thinking:
                os.environ[THINKING_ENV] = thinking
        try:
            results.append(judge(p, use_model, a.timeout, backend, targets, base, anchors, base_t, a.context))
        except Exception as e:
            print(f"⛔ 호출 실패 — {p.name}: {type(e).__name__}: {e}"[:300])
            print("   검사되지 않았습니다 — 세션이 규칙을 직접 읽고 판정합니다.")
            return 4
        finally:
            if by_level:    # 한 프로세스에서 main 을 여러 번 부르는 측정 도구가 다음 호출을 직접 지정으로 오해하지 않게
                os.environ.pop(THINKING_ENV, None)
        show(results[-1])
        if rerun:
            print(f"  ⚠️ {p.name} 은 앞서 판정한 문서라 이번에 문서 전체를 다시 판정했습니다 — 고친 줄만 다시 보려면 "
                  "--since 를 붙입니다(git 밖 문서는 REF 없이 --since 만: 판정기가 아직 안 본 줄만 판정)")
    if a.json:
        Path(a.json).write_text(json.dumps(results, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
