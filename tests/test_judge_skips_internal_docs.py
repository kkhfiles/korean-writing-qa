"""작성자만 보는 저장소 내부 문서는 판정기가 판정하지 않는지 본다 — 모델은 안 부른다.

(2026-11-05 사용자) 「내가 직접 보거나 공유하거나 문서화하거나 발표용으로 만들거나 게시하는게 아닌 문서를
쓸데없이 검사 안하도록 뭔가 장치를」 — 세션이 발행 대상이 아닌 내부 기록을 손으로 판정하다 재판정 상한을 넘겨
사용자에게 사람 확인을 넘겼다. 훅은 그 문서를 작성자용으로 갈랐는데 판정기는 안 봤다.

**지키는 것**

- 개인 설정 `check_scope = "shared"` 에서 `[publish]` 대상이 아닌 저장소 문서는 호출 없이 건너뜀
- 발행 대상, 머리말 `audience: share`, `--internal` 은 판정함
- 개인 설정이 없으면(다른 설치본) 예전처럼 판정함
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import layer2_coverage as coverage  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402

TEXT = "# 메모\n\n결정을 기다리는 항목을 모았습니다.\n"


class SkipInternalTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        (self.repo / "docs").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "korean-qa.toml").write_text('[publish]\ntargets = ["README.md"]\n', encoding="utf-8")
        for rel in ("README.md", "docs/notes.md"):
            (self.repo / rel).write_text(TEXT, encoding="utf-8")
        self.personal = root / "personal.toml"
        self.personal.write_text('check_scope = "shared"\n', encoding="utf-8")
        self.saved = (os.environ.get("KOREAN_QA_PUBLISH_REPOS"), judge.LOG, coverage.ANSWERS,
                      coverage.DISMISSALS, coverage.DECISIONS)
        os.environ["KOREAN_QA_PUBLISH_REPOS"] = str(self.personal)
        judge.LOG = root / "calls.jsonl"
        coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS = (root / "a.jsonl", root / "d.jsonl",
                                                                     root / "dec.jsonl")
        judge._GATE.clear()             # 개인 목록 경로는 훅을 불러올 때 읽힌다

    def tearDown(self) -> None:
        env, judge.LOG, coverage.ANSWERS, coverage.DISMISSALS, coverage.DECISIONS = self.saved
        if env is None:
            os.environ.pop("KOREAN_QA_PUBLISH_REPOS", None)
        else:
            os.environ["KOREAN_QA_PUBLISH_REPOS"] = env
        judge._GATE.clear()
        self.tmp.cleanup()

    def run_main(self, *argv: str) -> tuple[int, str, FakeBackend]:
        fake = FakeBackend([])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = judge.main([*argv, "--level", "max", "--json", str(Path(self.tmp.name) / "r.json")],
                            backend=fake.pair())
        return rc, out.getvalue(), fake

    def test_an_internal_doc_is_skipped_without_a_call(self) -> None:
        rc, out, fake = self.run_main(str(self.repo / "docs" / "notes.md"))
        self.assertEqual(0, rc, out)
        self.assertEqual([], fake.calls, "작성자만 보는 내부 문서를 판정했습니다")
        self.assertIn("판정하지 않았습니다", out)

    def test_a_publish_target_is_judged(self) -> None:
        _, out, fake = self.run_main(str(self.repo / "README.md"))
        self.assertEqual(1, len(fake.calls), out)

    def test_audience_share_or_the_flag_brings_it_back(self) -> None:
        notes = self.repo / "docs" / "notes.md"
        _, out, fake = self.run_main(str(notes), "--internal")
        self.assertEqual(1, len(fake.calls), out)
        notes.write_text("---\naudience: share\n---\n" + TEXT, encoding="utf-8")
        _, out, fake = self.run_main(str(notes))
        self.assertEqual(1, len(fake.calls), out)

    def test_without_the_personal_setting_everything_is_judged(self) -> None:
        self.personal.write_text("", encoding="utf-8")
        judge._GATE.clear()
        _, out, fake = self.run_main(str(self.repo / "docs" / "notes.md"))
        self.assertEqual(1, len(fake.calls), "다른 설치본(개인 설정 없음)의 판정이 꺼졌습니다")


if __name__ == "__main__":
    unittest.main()
