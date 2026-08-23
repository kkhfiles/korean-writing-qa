#!/usr/bin/env python
"""Build a reproducible local document catalog and diagnostic sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path


TEXT_EXTENSIONS = {".md", ".html", ".txt"}
KOREAN = re.compile(r"[가-힣]")


def size_bucket(size: int) -> str:
    if size < 4 * 1024:
        return "small"
    if size < 20 * 1024:
        return "medium"
    return "large"


def top_bucket(relative_path: Path) -> str:
    return relative_path.parts[0] if len(relative_path.parts) > 1 else "_root"


def catalog(source_root: Path) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        relative = path.relative_to(source_root)
        stat = path.stat()
        documents.append(
            {
                "relative_path": relative.as_posix(),
                "extension": path.suffix.lower(),
                "bytes": stat.st_size,
                "modified_utc": datetime.fromtimestamp(
                    stat.st_mtime, timezone.utc
                ).isoformat(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "line_count": len(text.splitlines()),
                "korean_chars": len(KOREAN.findall(text)),
                "source_bucket": top_bucket(relative),
                "size_bucket": size_bucket(stat.st_size),
            }
        )
    return documents


def select_sample(
    documents: list[dict[str, object]],
    sample_size: int,
    minimum_bytes: int = 512,
    minimum_korean_chars: int = 200,
) -> list[dict[str, object]]:
    strata: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for document in documents:
        if int(document["bytes"]) < minimum_bytes:
            continue
        if int(document["korean_chars"]) < minimum_korean_chars:
            continue
        key = (str(document["source_bucket"]), str(document["size_bucket"]))
        strata[key].append(document)

    queues: dict[tuple[str, str], deque[dict[str, object]]] = {}
    for key, values in strata.items():
        ordered = sorted(
            values,
            key=lambda item: (str(item["sha256"]), str(item["relative_path"])),
        )
        queues[key] = deque(ordered)

    selected: list[dict[str, object]] = []
    keys = sorted(queues)
    while len(selected) < sample_size:
        progressed = False
        for key in keys:
            if not queues[key]:
                continue
            selected.append(queues[key].popleft())
            progressed = True
            if len(selected) == sample_size:
                break
        if not progressed:
            break
    return selected


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def build(
    source_root: Path,
    project_root: Path,
    run_id: str,
    sample_size: int,
) -> dict[str, object]:
    source_root = source_root.resolve()
    project_root = project_root.resolve()
    catalog_path = project_root / "data" / "catalog" / "documents.jsonl"
    raw_root = project_root / "data" / "raw" / run_id
    run_root = project_root / "runs" / run_id
    manifest_path = run_root / "sample-manifest.json"

    if not source_root.is_dir():
        raise ValueError(f"Source directory not found: {source_root}")
    if raw_root.exists() and any(raw_root.iterdir()):
        raise ValueError(f"Raw sample directory is not empty: {raw_root}")
    if manifest_path.exists():
        raise ValueError(f"Run manifest already exists: {manifest_path}")

    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    raw_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)

    documents = catalog(source_root)
    selected = select_sample(documents, sample_size)
    if len(selected) < sample_size:
        raise ValueError(
            f"Only {len(selected)} eligible documents for requested sample {sample_size}"
        )

    sample_documents: list[dict[str, object]] = []
    for index, document in enumerate(selected, start=1):
        extension = str(document["extension"])
        document_id = f"doc-{index:03d}"
        copy_relative = Path("data") / "raw" / run_id / f"{document_id}{extension}"
        source = source_root / str(document["relative_path"])
        target = project_root / copy_relative
        shutil.copyfile(source, target)
        copied = dict(document)
        copied.update(
            {
                "document_id": document_id,
                "copy_path": copy_relative.as_posix(),
            }
        )
        sample_documents.append(copied)

    write_jsonl(catalog_path, documents)
    manifest: dict[str, object] = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_root": source_root.as_posix(),
        "catalog_path": catalog_path.relative_to(project_root).as_posix(),
        "catalog_documents": len(documents),
        "sample_size": len(sample_documents),
        "selection": {
            "method": "round-robin by source bucket and size bucket",
            "minimum_bytes": 512,
            "minimum_korean_chars": 200,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Catalog local documents and copy a deterministic diagnostic sample."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--run-id", default="diagnostic-001")
    parser.add_argument("--sample-size", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build(
        source_root=args.source_root,
        project_root=args.project_root,
        run_id=args.run_id,
        sample_size=args.sample_size,
    )
    print(
        f"catalog={manifest['catalog_documents']} sample={manifest['sample_size']} "
        f"run={manifest['run_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
