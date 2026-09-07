"""발행 순간에 2층을 부르라는 안내가 실제로 뜨는지 확인한다.

**왜 붙였나.** 안내가 1층 지적 목록의 머리줄에 있었다. 그래서 1층이 뭔가 잡았을
때만 떴고, 실측으로 발행 640회 중 59회(9.2%)만 나왔다. 1층 회수율이 0.057이라
당연한 결과다 — **1층이 아무것도 못 잡은 때가 2층이 가장 필요한 때인데 바로
그때 안내가 없었다.**

**소음이 되면 안 된다.** 노션 발행 하나가 수십 번 호출된다(발행 도구 호출 하루
46회 · 문서 단위로는 6.4건). 문서마다 세션에 한 번만 낸다.

**쓰는 순간에는 안 낸다.** 초안까지 2층을 태우라고 하면 사람이 알림을 끈다.

**시험은 공용 상태 파일을 안 쓴다.** 처음엔 실제 파일에 썼다가 돌연변이 잔재가
남아 다음 실행이 통째로 깨졌고 사람이 쓰는 훅 상태까지 더럽혔다.

**시료 경로가 `Temp` 안이면 안 된다.** 훅이 임시 폴더를 검사에서 빼므로,
거기 두면 「쓰는 순간엔 안 뜬다」가 저절로 통과한다(돌연변이로 확인).
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK = repo_paths.hook("doc-style-gate.py")
SANDBOX = REPO_ROOT / ".hook-sandbox"        # 훅이 건너뛰지 않는 경로

CLEAN = """---
form: structured
---
# 도구 조사 결과

**조사한 도구 · 직전 대비 변화** — 한 장 조망

- **도구 가**: 2026-03 출시
- **도구 나**: 2026-02 통합
"""

DIRTY = """---
form: structured
---
# 점검 결과

**점검 대상 · 결과** — 한 장 조망

