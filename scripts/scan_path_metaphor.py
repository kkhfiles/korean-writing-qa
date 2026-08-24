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
    from scripts.source_text import TEXT_EXTENSIONS, extract_source_text
except ModuleNotFoundError:  # Direct execution: python scripts/scan_path_metaphor.py
    from source_text import TEXT_EXTENSIONS, extract_source_text
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


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def classify(line: str, start: int, end: int) -> tuple[str, str | None, str]:
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
            "source_text_sha256": hash_file(Path(__file__).with_name("source_text.py")),
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
