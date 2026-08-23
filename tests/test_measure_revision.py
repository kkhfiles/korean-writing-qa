from __future__ import annotations

import unittest

from scripts.measure_revision import body, levenshtein_distance, measure


class RevisionMeasureTests(unittest.TestCase):
    def test_levenshtein_distance(self) -> None:
        self.assertEqual(levenshtein_distance("kitten", "sitting"), 3)

    def test_summary_is_excluded(self) -> None:
        text = "본문\n\n<!-- HUMANIZE-SUMMARY\nchange_rate: 10%\n-->\n"
        self.assertEqual(body(text), "본문\n")

    def test_protected_tokens_are_compared(self) -> None:
        result = measure("Claude 5는 100%다.\n", "Claude는 완전하다.\n")
        self.assertEqual(result["protected_removed"], ["100%", "5"])
        self.assertEqual(result["protected_added"], [])


if __name__ == "__main__":
    unittest.main()
