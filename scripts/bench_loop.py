"""회귀 시료를 한 문서로 합쳐 2층 판정 고리를 끝까지 돌린다 — 반복과 정확도를 같은 입력으로 잰다.

**왜 필요한가** (2026-10-13) — 하루에 커밋 열여섯 개를 내고 「호출이 줄어듦」을 적었지만, 같은 일감으로
잰 적이 없었다. 다른 문서끼리 견주니 README 판정 호출이 오히려 4회에서 10회로 늘어 있었다. 사례별로
나뉜 회귀 시료를 한 문서로 합쳐 「판정 → 수정안 적용 → 고친 줄 재판정」을 끝까지 돌리면, 같은 입력으로
반복이 재현된다.

**판정기는 실행마다 크게 흔들린다** — 같은 문서의 0회차 지적이 136건과 169건, 판정기 글 재지적이 17건과
54건이었다. 그래서 한 번 잰 값으로 효과를 말하지 않는다. 기준과 후보를 각각 세 번 이상 돌리고 아래
`PREREGISTERED` 의 규칙으로만 견준다. 규칙은 그 판의 기준선을 재기 전에 적는다 — 결과를 보고 고치면 탐색적이다.

**재는 것이 목표 그 자체는 아니다**(2판 · 2026-10-15) — 최종 목표는 구독 사용량과 수행 시간이다. 환산 비용
(CLI 의 `total_cost_usd` · 청구액 아님)은 대리 지표이고, 구독 사용량과 비례한다는 근거는 없다(외부 검토).
그래서 셋을 따로 적는다 — 환산 비용과 캐시 쓰기 · 읽기 · 출력, 실제 걸린 시간, 그리고 SDK 가 호출마다 주는
구독 사용률(5시간 · 7일 창, 1% 단위라 거칠다). 1판은 출력 토큰 하나로 판정했는데 실사용 환산 비용의 약
60% 가 캐시 쓰기였다.

    python -X utf8 scripts/bench_loop.py run <이름> [--times 3] [--policy all|known] [--rounds 6] [--limit N]
    python -X utf8 scripts/bench_loop.py compare <기준 이름> <후보 이름>

- **문서** — 사용자가 짚은 표현 대장의 문장(`data/cases/flagged-rounds.jsonl`)과 기여 시료의 정상 문장
  (`data/cases/contributed.jsonl` 의 expect=clean). 시료마다 한 줄 · 순서 고정. 머리말 `form: prose` —
  목록 항목이 모두 「~합니다.」라 형식 검사가 줄마다 걸려 1층이 시료를 잡았는지 셀 수 없었다(2판).
- **고리** — 전체 판정 → 수정안 적용 → 판정 안 한 줄만 다시 판정(`--since main`). 지적이 없거나, 적용할
  수정안이 없거나, 판정할 새 줄이 없으면 끝. 같은 줄 4번째 재판정의 사람 확인 넘김은 판정기 안에서 일어나
  실사용과 같다 — 넘긴 지적은 적용하지 않으므로 `--rounds` 는 그 위의 안전 상한이다.
- **정책** — all = 고칠 지적의 수정안을 모두 적용(세션이 판정기를 그대로 따를 때 · 스트레스 시험) ·
  known = 짚은 문장 줄만 적용(정상 줄 지적은 세기만 함).
- **격리** — 판정 · 답 · 사용자 결정 · 처리 기록을 실행 폴더에 따로 둔다. 쌓인 사용자 답이 프롬프트에
  섞이면 실행마다 입력이 달라진다.
- **결과** — `<--out>/<이름>/<시각>/summary.json`. 기본 폴더는 저장소 밖(`~/.claude/state/korean-bench`).
- **기준과 후보를 번갈아 돌리려면** — 후보 코드를 다른 작업 트리에 두고 그 트리의 이 파일로 돌린다(각자 자기
  저장소의 판정기를 불러온다). 같은 시간대에 번갈아 돌려야 한도 · 캐시 상태 차이가 한쪽에 몰리지 않는다.
- ⛔ **정상 줄 지적은 오탐률이 아니다** — 정상 시료는 1층에서 정상인 문장이라 2층 결함이 섞여 있다.
- ⛔ **판정기를 실제로 부른다** — 구독 한도를 쓴다(한 번에 출력 6만여 토큰 · 9분 안팎 · 환산 1.7~2.3달러,
  2026-10-14 실측). 7일 창이 차 있으면 다른 업무 세션까지 멈출 수 있으니 돌리기 전에 사용률을 본다.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402

CHECKER = ROOT / "assets" / "doc-style-check.py"
OUT = Path.home() / ".claude" / "state" / "korean-bench"
TOTAL = re.compile(r"합계 — 오류 (\d+) · 주의 (\d+)")
#: 검사기 출력의 지적 줄 — 「   ❌ [갈래] 12행  …」 · 「   ⚠️ [갈래] 12행  …」
CHECKER_HIT = re.compile(r"^\s*(?:❌|⚠️)\s*\[[^\]]+\]\s*(\d+)행")
HEAD = ["---", "form: prose", "---"]

#: 비교 규칙 2판 — 2판 기준선을 재기 전에 적었다(2026-10-15). 1판(출력 토큰 하나로 판정)은 git 이력에 남는다.
PREREGISTERED = {
    # 한쪽에 완주한 실행이 이보다 적으면 판정 불가 · 많으면 탐색적(앞 결과를 보고 더 돌린 것일 수 있다)
    "runs": 3,
    # 목표에 가까운 대리 지표 둘 — 낮을수록 좋다. 하나라도 범위가 겹치지 않게 낮고, 어느 쪽도 겹치지 않게
    # 높지 않을 때만 개선. 셋 대 셋 범위 비겹침은 탐색용의 보수적 규칙이지 통계적 보장이 아니다(외부 검토).
    "targets": ["환산 비용", "걸린 시간"],
    # 같이 적되 판정에 안 쓰는 값
    "report": ["출력 토큰", "캐시 쓰기", "캐시 읽기", "호출", "회차", "판정기 글 재지적", "되돌림", "상한 올림",
               "사람 확인", "자리표시", "사실 확인", "5시간 사용률 변화",
               # 세션 흉내에서만 나오는 값 — 사람 · 세션 몫
               "사람 답", "사실 확인 닫기", "지시반영 닫기", "같은 근거 다시 닫기", "대상 3줄 이하 재판정",
               "지시 안 뜻 바뀜 짚은 줄", "지시 밖 짚은 줄"],
    # 정확도 — 후보 최솟값이 기준 최솟값보다 이만큼 넘게 낮으면 악화(낭비가 줄어도 개선으로 안 봄).
    # 1판은 1층 담당 시료까지 2층 회수로 세어 두 층의 책임을 섞었다 — 2층 담당은 2층 회수로, 전체는 1층과
    # 2층을 합친 회수로 본다.
    "guard_floor": {"0회차 회수(2층)": 2, "통합 회수(짚음)": 1},
    # 끝난 문서의 1층 오류 — 후보 최댓값이 기준 최댓값보다 이만큼 넘게 많으면 악화
    "guard_ceiling": {"1층 오류(끝)": 2},
}


def load_samples(limit: int = 0) -> tuple[list[dict], list[dict]]:
    def rows(rel: str) -> list[dict]:
        return [json.loads(l) for l in (ROOT / rel).read_text(encoding="utf-8").splitlines() if l.strip()]
    flagged = rows("data/cases/flagged-rounds.jsonl")
    clean = [c for c in rows("data/cases/contributed.jsonl") if c.get("expect") == "clean"]
    return (flagged[:limit], clean[:limit]) if limit else (flagged, clean)


def load_edits() -> list[dict]:
    """사용자 지시로 뜻을 일부러 바꾸는 편집 — 지어낸 문장(`data/cases/instructed-edits.jsonl`)."""
    p = ROOT / "data" / "cases" / "instructed-edits.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def build_doc(flagged: list[dict], clean: list[dict],
              edits: list[dict] = ()) -> tuple[list[str], dict[int, dict]]:
    """(줄들, 줄 번호 → 시료). 시료 순서를 바꾸면 다른 일감이 된다."""
    lines = HEAD + ["# 회귀 시료 묶음", "", "검사기 회귀 시료 — 사용자가 짚은 문장과 정상 문장을 한 문서로 모았습니다.", "",
                    "## 짚은 문장", ""]
    meta: dict[int, dict] = {}
    for r in flagged:
        lines.append("- " + " ".join(str(r["sentence"]).split()))
        meta[len(lines)] = {"kind": "짚음", "id": r["flag_id"], "owner": r.get("owner")}
    lines += ["", "## 정상 문장", ""]
    for c in clean:
        lines.append("- " + " ".join(str(c["text"]).split()))
        meta[len(lines)] = {"kind": "정상", "id": c["case_id"], "owner": None}
    if edits:
        lines += ["", "## 지시로 고칠 문장", ""]
        for e in edits:
            lines.append("- " + e["before"])
            meta[len(lines)] = {"kind": "지시", "id": e["edit_id"], "owner": None, "scope": e.get("scope", "in"),
                                "after": "- " + e["after"], "instruction": e["instruction"]}
    return lines, meta


@contextlib.contextmanager
def isolated(folder: Path):
    """판정 · 답 · 결정 · 처리 기록을 실행 폴더로 돌린다 — 끝나면 원래대로."""
    spots = [(judge, "LOG", "judge.jsonl"), (coverage, "LOG", "judge.jsonl"),
             (coverage, "ANSWERS", "answers.jsonl"), (coverage, "DECISIONS", "decisions.jsonl"),
             (coverage, "DISMISSALS", "dismissals.jsonl"), (coverage, "INSTRUCTIONS", "instructions.jsonl")]
    saved = [getattr(m, name) for m, name, _ in spots]
    for m, name, file in spots:
        setattr(m, name, folder / file)
    try:
        yield
    finally:
        for (m, name, _), value in zip(spots, saved):
            setattr(m, name, value)


@contextlib.contextmanager
def watch_limits(seen: list[dict]):
    """SDK 가 호출마다 주는 구독 사용률을 모은다 — `seen` 에 {창: 사용률}. Claude 백엔드가 없으면 빈 채로 둔다.

    판정기 백엔드는 사용량 네 칸만 넘기고 이 사건은 버린다. 그래서 SDK 의 질의 함수를 감싸 엿본다.
    """
    try:
        from llm_playbook.backends import claude_sdk
    except ImportError:
        yield
        return
    real = claude_sdk.query

    async def spy(*a, **kw):
        async for m in real(*a, **kw):
            info = getattr(m, "rate_limit_info", None)
            raw = getattr(info, "raw", None) if info is not None else None
            if isinstance(raw, dict):
                wins = raw.get("unifiedWindows") or {}
                seen.append({k: v.get("utilization") for k, v in wins.items() if isinstance(v, dict)})
            yield m

    claude_sdk.query = spy
    try:
        yield
    finally:
        claude_sdk.query = real


def _alive(pid: int) -> bool:
    try:
        import psutil
    except ImportError:     # 모르면 살아 있다고 본다 — 판정이 겹치는 쪽이 더 비싸다
        return True
    return psutil.pid_exists(pid)


@contextlib.contextmanager
def locked(folder: Path):
    """같은 이름을 둘이 동시에 돌리지 않는다 — 한도로 멈춘 줄 안 실행이 살아 있어 판정이 겹친 적이 있다."""
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / "bench.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        pid = int((lock.read_text(encoding="utf-8").strip() or "0"))
        if _alive(pid):
            raise RuntimeError(f"이미 도는 실행이 있습니다 — {lock} (pid {pid})") from None
        lock.unlink()
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def layer1(path: Path) -> tuple[int | None, set[int]]:
    """(1층 오류 수, 오류나 주의가 난 줄 번호)."""
    out = subprocess.run([sys.executable, "-X", "utf8", str(CHECKER), str(path), "--no-rules", "--new-doc"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    m = TOTAL.search(out)
    hits = {int(h.group(1)) for line in out.splitlines() if (h := CHECKER_HIT.match(line))}
    return (int(m.group(1)) if m else None), hits


def end_state(finished: bool, rows: list[dict], rounds: int) -> str:
    """고리가 어떻게 끝났나 — 싸게 실패한 실행을 개선으로 읽지 않게 함께 적는다."""
    if not finished:
        return "실패"
    last = rows[-1] if rows else {}
    if not last.get("지적"):
        return "수렴"
    if not last.get("적용") and last.get("사람 확인") == last.get("지적"):
        return "사람 이관"
    if last.get("적용") and len(rows) == rounds + 1:
        return "회차 상한"
    return "적용할 것 없음"


def run_once(folder: Path, flagged: list[dict], clean: list[dict], policy: str = "all",
             rounds: int = 6, backend=None, echo=None, context: str = judge.DEFAULT_CONTEXT) -> dict:
    """한 번 돌리고 {"rounds": 회차별 값, "total": 합계}를 `folder/summary.json` 에도 쓴다."""
    folder.mkdir(parents=True)
    lines, meta = build_doc(flagged, clean)
    doc = folder / "bench.md"
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "start.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@localhost", "-C", str(folder), *args],
                       capture_output=True, check=True)
    git("init", "-q", "-b", "main")
    git("add", "bench.md")
    git("commit", "-q", "-m", "base")
    git("switch", "-q", "-c", "work")

    history: dict[int, list[str]] = {}       # 줄 번호 → 거쳐 간 글
    written: dict[int, list[str]] = {}       # 바로 앞 회차에 판정기 수정안으로 쓴 말
    first_hits: set[int] = set()
    first_fixes: list[dict] = []
    rows, finished, said, limits = [], True, io.StringIO(), []
    started = time.time()
    with isolated(folder), watch_limits(limits):
        for rnd in range(rounds + 1):
            out = folder / f"round{rnd}.json"
            argv = [str(doc), "--json", str(out)] + (["--since", "main", "--context", context] if rnd else [])
            with contextlib.redirect_stdout(said):
                rc = judge.main(argv, backend=backend)
            if rc != 0 or not out.is_file():
                finished = False
                break
            res = json.loads(out.read_text(encoding="utf-8"))[0]
            found, calls = res["findings"], res["calls"]
            cur = doc.read_text(encoding="utf-8").splitlines()
            applied = skipped = own = reverted = clean_hits = 0
            now_written: dict[int, list[str]] = {}
            for f in sorted(found, key=lambda f: f.get("line") or 0):
                n, phrase, fix = f.get("line"), str(f.get("phrase") or ""), str(f.get("fix") or "")
                kind = meta[n]["kind"] if n in meta else "?"
                clean_hits += kind == "정상"
                if rnd == 0 and isinstance(n, int):
                    first_hits.add(n)
                    if not judge.is_ask(f):
                        first_fixes.append(f)
                if n in written and phrase and any(phrase in w or w in phrase for w in written[n]):
                    own += 1
                if judge.is_ask(f) or (policy == "known" and kind != "짚음"):
                    continue
                if not (isinstance(n, int) and 0 < n <= len(cur)) or not phrase or not fix \
                        or fix.startswith("(") or "\n" in fix or phrase not in cur[n - 1]:
                    skipped += 1
                    continue
                before = cur[n - 1]
                after = before.replace(phrase, fix, 1)
                if after == before:
                    skipped += 1
                    continue
                history.setdefault(n, [before])
                reverted += after in history[n]
                history[n].append(after)
                cur[n - 1] = after
                now_written.setdefault(n, []).append(fix)
                applied += 1
            doc.write_text("\n".join(cur) + "\n", encoding="utf-8")
            written = now_written
            row = {"회차": rnd, "호출": len(calls), "대상 줄": res.get("targets") if rnd else "전체",
                   "지적": len(found), "정상 줄 지적": clean_hits, "적용": applied, "적용 못함": skipped,
                   "사람 확인": sum(1 for f in found if judge.is_ask(f)),
                   "상한 올림": sum(1 for f in found if f.get("held")),
                   "뜻 바뀜": sum(1 for f in found if "뜻이 바뀐" in str(f.get("category") or "")),
                   "판정기 글 재지적": own, "되돌림": reverted,
                   "출력 토큰": sum(c.get("output_tokens") or 0 for c in calls),
                   "캐시 쓰기": sum(c.get("cache_write") or 0 for c in calls),
                   "캐시 읽기": sum(c.get("cache_read") or 0 for c in calls),
                   "환산 비용": round(sum(c.get("cost_usd") or 0 for c in calls), 4),
                   "초": round(sum(c.get("seconds") or 0 for c in calls))}
            rows.append(row)
            if echo:
                echo(json.dumps(row, ensure_ascii=False))
            if not found or not applied:
                break
    elapsed = round(time.time() - started)
    (folder / "judge-output.txt").write_text(said.getvalue(), encoding="utf-8")

    flagged_at = {n for n, m in meta.items() if m["kind"] == "짚음"}
    owned = {o: {n for n in flagged_at if meta[n]["owner"] == o} for o in ("2층", "규칙", "단어 점검")}
    clean_at = {n for n, m in meta.items() if m["kind"] == "정상"}
    errors_start, checker_hits = layer1(folder / "start.md")
    errors_end, _ = layer1(doc)
    five = [w.get("five_hour") for w in limits if w.get("five_hour") is not None]
    week = [w.get("seven_day") for w in limits if w.get("seven_day") is not None]
    total = {"정책": policy, "문맥": context, "완주": finished, "종료": end_state(finished, rows, rounds),
             "시료": {"짚음": len(flagged_at), **{f"짚음({o})": len(s) for o, s in owned.items()},
                    "정상": len(clean_at)},
             "회차": sum(1 for r in rows if r["호출"]),
             **{k: sum(r[k] for r in rows) for k in ("호출", "출력 토큰", "캐시 쓰기", "캐시 읽기", "초",
                                                    "사람 확인", "상한 올림", "판정기 글 재지적", "되돌림")},
             "환산 비용": round(sum(r["환산 비용"] for r in rows), 4),
             "걸린 시간": elapsed,
             "0회차 회수(짚음)": len(first_hits & flagged_at),
             **{f"0회차 회수({o})": len(first_hits & s) for o, s in owned.items()},
             # 1층이 시작 문서에서 잡은 줄과 2층이 0회차에 짚은 줄을 합친 것 — 발행 전에 어느 층에서든 짚였나
             "1층 회수(규칙)": len(checker_hits & owned["규칙"]),
             "통합 회수(짚음)": len((first_hits | checker_hits) & flagged_at),
             "0회차 정상 줄 지적": len(first_hits & clean_at),
             "정상 줄 지적(전 회차)": sum(r["정상 줄 지적"] for r in rows),
             # 세션 · 사람 몫으로 넘어가는 일 — 판정기 출력이 줄어도 이것이 늘면 비용이 옮겨 간 것이다
             "자리표시": sum(1 for f in first_fixes if "○○" in str(f.get("fix") or "")),
             "사실 확인": sum(1 for f in first_fixes if coverage.needs_check(f)),
             "1층 오류(처음)": errors_start, "1층 오류(끝)": errors_end,
             "5시간 사용률": [five[0], five[-1]] if five else None,
             "5시간 사용률 변화": round(five[-1] - five[0], 2) if len(five) > 1 else None,
             "7일 사용률": [week[0], week[-1]] if week else None,
             "가장 많이 고친 줄": sorted(([len(v) - 1, n, meta[n]["kind"] if n in meta else "?"]
                                     for n, v in history.items()), reverse=True)[:5]}
    summary = {"rounds": rows, "total": total}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


#: 세션 흉내의 사람 확인 답 열쇠 — 판정기 제안대로 고침(사용자는 넘긴 61건 중 52건을 그렇게 답했다 · 2026-10-07)
SESSION_ANSWER = "고침 — 재현 일감의 답 열쇠"


def apply_fix(line: str, phrase: str, fix: str) -> str:
    """수정안을 줄에 넣는다 — 수정안이 짚은 표현의 앞뒤 글자까지 담고 있으면 겹친 만큼 넓혀 바꾼다.

    (2026-10-19) 표현 「엔진 실행 파일로 끝까지 실행」에 수정안이 「시나리오 1종이 엔진 실행 파일에서 끝까지
    실행됨」이었다. 글자 그대로 바꾸자 「시나리오 1종이 시나리오 1종이 … 실행됨됨」이 됐고, 판정기가 되돌리라고
    짚어 두 판을 오가며 끝나지 않았다. 세션은 이렇게 넣지 않는다.
    """
    i = line.index(phrase)
    before, after = line[:i], line[i + len(phrase):]
    k = max((n for n in range(1, min(len(before), len(fix)) + 1) if before.endswith(fix[:n])), default=0)
    m = max((n for n in range(1, min(len(after), len(fix) - k) + 1) if after.startswith(fix[-n:])), default=0)
    return before[:len(before) - k] + fix + after[m:]


def process(doc: Path, meta: dict[int, dict], mode: str, counts: dict,
            history: dict[int, set] | None = None) -> int:
    """열린 지적을 세션처럼 처리한다 — 글을 바꾼 수. `one` 이면 글을 하나 바꾸면 멈춘다(작은 재판정 재현).

    - 사람 확인: 답 열쇠(고침)로 답한다. 수정안을 글자로 넣을 수 있으면 넣고 그 글을 확정(다시 판정 안 함),
      못 넣으면 「그대로」로 답한다. 줄 하나에 답 하나 — 사람 확인 표가 줄 단위다
    - 사실 확인 지적: 수정안을 넣지 않고 「확인함」으로 닫는다(자료로 확인했다고 본다)
    - 지시로 바꾼 줄의 「뜻이 바뀐 곳」: 지시 원문을 옮겨 「지시반영」으로 닫는다
    - 그 밖의 고칠 지적: 수정안을 넣는다 · 글자로 못 넣으면 「대상아님」으로 닫는다(세션이 손으로 고친 셈)
    - 넣으면 그 줄이 이 실행에서 가졌던 판으로 되돌아가는 수정안: 넣지 않고 닫는다(`history` · 줄 번호별
      지난 판). 예전 판으로 돌아가면 그때 남은 지적이 다시 열려 두 판을 오간다
    """
    key = coverage.doc_key(doc)
    edits = 0
    history = history if history is not None else {}
    for _ in range(2000):
        lines = doc.read_text(encoding="utf-8").splitlines()
        asks = coverage.open_asks(key, lines, judge.LOG)
        fixes = coverage.open_fixes(key, lines, judge.LOG)
        todo = sorted([(n, "ask", a) for n, a in asks] + [(n, "fix", f) for n, f in fixes], key=lambda x: (x[0], x[1]))
        if not todo or (mode == "one" and edits):
            return edits
        n, what, item = todo[0]
        if what == "ask":
            on = [a for m, a in asks if m == n]
            counts["사람 답"] += 1
            settled = judge.edited_by_answer(lines[n - 1], on)
            if settled:
                for k in {a.get("line_key") for a in on}:
                    judge.record_decision(doc, k, SESSION_ANSWER, judge.ask_sheet.EDIT, "bench", lines[n - 1])
                judge.approve(doc, settled, SESSION_ANSWER, coverage.line_key(lines[n - 1]))
                lines[n - 1] = settled
                doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
                edits += 1
            else:
                judge.answer(doc, [n], "재현 일감의 답 열쇠: 그대로")
            continue
        category = str(item.get("category") or "")
        phrase, fix = str(item.get("phrase") or ""), str(item.get("fix") or "")
        if meta.get(n, {}).get("kind") == "지시" and judge.INTENT_ONLY in category:
            if meta[n].get("scope") == "out":     # 지시 밖 변경을 짚은 것 — 세션이 그 부분을 바로잡았다고 본다
                counts["지시 밖 짚음 처리"] += 1
                judge._close_fix(doc, lines, n, item, {"reason": "대상아님", "note": "재현 일감 — 지시 밖 변경을 짚음"})
            else:
                counts["지시반영 닫기"] += 1
                judge._close_fix(doc, lines, n, item, {"reason": "지시반영",
                                                       "note": f"사용자 지시 「{meta[n]['instruction']}」(재현 일감)"})
        elif coverage.needs_check(item):
            counts["사실 확인 닫기"] += 1
            judge._close_fix(doc, lines, n, item, {"reason": "확인함", "note": "재현 일감 — 자료로 확인했다고 본다"})
        elif phrase and fix and not fix.startswith("(") and "\n" not in fix and phrase in lines[n - 1]:
            new = apply_fix(lines[n - 1], phrase, fix)
            past = history.setdefault(n, set())
            if new in past:
                counts["되돌림 닫기"] = counts.get("되돌림 닫기", 0) + 1
                judge._close_fix(doc, lines, n, item, {"reason": "대상아님",
                                                       "note": "재현 일감 — 앞선 판으로 되돌리는 수정안"})
                continue
            counts["적용"] += 1
            past.add(lines[n - 1])
            lines[n - 1] = new
            doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
            edits += 1
        else:
            counts["적용 못함 닫기"] += 1
            judge._close_fix(doc, lines, n, item, {"reason": "대상아님", "note": "재현 일감 — 기계로 넣을 수 없는 수정안"})
    raise RuntimeError("처리가 끝나지 않습니다 — 닫은 지적이 다시 열리는지 봅니다")


def reclosed(dismissals: Path) -> int:
    """같은 표현을 같은 사유로 다른 줄 해시에 다시 닫은 횟수 — 줄을 고칠 때마다 사실 확인이 다시 열린 몫."""
    seen: dict[tuple, set] = {}
    if dismissals.is_file():
        for l in dismissals.read_text(encoding="utf-8").splitlines():
            r = json.loads(l)
            seen.setdefault((r.get("phrase"), r.get("reason")), set()).add(r.get("line_key"))
    return sum(len(v) - 1 for v in seen.values())


def run_session(folder: Path, flagged: list[dict], clean: list[dict], edits: list[dict], mode: str = "batch",
                max_calls: int = 60, backend=None, echo=None, context: str = judge.DEFAULT_CONTEXT,
                instructions: bool = False) -> dict:
    """세션처럼 처리하며 고리를 돈다 — 실사용 흐름 재생(외부 검토의 둘째 트랙). 「전부 적용」은 스트레스 시험이다.

    0회차를 처리한 뒤 사용자 지시 편집을 넣는다. `batch` 는 열린 지적을 다 처리하고 다시 판정하고, `one` 은 글을
    하나 고칠 때마다 다시 판정한다 — 실사용 재판정의 60% 가 대상 3줄 이하였다(10/07~10/14).
    """
    folder.mkdir(parents=True)
    lines, meta = build_doc(flagged, clean, edits)
    doc = folder / "bench.md"
    doc.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (folder / "start.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@localhost", "-C", str(folder), *args],
                       capture_output=True, check=True)
    git("init", "-q", "-b", "main")
    git("add", "bench.md")
    git("commit", "-q", "-m", "base")
    git("switch", "-q", "-c", "work")

    counts: dict[str, int] = {k: 0 for k in ("사람 답", "사실 확인 닫기", "지시반영 닫기", "지시 밖 짚음 처리", "적용",
                                             "적용 못함 닫기", "되돌림 닫기")}
    history: dict[int, set] = {}
    rows, limits, said = [], [], io.StringIO()
    first_hits: set[int] = set()
    first_fixes: list[dict] = []
    finished, state, calls_total = True, "멈춤", 0
    started = time.time()
    with isolated(folder), watch_limits(limits):
        for rnd in range(10_000):
            if calls_total >= max_calls:
                state = "호출 상한"
                break
            out = folder / f"round{rnd}.json"
            argv = [str(doc), "--json", str(out)] + (["--since", "main", "--context", context] if rnd else [])
            with contextlib.redirect_stdout(said):
                rc = judge.main(argv, backend=backend)
            if rc != 0 or not out.is_file():
                finished, state = False, "실패"
                break
            res = json.loads(out.read_text(encoding="utf-8"))[0]
            calls = res["calls"]
            calls_total += len(calls)
            if rnd == 0:
                first_hits = {f["line"] for f in res["findings"] if isinstance(f.get("line"), int)}
                first_fixes = [f for f in res["findings"] if not judge.is_ask(f)]
            did = process(doc, meta, mode, counts, history)
            if rnd == 0:
                cur = doc.read_text(encoding="utf-8").splitlines()
                for n, m in meta.items():
                    if m["kind"] == "지시":
                        cur[n - 1] = m["after"]
                        did += 1
                doc.write_text("\n".join(cur) + "\n", encoding="utf-8")
                if instructions:      # 세션이 지시를 기록한 뒤 다시 판정한다(--instructed)
                    for n, m in meta.items():
                        if m["kind"] == "지시":
                            judge.instruct(doc, n, f"사용자 지시 「{m['instruction']}」(재현 일감)")
            row = {"회차": rnd, "호출": len(calls), "대상 줄": res.get("targets") if rnd else "전체",
                   "지적": len(res["findings"]), "글 바꿈": did,
                   "출력 토큰": sum(c.get("output_tokens") or 0 for c in calls),
                   "캐시 쓰기": sum(c.get("cache_write") or 0 for c in calls),
                   "캐시 읽기": sum(c.get("cache_read") or 0 for c in calls),
                   "환산 비용": round(sum(c.get("cost_usd") or 0 for c in calls), 4),
                   "초": round(sum(c.get("seconds") or 0 for c in calls))}
            rows.append(row)
            if echo:
                echo(json.dumps(row, ensure_ascii=False))
            if not did:
                now = doc.read_text(encoding="utf-8").splitlines()
                key = coverage.doc_key(doc)
                left = (coverage.open_lines(now, lines, coverage.judged(key, judge.LOG))
                        or coverage.open_fixes(key, now, judge.LOG) or coverage.open_asks(key, now, judge.LOG))
                state = "멈춤" if left else "완료"
                break
        all_found = [f for p in folder.glob("round*.json") for f in json.loads(p.read_text(encoding="utf-8"))[0]["findings"]]
        held = sum(1 for f in all_found if f.get("held"))
        # 지시로 바꾼 줄 가운데 「뜻이 바뀐 곳」을 짚은 줄 — 지시 안은 적을수록, 지시 밖은 다 짚어야 좋다
        moved = {f["line"] for f in all_found if judge.INTENT_ONLY in str(f.get("category") or "")}
        again = reclosed(coverage.DISMISSALS)
    elapsed = round(time.time() - started)
    (folder / "judge-output.txt").write_text(said.getvalue(), encoding="utf-8")

    flagged_at = {n for n, m in meta.items() if m["kind"] == "짚음"}
    owned = {o: {n for n in flagged_at if meta[n]["owner"] == o} for o in ("2층", "규칙", "단어 점검")}
    errors_start, checker_hits = layer1(folder / "start.md")
    errors_end, _ = layer1(doc)
    five = [w.get("five_hour") for w in limits if w.get("five_hour") is not None]
    week = [w.get("seven_day") for w in limits if w.get("seven_day") is not None]
    total = {"정책": f"session-{mode}", "문맥": context, "완주": finished, "종료": state,
             "회차": sum(1 for r in rows if r["호출"]),
             **{k: sum(r[k] for r in rows) for k in ("호출", "출력 토큰", "캐시 쓰기", "캐시 읽기", "초")},
             "환산 비용": round(sum(r["환산 비용"] for r in rows), 4), "걸린 시간": elapsed,
             "대상 3줄 이하 재판정": sum(1 for r in rows[1:] if r["호출"] and (r["대상 줄"] or 0) <= 3),
             **counts, "상한 올림": held, "같은 근거 다시 닫기": again, "지시 기록": instructions,
             "지시 안 뜻 바뀜 짚은 줄": len({n for n in moved if meta.get(n, {}).get("kind") == "지시"
                                          and meta[n].get("scope") != "out"}),
             "지시 밖 짚은 줄": len({n for n in moved if meta.get(n, {}).get("scope") == "out"}),
             "지시 밖 시료": sum(1 for m in meta.values() if m.get("scope") == "out"),
             "0회차 회수(짚음)": len(first_hits & flagged_at),
             **{f"0회차 회수({o})": len(first_hits & s) for o, s in owned.items()},
             "통합 회수(짚음)": len((first_hits | checker_hits) & flagged_at),
             "자리표시": sum(1 for f in first_fixes if "○○" in str(f.get("fix") or "")),
             "사실 확인": sum(1 for f in first_fixes if coverage.needs_check(f)),
             "1층 오류(처음)": errors_start, "1층 오류(끝)": errors_end,
             "5시간 사용률": [five[0], five[-1]] if five else None,
             "5시간 사용률 변화": round(five[-1] - five[0], 2) if len(five) > 1 else None,
             "7일 사용률": [week[0], week[-1]] if week else None}
    summary = {"rounds": rows, "total": total}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def runs_of(out: Path, name: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))["total"] for p in sorted((out / name).glob("*/summary.json"))]


def _verdict(bv: list, cv: list) -> str:
    return "줄어듦" if cv[-1] < bv[0] else "늘어남" if cv[0] > bv[-1] else "판정 불가(겹침)"


def compare(base: list[dict], cand: list[dict], rule: dict = PREREGISTERED) -> dict:
    """두 실행 묶음(각 실행의 total)을 미리 적은 규칙으로 견준다. 완주 못 한 실행은 뺀다."""
    b = [t for t in base if t.get("완주")]
    c = [t for t in cand if t.get("완주")]
    if len(b) < rule["runs"] or len(c) < rule["runs"]:
        return {"결론": "판정 불가",
                "까닭": f"완주한 실행이 기준 {len(b)}회 · 후보 {len(c)}회 — 각 {rule['runs']}회 이상 필요"}
    missing = [k for k in [*rule["targets"], *rule["guard_floor"], *rule["guard_ceiling"]]
               if any(t.get(k) is None for t in b + c)]
    if missing:
        return {"결론": "판정 불가", "까닭": f"규칙이 보는 값이 없는 실행이 있음 — {', '.join(missing)}(다른 판의 실행)"}
    worse = [f"{k} {min(t[k] for t in c)} < 기준 최솟값 {min(t[k] for t in b)} - {tol}"
             for k, tol in rule["guard_floor"].items() if min(t[k] for t in c) < min(t[k] for t in b) - tol]
    worse += [f"{k} {max(t[k] for t in c)} > 기준 최댓값 {max(t[k] for t in b)} + {tol}"
              for k, tol in rule["guard_ceiling"].items() if max(t[k] for t in c) > max(t[k] for t in b) + tol]
    targets = {k: {"기준": sorted(t[k] for t in b), "후보": sorted(t[k] for t in c)} for k in rule["targets"]}
    for v in targets.values():
        v["판정"] = _verdict(v["기준"], v["후보"])
    report = {k: {"기준": sorted(t[k] for t in b if t.get(k) is not None),
                  "후보": sorted(t[k] for t in c if t.get(k) is not None)} for k in rule["report"]}
    states = {"기준": [t.get("종료") for t in b], "후보": [t.get("종료") for t in c]}
    verdicts = [v["판정"] for v in targets.values()]
    if worse:
        result = "정확도 악화"
    elif "늘어남" in verdicts:
        result = "악화"
    elif "줄어듦" in verdicts:
        result = "개선"
    else:
        result = "판정 불가"
    out = {"결론": result, "정확도": worse or "유지", "목표 지표": targets, "종료": states, "참고": report}
    if len(b) > rule["runs"] or len(c) > rule["runs"]:
        out["탐색적"] = f"미리 정한 {rule['runs']}회보다 많이 돌림 — 앞 결과를 보고 더한 것이면 이 결론은 탐색적"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="회귀 시료로 2층 판정 고리를 재현")
    ap.add_argument("--out", type=Path, default=OUT, help=f"결과 폴더(기본 {OUT})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="판정기를 실제로 불러 고리를 돌림")
    r.add_argument("name")
    r.add_argument("--times", type=int, default=1)
    r.add_argument("--policy", choices=("all", "known", "session"), default="all",
                   help="all · known = 수정안 적용 스트레스 시험 · session = 세션처럼 처리(실사용 흐름 재생)")
    r.add_argument("--mode", choices=("batch", "one"), default="batch", help="session 에서 한꺼번에 · 하나씩")
    r.add_argument("--max-calls", type=int, default=60, help="session 의 판정 호출 상한")
    r.add_argument("--instructions", action="store_true", help="session 에서 지시 편집 뒤 지시를 기록(--instructed)")
    r.add_argument("--rounds", type=int, default=6)
    r.add_argument("--context", choices=judge.CONTEXT_MODES, default=judge.DEFAULT_CONTEXT, help="재판정 문맥(판정기 --context)")
    r.add_argument("--limit", type=int, default=0, help="묶음마다 앞에서부터 이만큼(0 = 전부)")
    c = sub.add_parser("compare", help="미리 적은 규칙으로 두 이름을 견줌")
    c.add_argument("base")
    c.add_argument("cand")
    a = ap.parse_args(argv)
    if a.cmd == "compare":
        print(json.dumps(compare(runs_of(a.out, a.base), runs_of(a.out, a.cand)), ensure_ascii=False, indent=1))
        return 0
    flagged, clean = load_samples(a.limit)
    with locked(a.out / a.name):
        for i in range(a.times):
            folder = a.out / a.name / datetime.now().strftime("%Y%m%d-%H%M%S")
            print(f"── {i + 1}/{a.times} · {folder}", flush=True)
            echo = lambda s: print(s, flush=True)  # noqa: E731
            got = (run_session(folder, flagged, clean, load_edits(), a.mode, a.max_calls, echo=echo, context=a.context,
                               instructions=a.instructions)
                   if a.policy == "session"
                   else run_once(folder, flagged, clean, a.policy, a.rounds, echo=echo, context=a.context))
            print(json.dumps(got["total"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
