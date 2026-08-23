#!/usr/bin/env python
"""Build a local sample of AI-generated Markdown, JSONL, and text sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.build_confirmed_ai_sample import confirmed_documents
    from scripts.build_diagnostic_sample import select_sample, size_bucket, write_jsonl
except ModuleNotFoundError:  # Direct execution
    from build_confirmed_ai_sample import confirmed_documents
    from build_diagnostic_sample import select_sample, size_bucket, write_jsonl


GENERATED_JSONL = Path("mycelium-utility/llm-generated-raw-20260522.jsonl")
RAW_TEXT_NAME = re.compile(r"(?i)(agy|gemini|raw)")
ERROR_TEXT_NAME = re.compile(r"(?i)(err|error)")
KOREAN = re.compile(r"[가-힣]")
GROUP_ORDER = ("markdown", "jsonl", "text")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def public_record(candidate: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in candidate.items()
        if not key.startswith("_")
    }


def markdown_candidates(source_root: Path) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for document in confirmed_documents(source_root):
        if int(document["korean_chars"]) == 0:
            continue
        candidate = dict(document)
        candidate.update(
            {
                "source_unit_id": f"markdown:{document['relative_path']}",
                "sample_group": "markdown",
                "source_format": ".md",
                "provenance_basis": "frontmatter_model_and_generated_at",
                "_source_path": source_root / str(document["relative_path"]),
            }
        )
        candidates.append(candidate)
    return candidates


def jsonl_candidates(source_root: Path) -> list[dict[str, object]]:
    path = source_root / GENERATED_JSONL
    if not path.is_file():
        return []
    candidates: list[dict[str, object]] = []
    with path.open("rb") as stream:
        for line_number, raw_line in enumerate(stream, start=1):
            if not raw_line.strip():
                continue
            try:
                text = raw_line.decode("utf-8")
                value = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"Invalid generated JSONL at line {line_number}") from error
            korean_chars = len(KOREAN.findall(text))
            if korean_chars == 0:
                continue
            source_name = (
                str(value.get("source", "unknown"))
                if isinstance(value, dict)
                else "unknown"
            )
            candidates.append(
                {
                    "source_unit_id": f"jsonl:{GENERATED_JSONL.as_posix()}#L{line_number}",
                    "relative_path": GENERATED_JSONL.as_posix(),
                    "record_line": line_number,
                    "extension": ".jsonl",
                    "source_format": ".jsonl",
                    "sample_group": "jsonl",
                    "bytes": len(raw_line),
                    "sha256": sha256(raw_line),
                    "line_count": 1,
                    "korean_chars": korean_chars,
                    "source_bucket": f"jsonl:{source_name}",
                    "size_bucket": size_bucket(len(raw_line)),
                    "provenance_basis": "llm_generated_raw_filename",
                    "_raw_bytes": raw_line,
                }
            )
    return candidates


def text_candidates(source_root: Path) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for path in sorted(source_root.rglob("*.txt")):
        if not RAW_TEXT_NAME.search(path.name) or ERROR_TEXT_NAME.search(path.name):
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        korean_chars = len(KOREAN.findall(text))
        if korean_chars == 0:
            continue
        relative = path.relative_to(source_root)
        candidates.append(
            {
                "source_unit_id": f"text:{relative.as_posix()}",
                "relative_path": relative.as_posix(),
                "extension": ".txt",
                "source_format": ".txt",
                "sample_group": "text",
                "bytes": len(raw),
                "sha256": sha256(raw),
                "line_count": len(text.splitlines()),
                "korean_chars": korean_chars,
                "source_bucket": (
                    relative.parts[0] if len(relative.parts) > 1 else "_root"
                ),
                "size_bucket": size_bucket(len(raw)),
                "provenance_basis": "raw_model_output_filename",
                "_source_path": path,
            }
        )
    return candidates


def discover_candidates(source_root: Path) -> list[dict[str, object]]:
    source_root = source_root.resolve()
    candidates = (
        markdown_candidates(source_root)
        + jsonl_candidates(source_root)
        + text_candidates(source_root)
    )
    return sorted(candidates, key=lambda item: str(item["source_unit_id"]))


def select_candidates(
    candidates: list[dict[str, object]],
    markdown_count: int,
    jsonl_count: int,
) -> list[dict[str, object]]:
    requested = {"markdown": markdown_count, "jsonl": jsonl_count}
    selected: list[dict[str, object]] = []
    for group in GROUP_ORDER:
        group_candidates = [
            item for item in candidates if item["sample_group"] == group
        ]
        if group == "text":
            chosen = group_candidates
        else:
            chosen = select_sample(
                group_candidates,
                requested[group],
                minimum_bytes=1,
                minimum_korean_chars=1,
            )
            if len(chosen) < requested[group]:
                raise ValueError(
                    f"Only {len(chosen)} {group} candidates for requested "
                    f"sample {requested[group]}"
                )
        selected.extend(chosen)
    return selected


def copy_candidate(candidate: dict[str, object], target: Path) -> None:
    if "_raw_bytes" in candidate:
        target.write_bytes(bytes(candidate["_raw_bytes"]))
        return
    shutil.copyfile(Path(candidate["_source_path"]), target)


def build(
    source_root: Path,
    project_root: Path,
    run_id: str,
    markdown_count: int,
    jsonl_count: int,
) -> dict[str, object]:
    source_root = source_root.resolve()
    project_root = project_root.resolve()
    catalog_path = project_root / "data" / "catalog" / "multiformat-ai-units.jsonl"
    raw_root = project_root / "data" / "raw" / run_id
    run_root = project_root / "runs" / run_id
    manifest_path = run_root / "sample-manifest.json"

    if not source_root.is_dir():
        raise ValueError(f"Source directory not found: {source_root}")
    if raw_root.exists() and any(raw_root.iterdir()):
        raise ValueError(f"Raw sample directory is not empty: {raw_root}")
    if manifest_path.exists():
        raise ValueError(f"Run manifest already exists: {manifest_path}")

    candidates = discover_candidates(source_root)
    selected = select_candidates(candidates, markdown_count, jsonl_count)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    write_jsonl(catalog_path, [public_record(item) for item in candidates])

    sample_units: list[dict[str, object]] = []
    for index, candidate in enumerate(selected, start=1):
        unit_id = f"unit-{index:03d}"
        extension = str(candidate["source_format"])
        copy_relative = Path("data") / "raw" / run_id / f"{unit_id}{extension}"
        target = project_root / copy_relative
        copy_candidate(candidate, target)
        copied = public_record(candidate)
        copied.update({"unit_id": unit_id, "copy_path": copy_relative.as_posix()})
        if sha256(target.read_bytes()) != candidate["sha256"]:
            raise ValueError(f"Copy hash mismatch: {copy_relative}")
        sample_units.append(copied)

    candidate_counts = Counter(str(item["sample_group"]) for item in candidates)
    sample_counts = Counter(str(item["sample_group"]) for item in selected)
    manifest: dict[str, object] = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": source_root.as_posix(),
        "catalog_path": catalog_path.relative_to(project_root).as_posix(),
        "candidate_condition": {
            "markdown": "frontmatter contains model and generated_at",
            "jsonl": f"exact source file {GENERATED_JSONL.as_posix()}",
            "text": "filename identifies raw model output and contains Korean",
        },
        "candidate_counts": dict(sorted(candidate_counts.items())),
        "sample_counts": dict(sorted(sample_counts.items())),
        "sample_size": len(sample_units),
        "selection": {
            "markdown_count": markdown_count,
            "jsonl_count": jsonl_count,
            "text_count": "all candidates",
            "method": "round-robin by source and size, then SHA-256",
        },
        "units": sample_units,
    }
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local multi-format sample of AI-generated sources."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--run-id", default="diagnostic-003")
    parser.add_argument("--markdown-count", type=int, default=30)
    parser.add_argument("--jsonl-count", type=int, default=100)
    args = parser.parse_args()
    manifest = build(
        source_root=args.source_root,
        project_root=args.project_root,
        run_id=args.run_id,
        markdown_count=args.markdown_count,
        jsonl_count=args.jsonl_count,
    )
    counts = manifest["sample_counts"]
    print(
        f"candidates={sum(manifest['candidate_counts'].values())} "  # type: ignore[union-attr]
        f"sample={manifest['sample_size']} formats={counts} run={manifest['run_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
