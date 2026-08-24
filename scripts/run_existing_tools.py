#!/usr/bin/env python
"""Run installed Korean writing checkers on one diagnostic sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DOC_STYLE_TOTAL = re.compile(
    r"합계\s*—\s*오류\s*(\d+)\s*·\s*주의\s*(\d+)(?:\s*·\s*검사 불가\s*(\d+))?"
)
VALUE_SLOTS = re.compile(r"값 슬롯\s*(\d+)")


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_input_hash(path: Path, declared_sha256: str) -> str:
    actual_sha256 = hash_file(path)
    if actual_sha256 != declared_sha256:
        raise ValueError(
            f"Input hash mismatch for {path}: "
            f"manifest={declared_sha256} actual={actual_sha256}"
        )
    return actual_sha256


def parse_doc_style(output: str) -> dict[str, int]:
    match = DOC_STYLE_TOTAL.search(output)
    if not match:
        raise ValueError("doc-style-check summary not found")
    slots = [int(value) for value in VALUE_SLOTS.findall(output)]
    return {
        "errors": int(match.group(1)),
        "warnings": int(match.group(2)),
        "blind": int(match.group(3) or 0),
        "value_slots": sum(slots),
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def run(
    project_root: Path,
    manifest_path: Path,
    doc_style_path: Path,
    metrics_path: Path,
    baseline_path: Path,
    baseline_v2_path: Path,
    genre: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    project_root = project_root.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_id = str(manifest["run_id"])
    run_root = project_root / "runs" / run_id
    raw_root = run_root / "raw"
    raw_doc_style = raw_root / "doc-style"
    raw_humanize = raw_root / "humanize"
    raw_doc_style.mkdir(parents=True, exist_ok=True)
    raw_humanize.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    for document in manifest["documents"]:
        document_id = str(document["document_id"])
        input_path = project_root / str(document["copy_path"])
        extension = input_path.suffix.lower()
        input_sha256 = verify_input_hash(input_path, str(document["sha256"]))
        result: dict[str, object] = {
            "document_id": document_id,
            "source_relative_path": document["relative_path"],
            "extension": extension,
            "sha256": input_sha256,
        }

        if extension in {".md", ".html"}:
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", str(doc_style_path), str(input_path), "-v"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
            raw_path = raw_doc_style / f"{document_id}.txt"
            raw_path.write_text(
                completed.stdout + ("\n[stderr]\n" + completed.stderr if completed.stderr else ""),
                encoding="utf-8",
            )
            parsed = parse_doc_style(completed.stdout)
            parsed.update({"status": "scanned", "return_code": completed.returncode})
            result["doc_style"] = parsed
        else:
            result["doc_style"] = {"status": "unsupported_extension"}

        humanize_output = raw_humanize / f"{document_id}.json"
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-X",
                "utf8",
                str(metrics_path),
                "--input",
                str(input_path),
                "--genre",
                genre,
                "--output",
                str(humanize_output),
                "--baseline",
                str(baseline_path),
                "--baseline-v2",
                str(baseline_v2_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if completed.returncode != 0 or not humanize_output.exists():
            raise RuntimeError(
                f"humanize metrics failed for {document_id}: "
                f"rc={completed.returncode} stderr={completed.stderr.strip()}"
            )
        metrics = json.loads(humanize_output.read_text(encoding="utf-8"))
        result["humanize"] = {
            "status": "scanned",
            "return_code": completed.returncode,
            "risk_band": metrics.get("risk_band"),
            "baseline_warning": metrics.get("warning"),
            "v2_baseline_warnings": metrics.get("v2_baseline_warnings", []),
            "metrics": metrics.get("metrics", {}),
            "v2_metrics": metrics.get("v2_metrics", {}),
            "v2_interference_index": metrics.get("v2_interference_index", {}),
        }
        results.append(result)

    doc_style_results = [
        item["doc_style"]
        for item in results
        if item["doc_style"].get("status") == "scanned"
    ]
    humanize_results = [item["humanize"] for item in results]
    summary: dict[str, object] = {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sample_documents": len(results),
        "tools": {
            "doc_style_check": {
                "path": doc_style_path.resolve().as_posix(),
                "sha256": hash_file(doc_style_path),
            },
            "humanize_metrics_v2": {
                "path": metrics_path.resolve().as_posix(),
                "sha256": hash_file(metrics_path),
                "baseline_sha256": hash_file(baseline_path),
                "baseline_v2_sha256": hash_file(baseline_v2_path),
                "genre": genre,
            },
        },
        "doc_style": {
            "scanned_documents": len(doc_style_results),
            "unsupported_documents": len(results) - len(doc_style_results),
            "documents_with_errors": sum(int(item["errors"]) > 0 for item in doc_style_results),
            "documents_with_warnings": sum(int(item["warnings"]) > 0 for item in doc_style_results),
            "errors": sum(int(item["errors"]) for item in doc_style_results),
            "warnings": sum(int(item["warnings"]) for item in doc_style_results),
            "blind": sum(int(item["blind"]) for item in doc_style_results),
        },
        "humanize": {
            "scanned_documents": len(humanize_results),
            "risk_bands": dict(
                sorted(Counter(str(item["risk_band"]) for item in humanize_results).items())
            ),
            "documents_with_v1_baseline_warning": sum(
                bool(item["baseline_warning"]) for item in humanize_results
            ),
            "documents_with_v2_placeholder_warning": sum(
                bool(item["v2_baseline_warnings"]) for item in humanize_results
            ),
        },
        "interpretation": "raw tool output only; no human ground-truth labels yet",
    }
    return results, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run installed writing checkers on a sample.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--doc-style", required=True, type=Path)
    parser.add_argument("--metrics-v2", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--baseline-v2", required=True, type=Path)
    parser.add_argument("--genre", default="qa")
    args = parser.parse_args()

    results, summary = run(
        project_root=args.project_root,
        manifest_path=args.manifest,
        doc_style_path=args.doc_style,
        metrics_path=args.metrics_v2,
        baseline_path=args.baseline,
        baseline_v2_path=args.baseline_v2,
        genre=args.genre,
    )
    run_root = args.project_root.resolve() / "runs" / str(summary["run_id"])
    write_jsonl(run_root / "existing-tools-results.jsonl", results)
    write_json(run_root / "existing-tools-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
