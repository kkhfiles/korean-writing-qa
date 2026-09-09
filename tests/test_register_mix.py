"""한 문서 안에서 말투가 섞였는지 — 소수 쪽만 낸다.

**반말 자체는 잘못이 아니다.** 작업 기록과 규칙 문서는 서술 문장의 90%가, 업무
보고서는 63%가 반말이고 그게 정상이다. 잘못은 **한 문서 안에서 섞이는 것**이다 —
존댓말로 쓰다 한 줄만 반말로 빠지면 읽는 사람이 거기서 걸린다(2026-09-09 사용자
지적 — 「갑자기 반말로」).

**왜 사례집(`C-0xx`)으로 못 지키나.** 그 시험틀은 한 줄을 넣어 판정을 본다. 섞임은
문서 전체를 봐야 판정되므로(서술 문장 12개 이상) 한 줄로는 영영 안 걸린다. 그래서
여기서 문서를 지어 놓고 본다.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HEAD = "---\nform: prose\n---\n# 조사 배경\n\n**조사 배경 · 대상** — 한 장 조망\n\n"
POLITE = [
    "조사 대상은 실 단위로 정했습니다.", "응답은 익명으로 받았습니다.",
    "회수율은 82%입니다.", "기준은 두 가지입니다.",
    "첫째는 대체 가능성입니다.", "둘째는 사업 기여도입니다.",
    "두 값을 따로 집계했습니다.", "결과는 다음 주에 공유합니다.",
    "문항은 다섯 개입니다.", "평균 응답 시간은 4분입니다.",
    "이견은 회의에서 정리합니다.", "추가 문의는 담당자에게 주시면 됩니다.",
]
PLAIN = [s.replace("습니다", "다").replace("입니다", "이다")
         .replace("합니다", "한다").replace("됩니다", "된다") for s in POLITE]
SLIP = "이번 조사는 회사 비즈니스 관점이다."


def load_checker():
    spec = importlib.util.spec_from_file_location(
        "doc_style_check", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RegisterMixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not repo_paths.CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {repo_paths.CHECKER}")
        cls.checker = load_checker()

    def kinds(self, sentences):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "doc.md"
            path.write_text(HEAD + " ".join(sentences) + "\n", encoding="utf-8")
            err, warn, _ = self.checker.scan_md(str(path))
        pick = lambda items: [i[1] if len(i) == 3 else i[0] for i in items]  # noqa: E731
        return pick(err), pick(warn)

    def test_one_plain_line_in_a_polite_report_is_flagged(self) -> None:
        """발단이 된 문장 — 존댓말 보고서에 반말 한 줄."""
        _err, warn = self.kinds(POLITE + [SLIP])
        self.assertIn("말투 섞임", warn)

    def test_a_report_written_entirely_in_plain_speech_stays_quiet(self) -> None:
        """반말로 통일된 문서는 정상이다 — 여기서 지적하면 규칙이 죽는다."""
        _err, warn = self.kinds(PLAIN)
        self.assertNotIn("말투 섞임", warn)

    def test_a_report_written_entirely_in_polite_speech_stays_quiet(self) -> None:
        _err, warn = self.kinds(POLITE)
        self.assertNotIn("말투 섞임", warn)

    def test_two_registers_in_equal_measure_is_not_a_slip(self) -> None:
        """반반이면 섞인 것이 아니라 두 말투를 쓴 문서다 — 사람이 정할 몫."""
        _err, warn = self.kinds(POLITE + PLAIN)
        self.assertNotIn("말투 섞임", warn)

    def test_a_short_document_is_not_judged(self) -> None:
        """서술 문장이 적으면 어느 쪽이 주인인지 못 가른다 — 판단 불가면 침묵."""
        _err, warn = self.kinds(POLITE[:4] + [SLIP])
        self.assertNotIn("말투 섞임", warn)

    def test_anida_is_plain_speech_not_polite(self) -> None:
        """⛔ 「아니다」·「지니다」·「다니다」가 존댓말로 잡히고 있었다.

        존댓말 「~ㅂ니다」는 앞 글자가 반드시 ㅂ 받침으로 끝난다(합니다·됩니다·
        입니다). 「아니다」의 「아」에는 받침이 없다. 「반말 서술형」 갈래가 기본으로
        꺼져 있어 이 버그가 안 드러나 있었고, 말투 섞임을 켜면서 반말로 쓴 규칙
        문서의 「…가 아니다」가 **존댓말 소수**로 튀어 나왔다(실측 7건 → 1건).
        """
        for word, polite in (("아니다", False), ("지니다", False),
                             ("다니다", False), ("합니다", True),
                             ("됩니다", True), ("입니다", True),
                             ("아닙니다", True), ("드립니다", True)):
            with self.subTest(word=word):
                self.assertEqual(polite, self.checker.is_polite(word))
                self.assertEqual(not polite,
                                 self.checker.is_plain_speech(word))


if __name__ == "__main__":
    unittest.main()
