"""사례집 §01·§04·§05 의 수치를 한 번에 잰다 — 페이지의 모든 비중이 이 실행에서 나온다.

**왜 비중인가.** 원수는 읽는 사람이 쓸 수가 없다(뭉치 크기 감이 없다). 그리고
스스로 낡는다 — 「규칙·기록」 뭉치는 `~/.claude` 라 세션 산출물이 쌓이고 지워져
규칙을 안 고쳐도 크기가 움직인다. 비중은 그 흔들림을 크게 줄인다.

**범위** — `.md` + `.html` · 기계가 만든 임시물(세션 기록·백업·파일 이력·캐시)과
실행 기록·원자료는 뺀다. 백업은 같은 글을 두 번 센다.
"""

import collections
import importlib.util
import json
import pathlib
import re
import time

CHECKER = pathlib.Path("P:/github/korean-writing-qa/assets/doc-style-check.py")
spec = importlib.util.spec_from_file_location("dsc", CHECKER)
dsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dsc)

SKIP = {".git", "node_modules", "__pycache__", ".venv", "projects", "todos",
        "shell-snapshots", "backups", "file-history", "cache", "statsig", "runs", "data"}
CORPORA = {
    "보고서": [pathlib.Path("P:/github/claude-workflow/reports")],
    "규칙·기록": [pathlib.Path("C:/Users/kkhfiles/.claude"),
                pathlib.Path("P:/github/korean-writing-qa")],
}

out = {}
for name, roots in CORPORA.items():
    files = []
    for root in roots:
        if root.is_dir():
            for pat in ("*.md", "*.html"):
                files += [p for p in root.rglob(pat)
                          if not any(part in SKIP for part in p.parts)]
    files.sort()
    kinds = collections.Counter()
    qlabel = 0
    words = collections.defaultdict(collections.Counter)
    err_docs = any_docs = tot_e = tot_w = 0
    t0 = time.perf_counter()
    for f in files:
        scan = dsc.scan_md if f.suffix == ".md" else dsc.scan_html
        try:
            e, w, _ = scan(str(f), False, None)
        except Exception:                                       # noqa: BLE001
            continue
        tot_e += len(e); tot_w += len(w)
        if e:
            err_docs += 1
        if e or w:
            any_docs += 1
        for item in list(e) + list(w):
            kind = item[1] if len(item) == 3 else item[0]
            msg = item[2] if len(item) == 3 else item[1]
            kinds[kind] += 1
            if kind == "절단형 종결" and "의문문" in msg:
                qlabel += 1
            if kind in ("모호한 지칭", "스캔 가치 없는 라벨"):
                m = re.search(r"「([^」]{1,12})」", msg)
                if m:
                    words[kind][m.group(1)] += 1
    out[name] = {
        "문서": len(files), "초": round(time.perf_counter() - t0, 1),
        "지적": tot_e + tot_w, "오류": tot_e, "주의": tot_w,
        "오류 문서": err_docs, "지적 문서": any_docs,
        "오류 문서 비율": round(err_docs * 100 / len(files)),
        "지적 문서 비율": round(any_docs * 100 / len(files)),
        "의문문 라벨": qlabel,
        "갈래": dict(kinds),
        "낱말": {k: v.most_common(3) for k, v in words.items()},
    }

pathlib.Path("P:/github/korean-writing-qa/runs/eval-010").mkdir(parents=True, exist_ok=True)
pathlib.Path("P:/github/korean-writing-qa/runs/eval-010/counts.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

for name, d in out.items():
    print(f"{name}: 문서 {d['문서']} · {d['초']}초 · 지적 {d['지적']} "
          f"(오류 {d['오류']} · 주의 {d['주의']}) · 오류 문서 {d['오류 문서 비율']}% "
          f"· 지적 문서 {d['지적 문서 비율']}%")
    print(f"   낱말: {d['낱말']}")
