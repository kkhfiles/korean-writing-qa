"""D2 — 공개 정책뉴스에 결함 다섯 갈래를 한 편에 하나씩 심고 도구마다 찾아내는 비율을 잰다.

- **F1 맞춤법과 띄어쓰기**, **F5 업무 문서 형식** — 정해진 치환
- **F2 공공언어 바로 쓰기**, **F3 AI 티**, **F4 문맥 결함** — GPT(sol)가 지정한 줄에 지정한 결함 하나만 넣음.
  판정기(Claude)와 다른 회사 모델이 심어, 치우침이 있다면 이 저장소에 불리한 쪽으로 가게 함
- 원문과 심은 글은 저장소 밖에 둠

    python -X utf8 runs/bench-external-20261031/bench_inject.py build
    python -X utf8 runs/bench-external-20261031/bench_inject.py run <시스템…>
    python -X utf8 runs/bench-external-20261031/bench_inject.py score [--json 경로]
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, boot, cached_run, finding_range, hangul, overlaps  # noqa: E402
import systems  # noqa: E402

SRC = DATA / "public/docs.jsonl"
OUT = DATA / "inject"
SEED = 20261031
INJECTOR = ("codex", "sol-medium")

F1 = [  # (이름, 찾을 꼴, 바꿀 꼴)
    ("됐→됬", r"됐", "됬"),
    ("의존 명사 붙여 씀", r"([가-힣]) (수|것|데|만큼) (있|없|이|으로|을|은)", r"\1\2 \3"),
    ("하다 띄어 씀", r"(?<=[가-힣]{2})(했다|한다|하고|하는|해야|했으며)", r" \1"),
    ("안/않 혼동", r"\b안 (했|한|하|된|됐|되)", r"않\1"),
    ("로서/로써 혼동", r"로서", "로써"),
    ("든지/던지 혼동", r"든지", "던지"),
    ("며칠/몇일", r"며칠", "몇일"),
]
F5 = [
    ("띄어 쓴 가운뎃점", r"([가-힣A-Za-z0-9])·([가-힣A-Za-z0-9])", r"\1 · \2"),
    ("모호한 지칭 「우리」", r"(?:^|(?<=\s))(?:정부|[가-힣]{2,6}(?:부|청|처|원|위원회))(는|은|가|이) ",
     lambda m: "우리" + {"은": "는", "이": "가"}.get(m.group(1), m.group(1)) + " "),
    ("절 번호로 가리킴", r"([가-힣])\.$", r"\1(§2 참조)."),
]
F2 = ["이중 피동(예: 되어지다, 보여지다, 만들어지다)",
      "번역투 「~에 있어서」, 「~을 가지다」, 「~에 의해」 가운데 하나",
      "중복 표현(예: 과반수 이상, 미리 예고, 기간 동안, 다시 재개)",
      "주어와 서술어가 호응하지 않는 문장",
      "쉬운 우리말을 두고 불필요한 외래어(예: 리스크, 프로세스, 니즈, 이니셔티브)",
      "명사를 셋 이상 이어 붙인 명사구(예: 지원사업추진계획수립)"]
F3 = ["상투 문형(예: 「단순한 ~을 넘어」, 「~라는 점에서 의미가 크다」, 「발판을 마련했다」)",
      "「A가 아니라 B」 대구",
      "결말 공식(예: 「결국 ~로 이어질 것이다」, 「~해야 할 때다」)",
      "근거 없는 평가 수식어(예: 혁신적인, 획기적인, 전례 없는)",
      "필요 없는 접속 부사(예: 또한, 나아가, 특히)를 문장 앞에 덧붙임"]
F4 = ["앞에 나온 숫자와 어긋나는 숫자",
      "앞에 나온 날짜나 시점과 어긋나는 날짜나 시점",
      "앞에 나온 기관이나 주체를 다른 기관이나 주체로 바꿈",
      "앞 문장과 반대되는 내용"]

INJECT_SYSTEM = """당신은 한국어 교정 도구를 시험하는 자료를 만듭니다. 사용자가 글 전체와 고칠 줄 번호, 넣을 결함 하나를 줍니다.
그 줄에 그 결함 하나만 자연스럽게 넣어 고쳐 쓴 줄을 냅니다. 결함과 상관없는 부분은 글자 그대로 둡니다.
다른 결함(맞춤법, 띄어쓰기 오류 등)은 넣지 않습니다.
출력은 JSON 하나만: {"line": "고쳐 쓴 줄 전체", "what": "넣은 결함을 짧게"}"""


def load_docs() -> list[dict]:
    return [json.loads(l) for l in SRC.open(encoding="utf-8") if l.strip()]


def candidate(line: str) -> bool:
    return hangul(line) >= 25 and line.rstrip().endswith((".", "다"))


def changed_span(before: str, after: str) -> tuple[int, int] | None:
    sm = difflib.SequenceMatcher(None, before, after, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    if not ops:
        return None
    return ops[0][3], max(ops[-1][4], ops[0][3] + 1)


def regex_inject(line: str, rules) -> tuple[str, str] | None:
    for name, pat, rep in rules:
        new, n = re.subn(pat, rep, line, count=1)
        if n and new != line:
            return name, new
    return None


def model_inject(lines: list[str], n: int, kind: str) -> tuple[str, str] | None:
    user = systems.numbered(lines) + f"\n\n고칠 줄: {n}\n넣을 결함: {kind}"
    try:
        r = systems.call_model(*INJECTOR, INJECT_SYSTEM, user, timeout=300)
    except Exception as e:
        print("  주입 실패", e)
        return None
    m = re.search(r"\{.*\}", r["text"], re.S)
    try:
        new = json.loads(m.group(0))["line"].strip() if m else ""
    except (json.JSONDecodeError, KeyError):
        return None
    old = lines[n - 1]
    if not new or new == old or difflib.SequenceMatcher(None, old, new).ratio() < 0.5:
        return None
    return kind, new


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    for k, doc in enumerate(load_docs()):
        f = OUT / f"docs/{doc['id']}.json"
        if f.exists():
            continue
        lines = doc["text"].split("\n")
        cands = [i for i, x in enumerate(lines, 1) if candidate(x)]
        rng.shuffle(cands)
        used, injected, cur = set(), [], list(lines)
        turn = lambda rules: rules[k % len(rules):] + rules[:k % len(rules)]   # 편마다 먼저 쓸 치환을 돌림
        plan = [("F1", turn(F1)), ("F5", turn(F5)), ("F2", F2[k % len(F2)]), ("F3", F3[k % len(F3)]), ("F4", F4[k % len(F4)])]
        for fam, spec in plan:
            for n in cands:
                if n in used or any(abs(n - u) < 1 for u in used):
                    continue
                if fam == "F4" and n == min(cands):      # 앞에 기준이 될 줄이 있어야 함
                    continue
                got = regex_inject(cur[n - 1], spec) if isinstance(spec, list) else model_inject(cur, n, spec)
                if not got:
                    continue
                kind, new = got
                span = changed_span(cur[n - 1], new)
                injected.append({"family": fam, "kind": kind, "line": n, "before": cur[n - 1], "after": new,
                                 "span": span})
                cur[n - 1] = new
                used.add(n)
                break
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"id": doc["id"], "url": doc["url"], "clean": lines, "injected": cur,
                                 "inj": injected}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(k, doc["id"], [(x["family"], x["line"]) for x in injected], flush=True)


def built() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / "docs").glob("*.json"))]


def run(names: list[str]) -> None:
    for name in names:
        for d in built():
            for kind in ("clean", "injected"):
                r = cached_run(name, d[kind], OUT / f"runs/{d['id']}/{kind}")
                print(name, kind, d["id"], f"{r['seconds']:.0f}초", len(r["findings"]), r.get("error", "")[:80],
                      flush=True)


def key_of(f: dict) -> tuple:
    """1층 지적의 같음 — 갈래와 짧은 인용. 문장 전체를 인용하는 갈래는 심은 줄에서 글자가 바뀌어 늘 새 지적으로
    보이므로 인용을 빼고 갈래만 견줌."""
    q = f.get("quote") or ""
    return f.get("kind"), q if len(q) <= 20 else ""


def score(names: list[str] | None = None) -> dict:
    docs = built()
    names = names or sorted({p.stem for p in OUT.glob("runs/*/injected/*.json")})
    table = {}
    for name in names:
        rec = collections.defaultdict(dict)
        rec_net = collections.defaultdict(dict)
        noise, cost = {}, collections.Counter()
        for d in docs:
            base = OUT / f"runs/{d['id']}"
            fi, fc = base / f"injected/{name}.json", base / f"clean/{name}.json"
            if not fi.exists() or not fc.exists():
                continue
            ri, rc = json.loads(fi.read_text(encoding="utf-8")), json.loads(fc.read_text(encoding="utf-8"))
            clean_keys = collections.defaultdict(set)
            for f in rc["findings"]:
                clean_keys[f["line"]].add(key_of(f))
            for x in d["inj"]:
                fl = [f for f in ri["findings"] if f["line"] == x["line"]]
                if name == "l1":            # 결정론 — 원문에도 있던 지적은 심은 결함을 잡은 것이 아님
                    fl = [f for f in fl if key_of(f) not in clean_keys[x["line"]]]
                    hit = bool(fl)
                    net = hit
                else:
                    span = tuple(x["span"]) if x["span"] else (0, len(x["after"]))
                    hit = any(r and overlaps(span, r) for r in (finding_range(f, x["after"]) for f in fl))
                    # 보정 — 원문의 같은 위치를 원문에서도 짚었으면 심은 결함을 잡은 것인지 못 가름
                    back = changed_span(x["after"], x["before"]) or (0, len(x["before"]))
                    was = any(r and overlaps(back, r) for r in
                              (finding_range(f, x["before"]) for f in rc["findings"] if f["line"] == x["line"]))
                    net = hit and not was
                a, b = rec[x["family"]].get(d["id"], (0, 0))
                rec[x["family"]][d["id"]] = (a + hit, b + 1)
                a, b = rec_net[x["family"]].get(d["id"], (0, 0))
                rec_net[x["family"]][d["id"]] = (a + net, b + 1)
            chars = sum(hangul(x) for x in d["clean"])
            noise[d["id"]] = (len(rc["findings"]), chars / 1000)
            for r in (ri, rc):
                for k in ("seconds", "cost_usd", "in_tok", "out_tok", "in_chars", "out_chars"):
                    cost[k] += r.get(k) or 0
                cost["errors"] += bool(r.get("error"))
            cost["kchars"] += 2 * chars / 1000
            cost["docs"] += 2
        if not cost["docs"]:
            continue
        def merged(fams, src=rec):
            m = collections.defaultdict(lambda: (0, 0))
            for fam in fams:
                for k, (a, b) in src.get(fam, {}).items():
                    m[k] = (m[k][0] + a, m[k][1] + b)
            return dict(m)
        table[name] = {
            "회수율": {fam: boot(v) for fam, v in sorted(rec.items())}
                    | {"F1~F4": boot(merged(["F1", "F2", "F3", "F4"])), "전체": boot(merged(list(rec)))},
            "보정 회수율": {fam: boot(v) for fam, v in sorted(rec_net.items())}
                      | {"F1~F4": boot(merged(["F1", "F2", "F3", "F4"], rec_net)),
                         "전체": boot(merged(list(rec_net), rec_net))},
            "원문 지적 밀도(1천 자당)": boot(noise),
            "비용": {k: round(v, 4) for k, v in cost.items()},
            "_per_doc": {fam: v for fam, v in rec.items()} | {"F1~F4": merged(["F1", "F2", "F3", "F4"]),
                                                              "F1~F4 보정": merged(["F1", "F2", "F3", "F4"], rec_net),
                                                              "noise": noise},
        }
    return table


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    r = sub.add_parser("run")
    r.add_argument("names", nargs="+")
    s = sub.add_parser("score")
    s.add_argument("--json")
    a = ap.parse_args()
    if a.cmd == "build":
        build()
        return 0
    if a.cmd == "run":
        run(a.names)
        return 0
    t = score()
    for name, v in t.items():
        print(f"{name:16s} " + " ".join(f"{f}:{x[0]:.2f}" for f, x in v["회수율"].items())
              + f"  원문 지적/1천자 {v['원문 지적 밀도(1천 자당)'][0]:.1f}\n{'  보정':16s} "
              + " ".join(f"{f}:{x[0]:.2f}" for f, x in v["보정 회수율"].items()))
    if a.json:
        Path(a.json).write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
