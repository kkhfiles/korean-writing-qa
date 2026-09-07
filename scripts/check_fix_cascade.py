"""우리가 처방한 수정문이 새 지적을 만드는지 잰다.

**왜 필요한가.** 규칙에 따라 A를 고치면 B가 생길 수 있다. 실제로 그렇다 —
개조식으로 줄이다 서술어를 날려 절단형이 되고, 영어를 한국어로 바꾸다 뜻이
달라진다. 이번 사용자 판정에서 오탐·보류 넷 가운데 셋이 그 형태였다.

**무엇을 재나.** 수정 전과 수정 후를 같은 골격에 넣고 두 검사기를 돌려,
**수정 후에만 나오는 지적**을 센다. 그것이 우리 처방이 만든 새 문제다.

**한계.** 문장 하나를 골격에 끼워 재므로 앞뒤 문맥이 필요한 지적은 못 본다.
여기서 잡히는 것은 문장 안에서 닫히는 결함뿐이다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import skill_bridge                                    # noqa: E402

import repo_paths

GLOBAL_CHECKER = repo_paths.CHECKER
# 진입점·제목이 없으면 검사기가 뼈대를 지적해 본문 판정을 가린다. 본문은 늘 7행이다.
SKELETON = "# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n- {line}\n"
BODY_LINE = "7행"


def load_global():
    spec = importlib.util.spec_from_file_location("doc_style_check", GLOBAL_CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pairs() -> list[dict[str, str]]:
    """수정 전후 쌍을 모은다. 출처를 함께 들고 다녀야 어디서 생긴 연쇄인지 알 수 있다."""
    home = skill_bridge.skill_home()
    out: list[dict[str, str]] = []

    def read(path: Path) -> list[dict]:
        if not path.is_file():
            return []
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    for row in read(home / "references" / "confirmed-rules.jsonl"):
        out.append({"source": "확정 규칙", "id": row.get("rule_id", ""),
                    "before": row["original"], "after": row.get("revised", "")})
    for row in read(home / "references" / "context-cases.jsonl"):
        out.append({"source": "문맥 시료", "id": row.get("case_id", ""),
                    "before": row["original"], "after": row.get("revised", "")})
    # 2층 지적은 원문 줄을 알고 있다. 문구만 떼어 재면 문장이 아니라는 이유로
    # 절단형이 잡혀 없는 연쇄가 생긴다 — 실측 1건이 그렇게 나왔다.
    source_dir = REPO_ROOT / "data" / "raw" / "diagnostic-002"
    for row in read(REPO_ROOT / "runs" / "eval-003" / "llm-findings.jsonl"):
        document = source_dir / f"{row['document_id']}.md"
        before = after = None
        if document.is_file():
            lines = document.read_text(encoding="utf-8").splitlines()
            index = int(row["line_number"]) - 1
            if 0 <= index < len(lines) and row["original"] in lines[index]:
                before = lines[index]
                after = lines[index].replace(row["original"], row.get("revised", ""))
        out.append({
            "source": "2층 지적",
            "id": f"{row['document_id']}:{row['line_number']}",
            "before": before if before is not None else row["original"],
            "after": after if after is not None else row.get("revised", ""),
            "whole_line": before is not None,
        })
    return [p for p in out if p["after"] and p["after"] != "삭제"]


def kinds(check, rules, global_checker, line: str) -> Counter:
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "doc.md"
        target.write_text(SKELETON.format(line=line), encoding="utf-8")
        found = Counter()
        for finding in check.scan_files(
            [target], rules, "general_it_business", False, "general"
        )["findings"]:
            found[f"스킬/{finding.get('rule_id')}"] += 1
        errors, warnings, _ = global_checker.scan_md(str(target))
        for kind, message in (*errors, *warnings):
            if message.startswith(BODY_LINE):
                found[kind] += 1
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    check = skill_bridge.load("check")
    rules = check.load_rules()
    global_checker = load_global()

    rows, introduced = [], Counter()
    for pair in pairs():
        before = kinds(check, rules, global_checker, pair["before"])
        after = kinds(check, rules, global_checker, pair["after"])
        new = after - before
        fixed = before - after
        if new:
            introduced.update(new)
        rows.append({**pair, "new": dict(new), "fixed": dict(fixed)})

    cascaded = [r for r in rows if r["new"]]
    whole = sum(1 for r in rows if r.get("whole_line"))
    print(f"수정 전후 쌍 {len(rows)}건 (원문 줄에 넣어 잰 것 {whole}건 · 문구만 잰 것 "
          f"{len(rows) - whole}건) · 새 지적을 만든 쌍 {len(cascaded)}건 "
          f"({len(cascaded) / len(rows) * 100:.1f}%)")
    print()
    if introduced:
        print("우리 처방이 새로 만든 지적")
        for kind, count in introduced.most_common():
            print(f"   {kind:<22} {count}")
        print()
    for row in cascaded:
        print(f"[{row['source']} {row['id']}] {', '.join(row['new'])}")
        print(f"   전: {row['before'][:64]}")
        print(f"   후: {row['after'][:64]}")

    if args.out:
        args.out.write_text(
            json.dumps({"pairs": len(rows), "cascaded": len(cascaded),
                        "introduced": dict(introduced), "rows": rows},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
