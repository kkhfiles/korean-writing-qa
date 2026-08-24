#!/usr/bin/env python
"""Scan source text for user-confirmed awkward Korean examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

try:
    from scripts.source_text import TEXT_EXTENSIONS, extract_source_text
except ModuleNotFoundError:  # Direct execution: python scripts/scan_user_feedback.py
    from source_text import TEXT_EXTENSIONS, extract_source_text


COMPARISON_MARKERS = ("→", "=>", "->", "❌", "✅")


def is_comparison_example(line: str, original: str, revised: str) -> bool:
    original_at = line.find(original)
    revised_at = line.find(revised)
    if original_at < 0 or revised_at < 0:
        return False
    if line.lstrip().startswith("|") and line.count("|") >= 3:
        return True
    if original_at < revised_at:
        between = line[original_at + len(original) : revised_at]
    else:
        between = line[revised_at + len(revised) : original_at]
    return any(marker in between for marker in COMPARISON_MARKERS)


def load_feedback(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_originals: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        record = json.loads(line)
        annotation_id = str(record["annotation_id"])
        original = str(record["original"])
        revised = str(record["revised"])
        if annotation_id in seen_ids:
            raise ValueError(f"Duplicate annotation_id at line {line_number}: {annotation_id}")
        if original in seen_originals:
            raise ValueError(f"Duplicate original at line {line_number}: {original}")
        if not original or not revised:
            raise ValueError(f"Empty original/revised at line {line_number}")
        seen_ids.add(annotation_id)
        seen_originals.add(original)
        records.append(record)
    return records


def applies_to_scope(record: dict[str, object], input_scope: str) -> bool:
    rule_scope = str(record["scope"])
    return (
        input_scope == "all"
        or rule_scope == "general_it_business"
        or rule_scope == input_scope
    )


def scan_text(
    text: str,
    feedback: Iterable[dict[str, object]],
    input_scope: str,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for record in feedback:
            if not applies_to_scope(record, input_scope):
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
                str(extracted["text"]), feedback, input_scope
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
    parser.add_argument(
        "--scope",
        required=True,
        help="Input document scope, or 'all' for an intentional cross-scope scan.",
    )
    args = parser.parse_args()

    feedback = load_feedback(args.feedback)
    findings = scan_path(args.source.resolve(), feedback, args.scope)
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
