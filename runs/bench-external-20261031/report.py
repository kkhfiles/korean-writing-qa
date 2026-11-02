"""세 시험의 점수를 모아 표와 짝지은 차이(같은 문서끼리 견준 부트스트랩 95% 구간)를 내고 result.json 에 수만 적는다.

    python -X utf8 runs/bench-external-20261031/report.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, boot_diff  # noqa: E402
import bench_e2e  # noqa: E402
import bench_inject  # noqa: E402
import bench_knct  # noqa: E402
import bench_precision  # noqa: E402

HERE = Path(__file__).parent
PERF = DATA / "perf.json"


def r3(x):
    if x is None:
        return None
    return [None if v != v else round(v, 3) for v in x] if isinstance(x, (list, tuple)) else round(x, 3)


def verdict(d):
    p, lo, hi = d
    return "높음" if lo > 0 else "낮음" if hi < 0 else "차이 판정 불가"


def cost_row(c: dict) -> dict:
    k = c.get("kchars") or 1
    return {"초/1천 자": round(c.get("seconds", 0) / k, 2),
            "환산 달러/1천 자(Claude만)": round(c.get("cost_usd", 0) / k, 4),
            "입력 토큰/1천 자": round(c.get("in_tok", 0) / k), "출력 토큰/1천 자": round(c.get("out_tok", 0) / k),
            "주고받은 글자/1천 자": round((c.get("in_chars", 0) + c.get("out_chars", 0)) / k),
            "실패 호출": c.get("errors", 0)}


def pairs(table: dict, metric_path, base: str, others: list[str]) -> dict:
    out = {}
    if base not in table:
        return out
    a = metric_path(table[base])
    for o in others:
        if o in table:
            d = boot_diff(a, metric_path(table[o]))
            out[f"{base} − {o}"] = {"차이": r3(d), "판정": verdict(d)}
    return out


def main() -> int:
    res: dict = {}
    k = bench_knct.score()
    models = ["plain-claude", "plain-gpt", "plain-argon", "plain-flash", "imnotai-claude", "kiwi-space", "kobart-gec"]
    res["D1 K-NCT"] = {
        n: {"회수율": r3(v["회수율"]["전체"]), "회수율(엄격)": r3(v["회수율(엄격)"]),
            "갈래별 회수율": {f: round(x[0], 3) for f, x in v["회수율"].items() if f != "전체"},
            "교정 정확도": r3(v["교정 정확도"]["전체"]),
            "정답 문장 지적/1천 자": r3(v["정답 문장 지적 밀도(1천 자당)"]), "비용": cost_row(v["비용"])}
        for n, v in k.items()}
    pk = {n: v["_per_doc"] for n, v in k.items()}
    res["D1 짝지은 차이"] = {
        "회수율": pairs(pk, lambda t: t["recall"], "l2", models),
        "교정 정확도": pairs(pk, lambda t: t["exact"], "l2", models),
        "정답 문장 지적 밀도": pairs(pk, lambda t: t["noise"], "l2", models)}

    i = bench_inject.score()
    res["D2 결함 심기"] = {
        n: {"회수율": {f: r3(x) for f, x in v["회수율"].items()},
            "보정 회수율": {f: r3(x) for f, x in v["보정 회수율"].items()},
            "원문 지적/1천 자": r3(v["원문 지적 밀도(1천 자당)"]), "비용": cost_row(v["비용"])}
        for n, v in i.items()}
    pi = {n: v["_per_doc"] for n, v in i.items()}
    others = ["l1", "plain-claude", "plain-gpt", "plain-argon", "plain-flash", "imnotai-claude", "kiwi-space", "kobart-gec"]
    res["D2 짝지은 차이"] = {
        "F1~F4 회수율": pairs(pi, lambda t: t["F1~F4"], "l2", others),
        "F1~F4 보정 회수율": pairs(pi, lambda t: t["F1~F4 보정"], "l2", others),
        "원문 지적 밀도": pairs(pi, lambda t: t["noise"], "l2", others)}
    for fam in ("F1", "F2", "F3", "F4", "F5"):
        res["D2 짝지은 차이"][f"{fam} 회수율"] = pairs(pi, lambda t, f=fam: t.get(f, {}), "l2", others)

    try:
        res["D2 정밀도"] = {n: {kk: r3(vv) for kk, vv in v.items()} for n, v in bench_precision.score().items()}
    except FileNotFoundError:
        res["D2 정밀도"] = "아직 안 돎"
    try:
        e = bench_e2e.score(("ours", "ours-noinvent", "l1only", "plain-claude"))
        for v in e["판정"].values():
            v.pop("_per_doc", None)
        res["D3 고쳐 쓰기"] = {"판정": {kk: {k2: r3(v2) if isinstance(v2, (int, float, tuple, list)) else v2
                                           for k2, v2 in vv.items()} for kk, vv in e["판정"].items()},
                             "비용": {n: cost_row(c) | {"호출": c.get("calls", 0)} for n, c in e["고쳐 쓰기 비용"].items()}}
    except FileNotFoundError:
        res["D3 고쳐 쓰기"] = "아직 안 돎"
    if PERF.exists():
        res["속도(공개 글 40편 한 번에)"] = json.loads(PERF.read_text(encoding="utf-8"))
    (HERE / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({kk: vv for kk, vv in res.items() if "차이" in kk}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
