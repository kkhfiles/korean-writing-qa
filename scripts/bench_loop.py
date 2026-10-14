"""회귀 시료를 한 문서로 합쳐 2층 판정 고리를 끝까지 돌린다 — 반복과 정확도를 같은 입력으로 잰다.

**왜 필요한가** (2026-10-13) — 하루에 커밋 열여섯 개를 내고 「호출이 줄어듦」을 적었지만, 같은 일감으로
잰 적이 없었다. 다른 문서끼리 견주니 README 판정 호출이 오히려 4회에서 10회로 늘어 있었다. 사례별로
나뉜 회귀 시료를 한 문서로 합쳐 「판정 → 수정안 적용 → 고친 줄 재판정」을 끝까지 돌리면, 같은 입력으로
반복이 재현된다.

**판정기는 실행마다 크게 흔들린다** — 같은 문서의 0회차 지적이 136건과 169건, 판정기 글 재지적이 17건과
54건이었다. 그래서 한 번 잰 값으로 효과를 말하지 않는다. 기준과 후보를 각각 세 번 이상 돌리고 아래
`PREREGISTERED` 의 규칙으로만 견준다. 그 규칙은 기준선을 재기 전에 적었다 — 결과를 보고 고치면 탐색적이다.

    python -X utf8 scripts/bench_loop.py run <이름> [--times 3] [--policy all|known] [--rounds 6] [--limit N]
    python -X utf8 scripts/bench_loop.py compare <기준 이름> <후보 이름>

- **문서** — 사용자가 짚은 표현 대장의 문장(`data/cases/flagged-rounds.jsonl`)과 기여 시료의 정상 문장
  (`data/cases/contributed.jsonl` 의 expect=clean). 시료마다 한 줄 · 순서 고정.
- **고리** — 전체 판정 → 수정안 적용 → 판정 안 한 줄만 다시 판정(`--since main`). 지적이 없거나, 적용할
  수정안이 없거나, 판정할 새 줄이 없으면 끝.
- **정책** — all = 고칠 지적의 수정안을 모두 적용(세션이 판정기를 그대로 따를 때) · known = 짚은 문장
  줄만 적용(정상 줄 지적은 세기만 함).
- **격리** — 판정 · 답 · 사용자 결정 · 처리 기록을 실행 폴더에 따로 둔다. 쌓인 사용자 답이 프롬프트에
  섞이면 실행마다 입력이 달라진다.
- **결과** — `<--out>/<이름>/<시각>/summary.json`. 기본 폴더는 저장소 밖(`~/.claude/state/korean-bench`).
- ⛔ **정상 줄 지적은 오탐률이 아니다** — 정상 시료는 1층에서 정상인 문장이라 2층 결함이 섞여 있다.
- ⛔ **판정기를 실제로 부른다** — 구독 한도를 쓴다(한 번에 출력 6만여 토큰 · 9분 안팎, 2026-10-13 실측).
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
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402

CHECKER = ROOT / "assets" / "doc-style-check.py"
OUT = Path.home() / ".claude" / "state" / "korean-bench"
TOTAL = re.compile(r"합계 — 오류 (\d+) · 주의 (\d+)")

#: 비교 규칙 — 기준선을 재기 전에 적었다(2026-10-14). 결과를 본 뒤 고치면 그 뒤 비교는 탐색적이다.
PREREGISTERED = {
    # 한쪽에 완주한 실행이 이보다 적으면 판정 불가 · 많으면 탐색적(앞 결과를 보고 더 돌린 것일 수 있다)
    "runs": 3,
    # 낭비 — 낮을수록 좋다. 후보 셋이 모두 기준 셋보다 낮을 확률은 차이가 없을 때 1/20 이다.
    # 결론은 주 지표 하나로 낸다 — 출력 토큰이 곧 시간이다(상관 0.97 · 2026-10-07 실측).
    "primary": "출력 토큰",
    "waste": ["출력 토큰", "호출", "초", "회차", "판정기 글 재지적", "되돌림", "상한 올림"],
    # 정확도 — 후보 최솟값이 기준 최솟값보다 이만큼 넘게 낮으면 악화(낭비가 줄어도 개선으로 안 봄)
    "guard_floor": {"0회차 회수(2층)": 2, "0회차 회수(짚음)": 3},
    # 끝난 문서의 1층 오류 — 후보 최댓값이 기준 최댓값보다 이만큼 넘게 많으면 악화
    "guard_ceiling": {"1층 오류(끝)": 2},
}


def load_samples(limit: int = 0) -> tuple[list[dict], list[dict]]:
    def rows(rel: str) -> list[dict]:
        return [json.loads(l) for l in (ROOT / rel).read_text(encoding="utf-8").splitlines() if l.strip()]
    flagged = rows("data/cases/flagged-rounds.jsonl")
    clean = [c for c in rows("data/cases/contributed.jsonl") if c.get("expect") == "clean"]
    return (flagged[:limit], clean[:limit]) if limit else (flagged, clean)


def build_doc(flagged: list[dict], clean: list[dict]) -> tuple[list[str], dict[int, dict]]:
    """(줄들, 줄 번호 → 시료). 시료 순서를 바꾸면 다른 일감이 된다."""
    lines = ["# 회귀 시료 묶음", "", "**검사기 회귀 시료** — 사용자가 짚은 문장과 정상 문장을 한 문서로 모음", "",
             "## 짚은 문장", ""]
    meta: dict[int, dict] = {}
    for r in flagged:
        lines.append("- " + " ".join(str(r["sentence"]).split()))
        meta[len(lines)] = {"kind": "짚음", "id": r["flag_id"], "owner": r.get("owner")}
    lines += ["", "## 정상 문장", ""]
    for c in clean:
        lines.append("- " + " ".join(str(c["text"]).split()))
        meta[len(lines)] = {"kind": "정상", "id": c["case_id"], "owner": None}
    return lines, meta


@contextlib.contextmanager
def isolated(folder: Path):
    """판정 · 답 · 결정 · 처리 기록을 실행 폴더로 돌린다 — 끝나면 원래대로."""
    spots = [(judge, "LOG", "judge.jsonl"), (coverage, "LOG", "judge.jsonl"),
             (coverage, "ANSWERS", "answers.jsonl"), (coverage, "DECISIONS", "decisions.jsonl"),
             (coverage, "DISMISSALS", "dismissals.jsonl")]
    saved = [getattr(m, name) for m, name, _ in spots]
    for m, name, file in spots:
        setattr(m, name, folder / file)
    try:
        yield
    finally:
        for (m, name, _), value in zip(spots, saved):
            setattr(m, name, value)


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


def layer1_errors(path: Path) -> int | None:
    out = subprocess.run([sys.executable, "-X", "utf8", str(CHECKER), str(path), "--no-rules", "--new-doc"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    m = TOTAL.search(out)
    return int(m.group(1)) if m else None


def run_once(folder: Path, flagged: list[dict], clean: list[dict], policy: str = "all",
             rounds: int = 6, backend=None, echo=None) -> dict:
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
    rows, finished, said = [], True, io.StringIO()
    with isolated(folder):
        for rnd in range(rounds + 1):
            out = folder / f"round{rnd}.json"
            argv = [str(doc), "--json", str(out)] + (["--since", "main"] if rnd else [])
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
                   "초": round(sum(c.get("seconds") or 0 for c in calls))}
            rows.append(row)
            if echo:
                echo(json.dumps(row, ensure_ascii=False))
            if not found or not applied:
                break
    (folder / "judge-output.txt").write_text(said.getvalue(), encoding="utf-8")

    flagged_at = {n for n, m in meta.items() if m["kind"] == "짚음"}
    layer2_at = {n for n in flagged_at if meta[n]["owner"] == "2층"}
    clean_at = {n for n, m in meta.items() if m["kind"] == "정상"}
    total = {"정책": policy, "완주": finished,
             "시료": {"짚음": len(flagged_at), "짚음(2층)": len(layer2_at), "정상": len(clean_at)},
             "회차": sum(1 for r in rows if r["호출"]),
             **{k: sum(r[k] for r in rows) for k in ("호출", "출력 토큰", "초", "상한 올림", "판정기 글 재지적", "되돌림")},
             "0회차 회수(짚음)": len(first_hits & flagged_at),
             "0회차 회수(2층)": len(first_hits & layer2_at),
             "0회차 정상 줄 지적": len(first_hits & clean_at),
             "정상 줄 지적(전 회차)": sum(r["정상 줄 지적"] for r in rows),
             "1층 오류(처음)": layer1_errors(folder / "start.md"),
             "1층 오류(끝)": layer1_errors(doc),
             "가장 많이 고친 줄": sorted(([len(v) - 1, n, meta[n]["kind"] if n in meta else "?"]
                                     for n, v in history.items()), reverse=True)[:5]}
    summary = {"rounds": rows, "total": total}
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def runs_of(out: Path, name: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8"))["total"] for p in sorted((out / name).glob("*/summary.json"))]


def compare(base: list[dict], cand: list[dict], rule: dict = PREREGISTERED) -> dict:
    """두 실행 묶음(각 실행의 total)을 미리 적은 규칙으로 견준다. 완주 못 한 실행은 뺀다."""
    b = [t for t in base if t.get("완주")]
    c = [t for t in cand if t.get("완주")]
    if len(b) < rule["runs"] or len(c) < rule["runs"]:
        return {"결론": "판정 불가",
                "까닭": f"완주한 실행이 기준 {len(b)}회 · 후보 {len(c)}회 — 각 {rule['runs']}회 이상 필요"}
    worse = [f"{k} {min(t[k] for t in c)} < 기준 최솟값 {min(t[k] for t in b)} - {tol}"
             for k, tol in rule["guard_floor"].items() if min(t[k] for t in c) < min(t[k] for t in b) - tol]
    worse += [f"{k} {max(t[k] for t in c)} > 기준 최댓값 {max(t[k] for t in b)} + {tol}"
              for k, tol in rule["guard_ceiling"].items() if max(t[k] for t in c) > max(t[k] for t in b) + tol]
    metrics = {}
    for k in rule["waste"]:
        bv, cv = sorted(t[k] for t in b), sorted(t[k] for t in c)
        verdict = "줄어듦" if cv[-1] < bv[0] else "늘어남" if cv[0] > bv[-1] else "판정 불가(겹침)"
        metrics[k] = {"기준": bv, "후보": cv, "판정": verdict}
    primary = metrics[rule["primary"]]["판정"]
    result = {"결론": "정확도 악화" if worse else {"줄어듦": "개선", "늘어남": "악화"}.get(primary, "판정 불가"),
              "정확도": worse or "유지", "지표": metrics}
    if len(b) > rule["runs"] or len(c) > rule["runs"]:
        result["탐색적"] = f"미리 정한 {rule['runs']}회보다 많이 돌림 — 앞 결과를 보고 더한 것이면 이 결론은 탐색적"
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="회귀 시료로 2층 판정 고리를 재현")
    ap.add_argument("--out", type=Path, default=OUT, help=f"결과 폴더(기본 {OUT})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="판정기를 실제로 불러 고리를 돌림")
    r.add_argument("name")
    r.add_argument("--times", type=int, default=1)
    r.add_argument("--policy", choices=("all", "known"), default="all")
    r.add_argument("--rounds", type=int, default=6)
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
            got = run_once(folder, flagged, clean, a.policy, a.rounds, echo=lambda s: print(s, flush=True))
            print(json.dumps(got["total"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
