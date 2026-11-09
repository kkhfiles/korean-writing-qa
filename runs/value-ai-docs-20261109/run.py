"""AI 투 교정의 품질과 반복 수정 효율 — 사전 기록은 plan.md.

본문(생성 문서, 고친 판, 판정 기록, 사용자 메모)은 저장소 밖 작업 폴더에만 쓴다. 저장소에는 집계(result.json)만.
모델 호출은 모두 구독이다. 사람이 손으로 돌리는 측정이다.

    python -X utf8 runs/value-ai-docs-20261109/run.py <작업 폴더> gen
    python -X utf8 runs/value-ai-docs-20261109/run.py <작업 폴더> flows [--only 흐름,…] [--docs 이름,…]
    python -X utf8 runs/value-ai-docs-20261109/run.py <작업 폴더> sheet        # 사람 판정 화면을 띄움(제출하면 끝)
    python -X utf8 runs/value-ai-docs-20261109/run.py <작업 폴더> score
"""
from __future__ import annotations

import contextlib
import difflib
import http.server
import importlib.util
import io
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "scripts"))
os.environ["LLM_PLAYBOOK_BILLING"] = "subscription"

import bench_loop  # noqa: E402
import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from llm_playbook.backends.claude_sdk import call_messages  # noqa: E402

HANGUL = re.compile(r"[가-힣]")
LEVEL = ["--level", "balanced", "--over-budget", "--note", "측정 도구(value-ai-docs) — 비용 한도는 측정 대상이 아님"]
MAX_CALLS = 40
LOOP_MAX = 5
NO_CHANGE = "변경 없음"
REINJECT = {"대구": r"(이|가) 아니라", "결국": r"결국", "이유입니다": r"이유입니다"}


