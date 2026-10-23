"""실험 6 산출물(같은 과제를 지시문 조건만 바꿔 쓴 문서)에서 「~가 아니라」 밀도를 조건별로 센다 — 모델 호출 없음."""
import collections
import importlib.util
import re
from pathlib import Path

s = importlib.util.spec_from_file_location("c", "P:/github/korean-writing-qa/assets/doc-style-check.py")
c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
OUT = Path("P:/github/korean-writing-qa/data/raw/exp6-instruction-style/out")
EXP6 = OUT.parent

agg = collections.defaultdict(lambda: [0, 0, 0, 0])   # 건수, 한글, 문서, 2회 이상 문서
per = collections.defaultdict(lambda: [0, 0])
for f in sorted(OUT.glob("doc_T*_C*_*.md")):
    m = re.match(r"doc_(T\d)_(C\d)_\d+\.md", f.name)
    t, cond = m.groups()
    raw = f.read_text(encoding="utf-8")
    body = "\n".join(c.mask(l) for l in raw.splitlines() if not c.is_example(l.strip()))
    n = len(c.NOT_BUT.findall(body)); h = len(re.findall(r"[가-힣]", body))
    a = agg[cond]; a[0] += n; a[1] += h; a[2] += 1; a[3] += n >= 2
    per[(t, cond)][0] += n; per[(t, cond)][1] += h
print("조건별 — 건수 / 한글 / 1만 자당 / 문서 / 2회 이상 문서")
for cond in sorted(agg):
    n, h, d, two = agg[cond]
    print(f"  {cond}: {n:>3} / {h:>7,} / {n / h * 1e4:5.2f} / {d:>2}편 / {two}편")
print("과제별 1만 자당")
for t in sorted({k[0] for k in per}):
    print("  ", t, "  ".join(f"{cond} {per[(t, cond)][0] / max(1, per[(t, cond)][1]) * 1e4:5.2f}"
                            for cond in sorted(agg) if (t, cond) in per))
for cond in ("C1", "C2", "C3", "C4"):
    p = EXP6 / f"{cond}.md"
    if p.exists():
        t = p.read_text(encoding="utf-8")
        body = "\n".join(c.mask(l) for l in t.splitlines() if not c.is_example(l.strip()))
        n = len(c.NOT_BUT.findall(body)); h = len(re.findall(r"[가-힣]", body))
        print(f"지시문 {cond}: 본문 대구 {n}회 · 1만 자당 {n / max(1, h) * 1e4:.1f}")
