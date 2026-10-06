"""2층 판정 — 문서를 판단 규칙 전문과 함께 CLAUDE.md 없는 모델 호출에 넘겨 지적 목록을 받는다.

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

**새 줄만 판정** — `--since origin/main` 이면 그 가지와 갈라진 뒤 새로 생겼고 판정기가
아직 안 본 줄이 든 묶음만 부르고, 그 줄에 달린 지적만 보여 준다. 호출마다 본 줄의
해시를 기록에 남기므로(`layer2_coverage.py`) 고친 줄만 다시 판정된다. 발행 게이트가
push 직전에 같은 기록으로 「새 줄을 다 봤나」를 가른다.

**사람 확인** (2026-10-06 사용자 결정) — 판정기는 지적마다 `decide` 를 낸다. 분명하면
`fix`, 문맥에 따라 정상일 수 있거나 규칙에 기준이 없거나 고치면 뜻이 바뀔 수 있으면
`ask` 다. `ask` 는 **세션이 정하지 않고 사용자에게 묻는다.** 판정 기록에 줄 해시와 함께
남고, 사용자가 답하면 `--answer` 로 그 줄에 답을 적는다. 답을 못 받은 지적이 남은
문서는 발행 직전 검사가 막는다(`hooks/doc-style-gate.py`).

    python -X utf8 scripts/judge_layer2.py <문서…> [--since REF] [--backend auto|claude|codex]
                                           [--model 별칭] [--json 경로]
    python -X utf8 scripts/judge_layer2.py <문서…> --sheet <저장소 밖 경로>.md
    python -X utf8 scripts/judge_layer2.py --answers-from <그 표>
    python -X utf8 scripts/judge_layer2.py <문서> --answer <행> [--answer <행>…] --note "사용자가 정한 것"
    python -X utf8 scripts/judge_layer2.py <문서…> --asks
    python -X utf8 scripts/judge_layer2.py --cost [--by day|month|doc]

**사용자에게 넘기는 형식은 표 한 장** (2026-10-07 사용자) — `--sheet` 가 md 표를 쓰고 사용자가
「답」 칸을 채우면 `--answers-from` 이 읽는다. 형식과 답 처리는 `ask_sheet.py` 에 있다.

종료 코드 — 0 돌았음(지적은 사람이 본다) · 1 `--asks` · `--sheet` · `--answers-from` 에서 답을 기다리는 지적이 남음 ·
2 사용법 · 표를 못 읽음 · 3 호출 백엔드 없음(세션이 규칙을 직접 읽는다) · 4 호출 실패
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    waiting = {n for n, _ in coverage.open_asks(key, lines, LOG)}
    rows = []
    for n in line_nos:
        if not 0 < n <= len(lines) or not coverage.line_key(lines[n - 1]):
            raise ValueError(f"{n}행은 한글이 든 줄이 아닙니다 — 판정 결과의 줄 번호를 적습니다")
        if n not in waiting:
            raise ValueError(f"{n}행에는 답을 기다리는 사람 확인 지적이 없습니다 — "
                             "--asks 로 줄 번호를 확인합니다")
        rows.append({"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(),
                     "doc": str(path), "key": key, "line": n,
                     "line_key": coverage.line_key(lines[n - 1]), "note": note.strip()})
    coverage.ANSWERS.parent.mkdir(parents=True, exist_ok=True)
    with coverage.ANSWERS.open("a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return [lines[r["line"] - 1].strip()[:40] for r in rows]


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


def write_sheet(paths: list[Path], out: Path) -> tuple[int, int]:
    """열린 사람 확인을 md 표 한 장으로 쓴다 — (줄 수, 지적 수). 형식은 `ask_sheet.py`."""
    docs = []
    for p in paths:
        lines = read_doc(p).splitlines()
        docs.append((p, lines, coverage.open_asks(coverage.doc_key(p), lines, LOG)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ask_sheet.render(docs, coverage.line_key), encoding="utf-8", newline="\n")
    asks = sum(len(a) for _, _, a in docs)
    rows = sum(len({n for n, _ in a}) for _, _, a in docs)
    return rows, asks


def read_answers(sheet: Path) -> int:
    """사용자가 표에 적은 답을 읽는다 — `그대로`는 답 기록에 남기고, 고칠 것은 목록으로 돌려준다.

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
    kept, edits, waiting, refused = [], [], [], []
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
        lines = read_doc(p).splitlines()
        # 표를 만든 뒤 위에 줄이 늘거나 줄었으면 같은 글의 줄을 찾아간다
        now = next((i for i, l in enumerate(lines, 1) if coverage.line_key(l) == key["line_key"]), None)
        if now is None:
            refused.append(f"{qid} {p.name} {key['line']}행 — 표를 만든 뒤 그 줄이 바뀌었습니다 · "
                           "표를 다시 만들어 다시 묻습니다")
            continue
        if kind == ask_sheet.EDIT:
            phrases = [str(a.get("phrase") or "") for n, a in
                       coverage.open_asks(coverage.doc_key(p), lines, LOG) if n == now]
            edits.append(f"{qid} {p.name} {now}행 「{' · '.join(phrases)}」 — 사용자 답: {raw}")
            continue
        try:
            answer(p, [now], f"사용자 답(사람 확인 표 {sheet.name} {qid}): {raw}")
            kept.append(qid)
        except ValueError as e:
            refused.append(f"{qid} {p.name} {now}행 — {e}")
    print(f"사람 확인 표 읽음 — {sheet.name} · 행 {len(keys)}개")
    print(f"  그대로 — 답 기록에 남김 {len(kept)}건" + (f" ({' '.join(kept)})" if kept else ""))
    if edits:
        print(f"  고칠 것 {len(edits)}건 — 세션이 고친 뒤 --since 로 고친 줄을 다시 판정합니다")
        for e in edits:
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
    """
    try:
        return probe.load_client(which)
    except Exception:
        return None


def input_total(row: dict) -> int:
    """입력 토큰 전부 — 캐시에 쓴 것·읽은 것까지."""
    return sum(int(row.get(k) or 0) for k in ("input_tokens", "cache_write", "cache_read"))


def log_call(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def open_for(path: Path, since: str) -> tuple[list[int], bool]:
    """`--since` 로 판정할 줄 — (줄 번호, git 안인가). ref 를 못 풀면 ValueError.

    갈라진 지점에 있던 줄과 판정기가 이미 본 줄은 뺀다. 고친 줄은 해시가 바뀌므로
    다시 판정 대상이 된다 — 고친 말이 새 문제를 들여오는지 보는 것이 재판정의 몫이다.
    """
    lines = read_doc(path).splitlines()
    base = coverage.base_lines(path, since)
    seen = coverage.judged(coverage.doc_key(path), LOG)
    return coverage.open_lines(lines, base, seen), base is not None


def judge(path: Path, model: str, timeout: float, backend, targets: list[int] | None = None) -> dict:
    """`targets` 가 있으면 그 줄이 든 묶음만 부르고 그 줄에 달린 지적만 낸다.

    ⛔ **지적을 거르는 까닭** — 판정기는 같은 글을 다시 판정해도 지적 수가 평균 16%
       달랐다(`docs/calibration-20260929.md`). 고친 줄 하나 때문에 묶음을 다시 보내면
       안 고친 줄에서 새 지적이 나오고, 그것을 고치면 또 다시 판정하게 된다. 프롬프트는
       탐침과 같게 두고 **결과만** 거른다 — 잰 것과 도는 것이 같아야 한다.
    """
    call_messages, parse_json = backend
    text = read_doc(path)
    lines = text.splitlines()
    key = coverage.doc_key(path)
    want = set(targets) if targets is not None else None
    system = probe.SYSTEM.format(rules=probe.rules_for("guided"))
    found, calls, hidden, foreign = [], [], 0, 0
    for first, part in chunks(lines):
        if want is not None and not any(first <= n < first + len(part) for n in want):
            continue
        started = time.time()
        row = {"at": datetime.now().isoformat(timespec="seconds"), "when": time.time(),
               "doc": str(path), "key": key,
               "sha256": hashlib.sha256("\n".join(part).encode("utf-8")).hexdigest()[:16],
               "lines": f"{first}-{first + len(part) - 1}", "model": model,
               # 게이트가 「이번 가지의 새 줄을 판정기가 다 봤나」를 이것으로 가른다
               "seen": coverage.seen_keys(part)}
        try:
            r = call_messages(model=model, system=system,
                              user=probe.USER.format(document=numbered(part, first)),
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
        asks = []
        for it in items:
            if isinstance(it, dict):
                it["line"] = relocate(lines, it.get("line"), str(it.get("phrase") or ""))
                # 줄을 못 찾은 지적은 남긴다 — 새 줄 것인지 모르면 보이는 쪽으로
                if want is not None and it["line"] is not None and it["line"] not in want:
                    hidden += 1
                    continue
                # ⛔ 한글이 없는 줄의 지적은 뺀다 — 이 판정기는 한글을 본다. 영문 페이지에서
                #    영어 문장을 사람 확인으로 냈는데 답 기록은 한글 줄만 받아, 배포가 풀 길
                #    없이 막힐 뻔했다(2026-10-06 사이트 첫 전수 판정).
                n = it["line"]
                if isinstance(n, int) and 0 < n <= len(lines) and not coverage.line_key(lines[n - 1]):
                    foreign += 1
                    continue
                found.append(it)
                if is_ask(it):
                    n = it["line"]
                    asks.append({"line_key": coverage.line_key(lines[n - 1])
                                 if isinstance(n, int) and 0 < n <= len(lines) else None,
                                 "line": n, "phrase": it.get("phrase"), "fix": it.get("fix"),
                                 "why": it.get("why"), "category": it.get("category")})
        # 발행 직전 검사가 「사용자 답을 아직 못 받은 지적」을 이것으로 가른다
        row["asks"] = asks
        log_call(row)
        calls.append(row)
    freq = load_freq()
    doc_lemmas = set(_lemmas(text)) if freq is not None else set()
    for it in found:
        it["fix_notes"] = fix_notes(str(it.get("fix") or ""), str(it.get("phrase") or ""),
                                    doc_lemmas, freq)
    return {"doc": str(path), "findings": found, "calls": calls, "fix_checked": freq is not None,
            "targets": None if want is None else len(want), "hidden": hidden, "foreign": foreign}


def show(result: dict) -> None:
    calls = result["calls"]
    secs = sum(c.get("seconds") or 0 for c in calls)
    cost = sum(c.get("cost_usd") or 0 for c in calls)
    tin = sum(input_total(c) for c in calls)
    tout = sum(c.get("output_tokens") or 0 for c in calls)
    # Codex 는 금액을 안 준다 — 0.00달러로 찍으면 공짜로 읽힌다
    priced = any(c.get("cost_usd") is not None for c in calls)
    money = f"환산 {cost:.2f}달러(구독 · 청구액 아님)" if priced else "금액 없음(Codex 구독 · 토큰만 기록)"
    print(f"── 2층 판정 · {Path(result['doc']).name} · 지적 {len(result['findings'])}건 · "
          f"호출 {len(calls)}회 · {secs:.0f}초 · 토큰 입력 {tin:,} · 출력 {tout:,} · {money}")
    if result.get("targets") is not None:
        if not result["targets"]:
            print("  판정할 새 줄 없음 — 갈라진 지점 뒤 새 줄을 판정기가 모두 봤습니다")
        else:
            print(f"  새 줄 {result['targets']}개만 판정 · 그 밖의 줄에 달린 지적 "
                  f"{result.get('hidden', 0)}건은 숨김(이미 판정했거나 갈라진 지점에 있던 줄)")
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
            print(f"  {str(f.get('line') or '?'):>4}행  「{f.get('phrase')}」 — "
                  f"{f.get('category')} → {f.get('fix')}")
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
    print("  ⚠️ 지적마다 맞는지 판단한다 — 헛짚음이 섞인다. 고치지 않은 지적은 까닭을 남긴다.")
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
    a = ap.parse_args(argv)
    if a.cost:
        cost_report(a.by)
        return 0
    if a.answers_from:
        return read_answers(Path(a.answers_from))
    if not a.docs:
        ap.print_usage()
        return 2
    if a.sheet:
        missing = [d for d in a.docs if not Path(d).is_file()]
        if missing:
            print(f"⛔ 파일 없음 — {missing[0]}")
            return 2
        out = Path(a.sheet)
        rows, asks = write_sheet([Path(d) for d in a.docs], out)
        print(f"사람 확인 표 — 줄 {rows}개 · 지적 {asks}건 · {out.resolve().as_uri()}")
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
        targets = None
        if a.since:
            try:
                targets, in_git = open_for(p, a.since)
            except ValueError as e:
                print(f"⛔ {e}")
                return 2
            if not in_git:
                print(f"  {p.name} — git 밖 문서라 갈라진 지점이 없습니다 · 아직 판정 안 한 한글 줄을 모두 봅니다")
        try:
            results.append(judge(p, model, a.timeout, backend, targets))
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
