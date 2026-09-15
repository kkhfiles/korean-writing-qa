"""게이트의 시험 통로가 상태를 안 건드리는지 본다.

**왜 있나.** 게이트는 「파일당 세션 1회」로 같은 파일의 둘째 호출을 조용히
넘긴다. 그 성질을 모르고 같은 파일로 두 번 재면 **「이 도구를 안 본다」로
읽힌다** — 2026-09-15 에 그 오독을 세 번 했다. `--probe` 는 상태를 읽지도
쓰지도 않으므로 몇 번을 불러도 같은 답이 나온다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GATE = os.path.join(ROOT, "hooks", "doc-style-gate.py")

BAD = "# 점검\n\n- **언제 도나** — 매일\n- 새 자료는 해당 폴더에\n"


class GateProbeTests(unittest.TestCase):

    def setUp(self) -> None:
        # ⛔ 시스템 임시 폴더에 두면 안 된다 — 게이트의 SKIP 이 `Temp` 를 건너뛴다.
        #    안 걸리는 자리에서 재고 「안 걸린다」고 적으면 맞는 진단을 지운다.
        self.dir = tempfile.mkdtemp(prefix=".gate-probe-", dir=ROOT)
        self.doc = os.path.join(self.dir, "probe-target.md")
        with open(self.doc, "w", encoding="utf-8", newline="\n") as f:
            f.write(BAD)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def _run(self, *args):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Write",
                   "session_id": "probe-session",
                   "tool_input": {"file_path": self.doc},
                   "tool_response": {"filePath": self.doc}}
        done = subprocess.run([sys.executable, "-X", "utf8", GATE, *args],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=180)
        return done.stdout + done.stderr

    def test_probe_gives_the_same_answer_twice(self) -> None:
        """상태를 안 쓰므로 두 번 불러도 같은 답이 나온다."""
        first = self._run("--probe")
        second = self._run("--probe")
        self.assertIn("규칙 위반", first, f"첫 호출이 조용합니다: {first[:200]}")
        self.assertIn("규칙 위반", second,
                      "둘째 호출이 조용합니다 — `--probe` 가 상태를 쓰고 있습니다")

    def test_probe_does_not_silence_the_real_path(self) -> None:
        """시험 통로로 불러도 실제 경로의 상태를 안 먹는다."""
        self._run("--probe")
        real = self._run()
        self.assertIn("규칙 위반", real,
                      "`--probe` 가 실제 경로의 「파일당 1회」를 먹었습니다")


if __name__ == "__main__":
    unittest.main()
