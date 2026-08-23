#!/usr/bin/env python
"""Build a diagnostic sample from reports with explicit model metadata."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.build_diagnostic_sample import catalog, select_sample, write_jsonl
except ModuleNotFoundError:  # Direct execution: python scripts/build_confirmed_ai_sample.py
    from build_diagnostic_sample import catalog, select_sample, write_jsonl


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    values: dict[str, str] = {}
    for line in lines[1:60]:
        if line.strip() == "---":
            return values
        if ":" not in line or line[:1].isspace():
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return {}


def confirmed_documents(source_root: Path) -> list[dict[str, object]]:
    confirmed: list[dict[str, object]] = []
    for document in catalog(source_root):
        if document["extension"] != ".md":
            continue
        path = source_root / str(document["relative_path"])
        frontmatter = parse_frontmatter(
            path.read_text(encoding="utf-8", errors="replace")
        )
        if not frontmatter.get("model") or not frontmatter.get("generated_at"):
            continue
        enriched = dict(document)
        enriched.update(
            {
                "document_type": frontmatter.get("type", "unknown"),
                "model": frontmatter["model"],
                "generated_at": frontmatter["generated_at"],
                "source_bucket": frontmatter.get("type", "unknown"),
            }
        )
        confirmed.append(enriched)
    return confirmed


def build(
    source_root: Path,
    project_root: Path,
    run_id: str,
    sample_size: int,
) -> dict[str, object]:
    source_root = source_root.resolve()
    project_root = project_root.resolve()
    catalog_path = project_root / "data" / "catalog" / "confirmed-ai-documents.jsonl"
    raw_root = project_root / "data" / "raw" / run_id
    run_root = project_root / "runs" / run_id
    manifest_path = run_root / "sample-manifest.json"

    if raw_root.exists() and any(raw_root.iterdir()):
        raise ValueError(f"Raw sample directory is not empty: {raw_root}")
    if manifest_path.exists():
        raise ValueError(f"Run manifest already exists: {manifest_path}")

    candidates = confirmed_documents(source_root)
    selected = select_sample(
        candidates,
        sample_size,
        minimum_bytes=512,
        minimum_korean_chars=500,
    )
    if len(selected) < sample_size:
        raise ValueError(
            f"Only {len(selected)} eligible documents for requested sample {sample_size}"
        )

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    write_jsonl(catalog_path, candidates)

    sample_documents: list[dict[str, object]] = []
    for index, document in enumerate(selected, start=1):
        document_id = f"doc-{index:03d}"
        copy_relative = Path("data") / "raw" / run_id / f"{document_id}.md"
        shutil.copyfile(
            source_root / str(document["relative_path"]),
            project_root / copy_relative,
        )
        copied = dict(document)
        copied.update(
            {
                "document_id": document_id,
                "copy_path": copy_relative.as_posix(),
            }
        )
        sample_documents.append(copied)

    manifest: dict[str, object] = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": source_root.as_posix(),
        "candidate_condition": "frontmatter contains model and generated_at",
        "candidate_documents": len(candidates),
        "catalog_path": catalog_path.relative_to(project_root).as_posix(),
        "sample_size": len(sample_documents),
        "selection": {
            "method": "round-robin by frontmatter type and size bucket",
            "minimum_bytes": 512,
            "minimum_korean_chars": 500,
            "order_within_stratum": "sha256 then relative path",
        },
        "documents": sample_documents,
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
        description="Build a sample of final Markdown reports with model metadata."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--run-id", default="diagnostic-002")
    parser.add_argument("--sample-size", type=int, default=20)
    args = parser.parse_args()

    manifest = build(
        source_root=args.source_root,
        project_root=args.project_root,
        run_id=args.run_id,
        sample_size=args.sample_size,
    )
    print(
        f"candidates={manifest['candidate_documents']} "
        f"sample={manifest['sample_size']} run={manifest['run_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