def load(name: str, path: Path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


probe = load("probe", REPO / "scripts/probe_layer2_kinds.py")
imn = load("imn", REPO / "runs/imnotai-miss-mining-20261023/run.py")
chk = load("chk", REPO / "assets/doc-style-check.py")

# ---------------------------------------------------------------- 생성

TOPICS = {
    "weekly": ("가상의 회사에서 사내 시험 자동화 도구를 만드는 5명 개발팀의 주간 업무 보고서를 한국어로 써 주세요. "
               "이번 주에 한 일, 이슈와 위험, 다음 주 계획을 넣고 진척률, 건수, 날짜 같은 숫자를 몇 개 넣어 주세요. "
               "마크다운으로 1,000~1,500자. 보고서 본문만 출력하세요."),
    "notice": ("가상의 회사에서 사내 메신저를 새 도구로 바꾸는 일정과 직원이 준비할 일을 전 직원에게 알리는 공지문을 "
               "한국어로 써 주세요. 일정, 직원이 할 일, 바뀌는 점, 문의처(가상)를 넣어 주세요. 마크다운으로 "
               "800~1,200자. 공지문 본문만 출력하세요."),
}
WRITERS = ("claude", "gpt", "gemini")


def write_doc(writer: str, prompt: str) -> tuple[str, dict]:
    t = time.time()
    if writer == "claude":
        r = call_messages(model="opus", system=None, user=prompt, max_tokens=8000, timeout=600, billing="subscription")
        return r["text"], {"model": r.get("model"), "sec": round(time.time() - t), "cost_usd": r.get("cost_usd")}
    if writer == "gpt":
        from llm_playbook.backends import codex_http
        r = codex_http.call(prompt, model="sol-medium", fallback=False, timeout=600)
    else:
        from llm_playbook.backends import agy
        r = agy.call(prompt, model="flash-high", fallback=False, tools="none", timeout=600)
    return r.get("text") or r.get("output") or "", {"model": r.get("model"), "sec": round(time.time() - t)}


def gen(work: Path) -> None:
    (work / "docs").mkdir(parents=True, exist_ok=True)
    meta = {}
    for topic, prompt in TOPICS.items():
        for w in WRITERS:
            name = f"{w}-{topic}"
            f = work / "docs" / f"{name}.md"
            if f.exists():
                continue
            text, info = write_doc(w, prompt)
            f.write_text(imn.unfence(text).strip() + "\n", encoding="utf-8")
            meta[name] = info
            print(name, json.dumps(info, ensure_ascii=False), flush=True)
    old = json.loads((work / "gen.json").read_text(encoding="utf-8")) if (work / "gen.json").exists() else {}
    (work / "gen.json").write_text(json.dumps({**old, **meta}, ensure_ascii=False, indent=1), encoding="utf-8")

# ---------------------------------------------------------------- 고치는 흐름

PLAIN = ("당신은 한국어 업무 문서 편집자입니다. 사용자가 준 문서를 자연스러운 한국어 업무 문서로 다듬습니다. "
         "사실, 숫자, 이름, 일정은 바꾸지 않습니다. 고친 문서 전체만 출력하고 설명은 붙이지 않습니다.")
RULES_TAIL = ("\n\n---\n\n당신은 위 판단 규칙을 따르는 한국어 업무 문서 편집자입니다. 사용자가 준 문서를 위 규칙에 맞게 "
              "고칩니다. 사실, 숫자, 이름, 일정은 바꾸지 않고, 규칙에 걸리지 않는 곳은 그대로 둡니다. 고친 문서 전체만 "
              "출력하고 설명은 붙이지 않습니다. 고칠 곳이 하나도 없으면 「" + NO_CHANGE + "」 한 줄만 출력합니다.")


def opus(system: str, text: str) -> tuple[str, dict]:
    t = time.time()
    r = call_messages(model="opus", system=system, user=text, max_tokens=32000, timeout=900, billing="subscription")
    return imn.unfence(r["text"]).strip(), {"calls": 1, "sec": round(time.time() - t), "cost_usd": r.get("cost_usd") or 0}


def add(a: dict, b: dict) -> dict:
    return {k: round((a.get(k) or 0) + (b.get(k) or 0), 4) for k in set(a) | set(b)}


def split_front(text: str) -> tuple[str, str]:
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    return (m.group(0), text[m.end():]) if m else ("", text)


def pieces(text: str) -> list[str]:
    """운반 문서는 판정기와 같은 절 단위 묶음으로 — 문서 한 편은 통째로."""
    if len(HANGUL.findall(text)) <= 3000:
        return [text]
    lines = text.splitlines()
    return ["\n".join(lines[a:b]) for a, b in probe.chunks(text)]


def flow_plain(text: str, work: Path) -> tuple[str, dict]:
    out, cost = [], {}
    for p in pieces(text):
        t, c = opus(PLAIN, p)
        out.append(t)
        cost = add(cost, c)
    return "\n".join(out), cost


def rules_system() -> str:
    return probe.rules_for("guided") + RULES_TAIL


def flow_rules(text: str, work: Path) -> tuple[str, dict]:
    out, cost, system = [], {}, rules_system()
    for p in pieces(text):
        t, c = opus(system, p)
        out.append(p if t.strip() == NO_CHANGE else t)
        cost = add(cost, c)
    return "\n".join(out), cost


def flow_rules_loop(text: str, work: Path) -> tuple[str, dict]:
    cur, cost, system, rounds = text, {}, rules_system(), 0
    for _ in range(LOOP_MAX):
        t, c = opus(system, cur)
        cost = add(cost, c)
        rounds += 1
        if t.strip() == NO_CHANGE or t.strip() == cur.strip():
            break
        cur = t
    cost["rounds"] = rounds
    return cur, cost


def flow_imnotai(text: str, work: Path) -> tuple[str, dict]:
    out, cost = [], {}
    for i, p in enumerate(pieces(text)):
        w = work / f"piece{i}"
        w.mkdir(parents=True, exist_ok=True)
        (w / "01_input.txt").write_text(p, encoding="utf-8")
        t, log = imn.imnotai(w)
        out.append(t.strip())
        for step in log.values():
            cost = add(cost, {"calls": 1, "sec": step.get("sec") or 0, "cost_usd": step.get("cost_usd") or 0})
    return "\n".join(out), cost


def checker(text: str, work: Path, since: bool) -> tuple[str, dict]:
    """세션 흉내 — 판정, 수정안 적용, (고친 줄만 | 문서 전체) 다시 판정을 끝날 때까지."""
    work.mkdir(parents=True, exist_ok=True)
    doc = work / "doc.md"
    doc.write_text(text, encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@localhost", "-C", str(work), *args],
                       capture_output=True, check=True)
    git("init", "-q", "-b", "main")
    git("add", "doc.md")
    git("commit", "-q", "-m", "base")
    git("switch", "-q", "-c", "work")
    counts = {k: 0 for k in ("사람 답", "사실 확인 닫기", "지시반영 닫기", "지시 밖 짚음 처리", "적용",
                             "적용 못함 닫기", "되돌림 닫기", "되살림 닫기")}
    history, calls, said, rounds, state, held = {}, [], io.StringIO(), 0, "완료", 0
    with bench_loop.isolated(work):
        for rnd in range(20):
            if len(calls) >= MAX_CALLS:
                state = "호출 상한"
                break
            out = work / f"round{rnd}.json"
            argv = [str(doc), "--json", str(out), *LEVEL] + (["--since", "main"] if rnd and since else [])
            with contextlib.redirect_stdout(said):
                rc = judge.main(argv)
            if rc not in (0, 1) or not out.is_file():
                state = f"실패 rc={rc}"
                break
            res = json.loads(out.read_text(encoding="utf-8"))[0]
            calls += res["calls"]
            held += sum(1 for f in res["findings"] if f.get("held"))
            rounds += 1 if res["calls"] else 0
            did = bench_loop.process(doc, {}, "batch", counts, history)
            if not did:
                break
        else:
            state = "회차 상한"
    (work / "judge-output.txt").write_text(said.getvalue(), encoding="utf-8")
    cost = {"calls": len(calls), "rounds": rounds, "sec": round(sum(c.get("seconds") or 0 for c in calls)),
            "cost_usd": round(sum(c.get("cost_usd") or 0 for c in calls), 4), "held": held,
            "applied": counts["적용"], "answered": counts["사람 답"], "state": state}
    return doc.read_text(encoding="utf-8"), cost


L1_SYSTEM = ("당신은 한국어 업무 문서 편집자입니다. 사용자가 줄 번호를 붙인 문서와 문서 검사기가 짚은 줄 목록을 줍니다. "
             "짚은 줄만 검사기 안내대로 고치고, 짚지 않은 줄은 글자 하나 바꾸지 않습니다. 사실, 숫자, 이름, 일정은 바꾸지 "
             "않습니다. 줄 번호를 뺀 문서 전체(맨 앞 머리말 포함)만 출력하고 설명은 붙이지 않습니다.")


def form_of(name: str) -> str:
    """문서 형식 — 실사용에서는 사용자가 고른다(finalize 스킬 8단계). 공지는 공지형, 주간보고는 구조형."""
    return "notice" if name.endswith("notice") else "structured"


def l1_errors(doc: Path) -> list[tuple[str, str]]:
    err, _, _ = chk.scan_md(str(doc))
    return err


def checker2(text: str, work: Path, form: str | None) -> tuple[str, dict]:
    """실사용 흐름 — 2층 판정과 수정안 반영(사실 확인은 작성자가 확인해 줬다고 봄)을 끝까지 돈 뒤, 1층 오류 줄을 고치고
    (세션이 하는 일을 Opus 한 번으로) 고친 줄을 다시 판정한다. 1층 오류가 없거나 더 바뀌지 않을 때까지 최대 3회."""
    work.mkdir(parents=True, exist_ok=True)
    doc = work / "doc.md"
    front = f"---\nform: {form}\n---\n" if form and not text.startswith("---\n") else ""
    doc.write_text(front + text, encoding="utf-8")

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=bench", "-c", "user.email=bench@localhost", "-C", str(work), *args],
                       capture_output=True, check=True)
    git("init", "-q", "-b", "main")
    git("add", "doc.md")
    git("commit", "-q", "-m", "base")
    git("switch", "-q", "-c", "work")
    counts = {k: 0 for k in ("사람 답", "사실 확인 닫기", "지시반영 닫기", "지시 밖 짚음 처리", "적용",
                             "적용 못함 닫기", "되돌림 닫기", "되살림 닫기")}
    history, calls, said, rounds, state, held, rnd = {}, [], io.StringIO(), 0, "완료", 0, 0
    l1 = {"처음": len(l1_errors(doc)), "고침 호출": 0, "고침 비용": 0.0, "고침 초": 0}
    with bench_loop.isolated(work):
        for outer in range(3):
            while rnd < 20 and len(calls) < MAX_CALLS:
                # 1층 고침이 줄을 앞 판으로 되돌리면 그때의 지적이 다시 열리고, 판정기는 열린 지적이 남으면 재판정을
                # 미룬다(종료 코드 6 · Gemini 공지에서 실측) — 세션처럼 먼저 처리하고 부른다
                if rnd:
                    bench_loop.process(doc, {}, "batch", counts, history, apply_checked=True)
                out = work / f"round{rnd}.json"
                argv = [str(doc), "--json", str(out), *LEVEL] + (["--since", "main"] if rnd else [])
                with contextlib.redirect_stdout(said):
                    rc = judge.main(argv)
                rnd += 1
                if rc not in (0, 1) or not out.is_file():
                    state = f"실패 rc={rc}"
                    break
                res = json.loads(out.read_text(encoding="utf-8"))[0]
                calls += res["calls"]
                held += sum(1 for f in res["findings"] if f.get("held"))
                rounds += 1 if res["calls"] else 0
                if not bench_loop.process(doc, {}, "batch", counts, history, apply_checked=True):
                    break
            errs = l1_errors(doc)
            if not errs or state != "완료":
                break
            lines = doc.read_text(encoding="utf-8").splitlines()
            listing = "\n".join(f"- {msg}  [{kind}]" for kind, msg in errs)
            numbered = "\n".join(f"{i}\t{l}" for i, l in enumerate(lines, 1))
            new, c = opus(L1_SYSTEM, f"## 검사기가 짚은 줄\n\n{listing}\n\n## 문서\n\n{numbered}")
            l1["고침 호출"] += 1
            l1["고침 비용"] = round(l1["고침 비용"] + (c.get("cost_usd") or 0), 4)
            l1["고침 초"] += c.get("sec") or 0
            if front and not new.startswith("---\n"):
                new = front + new
            if new.strip() == "\n".join(lines).strip():
                break
            doc.write_text(new.rstrip() + "\n", encoding="utf-8")
    l1["끝"] = len(l1_errors(doc))
    (work / "judge-output.txt").write_text(said.getvalue(), encoding="utf-8")
    final = doc.read_text(encoding="utf-8")
    if front and final.startswith(front):
        final = final[len(front):]
    cost = {"calls": len(calls) + l1["고침 호출"], "rounds": rounds,
            "sec": round(sum(c.get("seconds") or 0 for c in calls)) + l1["고침 초"],
            "cost_usd": round(sum(c.get("cost_usd") or 0 for c in calls) + l1["고침 비용"], 4), "held": held,
            "applied": counts["적용"], "answered": counts["사람 답"], "state": state, "1층": l1}
    return final, cost


