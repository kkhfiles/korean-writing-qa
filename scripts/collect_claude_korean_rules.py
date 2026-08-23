#!/usr/bin/env python
"""Collect Korean-writing rules from Claude Code rules and memories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".json",
    ".jsonl",
    ".md",
    ".properties",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
EXCLUDED_DIRECTORIES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "tool-results",
}

SOURCE_PRIORITY = {
    "global_rule": 0,
    "reference": 1,
    "command": 2,
    "project_rule": 3,
    "global_memory": 4,
    "project_memory": 5,
    "skill": 6,
    "plugin_rule": 7,
}

# A section with one weak word such as ``표현`` is not enough. Each category
# therefore uses phrases that describe an actual writing rule or preference.
CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "natural_korean": (
        r"한국어",
        r"한글",
        r"번역투",
        r"영어[ -]?직역",
        r"영어 어순",
        r"어색(?:한|하게|함|하다고|하지)",
        r"자연스러운 한글",
        r"자연스러운 한국어",
        r"자연스럽게 (?:고쳐|다듬|재작성)",
    ),
    "brevity_and_clarity": (
        r"군더더기",
        r"단문",
        r"복문",
        r"주어와 술어",
        r"같은 말을 두 번",
        r"어려운 말",
        r"소리 내어 읽",
        r"과도한? 축약",
        r"완성된 (?:구|절)",
    ),
    "register_and_terms": (
        r"구어체",
        r"비격식",
        r"반말",
        r"경어체",
        r"합쇼체",
        r"말투",
        r"어조",
        r"슬로건",
        r"마케팅 (?:어조|용어)",
        r"과한 영어",
        r"영문 용어",
        r"외래어",
        r"한자어",
        r"약어.{0,20}(?:금지|풀어|정의)",
        r"기술 용어.{0,20}(?:금지|풀어|정의)",
        r"용어.{0,20}(?:금지|통일|일관|풀어)",
        r"평이한 한국어",
        r"평이어",
    ),
    "document_structure": (
        r"라벨\s*[:：]\s*값",
        r"라벨은 명사구",
        r"의문문 라벨",
        r"개조식",
        r"명사형 종결",
        r"서술형 종결",
        r"절단형 종결",
        r"조사로 끝",
        r"값 칸",
        r"진입점",
        r"한 줄\s*=\s*한 사실",
        r"한 묶음 [0-9]+[~～-][0-9]+행",
        r"목록 항목의 굵게",
        r"표 칸",
    ),
    "reference_and_ambiguity": (
        r"모호한 지칭",
        r"대상은 이름으로 지칭",
        r"지시어",
        r"대명사",
        r"주어 (?:명시|누락|복원)",
        r"숫자.{0,10}주어 명시",
        r"~하는 자리",
        r"제품화 경로",
        r"다시 세우는 부분",
        r"내부 추상어",
        r"평가 수식어",
    ),
    "reader_framing": (
        r"독자가 품은 적 없는",
        r"독자.{0,30}(?:오해|지적)",
        r"로 읽으면 틀림",
        r"깔고 들어가지 말",
        r"사실을 그대로 (?:서술|진술)",
    ),
    "ai_tells": (
        r"AI 티",
        r"인공지능 티",
        r"AI(?:가|로)? (?:쓴|작성|생성).{0,20}(?:문체|표현|글)",
        r"AI[- ]?tell",
        r"post-editese",
        r"휴먼라이즈",
        r"윤문",
    ),
    "content_fidelity": (
        r"내용.{0,20}(?:보존|바꾸지|건드리지)",
        r"의미.{0,20}(?:보존|바꾸지)",
        r"사실.{0,20}(?:추가|삭제|변경).{0,10}(?:금지|하지)",
        r"고유명사.{0,20}(?:보존|변경 금지)",
        r"숫자.{0,20}(?:보존|변경 금지)",
    ),
    "presentation_language": (
        r"슬라이드.{0,20}(?:문체|문구|표현|용어|제목)",
        r"제목.{0,20}(?:명사형|주어|직설|결론)",
        r"헤드라인",
        r"발표자 노트.{0,20}(?:경어체|구어)",
        r"화면 문구",
        r"임원 (?:발표|보고).{0,20}(?:문체|어조|용어|표현)",
    ),
}

COMPILED_PATTERNS = {
    category: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for category, patterns in CATEGORY_PATTERNS.items()
}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def iter_files(root: Path, names_only: set[str] | None = None) -> Iterable[Path]:
    """Yield text files while ignoring generated/session-data directories."""
    if not root.exists():
        return
    for current, directories, filenames in os.walk(root, onerror=lambda _: None):
        directories[:] = [
            name for name in directories if name not in EXCLUDED_DIRECTORIES
        ]
        for filename in filenames:
            if names_only is not None and filename.casefold() not in names_only:
                continue
            path = Path(current) / filename
            if path.suffix.casefold() in TEXT_EXTENSIONS:
                yield path


def discover_sources(
    claude_root: Path, workspace_roots: Iterable[Path]
) -> list[dict[str, object]]:
    found: dict[str, dict[str, object]] = {}

    def add(path: Path, source_type: str) -> None:
        try:
            resolved = path.resolve()
            if not resolved.is_file() or resolved.suffix.casefold() not in TEXT_EXTENSIONS:
                return
            stat = resolved.stat()
            data = resolved.read_bytes()
        except (OSError, UnicodeError):
            return
        key = str(resolved).casefold()
        previous = found.get(key)
        if previous and SOURCE_PRIORITY[str(previous["source_type"])] <= SOURCE_PRIORITY[source_type]:
            return
        found[key] = {
            "source_path": resolved.as_posix(),
            "source_type": source_type,
            "bytes": len(data),
            "modified_utc": datetime.fromtimestamp(
                stat.st_mtime, timezone.utc
            ).isoformat(),
            "sha256": sha256_bytes(data),
        }

    add(claude_root / "CLAUDE.md", "global_rule")
    for directory, source_type in (
        ("commands", "command"),
        ("references", "reference"),
        ("skills", "skill"),
        ("memory", "global_memory"),
    ):
        for path in iter_files(claude_root / directory):
            add(path, source_type)

    projects_root = claude_root / "projects"
    if projects_root.exists():
        for path in iter_files(projects_root):
            parts = {part.casefold() for part in path.parts}
            if "memory" in parts:
                add(path, "project_memory")

    for path in iter_files(claude_root / "plugins" / "cache"):
        add(path, "plugin_rule")

    for workspace_root in workspace_roots:
        for path in iter_files(workspace_root, {"claude.md"}):
            add(path, "project_rule")

    sources = sorted(
        found.values(),
        key=lambda item: (
            SOURCE_PRIORITY[str(item["source_type"])],
            str(item["source_path"]).casefold(),
        ),
    )
    canonical_by_hash: dict[str, str] = {}
    for source in sources:
        digest = str(source["sha256"])
        source["duplicate_of"] = canonical_by_hash.get(digest)
        canonical_by_hash.setdefault(digest, str(source["source_path"]))
    return sources


def split_sections(text: str) -> list[dict[str, object]]:
    lines = text.splitlines()
    sections: list[dict[str, object]] = []
    heading_stack: list[tuple[int, str]] = []
    content_start = 1
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:100], start=1):
            if line.strip() == "---":
                content_start = index + 2
                break
    start = content_start
    current_path: list[str] = ["(preamble)"]

    def append_section(end: int) -> None:
        if end < start:
            return
        section_text = "\n".join(lines[start - 1 : end]).strip()
        if section_text:
            sections.append(
                {
                    "heading_path": current_path.copy(),
                    "line_start": start,
                    "line_end": end,
                    "text": section_text,
                }
            )

    for line_number, line in enumerate(lines, start=1):
        if line_number < content_start:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        append_section(line_number - 1)
        level = len(match.group(1))
        title = match.group(2).strip()
        heading_stack = [item for item in heading_stack if item[0] < level]
        heading_stack.append((level, title))
        current_path = [item[1] for item in heading_stack]
        start = line_number
    append_section(len(lines))
    return sections


def matched_categories(text: str) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for category, patterns in COMPILED_PATTERNS.items():
        found = sorted(
            {
                match.group(0)
                for pattern in patterns
                for match in pattern.finditer(text)
            },
            key=str.casefold,
        )
        if found:
            matches[category] = found
    return matches


def collect_passages(sources: list[dict[str, object]]) -> list[dict[str, object]]:
    aliases_by_hash: defaultdict[str, list[str]] = defaultdict(list)
    for source in sources:
        aliases_by_hash[str(source["sha256"])].append(str(source["source_path"]))

    passages_by_hash: dict[str, dict[str, object]] = {}
    for source in sources:
        if source["duplicate_of"] is not None:
            continue
        path = Path(str(source["source_path"]))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for section in split_sections(text):
            matches = matched_categories(str(section["text"]))
            if not matches:
                continue
            normalized = normalized_text(str(section["text"]))
            digest = sha256_bytes(normalized.encode("utf-8"))
            score = sum(len(values) for values in matches.values()) + 2 * len(matches)
            passage = {
                "passage_sha256": digest,
                "source_path": source["source_path"],
                "source_aliases": aliases_by_hash[str(source["sha256"])],
                "source_type": source["source_type"],
                "heading_path": section["heading_path"],
                "line_start": section["line_start"],
                "line_end": section["line_end"],
                "categories": sorted(matches),
                "matched_phrases": matches,
                "relevance_score": score,
                "text": section["text"],
            }
            previous = passages_by_hash.get(digest)
            if previous is None or score > int(previous["relevance_score"]):
                passages_by_hash[digest] = passage
            elif previous is not None:
                previous_aliases = set(previous["source_aliases"])
                previous_aliases.update(passage["source_aliases"])
                previous["source_aliases"] = sorted(previous_aliases, key=str.casefold)

    passages = list(passages_by_hash.values())
    passages.sort(
        key=lambda item: (
            -int(item["relevance_score"]),
            str(item["source_path"]).casefold(),
            int(item["line_start"]),
        )
    )
    for index, passage in enumerate(passages, start=1):
        passage["passage_id"] = f"claude-rule-{index:04d}"
    return passages


def write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def build(
    claude_root: Path,
    project_root: Path,
    workspace_roots: Iterable[Path],
    run_id: str,
) -> dict[str, object]:
    claude_root = claude_root.resolve()
    project_root = project_root.resolve()
    workspace_roots = [root.resolve() for root in workspace_roots if root.exists()]

    sources = discover_sources(claude_root, workspace_roots)
    passages = collect_passages(sources)

    catalog_path = project_root / "data" / "catalog" / "claude-rule-sources.jsonl"
    raw_path = project_root / "data" / "raw" / run_id / "candidate-passages.jsonl"
    run_root = project_root / "runs" / run_id
    summary_path = run_root / "collection-summary.json"
    if summary_path.exists():
        raise ValueError(f"Run summary already exists: {summary_path}")

    write_jsonl(catalog_path, sources)
    write_jsonl(raw_path, passages)

    source_types = Counter(str(source["source_type"]) for source in sources)
    source_extensions = Counter(
        Path(str(source["source_path"])).suffix.casefold() for source in sources
    )
    category_counts = Counter(
        category for passage in passages for category in passage["categories"]
    )
    duplicate_files = sum(source["duplicate_of"] is not None for source in sources)
    high_confidence = sum(int(item["relevance_score"]) >= 8 for item in passages)
    summary: dict[str, object] = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "claude_root": claude_root.as_posix(),
        "workspace_roots": [root.as_posix() for root in workspace_roots],
        "scope": {
            "included": [
                "global CLAUDE.md",
                "commands and references",
                "skills",
                "global and project memory text/structured rules",
                "installed plugin text/structured rules",
                "workspace CLAUDE.md",
            ],
            "excluded": [
                "session transcripts",
                "tool results",
                "debug logs",
                "generated caches",
            ],
        },
        "source_files": len(sources),
        "unique_source_files": len(sources) - duplicate_files,
        "duplicate_source_files": duplicate_files,
        "source_type_counts": dict(sorted(source_types.items())),
        "source_extension_counts": dict(sorted(source_extensions.items())),
        "candidate_passages": len(passages),
        "high_confidence_passages_score_ge_8": high_confidence,
        "category_counts": dict(sorted(category_counts.items())),
        "catalog_path": catalog_path.relative_to(project_root).as_posix(),
        "raw_passages_path": raw_path.relative_to(project_root).as_posix(),
        "raw_passages_git_ignored": True,
        "collector_path": Path(__file__).resolve().as_posix(),
        "collector_sha256": sha256_bytes(Path(__file__).resolve().read_bytes()),
        "limitations": [
            "Keyword retrieval is exhaustive for the declared patterns, not semantic proof that no other writing rule exists.",
            "Workspace CLAUDE.md discovery is limited to the supplied workspace roots.",
            "Automatic candidates require human review before becoming checker rules.",
        ],
    }
    run_root.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect Korean-writing rules from Claude Code rules and memories."
    )
    parser.add_argument("--claude-root", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--workspace-root", action="append", default=[], type=Path)
    parser.add_argument("--run-id", default="claude-korean-rules-001")
    args = parser.parse_args()
    summary = build(
        claude_root=args.claude_root,
        project_root=args.project_root,
        workspace_roots=args.workspace_root,
        run_id=args.run_id,
    )
    print(
        f"sources={summary['source_files']} "
        f"passages={summary['candidate_passages']} run={summary['run_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
