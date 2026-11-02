"""D2 정밀도 — 결함을 심지 않은 공개 정책뉴스에서 도구가 낸 지적을 뽑아, 어느 도구 것인지 가리고 판정자 셋이 가른다.

- 도구마다 지적 40건을 고정 시드로 뽑음(모자라면 전부)
- 판정자: Claude Opus, GPT Astra, Gemini Argon — 같은 지적을 셋이 따로 봄. 다수결과 판정자별 값을 함께 적음
- 판정 갈래: 고쳐야 함 · 고치면 나음 · 고칠 필요 없음 · 고치면 틀림
- 1층 「반말 서술형」처럼 이 저장소의 문체 결정(합쇼체)에서 나온 지적은 공개 기사(해라체)에 맞지 않아 따로 셈

    python -X utf8 runs/bench-external-20261031/bench_precision.py judge <판정자…>
    python -X utf8 runs/bench-external-20261031/bench_precision.py score [--json 경로]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, boot  # noqa: E402
import systems  # noqa: E402
from bench_e2e import JUDGES  # noqa: E402

INJ = DATA / "inject"
OUT = DATA / "precision"
PER_SYSTEM, SEED = 40, 20261101
L1_CONTENT = "l1(문체 결정 밖 전부)"
FIRST_EIGHT = ("imnotai-claude", "kiwi-space", "kobart-gec", "l1", "l2", "plain-argon", "plain-claude", "plain-gpt")
HOUSE = ("반말 서술형", "서술형 종결", "서술형 문단", "진입점", "제목")
VERDICTS = {"고쳐야 함": 1.0, "고치면 나음": 1.0, "고칠 필요 없음": 0.0, "고치면 틀림": 0.0}
SYSTEM = """당신은 회사 업무 문서와 공공기관 글을 감수하는 한국어 전문가입니다. 사용자가 글의 일부(앞뒤 줄 포함)와
어떤 검사 도구가 그 글에 낸 지적 하나를 줍니다. 지적이 맞는지 가릅니다. 이 글은 보도 기사체(해라체)이며 그 문체 자체는 결함이 아닙니다.
- 고쳐야 함: 맞춤법, 문법, 사실이나 논리 오류, 뜻이 모호해 오해할 수 있는 곳처럼 고치지 않으면 결함
- 고치면 나음: 결함은 아니지만 지적대로 고치면 분명히 더 읽기 쉬움
- 고칠 필요 없음: 지적이 헛짚었거나 취향 차이
- 고치면 틀림: 수정안대로 고치면 뜻이 바뀌거나 새 오류가 생김
출력은 JSON 하나만: {"verdict": "고쳐야 함" 또는 "고치면 나음" 또는 "고칠 필요 없음" 또는 "고치면 틀림", "why": "한 문장"}"""


def items() -> list[dict]:
    """도구마다 원문 지적을 뽑아 한 목록으로 — 같은 지적이 여러 도구에서 나와도 따로 둠."""
    docs = {json.loads(p.read_text(encoding="utf-8"))["id"]: json.loads(p.read_text(encoding="utf-8"))
            for p in (INJ / "docs").glob("*.json")}
    rng = random.Random(SEED)
    out = []
    # 처음 판정한 여덟 도구는 같은 난수 하나를 이어 써서 뽑았음 — 도구를 더해도 그 표본이 바뀌지 않게 순서를 고정하고,
    # 나중에 더한 도구는 이름별 난수로 뽑음(2026-11-02)
    names = sorted({p.stem for p in INJ.glob("runs/*/clean/*.json")})
    names = [n for n in FIRST_EIGHT if n in names] + [n for n in names if n not in FIRST_EIGHT]
    for name in names:
        if name not in FIRST_EIGHT:
            rng = random.Random(f"{SEED}|{name}")
        pool = []
        for doc_id, d in docs.items():
            f = INJ / f"runs/{doc_id}/clean/{name}.json"
            if not f.exists():
                continue
            for x in json.loads(f.read_text(encoding="utf-8"))["findings"]:
                if 0 < x["line"] <= len(d["clean"]):
                    pool.append({"system": name, "doc": doc_id, **x})
        for x in rng.sample(pool, min(PER_SYSTEM, len(pool))):
            x["id"] = hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
            out.append(x)
    # 1층 표본 40건 중 38건이 문체 결정(반말 서술형)이라, 문체 결정 밖 1층 지적은 전부 따로 넣음(2026-10-31 추가).
    # 뽑기 난수와 섞이지 않게 위 표본 뒤에 붙임
    for doc_id, d in docs.items():
        f = INJ / f"runs/{doc_id}/clean/l1.json"
        for x in json.loads(f.read_text(encoding="utf-8"))["findings"] if f.exists() else []:
            if not any(h in x["kind"] for h in HOUSE) and 0 < x["line"] <= len(d["clean"]):
                x = {"system": L1_CONTENT, "doc": doc_id, **x}
                x["id"] = hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
                out.append(x)
    return out


def prompt(x: dict, docs: dict) -> str:
    lines = docs[x["doc"]]["clean"]
    n = x["line"]
    ctx = "\n".join(f"{'▶' if i == n else ' '} {lines[i - 1]}" for i in range(max(1, n - 1), min(len(lines), n + 1) + 1))
    fix = f"\n수정안: {x['fix']}" if x.get("fix") not in (None, "") else "\n수정안: (없음 — 지적만 함)"
    return f"## 글(▶ 줄이 지적 대상)\n{ctx}\n\n## 지적\n대상 표현: 「{x['quote']}」{fix}\n지적 갈래: {x['kind']}"


FIRST_TWO = ("claude", "argon")


def vote(jn: str, item_id: str) -> float | None:
    f = OUT / f"{jn}/{item_id}.json"
    if not f.exists():
        return None
    v = json.loads(f.read_text(encoding="utf-8")).get("verdict")
    return VERDICTS.get(v)


def agreed(item_id: str) -> float | None:
    a, b = (vote(j, item_id) for j in FIRST_TWO)
    return a if a is not None and a == b else None


def majority(item_id: str) -> float | None:
    """세 판정자 다수결 — 앞 두 판정자가 같으면 그 값, 갈리면 GPT 가 가름(GPT 한도를 아끼려고 갈린 것만 부름)."""
    a = agreed(item_id)
    if a is not None:
        return a
    if any(vote(j, item_id) is None for j in FIRST_TWO):
        return None
    return vote("gpt", item_id)


def judge(names: list[str], tiebreak: bool = False) -> None:
    docs = {json.loads(p.read_text(encoding="utf-8"))["id"]: json.loads(p.read_text(encoding="utf-8"))
            for p in (INJ / "docs").glob("*.json")}
    todo = items()
    random.Random(SEED).shuffle(todo)       # 도구 순서대로 보지 않게
    for jn in names:
        vendor, model = JUDGES[jn]
        for x in todo:
            f = OUT / f"{jn}/{x['id']}.json"
            if f.exists() and not json.loads(f.read_text(encoding="utf-8")).get("error"):
                continue
            if tiebreak and x["system"] != L1_CONTENT and agreed(x["id"]) is not None:   # 앞 둘이 같으면 이미 다수결
                continue
            if jn == "argon" and x["system"] == L1_CONTENT:  # Argon 주간 한도 소진 뒤 추가한 묶음
                continue
            rec = {"system": x["system"], "kind": x["kind"]}
            try:
                t = time.time()
                r = systems.call_model(vendor, model, SYSTEM, prompt(x, docs), timeout=300)
                rec["seconds"] = time.time() - t
                m = re.search(r"\{.*\}", r["text"], re.S)
                v = json.loads(m.group(0)) if m else {}
                rec["verdict"] = v.get("verdict")
                rec["why"] = v.get("why")
                if rec["verdict"] not in VERDICTS:
                    rec["error"] = "판정 없음: " + r["text"][:120]
            except Exception as e:
                rec["error"] = f"{type(e).__name__}: {e}"[:300]
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            print(jn, x["system"], rec.get("verdict"), rec.get("error", "")[:60], flush=True)


def score() -> dict:
    todo = items()
    table = {}
    by_sys = collections.defaultdict(list)
    for x in todo:
        by_sys[x["system"]].append(x)
    for name, xs in sorted(by_sys.items()):
        row = {}
        votes_all = {}
        for jn in JUDGES:
            vals = {}
            for x in xs:
                f = OUT / f"{jn}/{x['id']}.json"
                if f.exists():
                    v = json.loads(f.read_text(encoding="utf-8")).get("verdict")
                    if v in VERDICTS:
                        vals[x["id"]] = (VERDICTS[v], 1)
                        votes_all.setdefault(x["id"], []).append(VERDICTS[v])
            if vals:
                row[f"{jn} 판정 맞음 비율"] = boot(vals)
        if name == L1_CONTENT:      # Claude 와 GPT 두 판정자 — 둘이 같은 것만 셈
            major = {x["id"]: (vote("claude", x["id"]), 1) for x in xs
                     if vote("claude", x["id"]) is not None and vote("claude", x["id"]) == vote("gpt", x["id"])}
        else:
            major = {x["id"]: (m, 1) for x in xs if (m := majority(x["id"])) is not None}
        pair = ("claude", "gpt") if name == L1_CONTENT else FIRST_TWO
        two = [x["id"] for x in xs if all(vote(j, x["id"]) is not None for j in pair)]
        row["두 판정자 일치율"] = round(sum(len({vote(j, i) for j in pair}) == 1 for i in two) / len(two), 3) if two else None
        # GPT 셋째 판정이 한도로 빠져 다수결을 다 못 냄 — 두 판정자 기준 범위로 적음(2026-10-31)
        row["두 판정자 모두 맞음"] = boot({i: (float(all(vote(j, i) for j in pair)), 1) for i in two})
        row["한 판정자 이상 맞음"] = boot({i: (float(any(vote(j, i) for j in pair)), 1) for i in two})
        house = {x["id"] for x in xs if any(h in x["kind"] for h in HOUSE)}
        row["다수결 맞음 비율"] = boot(major)
        row["다수결 맞음 비율(문체 결정 지적 뺌)"] = boot({i: v for i, v in major.items() if i not in house})
        row["문체 결정 지적 수"] = len(house)
        row["표본"] = len(xs)
        table[name] = row
    return table


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("judge")
    j.add_argument("names", nargs="+")
    j.add_argument("--tiebreak", action="store_true", help="앞 두 판정자가 갈린 지적만 부름")
    s = sub.add_parser("score")
    s.add_argument("--json")
    a = ap.parse_args()
    if a.cmd == "judge":
        judge(a.names, a.tiebreak)
        return 0
    t = score()
    for name, v in t.items():
        m = v["다수결 맞음 비율"]
        h = v["다수결 맞음 비율(문체 결정 지적 뺌)"]
        print(f"{name:16s} 다수결 {m[0]:.2f} [{m[1]:.2f}~{m[2]:.2f}]  문체 결정 뺌 {h[0]:.2f}  표본 {v['표본']}  "
              + " ".join(f"{k.split()[0]}:{x[0]:.2f}" for k, x in v.items() if k.endswith("판정 맞음 비율")))
    if a.json:
        Path(a.json).write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
