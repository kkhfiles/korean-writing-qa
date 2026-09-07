#!/usr/bin/env python
"""Preview or capture Korean writing feedback without activating a rule."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import check


DEFAULT_QA_ROOT = Path(
    os.environ.get("KOREAN_WRITING_QA_HOME", "P:/github/korean-writing-qa")
)
DEFAULT_CANDIDATES = DEFAULT_QA_ROOT / "data" / "feedback" / "candidates.jsonl"
HUMAN_SOURCES = {"user_direct", "user_accept", "human_review"}
CONTEXT_LEVELS = {"sentence", "window", "block", "document"}
VERDICTS = {"observed", "corrected", "accepted", "false_positive"}
DECISION_SOURCES = {*HUMAN_SOURCES, "model_candidate"}


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def validate_candidate(candidate: dict[str, object]) -> list[str]:
    errors: list[str] = []
    verdict = str(candidate.get("user_verdict", ""))
    decision_source = str(candidate.get("decision_source", ""))
    context_level = str(candidate.get("context_level", ""))
    original = str(candidate.get("original", ""))
    revised = str(candidate.get("revised", ""))

    for field in ("candidate_id", "rule_id", "original", "scope", "category"):
        if not candidate.get(field):
            errors.append(f"missing {field}")
    if str(candidate.get("detector", "literal")) == "regex":
        if not candidate.get("pattern"):
            errors.append("a regex candidate needs a pattern")
        else:
            probe = dict(candidate)
            try:
                check.compile_rule(probe, 0)
            except ValueError as error:
                errors.append(str(error))
            else:
                # 관찰한 표현을 못 잡는 패턴은 규칙이 아니라 오타다. 기록 단계에서 막는다.
                if original and not check.rule_matches(probe, original):
                    errors.append(
                        f"pattern does not match the observed expression: {original}"
                    )
    errors.extend(check.allow_example_errors(candidate))
    if verdict not in VERDICTS:
        errors.append(f"invalid user_verdict: {verdict}")
    if decision_source not in DECISION_SOURCES:
        errors.append(f"invalid decision_source: {decision_source}")
    if context_level not in CONTEXT_LEVELS:
        errors.append(f"invalid context_level: {context_level}")
    if verdict in {"corrected", "accepted"}:
        if not revised:
            errors.append("revised text is required for corrected or accepted feedback")
        elif original == revised:
            errors.append("original and revised expressions must differ")
    if decision_source == "model_candidate" and verdict != "observed":
        errors.append("model_candidate must use the observed verdict")
    if context_level == "window" and not (
        candidate.get("context_before") or candidate.get("context_after")
    ):
        errors.append("window context requires context_before or context_after")
    if context_level == "block" and not (
        candidate.get("section_title") or candidate.get("logical_path")
    ):
        errors.append("block context requires section_title or logical_path")
    if context_level == "document" and not (
        candidate.get("source_ref") and candidate.get("source_hash")
    ):
        errors.append("document context requires source_ref and source_hash")
    return errors


def build_candidate(args: argparse.Namespace) -> dict[str, object]:
    profile = getattr(args, "profile", None)
    scope = check.PROFILE_SCOPES[profile] if profile else args.scope
    category = args.category or (
        "MODEL_OBSERVED_EXPRESSION"
        if args.decision_source == "model_candidate"
        else "USER_CONFIRMED_EXPRESSION"
    )
    status = (
        "confirmed"
        if args.decision_source in HUMAN_SOURCES
        and args.user_verdict in {"corrected", "accepted", "false_positive"}
        else "observed"
    )
    candidate: dict[str, object] = {
        "candidate_id": args.candidate_id,
        "record_kind": "language_rule",
        "rule_id": args.rule_id,
        "original": args.original,
        "revised": args.revised or "",
        "scope": scope,
        "category": category,
        "context_level": args.context_level,
        "decision_source": args.decision_source,
        "user_verdict": args.user_verdict,
        "status": status,
        "replacement_mode": (
            "contextual_rewrite"
            if args.contextual or args.context_level != "sentence"
            else "exact_suggestion"
        ),
        "requires_context": args.requires_context or args.context_level != "sentence",
    }
    if profile:
        candidate["profile"] = profile
    if getattr(args, "pattern", None):
        candidate["detector"] = "regex"
        candidate["pattern"] = args.pattern
        candidate["replacement_mode"] = "contextual_rewrite"
        candidate["requires_context"] = True
    if getattr(args, "allow", None):
        candidate["allow"] = list(dict.fromkeys(args.allow))
    if getattr(args, "allow_example", None):
        candidate["allow_examples"] = list(args.allow_example)
    optional_fields = (
        "context_before",
        "context_after",
        "context_excerpt",
        "section_title",
        "logical_path",
        "source_ref",
        "source_hash",
        "note",
    )
    for field in optional_fields:
        value = getattr(args, field)
        if value:
            candidate[field] = value
    return candidate


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--rule-id", required=True)
    parser.add_argument("--original", required=True)
    parser.add_argument("--revised")
    scope_group = parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument("--profile", choices=sorted(check.PROFILE_SCOPES))
    scope_group.add_argument(
        "--scope", choices=sorted(set(check.PROFILE_SCOPES.values()))
    )
    parser.add_argument(
        "--pattern",
        help="정규식으로 찾을 형태. 주면 정규식 규칙이 된다. 관찰한 표현을 실제로 잡아야 한다.",
    )
    parser.add_argument(
        "--allow",
        action="append",
        default=[],
        metavar="정규식",
        help="이 형태로 나오면 지적하지 않는다. 오탐을 규칙에 되먹이는 통로다.",
    )
    parser.add_argument(
        "--allow-example",
        action="append",
        default=[],
        metavar="문장",
        help="허용 형태의 실제 예문. 회귀 시료가 된다. --allow 와 같은 순서로 적는다.",
    )
    parser.add_argument("--category")
    parser.add_argument("--decision-source", choices=sorted(DECISION_SOURCES), required=True)
    parser.add_argument("--user-verdict", choices=sorted(VERDICTS), required=True)
    parser.add_argument("--context-level", choices=sorted(CONTEXT_LEVELS), default="sentence")
    parser.add_argument("--context-before")
    parser.add_argument("--context-after")
    parser.add_argument("--context-excerpt")
    parser.add_argument("--section-title")
    parser.add_argument("--logical-path")
    parser.add_argument("--source-ref")
    parser.add_argument("--source-hash")
    parser.add_argument("--contextual", action="store_true")
    parser.add_argument("--requires-context", action="store_true")
    parser.add_argument("--note")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = make_parser().parse_args()
    candidate = build_candidate(args)
    errors = validate_candidate(candidate)
    existing = read_jsonl(args.candidates)
    if any(row.get("candidate_id") == args.candidate_id for row in existing):
        errors.append(f"duplicate candidate_id: {args.candidate_id}")

    result = {
        "applied": False,
        "candidate": candidate,
        "errors": errors,
    }
    if errors:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    try:
        write_jsonl(args.candidates, [*existing, candidate])
    except OSError as error:
        result["errors"] = [f"candidate write failed: {error}"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1
    result["applied"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
