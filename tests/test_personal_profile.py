"""개인 항목 스위치 — 개인 설정이 있으면 지금 그대로, 없으면 개인 항목만 빠지는지 본다. 모델은 안 부른다.

(2026-10-20 사용자 판정) 「늘」, 「매일 밤」과 2층 대표 수정 표의 네 행은 업무 글에서도 흔히 쓰는 표현을
작성자가 고른 것이라, 이 검사기를 받아 쓰는 다른 사람에게는 기본으로 꺼 둔다. 같이 개인으로 판정한 모임 뜻
「자리」는 같은 어간의 은유와 못 갈라 끄지 않는다. 목록과 근거는 `docs/check-inventory-personal.md`.

**지키는 것**

- 켜면 판정기에 가는 규칙 글이 표시를 넣기 전과 글자까지 같다 — 이 PC의 정확도를 다시 잴 필요가 없다
- 끄면 개인 행만 빠지고 나머지 글은 그대로다
- 1층은 끄면 개인 항목만 조용해지고 공통 항목(「~하는 자리」 의심 등)은 그대로 낸다
- 검사기와 판정기 스크립트의 스위치 판정이 같다
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parent))

import probe_layer2_kinds as probe  # noqa: E402
import repo_paths  # noqa: E402

PROBE = ("---\nform: prose\n---\n\n# 점검 안내\n\n배치는 매일 밤 실행합니다.\n\n결과는 늘 같습니다.\n\n"
         "의견을 받는 자리를 마련합니다.\n\n질문을 묻는 자리입니다.\n")
PERSONAL_ROWS = ("| 제품화 경로 |", "| 테스트를 만드는 데 공수가", "| 구축됐으나 합격 조건 미충족 |",
                 "| 사람 손으로 친 커밋도")


def check(text: str, switch: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "probe.md"
        p.write_text(text, encoding="utf-8")
        env = dict(os.environ, KOREAN_QA_PERSONAL_RULES=switch)
        return subprocess.run([sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(p), "-v", "--no-rules"],
                              capture_output=True, text=True, encoding="utf-8", env=env).stdout


class LayerTwoTests(unittest.TestCase):

    def rules(self, switch: str) -> str:
        with mock.patch.dict(os.environ, {"KOREAN_QA_PERSONAL_RULES": switch}):
            return probe.rules_for("guided")

    def test_on_is_the_file_without_marks(self) -> None:
        raw = probe.RULES.read_text(encoding="utf-8")
        on = self.rules("on")
        self.assertNotIn(probe.PERSONAL_MARK, on)
        self.assertTrue(on.startswith(raw.replace(probe.PERSONAL_MARK, "")),
                        "켰을 때 규칙 글이 표시만 뗀 파일과 달라졌습니다 — 이 PC의 판정 입력이 바뀝니다")

    def test_marked_rows_are_the_judged_ones(self) -> None:
        raw = probe.RULES.read_text(encoding="utf-8")
        marked = [l for l in raw.splitlines() if probe.PERSONAL_MARK in l]
        self.assertEqual(len(marked), len(PERSONAL_ROWS))
        for row in PERSONAL_ROWS:
            self.assertTrue(any(l.startswith(row) for l in marked), row)

    def test_off_drops_only_the_marked_rows(self) -> None:
        on, off = self.rules("on"), self.rules("off")
        for row in PERSONAL_ROWS:
            self.assertIn(row, on)
            self.assertNotIn(row, off)
        kept = [l for l in on.splitlines() if not any(l.startswith(r) for r in PERSONAL_ROWS)]
        self.assertEqual(kept, off.splitlines())


class LayerOneTests(unittest.TestCase):

    def test_on_flags_the_personal_items(self) -> None:
        out = check(PROBE, "on")
        for word in ("「매일 밤」", "「늘」", "「받는 자리」", "「묻는 자리」"):
            self.assertIn(word, out)

    def test_off_keeps_only_the_common_ones(self) -> None:
        out = check(PROBE, "off")
        for word in ("「매일 밤」", "「늘」"):
            self.assertNotIn(word, out, f"개인 설정이 없는데 {word} 를 냈습니다")
        # 모임 뜻 「자리」는 개인 판정이지만 같은 어간의 은유를 못 갈라 끄지 않는다(검사기 JARI_OK 주석)
        for word in ("「받는 자리」", "「묻는 자리」"):
            self.assertIn(word, out, f"{word} 는 은유와 못 갈라 개인 설정과 무관하게 냅니다")


class SwitchTests(unittest.TestCase):

    def test_checker_and_scripts_agree(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("doc_style_check_profile", repo_paths.CHECKER)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        with tempfile.TemporaryDirectory() as d:
            there = Path(d) / repo_paths.PROFILE_FILE
            there.write_text("", encoding="utf-8")
            for value in ("on", "off", "1", "0", str(there), str(Path(d) / "없음.txt")):
                with mock.patch.dict(os.environ, {"KOREAN_QA_PERSONAL_RULES": value}):
                    self.assertEqual(checker.personal_profile(), repo_paths.personal_profile(), value)
        self.assertEqual(checker.PROFILE_FILE, repo_paths.PROFILE_FILE)


if __name__ == "__main__":
    unittest.main()
