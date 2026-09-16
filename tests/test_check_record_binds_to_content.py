"""검사 통과 기록이 **내용에 묶여 있는지** 본다.

**왜 있나.** 「검사했다」만 기록하면 옛 판을 검사한 뒤 고쳐서 내보내는 길이
열린다(2026-09-16 외부 검토 지적). 한 글자만 고쳐도 기록이 안 맞아야 한다.
검사기가 바뀐 뒤의 옛 통과도 못 믿는다.
"""
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "scripts", "check_record.py")


def load_module(store):
    """저장소 경로를 갈아 끼운 판을 새로 읽는다 — 진짜 기록을 안 건드리려고."""
    os.environ["KOREAN_CHECK_RECORD"] = store
    spec = importlib.util.spec_from_file_location("check_record_t", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CheckRecordTests(unittest.TestCase):

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="check-record-")
        self.doc = os.path.join(self.dir, "doc.md")
        self.store = os.path.join(self.dir, "store.jsonl")
        self._write("# 계획\n\n**요점 셋** — 하나 · 둘 · 셋\n")
        self.mod = load_module(self.store)

    def tearDown(self) -> None:
        os.environ.pop("KOREAN_CHECK_RECORD", None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, body):
        with io.open(self.doc, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)

    def test_a_pass_is_seen(self) -> None:
        self.mod.record(self.doc, "structure", "pass")
        self.assertEqual("pass", self.mod.status(self.doc)["stages"]["structure"])

    def test_editing_the_file_invalidates_the_pass(self) -> None:
        """⛔ 여기가 핵심 — 검사한 뒤 고치면 그 통과는 이 내용의 것이 아니다."""
        self.mod.record(self.doc, "structure", "pass")
        self._write("# 계획\n\n**요점 셋** — 하나 · 둘 · 넷\n")
        self.assertIsNone(self.mod.status(self.doc)["stages"]["structure"],
                          "한 글자를 고쳤는데 옛 통과가 그대로 살아 있습니다")

    def test_line_endings_do_not_matter(self) -> None:
        """줄 끝만 바뀐 것은 같은 글이다 — 그것으로 기록이 깨지면 소음이 된다."""
        self.mod.record(self.doc, "structure", "pass")
        body = io.open(self.doc, encoding="utf-8", newline="").read()
        with io.open(self.doc, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(body)
        self.assertEqual("pass", self.mod.status(self.doc)["stages"]["structure"])

    def test_a_fail_is_not_a_pass(self) -> None:
        self.mod.record(self.doc, "words", "fail")
        self.assertEqual("fail", self.mod.status(self.doc)["stages"]["words"])

    def test_a_later_record_wins(self) -> None:
        """고치고 다시 돌린 경우 — 나중 판정이 이긴다."""
        self.mod.record(self.doc, "words", "fail")
        self.mod.record(self.doc, "words", "pass")
        self.assertEqual("pass", self.mod.status(self.doc)["stages"]["words"])

    def test_an_old_record_is_not_trusted(self) -> None:
        """규칙이 바뀌었을 수 있으므로 오래된 통과는 안 믿는다."""
        self.mod.record(self.doc, "structure", "pass")
        rows = io.open(self.store, encoding="utf-8").read().splitlines()
        stale = rows[-1].replace(
            f'"when": {self.mod.load()[-1]["when"]}',
            f'"when": {time.time() - (self.mod.STALE_DAYS + 1) * 86400}')
        with io.open(self.store, "w", encoding="utf-8", newline="\n") as f:
            f.write(stale + "\n")
        self.assertIsNone(self.mod.status(self.doc)["stages"]["structure"],
                          f"{self.mod.STALE_DAYS}일보다 오래된 통과를 믿고 있습니다")

    def test_require_fails_when_a_stage_is_missing(self) -> None:
        env = dict(os.environ, KOREAN_CHECK_RECORD=self.store)
        self.mod.record(self.doc, "structure", "pass")
        done = subprocess.run(
            [sys.executable, "-X", "utf8", TOOL, "status", self.doc,
             "--require", "structure,words,judgment"],
            capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
        self.assertEqual(1, done.returncode, done.stdout + done.stderr)
        self.assertIn("words", done.stdout)

    def test_require_passes_when_all_stages_are_there(self) -> None:
        env = dict(os.environ, KOREAN_CHECK_RECORD=self.store)
        for stage in self.mod.STAGES:
            self.mod.record(self.doc, stage, "pass")
        done = subprocess.run(
            [sys.executable, "-X", "utf8", TOOL, "status", self.doc,
             "--require", ",".join(self.mod.STAGES)],
            capture_output=True, text=True, encoding="utf-8", env=env, cwd=ROOT)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
