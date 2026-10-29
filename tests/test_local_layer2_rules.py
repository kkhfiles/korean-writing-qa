"""개인 판정 기준 — 받아 쓰는 사람이 저장소 밖 파일에 적은 기준이 2층 판정기 프롬프트에 실리는지 본다.

**왜 있나** (2026-10-29) — 1층 개인 낱말 목록은 동사 짝만 받아, 문맥을 봐야 갈리는 자기 조직의 기준을
더할 곳이 없었다. 판정 원칙 파일을 직접 고치면 다음 설치 때 덮인다.

**지키는 것**
- 적은 기준이 실제 판정의 규칙 글에 붙나
- 본보기 그대로(주석뿐)면 아무것도 안 붙나 — 빈 절이 프롬프트를 늘리지 않게
- 규칙 전후 비교(`core` 를 준 호출)에는 안 붙나 — 이 PC 의 기준이 측정값을 바꾸지 않게
- `off` 로 끌 수 있나
- 설치가 이 파일을 옮기나
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import install  # noqa: E402
import probe_layer2_kinds as probe  # noqa: E402
import repo_paths  # noqa: E402

RULE = "- **「검증」과 「확인」 구분**: 시험을 실행해 결과를 낸 것만 「검증」"


class LocalLayer2RulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / probe.LOCAL_RULES_FILE

    def pinned(self, value: str):
        return mock.patch.dict(os.environ, {"KOREAN_QA_LOCAL_RULES": value})

    def test_rule_is_added_to_the_judge_rules(self) -> None:
        self.file.write_text(f"<!-- 설명 -->\n\n{RULE}\n", encoding="utf-8")
        with self.pinned(str(self.file)):
            text = probe.rules_for("guided")
        self.assertIn(RULE, text)
        self.assertIn("이 검사기를 쓰는 사람이 더한 기준", text)
        self.assertNotIn("설명", text.split("이 검사기를 쓰는 사람이 더한 기준")[1], "주석을 판정기에 보냈습니다")

    def test_example_alone_adds_nothing(self) -> None:
        example = ROOT / "data" / "catalog" / "local-layer2-rules.example.md"
        with self.pinned(str(example)):
            self.assertEqual("", probe.local_rules(), "본보기만 둔 PC 에서 빈 절이 프롬프트에 붙었습니다")

    def test_not_added_when_comparing_rule_versions(self) -> None:
        self.file.write_text(RULE, encoding="utf-8")
        with self.pinned(str(self.file)):
            text = probe.rules_for("blind", core="# 규칙\n")
        self.assertNotIn(RULE, text, "규칙 전후 비교에 이 PC 의 기준이 섞였습니다")

    def test_off_removes_it(self) -> None:
        with self.pinned("off"):
            self.assertEqual("", probe.local_rules())

    def test_install_copies_it(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            catalog = Path(d) / "data" / "catalog"
            catalog.mkdir(parents=True)
            (catalog / probe.LOCAL_RULES_FILE).write_text(RULE, encoding="utf-8")
            with mock.patch.object(repo_paths, "REPO", Path(d)):
                dsts = [dst for src, dst in install.pairs() if src.name == probe.LOCAL_RULES_FILE]
        self.assertEqual([repo_paths.installed("data", "catalog", probe.LOCAL_RULES_FILE)], dsts)


if __name__ == "__main__":
    unittest.main()
