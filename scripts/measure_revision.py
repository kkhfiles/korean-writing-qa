#!/usr/bin/env python
"""Measure a revision without counting its humanize summary comment."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


SUMMARY = re.compile(r"\n<!-- HUMANIZE-SUMMARY\n.*?\n-->\s*$", re.DOTALL)
PROTECTED = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[A-Za-z][A-Za-z0-9_.+/-]*|\d[\d.,~:+/-]*[A-Za-z%]*)"
    r"(?![A-Za-z0-9])"
    r'|"[^"\n]+"|「[^」\n]+」|『[^』\n]+』'
)


def body(text: str) -> str:
    return SUMMARY.sub("", text.replace("\r\n", "\n")).rstrip() + "\n"


def levenshtein_distance(left: str, right: str) -> int:
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for row, right_character in enumerate(right, start=1):
        current = [row]
        for column, left_character in enumerate(left, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def measure(original: str, revised: str) -> dict[str, object]:
    original_body = body(original)
    revised_body = body(revised)
    distance = levenshtein_distance(original_body, revised_body)
    protected_before = Counter(PROTECTED.findall(original_body))
    protected_after = Counter(PROTECTED.findall(revised_body))
    return {
        "original_chars": len(original_body),
        "revised_chars": len(revised_body),
        "levenshtein_distance": distance,
        "change_rate": distance / max(1, len(original_body)),
        "protected_removed": sorted((protected_before - protected_after).elements()),
        "protected_added": sorted((protected_after - protected_before).elements()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("revised", type=Path)
    args = parser.parse_args()
    result = measure(
        args.original.read_text(encoding="utf-8"),
        args.revised.read_text(encoding="utf-8"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
