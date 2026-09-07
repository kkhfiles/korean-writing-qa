"""검사 범위가 조용히 넓어지지 않는지 지킨다.

**확정된 범위**(2026-08-31) — 글이 보고·공유·제출용으로 **파일에 적히는 순간**만
본다. 터미널 응답과 대화는 대상이 아니다.

**왜 시험으로 두나.** 이 범위는 세 번 흔들렸다. 시각 서식을 볼지, 응답 말투를
볼지, 빈 명사를 검사기에 넣을지 — 매번 「그것도 한국어 문제다」라는 이유로
번졌다. 번지면 이 시스템이 무엇인지가 흐려지고, 정작 문서에서 잡아야 할 것이
소음에 묻힌다(시각 서식이 주의의 88%를 먹던 것이 그 예다).

**시험이 막는 것 둘**
1. 범위 기술이 문서에서 사라지는 것 — 사라지면 다음 사람이 다시 넓힌다
2. 검사기가 시각 서식으로 되돌아가는 것 — `test_global_checker_scope`가 맡는다
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
STATUS = REPO_ROOT / "docs" / "status.md"
DECISIONS = REPO_ROOT / "docs" / "decisions-pending.md"
CHECKER = repo_paths.CHECKER


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScopeIsRecordedTests(unittest.TestCase):
    """범위가 어디에도 안 적혀 있으면 다음 세션이 처음부터 다시 정한다."""

    def test_the_status_page_states_when_the_check_applies(self) -> None:
        text = STATUS.read_text(encoding="utf-8")

        self.assertIn("문서로 나갈 때", text)
        self.assertIn("터미널 응답", text)

    def test_the_closed_option_is_recorded_with_its_reason(self) -> None:
        """닫은 이유가 없으면 같은 안이 다시 올라온다 — 실제로 세 번 올라왔다."""
        text = DECISIONS.read_text(encoding="utf-8")

        self.assertIn("검사 범위", text)
        self.assertIn("7.9", text, "응답 쪽 실측값이 빠졌습니다")
        self.assertIn("0.52", text, "문서 쪽 실측값이 빠졌습니다")


class TheCheckerStaysInScopeTests(unittest.TestCase):
    """검사기가 문서 밖을 보려 들지 않는지."""

    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.source = CHECKER.read_text(encoding="utf-8")

    def test_it_reads_files_not_conversations(self) -> None:
        """대화 전사를 읽기 시작하면 범위 밖이다."""
        for term in ("projects", "jsonl", "transcript", "assistant"):
            with self.subTest(term=term):
                self.assertNotIn(term, self.source.lower())

    def test_the_empty_noun_rule_was_not_added(self) -> None:
        """응답에서만 나는 문제라 검사기에 안 넣기로 했다.

        넣으면 「계산하는 값」·「튀는 값」 같은 정상 한국어를 잡는다 —
        세 뭉치 실측 11건이 전부 정당한 쓰임이었다.
        """
        for kind in ("빈 명사", "판창값", "판·창·값"):
            with self.subTest(kind=kind):
                self.assertNotIn(kind, self.source)

    def test_the_jari_rule_still_fires(self) -> None:
        """빼는 쪽만 시험하면 검사기를 통째로 비워도 통과한다.

        글자가 남아 있는지가 아니라 **실제로 걸리는지**를 본다 — 정규식을
        아무것도 안 맞게 바꿔도 이름은 그대로 남아서, 글자만 보면 못 잡는다
        (돌연변이로 확인).

        「자리」는 문서에서도 실측으로 튀어(사용자 1만자당 0.38 · 나 3.16)
        규칙이 서 있다. 빈 명사와 갈리는 지점이 그것이다.
        """
        checker = load_checker()

        def kinds(items):
            return [i[1] if len(i) == 3 else i[0] for i in items]

        # 두 겹을 **등급까지** 본다. 어느 쪽이든 걸리기만 하면 된다고 두면,
        # 안쪽 겹을 지워도 바깥 겹이 받아 주의로 뜨므로 통과한다(돌연변이로 확인).
        for phrase, layer, must_error in (
            ("규칙이 걸리는 자리", "은유 용언 목록 — 오탐 0이라 오류", True),
            ("설명을 만드는 자리", "그 밖의 관형형 — 정당한 쓰임이 섞여 주의", False),
        ):
            with self.subTest(layer=layer):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "doc.md"
                    path.write_text(
                        "---\nform: structured\n---\n"
                        "# 점검 결과\n\n"
                        "**점검 대상 · 결과** — 한 장 조망\n\n"
                        f"- **문제 지점**: {phrase}\n",
                        encoding="utf-8")
                    errors, warnings, _ = checker.scan_md(str(path))

                hard = [k for k in kinds(errors) if "자리" in k]
                soft = [k for k in kinds(warnings) if "자리" in k]
                if must_error:
                    self.assertTrue(hard, f"「{phrase}」는 오류여야 합니다: {soft}")
                else:
                    self.assertTrue(soft, f"「{phrase}」는 주의여야 합니다: {hard}")
                    self.assertFalse(hard, f"「{phrase}」를 오류로 올렸습니다")


if __name__ == "__main__":
    unittest.main()
