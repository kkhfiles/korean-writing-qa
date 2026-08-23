#!/usr/bin/env python
"""Scan source text for user-confirmed awkward Korean examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".html",
    ".json",
    ".jsonl",
    ".md",
    ".properties",
    ".txt",
    ".yaml",
    ".yml",
}


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


def scan_text(
    text: str, feedback: Iterable[dict[str, object]]
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for record in feedback:
            original = str(record["original"])
            revised = str(record["revised"])
            if original in line and revised in line:
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
    source: Path, feedback: Iterable[dict[str, object]]
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
        for finding in scan_text(
            path.read_text(encoding="utf-8", errors="replace"), feedback
        ):
            finding["relative_path"] = path.relative_to(source_root).as_posix()
            findings.append(finding)
    findings.sort(
        key=lambda item: (
            str(item["relative_path"]),
            int(item["line_number"]),
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
    args = parser.parse_args()

    feedback = load_feedback(args.feedback)
    findings = scan_path(args.source.resolve(), feedback)
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
