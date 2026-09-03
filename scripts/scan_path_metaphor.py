#!/usr/bin/env python
"""Extract and provisionally classify Korean '경로' occurrences."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

try:
    from scripts import skill_bridge
except ImportError:  # Direct execution: python scripts/scan_path_metaphor.py
    # ImportError 로 잡는다 — `scripts` 가 위치 없는 이름공간으로 잡히면
    # ModuleNotFoundError 가 아니라 ImportError 가 난다(실측).
    import skill_bridge

# 추출 논리도 스킬이 정본이다 — 사본을 두면 한쪽만 고쳐진다.
_source_text = skill_bridge.load("source_text")
TEXT_EXTENSIONS = _source_text.TEXT_EXTENSIONS
extract_source_text = _source_text.extract_source_text

# 탐지 논리는 배포된 스킬이 정본이다. 여기서 다시 적으면 한쪽만 고쳐진다.
_check = skill_bridge.load("check")
TERM = _check.TERM
ABSTRACT_PREFIXES = _check.ABSTRACT_PREFIXES
ABSTRACT = _check.ABSTRACT
AGENT_PATH_METAPHOR = _check.AGENT_PATH_METAPHOR
LITERAL = _check.LITERAL
classify = _check.classify_path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan(source_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in TEXT_EXTENSIONS:
            continue
        for extracted in extract_source_text(path):
            line = str(extracted["text"])
            for occurrence, match in enumerate(TERM.finditer(line), start=1):
                classification, evidence, context = classify(
                    line, match.start(), match.end()
                )
                findings.append(
                    {
                        "relative_path": path.relative_to(source_root).as_posix(),
                        "line_number": extracted["line_number"],
                        "logical_path": extracted["logical_path"],
                        "unit_id": extracted["unit_id"],
                        "unit_kind": extracted["kind"],
                        "source_format": extracted["source_format"],
                        "occurrence": occurrence,
                        "term": match.group(0),
                        "classification": classification,
                        "evidence": evidence,
                        "context": context,
                    }
                )
    findings.sort(
        key=lambda item: (
            str(item["relative_path"]),
            -1 if item["line_number"] is None else int(item["line_number"]),
            str(item["logical_path"]),
            int(item["occurrence"]),
        )
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
        "implementation": {
            "scanner_sha256": hash_file(Path(__file__)),
            # 배포본의 해시를 적는다 — 저장소 사본을 적으면 실제로 돈 것과 어긋난다
            "source_text_sha256": hash_file(
                skill_bridge.skill_home() / "scripts" / "source_text.py"),
        },
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
