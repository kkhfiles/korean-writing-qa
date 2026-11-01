"""검토 화면 시안 — 초안 한 편에 1층과 2층 지적을 표시해, 수정 제안을 diff 로 보고 고르는 HTML 을 만든다(버리는 시안).

입력은 외부 비교 측정(`runs/bench-external-20261031`)이 저장소 밖에 남긴 D3 초안과 2층 판정 기록이다.
출력도 저장소 밖에 둔다. 한글 서체는 만든 뒤 `~/.claude/assets/fonts/inline-korean-font.py` 로 심는다.

    python -X utf8 runs/review-screen-proto-20261101/make_proto.py
    python -X utf8 runs/review-screen-proto-20261101/click_test.py     # 버튼 동작 확인(Playwright)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

B = Path.home() / ".local/share/korean-writing-qa/bench-external"
OUT = B / "review-proto/review-proto.html"
DOC = 6
CHECKER = str(Path(__file__).resolve().parents[2] / "assets" / "doc-style-check.py")
L1_LINE = re.compile(r"^\s*(❌|⚠️)\s+\[(.+?)\]\s+(\d+)행\s+(.*)$")
STYLE_KINDS = {"서술형 종결", "반말 서술형", "서술형 문단"}

draft = json.loads((B / f"e2e/drafts/{DOC:02d}.json").read_text(encoding="utf-8"))
lines = draft["text"].split("\n")
items = []

rows = [json.loads(l) for l in (B / f"e2e/work/{DOC:02d}/r0-l2/judge.jsonl").open(encoding="utf-8")]
for kind in ("fixes", "asks"):
    for f in [f for r in rows for f in (r.get(kind) or [])]:
        info = bool((f.get("check") or "").strip()) or kind == "asks"
        items.append({"layer": "2층", "line": f["line"], "phrase": f.get("phrase") or "", "fix": f.get("fix") or "",
                      "cat": f.get("category") or "", "type": "info" if info else "replace",
                      "why": f.get("why") or "", "check": f.get("check") or ""})

env = dict(__import__("os").environ, KOREAN_QA_PERSONAL_RULES="off")
out = subprocess.run([sys.executable, "-X", "utf8", CHECKER, "--no-rules",
                      str(B / f"e2e/work/{DOC:02d}/r0-l1/doc.md")], capture_output=True, text=True,
                     encoding="utf-8", env=env).stdout
for raw in out.splitlines():
    m = L1_LINE.match(raw)
    if not m or m.group(2) in ("스캔 가치 없는 라벨",):
        continue
    kind, body = m.group(2), m.group(4)
    q = re.search(r"「(.+?)」", body)
    n = int(m.group(3))
    phrase = q.group(1) if q else lines[n - 1].lstrip("-*# ").split(" — ")[0]
    if phrase not in lines[n - 1]:
        phrase = lines[n - 1].strip().lstrip("-* ")
    else:       # 검사기 인용이 어절 중간에서 잘리면(「경에서의」) 어절 전체로 넓힘
        line, i = lines[n - 1], lines[n - 1].index(phrase)
        a, b = i, i + len(phrase)
        while a > 0 and not line[a - 1].isspace():
            a -= 1
        while b < len(line) and not line[b].isspace():
            b += 1
        phrase = line[a:b]
    items.append({"layer": "1층", "line": n, "phrase": phrase, "fix": "",
                  "cat": kind, "type": "style" if kind in STYLE_KINDS else "replace",
                  "why": body.split(" — ", 1)[1] if " — " in body else "", "check": ""})

items.sort(key=lambda x: (x["line"], {"replace": 0, "info": 1, "style": 2}[x["type"]]))
for i, x in enumerate(items, 1):
    x["id"] = i

data = json.dumps({"title": draft["topic"], "lines": lines, "items": items}, ensure_ascii=False)
html = (Path(__file__).parent / "template.html").read_text(encoding="utf-8").replace("/*DATA*/null", data)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print(OUT, len(items), "지적", {t: sum(x["type"] == t for x in items) for t in ("replace", "info", "style")})