FLOWS = {
    "plain": flow_plain, "rules": flow_rules, "imnotai": flow_imnotai, "rules_loop": flow_rules_loop,
    "checker": lambda t, w: checker(t, w, True), "checker_full": lambda t, w: checker(t, w, False),
    "checker2": None,      # 문서 형식을 이름으로 정해야 해서 flows 에서 부른다
}
CARRIER_FLOWS = ("plain", "rules", "imnotai", "checker", "checker2")


def flows(work: Path, only: list[str] | None, docs: list[str] | None) -> None:
    jobs = [(f.stem, f.read_text(encoding="utf-8"), list(FLOWS)) for f in sorted((work / "docs").glob("*.md"))]
    jobs.append(("carrier", probe.CARRIER.read_text(encoding="utf-8"), list(CARRIER_FLOWS)))
    for name, text, names in jobs:
        if docs and name not in docs:
            continue
        front, body = split_front(text)
        for fl in names:
            if only and fl not in only:
                continue
            d = work / "out" / name / fl
            if (d / "result.md").exists():
                continue
            d.mkdir(parents=True, exist_ok=True)
            print(f"[{time.strftime('%H:%M:%S')}] {name} {fl}", flush=True)
            # 판정기 흐름은 머리말(form: prose)까지 넘긴다 — 운반 문서가 1층에서 조용하도록 만든 표시
            src = text if fl.startswith("checker") else body
            try:
                if fl == "checker2":
                    after, cost = checker2(src, d / "work", None if name == "carrier" else form_of(name))
                else:
                    after, cost = FLOWS[fl](src, d / "work")
            except Exception as e:  # 한 흐름이 실패해도 나머지는 돈다 — 실패는 기록에 남긴다
                (d / "error.txt").write_text(f"{type(e).__name__}: {e}", encoding="utf-8")
                print(f"  실패 {type(e).__name__}: {e}"[:300], flush=True)
                continue
            if not fl.startswith("checker"):
                after = front + after
            (d / "result.md").write_text(after.rstrip() + "\n", encoding="utf-8")
            (d / "cost.json").write_text(json.dumps(cost, ensure_ascii=False, indent=1), encoding="utf-8")
            print("  " + json.dumps(cost, ensure_ascii=False), flush=True)

