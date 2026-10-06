"""사이트 배포 직전에 **배포되는 원본이 한글 검사를 다 거쳤는지** 보는지 확인한다 — 모델은 안 부른다.

**왜 있나**(2026-10-06 사용자 「디스패치 왜 검사 안함?? 검사하게 만드세요」) — 발행 게이트는
노션 · 슬라이드 · PDF 명령과 Artifact 만 발행으로 봤다. 사이트 배포 명령은 대상 파일을 적지 않아
7일에 19회 배포가 한 번도 안 걸렸고, 그 사이트에서 사용자가 한글 21건을 짚었다.

**막는 것과 여는 것을 짝으로 본다** — 열 길이 없는 자물쇠는 넘기기를 습관으로 만든다.
- 배포 목록(`sources.json`)을 그대로 읽어 원본을 정한다 · 뺄 것(`exclude`)은 뺀다
- 모든 원본 — 1층 오류 · 답을 못 받은 사람 확인이 있으면 막는다
- 지난 통과 뒤 바뀐 원본 — 판정기가 안 본 줄 · 판단 기록 · 주의 검토 기록을 요구한다
- 통과하면 원본의 내용 해시를 적어 다음에는 바뀐 것만 다시 요구한다
- `cd` · `--prefix` 를 따라가고, 따옴표 안의 배포 명령은 배포로 안 본다
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "doc-style-gate.py"
RECORDER = ROOT / "scripts" / "check_record.py"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import layer2_coverage as coverage  # noqa: E402
import gate_result  # noqa: E402

PAGE = ("<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><title>업무 비서 소개</title>"
        "</head><body>\n<h1>업무 비서 소개</h1>\n"
        "<p class=\"lede\">마감 기준 업무 정리 · 오늘 시작할 일 표시</p>\n"
        "<ul><li>마감일 기준 착수일 계산</li><li>진행 기록 자동 수집</li></ul>\n</body></html>\n")
CONFIG = ('[deploy]\nmanifest = "sources.json"\nfield = "from"\n'
          'exclude = ["*/state/*"]\n')


class DeployGateTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.site = t / "host"
        self.content = t / "content"
        (self.content / "state").mkdir(parents=True)
        self.site.mkdir()
        self.page = self.content / "home.html"
        self.page.write_text(PAGE, encoding="utf-8")
        # 개인 보드 같은 것 — 사람이 쓴 글이 아니라 빼 둔다(오류가 있어도 안 본다)
        (self.content / "state" / "board.html").write_text(
            PAGE.replace("진행 기록 자동 수집", "진행 기록을 자동으로 모은다."), encoding="utf-8")
        (self.site / "korean-qa.toml").write_text(CONFIG, encoding="utf-8")
        (self.site / "sources.json").write_text(json.dumps([
            {"to": "ko/index.html", "from": self.page.as_posix()},
            {"to": "board/index.html", "from": (self.content / "state" / "board.html").as_posix()},
            {"to": "favicon.svg", "from": (self.content / "icon.svg").as_posix()},
        ]), encoding="utf-8")
        self.log, self.answers = t / "judge.jsonl", t / "answers.jsonl"
        self.passes, self.store = t / "deploy-pass.jsonl", t / "pass.jsonl"
        self.env = dict(os.environ, KOREAN_QA_JUDGE_LOG=str(self.log),
                        KOREAN_QA_ANSWER_LOG=str(self.answers), KOREAN_QA_DEPLOY_PASS=str(self.passes),
                        KOREAN_CHECK_RECORD=str(self.store), KOREAN_QA_RECORDER=str(RECORDER),
                        KOREAN_QA_COVERAGE=str(ROOT / "scripts" / "layer2_coverage.py"),
                        KOREAN_QA_JUDGE=str(ROOT / "scripts" / "judge_layer2.py"))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def deploy(self, cmd: str = "npm run publish", cwd: Path | None = None,
               probe: bool = True) -> tuple[int, str]:
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "session_id": "deploy-t",
                   "cwd": str(cwd or self.site), "tool_input": {"command": cmd}}
        argv = [sys.executable, "-X", "utf8", str(GATE)] + (["--probe"] if probe else [])
        done = subprocess.run(argv, input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=180, env=self.env)
        return gate_result.read(done)

    def judged(self, asks: list | None = None) -> None:
        lines = coverage.read_doc(self.page).splitlines()
        row = {"ok": True, "when": time.time(), "key": coverage.doc_key(self.page),
               "seen": coverage.seen_keys(lines), "asks": asks or []}
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def recorded(self) -> None:
        subprocess.run([sys.executable, "-X", "utf8", str(RECORDER), "record", str(self.page),
                        "--stage", "judgment", "--verdict", "pass", "--note", "남은 지적 없음"],
                       check=True, capture_output=True, env=self.env)

    def test_a_repo_without_deploy_is_not_gated(self) -> None:
        (self.site / "korean-qa.toml").write_text('[rules]\noff = []\n', encoding="utf-8")
        self.assertEqual(0, self.deploy()[0])

    def test_an_unchecked_page_blocks(self) -> None:
        rc, out = self.deploy()
        self.assertEqual(2, rc, out)
        self.assertIn("home.html", out)
        self.assertIn("판정기가 아직 안 본 한글 줄", out)
        self.assertIn("judgment 기록 없음", out)
        self.assertNotIn("board.html", out, "빼 두라고 적은 원본까지 봤습니다")
        self.assertNotIn("icon.svg", out, "글이 아닌 원본까지 봤습니다")

    def test_judged_and_recorded_lets_it_through(self) -> None:
        self.judged()
        self.recorded()
        rc, out = self.deploy()
        self.assertEqual(0, rc, out)

    def test_a_passed_page_is_not_asked_again(self) -> None:
        """안 바뀐 원본까지 매번 기록을 요구하면 기록이 고무도장이 된다."""
        self.judged()
        self.recorded()
        self.assertEqual(0, self.deploy(probe=False)[0])
        self.store.unlink()
        rc, out = self.deploy()
        self.assertEqual(0, rc, f"안 바뀐 원본인데 다시 막았습니다: {out[:300]}")

    def test_the_probe_does_not_record_a_pass(self) -> None:
        self.judged()
        self.recorded()
        self.assertEqual(0, self.deploy()[0])
        self.assertFalse(self.passes.exists(), "시험 통로가 통과 기록을 썼습니다")

    def test_editing_after_a_pass_asks_again(self) -> None:
        self.judged()
        self.recorded()
        self.assertEqual(0, self.deploy(probe=False)[0])
        self.page.write_text(PAGE.replace("</ul>", "<li>회의록 자동 정리</li></ul>"), encoding="utf-8")
        rc, out = self.deploy()
        self.assertEqual(2, rc, "고친 뒤에도 옛 통과로 배포됩니다")
        self.assertIn("판정기가 아직 안 본 한글 줄 1개", out)

    def test_a_layer_one_error_blocks_even_a_passed_page(self) -> None:
        """규칙이 새로 생기면 안 바뀐 원본도 걸려야 한다 — 1층은 싸니 매번 본다."""
        self.page.write_text(PAGE.replace("진행 기록 자동 수집", "진행 기록을 자동으로 모은다."),
                             encoding="utf-8")
        self.judged()
        self.recorded()
        with self.passes.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"page": self.page.as_posix(), "hash": "x"}) + "\n")
        rc, out = self.deploy()
        self.assertEqual(2, rc, out)
        self.assertIn("1층 오류", out)

    def test_an_open_ask_blocks(self) -> None:
        lines = coverage.read_doc(self.page).splitlines()
        n = next(i for i, l in enumerate(lines) if "진행 기록" in l)
        self.judged(asks=[{"line_key": coverage.line_key(lines[n]), "phrase": "진행 기록 자동 수집",
                           "fix": "-"}])
        self.recorded()
        rc, out = self.deploy()
        self.assertEqual(2, rc, out)
        self.assertIn("사람 확인 지적 1개", out)

    def test_cd_and_prefix_are_followed(self) -> None:
        elsewhere = Path(self.tmp.name)
        for cmd in (f'cd "{self.site.as_posix()}" && npm run publish',
                    f'npm --prefix "{self.site.as_posix()}" run publish'):
            with self.subTest(cmd=cmd):
                rc, out = self.deploy(cmd, cwd=elsewhere)
                self.assertEqual(2, rc, f"배포 폴더를 못 따라갔습니다: {out[:200]}")

    def test_a_quoted_deploy_is_not_a_deploy(self) -> None:
        rc, out = self.deploy('git commit -m "npm run publish 뒤 정리"')
        self.assertEqual(0, rc, out)

    def test_an_unreadable_manifest_blocks(self) -> None:
        (self.site / "sources.json").write_text("{깨진", encoding="utf-8")
        rc, out = self.deploy()
        self.assertEqual(2, rc, "배포 목록을 못 읽었는데 그대로 배포됩니다")
        self.assertIn("배포 목록을 못 읽었습니다", out)

    def test_a_broken_check_blocks_instead_of_passing(self) -> None:
        """⛔ 훅이 죽으면 명령은 그대로 돈다 — 설치본 모듈이 옛 판이라 실제로 죽었다."""
        stale = Path(self.tmp.name) / "old_coverage.py"
        stale.write_text("from pathlib import Path\nLOG = Path('x')\n"
                         "def read_doc(p):\n    return Path(p).read_text(encoding='utf-8')\n"
                         "def doc_key(p):\n    return str(p)\n"
                         "def open_asks(key, lines):\n    return []\n"
                         "def open_lines(lines, base, seen):\n    return []\n"
                         "def judged(key, log=None, now=None):\n    return set()\n", encoding="utf-8")
        self.env["KOREAN_QA_COVERAGE"] = str(stale)
        rc, out = self.deploy()
        self.assertEqual(2, rc, f"검사가 죽었는데 배포가 그대로 나갑니다: {out[:300]}")
        self.assertIn("배포 검사를 못 돌렸습니다", out)

    def test_the_escape_hatch_works(self) -> None:
        rc, out = self.deploy("KOREAN_PUBLISH_FORCE=1 npm run publish")
        self.assertEqual(0, rc, out)


if __name__ == "__main__":
    unittest.main()
