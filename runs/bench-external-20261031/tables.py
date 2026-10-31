"""result.json 에서 README 의 정밀도 표와 D3 표를 뽑는다 — 손으로 옮기다 틀리지 않게.

    python -X utf8 runs/bench-external-20261031/tables.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bench_e2e  # noqa: E402

HERE = Path(__file__).parent
r = json.loads((HERE / "result.json").read_text(encoding="utf-8"))
NAMES = {"none": "고치지 않은 초안", "plain-claude": "Claude 단순 요청", "plain-gpt": "GPT 단순 요청",
         "plain-argon": "Argon 단순 요청", "imnotai": "im-not-ai 규칙", "ours": "검사기 흐름",
         "ours-noinvent": "검사기 흐름(정보 지어내기 금지)", "l1only": "1층만 적용"}


def f2(x):
    return "—" if x is None else f"{x:.2f}"


def precision() -> str:
    out = ["| 시스템 | 두 판정자 모두 맞음 | 한 판정자 이상 맞음 | 두 판정자 일치율 | 표본 |", "|---|---:|---:|---:|---:|"]
    for n, v in r["D2 정밀도"].items():
        if n.startswith("l1("):
            continue
        both, any_ = v.get("두 판정자 모두 맞음"), v.get("한 판정자 이상 맞음")
        out.append(f"| `{n}` | {f2(both[0])} ({f2(both[1])}~{f2(both[2])}) | {f2(any_[0])} ({f2(any_[1])}~{f2(any_[2])}) "
                   f"| {f2(v.get('두 판정자 일치율'))} | {v['표본']} |")
    return "\n".join(out)


def record(jn: str, base: str, rival: str):
    """판정 파일에서 승·비김·패와 뜻 바뀜 합을 바로 셈(result.json 은 승률만 담음)."""
    d = bench_e2e.judged_dir(base) / jn / rival
    w = t = l = mo = mr = 0
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        rec = json.loads(f.read_text(encoding="utf-8"))
        v = rec.get("verdict")
        if not v:
            continue
        o, x = ("A", "B") if rec["a_is_ours"] else ("B", "A")
        w += v.get("winner") == o
        t += v.get("winner") == "tie"
        l += v.get("winner") == x
        mo += int(v.get(f"meaning_changes_{o}") or 0)
        mr += int(v.get(f"meaning_changes_{x}") or 0)
    return (w, t, l, mo, mr) if w + t + l else None


def d3() -> str:
    out = ["| 비교 | Claude 판정 승-비김-패 | GPT 판정 | Argon 판정 | 뜻 바뀜 합(앞/뒤, Claude 판정) |",
           "|---|---|---|---|---|"]
    pairs = [("ours", x) for x in bench_e2e.RIVALS + ["plain-gpt"] if x != "plain-gpt"] + [("ours", "plain-gpt")]
    pairs += [("ours-noinvent", x) for x in ("ours", "none", "plain-claude")]
    pairs += [("l1only", x) for x in ("ours", "none", "plain-claude")]
    pairs += [("plain-claude", "none")]
    for base, rival in pairs:
        cells = []
        for jn in ("claude", "gpt", "argon"):
            rec = record(jn, base, rival)
            cells.append("—" if rec is None or sum(rec[:3]) < 12 else f"{rec[0]}-{rec[1]}-{rec[2]}")
        c = record("claude", base, rival)
        mean = f"{c[3]} / {c[4]}" if c else "—"
        out.append(f"| {NAMES[base]} 대 {NAMES[rival]} | " + " | ".join(cells) + f" | {mean} |")
    return "\n".join(out)


def cost() -> str:
    out = ["| 고쳐 쓰기 | 초/1천 자 | 환산 달러/1천 자 | 입력 토큰/1천 자 |", "|---|---:|---:|---:|"]
    for n, v in r["D3 고쳐 쓰기"]["비용"].items():
        usd = f"{v['환산 달러/1천 자(Claude만)']:.3f}" if v["환산 달러/1천 자(Claude만)"] else "—"
        tok = f"{v['입력 토큰/1천 자']:,}" if v["입력 토큰/1천 자"] else "—"
        out.append(f"| {NAMES.get(n, n)} | {v['초/1천 자']:.1f} | {usd} | {tok} |")
    return "\n".join(out)


if __name__ == "__main__":
    print(precision(), "\n")
    print(d3(), "\n")
    print(cost())
