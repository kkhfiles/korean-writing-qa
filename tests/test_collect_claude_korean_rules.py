from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_claude_korean_rules import (
    build,
    collect_passages,
    discover_sources,
    split_sections,
)


class ClaudeKoreanRuleCollectionTests(unittest.TestCase):
    def test_discovery_includes_rules_and_memory_but_not_tool_results(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            claude = root / ".claude"
            (claude / "projects" / "p" / "memory").mkdir(parents=True)
            (claude / "projects" / "p" / "tool-results").mkdir(parents=True)
            (claude / "plugins" / "cache" / "plugin").mkdir(parents=True)
            workspace = root / "workspace"
            workspace.mkdir()

            (claude / "CLAUDE.md").write_text("한국어 문체 규칙", encoding="utf-8")
            (claude / "projects" / "p" / "memory" / "tone.md").write_text(
                "자연스러운 한국어", encoding="utf-8"
            )
            (claude / "projects" / "p" / "tool-results" / "noise.txt").write_text(
                "번역투", encoding="utf-8"
            )
            (claude / "plugins" / "cache" / "plugin" / "SKILL.md").write_text(
                "윤문", encoding="utf-8"
            )
            (claude / "plugins" / "cache" / "plugin" / "baseline.json").write_text(
                '{"notes":"한국어 기준값"}', encoding="utf-8"
            )
            (workspace / "CLAUDE.md").write_text("용어 통일", encoding="utf-8")

            sources = discover_sources(claude, [workspace])
            paths = {str(item["source_path"]) for item in sources}

            self.assertEqual(len(sources), 5)
            self.assertFalse(any("tool-results" in path for path in paths))
            self.assertIn("project_rule", {item["source_type"] for item in sources})

    def test_exact_duplicate_sources_are_linked(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            claude = root / ".claude"
            (claude / "projects" / "a" / "memory").mkdir(parents=True)
            (claude / "projects" / "b" / "memory").mkdir(parents=True)
            for name in ("a", "b"):
                (claude / "projects" / name / "memory" / "tone.md").write_text(
                    "# 문체\n자연스러운 한국어 문장", encoding="utf-8"
                )

            sources = discover_sources(claude, [])

            self.assertEqual(len(sources), 2)
            self.assertEqual(sum(item["duplicate_of"] is not None for item in sources), 1)
            self.assertEqual(len(collect_passages(sources)), 1)

    def test_sections_keep_heading_path_and_find_rule_categories(self) -> None:
        text = (
            "---\nname: test\ndescription: 한국어 규칙\n---\n"
            "# 원칙\n서문\n## 문체\n영어 어순을 직역하지 않는다.\n"
        )
        sections = split_sections(text)

        self.assertEqual(sections[-1]["heading_path"], ["원칙", "문체"])
        self.assertFalse(any("description:" in section["text"] for section in sections))

        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            claude = root / ".claude"
            claude.mkdir()
            (claude / "CLAUDE.md").write_text(text, encoding="utf-8")
            passages = collect_passages(discover_sources(claude, []))

            self.assertEqual(len(passages), 1)
            self.assertIn("natural_korean", passages[0]["categories"])

    def test_build_writes_catalog_raw_candidates_and_summary(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            claude = root / ".claude"
            project = root / "project"
            claude.mkdir()
            project.mkdir()
            (claude / "CLAUDE.md").write_text(
                "# 문체\n군더더기를 지우고 단문으로 쓴다.", encoding="utf-8"
            )

            summary = build(claude, project, [], "run-001")

            self.assertEqual(summary["source_files"], 1)
            self.assertEqual(summary["candidate_passages"], 1)
            self.assertEqual(summary["source_extension_counts"], {".md": 1})
            self.assertRegex(summary["collector_sha256"], r"^[0-9a-f]{64}$")
            catalog = project / "data" / "catalog" / "claude-rule-sources.jsonl"
            raw = project / "data" / "raw" / "run-001" / "candidate-passages.jsonl"
            report = project / "runs" / "run-001" / "collection-summary.json"
            self.assertTrue(catalog.exists())
            self.assertTrue(raw.exists())
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["run_id"], "run-001")


if __name__ == "__main__":
    unittest.main()
