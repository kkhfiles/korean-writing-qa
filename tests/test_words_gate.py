"""`words` 게이트가 판정을 내고, 그 판정을 통과할 길이 있는지 본다.

**왜 있나.** 이 저장소가 지키는 것은 「문제가 되는 한글이 나오면 안 된다」이고,
비용은 근거가 못 된다(`CLAUDE.md`). 그래서 드문 단어는 **고치거나 근거를 적어
등록하거나** 둘 중 하나를 해야 지나간다.

⛔ **열쇠를 함께 시험한다.** 판정만 넣고 통과할 길을 안 만들면 사람이 게이트를
   끈다 — 2026-09-16 에 발행 게이트로 그 실수를 한 번 했다.
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

#: 「되먹임」은 사용자가 4회차에 짚은 말이고 기준선이 0이다 — 반드시 막혀야 한다.
DIRTY = "# 계획\n\n되먹임을 보는 구조다. 되먹임이 없으면 아무도 모른다.\n"
CLEAN = "# 계획\n\n결과를 다시 보는 구조다. 확인이 없으면 아무도 모른다.\n"


def run(*args):
    done = subprocess.run([sys.executable, "-X", "utf8", SWEEP, *args],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, cwd=ROOT)
    return done.returncode, done.stdout + done.stderr


class WordsGateTests(unittest.TestCase):

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="words-gate-")
        self.known = os.path.join(self.dir, "known.jsonl")
        io.open(self.known, "w", encoding="utf-8", newline="\n").close()
        self.dirty = self._doc("dirty.md", DIRTY)
        self.clean = self._doc("clean.md", CLEAN)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def _doc(self, name, body):
        p = os.path.join(self.dir, name)
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        return p

    def test_an_unresolved_rare_word_fails(self) -> None:
        rc, out = run(self.dirty, "--gate", "--known", self.known, "--top", "50")
        self.assertEqual(1, rc, f"막아야 하는데 통과했습니다: {out[:300]}")
        self.assertIn("되먹이", out)

    def test_the_exit_code_reaches_the_caller(self) -> None:
        """⛔ 종료 코드를 안 넘기면 게이트로 쓰는 쪽이 통과로 읽는다."""
        rc, _ = run(self.dirty, "--gate", "--known", self.known, "--top", "0")
        self.assertEqual(1, rc)

    def test_the_gate_threshold_is_separate_from_the_list_threshold(self) -> None:
        """목록을 보여 주는 문턱과 막는 문턱은 같을 이유가 없다.

        사용자가 짚은 「가리다」가 기준선 43회로 **40 과 60 사이**에 있었다.
        보여 주는 문턱(40)만 있었으면 그 말은 영영 안 걸린다(2026-09-16 실측).
        """
        doc = self._doc("between.md",
                        "# 계획\n\n미정 항목은 §2에 가려 두었다.\n")
        rc_low, _ = run(doc, "--gate", "--known", self.known,
                        "--gate-max", "40", "--top", "0")
        rc_high, out = run(doc, "--gate", "--known", self.known,
                           "--gate-max", "60", "--top", "50")
        self.assertEqual(1, rc_high, f"문턱 60인데 안 막았습니다: {out[:300]}")
        self.assertIn("가리", out)
        self.assertNotEqual(
            rc_low, rc_high,
            "문턱 40 과 60 의 판정이 같습니다 — 문턱이 따로 도는지 확인하십시오")

    def test_accepting_the_word_lets_it_through(self) -> None:
        rc, _ = run("--accept", "되먹이/NNG", "--context", "*", "--why", "시험용",
                    "--known", self.known)
        self.assertEqual(0, rc)
        rc, out = run(self.dirty, "--gate", "--known", self.known, "--top", "0")
        self.assertEqual(0, rc, f"등록했는데 막혔습니다: {out[:300]}")

    def test_the_template_round_trips(self) -> None:
        """⛔ 여기가 열쇠다 — 서식을 받아 `why` 만 채우면 한 번에 등록된다."""
        tmpl = os.path.join(self.dir, "review.jsonl")
        run(self.dirty, "--gate", "--known", self.known, "--top", "0",
            "--emit-template", tmpl)
        self.assertTrue(os.path.exists(tmpl), "서식이 안 만들어졌습니다")
        rows = []
        with io.open(tmpl, encoding="utf-8") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    row = json.loads(line)
                    row["why"] = "시험용 근거"
                    rows.append(row)
        self.assertTrue(rows, "서식이 비었습니다")
        with io.open(tmpl, "w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        rc, out = run("--accept-file", tmpl, "--known", self.known)
        self.assertEqual(0, rc, out[:300])
        rc, out = run(self.dirty, "--gate", "--known", self.known, "--top", "0")
        self.assertEqual(0, rc, f"한 번에 등록했는데 막혔습니다: {out[:300]}")

    def test_a_bulk_entry_without_a_reason_is_refused(self) -> None:
        """근거 없이 열어 준 짝은 나중에 왜 열렸는지 아무도 모른다."""
        tmpl = os.path.join(self.dir, "noreason.jsonl")
        with io.open(tmpl, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"word": "되먹이/NNG", "context": "*", "why": ""},
                               ensure_ascii=False) + "\n")
        rc, out = run("--accept-file", tmpl, "--known", self.known)
        self.assertEqual(1, rc, "근거 없이 등록됐습니다")
        self.assertIn("근거", out)

    def test_a_clean_document_passes(self) -> None:
        rc, out = run(self.clean, "--gate", "--known", self.known,
                      "--gate-max", "60", "--top", "0")
        self.assertEqual(0, rc, f"깨끗한 문서가 막혔습니다: {out[:400]}")


if __name__ == "__main__":
    unittest.main()
