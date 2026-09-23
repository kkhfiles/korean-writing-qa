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
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import repo_paths  # noqa: E402

GATE = os.path.join(ROOT, "hooks", "doc-style-gate.py")
TOOL = os.path.join(ROOT, "scripts", "check_record.py")

BODY = "# 계획\n\n**요점 셋** — 하나 · 둘 · 셋\n"
STAGES = ("structure", "words", "judgment")

#: ⛔ 막는 단계는 기본이 `structure` 하나다 — 뒤의 둘은 **적는 길이 아직 없다.**
#   열쇠 없는 자물쇠를 기본으로 두면 넘기기가 습관이 되고, 그 뒤로는 어떤
#   게이트도 안 듣는다. 이 시험은 셋을 다 요구하는 설정으로 장치 자체를 본다.
STRICT = {"KOREAN_PUBLISH_REQUIRE": "structure,words,judgment"}


class PublishRecordTests(unittest.TestCase):

    def setUp(self) -> None:
        # ⛔ 게이트가 Temp·scratchpad 를 건너뛰므로 거기는 안 된다 — 그렇다고 저장소
        #    안에 두면 지우기에 실패한 판이 뿌리에 쌓인다(`repo_paths.gate_scratch`).
        self.dir = repo_paths.gate_scratch(".pub-rec-")
        self.doc = os.path.join(self.dir, "plan.md")
        with io.open(self.doc, "w", encoding="utf-8", newline="\n") as f:
            f.write(BODY)
        self.store = os.path.join(self.dir, "store.jsonl")
        self.env = dict(os.environ, KOREAN_CHECK_RECORD=self.store, **STRICT)
        self.lenient = dict(os.environ, KOREAN_CHECK_RECORD=self.store,
                            KOREAN_PUBLISH_REQUIRE="structure")

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def _record(self, *stages):
        for s in stages:
            subprocess.run([sys.executable, "-X", "utf8", TOOL, "record",
                            self.doc, "--stage", s, "--verdict", "pass"],
                           capture_output=True, env=self.env, cwd=ROOT, timeout=60)

    def _publish(self, prefix="", env=None):
        cmd = f"{prefix}python notion.py create --md {self.doc}".strip()
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "session_id": "pub-session", "tool_input": {"command": cmd}}
        done = subprocess.run([sys.executable, "-X", "utf8", GATE],
                              input=json.dumps(payload, ensure_ascii=False),
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=240, env=env or self.env)
        return done.returncode, done.stdout + done.stderr

    def test_the_default_does_not_demand_what_nothing_records(self) -> None:
        """⛔ 기본 설정은 **적을 길이 있는 것만** 요구한다.

        셋을 다 요구하면서 뒤의 둘을 적는 곳을 안 만들면 모든 발행이 막히고
        통로가 넘기기 하나뿐이다. 넘기기가 습관이 되면 그 뒤로는 어떤 게이트도
        안 듣는다 — 자물쇠가 없는 것보다 나쁘다(2026-09-16 에 그 상태로 배포함).
        """
        rc, out = self._publish(env=self.lenient)
        self.assertEqual(0, rc, f"기본 설정인데 발행이 막혔습니다: {out[:300]}")

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
