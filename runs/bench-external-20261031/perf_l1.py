"""1층 검사기와 로컬 교정 도구의 처리 속도 — 공개 정책뉴스 40편을 한 번에 넣어 한글 1천 자당 초를 잰다.

    python -X utf8 runs/bench-external-20261031/perf_l1.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, hangul  # noqa: E402
import systems  # noqa: E402

docs = [json.loads(l) for l in (DATA / "public/docs.jsonl").open(encoding="utf-8")]
folder = DATA / "perf"
folder.mkdir(parents=True, exist_ok=True)
for d in docs:
    (folder / f"{d['id']}.md").write_text("---\nform: prose\n---\n\n" + d["text"] + "\n", encoding="utf-8")
chars = sum(hangul(d["text"]) for d in docs)
out = {"문서": len(docs), "한글 글자": chars}

for rep in range(3):        # 첫 회는 파이썬 시작과 사전 읽기가 섞임
    t = time.time()
    subprocess.run([sys.executable, "-X", "utf8", str(systems.CHECKER), "--no-rules", str(folder)],
                   capture_output=True, text=True, encoding="utf-8")
    out[f"l1 {rep + 1}회 초"] = round(time.time() - t, 2)

t = time.time()
for d in docs:
    systems.run_kiwi(d["text"].split("\n"))
out["kiwi-space 초(모형 읽기 포함)"] = round(time.time() - t, 2)

for k in [k for k in out if k.endswith("초") or "초(" in k]:
    out[k.replace("초", "초/1천 자", 1) if k.endswith("초") else k + " /1천 자"] = round(out[k] / (chars / 1000), 3)
print(json.dumps(out, ensure_ascii=False, indent=1))
(DATA / "perf.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
