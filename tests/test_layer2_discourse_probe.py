"""문장 사이 관계 탐침이 **잴 수 있는 상태인지** 본다 — 모델은 안 부른다.

**지키는 것**

- 사례마다 같은 갈래의 정상 짝이 있다 (짝이 없으면 접속어만 보고 짚는 판정기를 못 거른다)
- 짚을 표현이 대상 문장 안에 있고, 대상 문장이 운반 문서의 한 줄에 하나씩 있다
- 갈래 이름이 9단계 항목에 있다 (항목 이름이 바뀌면 채점이 조용히 0 이 된다)
- 규칙 글이 대상 문장을 통째로 인용하지 않는다 (인용되면 되찾기 시험으로 바뀐다)
- 운반 문서가 부를 때마다 같다 (회차끼리 같은 문서여야 견준다)
- 바꾸기 전 규칙 글을 커밋에서 읽어 조립한다
"""
from __future__ import annotations

import re
import subprocess
import sys
import unittest
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import probe_layer2_discourse as probe  # noqa: E402


class CaseTests(unittest.TestCase):

    def setUp(self) -> None:
        self.cases = probe.load_cases()
        self.doc = probe.document()

    def test_every_case_has_a_clean_partner_of_the_same_kind(self) -> None:
        pairs = defaultdict(list)
        for c in self.cases:
            pairs[c["pair"]].append(c)
        for n, rows in pairs.items():
            self.assertEqual({"finding", "clean"}, {r["expect"] for r in rows}, f"짝 {n}: 사례와 정상이 다 있어야 합니다")
            self.assertEqual(1, len({r["kind"] for r in rows}), f"짝 {n}: 갈래가 갈렸습니다")

    def test_spans_sit_in_their_sentence_and_each_sentence_has_its_own_line(self) -> None:
        for c in self.cases:
            self.assertIn(c["text"], c["sentence"], f"{c['id']}: 짚을 표현이 문장 밖입니다")
            lines = [n for n, line in enumerate(self.doc.splitlines(), 1) if c["sentence"] in line]
            self.assertEqual(1, len(lines), f"{c['id']}: 운반 문서에서 한 줄로 안 잡힙니다 — {lines}")
        lines = [probe.kinds.line_of(self.doc, c["sentence"]) for c in self.cases]
        self.assertEqual(len(lines), len(set(lines)), "두 사례가 한 줄에 있습니다 — 채점이 섞입니다")

    def test_every_kind_is_an_item_of_the_step(self) -> None:
        body = probe.kinds.step_body(probe.kinds.SKILL_MD.read_text(encoding="utf-8"), probe.kinds.STEP_TITLE)
        titles = set(re.findall(r"^   - \*\*(.+?)\*\*", body, re.M))
        for c in self.cases:
            self.assertIn(c["kind"], titles, f"{c['id']}: 9단계에 「{c['kind']}」 항목이 없습니다")

    def test_the_rules_do_not_quote_a_whole_sentence(self) -> None:
        rules = probe.kinds.rules_for("guided").replace("*", "")
        leaked = [c["id"] for c in self.cases if c["sentence"] in rules or c["context"] in rules]
        self.assertEqual([], leaked, "규칙이 시료 문장을 인용합니다 — 시료를 바꿉니다")

    def test_the_carrier_is_the_same_every_time(self) -> None:
        self.assertEqual(self.doc, probe.document())


class ScoreTests(unittest.TestCase):

    def test_a_finding_on_a_clean_line_counts_against_the_rule(self) -> None:
        cases = probe.load_cases()
        doc = probe.document(cases)
        clean = next(c for c in cases if c["expect"] == "clean")
        hit = next(c for c in cases if c["expect"] == "finding")
        findings = [{"line": probe.kinds.line_of(doc, clean["sentence"]), "phrase": clean["text"],
                     "category": clean["kind"]},
                    {"line": probe.kinds.line_of(doc, hit["sentence"]), "phrase": hit["text"], "category": "다른 이름"}]
        s = probe.score_discourse(cases, findings, doc, [clean["kind"]])
        self.assertEqual(1, s["정상 짝 지적 줄"])
        self.assertEqual(1, s["정상 짝 관계 갈래 지적"])
        self.assertEqual(1, s["회수(줄)"])
        self.assertEqual(1, s["회수(표현)"])


class RulesAtTests(unittest.TestCase):

    def test_rules_come_from_the_named_commit(self) -> None:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=probe.REPO_ROOT, capture_output=True,
                              text=True).stdout.strip()
        if not head:
            self.skipTest("git 저장소가 아닙니다")
        core, skill = probe.rules_at(head)
        self.assertIn("## 공통 원칙", core)
        self.assertIn(probe.kinds.STEP_TITLE, skill)


if __name__ == "__main__":
    unittest.main()
