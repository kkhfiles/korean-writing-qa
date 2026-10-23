"""재판정 좁히기 진단 — 수정안을 넣은 줄 중 첫 재판정이 다시 짚은 줄을, 결정적 표지 대조가 미리 가려내는가.

모델 호출 없음. 2026-10-21 「재판정 생략」 진단과 같은 실행 18회를 다시 읽는다.
"""
import collections
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path.home() / ".claude" / "state" / "korean-bench"
SETS = ["session-batch-1019b", "session-batch-compact-1019", "session-batch-compact2-1020",
        "session-batch-fixed-1020", "session-batch-sysreuse-1020"]
s = importlib.util.spec_from_file_location("cm", "P:/github/korean-writing-qa/skills/finalize-korean-document/scripts/check_meaning.py")
cm = importlib.util.module_from_spec(s); s.loader.exec_module(cm)
s = importlib.util.spec_from_file_location("bl", "P:/github/korean-writing-qa/scripts/bench_loop.py")
sys.argv = ["x"]
bl = importlib.util.module_from_spec(s); s.loader.exec_module(bl)
s = importlib.util.spec_from_file_location("c", "P:/github/korean-writing-qa/assets/doc-style-check.py")
chk = importlib.util.module_from_spec(s); s.loader.exec_module(chk)

MEANING = {"고치다 뜻이 바뀐 곳", "고치다 논리를 깬 곳"}


def findings(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for block in d if isinstance(d, list) else [d]:
        out += block.get("findings", [])
    return out


tot = collections.Counter()
examples = []
for name in SETS:
    for run in sorted((ROOT / name).glob("2026*")):
        start, r0, r1 = run / "start.md", run / "round0.json", run / "round1.json"
        if not (start.exists() and r0.exists() and r1.exists()):
            continue
        lines = start.read_text(encoding="utf-8").splitlines()
        after = list(lines)
        applied = set()
        for f in findings(r0):
            n, ph, fx = f.get("line"), str(f.get("phrase") or ""), str(f.get("fix") or "")
            if f.get("decide") != "fix" or not isinstance(n, int) or not (0 < n <= len(after)):
                continue
            if not ph or not fx or fx.startswith("(") or "\n" in fx or "○○" in fx or ph not in after[n - 1]:
                continue
            after[n - 1] = bl.apply_fix(after[n - 1], ph, fx)
            applied.add(n)
        re_flag = collections.defaultdict(set)
        for f in findings(r1):
            if isinstance(f.get("line"), int):
                re_flag[f["line"]].add(str(f.get("category") or ""))
        tot["실행"] += 1
        for n in applied:
            before, new = lines[n - 1], after[n - 1]
            sig_marker = bool(cm.marker_sentences(before, new)) or bool(cm.marker_drops(before, new))
            e0, w0, _ = 0, 0, 0
            flagged = n in re_flag
            meaning = bool(re_flag.get(n, set()) & MEANING)
            tot["넣은 줄"] += 1
            tot["표지 신호"] += sig_marker
            if flagged:
                tot["다시 짚힘"] += 1
                tot["다시 짚힘·표지 신호"] += sig_marker
            if meaning:
                tot["뜻·논리"] += 1
                tot["뜻·논리·표지 신호"] += sig_marker
                if not sig_marker and len(examples) < 12:
                    examples.append((before[:70], new[:70], sorted(re_flag[n])))
print(dict(tot))
print(f"표지 신호가 뜬 줄 비율(재판정 남김) {tot['표지 신호'] / tot['넣은 줄']:.1%}")
print(f"다시 짚힌 줄 중 표지가 잡은 비율 {tot['다시 짚힘·표지 신호'] / max(1, tot['다시 짚힘']):.1%}")
print(f"뜻·논리 지적 줄 중 표지가 잡은 비율 {tot['뜻·논리·표지 신호'] / max(1, tot['뜻·논리']):.1%}")
print("표지가 못 잡은 뜻·논리 예:")
for b, a, c in examples:
    print("  -", b, "\n    →", a, c)
