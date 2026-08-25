#!/usr/bin/env python
"""라벨된 실문서에서 스크립트 층이 얼마나 잡는지를 잰다.

**왜 필요한가.** 지금 회귀시험은 통과와 실패만 낸다. 규칙을 하나 더 넣었을 때
실제로 더 잡게 됐는지, 정상 문장을 더 지적하게 됐는지를 답할 수단이 없다.
점진 개선은 그 수치가 있어야 가능하다.

**무엇을 재나.** 하이브리드 운영 모델의 1층(결정 규칙 스크립트)만 잰다.
2층(LLM 검토)이 얼마나 남았는지가 여기서 나온다.

| 세트 | 출처 | 기대 |
|---|---|---|
| 양성 | `data/annotations/diagnostic-002-review.jsonl` 의 `revise` | 그 줄에서 지적이 나와야 함 |
| 음성(허용) | 같은 파일의 `allow` | 지적이 나오면 안 됨 |
| 음성(실제 경로) | `runs/diagnostic-002/path-term-candidates.jsonl` | 비유로 분류되면 안 됨 |

**라벨 없는 지적은 오탐으로 세지 않는다.** 그 줄에 사람 판정이 없으면 맞는지
틀리는지 알 수 없다. 「판정 불가」로 따로 낸다 — 오탐과 섞으면 수치가 거짓이 된다.

배포된 스킬 검사기를 부른다. 저장소 사본이 아니라 사용자에게 실제로 도는 코드다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_ROOT = Path.home() / ".claude" / "skills" / "finalize-korean-document"
DEFAULT_GLOBAL_CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"
REVIEW_LABELS = REPO_ROOT / "data" / "annotations" / "diagnostic-002-review.jsonl"
PATH_ALLOW = REPO_ROOT / "runs" / "diagnostic-002" / "path-term-candidates.jsonl"
SOURCE_DIR = REPO_ROOT / "data" / "raw" / "diagnostic-002"
LINE_PREFIX = re.compile(r"^(\d+)행")
QUOTED_TERM = re.compile(r"[「『]([^」』]+)[」』]")
OVERLAP_CHARS = 12


def shares_run(left: str, right: str, size: int = OVERLAP_CHARS) -> bool:
    """두 문자열이 size 글자 이상 이어지는 부분을 공유하는지 본다."""
    text = left.strip()
    for start in range(0, max(0, len(text) - size) + 1):
        chunk = text[start:start + size]
        if len(chunk) == size and chunk in right:
            return True
    return False


def concerns_label(message: str, labeled: str, line_text: str) -> str:
    """그 지적이 라벨이 가리키는 표현을 두고 한 말인지 판정한다.

    세 값을 낸다 — `yes`(그 표현을 지적) · `no`(같은 줄의 다른 표현을 지적)
    · `unknown`(지적문에 대상이 안 실려 글로는 판정 불가).

    **왜 세 값인가.** 같은 줄이라는 이유로 잡았다고 세면 다른 문제를 잡은 것이
    정탐이 된다(실측 1건 과대). 반대로 대상이 안 실린 지적을 미탐으로 밀면
    이번엔 과소가 된다(실측 1건). 둘을 「미확인」으로 뭉치면 회수율이 거짓이
    되므로 판정 불가를 따로 세고 회수율은 상한과 하한으로 낸다.
    """
    quoted = QUOTED_TERM.findall(message)
    if quoted:
        return "yes" if any(term in labeled for term in quoted) else "no"
    body = message.split("행", 1)[-1].strip()
    if shares_run(labeled, body):
        return "yes"
    if shares_run(line_text, body):
        return "no"
    return "unknown"


def read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def locate_line(source: Path, needle: str) -> int | None:
    """라벨 원문이 몇 번째 줄에 있는지 찾는다. 못 찾으면 None."""
    lines = source.read_text(encoding="utf-8").splitlines()
    head = needle.splitlines()[0] if needle.splitlines() else needle
    for index, line in enumerate(lines, 1):
        if head and head in line:
            return index
    return None


def skill_findings(skill_check, rules, path: Path, profile: str) -> dict[int, list[tuple[str, str]]]:
    """스킬 검사기의 지적을 줄 번호별로 모은다. 값은 (이름, 지적 대상)."""
    scope = skill_check.PROFILE_SCOPES[profile]
    result = skill_check.scan_files([path], rules, scope, False, profile)
    by_line: dict[int, list[tuple[str, str]]] = {}
    for finding in result["findings"]:
        line_number = finding.get("line_number")
        if line_number is None:
            continue
        name = f"{finding['source']}/{finding.get('rule_id')}"
        by_line.setdefault(int(line_number), []).append(
            (name, f"「{finding.get('original')}」")
        )
    return by_line


def global_findings(global_checker, path: Path) -> tuple[dict[int, list[tuple[str, str]]], bool]:
    """전역 검사기의 지적을 줄 번호별로 모은다. 값 슬롯 인식 여부도 함께 낸다."""
    scan = global_checker.scan_md if path.suffix == ".md" else global_checker.scan_html
    errors, warnings, slots = scan(str(path))
    by_line: dict[int, list[tuple[str, str]]] = {}
    for tier, items in (("오류", errors), ("주의", warnings)):
        for kind, message in items:
            match = LINE_PREFIX.match(message)
            if not match:
                continue
            by_line.setdefault(int(match.group(1)), []).append(
                (f"{tier}/{kind}", message)
            )
    return by_line, bool(slots)


def llm_covers(labeled: str, reported: str) -> bool:
    """2층 지적이 그 라벨을 가리키는지 본다.

    문서만 맞으면 세는 방식으로 하면 **문서마다 아무 지적이나 하나 내면 회수율이
    오르는 계기판**이 된다. 표현이 실제로 겹쳐야 센다.
    """
    if not labeled or not reported:
        return False
    return shares_run(labeled, reported, size=6) or shares_run(reported, labeled, size=6)


def load_llm_findings(path: Path | None) -> dict[str, list[dict[str, object]]]:
    """2층(LLM 검토)이 낸 지적을 문서별로 모은다.

    1층만 재면 이 시스템의 절반만 보는 것이다. 실측으로 규칙 후보 12개 가운데 정밀도가
    쓸 만한 것이 하나도 없었으므로, 남은 회수율은 대부분 2층이 메워야 한다. 그 몫이
    실제로 메워지는지 재려면 2층 결과도 같은 라벨에 대고 세야 한다.

    한 줄에 한 지적. `document_id` 와 `original`(지적한 표현)이 필요하다.
    """
    findings: dict[str, list[dict[str, object]]] = {}
    if path is None:
        return findings
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        findings.setdefault(str(row["document_id"]), []).append(row)
    return findings


def evaluate(
    skill_root: Path,
    global_checker_path: Path,
    profile: str,
    llm_findings_path: Path | None = None,
) -> dict[str, object]:
    sys.path.insert(0, str(skill_root / "scripts"))
    skill_check = load_module("skill_check", skill_root / "scripts" / "check.py")
    global_checker = load_module("global_checker", global_checker_path)
    rules = skill_check.load_rules(skill_root / "references" / "confirmed-rules.jsonl")

    labels = read_jsonl(REVIEW_LABELS)
    llm_findings = load_llm_findings(llm_findings_path)
    documents = sorted({str(row["document_id"]) for row in labels})
    scanned: dict[str, dict[str, object]] = {}
    for document_id in documents:
        source = SOURCE_DIR / f"{document_id}.md"
        if not source.is_file():
            scanned[document_id] = {"available": False}
            continue
        skill_lines = skill_findings(skill_check, rules, source, profile)
        global_lines, slots_found = global_findings(global_checker, source)
        scanned[document_id] = {
            "available": True,
            "source": source,
            "lines": source.read_text(encoding="utf-8").splitlines(),
            "skill": skill_lines,
            "global": global_lines,
            "slots_found": slots_found,
        }

    positives: list[dict[str, object]] = []
    negatives: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    for row in labels:
        document_id = str(row["document_id"])
        state = scanned[document_id]
        if not state.get("available"):
            unresolved.append({
                "annotation_id": row["annotation_id"],
                "reason": "원문 문서 없음 — 조사 안 함",
            })
            continue
        line_number = locate_line(state["source"], str(row["original"]))  # type: ignore[arg-type]
        if line_number is None:
            unresolved.append({
                "annotation_id": row["annotation_id"],
                "reason": "라벨 원문을 원본에서 못 찾음 — 판정 불가",
            })
            continue
        labeled = str(row["original"])
        line_text = state["lines"][line_number - 1]               # type: ignore[index]
        skill_line = state["skill"].get(line_number, [])          # type: ignore[union-attr]
        global_line = state["global"].get(line_number, [])        # type: ignore[union-attr]

        def split(entries):
            verdicts = [(n, concerns_label(m, labeled, line_text)) for n, m in entries]
            return (
                [n for n, v in verdicts if v == "yes"],
                [n for n, v in verdicts if v == "unknown"],
                [n for n, v in verdicts if v == "no"],
            )

        skill_hit, skill_unknown, skill_other = split(skill_line)
        global_hit, global_unknown, global_other = split(global_line)
        undecidable = skill_unknown + global_unknown
        script_hit = bool(skill_hit or global_hit)
        # 2층 지적은 라벨과 표현이 실제로 겹칠 때만 센다. 같은 문서라는 이유로 세면
        # 문서마다 아무 지적이나 하나 내면 회수율이 오르는 계기판이 된다.
        llm_hit = [
            str(row.get("category") or row.get("note") or "LLM")
            for row in llm_findings.get(document_id, [])
            if llm_covers(labeled, str(row.get("original") or ""))
        ]
        caught_by = (
            "둘 다" if skill_hit and global_hit
            else "스킬" if skill_hit
            else "전역" if global_hit
            else "판정 불가" if undecidable
            else "아무도"
        )
        record = {
            "annotation_id": row["annotation_id"],
            "document_id": document_id,
            "line_number": line_number,
            "category": row.get("category"),
            "original": labeled,
            "recorded_detector": row.get("detected_by"),
            "skill": skill_hit,
            "global": global_hit,
            "undecidable_finding": undecidable,
            "same_line_other_finding": skill_other + global_other,
            "caught_by": caught_by,
            "llm": llm_hit,
            "covered_by": (
                "1층" if script_hit and not llm_hit
                else "1층과 2층" if script_hit and llm_hit
                else "2층" if llm_hit
                else "판정 불가" if undecidable
                else "아무도"
            ),
        }
        (positives if row.get("human_label") == "revise" else negatives).append(record)

    labeled_lines = {
        (str(row["document_id"]), record["line_number"])
        for row, record in zip(
            [r for r in labels if r["annotation_id"] in
             {p["annotation_id"] for p in positives} |
             {n["annotation_id"] for n in negatives}],
            positives + negatives,
        )
    }
    unlabeled = 0
    for document_id, state in scanned.items():
        if not state.get("available"):
            continue
        every_line = set(state["skill"]) | set(state["global"])   # type: ignore[arg-type]
        unlabeled += sum(
            1 for line in every_line if (document_id, line) not in labeled_lines
        )

    path_rows = read_jsonl(PATH_ALLOW)
    path_false = [
        row for row in path_rows
        if skill_check.classify_path(
            str(row["context"]),
            *next(
                ((m.start(), m.end()) for m in skill_check.TERM.finditer(str(row["context"]))),
                (0, 0),
            ),
        )[0] == "abstract_candidate"
    ]

    caught = [p for p in positives if p["caught_by"] in ("스킬", "전역", "둘 다")]
    undecided = [p for p in positives if p["caught_by"] == "판정 불가"]
    by_layer: dict[str, int] = {}
    for item in positives:
        by_layer[str(item["caught_by"])] = by_layer.get(str(item["caught_by"]), 0) + 1

    total = len(positives)
    covered = [p for p in positives if p["covered_by"] in ("1층", "2층", "1층과 2층")]
    by_cover: dict[str, int] = {}
    for item in positives:
        by_cover[str(item["covered_by"])] = by_cover.get(str(item["covered_by"]), 0) + 1
    return {
        "profile": profile,
        "skill_root": str(skill_root),
        "llm_findings_supplied": llm_findings_path is not None,
        "hybrid": {
            "by_layer": by_cover,
            "covered": len(covered),
            "combined_recall_floor": round(len(covered) / total, 3) if total else None,
            "note": (
                "2층 결과를 안 넘겼다 — 1층만 잰 값이다"
                if llm_findings_path is None
                else "1층과 2층을 함께 잰 값이다"
            ),
        },
        "positives": {
            "total": total,
            "caught": len(caught),
            "undecidable": len(undecided),
            "recall_floor": round(len(caught) / total, 3) if total else None,
            "recall_ceiling": (
                round((len(caught) + len(undecided)) / total, 3) if total else None
            ),
            "by_layer": by_layer,
            "missed": [p for p in positives if p["caught_by"] == "아무도"],
            "undecided": undecided,
            "items": positives,
        },
        "labeled_negatives": {
            "total": len(negatives),
            "wrongly_flagged": [n for n in negatives if n["caught_by"] != "아무도"],
        },
        "path_allow_negatives": {
            "total": len(path_rows),
            "wrongly_abstract": len(path_false),
        },
        "unlabeled_findings": {
            "count": unlabeled,
            "note": "그 줄에 사람 판정이 없다 — 오탐인지 정탐인지 판정 불가",
        },
        "unresolved_labels": unresolved,
    }


def print_report(result: dict[str, object]) -> None:
    positives = result["positives"]          # type: ignore[index]
    print(f"프로필 {result['profile']} · 배포 스킬 {result['skill_root']}")
    print()
    hybrid = result["hybrid"]                                    # type: ignore[index]
    print("── 하이브리드 전체 (1층 스크립트 + 2층 LLM 검토)")
    print(f"   메운 것 {hybrid['covered']}/{positives['total']} "
          f"· 합산 회수율 하한 {hybrid['combined_recall_floor']}")
    for layer, count in sorted(hybrid["by_layer"].items()):       # type: ignore[union-attr]
        print(f"      {layer:10} {count}건")
    print(f"   {hybrid['note']}")
    print()
    print("── 양성 (사람이 「고쳐야 한다」고 판정한 실문서 지점)")
    print(f"   전체 {positives['total']}건 · 확정 정탐 {positives['caught']}건 "
          f"· 판정 불가 {positives['undecidable']}건")
    print(f"   회수율 하한 {positives['recall_floor']} "
          f"· 상한 {positives['recall_ceiling']}")
    for layer, count in sorted(positives["by_layer"].items()):   # type: ignore[union-attr]
        print(f"      {layer:8} {count}건")
    print()
    print("── 놓친 것 (2층 LLM이 맡아야 하는 몫)")
    for item in positives["missed"]:                             # type: ignore[index]
        other = item.get("same_line_other_finding")
        tail = f"   ← 같은 줄 다른 지적 {other}" if other else ""
        print(f"   [{item['category']}] {str(item['original'])[:52]}{tail}")
    if positives["undecided"]:                                   # type: ignore[index]
        print()
        print("── 판정 불가 (지적문에 대상이 안 실려 글로는 못 가름 · 사람이 봐야 함)")
        for item in positives["undecided"]:                      # type: ignore[index]
            print(f"   [{item['category']}] {str(item['original'])[:44]} "
                  f"← {item['undecidable_finding']}")
    print()
    negatives = result["labeled_negatives"]                      # type: ignore[index]
    path_negatives = result["path_allow_negatives"]              # type: ignore[index]
    print("── 음성 (지적하면 안 되는 것)")
    print(f"   사람이 「허용」 판정한 지점 {negatives['total']}건 중 "
          f"잘못 지적 {len(negatives['wrongly_flagged'])}건")
    print(f"   실제 파일 경로 {path_negatives['total']}건 중 "
          f"비유로 오분류 {path_negatives['wrongly_abstract']}건")
    print()
    unlabeled = result["unlabeled_findings"]                     # type: ignore[index]
    print("── 판정 불가")
    print(f"   라벨 없는 줄의 지적 {unlabeled['count']}건 — {unlabeled['note']}")
    for row in result["unresolved_labels"]:                      # type: ignore[index]
        print(f"   {row['annotation_id']}: {row['reason']}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-root", type=Path, default=DEFAULT_SKILL_ROOT)
    parser.add_argument("--global-checker", type=Path, default=DEFAULT_GLOBAL_CHECKER)
    parser.add_argument("--profile", default="general")
    parser.add_argument(
        "--llm-findings",
        type=Path,
        help="2층(LLM 검토)이 낸 지적 JSONL. 한 줄에 document_id 와 original 이 필요하다.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if not (args.skill_root / "scripts" / "check.py").is_file():
        print(f"eval_failed: 배포 스킬을 찾지 못함 {args.skill_root}", file=sys.stderr)
        return 2
    if not args.global_checker.is_file():
        print(f"eval_failed: 전역 검사기를 찾지 못함 {args.global_checker}", file=sys.stderr)
        return 2

    result = evaluate(
        args.skill_root, args.global_checker, args.profile, args.llm_findings
    )
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print_report(result)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
