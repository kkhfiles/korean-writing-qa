"""D1 — 공개 문법 교정 시험 세트 K-NCT 로 맞춤법·문법 오류 회수율과 교정 정확도를 잰다.

- 오류 갈래(띄어쓰기 · 문장 부호 · 숫자 · 맞춤법과 문법) 마다 100문장을 고정 시드로 뽑아 25문장씩 한 편으로 묶음
- 같은 묶음의 정답 문장으로 만든 편을 「깨끗한 글」로 따로 돌림
- 시험 세트 문장은 저장소에 옮기지 않음(라이선스 표기 없음 · 수만 적음)

    python -X utf8 runs/bench-external-20261031/bench_knct.py run <시스템…>
    python -X utf8 runs/bench-external-20261031/bench_knct.py score [--json 경로]
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, apply_fixes, boot, cached_run, finding_range, hangul, is_local, overlaps  # noqa: E402

SRC = DATA / "dl/K-NCT/K-NCT_v1.4.json"
OUT = DATA / "knct"
PER_FAMILY, PER_DOC, SEED = 100, 25, 20261031
TAG = re.compile(r"<e(\d+)>(.*?)</e\1>")


def family(err_types: dict) -> str:
    first = next(iter(err_types.values())).split(",")[0].strip()
    return {"spacing": "띄어쓰기", "punctuation": "문장 부호", "numerical": "숫자"}.get(first, "맞춤법과 문법")


def untag(s: str) -> tuple[str, list[tuple[int, int]]]:
    """태그를 지운 문장과 오류 구간들."""
    out, spans, pos = [], [], 0
    for m in TAG.finditer(s):
        out.append(s[pos:m.start()])
        a = sum(len(x) for x in out)
        out.append(m.group(2))
        spans.append((a, a + max(len(m.group(2)), 1)))
        pos = m.end()
    out.append(s[pos:])
    return "".join(out), spans


def sample() -> list[dict]:
    data = json.loads(SRC.read_text(encoding="utf-8"))["data"]
    by = collections.defaultdict(list)
    for r in data:
        if r["error_type"] and len(set(family({k: v}) for k, v in r["error_type"].items())) == 1:
            by[family(r["error_type"])].append(r)
    rng = random.Random(SEED)
    picked = []
    for fam in sorted(by):
        for r in rng.sample(by[fam], PER_FAMILY):
            text, spans = untag(r["error_sentence"])
            if "\n" in text or not spans:
                continue
            picked.append({"id": r["index"], "family": fam, "error": text, "spans": spans,
                           "correct": r["correct_sentence"].strip()})
    rng.shuffle(picked)
    return picked


def docs(items: list[dict]) -> list[list[dict]]:
    return [items[i:i + PER_DOC] for i in range(0, len(items), PER_DOC)]


def run(names: list[str]) -> None:
    groups = docs(sample())
    for name in names:
        for d, g in enumerate(groups):
            for kind, key in (("err", "error"), ("ok", "correct")):
                r = cached_run(name, [x[key] for x in g], OUT / f"{kind}{d:02d}")
                print(name, kind, d, f"{r['seconds']:.0f}초", len(r["findings"]), r.get("error", "")[:80], flush=True)


def score(names: list[str] | None = None) -> dict:
    groups = docs(sample())
    names = names or sorted({p.stem for p in OUT.glob("err00/*.json")})
    table = {}
    for name in names:
        rec = collections.defaultdict(dict)       # 갈래 → 문서 → (맞힌 구간, 구간)
        exact = collections.defaultdict(dict)
        rec_strict: dict = {}
        noise, cost = {}, collections.Counter()
        for d, g in enumerate(groups):
            fe, fo = OUT / f"err{d:02d}/{name}.json", OUT / f"ok{d:02d}/{name}.json"
            if not fe.exists() or not fo.exists():
                continue
            re_, ro = json.loads(fe.read_text(encoding="utf-8")), json.loads(fo.read_text(encoding="utf-8"))
            by_line, ok_kinds = collections.defaultdict(list), collections.defaultdict(set)
            for f in re_["findings"]:
                by_line[f["line"]].append(f)
            for f in ro["findings"]:
                ok_kinds[f["line"]].add(f["kind"])
            outs = (re_.get("text_out") or "").split("\n") if re_.get("text_out") is not None else None
            for i, x in enumerate(g, 1):
                fl = by_line.get(i, [])
                if name == "l1":    # 결정론 — 정답 문장에도 나는 갈래의 지적은 오류를 잡은 것이 아님
                    hit = len(x["spans"]) if any(f["kind"] not in ok_kinds[i] for f in fl) else 0
                    strict = hit
                else:
                    ranges = [r for r in (finding_range(f, x["error"]) for f in fl) if r]
                    hit = sum(1 for s in x["spans"] if any(overlaps(s, r) for r in ranges))
                    strict = sum(1 for s in x["spans"]
                                 if any(overlaps(s, r) and is_local(r, x["error"]) for r in ranges))
                a, b = rec[x["family"]].get(d, (0, 0))
                rec[x["family"]][d] = (a + hit, b + len(x["spans"]))
                a, b = rec_strict.get(d, (0, 0))
                rec_strict[d] = (a + strict, b + len(x["spans"]))
                fixed = outs[i - 1] if outs is not None else apply_fixes(x["error"], fl)
                ok = re.sub(r"\s+", " ", fixed).strip() == re.sub(r"\s+", " ", x["correct"]).strip()
                a, b = exact[x["family"]].get(d, (0, 0))
                exact[x["family"]][d] = (a + ok, b + 1)
            chars = sum(hangul(x["correct"]) for x in g)
            noise[d] = (len(ro["findings"]), chars / 1000)
            for r in (re_, ro):
                cost["seconds"] += r["seconds"]
                cost["cost_usd"] += r.get("cost_usd") or 0
                cost["in_tok"] += r.get("in_tok") or 0
                cost["out_tok"] += r.get("out_tok") or 0
                cost["in_chars"] += r.get("in_chars") or 0
                cost["out_chars"] += r.get("out_chars") or 0
                cost["errors"] += bool(r.get("error"))
            cost["kchars"] += 2 * chars / 1000
            cost["docs"] += 2
        if not cost["docs"]:
            continue
        allrec = collections.defaultdict(lambda: (0, 0))
        allex = collections.defaultdict(lambda: (0, 0))
        for fam in rec:
            for d, (a, b) in rec[fam].items():
                allrec[d] = (allrec[d][0] + a, allrec[d][1] + b)
            for d, (a, b) in exact[fam].items():
                allex[d] = (allex[d][0] + a, allex[d][1] + b)
        table[name] = {
            "회수율": {fam: boot(v) for fam, v in sorted(rec.items())} | {"전체": boot(dict(allrec))},
            "회수율(엄격)": boot(rec_strict),
            "교정 정확도": {fam: boot(v) for fam, v in sorted(exact.items())} | {"전체": boot(dict(allex))},
            "정답 문장 지적 밀도(1천 자당)": boot(noise),
            "비용": {k: round(v, 4) for k, v in cost.items()},
            "_per_doc": {"recall": {str(d): v for d, v in allrec.items()}, "exact": {str(d): v for d, v in allex.items()},
                         "noise": {str(d): v for d, v in noise.items()}},
        }
    return table


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("names", nargs="+")
    s = sub.add_parser("score")
    s.add_argument("--json")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.names)
        return 0
    t = score()
    for name, v in t.items():
        rc, ex = v["회수율"]["전체"], v["교정 정확도"]["전체"]
        print(f"{name:16s} 회수 {rc[0]:.2f} [{rc[1]:.2f}~{rc[2]:.2f}] 엄격 {v['회수율(엄격)'][0]:.2f}  교정 {ex[0]:.2f}  "
              f"정답글 지적/1천자 {v['정답 문장 지적 밀도(1천 자당)'][0]:.1f}  "
              + " ".join(f"{f}:{x[0]:.2f}" for f, x in v["회수율"].items() if f != "전체"))
    if a.json:
        Path(a.json).write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
