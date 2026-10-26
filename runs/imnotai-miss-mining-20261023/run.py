"""im-not-ai 정밀 경로로 고쳐 쓴 줄 중 이 저장소가 안 짚은 줄을 뽑는다 — 사전 기록은 plan.md.

본문은 저장소 밖 작업 폴더(첫 인자)에만 쓴다. 저장소에는 집계(summary.json)만 남긴다.
모델 호출은 모두 구독이다.

python -X utf8 runs/imnotai-miss-mining-20261023/run.py <작업 폴더> [doc-002 … | 파일 경로 …] [--summary 집계 경로]

파일 경로를 주면 그 문서를 쓴다(이름은 파일 이름 · 2026-10-26 실제 발행 문서 회차).
"""
import difflib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[1]
SRC = REPO / "data/raw/diagnostic-002"
DOCS = ["doc-002", "doc-004", "doc-005", "doc-015", "doc-016"]
IMN = Path.home() / ".claude/plugins/cache/im-not-ai/humanize-korean/2.3.2"
REFS = IMN / "skills/humanize-korean/references"
HANGUL = re.compile(r"[가-힣]")
os.environ["LLM_PLAYBOOK_BILLING"] = "subscription"

from llm_playbook.backends.claude_sdk import call_messages  # noqa: E402


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


chk = load("chk", REPO / "assets/doc-style-check.py")
sys.path.insert(0, str(REFS))
mv2 = load("metrics_v2", REFS / "metrics_v2.py")


def agent_body(name):
    """에이전트 정의에서 머리말을 뗀 본문 — 시스템 프롬프트로 쓴다."""
    t = (IMN / "agents" / f"{name}.md").read_text(encoding="utf-8")
    return re.sub(r"^---\n.*?\n---\n", "", t, count=1, flags=re.S)


def strip_front(t):
    return re.sub(r"^---\n.*?\n---\n", "", t, count=1, flags=re.S).lstrip("\n")


def unfence(t):
    """답 전체가 코드 울타리에 싸여 오면 벗긴다."""
    m = re.fullmatch(r"\s*```[a-z]*\n(.*?)\n```\s*", t, re.S)
    return m.group(1) if m else t


def shim(work, diagnosis=None):
    cmd = [sys.executable, "-X", "utf8", str(IMN / "scripts/prepare_monolith_input.py"),
           "--run-dir", str(work), "--genre", "report"]
    if diagnosis:
        cmd += ["--diagnosis", str(diagnosis)]
    subprocess.run(cmd, check=True, capture_output=True)
    return (work / "01_input_with_metrics.txt").read_text(encoding="utf-8")


def ask(system, blocks, timeout=900):
    t0 = time.time()
    r = call_messages(model="opus", system=system, user=blocks, max_tokens=32000,
                      timeout=timeout, billing="subscription")
    return r["text"], round(time.time() - t0), r.get("cost_usd"), r.get("billing")


def imnotai(work):
    log = {}
    combined = shim(work)
    text, sec, cost, bill = ask(agent_body("humanize-diagnostician"), [
        "## diagnosis-rules.md\n\n" + (REFS / "diagnosis-rules.md").read_text(encoding="utf-8"),
        "## 01_input_with_metrics.txt\n\n" + combined
        + "\n\n---\n도구는 없다. 02_diagnosis.md 에 쓸 내용만 마크다운으로 출력하라."])
    (work / "02_diagnosis.md").write_text(unfence(text), encoding="utf-8")
    log["diagnose"] = {"sec": sec, "cost_usd": cost, "billing": bill}
    combined = shim(work, work / "02_diagnosis.md")
    text, sec, cost, bill = ask(agent_body("humanize-monolith"), [
        "## quick-rules.md\n\n" + (REFS / "quick-rules.md").read_text(encoding="utf-8"),
        "## 01_input_with_metrics.txt\n\n" + combined
        + "\n\n---\n도구는 없다. final.md 에 쓸 내용 전체(윤문본 본문과 끝의 HUMANIZE-SUMMARY 주석 블록)만 출력하라."])
    final = unfence(text)
    (work / "final.md").write_text(final, encoding="utf-8")
    log["rewrite"] = {"sec": sec, "cost_usd": cost, "billing": bill}
    return re.sub(r"\n*<!-- HUMANIZE-SUMMARY.*", "", final, flags=re.S), log


def ours(path, work):
    err, warn, _ = chk.scan_md(str(path))
    l1 = {}
    for kind, msg in err + warn:
        m = re.match(r"(\d+)행", msg)
        if m:
            l1.setdefault(int(m.group(1)), []).append(kind)
    out = work / "judge.json"
    p = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "scripts/judge_layer2.py"), str(path),
                        "--backend", "claude", "--json", str(out)], capture_output=True, text=True,
                       encoding="utf-8", timeout=1800)
    (work / "judge.log").write_text(p.stdout + p.stderr, encoding="utf-8")
    l2 = {}

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("line"), int) and (x.get("phrase") or x.get("category")):
                l2.setdefault(x["line"], []).append(x.get("category") or "?")
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    if out.exists():
        walk(json.loads(out.read_text(encoding="utf-8")))
    return l1, l2, p.returncode


def changed(before, after):
    """원문 줄 번호(1부터)와 바뀐 뒤 글 — 같은 줄로 짝이 안 맞으면 묶음째 붙인다."""
    a, b = before.splitlines(), after.splitlines()
    sm = difflib.SequenceMatcher(None, [x.strip() for x in a], [x.strip() for x in b], autojunk=False)
    rows = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("equal", "insert"):
            continue
        new = b[j1:j2]
        for k, i in enumerate(range(i1, i2)):
            if not HANGUL.search(a[i]):
                continue
            if op == "replace" and i2 - i1 == j2 - j1:
                rows.append((i + 1, a[i], new[k]))
            else:
                rows.append((i + 1, a[i], "\n".join(new) if k == 0 else "(위 묶음에 합쳐짐)"))
    return rows


def main():
    args = sys.argv[1:]
    out = HERE / "summary.json"
    if "--summary" in args:
        i = args.index("--summary")
        out = Path(args[i + 1])
        del args[i:i + 2]
    work_root = Path(args[0])
    names = args[1:] or DOCS
    summary = {}
    for name in names:
        src = Path(name) if Path(name).is_file() else SRC / f"{name}.md"
        name = src.stem
        work = work_root / name
        work.mkdir(parents=True, exist_ok=True)
        body = strip_front(src.read_text(encoding="utf-8"))
        (work / "01_input.txt").write_text(body, encoding="utf-8")
        doc = work / f"{name}.md"
        doc.write_text(body, encoding="utf-8")
        print(f"[{time.strftime('%H:%M:%S')}] {name} — im-not-ai", flush=True)
        after, log = imnotai(work)
        print(f"[{time.strftime('%H:%M:%S')}] {name} — 이 저장소 판정", flush=True)
        l1, l2, rc = ours(doc, work)
        rows = changed(body, after)
        miss = [r for r in rows if r[0] not in l1 and r[0] not in l2]
        (work / "miss.json").write_text(json.dumps(
            [{"line": n, "before": x, "after": y} for n, x, y in miss], ensure_ascii=False, indent=1), encoding="utf-8")
        summary[name] = {"hangul": len(HANGUL.findall(body)), "change_rate": round(mv2.change_rate(body, after), 3),
                         "changed_lines": len(rows), "l1_lines": len(l1), "l2_lines": len(l2), "judge_rc": rc,
                         "changed_and_l1_or_l2": len(rows) - len(miss), "miss_candidates": len(miss), **log}
        print(json.dumps(summary[name], ensure_ascii=False), flush=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
