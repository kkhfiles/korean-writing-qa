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
        # 저장소 밖에 만든다 — 안에 만들면 지우기가 실패한 판이 저장소에 남는다
        #   (2026-09-23 · 빈 폴더 둘이 추적 안 된 채 뿌리에 쌓여 있었다)
        self.dir = tempfile.mkdtemp(prefix="known-scope-")
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
        # 경로 범위가 없어도 되는 것은 **문맥으로 좁힌 짝**뿐이다(2026-09-23).
        #   「테스트 러너」처럼 문맥이 붙으면 낱말을 연 것이 아니라 그 짝을 연
        #   것이다. 이 목록은 공개 저장소에 실려 다른 프로젝트 경로를 범위로 못
        #   적는다 — 적으면 내부 경로가 나간다. 그래서 그 경우는 문맥으로 좁힌다.
        #   ⛔ 낱말만(문맥 `*`) 모든 문서에 여는 것은 여전히 막는다.
        wide = [r for r in rows
                if r.get("scope", "*") == "*" and r.get("context", "*") == "*"]
        self.assertEqual([], wide,
                         "범위도 문맥도 없이 모든 문서에 열어 준 낱말이 있습니다: "
                         + ", ".join(r["word"] for r in wide[:5]))
        for r in rows:
            self.assertTrue(r.get("why"), f"{r['word']} 에 근거가 없습니다")


class KnownWordContextTests(unittest.TestCase):
    """문맥을 적어 등록한 것이 **쓰임마다** 듣는지 본다.

    2026-09-23 에 문맥 한정 등록이 처음 들어오자 두 가지가 드러났다. 예전에는
    낱말마다 첫 문장 하나를, 화면용으로 56자에서 자른 것을 대 봤다.
    · 마침표 없는 목록은 한 문장으로 뭉쳐 둘째 줄부터의 문맥이 안 보였다
    · 첫 쓰임이 등록된 문맥이면 뒤의 등록 안 된 쓰임까지 가려졌다(미탐)
    """

    #: 발췌 56자를 넘기는 첫 줄 — 옛 판에서는 둘째 줄 문맥이 여기서 잘렸다
    LONG = "- 이 줄은 일부러 길게 써서 화면에 보이는 발췌 쉰여섯 자를 넘기도록 만든 첫째 항목\n"

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="known-ctx-")
        self.known = os.path.join(self.dir, "known.jsonl")
        with io.open(self.known, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"word": "러너/NNG", "context": "테스트 러너", "scope": "*",
                                "why": "시험용 — 시험 실행기"}, ensure_ascii=False) + "\n")

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def doc(self, body):
        p = os.path.join(self.dir, "d.md")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write("# 점검\n\n" + body)
        return p

    def test_a_registered_context_past_the_first_line_is_folded(self) -> None:
        out = run(self.doc(self.LONG + "- 테스트 러너를 상시 가동\n"),
                  "--known", self.known, "--top", "200")
        self.assertNotIn("러너/NNG", out, "둘째 줄의 등록된 문맥이 안 들었습니다")

    def test_an_unregistered_usage_is_not_hidden_by_a_registered_one(self) -> None:
        """⛔ 핵심 — 먼저 나온 등록된 쓰임이 뒤의 것을 덮으면 안 된다."""
        out = run(self.doc("- 테스트 러너를 상시 가동\n- 마라톤 러너가 결승선에 닿음\n"),
                  "--known", self.known, "--top", "200")
        self.assertIn("러너/NNG", out, "등록 안 된 쓰임이 가려졌습니다")
        row = next(l for l in out.splitlines() if "러너/NNG" in l)
        self.assertIn("마라톤", row, "보여 주는 문장이 고칠 쓰임이 아닙니다")


if __name__ == "__main__":
    unittest.main()
