"""번역투 규칙 셋을 시료로 고정한다 — 뭉치에 없는 갈래도 포함한다.

**왜 시료를 만들어 넣었나.** 처음에 「지금 이 뭉치에서 안 나온다」를 근거로 채택을
접으려 했다. 그건 틀린 관문이다 — 시료가 없다고 검사기를 안 만드는 것과 같다.

| 물음 | 무엇으로 답하나 |
|---|---|
| 이 항목이 잘못된 한국어인가 | **항목 자체로 판단** · 문법서·번역학 |
| 이 규칙이 정상 문장을 잡는가 | 실측 · 오탐만 본다 |

그래서 채택은 항목으로 하고, 실측은 정밀도에만 썼다. 이중 피동은 이 뭉치에 한 건도
없지만 규칙은 들어간다 — 나면 잡아야 하는 오류다.

**실측이 실제로 두 갈래를 잘라 냈다.** 넣어 보고 실문서에 돌리니 오탐이 나왔다.

| 갈래 | 실문서 | 처리 |
|---|---|---|
| 이중 피동 | 2건 전부 「구축되지는 않습니다」 · 「-지 않다」 부정형 | 어간에서 「되」를 뺌 |
| 이중 조사 | 20건 중 절반 넘게 「경로의」·「대로의」 · 「로」가 낱말의 일부 | `LO_WORD` 목록으로 막음 |
| ~에 있어 | 8건 **전부** 「저장소에 있어 접근이 안 된다」 · 있다가 진짜 서술어 | **규칙에서 뺌** · 판단 층으로 |

마지막 것은 폐기가 아니다. 줄만 봐서 안 갈리는 갈래라 읽는 층이 맡는다 —
「불필요한 영어」와 같은 자리다.
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

CHECKER = repo_paths.CHECKER
HEAD = "# 검토 결과\n\n**하반기 검토 범위** — 한 장 조망\n\n## 본문\n\n"
KINDS = {"이중 피동", "번역투 이중 조사", "번역투 그녀"}

# 이 뭉치에 없어서 **만든** 시료다. 없다고 규칙을 안 만들지는 않는다.
POSITIVE = [
    ("이중 피동 불려지다", "- 그렇게 불려지는 이름", "이중 피동"),
    ("이중 피동 되어지다", "- 자동으로 처리되어지는 항목", "이중 피동"),
    ("이중 피동 보여지다", "- 화면에 보여지는 값", "이중 피동"),
    ("이중 피동 나뉘어지다", "- 두 갈래로 나뉘어진 구조", "이중 피동"),
    ("이중 조사 에서의", "- 현장에서의 확인 결과", "번역투 이중 조사"),
    ("이중 조사 으로의", "- 자동화로의 전환 계획", "번역투 이중 조사"),
    ("이중 조사 로부터의", "- 고객으로부터의 요청 목록", "번역투 이중 조사"),
    ("그녀", "- 그녀가 담당한 항목", "번역투 그녀"),
]

# 앞 넷은 실문서에서 실제로 잘못 걸렸던 것이다 — 되돌아오면 여기서 막힌다.
NEGATIVE = [
    ("되지는 — 부정형", "- 마법처럼 구축되지는 않습니다"),
    ("경로의 — 낱말 일부", "- 그 경로의 확인 결과"),
    ("대로의 — 낱말 일부", "- 계획대로의 진행 상황"),
    ("서로의 — 낱말 일부", "- 서로의 결과를 대조"),
    ("옮겨지다 — 능동 어간", "- 문서가 폴더로 옮겨진 뒤 확인"),
    ("만들어지다 — 능동 어간", "- 회의가 끝나고 자료가 만들어짐"),
    ("정상 피동", "- 파일이 자동으로 삭제됨"),
    ("정상 조사", "- 현장에서 확인한 결과"),
    ("코드 안 언급", "- `에서의` 는 이중 조사임"),
    ("인용 안 언급", "- 「현장에서의」 는 고칠 표현"),
]


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TranslationeseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    def kinds_of(self, line: str) -> set:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text(HEAD + line + "\n", encoding="utf-8")
            errors, warnings, _ = self.checker.scan_md(str(target))
        found = set()
        for item in (*errors, *warnings):
            kind = item[1] if len(item) == 3 else item[0]
            if kind in KINDS:
                found.add(kind)
        return found

    def test_each_marker_is_caught(self) -> None:
        for name, line, kind in POSITIVE:
            with self.subTest(case=name):
                self.assertIn(kind, self.kinds_of(line))

    def test_normal_korean_is_left_alone(self) -> None:
        """앞 넷은 실문서에서 실제로 잘못 걸렸던 문장이다."""
        for name, line in NEGATIVE:
            with self.subTest(case=name):
                self.assertEqual(self.kinds_of(line), set())

    def test_double_passive_blocks_publication(self) -> None:
        """문법서가 오류로 다루는 형태다 — 주의로 내리면 발행을 막지 못한다."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text(HEAD + "- 그렇게 불려지는 이름\n", encoding="utf-8")
            errors, _, _ = self.checker.scan_md(str(target))
        kinds = [i[1] if len(i) == 3 else i[0] for i in errors]

        self.assertIn("이중 피동", kinds)

    def test_the_two_soft_markers_only_warn(self) -> None:
        """굳은 쓰임이 섞이는 갈래는 발행을 막지 않는다."""
        for line, kind in (("- 현장에서의 확인 결과", "번역투 이중 조사"),
                           ("- 그녀가 담당한 항목", "번역투 그녀")):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as directory:
                    target = Path(directory) / "doc.md"
                    target.write_text(HEAD + line + "\n", encoding="utf-8")
                    errors, warnings, _ = self.checker.scan_md(str(target))
                self.assertIn(kind, [i[1] if len(i) == 3 else i[0] for i in warnings])
                self.assertNotIn(kind, [i[1] if len(i) == 3 else i[0] for i in errors])

    def test_the_locative_marker_stays_out(self) -> None:
        """「~에 있어」는 실문서 8건이 전부 오탐이었다 — 되살리면 그 8건이 돌아온다."""
        source = CHECKER.read_text(encoding="utf-8")

        self.assertNotIn("ISSEO", source,
                         "「~에 있어」 규칙이 되살아났습니다 — 판단 층 소관입니다")
        self.assertIn("판단 층 소관", source)

    def test_translationese_survives_the_prose_axis(self) -> None:
        """번역투는 산문에서도 번역투다 — 형식 축이 꺼서는 안 된다."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text("---\nform: prose\n---\n" + HEAD
                              + "- 그렇게 불려지는 이름\n", encoding="utf-8")
            errors, _, _ = self.checker.scan_md(str(target))

        self.assertIn("이중 피동", [i[1] if len(i) == 3 else i[0] for i in errors])


class HypeVocabularyTests(unittest.TestCase):
    """과장 어휘 여섯 — 실측 20배로 튄 갈래. 기존 평가 수식어 규칙을 늘린 것이다."""

    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    def test_the_added_words_are_in_the_list(self) -> None:
        for word in ("압도적", "대대적", "획기적", "폭발적", "파격적", "막강한"):
            with self.subTest(word=word):
                self.assertIn(word, self.checker.SELF_PRAISE)

    def test_the_original_words_are_still_there(self) -> None:
        """늘리다가 원래 것을 지우면 조용히 회수율이 떨어진다."""
        for word in ("가벼운", "강력한", "유연한", "혁신적", "완벽한", "뛰어난"):
            with self.subTest(word=word):
                self.assertIn(word, self.checker.SELF_PRAISE)

    def test_a_hype_word_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "doc.md"
            target.write_text(HEAD + "- 압도적 성능을 제공\n", encoding="utf-8")
            _, warnings, _ = self.checker.scan_md(str(target))

        self.assertIn("평가 수식어", [i[1] if len(i) == 3 else i[0] for i in warnings])


if __name__ == "__main__":
    unittest.main()
