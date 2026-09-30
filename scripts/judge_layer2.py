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

    python -X utf8 scripts/judge_layer2.py <문서…> [--model opus] [--json 경로]
    python -X utf8 scripts/judge_layer2.py --cost [--by day|month|doc]

종료 코드 — 0 돌았음(지적은 사람이 본다) · 2 사용법 · 3 호출 백엔드 없음
(세션이 규칙을 직접 읽는다) · 4 호출 실패
"""

from __future__ import annotations

import argparse
import hashlib
import html.parser
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

import probe_layer2_kinds as probe  # noqa: E402

LOG = Path(os.environ.get("KOREAN_QA_JUDGE_LOG")
           or Path.home() / ".claude" / "state" / "korean-layer2-judge.jsonl")
#: 한 번에 넘기는 줄 수 — 탐침에서 문서가 길어지면 회수가 흔들렸다(17 → 29건).
#: 넘으면 제목 경계에서 나눈다.
CHUNK_LINES = 180
DEFAULT_MODEL = "opus"      # 점검표에서 Sonnet 은 일상 동사 묶음 4/7 · Opus 6/7


class _Text(html.parser.HTMLParser):
    """HTML 에서 사람이 읽는 글만 줄 단위로 뽑는다 — script·style 은 뺀다."""

    BLOCK = {"p", "li", "dd", "dt", "td", "th", "tr", "h1", "h2", "h3", "h4",
             "h5", "h6", "div", "section", "article", "br", "pre", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def read_doc(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in (".html", ".htm"):
        p = _Text()
        p.feed(text)
        lines = [re.sub(r"\s+", " ", l).strip() for l in "".join(p.parts).splitlines()]
        return "\n".join(l for l in lines if l)
    return text


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
        from kiwipiepy import Kiwi
        _kiwi = Kiwi()
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


def load_backend():
    """정본은 `llm_playbook.backends` 하나다 — 없으면 None(세션이 직접 읽는다)."""
    try:
        from llm_playbook.backends.claude_sdk import call_messages, parse_json_from_text
    except Exception:
        return None
    return call_messages, parse_json_from_text


def input_total(row: dict) -> int:
    """입력 토큰 전부 — 캐시에 쓴 것·읽은 것까지."""
    return sum(int(row.get(k) or 0) for k in ("input_tokens", "cache_write", "cache_read"))


def log_call(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def judge(path: Path, model: str, timeout: float, backend) -> dict:
    call_messages, parse_json = backend
    text = read_doc(path)
    lines = text.splitlines()
    system = probe.SYSTEM.format(rules=probe.rules_for("guided"))
    found, calls = [], []
    for first, part in chunks(lines):
        started = time.time()
        row = {"at": datetime.now().isoformat(timespec="seconds"), "doc": str(path),
               "sha256": hashlib.sha256("\n".join(part).encode("utf-8")).hexdigest()[:16],
               "lines": f"{first}-{first + len(part) - 1}", "model": model}
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
        log_call(row)
        calls.append(row)
        for it in items:
            if isinstance(it, dict):
                it["line"] = relocate(lines, it.get("line"), str(it.get("phrase") or ""))
                found.append(it)
    freq = load_freq()
    doc_lemmas = set(_lemmas(text)) if freq is not None else set()
    for it in found:
        it["fix_notes"] = fix_notes(str(it.get("fix") or ""), str(it.get("phrase") or ""),
                                    doc_lemmas, freq)
    return {"doc": str(path), "findings": found, "calls": calls, "fix_checked": freq is not None}


def show(result: dict) -> None:
    calls = result["calls"]
    secs = sum(c.get("seconds") or 0 for c in calls)
    cost = sum(c.get("cost_usd") or 0 for c in calls)
    tin = sum(input_total(c) for c in calls)
    tout = sum(c.get("output_tokens") or 0 for c in calls)
    print(f"── 2층 판정 · {Path(result['doc']).name} · 지적 {len(result['findings'])}건 · "
          f"호출 {len(calls)}회 · {secs:.0f}초 · 토큰 입력 {tin:,} · 출력 {tout:,} · "
          f"환산 {cost:.2f}달러(구독 · 청구액 아님)")
    for f in sorted(result["findings"], key=lambda f: (f.get("line") or 0)):
        print(f"  {str(f.get('line') or '?'):>4}행  「{f.get('phrase')}」 — "
              f"{f.get('category')} → {f.get('fix')}")
        if f.get("why"):
            print(f"         {f['why']}")
        for note in f.get("fix_notes") or []:
            print(f"         ⚠️ {note}")
    if not result.get("fix_checked", True):
        print("  ⚠️ 형태소 분석기가 없어 고친 말의 드문 낱말을 안 봤습니다(지시어·형식은 봄)")
    print("  ⚠️ 지적마다 맞는지 판단한다 — 헛짚음이 섞인다. 고치지 않은 지적은 까닭을 남긴다.")


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
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--json", help="지적을 JSON 으로도 씀")
    ap.add_argument("--cost", action="store_true", help="누적 비용 보기")
    ap.add_argument("--by", choices=("day", "month", "doc"), default="day")
    a = ap.parse_args(argv)
    if a.cost:
        cost_report(a.by)
        return 0
    if not a.docs:
        ap.print_usage()
        return 2
    backend = backend or load_backend()
    if backend is None:
        print("⛔ 2층 판정 호출을 못 합니다 — llm_playbook 이 없습니다. "
              "판단 규칙과 9단계를 세션이 직접 읽고 판정합니다.")
        return 3
    results = []
    for d in a.docs:
        p = Path(d)
        if not p.is_file():
            print(f"⛔ 파일 없음 — {d}")
            return 2
        try:
            results.append(judge(p, a.model, a.timeout, backend))
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
