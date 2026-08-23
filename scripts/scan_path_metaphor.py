#!/usr/bin/env python
"""Extract and provisionally classify Korean '경로' occurrences."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


TEXT_EXTENSIONS = {".md", ".html", ".txt"}
TERM = re.compile("경로")
ABSTRACT_PREFIXES = (
    "제품화",
    "도입",
    "성장",
    "개선",
    "상용화",
    "발전",
    "전환",
    "확장",
    "진입",
    "학습",
    "실현",
    "달성",
    "해결",
    "복구",
    "성공",
    "수익화",
    "배포",
    "운영",
)
ABSTRACT = re.compile(rf"({'|'.join(ABSTRACT_PREFIXES)})\s*경로")
LITERAL = re.compile(
    r"(?:파일|폴더|디렉터리|절대|상대|UNC|네임스페이스|메뉴|화면|URL|URI)\s*경로"
    r"|경로\s*(?:문자열|구분자|표기|입력|인자|변수)"
    r"|(?:[A-Za-z]:[\\/]|\\\\|(?:^|\s)/[A-Za-z0-9_.-])"
)


def classify(line: str, start: int, end: int) -> tuple[str, str | None, str]:
    left = max(0, start - 40)
    right = min(len(line), end + 40)
    context = line[left:right].strip()
    abstract = ABSTRACT.search(context)
    if abstract:
        return "abstract_candidate", abstract.group(0), context
    literal = LITERAL.search(context)
    if literal:
        return "literal_candidate", literal.group(0), context
    return "review", None, context


def scan(source_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for occurrence, match in enumerate(TERM.finditer(line), start=1):
                classification, evidence, context = classify(
                    line, match.start(), match.end()
                )
                findings.append(
                    {
                        "relative_path": path.relative_to(source_root).as_posix(),
                        "line_number": line_number,
                        "occurrence": occurrence,
                        "term": match.group(0),
                        "classification": classification,
                        "evidence": evidence,
                        "context": context,
                    }
                )
    return findings


def write_jsonl(path: Path, findings: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for finding in findings:
            stream.write(json.dumps(finding, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract literal and metaphorical Korean 경로 candidates."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    findings = scan(source_root)
    write_jsonl(args.output, findings)
    counts = Counter(str(item["classification"]) for item in findings)
    summary = {
        "source_root": source_root.as_posix(),
        "documents_with_term": len({item["relative_path"] for item in findings}),
        "occurrences": len(findings),
        "classifications": dict(sorted(counts.items())),
        "rule_status": "candidate_only",
        "positive_seed": "제품화 경로",
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.summary.with_suffix(args.summary.suffix + ".tmp")
    temporary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.summary)
    print(
        f"occurrences={len(findings)} files={summary['documents_with_term']} "
        + " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
