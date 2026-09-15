"""정상 판정 목록이 **범위**를 지키는지 본다.

**왜 있나.** 「명사」·「동사」는 이 저장소 글의 주제라 안 쓸 수 없지만, 사람이 쓴
업무 한국어 4,790만 자에서는 각각 12회·9회로 **진짜 드문 말**이다. 낱말만 열어
주면 업무 보고서에 같은 말을 써도 안 걸린다 — 그러면 이 도구가 막으려던 것을
이 도구가 뚫는다. 2026-09-16 외부 검토가 짚은 대목이다.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SWEEP = os.path.join(ROOT, "scripts", "rare_words.py")

#: 문법 용어가 든 문서 — 이 저장소에서는 정상, 업무 문서에서는 지적 대상
BODY = "# 점검\n\n문단의 명사와 동사를 본다. 관형형 어미도 함께 본다.\n"


def run(*args):
    done = subprocess.run([sys.executable, "-X", "utf8", SWEEP, *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=240, cwd=ROOT)
    return done.stdout + done.stderr


class KnownWordScopeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="known-scope-", dir=ROOT)
        self.inside = os.path.join(self.dir, "inside.md")
        self.outside = os.path.join(tempfile.mkdtemp(prefix="known-out-"), "outside.md")
        for p in (self.inside, self.outside):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with io.open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(BODY)
        self.known = os.path.join(self.dir, "known.jsonl")
        rows = [{"word": "명사/NNG", "context": "*",
                 "scope": self.dir.replace(os.sep, "/") + "/*",
                 "why": "시험용 — 이 폴더에서만 정상"}]
        with io.open(self.known, "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(os.path.dirname(self.outside), ignore_errors=True)

    def test_inside_the_scope_it_is_folded(self) -> None:
        out = run(self.inside, "--known", self.known, "--top", "200")
        self.assertNotIn("명사/NNG", out,
                         "범위 안인데 접히지 않았습니다")

    def test_outside_the_scope_it_still_shows(self) -> None:
        """⛔ 여기가 핵심 — 범위 밖에서는 같은 낱말이 그대로 걸려야 한다."""
        out = run(self.outside, "--known", self.known, "--top", "200")
        self.assertIn("명사/NNG", out,
                      "범위 밖인데 접혔습니다 — 정상 판정이 모든 문서에 새고 있습니다")

    def test_all_shows_what_was_folded(self) -> None:
        out = run(self.inside, "--known", self.known, "--top", "200", "--all")
        self.assertIn("명사/NNG", out, "`--all` 인데 접힌 것이 안 보입니다")

    def test_accept_demands_a_reason(self) -> None:
        """근거 없이 열어 준 짝은 나중에 왜 열렸는지 아무도 모른다."""
        done = subprocess.run(
            [sys.executable, "-X", "utf8", SWEEP, "--accept", "갈래/NNG",
             "--context", "두 갈래", "--known", self.known],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        self.assertNotEqual(0, done.returncode,
                            "`--why` 없이도 등록됐습니다")

    def test_the_shipped_list_scopes_domain_words(self) -> None:
        """딸려 오는 목록이 문법 용어를 이 저장소로 좁혀 두었나."""
        shipped = os.path.join(ROOT, "data", "catalog", "known-words.jsonl")
        if not os.path.exists(shipped):
            self.skipTest("목록이 아직 없다")
        with io.open(shipped, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f
                    if l.strip() and not l.startswith("#")]
        self.assertTrue(rows, "목록이 비었습니다")
        wide = [r for r in rows if r.get("scope", "*") == "*"]
        self.assertEqual([], wide,
                         "범위 없이 모든 문서에 열어 준 짝이 있습니다: "
                         + ", ".join(r["word"] for r in wide[:5]))
        for r in rows:
            self.assertTrue(r.get("why"), f"{r['word']} 에 근거가 없습니다")


if __name__ == "__main__":
    unittest.main()
