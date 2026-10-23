"""python -X utf8 runs/rule-candidates-triage-20261023/two_names.py

같은 괄호 원어에 다른 한국어 이름을 붙인 문서, 「~하는 것입니다」 홑쓰임을 센다 — 표본은 화면만."""
import collections
import re
import sys
from pathlib import Path

sys.argv = ["probe.py", "0", "ZZZ"]
import importlib.util
s = importlib.util.spec_from_file_location("p", str(Path(__file__).parents[1] / "corruption-recall-20261023" / "probe.py"))
p = importlib.util.module_from_spec(s); s.loader.exec_module(p)

# 한국어 이름(한두 어절) + 괄호 원어
GLOSS = re.compile(r'((?:[가-힣]+\s)?[가-힣]+)\s?\(([A-Za-z][A-Za-z0-9 .\-]{2,40})\)')
ISNOM = re.compile(r'[가-힣]+(?:하|되)는\s?것(?:입니다|이다)(?=[.\s]|$)')
for name, docs in (("사람", p.human()), ("AI", p.ai()), ("저장소", [f.read_text(encoding="utf-8") for f in Path("P:/github/korean-writing-qa/docs").rglob("*.md") if "archived" not in f.parts])):
    flagged, samples = 0, []
    nom_docs = nom_hits = 0
    big = [d for d in docs if len(p.HANGUL.findall(d)) >= 300]
    for d in big:
        names = collections.defaultdict(set)
        for m in GLOSS.finditer(d):
            names[m.group(2).strip().lower()].add(m.group(1).split()[-1])
        multi = {k: v for k, v in names.items() if len(v) > 1}
        if multi:
            flagged += 1
            samples += [f"{k}: {' / '.join(sorted(v))}" for k, v in list(multi.items())[:2]]
        n = len(ISNOM.findall(d))
        nom_hits += n; nom_docs += n > 0
    print(f"## {name} {len(big)}편 — 같은 원어 다른 이름 {flagged}편 · 「~하는 것입니다」 {nom_hits}건 {nom_docs}편")
    for x in samples[:12]:
        print("    ", x)
