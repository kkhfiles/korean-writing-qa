"""통과 기록이 없으면 발행이 보류되는지 본다.

**왜 있나.** 안내는 읽고 넘길 수 있다 — 실측 이행율 3.8%. 발행은 되돌릴 수
없으므로 안내가 아니라 **허용 조건**을 바꾼다(2026-09-16 외부 검토 제안).

**푸는 길을 함께 시험한다.** 막기만 하고 풀 길이 없으면 급할 때 사람이 도구를
통째로 끈다. 넘긴 기록이 명령문에 남는 것도 함께 본다.
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
GATE = os.path.join(ROOT, "hooks", "doc-style-gate.py")
TOOL = os.path.join(ROOT, "scripts", "check_record.py")

BODY = "# 계획\n\n**요점 셋** — 하나 · 둘 · 셋\n"
STAGES = ("structure", "words", "judgment")


class PublishRecordTests(unittest.TestCase):

    def setUp(self) -> None:
        # ⛔ 게이트가 Temp·scratchpad 를 건너뛰므로 저장소 안에 만든다.
        self.dir = tempfile.mkdtemp(prefix=".pub-rec-", dir=ROOT)
        self.doc = os.path.join(self.dir, "plan.md")
        with io.open(self.doc, "w", encoding="utf-8", newline="\n") as f:
            f.write(BODY)
        self.store = os.path.join(self.dir, "store.jsonl")
        self.env = dict(os.environ, KOREAN_CHECK_RECORD=self.store)

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def _record(self, *stages):
        for s in stages:
            subprocess.run([sys.executable, "-X", "utf8", TOOL, "record",
                            self.doc, "--stage", s, "--verdict", "pass"],
                           capture_output=True, env=self.env, cwd=ROOT, timeout=60)

    def _publish(self, prefix=""):
        cmd = f"{prefix}python notion.py create --md {self.doc}".strip()
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "session_id": "pub-session", "tool_input": {"command": cmd}}
        done = subprocess.run([sys.executable, "-X", "utf8", GATE],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=240, env=self.env)
        return done.returncode, done.stdout + done.stderr

    def test_no_record_blocks_the_publish(self) -> None:
        """⚠️ `structure` 는 게이트가 발행 직전에 실제로 돌려 그 자리에서 통과로
        적는다. 그러니 빠진 것으로 남는 것은 사람·모델이 적어야 하는 둘이다."""
        rc, out = self._publish()
        self.assertEqual(2, rc, f"기록이 없는데 발행이 통과했습니다: {out[:300]}")
        self.assertIn("발행 보류", out)
        for stage in ("words", "judgment"):
            self.assertIn(stage, out, f"빠진 단계 {stage} 를 안 알려 줍니다")

    def test_a_partial_record_still_blocks(self) -> None:
        """1층만 통과한 것으로는 부족하다 — 그것이 잡는 것은 표면 모양뿐이다."""
        self._record("structure")
        rc, out = self._publish()
        self.assertEqual(2, rc, "1층만 통과했는데 발행이 통과했습니다")
        self.assertIn("words", out)
        self.assertNotIn("structure —", out)

    def test_all_stages_let_it_through(self) -> None:
        self._record(*STAGES)
        rc, out = self._publish()
        self.assertEqual(0, rc, f"셋 다 통과인데 막혔습니다: {out[:300]}")

    def test_editing_after_the_pass_blocks_again(self) -> None:
        """⛔ 핵심 — 통과한 뒤 고쳐서 내보내는 길을 막는다."""
        self._record(*STAGES)
        self.assertEqual(0, self._publish()[0])
        with io.open(self.doc, "w", encoding="utf-8", newline="\n") as f:
            f.write(BODY + "\n- 새 자료는 해당 폴더에\n")
        rc, out = self._publish()
        self.assertEqual(2, rc, "고친 뒤에도 옛 통과로 발행이 됩니다")

    def test_the_escape_hatch_works_and_shows_in_the_command(self) -> None:
        """막기만 하고 풀 길이 없으면 급할 때 도구를 통째로 끈다."""
        rc, out = self._publish(prefix="KOREAN_PUBLISH_FORCE=1 ")
        self.assertEqual(0, rc, f"넘기는 길이 막혔습니다: {out[:300]}")

    def test_probe_never_blocks(self) -> None:
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "session_id": "pub-session",
                   "tool_input": {"command": f"python notion.py create --md {self.doc}"}}
        done = subprocess.run([sys.executable, "-X", "utf8", GATE, "--probe"],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=240, env=self.env)
        self.assertNotEqual(2, done.returncode, "시험 통로가 발행을 막았습니다")


if __name__ == "__main__":
    unittest.main()
