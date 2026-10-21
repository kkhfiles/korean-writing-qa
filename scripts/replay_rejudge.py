"""저장된 재판정 입력을 문맥 방식마다 같은 입력으로 재생해 지적 차이를 본다 — 판정 기록은 건드리지 않는다.

**왜 필요한가** (2026-10-16) — 재판정에 대상 주변만 보내면(`--context fixed|block`) 비용이 크게 줄 것으로 보이지만,
문맥이 줄어 놓치는 것이 생길 수 있다. 세션 흐름째로 견주면 처리 결과가 다음 판정의 입력을 바꿔 차이가 어디서
났는지 못 가른다. 그래서 실사용 재판정 시점의 입력(문서 · 대상 · 기준 판 · 계보 · 닫은 지적 · 사용자 답)을
판정기가 남겨 두고(`judge_layer2.save_case`), 여기서 같은 입력을 방식마다 부른다(외부 검토 권고).

    python -X utf8 scripts/replay_rejudge.py list
    python -X utf8 scripts/replay_rejudge.py run <이름> [--modes chunk,fixed,block,fixed@bare] [--repeat 2] [--limit N]
    python -X utf8 scripts/replay_rejudge.py sheet <이름>
    python -X utf8 scripts/replay_rejudge.py --dir <입력 폴더> rescore <이름> [--html-window on|off]

- **run** — 사례마다 방식마다 `--repeat` 번 부른다. 같은 방식을 두 번 이상 불러야 방식 사이 차이와 판정기 흔들림을
  가른다. 결과는 `~/.claude/state/korean-replay-runs/<이름>/results.jsonl`. 방식 뒤에 `@bare` 를 붙이면 기준 판의
  「고친 까닭」을 빼고 부른다 — 그것을 싣기 전 입력과 같은 조건으로 견준다. `@low` 처럼 사고 깊이를 붙이면 그
  깊이로 부르고, `@bare+low` 로 둘을 함께 쓴다.
- **비용은 캐시와 떼어 본다** — 같은 입력을 연달아 부르면 먼저 부른 쪽이 캐시를 쓰고, 순서를 반복마다 돌려도
  2회차는 모든 방식이 1회차 캐시를 읽어 상쇄되지 않는다. 그래서 금액 옆에 토큰과 「캐시와 뗀 비용」을 함께 내고,
  모든 방식이 같은 프롬프트를 보낸 사례(프롬프트 지문이 같음)를 따로 세어 「입력이 달랐던 사례만」의 합계를 낸다
  (2026-10-21 회고 검토).
- **rescore** — 지문이 없던 옛 결과에 지금 코드로 만든 프롬프트 지문을 붙여 다시 집계한다. 부르지 않는다.
- **sheet** — 대상 줄마다 방식별 지적을 나란히 둔 표. 방식 이름 대신 사례마다 섞은 A · B · C 를 쓰고 대응은
  `key.json` 에 따로 둔다 — 검토자가 어느 방식인지 모른 채 고르게. 차이만 보면 양쪽이 함께 놓친 것은 못 찾으므로
  일치한 줄도 표에 남긴다.
- ⛔ **판정기를 실제로 부른다** — 구독 한도를 쓴다. 7일 창 사용률을 먼저 본다.
- ⛔ **사내 문서 원문이 들어간다** — 입력과 결과는 저장소 밖에만 두고 외부 서비스로 보내지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import judge_layer2 as judge  # noqa: E402
import probe_layer2_kinds as probe  # noqa: E402

OUT = Path.home() / ".claude" / "state" / "korean-replay-runs"
#: 100만 토큰당 환산 단가(달러) — 실사용 판정 기록의 금액을 토큰으로 회귀해 얻은 값(2026-10-21 회고 검토).
#: 비용을 캐시 상태와 떼어 견줄 때만 쓴다 — 같은 입력을 연달아 부르면 먼저 부른 쪽이 캐시를 써서, 재생의 금액
#: 차이 상당 부분이 순서 효과였다(고친 까닭 첨부 「+14%」 · 캐시가 찬 2회차에서는 0.401 대 0.401)
PRICE = {"write_5m": 5.00, "read": 0.20, "output": 20.0}
#: 방식 뒤 「@」 다음에 「+」로 잇는 표시 — bare 는 고친 까닭을 뺌, 나머지는 사고 깊이
EFFORTS = ("low", "medium", "high")


def prompt_print(system: str, user, effort: str | None = None) -> str:
    """입력 지문 — 사고 깊이도 넣는다. 깊이만 다른 두 방식은 프롬프트가 같아도 입력이 다르다."""
    return hashlib.sha256(json.dumps([system, user, effort], ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def parse_mode(mode: str) -> tuple[str, bool, str | None]:
    """「fixed@bare+low」 → (fixed, 고친 까닭 실음 여부, 사고 깊이)."""
    base, _, flags = mode.partition("@")
    marks = [f for f in flags.split("+") if f]
    unknown = [f for f in marks if f != "bare" and f not in EFFORTS]
    if unknown:
        raise ValueError(f"모르는 방식 표시 — {', '.join(unknown)}")
    return base, "bare" not in marks, next((f for f in marks if f in EFFORTS), None)


def load_cases(folder: Path) -> list[dict]:
    out = []
    for p in sorted(folder.glob("*.json")):
        case = json.loads(p.read_text(encoding="utf-8"))
        case["file"] = p.name
        case["info"] = {int(k): v for k, v in (case.get("info") or {}).items()}
        out.append(case)
    return out


def replay(case: dict, mode: str, backend, model: str, timeout: float = 900, reasons: bool = True,
           effort: str | None = None) -> dict:
    """사례 하나를 한 방식으로 — {"findings", "calls", "cost", "cache_write", "cache_read", "output", "short", "seconds",
    "prompts"}.

    `reasons` — 기준 판에 「고친 까닭」(앞선 판정의 지적)을 싣는다. 끄면 싣기 전과 같은 입력이다(견줄 때).
    `backend` 가 None 이면 부르지 않고 첫 조각들의 프롬프트 지문만 낸다 — 두 방식이 같은 입력을 보냈는지 가린다.
    """
    call_messages, parse_json = backend or (None, None)
    lines = case["text"].splitlines()
    want = set(case["targets"])
    info = {n: {k: v for k, v in i.items() if k != "root_found"} for n, i in case["info"].items()}
    path = Path(case["doc"])
    if reasons:
        root = [n for n, i in case["info"].items() if i.get("root_found")]
        for n in root:
            info[n]["root_found"] = case["info"][n]["root_found"]
        # 싣기 전(2026-10-20)에 남긴 입력은 판정 기록에서 그때 앞의 것으로 되살린다. 세션 흉내(`bench_loop.py`)는
        # 문서 옆에 따로 기록을 둔다
        if not root and case.get("key"):
            own = path.with_name("judge.jsonl")
            judge.root_findings(case["key"], info, before=datetime.fromisoformat(case["at"]).timestamp(),
                                log=own if own.is_file() else None)
    closed = [tuple(x) for x in case.get("closed") or []]
    decided = [tuple(x) for x in case.get("decided") or []]
    instructed = [tuple(x) for x in case.get("instructed") or []]
    system = probe.system_prompt().format(rules=probe.rules_for("guided")) + (case.get("decisions_prompt") or "")
    heads = {int(k): v for k, v in case["heads"].items()} if case.get("heads") is not None else None
    queue = judge.parts_for(lines, want, mode, path, heads)
    got = {"findings": [], "calls": 0, "cost": 0.0, "cache_write": 0, "cache_read": 0, "output": 0, "short": [],
           "seconds": 0.0, "modes": [], "prompts": []}
    while queue:
        piece = queue.pop(0)
        windowed = piece["mode"] in ("fixed", "block")
        user = judge.rejudge_user(piece, info, closed, decided, instructed, case.get("extra") or "")
        got["prompts"].append(prompt_print(system, user, effort))
        if call_messages is None:
            continue
        started = time.time()
        r = call_messages(model=model, system=system, user=user, max_tokens=12000, temperature=0, timeout=timeout,
                          **({"effort": effort} if effort else {}))
        usage = r.get("usage") or {}
        got["calls"] += 1
        got["modes"].append(piece["mode"])
        got["seconds"] += time.time() - started
        got["cost"] += r.get("cost_usd") or 0
        got["cache_write"] += usage.get("cache_creation_input_tokens", 0)
        got["cache_read"] += usage.get("cache_read_input_tokens", 0)
        got["output"] += usage.get("output_tokens", 0)
        short = set()
        for it in probe.as_findings(parse_json(r.get("text") or "") or []):
            if not isinstance(it, dict):
                continue
            n = judge.relocate(lines, it.get("line"), str(it.get("phrase") or ""))
            if n not in want:
                continue
            if windowed and it.get("category") == judge.CONTEXT_SHORT:
                short.add(n)
                continue
            got["findings"].append({"line": n, "phrase": it.get("phrase"), "category": it.get("category"),
                                    "fix": it.get("fix"), "decide": it.get("decide")})
        if short:
            got["short"] += sorted(short)
            queue += [dict(p, mode=f"chunk←{judge.CONTEXT_SHORT}") for p in judge.parts_for(lines, short, "chunk", path)]
    got["cost"] = round(got["cost"], 4)
    got["seconds"] = round(got["seconds"], 1)
    return got


def run(name: str, cases: list[dict], modes: list[str], repeat: int, backend, model: str, out: Path = OUT) -> Path:
    folder = out / name
    folder.mkdir(parents=True, exist_ok=True)
    results = folder / "results.jsonl"
    rules_now = hashlib.sha256(probe.rules_for("guided").encode("utf-8")).hexdigest()[:12]
    with results.open("a", encoding="utf-8", newline="\n") as f:
        for case in cases:
            for k in range(repeat):
                # 방식 순서를 반복마다 돌려 캐시 상태가 한쪽에 몰리지 않게
                order = modes[k % len(modes):] + modes[:k % len(modes)]
                for mode in order:
                    # 「방식@bare」 — 기준 판의 고친 까닭을 빼고 부른다(싣기 전 입력과 견줄 때) · 「@low」 — 사고 깊이
                    base_mode, reasons, effort = parse_mode(mode)
                    got = replay(case, base_mode, backend, model, reasons=reasons, effort=effort)
                    row = {"case": case["file"], "mode": mode, "repeat": k, "targets": case["targets"],
                           "rules_changed": case.get("rules") != rules_now, **got}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(f"{case['file']} · {mode} · {k} · 호출 {got['calls']} · 지적 {len(got['findings'])} · "
                          f"환산 {got['cost']} · 문맥 부족 {len(got['short'])}", flush=True)
    return results


def cold_cost(r: dict) -> float:
    """캐시 상태와 뗀 비용 — 입력을 모두 처음 쓰는 값으로 친다. 방식 사이 순서 효과를 뺀 비교용."""
    prompt = (r.get("cache_write") or 0) + (r.get("cache_read") or 0)
    return (prompt * PRICE["write_5m"] + (r.get("output") or 0) * PRICE["output"]) / 1e6


def _tally(rows: list[dict]) -> dict[str, dict]:
    by_mode: dict[str, dict] = {}
    for r in rows:
        m = by_mode.setdefault(r["mode"], {"runs": 0, "calls": 0, "cost": 0.0, "findings": 0, "short": 0,
                                           "프롬프트 토큰": 0, "출력 토큰": 0, "캐시와 뗀 비용": 0.0})
        m["runs"] += 1
        m["calls"] += r["calls"]
        m["cost"] = round(m["cost"] + r["cost"], 4)
        m["findings"] += len(r["findings"])
        m["short"] += len(r["short"])
        m["프롬프트 토큰"] += (r.get("cache_write") or 0) + (r.get("cache_read") or 0)
        m["출력 토큰"] += r.get("output") or 0
        m["캐시와 뗀 비용"] = round(m["캐시와 뗀 비용"] + cold_cost(r), 4)
    return by_mode


def same_prompt_cases(rows: list[dict]) -> set[str]:
    """모든 방식이 같은 프롬프트를 보낸 사례 — 이 사례의 차이는 방식 차이가 아니라 흔들림과 순서 효과다.

    (2026-10-21) HTML 재생 12건 중 6건, Markdown 재생 30건 중 11건이 두 방식이 같은 입력이었는데 합계에 섞였다.
    """
    seen: dict[str, dict[str, set]] = {}
    for r in rows:
        if r.get("prompts"):
            seen.setdefault(r["case"], {}).setdefault(r["mode"], set()).add(tuple(r["prompts"]))
    return {c for c, per in seen.items() if len(per) > 1 and len(set().union(*per.values())) == 1}


def summarize(rows: list[dict]) -> dict:
    """방식별 합계와, 같은 사례에서 방식 사이 · 같은 방식 반복 사이의 지적 줄 일치율.

    프롬프트 지문이 있으면 모든 방식이 같은 입력을 보낸 사례를 따로 세고, 입력이 달랐던 사례만의 합계를 함께 낸다.
    """
    by_mode = _tally(rows)
    same = same_prompt_cases(rows)

    def lines_of(r):
        return {(f["line"], f.get("category")) for f in r["findings"]}

    def jaccard(a, b):
        return 1.0 if not a and not b else len(a & b) / len(a | b)
    cases: dict[str, dict] = {}
    for r in rows:
        cases.setdefault(r["case"], {}).setdefault(r["mode"], []).append(lines_of(r))
    same_runs, cross = [], {}
    for per in cases.values():
        for mode, runs in per.items():
            same_runs += [jaccard(a, b) for i, a in enumerate(runs) for b in runs[i + 1:]]
        if "chunk" in per:
            for mode, runs in per.items():
                if mode != "chunk":
                    cross.setdefault(mode, []).extend(jaccard(a, b) for a in runs for b in per["chunk"])
    mean = lambda v: round(sum(v) / len(v), 3) if v else None  # noqa: E731
    out = {"방식별": by_mode, "같은 방식 반복 일치": mean(same_runs),
           "chunk 와의 일치": {m: mean(v) for m, v in cross.items()}}
    if any(r.get("prompts") for r in rows):
        out["모든 방식이 같은 입력인 사례"] = len(same)
        out["입력이 달랐던 사례만"] = _tally([r for r in rows if r["case"] not in same])
    return out


def rescore(rows: list[dict], cases: list[dict]) -> list[dict]:
    """옛 결과에 프롬프트 지문을 붙인다 — 부르지 않는다. 지금 코드로 다시 만든 입력이라 그때와 글자가 다를 수
    있지만, 두 방식이 같은 조각으로 갈렸는지는 조각 나누기(`parts_for`)가 정해 그대로 가려진다."""
    by_file = {c["file"]: c for c in cases}
    out = []
    for r in rows:
        case = by_file.get(r["case"])
        if case is None:
            out.append(r)
            continue
        base_mode, reasons, effort = parse_mode(r["mode"])
        out.append(dict(r, prompts=replay(case, base_mode, None, "", reasons=reasons, effort=effort)["prompts"]))
    return out


def sheet(rows: list[dict], folder: Path, seed: int = 0) -> Path:
    """방식을 가린 비교 표 — 대상 줄마다 A · B · C 의 지적. 대응은 key.json."""
    rng = random.Random(seed)
    cases: dict[str, list[dict]] = {}
    for r in rows:
        if r["repeat"] == 0:
            cases.setdefault(r["case"], []).append(r)
    key, out = {}, ["# 재판정 문맥 비교 — 어느 방식인지 가린 표", "",
                    "대상 줄마다 방식별 지적을 나란히 둡니다. 지적이 맞는지, 놓친 것이 있는지를 줄마다 적습니다.", ""]
    for case, runs in sorted(cases.items()):
        labels = [chr(ord("A") + i) for i in range(len(runs))]
        rng.shuffle(labels)
        key[case] = {lab: r["mode"] for lab, r in zip(labels, runs)}
        out += [f"## {case}", "", "| 줄 | " + " | ".join(sorted(labels)) + " | 판단 |",
                "|---|" + "---|" * len(labels) + "---|"]
        mapping = dict(zip(labels, runs))
        for n in runs[0]["targets"]:
            cells = []
            for lab in sorted(labels):
                fs = [f for f in mapping[lab]["findings"] if f["line"] == n]
                cells.append(" · ".join(f"「{f['phrase']}」({f['category']})" for f in fs).replace("|", "/") or "없음")
            out.append(f"| {n} | " + " | ".join(cells) + " |  |")
        out.append("")
    (folder / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    p = folder / "sheet.md"
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="저장된 재판정 입력을 문맥 방식마다 재생")
    ap.add_argument("--dir", type=Path, default=None, help="저장된 입력 폴더(기본: 판정 기록 옆 korean-replay)")
    ap.add_argument("--out", type=Path, default=OUT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("name")
    r.add_argument("--modes", default="chunk,fixed,block")
    r.add_argument("--repeat", type=int, default=2)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--model", default=judge.DEFAULT_MODEL)
    r.add_argument("--html-window", action="store_true", help="HTML 에도 fixed 창(judge.WINDOW_HTML)")
    s = sub.add_parser("sheet")
    s.add_argument("name")
    q = sub.add_parser("rescore", help="옛 결과에 프롬프트 지문을 붙여 다시 집계(부르지 않음 · --dir 은 그때의 입력 폴더)")
    q.add_argument("name")
    q.add_argument("--html-window", choices=("on", "off"), default="on", help="그 실행 때 HTML 창을 썼나")
    a = ap.parse_args(argv)
    folder = a.dir or judge.replay_dir()
    if a.cmd == "rescore":
        judge.WINDOW_HTML = a.html_window == "on"
        rows = [json.loads(l) for l in (a.out / a.name / "results.jsonl").read_text(encoding="utf-8").splitlines()]
        print(json.dumps(summarize(rescore(rows, load_cases(folder))), ensure_ascii=False, indent=1))
        return 0
    if a.cmd == "list":
        cases = load_cases(folder)
        print(f"저장된 재판정 입력 {len(cases)}건 — {folder}")
        for c in cases[-20:]:
            print(f"  {c['file']} · 대상 {len(c['targets'])} · {Path(c['doc']).name}")
        return 0
    if a.cmd == "sheet":
        rows = [json.loads(l) for l in (a.out / a.name / "results.jsonl").read_text(encoding="utf-8").splitlines()]
        print(json.dumps(summarize(rows), ensure_ascii=False, indent=1))
        print(f"비교 표 — {sheet(rows, a.out / a.name)}")
        return 0
    cases = load_cases(folder)
    if a.limit:
        cases = cases[-a.limit:]
    name = judge.pick_backend("auto")
    backend = judge.load_backend(name) if name else None
    if backend is None:
        print("⛔ 판정기를 부를 수 없습니다")
        return 3
    import os
    os.environ.setdefault(judge.CACHE_TTL_ENV, judge.CACHE_TTL)
    judge.WINDOW_HTML = judge.WINDOW_HTML or a.html_window
    print(f"결과 — {run(a.name, cases, a.modes.split(','), a.repeat, backend, a.model, a.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