# ---------------------------------------------------------------- 사람 판정 화면

SHEET_FLOWS = ("source", "plain", "rules", "imnotai", "rules_loop", "checker")
LABELS = "가나다라마바"


def version(work: Path, name: str, fl: str) -> str | None:
    f = work / "docs" / f"{name}.md" if fl == "source" else work / "out" / name / fl / "result.md"
    return f.read_text(encoding="utf-8") if f.exists() else None


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def spans(src: list[str], out: list[str]) -> list[tuple[int, int]]:
    """고친 판이 원문과 달라진 원문 줄 구간 [a, b). 끼워 넣은 줄은 바로 앞 원문 줄 구간에 붙인다."""
    sm = difflib.SequenceMatcher(None, [x.strip() for x in src], [x.strip() for x in out], autojunk=False)
    res = []
    for op, a, b, _, _ in sm.get_opcodes():
        if op == "equal":
            continue
        if a == b:
            a = max(0, a - 1)
            b = a + 1
        res.append((a, b))
    return res


def spot_text(src: list[str], out: list[str], a: int, b: int) -> str:
    """원문 [a, b) 에 해당하는 고친 판의 글 — 같은 줄은 그대로, 달라진 구간은 고친 줄."""
    sm = difflib.SequenceMatcher(None, [x.strip() for x in src], [x.strip() for x in out], autojunk=False)
    got = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            lo, hi = max(a, i1), min(b, i2)
            got += out[j1 + lo - i1:j1 + hi - i1] if lo < hi else []
        elif (i1 < b and i2 > a) or (i1 == i2 and a <= i1 <= b):
            got += out[j1:j2]
    return "\n".join(x for x in got if x.strip()).strip()


def marked(base: str, text: str) -> str:
    """원문과 달라진 글자를 표시 — 넣은 글자는 <ins>, 지운 글자는 <del>."""
    sm = difflib.SequenceMatcher(None, base, text, autojunk=False)
    out = []
    for op, a, b, c, d in sm.get_opcodes():
        if op == "equal":
            out.append(esc(text[c:d]))
            continue
        if b > a:
            out.append(f"<del>{esc(base[a:b])}</del>")
        if d > c:
            out.append(f"<ins>{esc(text[c:d])}</ins>")
    return "".join(out)


