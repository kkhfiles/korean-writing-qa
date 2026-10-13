"""시험 도우미 — 판정기가 문서의 지금 줄을 다 본 것처럼 시험용 판정 기록에 적는다.

(2026-10-13) 발행 게이트가 판정기가 안 본 한글 줄을 막게 되면서, 구조 · 검토 기록을 재는 발행 시험이
그 차단에 먼저 걸렸다. 그 시험들이 원래 재려던 것만 재도록 문서를 「판정을 받은 문서」로 만든다.
게이트는 `KOREAN_QA_JUDGE_LOG` 로 이 기록을 읽는다 — 시험 환경에 같은 경로를 넣는다.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import layer2_coverage as coverage  # noqa: E402


def mark(log: str | Path, doc: str | Path) -> None:
    doc = Path(doc)
    lines = coverage.read_doc(doc).splitlines()
    row = {"ok": True, "when": time.time(), "key": coverage.doc_key(doc), "seen": coverage.seen_keys(lines)}
    with Path(log).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
