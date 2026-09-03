#!/usr/bin/env python
"""Scan source text for user-confirmed awkward Korean examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

try:
    from scripts import skill_bridge
except ImportError:  # Direct execution: python scripts/scan_user_feedback.py
    # ImportError 로 잡는다 — `scripts` 가 위치 없는 이름공간으로 잡히면
    # ModuleNotFoundError 가 아니라 ImportError 가 난다(실측).
    import skill_bridge

# 추출 논리도 스킬이 정본이다 — 사본을 두면 한쪽만 고쳐진다.
_source_text = skill_bridge.load("source_text")
TEXT_EXTENSIONS = _source_text.TEXT_EXTENSIONS
extract_source_text = _source_text.extract_source_text

# 탐지 논리는 배포된 스킬이 정본이다. 여기서 다시 적으면 한쪽만 고쳐진다.
_check = skill_bridge.load("check")
COMPARISON_MARKERS = _check.COMPARISON_MARKERS
PROFILE_SCOPES = _check.PROFILE_SCOPES
is_comparison_example = _check.is_comparison_example
applies_to_scope = _check.applies_to_scope
load_feedback = _check.load_rules


def scan_text(
    text: str,
    feedback: Iterable[dict[str, object]],
    input_scope: str,
    input_profile: str | None = None,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for record in feedback:
            if not applies_to_scope(record, input_scope, input_profile):
                continue
            original = str(record["original"])
            revised = str(record["revised"])
            if is_comparison_example(line, original, revised):
                continue
            start = 0
            while True:
                index = line.find(original, start)
                if index < 0:
                    break
                replacement_mode = str(
                    record.get("replacement_mode", "exact_suggestion")
                )
                requires_context = bool(record.get("requires_context", False))
                action = (
                    "review_context"
                    if replacement_mode == "contextual_rewrite" or requires_context
                    else "suggest_exact"
                )
                findings.append(
                    {
                        "line_number": line_number,
                        "start_column": index + 1,
                        "end_column": index + len(original) + 1,
                        "annotation_id": record["annotation_id"],
                        "rule_id": record["rule_id"],
                        "category": record["category"],
                        "scope": record["scope"],
                        "input_scope": input_scope,
                        "original": original,
                        "suggestion": revised,
                        "replacement_mode": replacement_mode,
                        "requires_context": requires_context,
                        "action": action,
                        "context": line.strip(),
                    }
                )
                start = index + len(original)
    return findings


def scan_path(
    source: Path,
    feedback: Iterable[dict[str, object]],
    input_scope: str,
    input_profile: str | None = None,
) -> list[dict[str, object]]:
    if source.is_file():
        paths = [source]
        source_root = source.parent
    else:
        source_root = source
        paths = sorted(
            path
            for path in source.rglob("*")
            if path.is_file() and path.suffix.casefold() in TEXT_EXTENSIONS
        )
    findings: list[dict[str, object]] = []
    for path in paths:
        if path.suffix.casefold() not in TEXT_EXTENSIONS:
            continue
        for extracted in extract_source_text(path):
            unit_findings = scan_text(
                str(extracted["text"]), feedback, input_scope, input_profile
            )
            for finding in unit_findings:
                source_line = extracted["line_number"]
                if isinstance(source_line, int):
                    finding["line_number"] = source_line + int(finding["line_number"]) - 1
                else:
                    finding["line_number"] = None
                finding["relative_path"] = path.relative_to(source_root).as_posix()
                finding["logical_path"] = extracted["logical_path"]
                finding["unit_id"] = extracted["unit_id"]
                finding["unit_kind"] = extracted["kind"]
                finding["source_format"] = extracted["source_format"]
                findings.append(finding)
    findings.sort(
        key=lambda item: (
            str(item["relative_path"]),
            -1 if item["line_number"] is None else int(item["line_number"]),
            str(item["logical_path"]),
            int(item["start_column"]),
            str(item["annotation_id"]),
        )
    )
    return findings


def write_jsonl(path: Path, findings: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for finding in findings:
            handle.write(json.dumps(finding, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan source text for user-confirmed awkward Korean examples."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--feedback", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    scope_group = parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument(
        "--scope",
        help="Input document scope, or 'all' for an intentional cross-scope scan.",
    )
    scope_group.add_argument("--profile", choices=sorted(PROFILE_SCOPES))
    args = parser.parse_args()

    feedback = load_feedback(args.feedback)
    input_scope = PROFILE_SCOPES[args.profile] if args.profile else args.scope
    findings = scan_path(
        args.source.resolve(), feedback, input_scope, args.profile
    )
    write_jsonl(args.output, findings)
    counts = {
        action: sum(item["action"] == action for item in findings)
        for action in ("suggest_exact", "review_context")
    }
    print(
        f"findings={len(findings)} "
        f"suggest_exact={counts['suggest_exact']} "
        f"review_context={counts['review_context']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