def spots(work: Path) -> list[dict]:
    """문서마다 판끼리 다른 대목 — 대목마다 서로 다른 표현(같은 글은 하나로)과 그 표현을 낸 흐름."""
    rng = random.Random(20261109)
    names = [f.stem for f in sorted((work / "docs").glob("*.md"))]
    rng.shuffle(names)
    res = []
    for name in names:
        src = version(work, name, "source").splitlines()
        outs = {fl: version(work, name, fl).splitlines() for fl in SHEET_FLOWS[1:] if version(work, name, fl)}
        ivs = sorted(iv for o in outs.values() for iv in spans(src, o))
        merged = []
        for a, b in ivs:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            base = "\n".join(x for x in src[a:b] if x.strip()).strip()
            texts = {"source": base, **{fl: spot_text(src, o, a, b) for fl, o in outs.items()}}
            variants: dict[str, list[str]] = {}
            for fl, t in texts.items():
                variants.setdefault(t, []).append(fl)
            if len(variants) < 2:
                continue
            opts = list(variants.items())
            rng.shuffle(opts)
            res.append({"doc": name, "lines": [a + 1, b], "base": base,
                        "options": [{"text": t, "flows": fls} for t, fls in opts]})
    return res


def sheet(work: Path, port: int = 8765) -> None:
    items = spots(work)
    (work / "sheet-key.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    docs = list(dict.fromkeys(it["doc"] for it in items))
    blocks = []
    for k, it in enumerate(items):
        opts = "".join(
            f'<label class="opt"><input type="radio" name="s{k}" value="{j}">'
            f'<span class="t">{marked(it["base"], o["text"]) if o["text"] else "<em>(이 대목을 지움)</em>"}</span></label>'
            for j, o in enumerate(it["options"]))
        blocks.append(
            f'<section><h2>문서 {docs.index(it["doc"]) + 1} · 대목 {k + 1} / {len(items)}</h2>'
            f'<div class="base">원문: {esc(it["base"]) or "(없음)"}</div>{opts}'
            f'<label class="opt"><input type="radio" name="s{k}" value="none"><span class="t">고르기 어려움</span></label>'
            f'<input class="note" name="n{k}" placeholder="메모(선택)"></section>')
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>AI 투 교정 블라인드 판정</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{{color-scheme:light}} body{{font-family:Pretendard,"Malgun Gothic",sans-serif;background:#f7f7f5;color:#1d1d1b;margin:0 auto;max-width:980px;padding:16px 20px;line-height:1.7;word-break:keep-all}}
h1{{font-size:20px}} h2{{font-size:14px;color:#55554f;margin:0 0 6px}} .lead{{max-width:70ch}}
section{{background:#fff;border:1px solid #d6d6d0;border-radius:6px;padding:12px 14px;margin:14px 0}}
.base{{font-size:13px;color:#66665f;margin-bottom:8px;white-space:pre-wrap}}
.opt{{display:flex;gap:10px;align-items:flex-start;padding:6px 8px;border-radius:4px;cursor:pointer}} .opt:hover{{background:#f1f1ec}}
.opt input{{margin-top:6px}} .t{{white-space:pre-wrap}}
ins{{background:#d8f0d2;text-decoration:none}} del{{background:#f6d6d2;color:#7a3b33}}
.note{{width:100%;font:inherit;margin-top:6px;padding:4px 6px}} button{{font:inherit;font-size:16px;padding:10px 24px;margin:20px 0}}
</style></head><body><h1>AI 투 교정 블라인드 판정</h1>
<p class="lead">판끼리 표현이 다른 대목만 모았습니다. 대목마다 서로 다른 표현만 보이고(같은 표현은 하나로 합침), 원문과 달라진 글자는 <ins>초록</ins>(넣음)과 <del>빨강</del>(지움)으로 표시했습니다. 원문 그대로인 선택지도 섞여 있고, 순서는 무작위입니다. 「AI 투가 없고 업무 문서로 자연스러우며 뜻이 원문과 같은가」를 기준으로 가장 나은 하나를 고르세요. 다 고른 뒤 맨 아래 「제출」을 누르면 됩니다.</p>
<form method="post">{"".join(blocks)}<button type="submit">제출</button></form></body></html>"""
    done = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))

        def do_POST(self):
            from urllib.parse import parse_qs
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
            form = {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}
            (work / "sheet-answers.json").write_text(json.dumps(form, ensure_ascii=False, indent=1), encoding="utf-8")
            done["ok"] = True
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<p>받았습니다. 창을 닫아도 됩니다.</p>".encode("utf-8"))

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    print(f"http://127.0.0.1:{port}/ — 제출하면 끝납니다", flush=True)
    while not done:
        srv.handle_request()

# ---------------------------------------------------------------- 표현 판정(2026-11-09 사용자 「일관된 규칙으로 분류해서 그것만 고르게」)

PAIR_FLOWS = ("plain", "rules", "imnotai", "rules_loop", "checker")
KINDS = ("낱말 바꿈", "풀어 씀", "줄임", "문장 고쳐 씀")
PER_KIND = 2
MARKUP = re.compile(r"[\s*_`#>|·.,:;!?()\[\]「」'\"“”‘’~\-]")
TOKEN = re.compile(r"\S+|\n")


def kind_of(a: list[str], b: list[str]) -> str | None:
    """바뀐 어절 구간의 갈래 — 기호와 서식만 다르면 None(판정에서 뺌)."""
    if MARKUP.sub("", "".join(a)) == MARKUP.sub("", "".join(b)):
        return None
    if len(a) <= 2 and len(b) <= 2:
        return "낱말 바꿈"
    if len(b) - len(a) >= 3:
        return "풀어 씀"
    if len(a) - len(b) >= 3:
        return "줄임"
    return "문장 고쳐 씀"


def edits(src: str, out: str) -> list[dict]:
    """원문과 고친 판의 어절 단위 차이 — 앞뒤 어절 하나씩을 문맥으로."""
    s, o = TOKEN.findall(src), TOKEN.findall(out)
    words = lambda xs: [x for x in xs if x != "\n"]
    res = []
    for op, a, b, c, d in difflib.SequenceMatcher(None, s, o, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        k = kind_of(words(s[a:b]), words(o[c:d]))
        if k is None:
            continue
        before = " ".join(words(s[max(0, a - 6):a])[-2:])     # 같은 줄 안의 앞뒤 두 어절
        after = " ".join(words(s[b:b + 6])[:2])
        before = before if "\n" not in "".join(s[max(0, a - 2):a]) else before.split()[-1] if before else ""
        res.append({"kind": k, "before": before, "after": after,
                    "old": " ".join(words(s[a:b])), "new": " ".join(words(o[c:d]))})
    return res


def pairs(work: Path) -> list[dict]:
    """흐름마다 갈래별 최대 PER_KIND 건 — 같은 표현을 여러 흐름이 냈으면 한 건으로 합친다."""
    rng = random.Random(20261109)
    pool: dict[tuple, dict] = {}
    for f in sorted((work / "docs").glob("*.md")):
        src = f.read_text(encoding="utf-8")
        for fl in PAIR_FLOWS:
            out = version(work, f.stem, fl)
            for e in edits(src, out) if out else []:
                key = (f.stem, e["before"], e["old"], e["after"], e["new"])
                pool.setdefault(key, {**e, "doc": f.stem, "flows": []})["flows"].append(fl)
    items = list(pool.values())
    rng.shuffle(items)
    picked, used = [], set()
    for fl in PAIR_FLOWS:
        for k in KINDS:
            got = [i for i, it in enumerate(items) if fl in it["flows"] and it["kind"] == k][:PER_KIND]
            for i in got:
                if i not in used:
                    used.add(i)
                    picked.append(items[i])
    rng.shuffle(picked)
    return picked


def pair_key(it: dict) -> tuple:
    return it["doc"], it["before"], it["old"], it["after"], it["new"]


def carried_answers(work: Path, items: list[dict]) -> dict:
    """앞서 답한 표현과 글자가 같은 표현의 답 — 다시 묻지 않는다(2026-11-09 Gemini 문서를 깨끗하게 다시 만든 뒤)."""
    kf, af = work / "sheet2-key.v1.json", work / "sheet2-answers.v1.json"
    if not (kf.exists() and af.exists()):
        return {}
    k, a = json.loads(kf.read_text(encoding="utf-8")), json.loads(af.read_text(encoding="utf-8"))
    old = {pair_key(it): a[f"p{i}"] for i, it in enumerate(k) if a.get(f"p{i}")}
    return {f"p{i}": old[pair_key(it)] for i, it in enumerate(items) if pair_key(it) in old}


def pair_sheet(work: Path, port: int) -> None:
    items = pairs(work)
    carried = carried_answers(work, items)
    (work / "sheet2-key.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    rows = []
    for k, it in enumerate(items):
        if f"p{k}" in carried:
            continue
        ctx = lambda mid, tag: (f'{esc(it["before"])} <{tag}>{esc(mid) or "(지움)"}</{tag}> {esc(it["after"])}')
        radios = "".join(f'<label><input type="radio" name="p{k}" value="{v}">{v}</label>'
                         for v in ("나아짐", "비슷함", "나빠짐"))
        rows.append(f'<tr><td class="n">{k + 1}</td><td>{ctx(it["old"], "del")}</td><td>{ctx(it["new"], "ins")}</td>'
                    f'<td class="r">{radios}</td></tr>')
    page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>AI 투 교정 표현 판정</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{{color-scheme:light}} body{{font-family:Pretendard,"Malgun Gothic",sans-serif;background:#f7f7f5;color:#1d1d1b;margin:0 auto;max-width:1100px;padding:16px 20px;line-height:1.6;word-break:keep-all}}
h1{{font-size:20px}} .lead{{max-width:75ch}} table{{border-collapse:collapse;width:100%;background:#fff}}
th,td{{border-bottom:1px solid #e2e2dc;padding:8px;vertical-align:top;text-align:left}} th{{font-size:13px;color:#55554f}}
td.n{{color:#88887f;font-variant-numeric:tabular-nums;width:2.5em}} td.r{{white-space:nowrap}} td.r label{{margin-right:10px;cursor:pointer}}
ins{{background:#d8f0d2;text-decoration:none}} del{{background:#f6d6d2;text-decoration:none}}
button{{font:inherit;font-size:16px;padding:10px 24px;margin:20px 0}}
</style></head><body><h1>AI 투 교정 표현 판정</h1>
<p class="lead">다섯 가지 고치는 방식이 원문을 바꾼 표현을 같은 규칙으로 네 갈래(낱말 바꿈, 풀어 씀, 줄임, 문장 고쳐 씀)로 나누고, 방식마다 갈래별 두 건씩만 뽑았습니다. 기호와 서식만 다른 것은 뺐고, 어느 방식이 고쳤는지는 숨겼습니다. 앞뒤 어절 하나씩을 함께 보입니다. 원문 표현(빨강)보다 고친 표현(초록)이 「AI 투가 없고 업무 문서로 자연스러우며 뜻이 같은가」 기준으로 나아졌는지 골라 주세요. 다 고른 뒤 맨 아래 「제출」을 누르면 됩니다.</p>
<form method="post"><table><tr><th>#</th><th>원문</th><th>고친 표현</th><th>판정</th></tr>{"".join(rows)}</table>
<button type="submit">제출</button></form></body></html>"""
    print(f"앞서 답한 표현 {len(carried)}건은 답을 그대로 씀 · 새로 물을 표현 {len(items) - len(carried)}건", flush=True)
    serve(work, page, port, "sheet2-answers.json", carried)


def serve(work: Path, page: str, port: int, out_name: str, carried: dict | None = None) -> None:
    done = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))

        def do_POST(self):
            from urllib.parse import parse_qs
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
            form = {**(carried or {}), **{k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}}
            (work / out_name).write_text(json.dumps(form, ensure_ascii=False, indent=1), encoding="utf-8")
            done["ok"] = True
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<p>받았습니다. 창을 닫아도 됩니다.</p>".encode("utf-8"))

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    print(f"http://127.0.0.1:{port}/ — 제출하면 끝납니다", flush=True)
    while not done:
        srv.handle_request()


def pair_score(work: Path) -> dict | None:
    ans_f, key_f = work / "sheet2-answers.json", work / "sheet2-key.json"
    if not (ans_f.exists() and key_f.exists()):
        return None
    ans, key = json.loads(ans_f.read_text(encoding="utf-8")), json.loads(key_f.read_text(encoding="utf-8"))
    tally: dict = {}
    for k, it in enumerate(key):
        v = ans.get(f"p{k}")
        if not v:
            continue
        for fl in it["flows"]:
            for g in (it["kind"], "전체"):
                t = tally.setdefault(fl, {}).setdefault(g, {"나아짐": 0, "비슷함": 0, "나빠짐": 0})
                t[v] += 1
    net = {fl: {g: {**t, "나아짐−나빠짐 비율": round((t["나아짐"] - t["나빠짐"]) / max(1, sum(t.values())), 2)}
                for g, t in gs.items()} for fl, gs in tally.items()}
    return {"방식": "2026-11-09 사용자 「일관된 규칙으로 분류해서 그것만 고르게」 — 바뀐 표현을 기계 규칙으로 네 갈래로 "
                  f"나누고 흐름마다 갈래별 {PER_KIND}건을 고정 씨앗으로 뽑아 「나아짐, 비슷함, 나빠짐」으로 판정. "
                  "사전 기록의 판 순위와 다른 방식이라 탐색적",
            "표현": len(key), "답한 표현": sum(1 for k in range(len(key)) if ans.get(f"p{k}")), "흐름별": net}

# ---------------------------------------------------------------- 집계


def l1_count(text: str) -> tuple[int, int]:
    tmp = Path(os.environ.get("TEMP", ".")) / "value-ai-docs-l1.md"
    tmp.write_text(text, encoding="utf-8")
    err, warn, _ = chk.scan_md(str(tmp))
    return len(err), len(warn)


def meaning(before: str, after: str) -> dict:
    a, b = Path(os.environ.get("TEMP", ".")) / "vad-a.md", Path(os.environ.get("TEMP", ".")) / "vad-b.md"
    a.write_text(before, encoding="utf-8")
    b.write_text(after, encoding="utf-8")
    p = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "skills/finalize-korean-document/scripts/check_meaning.py"),
                        str(a), str(b), "--strict"], capture_output=True, text=True, encoding="utf-8")
    try:
        r = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"status": "읽기 실패"}
    return {"status": r.get("status"), "protected_removed": len(r.get("protected_removed") or []),
            "marker_drops": r.get("meaning_marker_drops")}


def change_rate(a: str, b: str) -> float:
    return round(1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 3)


def score(work: Path) -> dict:
    res = {"이름": "AI 투 교정의 품질과 반복 수정 효율", "사전 기록": "plan.md"}
    # 측정 1a — 152건 고침률
    items = probe.planted() + probe.held_out()
    carrier = probe.CARRIER.read_text(encoding="utf-8")
    plant_lines = {i for i, l in enumerate(carrier.splitlines()) if any(it["text"] in l for it in items)}
    a1 = {}
    for fl in CARRIER_FLOWS:
        after = version(work, "carrier", fl)
        if after is None:
            continue
        gone = [it for it in items if it["text"] not in after]
        src = carrier.splitlines()
        other = [l for i, l in enumerate(src) if i not in plant_lines and HANGUL.search(l)]
        after_lines = set(after.splitlines())
        cost = json.loads((work / "out/carrier" / fl / "cost.json").read_text(encoding="utf-8"))
        a1[fl] = {"고침(전체)": f"{len(gone)}/{len(items)}",
                  "고침(대장)": f"{sum(1 for it in gone if it['source'] == '대장')}/{sum(1 for it in items if it['source'] == '대장')}",
                  "고침(예비)": f"{sum(1 for it in gone if it['source'] == '예비')}/{sum(1 for it in items if it['source'] == '예비')}",
                  "심은 표현 없는 줄 변경": f"{sum(1 for l in other if l not in after_lines)}/{len(other)}",
                  "환산 비용": cost.get("cost_usd"), "호출": cost.get("calls"), "초": cost.get("sec")}
    res["측정 1a — 152건 고침률"] = a1
    # 측정 1b 자동 지표와 측정 2
    docs = [f.stem for f in sorted((work / "docs").glob("*.md"))]
    auto, eff = {}, {}
    for name in docs:
        src = version(work, name, "source")
        auto[name] = {"원문 1층": l1_count(src)}
        for fl in FLOWS:
            after = version(work, name, fl)
            if after is None:
                continue
            row = {"변경률": change_rate(src, after), "1층(오류, 주의)": l1_count(after), "뜻": meaning(src, after),
                   "새 꼴": {k: max(0, len(re.findall(p, after)) - len(re.findall(p, src))) for k, p in REINJECT.items()}}
            auto[name][fl] = row
            cost = json.loads((work / "out" / name / fl / "cost.json").read_text(encoding="utf-8"))
            eff.setdefault(fl, {})[name] = cost
    res["측정 1b — 자동 지표"] = auto
    res["측정 2 — 흐름별 비용"] = eff
    # 측정 1b — 사람 판정
    ans_f, key_f = work / "sheet-answers.json", work / "sheet-key.json"
    if ans_f.exists() and key_f.exists():
        ans, key = json.loads(ans_f.read_text(encoding="utf-8")), json.loads(key_f.read_text(encoding="utf-8"))
        chosen = []                     # 대목마다 고른 표현을 낸 흐름 집합 · 고르기 어려움은 뺀다
        for k, it in enumerate(key):
            v = ans.get(f"s{k}")
            if v not in (None, "", "none"):
                chosen.append((it, set(it["options"][int(v)]["flows"])))
        share = {fl: f"{sum(fl in c for _, c in chosen)}/{len(chosen)}" for fl in SHEET_FLOWS}
        wins = {}
        for fl in SHEET_FLOWS:
            if fl == "checker":
                continue
            by_doc = {}
            for it, c in chosen:            # 두 흐름의 표현이 다르고 그중 하나를 고른 대목만
                same = any("checker" in o["flows"] and fl in o["flows"] for o in it["options"])
                if same or not ({"checker", fl} & c):
                    continue
                w = by_doc.setdefault(it["doc"], [0, 0])
                w[0 if "checker" in c else 1] += 1
            dw = sum(1 for a_, b_ in by_doc.values() if a_ > b_)
            dl = sum(1 for a_, b_ in by_doc.values() if a_ < b_)
            n = len(by_doc)
            verdict = "앞섬" if n >= 5 and dw >= 5 else "뒤짐" if n >= 5 and dw <= 1 and dl >= 4 else "판정 불가"
            wins[fl] = {"대목 승패(checker 승, 짐)": [sum(a_ for a_, _ in by_doc.values()), sum(b_ for _, b_ in by_doc.values())],
                        "문서 승패(checker 승, 짐, 비김 제외)": [dw, dl], "견준 문서": n, "가름": verdict}
        res["측정 1b — 사람 판정"] = {
            "방식 변경": "2026-11-09 사용자 「다른 표현이 있는 문장만 남겨놓든지 해야 비교를 수월하게 할 것」 — 판 전체 순위 대신 판끼리 다른 대목마다 가장 나은 표현 하나를 고름. 가름의 문서 기준(6편 중 5편)은 사전 기록 그대로이고, 문서 승패는 그 문서에서 checker 표현을 고른 대목 수가 상대보다 많은지로 셈",
            "대목": len(key), "고른 대목": len(chosen),
            "흐름별 표현이 뽑힌 대목": share, "checker 일대일": wins,
            "메모 남긴 대목": sum(1 for k, v in ans.items() if k.startswith("n") and v.strip())}
    ps = pair_score(work)
    if ps:
        res["측정 1b — 표현 판정"] = ps
    return res


def main() -> int:
    args = sys.argv[1:]
    work, cmd = Path(args[0]), args[1]
    opt = lambda flag: args[args.index(flag) + 1].split(",") if flag in args else None
    work.mkdir(parents=True, exist_ok=True)
    if cmd == "gen":
        gen(work)
    elif cmd == "flows":
        flows(work, opt("--only"), opt("--docs"))
    elif cmd == "sheet":
        sheet(work, int(opt("--port")[0]) if opt("--port") else 8765)
    elif cmd == "pairs":
        pair_sheet(work, int(opt("--port")[0]) if opt("--port") else 18932)
    elif cmd == "score":
        r = score(work)
        (HERE / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
