"""게이트가 1층 판정을 **해시에 묶어 자동으로 적는지** 본다.

**왜 있나.** 사람이 따로 기록하게 하면 또 「기억해야 도는 구조」가 된다 —
2층 실행율 3.8% 가 그 결과다. 기계가 낸 판정은 기계가 적어야 발행 게이트와
정지 장치가 그것을 믿고 판정할 수 있다.
"""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import repo_paths  # noqa: E402

GATE = os.path.join(ROOT, "hooks", "doc-style-gate.py")
TOOL = os.path.join(ROOT, "scripts", "check_record.py")

CLEAN = "# 계획\n\n**요점 셋** — 하나 · 둘 · 셋\n"
DIRTY = "# 계획\n\n- **언제 도나** — 매일\n- 새 자료는 해당 폴더에\n"


class GateRecordsTests(unittest.TestCase):

    def setUp(self) -> None:
        # ⛔ 게이트가 Temp·scratchpad 를 건너뛰므로 거기는 안 된다 — 그렇다고 저장소
        #    안에 두면 지우기에 실패한 판이 뿌리에 쌓인다(`repo_paths.gate_scratch`).
        self.dir = repo_paths.gate_scratch(".gate-rec-")
        self.store = os.path.join(self.dir, "store.jsonl")
        self.env = dict(os.environ, KOREAN_CHECK_RECORD=self.store)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def _doc(self, name, body):
        p = os.path.join(self.dir, name)
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        return p

    def _fire(self, path, *args):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Write",
                   "session_id": "rec-session",
                   "tool_input": {"file_path": path},
                   "tool_response": {"filePath": path}}
        subprocess.run([sys.executable, "-X", "utf8", GATE, *args],
                       input=json.dumps(payload, ensure_ascii=False),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=240, env=self.env)

    def _status(self, path):
        done = subprocess.run(
            [sys.executable, "-X", "utf8", TOOL, "status", path, "--json"],
            capture_output=True, text=True, encoding="utf-8",
            env=self.env, cwd=ROOT, timeout=60)
        return json.loads(done.stdout.strip() or "{}")

    def test_a_clean_document_is_recorded_as_pass(self) -> None:
        p = self._doc("clean.md", CLEAN)
        self._fire(p)
        self.assertEqual("pass", self._status(p)["stages"]["structure"],
                         "깨끗한 문서인데 통과가 안 적혔습니다")

    def test_a_dirty_document_is_recorded_as_fail(self) -> None:
        p = self._doc("dirty.md", DIRTY)
        self._fire(p)
        self.assertEqual("fail", self._status(p)["stages"]["structure"],
                         "지적이 있는데 실패가 안 적혔습니다")

    def test_editing_after_the_pass_drops_it(self) -> None:
        """⛔ 핵심 — 통과한 뒤 고치면 그 통과는 지금 내용의 것이 아니다."""
        p = self._doc("edited.md", CLEAN)
        self._fire(p)
        self.assertEqual("pass", self._status(p)["stages"]["structure"])
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(CLEAN + "\n- 새 자료는 해당 폴더에\n")
        self.assertIsNone(self._status(p)["stages"]["structure"],
                          "고친 뒤에도 옛 통과가 살아 있습니다")

    def test_probe_does_not_record(self) -> None:
        """시험 통로는 상태도 기록도 안 건드린다."""
        p = self._doc("probe.md", CLEAN)
        self._fire(p, "--probe")
        self.assertIsNone(self._status(p)["stages"]["structure"],
                          "`--probe` 가 기록을 남겼습니다")


if __name__ == "__main__":
    unittest.main()
