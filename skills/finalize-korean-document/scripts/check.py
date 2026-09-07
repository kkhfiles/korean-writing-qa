#!/usr/bin/env python
"""Find user-confirmed awkward Korean and nonliteral '경로' candidates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from source_text import TEXT_EXTENSIONS, extract_source_text


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = SKILL_ROOT / "references" / "confirmed-rules.jsonl"
PROFILE_SCOPES = {
    "general": "general_it_business",
    "technical-report": "general_it_business",
    "executive-report": "general_it_business",
    "presentation": "general_it_business",
    "presenter-notes": "presenter_notes",
    "short-message": "general_it_business",
    "ct-project": "ct_project_context",
}
COMPARISON_MARKERS = ("→", "=>", "->", "❌", "✅")
# 나쁜 쪽과 좋은 쪽을 짝으로 보여 주는 표기. 고칠 문구가 없는 규칙은 이 짝으로만 예시를 가린다.
CONTRAST_PAIRS = (("❌", "✅"), ("✗", "✓"), ("×", "○"))
TERM = re.compile("경로")
ABSTRACT_PREFIXES = (
    "제품화", "도입", "성장", "개선", "상용화", "발전", "전환", "확장",
    "진입", "학습", "실현", "달성", "해결", "복구", "성공", "수익화",
    "배포", "운영",
)
ABSTRACT = re.compile(rf"({'|'.join(ABSTRACT_PREFIXES)})\s*경로")
AGENT_PATH_METAPHOR = re.compile(
    r"에이전트.{0,16}경로(?:를|에서)?\s*(?:이탈|벗어(?:나|났))"
)
LITERAL = re.compile(
    r"(?:파일|폴더|디렉터리|디렉토리|절대|상대|UNC|네임스페이스|메뉴|화면|"
    r"URL|URI|Windows|윈도우|import|임포트|권한|원격|소스|설정|스캔|호출|실행|"
    r"보고서|프로젝트|네트워크 공유(?:의\s+특정)?|하위호환|우회|Write)\s*경로"
    r"|경로(?:의|가|는|를|에|로)?\s*(?:문자열|구분자|표기|입력|인자|변수|"
    r"처리|패턴|포맷|불일치|잔재|전체|단축|조정|포함|삭제|재인덱싱|"
    r"비어|활성화|허용|한정)"
    r"|(?:아래|해당|특정|네트워크 공유의\s+특정)\s*경로(?:에|로|를)?\s*(?:생성|저장|등록|지정|"
    r"복사|이동|삭제|접근|확인)"
    r"|\|\s*경로\s*\|"
    r"|(?:[A-Za-z]:[\\/]|\\\\|(?:^|\s)/[A-Za-z0-9_.-]|"
    r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
)


def rule_key(record: dict[str, object]) -> str:
    """규칙이 무엇을 찾는지 나타내는 열쇠. 같은 것을 두 번 등록하지 못하게 한다."""
    if str(record.get("detector", "literal")) == "regex":
        return f"regex:{record.get('pattern')}"
    return f"literal:{record.get('original')}"


@lru_cache(maxsize=512)
def compiled(pattern: str) -> re.Pattern[str]:
    """정규식을 컴파일해 재사용한다.

    컴파일 결과를 규칙 레코드에 심지 않는다. 심어 두면 그 레코드를 파일에 쓰는 순간
    `Object of type Pattern is not JSON serializable` 로 터진다 — 지금은 그런 경로가
    없지만 규칙을 읽어 고쳐 쓰는 코드가 생기면 바로 걸린다.
    """
    return re.compile(pattern)


def compile_rule(record: dict[str, object], line_number: int) -> None:
    """정규식 규칙이 쓸 수 있는 것인지 확인한다. 실패하면 검사 중이 아니라 적재 중에 안다."""
    try:
        compiled(str(record["pattern"]))
    except re.error as error:
        raise ValueError(f"invalid pattern at line {line_number}: {error}") from error
    allow = record.get("allow") or []
    if not isinstance(allow, list):
        raise ValueError(f"allow must be a list at line {line_number}")
    for item in allow:
        try:
            compiled(str(item))
        except re.error as error:
            raise ValueError(
                f"invalid allow pattern at line {line_number}: {error}"
            ) from error


def allow_example_errors(record: dict[str, object]) -> list[str]:
    """허용 형태마다 통과하는 예문이 붙어 있는지 본다.

    예문이 없으면 승격기가 **정규식 문자열 자체를 시료 본문으로** 쓴다. `\\s*` 같은
    표기가 글자 그대로 들어가 허용 형태와 안 맞고, 그 시료는 승격 직후 자체 시험을
    실패시켜 통째로 되돌린다. 예문이 있어도 그것이 실제로 통과하지 않으면 같은 일이
    난다 — 그래서 예문을 검사기에 직접 돌려 본다.
    """
    allow = record.get("allow") or []
    if not allow:
        return []
    examples = record.get("allow_examples") or []
    if len(examples) != len(allow):
        return [
            f"each allow pattern needs one example: "
            f"{len(allow)} patterns, {len(examples)} examples"
        ]
    errors: list[str] = []
    probe = {
        key: record[key]
        for key in ("detector", "original", "pattern", "allow")
        if key in record
    }
    for index, example in enumerate(examples, 1):
        if rule_matches(probe, str(example)):
            errors.append(f"allow example {index} is still reported: {example}")
    return errors


def load_rules(path: Path = DEFAULT_RULES) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        annotation_id = str(record["annotation_id"])
        detector = str(record.get("detector", "literal"))
        if detector not in ("literal", "regex"):
            raise ValueError(f"unknown detector at line {line_number}: {detector}")
        if annotation_id in seen_ids:
            raise ValueError(f"duplicate annotation_id at line {line_number}: {annotation_id}")
        key = rule_key(record)
        if key in seen_keys:
            raise ValueError(f"duplicate rule target at line {line_number}: {key}")
        if "scope" not in record:
            raise ValueError(f"incomplete rule at line {line_number}")
        if detector == "regex":
            if not record.get("pattern"):
                raise ValueError(f"regex rule needs a pattern at line {line_number}")
            compile_rule(record, line_number)
        else:
            if not record.get("original") or not record.get("revised"):
                raise ValueError(f"incomplete rule at line {line_number}")
        seen_ids.add(annotation_id)
        seen_keys.add(key)
        records.append(record)
    return records


def applies_to_scope(
    record: dict[str, object],
    input_scope: str,
    input_profile: str | None = None,
) -> bool:
    if input_scope == "all":
        return True
    profiles = record.get("profiles")
    if isinstance(profiles, list) and profiles:
        if input_profile not in profiles:
            return False
    rule_scope = str(record["scope"])
    return (
        rule_scope == "general_it_business"
        or rule_scope == input_scope
    )


def is_comparison_example(line: str, original: str, revised: str) -> bool:
    if not revised:
        # 고칠 문구가 정해지지 않은 규칙은 나쁜 쪽과 좋은 쪽을 견줄 수 없다. 빈 문자열은
        # 어느 줄에서나 0번째에서 발견되므로 아래 판정을 그대로 태우면 **표 안의 지적과
        # 화살표 뒤의 지적이 통째로 사라진다**(실측 두 경우 모두). 대조 기호가 짝으로
        # 있는 줄만 예시로 본다.
        return any(bad in line and good in line for bad, good in CONTRAST_PAIRS)
    original_at = line.find(original)
    revised_at = line.find(revised)
    if original_at < 0 or revised_at < 0:
        return False
    if line.lstrip().startswith("|") and line.count("|") >= 3:
        return True
    if original_at < revised_at:
        between = line[original_at + len(original):revised_at]
    else:
        between = line[revised_at + len(revised):original_at]
    return any(marker in between for marker in COMPARISON_MARKERS)


def classify_path(line: str, start: int, end: int) -> tuple[str, str | None, str]:
    left = max(0, start - 40)
    right = min(len(line), end + 40)
    context = line[left:right].strip()
    abstract = ABSTRACT.search(context)
    if abstract:
        return "abstract_candidate", abstract.group(0), context
    agent_metaphor = AGENT_PATH_METAPHOR.search(context)
    if agent_metaphor:
        return "abstract_candidate", agent_metaphor.group(0), context
    literal = LITERAL.search(context)
    if literal:
        return "literal_candidate", literal.group(0), context
    return "review", None, context


def overlaps(start: int, end: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)


def is_allowed(record: dict[str, object], line: str, start: int, end: int) -> bool:
    """정당한 쓰임으로 등록된 형태인지 본다.

    사용자가 오탐이라고 판정한 것을 규칙에 되먹이는 통로다. 이 통로가 없으면 오탐은
    기록만 되고 검사기는 그대로라 같은 지적이 계속 나온다.

    허용 형태는 **그 자리에서** 맞아야 한다. 줄 전체로 보면 같은 줄에 정당한 쓰임과
    고쳐야 할 쓰임이 함께 있을 때 둘 다 넘어간다.
    """
    allow = record.get("allow") or []
    if not allow:
        return False
    left = max(0, start - 40)
    window = line[left:min(len(line), end + 40)]
    hit_start, hit_end = start - left, end - left
    for item in allow:
        for match in compiled(str(item)).finditer(window):
            if match.start() < hit_end and match.end() > hit_start:
                return True
    return False


def rule_matches(
    record: dict[str, object], line: str
) -> list[tuple[int, int, str]]:
    """한 규칙이 한 줄에서 찾아낸 자리를 (시작, 끝, 걸린 문자열)로 낸다."""
    spans: list[tuple[int, int, str]] = []
    if str(record.get("detector", "literal")) == "regex":
        source = record.get("pattern")
        if not source:
            return spans
        for match in compiled(str(source)).finditer(line):
            if match.start() == match.end():
                continue
            if is_allowed(record, line, match.start(), match.end()):
                continue
            spans.append((match.start(), match.end(), match.group(0)))
        return spans
    original = str(record.get("original") or "")
    if not original:
        return spans
    start = 0
    while True:
        index = line.find(original, start)
        if index < 0:
            return spans
        end = index + len(original)
        if not is_allowed(record, line, index, end):
            spans.append((index, end, original))
        start = end


def scan_text(
    text: str,
    rules: Iterable[dict[str, object]],
    input_scope: str,
    include_review: bool = False,
    input_profile: str | None = None,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for local_line_number, line in enumerate(text.splitlines() or [text], 1):
        covered_spans: list[tuple[int, int]] = []
        for record in rules:
            if not applies_to_scope(record, input_scope, input_profile):
                continue
            revised = str(record.get("revised") or "")
            for index, end, matched in rule_matches(record, line):
                if is_comparison_example(line, matched, revised):
                    continue
                replacement_mode = str(record.get("replacement_mode", "exact_suggestion"))
                requires_context = bool(record.get("requires_context", False))
                action = (
                    "review_context"
                    if replacement_mode == "contextual_rewrite" or requires_context
                    else "suggest_exact"
                )
                finding: dict[str, object] = {
                    "source": "user_feedback",
                    "action": action,
                    "classification": "confirmed_expression",
                    "detector": str(record.get("detector", "literal")),
                    "line_number": local_line_number,
                    "start_column": index + 1,
                    "end_column": end + 1,
                    "annotation_id": record["annotation_id"],
                    "rule_id": record["rule_id"],
                    "scope": record["scope"],
                    "input_scope": input_scope,
                    "original": matched,
                    "suggestion": revised or None,
                    "requires_context": requires_context,
                    "context": line.strip(),
                }
                rule_context = {
                    field: record[field]
                    for field in (
                        "context_level",
                        "context_before",
                        "context_after",
                        "context_excerpt",
                        "section_title",
                        "logical_path",
                        "source_ref",
                        "source_hash",
                        "context_note",
                        "profiles",
                    )
                    if record.get(field)
                }
                if rule_context:
                    finding["rule_context"] = rule_context
                findings.append(finding)
                covered_spans.append((index, end))
        for occurrence, match in enumerate(TERM.finditer(line), 1):
            if overlaps(match.start(), match.end(), covered_spans):
                continue
            classification, evidence, context = classify_path(
                line, match.start(), match.end()
            )
            if classification == "literal_candidate":
                continue
            if classification == "review" and not include_review:
                continue
            findings.append({
                "source": "path_metaphor",
                "action": "review_context",
                "classification": classification,
                "line_number": local_line_number,
                "start_column": match.start() + 1,
                "end_column": match.end() + 1,
                "rule_id": "KOR-METAPHOR-PATH-001",
                "input_scope": input_scope,
                "original": match.group(0),
                "suggestion": None,
                "requires_context": True,
                "evidence": evidence,
                "context": context,
                "occurrence": occurrence,
            })
    return findings


def iter_source_files(targets: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for target in targets:
        resolved = target.resolve()
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        if resolved.is_file():
            if resolved.suffix.casefold() not in TEXT_EXTENSIONS:
                raise ValueError(f"unsupported source format: {resolved}")
            files.add(resolved)
            continue
        files.update(
            path.resolve()
            for path in resolved.rglob("*")
            if path.is_file() and path.suffix.casefold() in TEXT_EXTENSIONS
        )
    if not files:
        raise ValueError("no supported source files found")
    return sorted(files)


def scan_files(
    targets: Iterable[Path],
    rules: list[dict[str, object]],
    input_scope: str,
    include_review: bool,
    input_profile: str | None = None,
) -> dict[str, object]:
    files = iter_source_files(targets)
    findings: list[dict[str, object]] = []
    unit_count = 0
    for path in files:
        units = extract_source_text(path)
        unit_count += len(units)
        for unit in units:
            unit_findings = scan_text(
                str(unit["text"]), rules, input_scope, include_review, input_profile
            )
            for finding in unit_findings:
                source_line = unit["line_number"]
                local_line = int(finding["line_number"])
                finding["line_number"] = (
                    int(source_line) + local_line - 1
                    if isinstance(source_line, int)
                    else None
                )
                finding["file"] = path.as_posix()
                finding["logical_path"] = unit["logical_path"]
                finding["source_format"] = path.suffix.casefold().lstrip(".")
                findings.append(finding)
    findings.sort(key=lambda item: (
        str(item["file"]),
        -1 if item["line_number"] is None else int(item["line_number"]),
        int(item["start_column"]),
        str(item["source"]),
    ))
    counts = Counter(str(item["action"]) for item in findings)
    return {
        "status": "findings" if findings else "clean",
        "input_scope": input_scope,
        "files_scanned": len(files),
        "units_scanned": unit_count,
        "finding_count": len(findings),
        "action_counts": dict(sorted(counts.items())),
        "findings": findings,
    }


def print_text(result: dict[str, object]) -> None:
    print(
        f"status={result['status']} files={result['files_scanned']} "
        f"units={result['units_scanned']} findings={result['finding_count']}"
    )
    for item in result["findings"]:  # type: ignore[assignment]
        line = item["line_number"] if item["line_number"] is not None else "?"
        suggestion = (
            f" -> {item['suggestion']}" if item.get("suggestion") else ""
        )
        print(
            f"[{item['action']}] {item['file']}:{line}:{item['start_column']} "
            f"{item['original']}{suggestion}"
        )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="+", type=Path)
    parser.add_argument("--profile", choices=sorted(PROFILE_SCOPES), default="general")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--include-review", action="store_true")
    parser.add_argument("--format", choices=("text", "json", "jsonl"), default="text")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        result = scan_files(
            args.targets,
            load_rules(args.rules),
            PROFILE_SCOPES[args.profile],
            args.include_review,
            args.profile,
        )
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        print(f"check_failed: {error}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.format == "jsonl":
        for finding in result["findings"]:  # type: ignore[assignment]
            print(json.dumps(finding, ensure_ascii=False, sort_keys=True))
    else:
        print_text(result)
    return 1 if args.strict and result["finding_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
