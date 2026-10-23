"""python -X utf8 runs/rule-candidates-triage-20261023/pair_gap.py

대장의 사용자 지적 가운데 「낱말은 다 흔한데 짝이 이상한 것」이 얼마나 되고 지금 누가 맡나."""
import collections
import json
from pathlib import Path

from kiwipiepy import Kiwi

REPO = Path("P:/github/korean-writing-qa")
freq = json.loads((REPO / "data/catalog/work-korean-freq.json").read_text(encoding="utf-8"))["freq"]
rows = [json.loads(l) for l in (REPO / "data/cases/flagged-rounds.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
kiwi = Kiwi()
KEEP = {"NNG", "VV", "VA", "MAG", "XR"}
by = collections.Counter()
common_pairs = collections.defaultdict(list)
for r in rows:
    toks = [f"{t.form}/{t.tag.split('-')[0]}" for t in kiwi.tokenize(r["text"]) if t.tag.split("-")[0] in KEEP]
    if not toks:
        kind = "내용어 없음"
    elif any(freq.get(t, 0) <= 40 for t in toks):
        kind = "드문 낱말 포함"
    elif len(toks) >= 2:
        kind = "흔한 낱말끼리 짝"
        common_pairs[r["owner"]].append(f"{r['flag_id']} {r['text']} ({' '.join(toks)})")
    else:
        kind = "흔한 낱말 하나"
    by[(kind, r["owner"])] += 1
print(f"대장 {len(rows)}건")
for (k, o), n in sorted(by.items()):
    print(f"  {k:<12} 주인 {o:<6} {n}")
for o, xs in common_pairs.items():
    print(f"\n## 흔한 낱말끼리 짝 — 주인 {o} ({len(xs)})")
    for x in xs[:40]:
        print("   ", x)
