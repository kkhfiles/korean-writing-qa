"""반말은 개인 기준, 섞임은 누구에게나 결함 — 설치 종류에 따라 말투 판정이 갈리는지 고정한다.

(2026-11-02) 「반말 서술형」은 저장소 주인 한 사람의 기준(문서는 합쇼체)이다. 2026-10-30 사용자 결정
「이 규칙과 검사기는 사용자 본인의 글에만 적용, 다른 사람에게 강요하지 않음」에 따라 개인 항목
스위치가 없는 설치에서는 해라체로 통일한 문서를 결함으로 보지 않는다. 한 문서에 합쇼체와 해라체가
섞인 줄은 누구에게나 결함이라 「말투 섞임」 오류로 낸다. 임계 근거는 검사기 `register_strays` 주석.

**지키는 것**

- 공유 기준: 해라체 일관 문서 0건(정상 쪽 시료를 여럿 둔다), 합쇼체 일관 문서 0건
- 공유 기준: 섞인 문서는 적은 쪽 줄만 「말투 섞임」 오류, 주인 말투를 못 정하면 주의 한 줄
- 공유 기준: 설정 `on = ["반말 서술형"]` 이면 개인 기준과 같고, 발행 게이트(`--no-rules`)도 그 켬을 따름
- 개인 기준: 지금 그대로 해라체 문장 전부가 「반말 서술형」 오류
- 인용, 코드, ❌ 예시, 지시 파일은 어느 쪽에서든 빠짐
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

HEAD = "---\nform: prose\n---\n# 조사 결과\n\n**조사 결과 요약** — 한 장 조망\n\n"

#: 해라체로 통일한 정상 문서 — 공유 기준에서 말투 지적이 하나도 없어야 한다
PLAIN_DOCS = {
    "보고서 문단": HEAD + ("조사 대상은 실 단위로 정했다. 응답은 익명으로 받았다. 회수율은 82%이다. "
                     "두 값을 따로 집계했다. 결과는 다음 주에 공유한다.\n"),
    "기사체와 존댓말 인용": HEAD + ("새만금 현지 사무소가 30일 문을 열었다. 청장은 \"현장 중심으로 협력하겠습니다\"라고 "
                         "말했다. 투자는 내년 3월 착공부터 본격화된다. 관계 기관도 지원을 약속했다.\n"),
    "목록과 근거 문장": HEAD + ("- **회수율 82%** — 익명으로 받아 응답이 늘었다.\n"
                       "- **문항 다섯 개** — 평균 응답 시간은 4분이다.\n"
                       "- **다음 단계** — 결과는 회의에서 정리한다.\n"),
    "코드와 대조 예시": HEAD + ("설정은 파일 하나로 끝난다. 예시는 `완료했습니다` 처럼 적지 않는다.\n\n"
                       "❌ *\"결과를 공유했습니다.\"* → ✅ **\"결과 공유\"**\n\n"
                       "나머지는 그대로 둔다. 검토는 담당자가 맡는다.\n"),
    "한 문장": HEAD + "결과는 다음 주에 공유한다.\n",
}
PLAIN_HTML = ("<!doctype html><html><head><meta name=\"form\" content=\"prose\"></head><body>"
              "<h1>조사 결과</h1><p>조사 대상은 실 단위로 정했다.</p><p>응답은 익명으로 받았다.</p>"
              "<ul><li>회수율은 82%이다.</li><li>결과는 다음 주에 공유한다.</li></ul></body></html>")
POLITE_DOC = HEAD + ("조사 대상은 실 단위로 정했습니다. 응답은 익명으로 받았습니다. 회수율은 82%입니다. "
                     "두 값을 따로 집계했습니다. 결과는 다음 주에 공유합니다.\n")
#: 합쇼체 문서에 해라체 한 줄
SLIP = "두 값을 따로 집계했다."
MIXED_POLITE = HEAD + ("조사 대상은 실 단위로 정했습니다. 응답은 익명으로 받았습니다.\n\n"
                       "회수율은 82%입니다.\n\n" + SLIP + "\n\n결과는 다음 주에 공유합니다.\n")
#: 해라체 문서에 합쇼체 한 줄
POLITE_SLIP = "결과는 다음 주에 공유합니다."
MIXED_PLAIN = HEAD + ("조사 대상은 실 단위로 정했다. 응답은 익명으로 받았다.\n\n회수율은 82%이다.\n\n"
                      "두 값을 따로 집계했다.\n\n" + POLITE_SLIP + "\n")
#: 두 말투가 비슷하게 많음 — 어느 쪽에 맞출지 못 정한다
EVEN = HEAD + ("조사 대상은 실 단위로 정했습니다. 응답은 익명으로 받았습니다.\n\n"
               "회수율은 82%이다. 두 값을 따로 집계했다.\n")
MIXED_HTML = ("<!doctype html><html><head><meta name=\"form\" content=\"prose\"></head><body>"
              "<h1>조사 결과</h1><p>조사 대상은 실 단위로 정했습니다.</p><p>응답은 익명으로 받았습니다.</p>"
              "<ul><li>회수율은 82%입니다.</li><li>" + SLIP + "</li></ul></body></html>")


def load(switch: str):
    with mock.patch.dict(os.environ, {"KOREAN_QA_PERSONAL_RULES": switch}):
        spec = importlib.util.spec_from_file_location(f"dsc_{switch}", repo_paths.CHECKER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    switch = "off"

    @classmethod
    def setUpClass(cls) -> None:
        if not repo_paths.CHECKER.is_file():
            raise unittest.SkipTest(f"검사기가 없습니다: {repo_paths.CHECKER}")
        cls.dsc = load(cls.switch)

    def scan(self, text: str, name: str = "doc.md", rules=None):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / name
            p.write_text(text, encoding="utf-8")
            f = self.dsc.scan_md if name.endswith(".md") else self.dsc.scan_html
            return f(str(p), False, None, rules)[:2]

    @staticmethod
    def of(items, kind):
        return [m for k, m in items if k == kind]


class SharedTests(Base):
    switch = "off"

    def test_switch_is_off(self) -> None:
        self.assertFalse(self.dsc.PROFILE)

    def test_consistent_plain_documents_are_quiet(self) -> None:
        """해라체로 통일한 글은 결함이 아니다 — 여기서 지적하면 받아 쓰는 사람이 검사기를 끈다."""
        for label, text in PLAIN_DOCS.items():
            with self.subTest(case=label):
                err, warn = self.scan(text)
                for kind in ("반말 서술형", "말투 섞임"):
                    self.assertEqual(self.of(err, kind) + self.of(warn, kind), [], f"{label} — {kind}")

    def test_consistent_plain_html_is_quiet(self) -> None:
        err, warn = self.scan(PLAIN_HTML, "doc.html")
        for kind in ("반말 서술형", "말투 섞임"):
            self.assertEqual(self.of(err, kind) + self.of(warn, kind), [], kind)

    def test_consistent_polite_document_is_quiet(self) -> None:
        err, warn = self.scan(POLITE_DOC)
        self.assertEqual(self.of(err, "말투 섞임") + self.of(warn, "말투 섞임"), [])

    def test_a_plain_line_in_a_polite_document_is_an_error(self) -> None:
        err, warn = self.scan(MIXED_POLITE)
        mixed = self.of(err, "말투 섞임")
        self.assertEqual(len(mixed), 1, err)
        self.assertIn(SLIP, mixed[0])
        self.assertTrue(mixed[0].startswith("12행"), mixed[0])
        self.assertEqual(self.of(err, "반말 서술형"), [])

    def test_a_polite_line_in_a_plain_document_is_an_error(self) -> None:
        err, _warn = self.scan(MIXED_PLAIN)
        mixed = self.of(err, "말투 섞임")
        self.assertEqual(len(mixed), 1, err)
        self.assertIn(POLITE_SLIP, mixed[0])

    def test_mixed_html_is_an_error(self) -> None:
        err, _warn = self.scan(MIXED_HTML, "doc.html")
        mixed = self.of(err, "말투 섞임")
        self.assertEqual(len(mixed), 1, err)
        self.assertIn(SLIP, mixed[0])

    def test_even_mix_goes_to_a_person(self) -> None:
        """주인 말투를 못 정하면 줄을 고르지 않고 주의 한 줄 — 침묵하면 그 섞임은 미탐이다."""
        err, warn = self.scan(EVEN)
        self.assertEqual(self.of(err, "말투 섞임") + self.of(err, "반말 서술형"), [])
        self.assertEqual(len(self.of(warn, "말투 섞임")), 1, warn)

    def test_opt_in_brings_back_the_personal_standard(self) -> None:
        on = self.dsc.Selection(on={"반말 서술형"}, source="시험")
        err, _warn = self.scan(PLAIN_DOCS["보고서 문단"], rules=on)
        self.assertTrue(self.of(err, "반말 서술형"))
        self.assertEqual(self.of(err, "말투 섞임"), [])

    def test_instruction_file_is_left_out(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "AGENTS.md"
            p.write_text(MIXED_POLITE, encoding="utf-8")
            err, _warn, _ = self.dsc.scan_md(str(p))
        self.assertEqual(self.of(err, "말투 섞임") + self.of(err, "반말 서술형"), [])

    def test_publish_gate_follows_opt_in(self) -> None:
        """`--no-rules` 는 끄고 낮춘 것만 무시한다 — 켠 합쇼체 기준을 발행 순간에 잃지 않게."""
        with tempfile.TemporaryDirectory() as d:
            doc = Path(d) / "doc.md"
            doc.write_text(PLAIN_DOCS["보고서 문단"], encoding="utf-8")
            env = dict(os.environ, KOREAN_QA_PERSONAL_RULES="off")
            run = lambda: subprocess.run(  # noqa: E731
                [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(doc), "--no-rules"],
                capture_output=True, text=True, encoding="utf-8", env=env, cwd=d).stdout
            self.assertNotIn("[반말 서술형]", run())
            (Path(d) / "korean-qa.toml").write_text(
                '[rules]\non = ["반말 서술형"]\noff = ["모호한 지칭"]\n', encoding="utf-8")
            out = run()
            self.assertIn("[반말 서술형]", out)
            self.assertIn("✓ 반말 서술형 — 켬", out)
            self.assertNotIn("⊘", out, "발행 게이트가 설정의 끔을 따랐습니다")


class PersonalTests(Base):
    switch = "on"

    def test_switch_is_on(self) -> None:
        self.assertTrue(self.dsc.PROFILE)

    def test_plain_documents_are_still_errors(self) -> None:
        for label in ("보고서 문단", "기사체와 존댓말 인용", "목록과 근거 문장"):
            with self.subTest(case=label):
                err, _warn = self.scan(PLAIN_DOCS[label])
                self.assertTrue(self.of(err, "반말 서술형"), label)
                self.assertEqual(self.of(err, "말투 섞임"), [], label)

    def test_mixed_document_keeps_the_old_kind(self) -> None:
        err, warn = self.scan(MIXED_POLITE)
        plain = self.of(err, "반말 서술형")
        self.assertEqual(len(plain), 1, err)
        self.assertIn(SLIP, plain[0])
        self.assertEqual(self.of(err, "말투 섞임"), [])
        # 옛 「말투 섞임」 주의는 서술 문장 12개 미만이면 판단하지 않는다(`register_mix`)
        self.assertEqual(self.of(warn, "말투 섞임"), [])

    def test_quotes_code_and_examples_stay_out(self) -> None:
        err, _warn = self.scan(PLAIN_DOCS["코드와 대조 예시"])
        for m in self.of(err, "반말 서술형"):
            self.assertNotIn("완료했습니다", m)
            self.assertNotIn("공유했습니다", m)


if __name__ == "__main__":
    unittest.main()
