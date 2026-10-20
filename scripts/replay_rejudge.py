"""저장된 재판정 입력을 문맥 방식마다 같은 입력으로 재생해 지적 차이를 본다 — 판정 기록은 건드리지 않는다.

**왜 필요한가** (2026-10-16) — 재판정에 대상 주변만 보내면(`--context fixed|block`) 비용이 크게 줄 것으로 보이지만,
문맥이 줄어 놓치는 것이 생길 수 있다. 세션 흐름째로 견주면 처리 결과가 다음 판정의 입력을 바꿔 차이가 어디서
났는지 못 가른다. 그래서 실사용 재판정 시점의 입력(문서 · 대상 · 기준 판 · 계보 · 닫은 지적 · 사용자 답)을
판정기가 남겨 두고(`judge_layer2.save_case`), 여기서 같은 입력을 방식마다 부른다(외부 검토 권고).

    python -X utf8 scripts/replay_rejudge.py list
    python -X utf8 scripts/replay_rejudge.py run <이름> [--modes chunk,fixed,block,fixed@bare] [--repeat 2] [--limit N]
    python -X utf8 scripts/replay_rejudge.py sheet <이름>

- **run** — 사례마다 방식마다 `--repeat` 번 부른다. 같은 방식을 두 번 이상 불러야 방식 사이 차이와 판정기 흔들림을
  가른다. 결과는 `~/.claude/state/korean-replay-runs/<이름>/results.jsonl`. 방식 뒤에 `@bare` 를 붙이면 기준 판의
  「고친 까닭」을 빼고 부른다 — 그것을 싣기 전 입력과 같은 조건으로 견준다.
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


def load_cases(folder: Path) -> list[dict]:
    out = []
    for p in sorted(folder.glob("*.json")):
        case = json.loads(p.read_text(encoding="utf-8"))
        case["file"] = p.name
        case["info"] = {int(k): v for k, v in (case.get("info") or {}).items()}
        out.append(case)
    return out


def replay(case: dict, mode: str, backend, model: str, timeout: float = 900, reasons: bool = True) -> dict:
    """사례 하나를 한 방식으로 — {"findings", "calls", "cost", "cache_write", "cache_read", "output", "short", "seconds"}.

    `reasons` — 기준 판에 「고친 까닭」(앞선 판정의 지적)을 싣는다. 끄면 싣기 전과 같은 입력이다(견줄 때).
    """
    call_messages, parse_json = backend
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
           "seconds": 0.0, "modes": []}
    while queue:
        piece = queue.pop(0)
        windowed = piece["mode"] in ("fixed", "block")
        started = time.time()
        r = call_messages(model=model, system=system,
                          user=judge.rejudge_user(piece, info, closed, decided, instructed,
                                                  case.get("extra") or ""),
                          max_tokens=12000, temperature=0, timeout=timeout)
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
                    # 「방식@bare」 — 기준 판의 고친 까닭을 빼고 부른다(싣기 전 입력과 견줄 때)
                    base_mode, _, flag = mode.partition("@")
                    got = replay(case, base_mode, backend, model, reasons=flag != "bare")
                    row = {"case": case["file"], "mode": mode, "repeat": k, "targets": case["targets"],
                           "rules_changed": case.get("rules") != rules_now, **got}
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(f"{case['file']} · {mode} · {k} · 호출 {got['calls']} · 지적 {len(got['findings'])} · "
                          f"환산 {got['cost']} · 문맥 부족 {len(got['short'])}", flush=True)
    return results


def summarize(rows: list[dict]) -> dict:
    """방식별 합계와, 같은 사례에서 방식 사이 · 같은 방식 반복 사이의 지적 줄 일치율."""
    by_mode: dict[str, dict] = {}
    for r in rows:
        m = by_mode.setdefault(r["mode"], {"runs": 0, "calls": 0, "cost": 0.0, "findings": 0, "short": 0})
        m["runs"] += 1
        m["calls"] += r["calls"]
        m["cost"] = round(m["cost"] + r["cost"], 4)
        m["findings"] += len(r["findings"])
        m["short"] += len(r["short"])

    def lines_of(r):
        return {(f["line"], f.get("category")) for f in r["findings"]}

    def jaccard(a, b):
        return 1.0 if not a and not b else len(a & b) / len(a | b)
    cases: dict[str, dict] = {}
    for r in rows:
        cases.setdefault(r["case"], {}).setdefault(r["mode"], []).append(lines_of(r))
    same, cross = [], {}
    for per in cases.values():
        for mode, runs in per.items():
            same += [jaccard(a, b) for i, a in enumerate(runs) for b in runs[i + 1:]]
        if "chunk" in per:
            for mode, runs in per.items():
                if mode != "chunk":
                    cross.setdefault(mode, []).extend(jaccard(a, b) for a in runs for b in per["chunk"])
    mean = lambda v: round(sum(v) / len(v), 3) if v else None  # noqa: E731
    return {"방식별": by_mode, "같은 방식 반복 일치": mean(same),
            "chunk 와의 일치": {m: mean(v) for m, v in cross.items()}}


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
    a = ap.parse_args(argv)
    folder = a.dir or judge.replay_dir()
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