- **판정**: 우리 쪽 기준으로는 통과한다.
"""


def load_hook():
    spec = importlib.util.spec_from_file_location("doc_style_gate", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FinalizeNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HOOK.is_file():
            raise unittest.SkipTest(f"훅이 없습니다: {HOOK}")
        # 검사기와 스킬까지 갖춘 가짜 HOME 을 한 번만 만든다 — 없으면 훅이
        # 「검사기 없음」만 내고, 그러면 시험이 아무것도 안 지킨다
        cls.home = Path(tempfile.mkdtemp())
        real = repo_paths.INSTALLED
        fake = cls.home / ".claude"
        (fake / "hooks").mkdir(parents=True)
        (fake / "assets").mkdir(parents=True)
        shutil.copy2(HOOK, fake / "hooks" / "doc-style-gate.py")
        checker = real / "assets" / "doc-style-check.py"
        if not checker.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {checker}")
        shutil.copy2(checker, fake / "assets" / "doc-style-check.py")
        skill = real / "skills" / "finalize-korean-document"
        if skill.is_dir():
            shutil.copytree(skill, fake / "skills" / "finalize-korean-document",
                            ignore=shutil.ignore_patterns("__pycache__"))
        cls.hook = fake / "hooks" / "doc-style-gate.py"
        cls.state = fake / "state" / "doc-style-seen.json"
        cls.env = dict(os.environ, USERPROFILE=str(cls.home), HOME=str(cls.home))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.home, ignore_errors=True)

    def setUp(self) -> None:
        if self.state.is_file():
            self.state.unlink()

        # 시료는 임시 폴더 밖에 둔다 — 훅이 임시 폴더를 검사에서 뺀다
        self.work = SANDBOX / uuid.uuid4().hex[:8]
        self.work.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, SANDBOX, True)

    def document(self, name: str, text: str = CLEAN) -> str:
        path = self.work / name
        path.write_text(text, encoding="utf-8")
        return str(path)

    def run_hook(self, payload: dict) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(self.hook)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", env=self.env,
        )

    def call(self, payload: dict) -> str:
        done = self.run_hook(payload)
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        if not (done.stdout or "").strip():
            return ""
        try:
            out = json.loads(done.stdout)
        except ValueError:
            return done.stdout
        return out.get("hookSpecificOutput", {}).get("additionalContext", "")

    def publish(self, path: str, session: str) -> dict:
        return {"hook_event_name": "PreToolUse", "tool_name": "Artifact",
                "tool_input": {"file_path": path}, "session_id": session}

    def write(self, path: str, session: str) -> dict:
        return {"hook_event_name": "PostToolUse", "tool_name": "Write",
                "tool_input": {"file_path": path}, "session_id": session}

    # ── 안내가 떠야 하는 자리 ────────────────────────────────────────────
    def test_the_notice_appears_even_when_nothing_is_flagged(self) -> None:
        """1층이 조용한 때가 2층이 가장 필요한 때다."""
        out = self.call(self.publish(self.document("clean.md"), "s1"))

        self.assertIn("finalize-korean-document", out)
        self.assertIn("발행 직전", out)

    def test_a_second_document_still_gets_its_notice(self) -> None:
        """한 번 냈다고 세션 전체를 막으면 다음 문서를 놓친다."""
        self.call(self.publish(self.document("one.md"), "s2"))
        out = self.call(self.publish(self.document("two.md"), "s2"))

        self.assertIn("발행 직전", out)

    # ── 안내가 뜨면 안 되는 자리 ─────────────────────────────────────────
    def test_the_notice_is_given_once_per_document(self) -> None:
        """노션 발행 하나가 수십 번 호출된다 — 매번 내면 소음이다."""
        payload = self.publish(self.document("clean.md"), "s3")
        first = self.call(payload)
        second = self.call(payload)

        self.assertIn("발행 직전", first)
        self.assertNotIn("발행 직전", second)

    def test_writing_a_draft_does_not_trigger_it(self) -> None:
        """초안까지 2층을 태우라고 하면 사람이 알림을 끈다.

        시료가 검사 대상이라는 것부터 확인한다 — 아니면 이 시험은 아무것도
        안 지킨다(임시 폴더에 두었더니 실제로 그랬다).
        """
        path = self.document("draft.md", DIRTY)
        out = self.call(self.write(path, "s4"))

        # 쓰는 순간에는 매체 무관 규칙만 낸다 — 서술형 종결은 여기서 안 나온다
        self.assertIn("모호한 지칭", out, "시료가 검사 대상이 아닙니다")
        self.assertNotIn("발행 직전", out)

    # ── 함께 지켜야 하는 것 ──────────────────────────────────────────────
    def test_findings_still_come_through(self) -> None:
        """안내를 붙이며 지적을 지우면 검사기가 통째로 조용해진다."""
        out = self.call(self.publish(self.document("dirty.md", DIRTY), "s5"))

        self.assertIn("서술형 종결", out)
        self.assertIn("발행 직전", out)

    def test_the_notice_says_why_the_script_is_not_enough(self) -> None:
        """「스킬을 도세요」만 적으면 왜인지 몰라 건너뛴다 — 실측 9.2%가 그 결과다."""
        module = load_hook()

        self.assertIn("0.057", module.NOTICE)
        self.assertIn("0.771", module.NOTICE)

    def test_the_state_file_stays_flat(self) -> None:
        """만료 정리가 값을 시각으로 읽는다 — 중첩 사전을 넣었더니 훅이 통째로 죽었다.

        훅은 실패해도 조용하다(rc만 1이고 화면에 아무것도 안 뜬다). 그래서
        「안내가 안 뜬다」로만 보이고 원인이 안 보였다.
        """
        self.call(self.publish(self.document("clean.md"), "s6"))
        state = json.loads(self.state.read_text(encoding="utf-8"))

        self.assertIn("s6", state, "상태가 안 남았습니다")
        for session, marks in state.items():
            with self.subTest(session=session):
                self.assertIsInstance(marks, dict)
                for value in marks.values():
                    self.assertIsInstance(value, (int, float),
                                          "값은 시각이어야 합니다 — 중첩 사전 금지")

    def test_the_hook_never_exits_nonzero(self) -> None:
        """훅이 죽으면 검사가 통째로 사라지는데 화면에는 아무 말도 안 나온다."""
        path = self.document("clean.md")
        for session in ("s7", "s7", "s8"):
            done = self.run_hook(self.publish(path, session))
            with self.subTest(session=session):
                self.assertEqual(done.returncode, 0, done.stderr[-400:])

    def test_the_test_does_not_touch_the_shared_state(self) -> None:
        """공용 파일을 쓰면 다음 실행이 깨지고 사람이 쓰는 훅까지 더럽힌다."""
        shared = repo_paths.installed("state", "doc-style-seen.json")
        before = shared.read_text(encoding="utf-8") if shared.is_file() else ""

        self.call(self.publish(self.document("clean.md"), "s9"))

        after = shared.read_text(encoding="utf-8") if shared.is_file() else ""
        self.assertEqual(before, after, "공용 상태 파일이 바뀌었습니다")


if __name__ == "__main__":
    unittest.main()
