"""판정기 출력 형식(행 형식 기본 · `json` 으로 되돌림)이 결과를 같은 모양으로 돌려주는지 본다 — 모델은 안 부른다.

(2026-10-19) 지적 하나에 출력이 약 217토큰이라 키 없는 행 형식 · 근거는 필요할 때만을 후보로 쟀고,
3회 대 3회에서 시간이 줄고 정확도 가드가 같아 2026-10-20 에 기본으로 바꿨다.

**지키는 것**

- 기본은 행 형식이고 형식 절이 실제로 바뀐다 — 바꿀 글이 안 맞아 조용히 객체 형식으로 도는 일을 막는다
- `json` 이면 예전 프롬프트와 글자까지 같다(되돌리는 길)
- 행으로 온 지적도 객체와 같은 칸 이름으로 판정 결과와 기록에 들어간다
- 칸이 어긋난 행을 세어 기록에 남긴다 — 버리지는 않는다
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import probe_layer2_kinds as probe  # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402


class PromptTests(unittest.TestCase):

    def test_json_brings_back_the_old_prompt(self) -> None:
        with mock.patch.dict(os.environ, {probe.FORMAT_ENV: "json"}):
            self.assertEqual("json", probe.output_format())
            self.assertEqual(probe.SYSTEM, probe.system_prompt())

    def test_the_default_really_replaces_the_format_block(self) -> None:
        self.assertIn(probe._FORMAT_JSON, probe.SYSTEM, "바꿀 형식 절이 프롬프트와 안 맞습니다")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(probe.FORMAT_ENV, None)
            self.assertEqual("compact", probe.output_format())
            got = probe.system_prompt()
        self.assertNotIn('"phrase":', got)
        self.assertIn("키 없는 배열", got)
        self.assertIn("늘 일곱 칸", got)
        got.format(rules="규칙")     # 중괄호가 남아 format 이 깨지지 않는다

    def test_shifted_rows_are_counted_not_dropped(self) -> None:
        rows = [[3, "던지기", "규칙", "입력", "fix", "", ""],          # 정상
                ["4", "p", "규칙", "q", "ask", "", "까닭"],             # 줄 번호가 글이어도 숫자면 정상
                [5, "p", "규칙", "q", "fix", "까닭"],                   # 한 칸 빠짐 — 근거가 check 로 읽힌다
                [6, "p", "규칙", "fix", "", "", ""],                   # 고친 말을 건너뜀 — decide 가 밀림
                ["여섯", "p", "규칙", "q", "fix", "", ""],              # 첫 칸이 줄 번호가 아님
                [], {"line": 7, "phrase": "p"}]
        self.assertEqual(4, probe.malformed(rows))
        self.assertEqual(len(rows), len(probe.as_findings(rows)), "어긋난 행을 버렸습니다")
        self.assertEqual(0, probe.malformed({"not": "a list"}))

    def test_rows_get_the_same_field_names(self) -> None:
        rows = [[3, "던지기", "업무에서 쓰는 말로 쓰기", "입력", "fix", "", ""], {"line": 4, "phrase": "p"}]
        got = probe.as_findings(rows)
        self.assertEqual({"line": 3, "phrase": "던지기", "category": "업무에서 쓰는 말로 쓰기", "fix": "입력",
                          "decide": "fix", "check": "", "why": ""}, got[0])
        self.assertEqual({"line": 4, "phrase": "p"}, got[1])
        self.assertEqual([], probe.as_findings({"not": "a list"}))


class JudgeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.saved = judge.LOG
        judge.LOG = self.dir / "calls.jsonl"
        self.doc = self.dir / "d.md"
        self.doc.write_text("# 소개\n\n결과는 한 줄로 던집니다.\n", encoding="utf-8")

    def tearDown(self) -> None:
        judge.LOG = self.saved
        self.tmp.cleanup()

    def test_a_compact_reply_becomes_ordinary_findings(self) -> None:
        fake = FakeBackend([[3, "한 줄로 던집니다", "업무에서 쓰는 말로 쓰기", "한 줄로 입력합니다", "fix", "", ""],
                            [3, "결과는", "군더더기 지우기", "결과", "fix", "까닭"]])
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(probe.FORMAT_ENV, None)
            result = judge.judge(self.doc, "opus", 10, fake.pair())
        self.assertIn("키 없는 배열", fake.calls[0]["system"])
        self.assertEqual([("한 줄로 던집니다", "한 줄로 입력합니다"), ("결과는", "결과")],
                         [(f["phrase"], f["fix"]) for f in result["findings"]])
        row = json.loads(judge.LOG.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual("compact", row["format"])
        self.assertEqual(1, row["malformed"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            judge.show(result)
        self.assertIn("칸이 어긋난 지적 1건", out.getvalue())


if __name__ == "__main__":
    unittest.main()
