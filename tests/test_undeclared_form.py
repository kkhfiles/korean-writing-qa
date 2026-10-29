"""형식을 안 적은 문서 — 공유 기본은 산문인지 판별해서 보고, 개인 스위치나 조직 설정이 있으면 지금처럼 개조식으로 본다.

(2026-10-29 사용자 — 「기본값이 개조식인게 아니라 산문인지 개조식인지를 보고 모드가 바뀌게 해야하는거
아니니? 나는 취향이 산문이 아니라서 개인 설정으로 한 것뿐」)

**지키는 것**
- 개인 스위치가 없으면 산문 글의 서술형 종결이 빠지고, 그렇게 봤다고 「형식 미표기」에 적나 — 조용히 빼지 않게
- 개인 스위치가 있으면 지금처럼 개조식으로 보고 형식만 물어보나
- 조직 설정 `[form] undeclared = "structured"` 이 개인 스위치보다 앞서나 · 값이 틀리면 멈추나
- 표와 라벨이 뼈대인 문서는 산문으로 안 넘어가나 — 판별이 정당한 지적을 지우지 않게
- 형식을 적었으면 선언대로 보나 · 발행 게이트(`--no-rules`)는 조직 설정을 안 읽나
- HTML 도 지적 쏠림으로 판별하나
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

PROSE = "# 공모 안내\n\n" + "\n\n".join(
    f"이번 공모는 업무에 쓴 AI 활용법을 동료와 나누려고 마련했습니다. {i}번째 안내입니다."
    for i in range(1, 13)) + "\n"
STRUCTURED = ("# 주간 점검\n\n**이번 주 상태와 다음 행동** — 한 장 조망\n\n"
              "| 항목 | 상태 |\n|---|---|\n| 빌드 | 통과 |\n| 배포 | 대기 |\n| 시험 | 1,349개 통과 |\n\n"
              "- **담당**: 품질팀\n- **기한**: 11월 5일\n- **위험**: 배포 창이 좁음\n"
              "- **다음 행동**: 배포 일정을 확정합니다.\n- **근거**: 지난주 회의\n")
HTML_PROSE = ("<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>안내</title></head><body>"
              "<h1>공모 안내</h1>" + "".join(
                  f"<p>이번 공모는 업무에 쓴 AI 활용법을 동료와 나누려고 마련했습니다. {i}번째 안내입니다.</p>"
                  for i in range(1, 13)) + "</body></html>\n")


class UndeclaredFormTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def run_checker(self, name: str, text: str, personal: str = "off", *flags: str) -> tuple[int, str]:
        doc = self.dir / name
        doc.write_text(text, encoding="utf-8")
        env = dict(os.environ, KOREAN_QA_PERSONAL_RULES=personal)
        r = subprocess.run([sys.executable, "-X", "utf8", str(repo_paths.CHECKER), *flags, str(doc)],
                           capture_output=True, text=True, encoding="utf-8", env=env, cwd=self.dir)
        return r.returncode, r.stdout

    def test_shared_default_reads_prose_as_prose_and_says_so(self) -> None:
        _, out = self.run_checker("a.md", PROSE)
        self.assertNotIn("[서술형 종결]", out, "형식을 안 적은 산문 글에 개조식 지적이 쏟아졌습니다")
        self.assertIn("산문으로 보고 개조식 검사", out, "산문으로 봤다는 사실을 알리지 않았습니다")

    def test_personal_switch_keeps_the_structured_default(self) -> None:
        _, out = self.run_checker("a.md", PROSE, "on")
        self.assertIn("[서술형 종결]", out, "개인 스위치가 있는데 개조식 검사를 뺐습니다")
        self.assertIn("형식을 안 적었다", out)

    def test_organisation_setting_comes_first(self) -> None:
        (self.dir / "korean-qa.toml").write_text('[form]\nundeclared = "structured"\n', encoding="utf-8")
        _, out = self.run_checker("a.md", PROSE, "off")
        self.assertIn("[서술형 종결]", out, "조직 설정 「structured」보다 판별이 앞섰습니다")

    def test_a_typo_in_the_setting_stops(self) -> None:
        (self.dir / "korean-qa.toml").write_text('[form]\nundeclared = "structure"\n', encoding="utf-8")
        rc, out = self.run_checker("a.md", PROSE)
        self.assertEqual(1, rc, out)
        self.assertIn("undeclared", out)

    def test_structured_document_is_not_read_as_prose(self) -> None:
        _, out = self.run_checker("b.md", STRUCTURED)
        self.assertNotIn("산문으로 보고", out, "표와 라벨이 뼈대인 문서를 산문으로 봤습니다")
        self.assertIn("[서술형 종결]", out, "개조식 문서의 정당한 지적이 사라졌습니다")

    def test_declared_form_wins(self) -> None:
        _, out = self.run_checker("a.md", "---\nform: structured\n---\n\n" + PROSE)
        self.assertIn("[서술형 종결]", out)
        self.assertNotIn("산문으로 보고", out)

    def test_publish_gate_ignores_the_organisation_setting(self) -> None:
        (self.dir / "korean-qa.toml").write_text('[form]\nundeclared = "structured"\n', encoding="utf-8")
        _, out = self.run_checker("a.md", PROSE, "off", "--no-rules")
        self.assertIn("산문으로 보고", out, "발행 게이트가 조직 설정을 읽었습니다")

    def test_html_is_detected_by_the_flood(self) -> None:
        _, out = self.run_checker("c.html", HTML_PROSE)
        self.assertNotIn("[서술형 문단]", out)
        self.assertIn('<meta name="form" content="structured">', out)
        _, kept = self.run_checker("c.html", HTML_PROSE, "on")
        self.assertNotIn("형식 미표기", kept, "개조식 설정의 HTML 에 없던 주의를 더했습니다")


if __name__ == "__main__":
    unittest.main()
