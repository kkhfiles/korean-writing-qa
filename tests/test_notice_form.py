"""공지 형식(`form: notice`) — 인사말과 맺음말 문단만 개조식 검사에서 빼고, 표와 목록은 그대로 본다.

(2026-10-30 사용자 — 형식을 「산문 / 개조식」 둘에서 고르면 공지가 어딘가 어긋나 새 값을 두기로 함.
 사내 게시판 공지 61편 중 60편에 인사말이나 맺음말이 있었고 사용자 보고서 454편에는 1편)

**지키는 것**
- 공지로 적은 문서의 인사말, 맺음말, 첫머리 안내 문장은 오류가 아니나 — 표 칸의 서술형은 그대로 오류인가
- 표와 목록 사이에 낀 문단은 앞뒤 문단이 아니라 개조식으로 보나 — 공지가 산문처럼 통째로 빠지지 않게
- HTML 도 같은가
- 형식을 안 적은 공지 — 공유 기본은 잠정으로 공지로 보고 그렇게 봤다고 적나, 개인 스위치가 있으면 지적을 두고 묻기만 하나
- 인사말이 없는 개조식 문서는 공지로 제안하지 않나
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import repo_paths  # noqa: E402

NOTICE = ("# 11월 비용 마감 안내\n\n"
          "안녕하세요, 재무팀 홍길동입니다.\n"
          "11월 비용 마감 일정을 아래와 같이 안내드립니다.\n\n"
          "| 구분 | 마감일 |\n|---|---|\n"
          "| 법인카드 | 12월 3일까지 제출합니다. |\n| 세금계산서 | 12월 5일 |\n\n"
          "문의 사항은 담당자에게 연락 부탁드립니다.\n"
          "감사합니다.\n")
SANDWICH = ("# 점검 안내\n\n안녕하세요, 품질팀입니다.\n\n"
            "- 대상: 전 부서\n\n"
            "가운데 문단은 앞뒤 문단이 아니라 본문입니다.\n\n"
            "- 기한: 11월 5일\n\n감사합니다.\n")
HTML_NOTICE = ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>{meta}<title>안내</title></head><body>"
               "<h1>11월 비용 마감 안내</h1>"
               "<p>안녕하세요, 재무팀 홍길동입니다.</p>"
               "<p>11월 비용 마감 일정을 아래와 같이 안내드립니다.</p>"
               "<table><tr><th>구분</th><th>마감일</th></tr>"
               "<tr><td>법인카드</td><td>12월 3일까지 제출합니다.</td></tr></table>"
               "<p>문의 사항은 담당자에게 연락 부탁드립니다.</p><p>감사합니다.</p></body></html>\n")
STRUCTURED = ("# 주간 점검\n\n**이번 주 상태와 다음 행동** — 한 장 조망\n\n"
              "| 항목 | 상태 |\n|---|---|\n| 빌드 | 통과 |\n| 배포 | 대기 |\n\n"
              "- **다음 행동**: 배포 일정을 확정합니다.\n")


class NoticeFormTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def run_checker(self, name: str, text: str, personal: str = "off") -> str:
        doc = self.dir / name
        doc.write_text(text, encoding="utf-8")
        env = dict(os.environ, KOREAN_QA_PERSONAL_RULES=personal)
        r = subprocess.run([sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(doc)],
                           capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.dir)
        self.assertIn(r.returncode, (0, 1), r.stderr)
        return r.stdout

    def errors(self, out: str) -> list[str]:
        return [l for l in out.splitlines() if "❌" in l]

    def test_declared_notice_spares_the_greeting_and_keeps_the_table(self) -> None:
        errs = self.errors(self.run_checker("n.md", "---\nform: notice\n---\n" + NOTICE))

        self.assertEqual(len(errs), 1, errs)
        self.assertIn("제출합니다", errs[0], "표 칸의 서술형을 놓쳤습니다")

    def test_a_paragraph_between_lists_is_still_body(self) -> None:
        errs = self.errors(self.run_checker("s.md", "---\nform: notice\n---\n" + SANDWICH))

        self.assertTrue(any("가운데 문단" in e for e in errs), "목록 사이 문단까지 뺐습니다")
        self.assertFalse(any("안녕하세요" in e or "감사합니다" in e for e in errs), errs)

    def test_html_notice_matches_markdown(self) -> None:
        meta = '<meta name="form" content="notice">'
        errs = self.errors(self.run_checker("n.html", HTML_NOTICE.format(meta=meta)))

        self.assertEqual(len(errs), 1, errs)
        self.assertIn("제출합니다", errs[0])

    def test_html_paragraph_between_lists_is_still_body(self) -> None:
        html = ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
                "<meta name=\"form\" content=\"notice\"><title>안내</title></head><body>"
                "<h1>점검 안내</h1><p>안녕하세요, 품질팀입니다.</p><ul><li>대상: 전 부서</li></ul>"
                "<p>가운데 문단은 앞뒤 문단이 아니라 본문입니다.</p><ul><li>기한: 11월 5일</li></ul>"
                "<p>감사합니다.</p></body></html>\n")
        errs = self.errors(self.run_checker("s.html", html))

        self.assertTrue(any("가운데 문단" in e for e in errs), "목록 사이 문단까지 뺐습니다")
        self.assertFalse(any("안녕하세요" in e or "감사합니다" in e for e in errs), errs)

    def test_undeclared_notice_is_read_as_a_notice_for_now_and_says_so(self) -> None:
        out = self.run_checker("n.md", NOTICE)

        self.assertIn("잠정으로 공지로 보고", out)
        self.assertIn("form: notice", out)
        self.assertEqual(len(self.errors(out)), 1, "공지로 봤는데 표 칸 말고도 오류가 남았습니다")

    def test_undeclared_html_notice_is_read_as_a_notice_for_now(self) -> None:
        out = self.run_checker("n.html", HTML_NOTICE.format(meta=""))

        self.assertIn("잠정으로 공지로 보고", out)
        self.assertIn('content="notice"', out)

    def test_personal_switch_keeps_the_findings_and_asks(self) -> None:
        out = self.run_checker("n.md", NOTICE, personal="on")

        self.assertIn("공지나 안내 메일로 보이는데", out)
        self.assertTrue(any("감사합니다" in e for e in self.errors(out)),
                        "개조식 설정인데 묻기 전에 지적을 뺐습니다")

    def test_structured_document_is_not_offered_as_a_notice(self) -> None:
        out = self.run_checker("s.md", STRUCTURED)

        self.assertNotIn("공지", out)


if __name__ == "__main__":
    unittest.main()
