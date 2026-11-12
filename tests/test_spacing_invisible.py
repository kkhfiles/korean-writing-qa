"""1층 맞춤법에 더한 꼴 — 붙여 쓴 의존 명사, 「안」 + 하다/되다, 「다음 주」, 「수많은」, 보이지 않는 글자, 겹친 문장 부호, 「어떤」 의문 라벨.

(2026-11-12 업무 소개 글 36편 읽기) 두 모델이 읽으며 찾은 1층 빈틈. 넣기 전에 사람 글 237편(업무 공지와 규정 201편,
업무 소개 글 36편)에서 오탐을 셌다 — 「안」 규칙이 「안내」를 「안」 + 「내다」로 읽어 5건 났고 「하다」, 「되다」로 좁힌 뒤 0건.

**지키는 것**

- 잡음 — 「아실겁니다」, 「동작한게」, 「할줄」, 「열었을때는」(오류), 「안하겠습니다」, 「안되시는」(주의), 「다음주」,
  「이번주」, 「수 많은」(오류), 낱말에 붙은 폭 없는 글자(오류), 「.!」(주의), 「어떤 업무에 쓰나」(의문 라벨)
- 안 잡음 — 「좋은데 나가자」(연결 어미), 「할 수 있다」, 「아는 것이 힘」, 「안내」, 「안정」, 「지난주」, 「수많은」,
  「정말...!」, 파일 첫머리 BOM, 형태소 분석기가 없으면 의존 명사 띄어쓰기는 안 봄(건너뜀 표시)
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import repo_paths  # noqa: E402


def load_checker():
    spec = importlib.util.spec_from_file_location("chk_spacing", repo_paths.CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = load_checker()
HAS_MORPH = C.morph() is not None


def hits(text: str) -> list[tuple[str, str]]:
    return [(h[0], h[1]) for h in C.spelling_hits(text)]


class SpacingTests(unittest.TestCase):

    @unittest.skipUnless(HAS_MORPH, "형태소 분석기가 없으면 의존 명사 띄어쓰기를 안 봄")
    def test_stuck_dependent_nouns_are_errors(self) -> None:
        for text, word in (("이미 아실겁니다.", "아실겁니다"), ("동작한게 맞는지 봅니다.", "동작한게"),
                           ("할줄 압니다.", "할줄"), ("열었을때는 비어 있었습니다.", "열었을때는")):
            with self.subTest(text=text):
                self.assertIn(("err", word), hits(text))

    @unittest.skipUnless(HAS_MORPH, "형태소 분석기가 없으면 안 봄")
    def test_stuck_an_is_a_warning(self) -> None:
        self.assertIn(("warn", "안하겠습니다"), hits("그렇게는 안하겠습니다."))
        self.assertIn(("warn", "안되시는"), hits("검색이 잘 안되시는 경우"))

    @unittest.skipUnless(HAS_MORPH, "형태소 분석기가 없으면 안 봄")
    def test_normal_spacing_is_left_alone(self) -> None:
        for text in ("날씨가 좋은데 나갑니다.", "할 수 있습니다.", "아는 것이 힘입니다.", "안 하겠습니다.", "할 때 봅니다.",
                     "변경 안내", "시스템 안정화", "안경을 썼습니다.", "지난주에 봤습니다.", "수많은 보고서"):
            with self.subTest(text=text):
                self.assertEqual([], [h for h in hits(text) if "띄어" in str(C.spelling_hits(text))], text)

    def test_week_and_sumanheun(self) -> None:
        self.assertIn(("err", "다음주"), hits("다음주에 봅니다."))
        self.assertIn(("err", "이번주"), hits("이번주 일정입니다."))
        self.assertIn(("err", "수 많은"), hits("수 많은 보고서가 있습니다."))
        self.assertEqual([], hits("지난주와 다음 주, 이번 주에 수많은 일이 있었습니다."))


class InvisiblePunctTests(unittest.TestCase):

    def test_a_glued_zero_width_char_is_an_error(self) -> None:
        got = C.spelling_hits("주소 https://example.com/﻿ 입니다")
        self.assertEqual(["err"], [h[0] for h in got if "보이지 않는" in h[4]])

    def test_a_lone_one_is_a_warning_and_bom_at_start_is_skipped(self) -> None:
        self.assertEqual(["warn"], [h[0] for h in C.spelling_hits("앞 ​ 뒤") if "보이지 않는" in h[4]])
        self.assertEqual([], [h for h in C.spelling_hits("﻿머리말") if "보이지 않는" in h[4]])

    def test_doubled_punctuation(self) -> None:
        self.assertIn(("warn", ".!"), hits("안녕하세요.!"))
        self.assertEqual([], [h for h in hits("정말...! 좋습니다. 왜?") if h[1] in (".!", ".?")])


class QuestionLabelTests(unittest.TestCase):

    def test_eotteon_label(self) -> None:
        self.assertIsNotNone(C.fragment("어떤 업무에 쓰나")[0])
        self.assertEqual((None, None), C.fragment("어떤 업무든 지원"))


if __name__ == "__main__":
    unittest.main()
