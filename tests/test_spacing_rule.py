"""띄어쓰기 두 꼴(「할수 있다」, 「관리 하고」)을 잡고 조사를 생략한 정상 문장은 두는지 고정한다.

**왜 이 꼴이 생겼나**(2026-11-03). 비교 측정(`runs/bench-external-20261031`)에서 공개 글에 심은
맞춤법 결함 40건 중 39건이 이 두 꼴이었고 1층이 하나도 못 잡았다.

**지켜야 하는 것**
- 의존 명사 「수」 붙여 씀은 **오류** — 말뭉치 세 곳에서 정상 쓰임 0건
- 「하다」, 「되다」 띄어 씀은 **주의** — 「최근 했던 일」, 「주인 된 삶」처럼 조사를 생략한 정상 쓰임이 섞임
- 정상 문장 — 「실수 없이」, 「별수 없다」, 「할수록」, 「세 세트 정도 하시면」, 「다음 할 일」, 「합의 해법」
- 형태소 분석기가 없으면 「하다」 꼴은 안 보고, 안 봤다는 사실이 남음
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402


def load_checker():
    spec = importlib.util.spec_from_file_location("chk_spacing", repo_paths.CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CHK = load_checker()
HAS_KIWI = CHK.morph() is not None

#: (문장, 걸려야 할 글자, 등급)
CATCH_SU = [
    ("이 값은 위원회가 달리 정할수 있습니다.", "할수", "err"),
    ("당장은 도움을 줄수 없어요.", "줄수", "err"),
    ("책을 읽을수 있으면 좋겠습니다.", "을수", "err"),
    ("내일 회의 때 들어갈수 있도록 준비합니다.", "갈수", "err"),
    ("작업량을 줄일수 있습니다.", "일수", "warn"),            # 「일수」는 날수와 못 가름 — 주의로 남김
    ("재직일수 없는 사람은 뺍니다.", "일수", "warn"),        # 날수 「일수」 — 정상이지만 글자로는 같은 꼴
]
CATCH_HA = [
    ("현재 관리 하고 있는 사업은 다섯 개입니다.", "관리 하고", "warn"),
    ("현장에서 지원 한다.", "지원 한다", "warn"),
    ("조치를 신속 하고 엄정하게 합니다.", "신속 하고", "warn"),
    ("모델과 연동 되지 않는 문제가 있습니다.", "연동 되지", "warn"),
    ("실패하면 재시도 할 수 있습니다.", "시도 할", "warn"),   # 분석기가 「재+시도」로 나눔
    ("오늘 세 건 처리 했다.", "처리 했다", "warn"),           # 단위 명사가 끼어도 봄
    ("두 번 확인 했습니다.", "확인 했습니다", "warn"),
    ("방송에 데뷔 하나 보네.", "데뷔 하나", "warn"),         # 「하나」 뒤에 말이 이어지면 용언
]
CLEAN = [
    "실수 없이 처리했습니다.",
    "별수 없다고 판단했습니다.",
    "쓸수록 익숙해집니다.",
    "검토할 수 있습니다.",
    "세 세트 정도 하시면 됩니다.",
    "다음 할 일은 검토입니다.",
    "업계 합의 해법을 따릅니다.",
    "공부를 하고 왔습니다.",
    "키가 180cm 정도 되는 학생입니다.",
    "관리하고 있습니다.",
    "몇 종 하려고 했습니다.",
    "몇 종 하려 했나",
    "사무실에서 커피 한 잔 했던 이후입니다.",
    "선행 확인 하나",                                         # 값 끝의 수사 「하나」
    "남은 것: 문서 검토 하나.",
    "변수 없이 처리합니다.",
    "점수 있는 항목만 봅니다.",
]


def hits(text: str) -> dict[str, str]:
    return {h[1]: h[0] for h in CHK.spacing_hits(text)}


class SpacingRuleTests(unittest.TestCase):
    def test_dependent_noun_su(self) -> None:
        for text, word, level in CATCH_SU:
            with self.subTest(text=text):
                self.assertEqual(hits(text).get(word), level, CHK.spacing_hits(text))

    @unittest.skipUnless(HAS_KIWI, "형태소 분석기 없음")
    def test_spaced_hada_and_doeda(self) -> None:
        for text, word, level in CATCH_HA:
            with self.subTest(text=text):
                self.assertEqual(hits(text).get(word), level, CHK.spacing_hits(text))

    @unittest.skipUnless(HAS_KIWI, "형태소 분석기 없음")
    def test_clean_sentences_stay_clean(self) -> None:
        for text in CLEAN:
            with self.subTest(text=text):
                self.assertEqual(CHK.spacing_hits(text), [])

    def test_reported_through_spelling_hits(self) -> None:
        """맞춤법 갈래로 나간다 — 「맞춤법」을 끈 설정에서는 함께 꺼진다."""
        self.assertIn(("err", "할수"), {h[:2] for h in CHK.spelling_hits("달리 정할수 있습니다.")})

    def test_without_morph_hada_is_skipped_and_announced(self) -> None:
        mod = load_checker()
        mod.morph = lambda: None
        self.assertFalse(mod.SPACING_SKIPPED)
        got = {h[1] for h in mod.spacing_hits("관리 하고 있고 정할수 있습니다.")}
        self.assertEqual(got, {"할수"})
        self.assertTrue(mod.SPACING_SKIPPED)


if __name__ == "__main__":
    unittest.main()
