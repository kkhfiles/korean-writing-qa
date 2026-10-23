#!/usr/bin/env python
"""im-not-ai 의 분류표와 후보 파일이 기록본과 달라졌는지 본다 — 주 1회 하루 점검 훅이 부른다.

    python -X utf8 scripts/check_imnotai_upstream.py            # 비교 — 같으면 0, 다르면 1, 못 받으면 3
    python -X utf8 scripts/check_imnotai_upstream.py --update   # 지금 판으로 기록본을 새로 씀
    python -X utf8 scripts/check_imnotai_upstream.py --local <저장소 경로>   # 내려받지 않고 로컬 사본을 읽음

**왜 있나.** 2026-10-23 에 im-not-ai 2.3.2 의 분류 85개를 대조해 넣었는데, 그 저장소는 계속
바뀐다(1.5.0 에서 2.3.2 까지 넉 달 동안 패턴이 40여 개에서 85개로 늘었다). 아무도 다시 안 보면
새 패턴은 그 순간부터 미탐이다.

**무엇을 비교하나** — 패턴 번호, 이름, 고치는 조건 줄(`quick_pattern`), 후보 번호와 상태.
예문과 처방 문구만 바뀐 것은 세지 않는다 — 그것까지 세면 매주 알림이 와서 아무도 안 본다.

**기록본을 갱신하면** `tests/test_imnotai_coverage.py` 가 대조표(`docs/imnotai-coverage-20261023.md`)에
새 번호의 행을 요구한다. 대조 없이 기록본만 올리는 길을 막는 장치다.

과금 호출 없음 — 공개 저장소의 원문 파일 둘을 받는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = REPO / "data" / "catalog" / "imnotai-snapshot.json"
RAW = "https://raw.githubusercontent.com/epoko77-ai/im-not-ai/main/"
FILES = {
    "taxonomy": "skills/humanize-korean/references/ai-tell-taxonomy.md",
    "candidates": "skills/humanize-korean/references/taxonomy-candidates.md",
    "marketplace": ".claude-plugin/marketplace.json",
}
TIMEOUT = 15

HEAD = re.compile(r"^###\s+([A-J]-\d+)\.\s*(.*)$")
QUICK = re.compile(r"quick_pattern:\s*(.*?)(?:\s·\squick_fix|_\s*$|$)")
CAND_ROW = re.compile(r"^\|\s*([A-Z][A-Za-z0-9/\-]*)\s*\|\s*(.*?)\s*\|.*?\|\s*([a-z]+)\s*\|")


def digest(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]


def parse_taxonomy(text: str) -> dict:
    out, cur = {}, None
    for line in text.splitlines():
        m = HEAD.match(line)
        if m:
            cur = m.group(1)
            # 제목 끝의 버전 꼬리표(「· v2.6 신규」)는 판정과 무관하게 바뀌므로 뗀다
            title = re.split(r"\s·\sv\d", m.group(2))[0].strip()
            out[cur] = {"title": title, "quick": ""}
            continue
        if cur and "quick_pattern" in line:
            q = QUICK.search(line)
            out[cur]["quick"] = digest(q.group(1)) if q else ""
    return out


def parse_candidates(text: str) -> dict:
    out, inside = {}, False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.startswith("## 후보 목록")
            continue
        m = CAND_ROW.match(line) if inside else None
        if m and m.group(1) not in ("임시ID",):
            out[m.group(1)] = {"pattern": digest(m.group(2)), "status": m.group(3)}
    return out


def fetch(local: Path | None) -> dict:
    texts = {}
    for key, rel in FILES.items():
        if local:
            texts[key] = (local / rel).read_text(encoding="utf-8")
        else:
            with urllib.request.urlopen(RAW + rel, timeout=TIMEOUT) as r:  # noqa: S310 — 고정 주소
                texts[key] = r.read().decode("utf-8")
    version = json.loads(texts["marketplace"]).get("metadata", {}).get("version", "")
    return {"version": version, "taxonomy": parse_taxonomy(texts["taxonomy"]),
            "candidates": parse_candidates(texts["candidates"])}


def diff(old: dict, new: dict) -> list[str]:
    lines = []
    if old.get("version") != new.get("version"):
        lines.append(f"판 {old.get('version')} → {new.get('version')}")
    for part, name in (("taxonomy", "패턴"), ("candidates", "후보")):
        a, b = old.get(part, {}), new.get(part, {})
        added = sorted(set(b) - set(a))
        gone = sorted(set(a) - set(b))
        changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
        if added:
            lines.append(f"새 {name} " + ", ".join(f"{k}({b[k].get('title', b[k].get('status', ''))})" for k in added))
        if gone:
            lines.append(f"없어진 {name} " + ", ".join(gone))
        if changed:
            lines.append(f"바뀐 {name} " + ", ".join(changed))
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--local", type=Path)
    a = ap.parse_args()
    try:
        new = fetch(a.local)
    except Exception as e:  # noqa: BLE001 — 받지 못한 것은 판단 불가로만 알린다
        print(f"판단 불가 — im-not-ai 원문을 못 받음: {type(e).__name__}")
        return 3
    if a.update:
        new["checked"] = date.today().isoformat()
        SNAPSHOT.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"기록본 갱신 — 판 {new['version']} · 패턴 {len(new['taxonomy'])} · 후보 {len(new['candidates'])}")
        return 0
    try:
        old = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("판단 불가 — 기록본이 없음(--update 로 만든다)")
        return 3
    changes = diff(old, new)
    if not changes:
        return 0
    print("im-not-ai 분류가 기록본과 다름 — " + " · ".join(changes))
    print("대조표(docs/imnotai-coverage-20261023.md)에 반영한 뒤 `python -X utf8 scripts/check_imnotai_upstream.py --update`")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
