#!/usr/bin/env python
"""Promote one human-confirmed feedback candidate into active rules and tests."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import check

from record_feedback import (
    DEFAULT_CANDIDATES,
    DEFAULT_QA_ROOT,
    HUMAN_SOURCES,
    read_jsonl,
    write_jsonl,
)


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = SKILL_ROOT / "references" / "confirmed-rules.jsonl"
DEFAULT_CASES = SKILL_ROOT / "references" / "regression-cases.jsonl"
DEFAULT_CONTEXT_CASES = SKILL_ROOT / "references" / "context-cases.jsonl"
DEFAULT_QA_RULES = DEFAULT_QA_ROOT / "data" / "annotations" / "user-confirmed-phrases.jsonl"
DEFAULT_QA_CASES = DEFAULT_QA_ROOT / "data" / "regression" / "detector-cases.jsonl"
DEFAULT_QA_MANIFEST = DEFAULT_QA_ROOT / "data" / "regression" / "corpus-sources.json"
SELF_TEST = Path(__file__).with_name("self_test.py")


def case_prefix(candidate_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", candidate_id).strip("-").upper()
    return f"FEEDBACK-{normalized}"


def build_rule(candidate: dict[str, object]) -> dict[str, object]:
    rule: dict[str, object] = {
        "annotation_id": candidate["candidate_id"],
        "rule_id": candidate["rule_id"],
        "category": candidate["category"],
        "original": candidate["original"],
        "revised": candidate["revised"],
        "human_label": "revise",
        "status": "user_confirmed",
        "scope": candidate["scope"],
        "replacement_mode": candidate["replacement_mode"],
        "requires_context": candidate["requires_context"],
        "context_level": candidate["context_level"],
        "decision_source": candidate["decision_source"],
    }
    if candidate.get("note"):
        rule["context_note"] = candidate["note"]
    if candidate.get("profile"):
        rule["profiles"] = [candidate["profile"]]
    if str(candidate.get("detector", "literal")) == "regex":
        rule["detector"] = "regex"
        rule["pattern"] = candidate["pattern"]
    if candidate.get("allow"):
        rule["allow"] = list(candidate["allow"])  # type: ignore[arg-type]
    for field in (
        "context_before",
        "context_after",
        "context_excerpt",
        "section_title",
        "logical_path",
        "source_ref",
        "source_hash",
    ):
        if candidate.get(field):
            rule[field] = candidate[field]
    return rule


def build_cases(candidate: dict[str, object]) -> list[dict[str, object]]:
    prefix = case_prefix(str(candidate["candidate_id"]))
    original = str(candidate["original"])
    revised = str(candidate.get("revised") or "")
    scope = str(candidate["scope"])
    action = (
        "review_context"
        if candidate["replacement_mode"] == "contextual_rewrite"
        or candidate["requires_context"]
        else "suggest_exact"
    )
    provenance = str(candidate["candidate_id"])
    cases: list[dict[str, object]] = [
        {
            "case_id": f"{prefix}-P",
            "detector": "user_feedback",
            "rule_id": candidate["rule_id"],
            "variant": "positive",
            "input_scope": scope,
            "text": original,
            "expected": "finding",
            "expected_action": action,
            "provenance": provenance,
        },
    ]
    # 정규식 규칙은 고칠 문구가 하나로 정해지지 않는다. 권장문·교육용 시료는 그
    # 문구가 있을 때만 만든다. 없는데 빈 문자열로 만들면 아무것도 안 지키는 시료가 된다.
    if revised:
        cases.append({
            "case_id": f"{prefix}-N",
            "detector": "user_feedback",
            "rule_id": candidate["rule_id"],
            "variant": "preferred",
            "input_scope": scope,
            "text": revised,
            "expected": "no_finding",
            "provenance": provenance,
        })
        cases.append({
            "case_id": f"{prefix}-T",
            "detector": "user_feedback",
            "rule_id": candidate["rule_id"],
            "variant": "teaching",
            "input_scope": scope,
            "text": f"❌ {original} → ✅ {revised}",
            "expected": "no_finding",
            "provenance": provenance,
        })
    # 허용 형태를 등록했으면 그것이 실제로 넘어가는지도 시료로 남긴다. 예문이 없으면
    # 만들지 않는다 — 정규식 문자열을 본문으로 쓰면 허용 형태와 안 맞는 시료가 된다.
    # 예문이 모자란 것은 `check.allow_example_errors` 가 따로 막는다.
    for index, text in enumerate(candidate.get("allow_examples") or [], 1):
        cases.append({
            "case_id": f"{prefix}-A{index}",
            "detector": "user_feedback",
            "rule_id": candidate["rule_id"],
            "variant": "allowed",
            "input_scope": scope,
            "text": text,
            "expected": "no_finding",
            "provenance": provenance,
        })
    profile = candidate.get("profile")
    if profile:
        for other_profile, other_scope in sorted(check.PROFILE_SCOPES.items()):
            if other_profile == profile:
                continue
            cases.append(
                {
                    "case_id": f"{prefix}-X-{other_profile.upper()}",
                    "detector": "user_feedback",
                    "rule_id": candidate["rule_id"],
                    "variant": "cross_profile",
                    "input_scope": other_scope,
                    "input_profile": other_profile,
                    "text": original,
                    "expected": "no_finding",
                    "provenance": provenance,
                }
            )
    elif scope != "general_it_business":
        cases.append(
            {
                "case_id": f"{prefix}-X",
                "detector": "user_feedback",
                "rule_id": candidate["rule_id"],
                "variant": "cross_scope",
                "input_scope": "general_it_business",
                "text": original,
                "expected": "no_finding",
                "provenance": provenance,
            }
        )
    expected_rule_context = {
        field: candidate[field]
        for field in (
            "context_level",
            "context_before",
            "context_after",
            "context_excerpt",
            "section_title",
            "logical_path",
            "source_ref",
            "source_hash",
        )
        if candidate.get(field)
    }
    if expected_rule_context:
        cases[0]["expected_rule_context"] = expected_rule_context
    if profile:
        cases[0]["expected_rule_context"] = {
            **cases[0].get("expected_rule_context", {}),
            "profiles": [profile],
        }
    for case in cases[:3]:
        if profile:
            case["input_profile"] = profile
    return cases


def promotion_errors(
    candidate: dict[str, object],
    rules: list[dict[str, object]],
    cases: list[dict[str, object]],
) -> list[str]:
    errors: list[str] = []
    required = (
        "candidate_id",
        "rule_id",
        "category",
        "original",
        "revised",
        "scope",
        "replacement_mode",
        "requires_context",
        "context_level",
        "decision_source",
        "user_verdict",
        "status",
    )
    missing = [field for field in required if field not in candidate]
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")
        return errors
    if candidate.get("record_kind") != "language_rule":
        errors.append("only language_rule candidates can be promoted")
    if candidate.get("decision_source") not in HUMAN_SOURCES:
        errors.append("a human decision source is required")
    if candidate.get("user_verdict") not in {"corrected", "accepted"}:
        errors.append("only corrected or accepted feedback can become an active rule")
    if candidate.get("status") != "confirmed":
        errors.append("candidate status must be confirmed")

    # 정규식 규칙은 고칠 문구가 하나로 정해지지 않는다. 대신 패턴이 실제로 컴파일되고
    # 관찰된 표현을 실제로 잡는지 확인한다 — 안 잡는 패턴은 규칙이 아니라 오타다.
    if str(candidate.get("detector", "literal")) == "regex":
        if not candidate.get("pattern"):
            errors.append("a regex rule needs a pattern")
        else:
            probe = {**candidate, "detector": "regex"}
            try:
                check.compile_rule(probe, 0)
            except ValueError as error:
                errors.append(str(error))
            else:
                observed = str(candidate.get("original") or "")
                if observed and not check.rule_matches(probe, observed):
                    errors.append(
                        f"pattern does not match the observed expression: {observed}"
                    )
    elif not candidate.get("revised") or candidate.get("original") == candidate.get("revised"):
        errors.append("a distinct revised expression is required")
    errors.extend(check.allow_example_errors(candidate))

    candidate_key = check.rule_key({
        "detector": candidate.get("detector", "literal"),
        "original": candidate.get("original"),
        "pattern": candidate.get("pattern"),
    })
    for rule in rules:
        if rule.get("annotation_id") == candidate.get("candidate_id"):
            errors.append(f"duplicate annotation_id: {candidate['candidate_id']}")
        if rule.get("rule_id") == candidate.get("rule_id"):
            errors.append(f"duplicate rule_id: {candidate['rule_id']}")
        if check.rule_key(rule) == candidate_key:
            errors.append(f"duplicate rule target: {candidate_key}")

    existing_case_ids = {str(row["case_id"]) for row in cases}
    duplicate_case_ids = sorted(
        str(row["case_id"])
        for row in build_cases(candidate)
        if str(row["case_id"]) in existing_case_ids
    )
    if duplicate_case_ids:
        errors.append(f"duplicate case_id: {', '.join(duplicate_case_ids)}")
    return errors


def mirror_errors(
    rules: list[dict[str, object]],
    cases: list[dict[str, object]],
    qa_rules: list[dict[str, object]],
    qa_cases: list[dict[str, object]],
    manifest: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    if rules != qa_rules:
        errors.append("runtime rules and QA rule mirror differ")
    if cases != qa_cases:
        errors.append("runtime cases and QA case mirror differ")
    detector = manifest.get("detector_cases")
    if not isinstance(detector, dict) or detector.get("expected_count") != len(cases):
        errors.append("QA detector case count manifest is out of sync")
    rewrite_pairs = manifest.get("human_rewrite_pairs")
    user_pair = next(
        (
            row
            for row in rewrite_pairs
            if isinstance(row, dict)
            and row.get("path") == "data/annotations/user-confirmed-phrases.jsonl"
        ),
        None,
    ) if isinstance(rewrite_pairs, list) else None
    if not isinstance(user_pair, dict) or user_pair.get("expected_count") != len(rules):
        errors.append("QA user feedback count manifest is out of sync")
    return errors


def update_manifest_counts(
    manifest: dict[str, object],
    rule_count: int,
    case_count: int,
) -> dict[str, object]:
    updated = json.loads(json.dumps(manifest))
    updated["detector_cases"]["expected_count"] = case_count
    for row in updated["human_rewrite_pairs"]:
        if row.get("path") == "data/annotations/user-confirmed-phrases.jsonl":
            row["expected_count"] = rule_count
            break
    return updated


def write_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def restore(path: Path, content: bytes | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(path.suffix + ".rollback")
    temporary.write_bytes(content)
    temporary.replace(path)


def run_self_test(args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(SELF_TEST),
            "--rules",
            str(args.rules),
            "--cases",
            str(args.cases),
            "--context-cases",
            str(args.context_cases),
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=60,
        check=False,
    )


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--context-cases", type=Path, default=DEFAULT_CONTEXT_CASES)
    parser.add_argument("--qa-rules", type=Path, default=DEFAULT_QA_RULES)
    parser.add_argument("--qa-cases", type=Path, default=DEFAULT_QA_CASES)
    parser.add_argument("--qa-manifest", type=Path, default=DEFAULT_QA_MANIFEST)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = make_parser().parse_args()
    candidates = read_jsonl(args.candidates)
    matches = [row for row in candidates if row.get("candidate_id") == args.candidate_id]
    if len(matches) != 1:
        print(json.dumps({
            "applied": False,
            "errors": [f"candidate_id matched {len(matches)} records: {args.candidate_id}"],
        }, ensure_ascii=False, indent=2))
        return 2

    candidate = matches[0]
    rules = read_jsonl(args.rules)
    cases = read_jsonl(args.cases)
    qa_rules = read_jsonl(args.qa_rules)
    qa_cases = read_jsonl(args.qa_cases)
    manifest = json.loads(args.qa_manifest.read_text(encoding="utf-8"))
    errors = [
        *promotion_errors(candidate, rules, cases),
        *mirror_errors(rules, cases, qa_rules, qa_cases, manifest),
    ]
    preview = {
        "applied": False,
        "promotion_ready": not errors,
        "candidate_id": args.candidate_id,
        "errors": errors,
    }
    if not args.apply or errors:
        if not errors:
            preview["rule"] = build_rule(candidate)
            preview["regression_cases"] = build_cases(candidate)
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0 if not errors else 2

    rule = build_rule(candidate)
    new_cases = build_cases(candidate)
    preview["rule"] = rule
    preview["regression_cases"] = new_cases
    updated_rules = [*rules, rule]
    updated_cases = [*cases, *new_cases]
    updated_manifest = update_manifest_counts(
        manifest,
        rule_count=len(updated_rules),
        case_count=len(updated_cases),
    )
    original_content = {
        path: path.read_bytes() if path.exists() else None
        for path in (
            args.rules,
            args.cases,
            args.candidates,
            args.qa_rules,
            args.qa_cases,
            args.qa_manifest,
        )
    }
    updated_candidates = [
        {**row, "status": "active"}
        if row.get("candidate_id") == args.candidate_id
        else row
        for row in candidates
    ]
    try:
        write_jsonl(args.rules, updated_rules)
        write_jsonl(args.cases, updated_cases)
        write_jsonl(args.qa_rules, updated_rules)
        write_jsonl(args.qa_cases, updated_cases)
        write_json(args.qa_manifest, updated_manifest)
        write_jsonl(args.candidates, updated_candidates)
        post_write_mirror_errors = mirror_errors(
            updated_rules,
            updated_cases,
            read_jsonl(args.qa_rules),
            read_jsonl(args.qa_cases),
            json.loads(args.qa_manifest.read_text(encoding="utf-8")),
        )
        if post_write_mirror_errors:
            raise RuntimeError("; ".join(post_write_mirror_errors))
        test_result = run_self_test(args)
        if test_result.returncode != 0:
            raise RuntimeError(test_result.stdout.strip() or test_result.stderr.strip())
        test_summary = json.loads(test_result.stdout)
    except Exception as error:
        for path, content in original_content.items():
            restore(path, content)
        print(json.dumps({
            **preview,
            "rolled_back": True,
            "errors": [*errors, f"regression test failed: {error}"],
        }, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({
        **preview,
        "applied": True,
        "promotion_ready": True,
        "qa_mirror_updated": True,
        "self_test": test_summary,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
