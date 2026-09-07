#!/usr/bin/env python
"""이슈로 들어온 사례를 회귀 시료로 박는다.

    python scripts/add_case.py --text "고칠 것은 코멘트로" --expect finding \\
        --kind "절단형 종결" --why "조사로 끝나 미완성으로 읽힘" --source "#12"

    python scripts/add_case.py --text "「국회 회기」" --expect clean \\
        --why "회의체가 여는 기간이라 정당" --source "#15"

    python scripts/add_case.py --list          # 들어온 사례와 상태
    python scripts/add_case.py --recheck       # 상태가 실제와 맞는지 다시 재고 고침

**왜 스크립트인가.** 사례가 이슈 본문에만 있으면 규칙을 고칠 때 아무도 그것을 다시
돌려 보지 않는다. 시료로 박아 두면 `tests/test_contributed_cases.py` 가 매번 돌린다.

**상태 둘.**

| 상태 | 뜻 | 시험 처리 |
|---|---|---|
| `open` | 접수했고 아직 규칙이 없음 | 실패가 예정된 것으로 처리 · 통과하면 오히려 알림 |
| `pinned` | 규칙이 들어가 실제로 잡힘 | 깨지면 실패 |

`open` 인 사례가 통과하기 시작하면 시험이 **예정에 없던 통과**로 알린다. 그때
`--recheck` 로 `pinned` 으로 올린다. 이 장치가 없으면 규칙이 들어간 뒤에도 사례가
`open` 인 채로 남아, 나중에 규칙이 되돌아가도 아무도 모른다.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows 기본 인코딩(CP949)으로 나가면 한글이 깨진다. 검사기와 같은 처리를 한다.
sys.stdout.reconfigure(encoding='utf-8')

import repo_paths  # noqa: E402

CASES = repo_paths.REPO / "data" / "cases" / "contributed.jsonl"
EXPECTS = ("finding", "clean")


def load() -> list[dict]:
    if not CASES.is_file():
        return []
    return [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]


def save(records: list[dict]) -> None:
    CASES.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records)
    CASES.write_text(body + "\n", encoding="utf-8")


def scan(text: str, form: str = "structured") -> tuple[list[str], list[str]]:
    """사례 한 줄을 값 슬롯에 넣고 검사기를 돌린다. (오류 갈래, 주의 갈래)"""
    doc = (f"---\nform: {form}\n---\n\n# 사례\n\n**검사 대상** — 한 줄 표본\n\n- {text}\n")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "case.md"
        path.write_text(doc, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(path), "-v", "--no-rules"],
            capture_output=True, text=True, encoding="utf-8",
        )
    err, warn = [], []
    for line in done.stdout.splitlines():
        line = line.strip()
        if line.startswith("❌ [") and "]" in line:
            err.append(line[3:line.index("]")].strip("[ "))
        elif line.startswith("⚠️") and "[" in line:
            warn.append(line[line.index("[") + 1:line.index("]")])
    return err, warn


def verdict(text: str, form: str) -> tuple[str, list[str]]:
    err, warn = scan(text, form)
    kinds = err + warn
    return ("finding" if kinds else "clean"), kinds


def next_id(records: list[dict]) -> str:
    used = [int(r["case_id"][2:]) for r in records if r["case_id"][:2] == "C-"]
    return f"C-{max(used, default=0) + 1:03d}"


def add(args) -> int:
    records = load()
    text = args.text.strip()
    if any(r["text"] == text for r in records):
        print(f"이미 들어 있는 사례다: {text}")
        return 1

    got, kinds = verdict(text, args.form)
    status = "pinned" if got == args.expect else "open"

    record = {
        "case_id": next_id(records),
        "text": text,
        "expect": args.expect,
        "kind": args.kind or (kinds[0] if kinds else None),
        "form": args.form,
        "why": args.why,
        "source": args.source,
        "status": status,
    }
    records.append(record)
    save(records)

    print(f"{record['case_id']}  {text}")
    print(f"  바라는 판정 {args.expect} · 지금 판정 {got}"
          + (f" ({' · '.join(kinds)})" if kinds else ""))
    if status == "pinned":
        print("  이미 맞다 — pinned 으로 박았다. 규칙이 되돌아가면 시험이 깨진다.")
    else:
        print("  아직 안 맞다 — open 으로 두었다. 규칙을 고친 뒤 `--recheck` 로 올린다.")
    return 0


def show(_args) -> int:
    records = load()
    if not records:
        print("들어온 사례가 없다.")
        return 0
    for r in records:
        mark = "고정" if r["status"] == "pinned" else "대기"
        print(f"[{mark}] {r['case_id']}  {r['text']}")
        print(f"       바라는 판정 {r['expect']} · 갈래 {r['kind'] or '미정'} · 출처 {r['source']}")
        print(f"       근거 {r['why']}")
    open_n = sum(1 for r in records if r["status"] == "open")
    print(f"\n모두 {len(records)}건 · 규칙 대기 {open_n}건")
    return 0


def recheck(_args) -> int:
    records = load()
    moved = []
    for r in records:
        got, kinds = verdict(r["text"], r.get("form", "structured"))
        want = "pinned" if got == r["expect"] else "open"
        if want != r["status"]:
            moved.append((r["case_id"], r["status"], want, kinds))
            r["status"] = want
            if want == "pinned" and kinds and not r.get("kind"):
                r["kind"] = kinds[0]
    if not moved:
        print(f"{len(records)}건 모두 상태가 실제와 맞는다.")
        return 0
    save(records)
    for case_id, before, after, kinds in moved:
        arrow = "규칙이 들어왔다" if after == "pinned" else "다시 안 잡힌다"
        print(f"{case_id}  {before} → {after}  ({arrow}"
              + (f" · {' · '.join(kinds)}" if kinds else "") + ")")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="이슈로 들어온 사례를 회귀 시료로 박는다")
    ap.add_argument("--text", help="사례 문장 한 줄")
    ap.add_argument("--expect", choices=EXPECTS, help="finding = 잡혀야 함 · clean = 통과해야 함")
    ap.add_argument("--kind", help="갈래 이름 — 비우면 검사기가 낸 것을 쓴다")
    ap.add_argument("--why", default="", help="왜 그렇게 판정해야 하는지")
    ap.add_argument("--source", default="", help="어디서 왔나 — 이슈 번호나 사람")
    ap.add_argument("--form", default="structured", choices=("structured", "prose"))
    ap.add_argument("--list", action="store_true", help="들어온 사례와 상태를 본다")
    ap.add_argument("--recheck", action="store_true", help="상태를 실제와 다시 맞춘다")
    args = ap.parse_args()

    if args.list:
        return show(args)
    if args.recheck:
        return recheck(args)
    if not args.text or not args.expect:
        ap.error("--text 와 --expect 가 함께 있어야 한다")
    if not args.why:
        ap.error("--why 가 없으면 나중에 왜 넣었는지 아무도 모른다")
    return add(args)


if __name__ == "__main__":
    raise SystemExit(main())
