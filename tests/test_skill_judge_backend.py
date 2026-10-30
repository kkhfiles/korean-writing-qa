"""Run the skill's documented calls without sending any document to a model."""
import contextlib
import importlib.util
import io
import json
import re
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import judge_layer2 as judge
import layer2_coverage as coverage


# llm_playbook 은 비공개 조직 저장소라 CI 가 설치하지 못한다 — 없으면 건너뛴다(로컬 전체 시험이 본다).
HAS_PLAYBOOK = importlib.util.find_spec("llm_playbook") is not None


@unittest.skipUnless(HAS_PLAYBOOK, "llm_playbook 이 없는 PC — 판정기 서비스 선택을 못 부른다")
class SkillJudgeBackendTests(unittest.TestCase):
    def test_documented_calls_keep_the_current_service(self):
        skill = (ROOT / "skills/finalize-korean-document/SKILL.md").read_text(encoding="utf-8")
        # 스킬은 저장소 도구를 입구(`korean_qa_run.py judge_layer2`)로 부른다 — 작성자 경로 대신(2026-10-30)
        examples = dict(re.findall(r"^# (Codex|Claude Code)\n(python[^\n]+judge_layer2(?:\.py)? [^\n]+)", skill, re.M))
        for session, expected in (("Codex", "codex"), ("Claude Code", "claude")):
            with self.subTest(session=session), tempfile.TemporaryDirectory() as folder:
                self.assertIn(session, examples, "Each session needs an executable example with its own backend.")
                doc = Path(folder) / "doc.md"
                doc.write_text("# 검토\n\n문맥 검사 대상\n", encoding="utf-8")
                command = shlex.split(examples[session])
                args = command[command.index(next(t for t in command if t in ("judge_layer2", "judge_layer2.py")
                                                  or t.endswith("/judge_layer2.py"))) + 1:]
                args = [str(doc) if t == "<수정문>" else t for t in args]
                selected = []

                def load(name):
                    selected.append(name)
                    return (lambda **kw: {"text": "[]", "model": "test", "usage": {}}, json.loads)

                # Both services are available: auto would prefer Claude, even in Codex.
                with patch("llm_playbook.ladder.available", return_value=(True, "test")), \
                     patch.object(judge, "load_backend", side_effect=load), \
                     patch.object(judge, "LOG", Path(folder) / "calls.jsonl"), \
                     patch.object(coverage, "DECISIONS", Path(folder) / "answers.jsonl"), \
                     contextlib.redirect_stdout(io.StringIO()):
                    rc = judge.main(args)
                self.assertEqual(0, rc)
                self.assertEqual([expected], selected)


if __name__ == "__main__":
    unittest.main()
