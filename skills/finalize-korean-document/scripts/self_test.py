#!/usr/bin/env python
"""Run bundled detector and meaning-preservation regression assertions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import check
import check_meaning
import promote_feedback
import record_feedback


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RULES = SKILL_ROOT / "references" / "confirmed-rules.jsonl"
DEFAULT_CASES = SKILL_ROOT / "references" / "regression-cases.jsonl"
DEFAULT_CONTEXT_CASES = SKILL_ROOT / "references" / "context-cases.jsonl"
CONTEXT_LEVELS = {"sentence", "window", "block", "document"}


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def run_meaning_marker_assertions() -> tuple[int, int, list[str]]:
    """뜻을 지탱하는 표지가 사라진 것을 알리는지 검사한다.

    낱말 대조만으로는 인과·조건·계획 상태가 사라져도 통과한다. 실제로
    「최초 실행 보고서로 재평가 대상 없음」을 「최초 실행 보고서 · 재평가 대상
    없음」으로 줄인 수정이 `preserved` 로 나왔고 사용자는 맥락 소실로 판정했다.

    **막지 않고 알리기만 한다** — 좋은 수정에서도 8%가 걸리므로 상태를 바꾸면
    정상 수정이 멈춘다. 그래서 상태가 그대로인지도 함께 확인한다.
    """
    failures: list[str] = []
    passed = 0

    # (이름, 수정 전, 수정 후, 걸려야 하는 표지 · None 이면 조용해야 함)
    cases = [
        ("인과 소실", "측정값이 낮으므로 폐기한다", "폐기한다", "인과·조건"),
        ("조건 소실", "코드가 바뀌면 다시 돌린다", "다시 돌린다", "인과·조건"),
        ("계획을 완료로", "커버리지를 올릴 예정입니다", "커버리지를 올렸습니다", "계획·진행"),
        ("부정 뒤집기", "이 기능은 지원하지 않는다", "이 기능은 지원한다", "부정·범위"),
        ("추정을 단정으로", "원인일 가능성이 있다", "원인이다", "추정·유보"),
        ("주체 생략", "개발팀이 검토한다", "검토한다", "행위 주체"),
        ("낱말만 바꿈", "제품화 경로를 검토한다", "제품화 단계를 검토한다", None),
        ("자평 제거", "강력한 검증 엔진을 도입한다", "검증 엔진을 도입한다", None),
        ("개조식화", "검토를 수행하였습니다", "검토 수행", None),
        ("면이 낱말 안에", "여러 측면을 검토한다", "여러 관점을 검토한다", None),
        ("주어 유지", "개발팀이 검토한다", "개발팀이 확인한다", None),
    ]
    for name, before, after, expected in cases:
        drops = {str(d["marker"]) for d in check_meaning.marker_drops(before, after)}
        if expected is None and drops:
            failures.append(f"meaning_marker/{name}: 조용해야 하는데 {sorted(drops)}")
        elif expected is not None and expected not in drops:
            failures.append(f"meaning_marker/{name}: {expected} 를 못 잡음 {sorted(drops)}")
        else:
            passed += 1

    # 이 한 건이 표지를 넣은 이유다 — 낱말은 하나도 안 사라져서 상태는 `preserved`
    # 인데 인과와 주어가 통째로 없어졌다. 상태를 바꾸지 않고 그 사실만 알린다.
    reported = check_meaning.measure("측정값이 낮으므로 폐기한다", "폐기한다", [])
    dropped = {str(d["marker"]) for d in reported["meaning_marker_drops"]}
    if reported["status"] != "preserved" or "인과·조건" not in dropped:
        failures.append(
            f"meaning_marker/보고 전용: status={reported['status']} drops={sorted(dropped)}"
        )
    else:
        passed += 1

    kept = check_meaning.measure("제품화 경로를 검토한다", "제품화 단계를 검토한다", [])
    if kept["status"] != "preserved" or kept["meaning_marker_drops"]:
        failures.append("meaning_marker/대조군: 정상 수정이 걸림")
    else:
        passed += 1

    return len(cases) + 2, passed, failures


def run_detector_format_assertions() -> tuple[int, int, list[str]]:
    """정규식 규칙과 허용 목록을 검사한다.

    허용 목록은 사용자가 오탐이라고 판정한 것을 규칙에 되먹이는 통로다. 이것이
    없으면 오탐은 기록만 되고 검사기는 그대로라 같은 지적이 계속 나온다.
    """
    failures: list[str] = []
    passed = 0

    def rule(**updates: object) -> dict[str, object]:
        record: dict[str, object] = {
            "annotation_id": "format-case",
            "rule_id": "KOR-FORMAT-CASE",
            "detector": "regex",
            "pattern": "겹치는\\s*자리",
            "revised": "",
            "scope": "general_it_business",
            "category": "TEST",
            "replacement_mode": "contextual_rewrite",
            "requires_context": True,
        }
        record.update(updates)
        check.compile_rule(record, 1)
        return record

    def hits(record: dict[str, object], line: str) -> int:
        return len(check.scan_text(line, [record], "general_it_business"))

    plain = rule()
    allowed = rule(allow=["의견을\\s*받는\\s*자리"], pattern="자리")
    literal_allowed = rule(
        detector="literal", original="경로", revised="단계", allow=["파일\\s*경로"]
    )

    assertions = [
        ("regex rule finds its pattern", hits(plain, "규칙이 겹치는 자리를 본다") == 1),
        ("regex rule ignores unrelated text", hits(plain, "규칙이 겹치는 위치를 본다") == 0),
        (
            "allow list clears a legitimate use",
            hits(allowed, "의견을 받는 자리를 마련한다") == 0,
        ),
        (
            "allow list does not clear the whole line",
            hits(allowed, "의견을 받는 자리 뒤에 겹치는 자리가 남는다") == 1,
        ),
        (
            "allow list works for literal rules too",
            hits(literal_allowed, "파일 경로를 확인한다") == 0
            and hits(literal_allowed, "제품화 경로를 검토한다") == 1,
        ),
        (
            "regex findings report the matched text, not the pattern",
            (lambda found: bool(found) and found[0]["original"] == "겹치는 자리")(
                check.scan_text("규칙이 겹치는 자리를 본다", [plain], "general_it_business")
            ),
        ),
        (
            "a broken pattern is refused while loading, not during a scan",
            _raises(lambda: check.compile_rule({"pattern": "[unclosed"}, 1)),
        ),
        (
            "a loaded rule stays plain data that can be written back out",
            _survives_a_round_trip(),
        ),
        (
            "an allow list that is not a list is refused",
            _raises(
                lambda: check.compile_rule(
                    {"pattern": "가", "allow": "목록이 아님"}, 1
                )
            ),
        ),
        (
            "rules without a detector field stay literal",
            hits(
                {
                    "annotation_id": "legacy",
                    "rule_id": "KOR-LEGACY",
                    "original": "제품화 경로",
                    "revised": "제품화 단계",
                    "scope": "general_it_business",
                },
                "제품화 경로를 검토한다",
            ) == 1,
        ),
        (
            "a candidate carrying a pattern is recorded as a regex rule",
            record_feedback.build_candidate(
                _regex_arguments()
            )["detector"] == "regex",
        ),
        (
            "recording refuses a pattern that misses the observed expression",
            any(
                "does not match the observed expression" in error
                for error in record_feedback.validate_candidate(
                    record_feedback.build_candidate(
                        _regex_arguments(pattern="없는표현")
                    )
                )
            ),
        ),
        (
            "promotion carries the detector, the pattern and the allow list",
            (lambda built: built.get("detector") == "regex"
             and built.get("pattern") == "겹치는\\s*자리"
             and built.get("allow") == ["의견을\\s*받는\\s*자리"])(
                promote_feedback.build_rule(
                    record_feedback.build_candidate(_regex_arguments())
                )
            ),
        ),
        (
            "promotion turns each allowed form into a negative case",
            any(
                case["variant"] == "allowed" and case["expected"] == "no_finding"
                for case in promote_feedback.build_cases(
                    record_feedback.build_candidate(_regex_arguments())
                )
            ),
        ),
        (
            "promotion refuses a regex rule that misses its own example",
            any(
                "does not match the observed expression" in error
                for error in promote_feedback.promotion_errors(
                    record_feedback.build_candidate(
                        _regex_arguments(pattern="없는표현")
                    ),
                    [],
                    [],
                )
            ),
        ),
        (
            "promotion refuses a second rule aimed at the same pattern",
            (lambda first: any(
                "duplicate rule target" in error
                for error in promote_feedback.promotion_errors(
                    record_feedback.build_candidate(
                        _regex_arguments(
                            candidate_id="format-case-2", rule_id="KOR-FORMAT-CASE-2"
                        )
                    ),
                    [first],
                    [],
                )
            ))(promote_feedback.build_rule(
                record_feedback.build_candidate(_regex_arguments())
            )),
        ),
        (
            "an empty preferred case is never generated for a regex rule",
            all(
                str(case["text"]).strip()
                for case in promote_feedback.build_cases(
                    record_feedback.build_candidate(_regex_arguments(revised=None))
                )
            ),
        ),
        # 고칠 문구가 없는 규칙은 빈 문자열이 어느 줄에서나 0번째에서 발견된다. 그것을
        # 대조 예시 판정에 그대로 태우면 표 안과 화살표 뒤의 지적이 통째로 사라졌다.
        (
            "a regex rule still reports inside a table",
            hits(plain, "| 항목 | 겹치는 자리 | 비고 |") == 1,
        ),
        (
            "a regex rule still reports after an arrow",
            hits(plain, "- 규칙 → 겹치는 자리를 본다") == 1,
        ),
        (
            "a paired contrast example is still skipped",
            hits(plain, "❌ 겹치는 자리 → ✅ 겹치는 위치") == 0,
        ),
        (
            "one contrast mark alone does not hide a finding",
            hits(plain, "✅ 겹치는 자리를 정리함") == 1,
        ),
        (
            "an allowed form without an example is refused",
            any(
                "needs one example" in error
                for error in promote_feedback.promotion_errors(
                    record_feedback.build_candidate(
                        _regex_arguments(allow_example=[])
                    ),
                    [],
                    [],
                )
            ),
        ),
        (
            "an allow example that is still reported is refused",
            any(
                "still reported" in error
                for error in promote_feedback.promotion_errors(
                    record_feedback.build_candidate(
                        _regex_arguments(allow_example=["겹치는 자리를 본다"])
                    ),
                    [],
                    [],
                )
            ),
        ),
        (
            "allowed cases are built from the examples, never from the pattern text",
            [
                case["text"]
                for case in promote_feedback.build_cases(
                    record_feedback.build_candidate(_regex_arguments())
                )
                if case["variant"] == "allowed"
            ] == ["의견을 받는 자리를 마련한다"],
        ),
    ]
    for name, condition in assertions:
        if condition:
            passed += 1
        else:
            failures.append(f"detector_format/{name}")
    return len(assertions), passed, failures


def _survives_a_round_trip() -> bool:
    """규칙을 읽어 다시 파일로 쓸 수 있어야 한다.

    컴파일한 정규식을 레코드에 심어 두면 그 레코드를 쓰는 순간 터진다. 지금은 그런
    경로가 없지만 규칙을 읽어 고쳐 쓰는 코드가 생기면 바로 걸리므로 여기서 막는다.
    """
    import tempfile

    row = {
        "annotation_id": "round-trip",
        "rule_id": "KOR-ROUND-TRIP",
        "detector": "regex",
        "pattern": "겹치는\\s*자리",
        "allow": ["의견을\\s*받는\\s*자리"],
        "revised": "",
        "scope": "general_it_business",
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "rules.jsonl"
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        loaded = check.load_rules(path)
        try:
            json.dumps(loaded[0])
        except TypeError:
            return False
    return True


def _regex_arguments(**updates: object) -> SimpleNamespace:
    """정규식 후보 하나를 만드는 명령줄 인자."""
    values: dict[str, object] = {
        "candidate_id": "format-case",
        "rule_id": "KOR-FORMAT-CASE",
        "original": "겹치는 자리",
        "revised": "겹치는 지점",
        "pattern": "겹치는\\s*자리",
        "allow": ["의견을\\s*받는\\s*자리"],
        "allow_example": ["의견을 받는 자리를 마련한다"],
        "profile": None,
        "scope": "general_it_business",
        "category": "TEST",
        "decision_source": "user_direct",
        "user_verdict": "corrected",
        "context_level": "sentence",
        "context_before": None,
        "context_after": None,
        "context_excerpt": None,
        "section_title": None,
        "logical_path": None,
        "source_ref": None,
        "source_hash": None,
        "contextual": False,
        "requires_context": False,
        "note": None,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _raises(action) -> bool:
    try:
        action()
    except ValueError:
        return True
    except Exception:
        return False
    return False


def run_feedback_workflow_assertions() -> tuple[int, int, list[str]]:
    failures: list[str] = []
    passed = 0

    def arguments(**updates: object) -> SimpleNamespace:
        values: dict[str, object] = {
            "candidate_id": "workflow-case",
            "rule_id": "KOR-WORKFLOW-CASE",
            "original": "어색한 표현",
            "revised": "자연스러운 표현",
            "profile": None,
            "scope": "general_it_business",
            "category": "TEST",
            "decision_source": "user_direct",
            "user_verdict": "corrected",
            "context_level": "sentence",
            "context_before": None,
            "context_after": None,
            "context_excerpt": None,
            "section_title": None,
            "logical_path": None,
            "source_ref": None,
            "source_hash": None,
            "contextual": False,
            "requires_context": False,
            "note": None,
        }
        values.update(updates)
        return SimpleNamespace(**values)

    human = record_feedback.build_candidate(arguments())
    contextual_human = record_feedback.build_candidate(
        arguments(context_level="window", context_before="앞 문장")
    )
    empty_manifest = {
        "detector_cases": {"expected_count": 0},
        "human_rewrite_pairs": [
            {
                "path": "data/annotations/user-confirmed-phrases.jsonl",
                "expected_count": 0,
            }
        ],
    }
    assertions = [
        ("human feedback becomes confirmed", human["status"] == "confirmed"),
        (
            "model candidate stays observed",
            record_feedback.build_candidate(arguments(
                decision_source="model_candidate", user_verdict="observed"
            ))["status"] == "observed",
        ),
        (
            "model candidate uses an observed category",
            record_feedback.build_candidate(arguments(
                decision_source="model_candidate",
                user_verdict="observed",
                category=None,
            ))["category"] == "MODEL_OBSERVED_EXPRESSION",
        ),
        (
            "document profile maps to an active rule scope",
            record_feedback.build_candidate(arguments(
                profile="technical-report", scope=None
            ))["scope"] == "general_it_business",
        ),
        (
            "profile-specific rule stays within one document type",
            (
                lambda rule: check.applies_to_scope(
                    rule, "general_it_business", "technical-report"
                )
                and not check.applies_to_scope(
                    rule, "general_it_business", "short-message"
                )
            )(
                promote_feedback.build_rule(
                    record_feedback.build_candidate(arguments(
                        profile="technical-report", scope=None
                    ))
                )
            ),
        ),
        (
            "window context rejects missing neighbors",
            any(
                "window context" in error
                for error in record_feedback.validate_candidate(
                    record_feedback.build_candidate(arguments(context_level="window"))
                )
            ),
        ),
        (
            "block context accepts a logical path",
            not record_feedback.validate_candidate(
                record_feedback.build_candidate(
                    arguments(context_level="block", logical_path="$.slides[2].title")
                )
            ),
        ),
        (
            "human correction is promotion ready",
            not promote_feedback.promotion_errors(human, [], []),
        ),
        (
            "promoted rule keeps captured context",
            (
                lambda rule: rule.get("context_before") == "앞 문장"
                and check.scan_text(
                    "어색한 표현",
                    [rule],
                    "general_it_business",
                )[0].get("rule_context", {}).get("context_before") == "앞 문장"
            )(promote_feedback.build_rule(contextual_human)),
        ),
        (
            "model candidate cannot be promoted",
            any(
                "human decision source" in error
                for error in promote_feedback.promotion_errors(
                    record_feedback.build_candidate(arguments(
                        decision_source="model_candidate", user_verdict="observed"
                    )),
                    [],
                    [],
                )
            ),
        ),
        (
            "matching runtime and QA mirrors are accepted",
            not promote_feedback.mirror_errors([], [], [], [], empty_manifest),
        ),
        (
            "different runtime and QA mirrors are rejected",
            any(
                "rule mirror differ" in error
                for error in promote_feedback.mirror_errors(
                    [human], [], [], [], empty_manifest
                )
            ),
        ),
    ]
    for name, condition in assertions:
        if condition:
            passed += 1
        else:
            failures.append(f"feedback_workflow/{name}")
    return len(assertions), passed, failures


def run(
    rules_path: Path,
    cases_path: Path,
    context_cases_path: Path,
) -> dict[str, object]:
    rules = check.load_rules(rules_path)
    cases = load_jsonl(cases_path)
    failures: list[str] = []
    detector_passed = 0
    rule_scopes = {str(row["rule_id"]): str(row["scope"]) for row in rules}

    seen_detector_ids: set[str] = set()
    for case in cases:
        case_id = str(case["case_id"])
        if case_id in seen_detector_ids:
            failures.append(f"detector/{case_id}: duplicate case id")
            continue
        seen_detector_ids.add(case_id)
        if case["detector"] == "user_feedback":
            scope = str(case.get("input_scope") or rule_scopes[str(case["rule_id"])])
            findings = [
                item
                for item in check.scan_text(
                    str(case["text"]),
                    rules,
                    scope,
                    True,
                    str(case["input_profile"])
                    if case.get("input_profile")
                    else None,
                )
                if item["source"] == "user_feedback"
                and item["rule_id"] == case["rule_id"]
            ]
            actual = "finding" if findings else "no_finding"
            expected_rule_context = case.get("expected_rule_context", {})
            finding_context = (
                findings[0].get("rule_context", {}) if findings else {}
            )
            context_matches = all(
                finding_context.get(field) == value
                for field, value in expected_rule_context.items()
            )
            if actual == case["expected"] and (
                not findings
                or not case.get("expected_action")
                or findings[0]["action"] == case["expected_action"]
            ) and context_matches:
                detector_passed += 1
            else:
                failures.append(
                    f"detector/{case_id}: expected={case['expected']} "
                    f"actual={actual} context_matches={context_matches} findings={findings}"
                )
            continue
        match = check.TERM.search(str(case["text"]))
        if not match:
            failures.append(f"detector/{case_id}: term not found")
            continue
        actual, _, _ = check.classify_path(str(case["text"]), match.start(), match.end())
        if actual == case["expected"]:
            detector_passed += 1
        else:
            failures.append(
                f"detector/{case_id}: expected={case['expected']} actual={actual}"
            )

    summary_comment = (
        "\n<!-- HUMANIZE-SUMMARY\nchange_rate: 5.3%\nrules: A-2, S1\n-->\n"
    )
    direct_meaning_cases = [
        (
            "meaning-preserved",
            "CT 2026.12에서 「검증 완료」를 확인했습니다.",
            "CT 2026.12에서 「검증 완료」를 확인했습니다.",
            [],
            [],
            "preserved",
        ),
        (
            "number-changed",
            "CT 2026.12에서 12건을 확인했습니다.",
            "CT 2026.12에서 13건을 확인했습니다.",
            [],
            [],
            "changed_protected_content",
        ),
        (
            "quote-changed",
            "결론은 「검증 완료」입니다.",
            "결론은 「개발 완료」입니다.",
            [],
            [],
            "changed_protected_content",
        ),
        (
            "proper-name-changed",
            "삼성전자 자료를 검토했습니다.",
            "현대자동차 자료를 검토했습니다.",
            ["삼성전자"],
            [],
            "changed_protected_content",
        ),
        # 아래는 사라진 것과 값이 바뀐 것을 가르는 규칙이다. 둘을 뭉치면 중복 제거
        # 같은 권장 수정이 막히고, 반대로 뭉쳐서 통과시키면 숫자가 조용히 사라진다.
        (
            "duplicate-removed-needs-acknowledgement",
            "| 개발 종료 | 10월 30일 |\n본문에서 개발 종료는 10월 30일입니다.",
            "| 개발 종료 | 10월 30일 |",
            [],
            [],
            "removed_content",
        ),
        (
            "acknowledged-removal-passes",
            "AI 기반 TEST 자동화를 검토했습니다.",
            "AI 기반 테스트 자동화를 검토했습니다.",
            [],
            ["TEST"],
            "preserved",
        ),
        (
            "acknowledgement-cannot-excuse-a-changed-value",
            "결함 2건을 확인했습니다.",
            "결함 3건을 확인했습니다.",
            [],
            ["2"],
            "changed_protected_content",
        ),
        (
            "explicit-protection-is-never-softened-to-removal",
            "삼성전자 자료를 검토했습니다.",
            "자료를 검토했습니다.",
            ["삼성전자"],
            [],
            "changed_protected_content",
        ),
        (
            "acknowledgement-cannot-clear-an-explicit-protection",
            "삼성전자 자료를 검토했습니다.",
            "자료를 검토했습니다.",
            ["삼성전자"],
            ["삼성전자"],
            "changed_protected_content",
        ),
        (
            "acknowledgement-still-clears-an-auto-detected-token",
            "TEST 자동화를 검토했습니다.",
            "테스트 자동화를 검토했습니다.",
            [],
            ["TEST"],
            "preserved",
        ),
        (
            "humanize-summary-comment-is-not-document-content",
            "검증을 3회 수행했습니다.",
            "검증을 3회 수행했습니다." + summary_comment,
            [],
            [],
            "preserved",
        ),
    ]
    meaning_passed = 0
    for case_id, before, after, protected, acknowledged, expected in direct_meaning_cases:
        actual = str(
            check_meaning.measure(before, after, protected, acknowledged)["status"]
        )
        if actual == expected:
            meaning_passed += 1
        else:
            failures.append(f"meaning/{case_id}: expected={expected} actual={actual}")

    context_cases = load_jsonl(context_cases_path)
    seen_context_ids: set[str] = set()
    reference_integrity_passed = 0
    for case in context_cases:
        case_id = str(case["case_id"])
        required = (
            "profile",
            "category",
            "provenance",
            "test_kind",
            "context_level",
            "expected_decision",
        )
        if case_id in seen_context_ids:
            failures.append(f"naturalness_reference/{case_id}: duplicate case id")
            continue
        seen_context_ids.add(case_id)
        if any(not case.get(field) for field in required):
            failures.append(f"naturalness_reference/{case_id}: incomplete reference")
            continue
        if case["test_kind"] != "rewrite_reference":
            failures.append(f"naturalness_reference/{case_id}: invalid test_kind")
            continue
        if case["context_level"] not in CONTEXT_LEVELS:
            failures.append(f"naturalness_reference/{case_id}: invalid context_level")
            continue
        # KEEP 은 「고치지 말라」 시료다. FIX 만 받으면 규칙의 예외를 지킨 적이
        # 있는지 확인할 길이 없다 — 실제로 시료 13건이 전부 FIX 였고, 그 사이
        # 「에이전틱」을 예외인데도 고치라고 낸 것이 사용자 판정에서 잡혔다.
        if case["expected_decision"] not in ("FIX", "KEEP"):
            failures.append(
                f"naturalness_reference/{case_id}: expected_decision must be FIX or KEEP")
            continue
        if case["expected_decision"] == "KEEP":
            if case.get("original") != case.get("revised"):
                failures.append(
                    f"naturalness_reference/{case_id}: KEEP must leave the wording unchanged")
                continue
            if not case.get("keep_reason"):
                failures.append(
                    f"naturalness_reference/{case_id}: KEEP needs keep_reason")
                continue
        context_level = str(case["context_level"])
        if context_level == "window" and not (
            case.get("context_before") or case.get("context_after")
        ):
            failures.append(
                f"naturalness_reference/{case_id}: window context is missing"
            )
            continue
        if context_level == "block" and not (
            case.get("source_ref")
            and case.get("source_hash")
            and case.get("logical_path")
            and case.get("source_excerpt")
            and case.get("source_line_hash")
        ):
            failures.append(
                f"naturalness_reference/{case_id}: block source evidence is missing"
            )
            continue
        if context_level == "document" and not (
            case.get("source_ref") and case.get("source_hash")
        ):
            failures.append(
                f"naturalness_reference/{case_id}: document source evidence is missing"
            )
            continue
        if case.get("source_ref"):
            source_ref = Path(str(case["source_ref"]))
            if source_ref.is_absolute():
                failures.append(
                    f"naturalness_reference/{case_id}: source_ref must be relative"
                )
                continue
            source_path = record_feedback.DEFAULT_QA_ROOT / source_ref
            source_excerpt = str(case.get("source_excerpt", ""))
            if source_excerpt and (
                hashlib.sha256(source_excerpt.encode("utf-8")).hexdigest()
                != case.get("source_line_hash")
            ):
                failures.append(
                    f"naturalness_reference/{case_id}: source excerpt hash changed"
                )
                continue
            if source_excerpt and str(case["original"]) not in source_excerpt:
                failures.append(
                    f"naturalness_reference/{case_id}: original not found in source excerpt"
                )
                continue
            if source_path.is_file():
                source_bytes = source_path.read_bytes()
                if hashlib.sha256(source_bytes).hexdigest() != case.get("source_hash"):
                    failures.append(
                        f"naturalness_reference/{case_id}: source hash changed"
                    )
                    continue
                line_match = re.fullmatch(
                    r"line:(\d+)", str(case.get("logical_path", ""))
                )
                if not line_match:
                    failures.append(
                        f"naturalness_reference/{case_id}: invalid logical_path"
                    )
                    continue
                source_lines = source_bytes.decode("utf-8").splitlines()
                line_number = int(line_match.group(1))
                if (
                    line_number < 1
                    or line_number > len(source_lines)
                    or source_lines[line_number - 1] != source_excerpt
                ):
                    failures.append(
                        f"naturalness_reference/{case_id}: source excerpt not found at logical_path"
                    )
                    continue
        reference_integrity_passed += 1

        protected = [str(value) for value in case.get("protect", [])]
        actual = str(
            check_meaning.measure(
                str(case["original"]), str(case["revised"]), protected
            )["status"]
        )
        expected = str(case.get("expected_meaning", "preserved"))
        if actual == expected:
            meaning_passed += 1
        else:
            failures.append(
                f"meaning/{case_id}: expected={expected} actual={actual}"
            )

    detector_assertions = len(cases)
    meaning_assertions = len(direct_meaning_cases) + len(context_cases)
    workflow_assertions, workflow_passed, workflow_failures = (
        run_feedback_workflow_assertions()
    )
    failures.extend(workflow_failures)
    format_assertions, format_passed, format_failures = (
        run_detector_format_assertions()
    )
    failures.extend(format_failures)
    marker_assertions, marker_passed, marker_failures = (
        run_meaning_marker_assertions()
    )
    failures.extend(marker_failures)
    result: dict[str, object] = {
        "status": "FAILED" if failures else "PASSED",
        "detector": {
            "assertions": detector_assertions,
            "passed": detector_passed,
        },
        "naturalness": {
            "reference_pairs": len(context_cases),
            "reference_integrity_passed": reference_integrity_passed,
            "automated_quality_assertions": 0,
            "note": "사람이 판정한 수정 기준문이며 자동 자연스러움 점수로 합격 처리하지 않음",
        },
        "meaning": {
            "assertions": meaning_assertions,
            "passed": meaning_passed,
        },
        "meaning_markers": {
            "assertions": marker_assertions,
            "passed": marker_passed,
            "note": "상태를 바꾸지 않고 사람이 볼 곳만 가리킨다",
        },
        "feedback_workflow": {
            "assertions": workflow_assertions,
            "passed": workflow_passed,
        },
        "detector_format": {
            "assertions": format_assertions,
            "passed": format_passed,
        },
        "language_assertions": detector_assertions + meaning_assertions + marker_assertions,
        "failures": failures,
    }
    return result


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--context-cases", type=Path, default=DEFAULT_CONTEXT_CASES)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = make_parser().parse_args()
    result = run(args.rules, args.cases, args.context_cases)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        detector = result["detector"]
        naturalness = result["naturalness"]
        meaning = result["meaning"]
        workflow = result["feedback_workflow"]
        print(str(result["status"]))
        print(
            f"detector assertions={detector['assertions']} passed={detector['passed']}"
        )
        print(
            "naturalness "
            f"reference_pairs={naturalness['reference_pairs']} "
            f"automated_quality_assertions={naturalness['automated_quality_assertions']}"
        )
        print(f"meaning assertions={meaning['assertions']} passed={meaning['passed']}")
        markers = result["meaning_markers"]
        print(f"meaning_markers assertions={markers['assertions']} passed={markers['passed']}")
        print(
            f"feedback_workflow assertions={workflow['assertions']} "
            f"passed={workflow['passed']}"
        )
        detector_format = result["detector_format"]
        print(
            f"detector_format assertions={detector_format['assertions']} "
            f"passed={detector_format['passed']}"
        )
        print(f"language_assertions={result['language_assertions']}")
        for failure in result["failures"]:
            print(failure)
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
