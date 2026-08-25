from __future__ import annotations

import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from scripts.measure_revision import measure
from scripts.scan_path_metaphor import TERM, classify
from scripts.scan_user_feedback import PROFILE_SCOPES, load_feedback, scan_text


class RegressionCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.cases = [
            json.loads(line)
            for line in (
                cls.root / "data" / "regression" / "detector-cases.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        cls.feedback = load_feedback(
            cls.root / "data" / "annotations" / "user-confirmed-phrases.jsonl"
        )
        cls.feedback_by_rule = {
            str(record["rule_id"]): record for record in cls.feedback
        }

    def test_case_ids_are_unique_and_expected_count_is_stable(self) -> None:
        manifest = json.loads(
            (self.root / "data" / "regression" / "corpus-sources.json").read_text(
                encoding="utf-8"
            )
        )
        ids = [str(case["case_id"]) for case in self.cases]

        self.assertEqual(len(ids), manifest["detector_cases"]["expected_count"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_each_user_feedback_rule_has_positive_preferred_and_teaching_cases(self) -> None:
        variants: defaultdict[str, set[str]] = defaultdict(set)
        for case in self.cases:
            if case["detector"] == "user_feedback":
                variants[str(case["rule_id"])].add(str(case["variant"]))

        source_rule_ids = {str(record["rule_id"]) for record in self.feedback}
        self.assertEqual(set(variants), source_rule_ids)
        for rule_id in source_rule_ids:
            with self.subTest(rule_id=rule_id):
                self.assertTrue(
                    {"positive", "preferred", "teaching"}.issubset(variants[rule_id])
                )

    def test_user_feedback_detector_cases(self) -> None:
        for case in self.cases:
            if case["detector"] != "user_feedback":
                continue
            input_scope = str(
                case.get(
                    "input_scope",
                    self.feedback_by_rule[str(case["rule_id"])]["scope"],
                )
            )
            findings = scan_text(
                str(case["text"]),
                self.feedback,
                input_scope,
                str(case["input_profile"]) if case.get("input_profile") else None,
            )
            matching = [
                finding
                for finding in findings
                if finding["rule_id"] == case["rule_id"]
            ]
            with self.subTest(case_id=case["case_id"]):
                if case["expected"] == "no_finding":
                    self.assertEqual(matching, [])
                else:
                    self.assertEqual(len(matching), 1)
                    self.assertEqual(matching[0]["action"], case["expected_action"])

    def test_scoped_rules_have_cross_scope_negative_cases(self) -> None:
        scoped_rule_ids = {
            str(record["rule_id"])
            for record in self.feedback
            if record["scope"] != "general_it_business"
        }
        covered_rule_ids = {
            str(case["rule_id"])
            for case in self.cases
            if case["detector"] == "user_feedback"
            and case["variant"] == "cross_scope"
            and case["expected"] == "no_finding"
        }

        self.assertEqual(covered_rule_ids, scoped_rule_ids)

    def test_profiled_rules_have_cross_profile_negative_cases(self) -> None:
        profiled_rules = {
            str(record["rule_id"]): set(record["profiles"])
            for record in self.feedback
            if isinstance(record.get("profiles"), list) and record["profiles"]
        }
        for rule_id, allowed_profiles in profiled_rules.items():
            covered_profiles = {
                str(case["input_profile"])
                for case in self.cases
                if case["detector"] == "user_feedback"
                and case["rule_id"] == rule_id
                and case["variant"] == "cross_profile"
                and case["expected"] == "no_finding"
            }
            with self.subTest(rule_id=rule_id):
                self.assertEqual(
                    covered_profiles,
                    set(PROFILE_SCOPES) - allowed_profiles,
                )

    def test_negative_cases_actually_contain_the_rule_text(self) -> None:
        """음성 시료가 규칙 원문을 담고 있어야 범위 필터를 지킨다.

        손으로 옮겨 적다 한 글자가 바뀐 시료가 둘 있었다. 원문이 안 들어 있으니
        범위 필터를 통째로 없애도 통과했다 — 지키는 것이 없는 시료다. 필터가
        일하는지 재는 척하면서 아무것도 안 재는 상태라 오히려 해롭다.
        """
        checked = 0
        for case in self.cases:
            if case["detector"] != "user_feedback":
                continue
            if case["variant"] not in ("cross_scope", "cross_profile"):
                continue
            original = str(self.feedback_by_rule[str(case["rule_id"])]["original"])
            with self.subTest(case_id=case["case_id"]):
                self.assertIn(
                    original,
                    str(case["text"]),
                    f"{case['case_id']}: 규칙 원문이 없어 필터와 무관하게 통과한다",
                )
            checked += 1

        self.assertGreater(checked, 0, "교차 음성 시료가 하나도 없다")

    def test_path_cases_cover_abstract_literal_and_review(self) -> None:
        path_cases = [case for case in self.cases if case["detector"] == "path_metaphor"]
        counts = Counter(str(case["expected"]) for case in path_cases)

        self.assertGreaterEqual(counts["abstract_candidate"], 10)
        self.assertGreaterEqual(counts["literal_candidate"], 14)
        self.assertGreaterEqual(counts["review"], 12)

        for case in path_cases:
            text = str(case["text"])
            match = TERM.search(text)
            self.assertIsNotNone(match, case["case_id"])
            with self.subTest(case_id=case["case_id"]):
                self.assertEqual(
                    classify(text, match.start(), match.end())[0],
                    case["expected"],
                )

    def test_human_reviewed_path_contexts_never_become_abstract(self) -> None:
        source = self.root / "runs" / "diagnostic-002" / "path-term-candidates.jsonl"
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(records), 33)
        for record in records:
            text = str(record["context"])
            matches = list(TERM.finditer(text))
            self.assertTrue(matches, record)
            for match in matches:
                with self.subTest(path=record["relative_path"], line=record["line_number"]):
                    self.assertNotEqual(
                        classify(text, match.start(), match.end())[0],
                        "abstract_candidate",
                    )

    def test_manual_rewrite_pairs_keep_protected_tokens(self) -> None:
        source = self.root / "data" / "annotations" / "diagnostic-002-review.jsonl"
        records = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(records), 14)
        for record in records:
            if not record["revised"]:
                continue
            result = measure(str(record["original"]), str(record["revised"]))
            with self.subTest(annotation_id=record["annotation_id"]):
                self.assertEqual(result["protected_removed"], [])
                self.assertEqual(result["protected_added"], [])


if __name__ == "__main__":
    unittest.main()
