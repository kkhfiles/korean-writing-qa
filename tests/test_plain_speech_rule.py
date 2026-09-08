"""반말 서술형 갈래가 켜질 때만 걸리는지 고정한다.

**왜 이 갈래가 생겼나.** 한국어 제품 홍보 쪽에 반말은 안 쓴다. 같이 만든 소개 쪽
셋은 서술 문장이 100% 존댓말인데 사례집 하나만 67건이 반말이었다(2026-09-08) —
만든 사람의 작업 문서 말투가 그대로 나간 것이다. 사람이 읽고서야 걸렸다.

**왜 기본으로 꺼 두나.** 반말 자체는 잘못이 아니다. 실측으로 작업 기록과 규칙
문서는 서술 문장의 90%가, 업무 보고서는 63%가 반말이고 그게 정상이다. 기본으로
켜면 정당한 글 수천 줄이 지적으로 쏟아져 정작 봐야 할 것을 덮는다 — 이 검사기가
서식 검사에서 이미 겪은 실패다(주의 2,546건 중 2,239건이 서식이었다).

**그래서 지켜야 하는 것이 셋이다** — 켜지 않으면 침묵 · 켜면 잡음 · 존댓말은
켜도 안 걸림.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

CHECKER = repo_paths.CHECKER

#: 반말 서술형 — 홍보 쪽에서 실제로 걸렸던 꼴
PLAIN = [
    ("평서형", "사례는 모두 실제 문서에서 가져왔다."),
    ("현재형", "받아서 그대로 쓰는 것이 아니라 켜고 끄고 등급을 바꿔서 쓴다."),
    ("지정사", "나머지는 문서 형식과 무관하게 어긋난 한국어다."),
    ("부정형", "주어를 「이 문서」로 잡지 않는다."),
    ("과거형", "값 칸을 문장으로 끝냈다."),
]

#: 존댓말 — 켜도 안 걸려야 한다
POLITE = [
    ("합쇼체", "사례는 모두 실제 문서에서 가져왔습니다."),
    ("이다 존대", "나머지는 문서 형식과 무관하게 어긋난 한국어입니다."),
    ("동사 존대", "받아서 그대로 쓰지 않고 켜고 끄고 등급을 바꿔서 씁니다."),
    ("해요체", "평소 쓰는 문장 그대로 물으면 돼요."),
    ("의문 존대", "무엇을 언제 쟀는지 값마다 붙여 두었습니까."),
]

#: 개조식 값 — 서술형이 아니라 애초에 대상이 아니다
NOT_SENTENCE = [
    ("명사형", "대체 아님 · 별도 추가"),
    ("체언", "되돌리기 비용 최대"),
]


def load():
    spec = importlib.util.spec_from_file_location("dsc", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PlainSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {CHECKER}")
        cls.dsc = load()

    # ── 판정 자체 ────────────────────────────────────────────────────────────
    def test_plain_speech_is_recognised(self) -> None:
        for label, text in PLAIN:
            with self.subTest(case=label):
                self.assertTrue(self.dsc.is_plain_speech(text), text)

    def test_polite_speech_is_not_flagged(self) -> None:
        """존댓말까지 걸면 고칠 길이 없어져 사람이 갈래를 통째로 끈다."""
        for label, text in POLITE:
            with self.subTest(case=label):
                self.assertFalse(self.dsc.is_plain_speech(text), text)

    def test_a_bullet_style_value_is_out_of_scope(self) -> None:
        """개조식 값은 서술형이 아니라 애초에 말투를 물을 대상이 아니다."""
        for label, text in NOT_SENTENCE:
            with self.subTest(case=label):
                self.assertFalse(self.dsc.is_plain_speech(text), text)

    # ── 켜고 끄기 ────────────────────────────────────────────────────────────
    def scan(self, text, suffix=".html", rules=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / f"doc{suffix}"
            p.write_text(text, encoding="utf-8")
            scan = self.dsc.scan_html if suffix == ".html" else self.dsc.scan_md
            err, warn, _ = scan(str(p), False, None, rules)
        return [k for k, _ in err] + [k for k, _ in warn]

    HTML = "<h1>소개</h1><p>사례는 모두 실제 문서에서 가져왔다.</p>"
    MD = "# 소개\n\n독자가 품는 질문 · 한 장 조망\n\n사례는 모두 실제 문서에서 가져왔다.\n"

    def test_it_stays_silent_until_switched_on(self) -> None:
        """★ 켜지 않으면 침묵한다 — 첫 실행에서 정당한 반말이 쏟아지면 사람은
        갈래가 아니라 검사기를 끈다."""
        for suffix, doc in ((".html", self.HTML), (".md", self.MD)):
            with self.subTest(형식=suffix):
                self.assertNotIn("반말 서술형", self.scan(doc, suffix))

    def test_switching_it_on_catches_it(self) -> None:
        on = self.dsc.Selection(on={"반말 서술형"}, source="시험")
        for suffix, doc in ((".html", self.HTML), (".md", self.MD)):
            with self.subTest(형식=suffix):
                self.assertIn("반말 서술형", self.scan(doc, suffix, on))

    def test_polite_text_passes_even_when_switched_on(self) -> None:
        on = self.dsc.Selection(on={"반말 서술형"}, source="시험")
        polite = "<h1>소개</h1><p>사례는 모두 실제 문서에서 가져왔습니다.</p>"
        self.assertNotIn("반말 서술형", self.scan(polite, ".html", on))

    def test_it_reads_the_footer_too(self) -> None:
        """★ 꼬리말은 사람이 보는 글이다 — `<p>` 만 보면 그대로 나간다.

        발행한 쪽의 꼬리말이 `<span>` 으로만 짜여 있어 반말 한 줄이 나갔고,
        검사기가 아니라 사람이 읽고서야 걸렸다(2026-09-08).
        """
        on = self.dsc.Selection(on={"반말 서술형"}, source="시험")
        doc = ("<h1>소개</h1><p>사례는 실제 문서에서 가져왔습니다.</p>"
               "<footer><span>이 페이지도 같은 검사기를 통과했다.</span></footer>")
        self.assertIn("반말 서술형", self.scan(doc, ".html", on))

    def test_plain_speech_before_a_dash_is_caught(self) -> None:
        """반말이 대시 앞에 있으면 문장의 끝이 아니라서 통째로 빠졌다."""
        on = self.dsc.Selection(on={"반말 서술형"}, source="시험")
        doc = "<h1>소개</h1><p>이 페이지도 같은 검사기를 통과했다 — 오류 0.</p>"
        self.assertIn("반말 서술형", self.scan(doc, ".html", on))

    def test_a_noun_ending_head_before_a_dash_still_passes(self) -> None:
        """개조식 결론 머리까지 걸면 규칙 §1 이 요구하는 형태가 못 쓰이게 된다."""
        on = self.dsc.Selection(on={"반말 서술형"}, source="시험")
        doc = "<h1>소개</h1><p><b>대체 아님 · 별도 추가</b> — 근거를 아래에 적었습니다.</p>"
        self.assertNotIn("반말 서술형", self.scan(doc, ".html", on))

    def test_the_kind_is_in_the_default_off_list(self) -> None:
        """목록에서 빠지면 조용히 기본 켜짐이 되어 모든 작업 문서가 쏟아진다."""
        self.assertIn("반말 서술형", self.dsc.DEFAULT_OFF)
        self.assertIn("반말 서술형", self.dsc.ALL_KINDS)

    def test_the_rule_list_marks_it_as_off_by_default(self) -> None:
        """켜야 쓰는 갈래인데 목록이 그 말을 안 하면 아무도 안 켠다."""
        import io as _io
        import contextlib
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.dsc.list_rules()
        out = buf.getvalue()
        self.assertIn("반말 서술형", out)
        self.assertIn("기본으로 꺼짐", out)
        self.assertIn('on = ["반말 서술형"]', out)


if __name__ == "__main__":
    unittest.main()
