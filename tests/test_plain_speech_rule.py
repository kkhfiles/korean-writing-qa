"""반말 서술형 갈래가 **문서 전부**에서 걸리는지 고정한다.

**왜 이 갈래가 생겼나.** 한국어 제품 홍보 쪽에 반말은 안 쓴다. 같이 만든 소개 쪽
셋은 서술 문장이 100% 존댓말인데 사례집 하나만 67건이 반말이었다(2026-09-08) —
만든 사람의 작업 문서 말투가 그대로 나간 것이다. 사람이 읽고서야 걸렸다.

**왜 기본으로 켜나**(2026-09-23 사용자 — 「반말 금지 넣을 것 · 문서는 전부」).
예전에는 「업무 보고서의 63%가 반말이고 그게 정상」이라며 기본으로 꺼 두었는데
빈도 논증이었다. 꺼 둔 탓에 발행 원고 열 개에서 반말 149줄이 통과한 적도 있다.

**그래서 지켜야 하는 것이 넷이다** — 설정 없이 걸림 · 목록·표 칸의 근거 문장까지
걸림 · 존댓말은 안 걸림 · Claude 만 읽는 지시 파일은 빠짐.
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

    def test_it_is_caught_without_any_setting(self) -> None:
        """★ 설정 없이 걸린다 — 켜야 걸리는 동안 발행 원고에서 149줄이 샜다."""
        for suffix, doc in ((".html", self.HTML), (".md", self.MD)):
            with self.subTest(형식=suffix):
                self.assertIn("반말 서술형", self.scan(doc, suffix))

    def test_a_reason_sentence_inside_a_list_is_caught(self) -> None:
        """★ 목록 속 「굵은 결론 — 근거 문장」의 근거 문장.

        개조식 검사는 근거 문장을 일부러 안 보고, 반말 검사는 문단만 봐서 이 문장은
        **어느 검사에도 안 걸렸다**(2026-09-23 확인).
        """
        md = "# 소개\n\n독자가 품는 질문 · 한 장 조망\n\n- **대체 아님** — 근거는 아래에 적었다.\n"
        html = "<h1>소개</h1><ul><li><b>대체 아님</b> — 근거는 아래에 적었다.</li></ul>"
        for suffix, doc in ((".md", md), (".html", html)):
            with self.subTest(형식=suffix):
                self.assertIn("반말 서술형", self.scan(doc, suffix))

    def test_a_table_cell_is_caught(self) -> None:
        md = ("# 소개\n\n독자가 품는 질문 · 한 장 조망\n\n| 항목 | 설명 |\n|---|---|\n"
              "| 범위 | 사례는 모두 실제 문서에서 가져왔다 |\n")
        html = ("<h1>소개</h1><table><tr><th>항목</th><th>설명</th></tr>"
                "<tr><td>범위</td><td>사례는 모두 실제 문서에서 가져왔다</td></tr></table>")
        for suffix, doc in ((".md", md), (".html", html)):
            with self.subTest(형식=suffix):
                self.assertIn("반말 서술형", self.scan(doc, suffix))

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

    def test_instruction_files_are_spared(self) -> None:
        """Claude 만 읽는 지시 파일은 사람이 읽는 문서가 아니다 — 빠진다."""
        with tempfile.TemporaryDirectory() as d:
            skill_ref = Path(d) / "skills" / "x" / "references"
            skill_ref.mkdir(parents=True)
            places = [Path(d) / "CLAUDE.md", Path(d) / "AGENTS.md", Path(d) / "SKILL.md",
                      skill_ref / "rules.md"]
            for p in places:
                p.write_text(self.MD, encoding="utf-8")
                err, warn, _ = self.dsc.scan_md(str(p), False, None, None)
                with self.subTest(파일=p.name):
                    self.assertNotIn("반말 서술형", [k for k, _ in err + warn])
            doc = Path(d) / "report.md"
            doc.write_text(self.MD, encoding="utf-8")
            err, _, _ = self.dsc.scan_md(str(doc), False, None, None)
            self.assertIn("반말 서술형", [k for k, _ in err], "보통 문서까지 빠졌다")

    def test_the_rule_list_says_every_document(self) -> None:
        """꺼 두던 시절의 안내(「기본으로 꺼짐」·켜는 법)가 남으면 거꾸로 읽힌다."""
        import io as _io
        import contextlib
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.dsc.list_rules()
        out = buf.getvalue()
        self.assertIn("반말 서술형", out)
        self.assertIn("문서 전부", out)
        self.assertNotIn("기본으로 꺼짐", out)


if __name__ == "__main__":
    unittest.main()
