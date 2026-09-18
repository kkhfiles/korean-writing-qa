"""주의를 읽고 정상으로 판단한 기록이 **실제로 문을 여는지** 고정한다.

**왜 만들었나**(2026-09-18 · 외부 검토가 짚고 사용자가 정함). 발행 직전 검사는
주의 한 건만 있어도 `structure: fail` 로 적었다. 그런데 주의는 「사람이 보고
판단하라」는 등급이다 — 오탐이라고 판단해도 그 판단을 받아 줄 곳이 없어
**문구를 지우거나 게이트를 통째로 넘기는 것**밖에 길이 없었다. 다시 돌려도 같은
주의가 또 나오므로 영원히 막혔다(실측 재현).

「사람이 본다」고 해 놓고 **본 결과를 적을 곳이 없으면 그 말은 빈말**이다.

## 이 시험이 지키는 다섯

| 경우 | 바라는 것 | 왜 |
|---|---|---|
| 주의만 · 검토 기록 없음 | 막힘 | 안 보고 나가면 안 됨 |
| 주의만 · 검토 기록 있음 | 열림 | 사람이 판단했음 |
| 검토 뒤 글을 고침 | 다시 막힘 | 기록은 **내용 해시**에 묶임 |
| 오류 있음 · 검토 기록 있음 | 막힘 | **오류는 사람 판단 대상이 아님** |
| 까닭 없이 검토 기록 | 거절 | 고무도장이 되면 넘기기와 같아짐 |

⛔ **셋째와 넷째가 이 장치의 값**이다. 그 둘이 없으면 검토 기록은 그냥 두 번째
   넘기기 통로가 된다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

GATE = repo_paths.hook("doc-style-gate.py")
RECORDER = repo_paths.REPO / "scripts" / "check_record.py"

HEAD = ("---\nform: structured\n---\n\n# 검토 결과\n\n"
        "**하반기 검토 범위** — 한 장 조망\n\n")
#: 오류 0 · 주의 1 — 표 머리 「비고」는 공문서 표준 관례라 정당한 오탐 후보다
WARN_ONLY = HEAD + "| 항목 | 비고 |\n|---|---|\n| 가 | 확인 완료 |\n"
#: 위에 오류 하나를 더한 것 — 조사로 끊긴 값
WITH_ERROR = WARN_ONLY + "\n- **산출물** — 해당 폴더에\n"

BLOCKED, OPEN = 2, 0


class ReviewRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        for path in (GATE, RECORDER):
            if not path.is_file():
                raise unittest.SkipTest(f"없습니다: {path}")
        # ⛔ **게이트는 `Temp` 를 건너뛴다** — 이 저장소 CLAUDE.md 에 적힌 함정이다.
        #    임시 디렉터리에서 재면 아무것도 안 일어나고 그것을 「안 막는다」로
        #    읽게 된다. 저장소 밖 작업 폴더에서 잰다.
        cls.work = repo_paths.REPO.parent / ".korean-qa-review-test"
        cls.work.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.store = Path(tempfile.mkdtemp()) / "record.jsonl"
        self.env = dict(os.environ)
        self.env["KOREAN_CHECK_RECORD"] = str(self.store)
        self.doc = self.work / f"{uuid.uuid4().hex[:12]}.md"

    def tearDown(self) -> None:
        self.doc.unlink(missing_ok=True)

    def publish(self) -> int:
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "session_id": str(uuid.uuid4()),
                   "tool_input": {
                       "command": f'python notion.py create --file "{self.doc}"'}}
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(GATE)],
            input=json.dumps(payload, ensure_ascii=False), env=self.env,
            capture_output=True, text=True, encoding="utf-8", timeout=120)
        return done.returncode

    def review(self, note: str = "표 머리 「비고」는 공문서 표준 관례"):
        args = [sys.executable, "-X", "utf8", str(RECORDER), "record",
                str(self.doc), "--stage", "review", "--verdict", "pass"]
        if note:
            args += ["--note", note]
        return subprocess.run(args, capture_output=True, text=True,
                              encoding="utf-8", env=self.env).returncode

    def test_warnings_alone_still_block_without_a_review(self) -> None:
        self.doc.write_text(WARN_ONLY, encoding="utf-8")
        self.assertEqual(BLOCKED, self.publish(),
                         "주의를 아무도 안 보고 나갈 수 있습니다")

    def test_a_review_opens_the_gate(self) -> None:
        self.doc.write_text(WARN_ONLY, encoding="utf-8")
        self.publish()
        self.assertEqual(0, self.review(), "검토 기록을 못 남겼습니다")
        self.assertEqual(OPEN, self.publish(),
                         "판단을 적었는데도 막힙니다 — 그러면 적을 이유가 없습니다")

    def test_editing_after_the_review_blocks_again(self) -> None:
        """기록은 **내용**에 묶인다 — 검토한 뒤 고쳐서 내보내는 길을 닫는다."""
        self.doc.write_text(WARN_ONLY, encoding="utf-8")
        self.publish()
        self.review()
        self.doc.write_text(WARN_ONLY + "\n- **덧붙임** — 확인 완료\n",
                            encoding="utf-8")
        self.assertEqual(BLOCKED, self.publish(),
                         "검토한 뒤 고친 글이 옛 판단으로 나갑니다")

    def test_a_review_does_not_open_the_gate_for_errors(self) -> None:
        """오류는 사람 판단 대상이 아니다 — 이 길로 열리면 안 된다."""
        self.doc.write_text(WITH_ERROR, encoding="utf-8")
        self.publish()
        self.review("오류도 통과되나 보는 시료")
        self.assertEqual(BLOCKED, self.publish(),
                         "오류가 검토 기록으로 열렸습니다 — 두 번째 넘기기 통로입니다")

    def test_a_review_without_a_reason_is_refused(self) -> None:
        """까닭 없는 승인은 고무도장이다 — 그러면 넘기기와 다를 것이 없다."""
        self.doc.write_text(WARN_ONLY, encoding="utf-8")
        self.assertEqual(1, self.review(note=""),
                         "까닭 없이 검토 기록이 남았습니다")

    def test_the_block_message_says_how_to_record_a_review(self) -> None:
        """막는 글에 이 길이 적혀 있어야 한다 — 안 적으면 아무도 모른다.

        「열쇠 없는 자물쇠」를 안 만든다. 열쇠를 만들어 놓고 **어디 있는지 안
        적으면** 없는 것과 같다.
        """
        self.doc.write_text(WARN_ONLY, encoding="utf-8")
        payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                   "session_id": str(uuid.uuid4()),
                   "tool_input": {
                       "command": f'python notion.py create --file "{self.doc}"'}}
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(GATE)],
            input=json.dumps(payload, ensure_ascii=False), env=self.env,
            capture_output=True, text=True, encoding="utf-8", timeout=120)

        self.assertIn("--stage review", done.stderr)
        self.assertIn("--note", done.stderr)


if __name__ == "__main__":
    unittest.main()
