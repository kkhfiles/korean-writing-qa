"""2층 이행률 측정기가 자기 자신에게 속지 않는지 확인한다.

**왜 시험이 필요한가.** 이 측정기는 두 번 틀렸다.

1. 「발행 직전」 넉 자만 찾아 **그 문구를 논의한 글까지** 셌다 — 발화율 208%
2. 이 시스템을 만드는 세션이 문구를 계속 인용하는데 그것도 셌다

둘 다 「측정기가 자기 활동을 성과로 센다」는 한 가지 실패다. 이 저장소는 같은
실패를 계기판 쪽에서도 겪었다(회수율 분모가 순환이던 것).

**침묵해야 하는 자리도 지킨다** — 붙인 뒤 표본이 적으면 판정 불가라고 말해야
한다. 0%를 결과로 내면 「안 먹혔다」로 읽힌다.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "measure_layer2_uptake.py"


def load():
    spec = importlib.util.spec_from_file_location("measure_layer2_uptake", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MarkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def test_the_marker_is_the_whole_line_the_hook_prints(self) -> None:
        """짧게 잡으면 그 문구를 논의한 글까지 세어 발화율이 100%를 넘는다."""
        self.assertGreater(len(self.mod.NOTICE_MARK), 20)
        self.assertIn("finalize-korean-document", self.mod.NOTICE_MARK)

    def test_the_marker_matches_what_the_hook_actually_prints(self) -> None:
        """훅 문구를 고치면 측정기가 조용히 0을 내기 시작한다."""
        hook = repo_paths.hook("doc-style-gate.py")
        if not hook.is_file():
            self.skipTest(f"훅이 없습니다: {hook}")

        self.assertIn(self.mod.NOTICE_MARK, hook.read_text(encoding="utf-8"),
                      "측정기가 찾는 문구가 훅에 없습니다")

    def test_this_project_is_left_out_of_the_count(self) -> None:
        """이 시스템을 만드는 세션은 문구를 계속 인용한다 — 성과가 아니다."""
        self.assertEqual(self.mod.SELF, "korean-writing-qa")


class PublishDefinitionTests(unittest.TestCase):
    """발행의 정의를 두 벌로 두면 어긋난다 — 실제로 어긋난 채 기준선을 냈다.

    측정기가 자기 정규식(`notion\\.py|marp|\\.pptx`)을 들고 있어서 조회
    (`notion.py children`)와 소스 읽기(`grep ... notion.py`)까지 발행으로 셌다.
    분모가 244 대신 627 이 됐고 기준선 발화율이 21.3% 대신 8.3% 로 기록됐다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()
        hook = repo_paths.hook("doc-style-gate.py")
        if not hook.is_file():
            raise unittest.SkipTest(f"훅이 없습니다: {hook}")
        cls.hook = cls.mod.load_hook()

    def call(self, command):
        return {"name": "Bash", "input": {"command": command}}

    def test_reading_the_publisher_is_not_publishing(self) -> None:
        for command in (
            "grep -n 'def ' ~/.claude/skills/notion-publish/notion.py",
            "python notion.py children --id abc --max 300",
            "python notion.py search --query 평가 --limit 30",
        ):
            with self.subTest(command=command[:40]):
                self.assertFalse(self.mod.is_publish(self.hook, self.call(command)))

    def test_an_actual_publish_still_counts(self) -> None:
        command = "python -X utf8 notion.py create --parent abc --title 보고 report.md"
        self.assertTrue(self.mod.is_publish(self.hook, self.call(command)))

    def test_the_meter_keeps_no_publish_pattern_of_its_own(self) -> None:
        """사본을 되살리면 같은 어긋남이 돌아온다."""
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("PUBLISH = re.compile", source)
        self.assertIn("hook.targets(payload)", source)


class BoundaryTests(unittest.TestCase):
    """경계는 날짜가 아니라 그 순간이다.

    자정으로 잡았더니 훅을 고치기 네 시간 **전** 활동이 「붙인 뒤」로 들어가
    「발행 8건에 안내 0건」이 됐다. 안내가 있을 수 없던 구간이다.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def test_the_boundary_is_a_moment_not_midnight(self) -> None:
        changed = self.mod.CHANGED

        self.assertNotEqual((changed.hour, changed.minute), (0, 0),
                            "경계가 자정이면 그날 앞 시간의 활동이 「붙인 뒤」로 샌다")

    def test_that_morning_falls_before_the_change(self) -> None:
        self.assertEqual(self.mod.bucket("2026-08-31T04:08:10.000Z"), "붙이기 전")
        self.assertEqual(self.mod.bucket("2026-08-31T09:00:00.000Z"), "붙인 뒤")


class VerdictTests(unittest.TestCase):
    """표본이 적을 때 침묵하는지 — 0%를 결과로 내면 「안 먹혔다」로 읽힌다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def test_a_small_sample_is_reported_as_undecidable(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("판정 불가", source)
        self.assertIn('after["발행 호출"] < 20', source)

    def test_the_two_stages_are_measured_apart(self) -> None:
        """어디서 새는지가 처방을 가른다 — 합치면 무엇을 고칠지 모른다."""
        result = self.mod.measure(days=1)

        for when in ("붙이기 전", "붙인 뒤"):
            with self.subTest(when=when):
                row = result["buckets"][when]
                for field in ("발행 호출", "안내 발화", "스킬 호출",
                              "안내 발화율", "안내 이행율"):
                    self.assertIn(field, row)


class WindowTests(unittest.TestCase):
    """기간은 **줄의 시각**으로 자른다 — 파일 수정 시각으로 자르면 옛 줄이 들어온다.

    오래 이어진 대화는 파일이 날마다 고쳐져서, 사흘로 잰 발행이 161회로 나왔다.
    줄 시각으로 다시 세니 8회였다(2026-09-23).
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()
        if not repo_paths.hook("doc-style-gate.py").is_file():
            raise unittest.SkipTest("훅이 없습니다")

    def test_an_old_line_in_a_fresh_file_is_left_out(self) -> None:
        publish = {"type": "tool_use", "name": "Bash", "input": {
            "command": "python -X utf8 notion.py create --parent abc --title 보고 P:/work/report.md"}}

        def line(days_ago: float) -> str:
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z",
                                  time.gmtime(time.time() - days_ago * 86400))
            return json.dumps({"timestamp": stamp, "message": {"content": [publish]}},
                              ensure_ascii=False)

        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "P--work-other"
            folder.mkdir()
            # 파일은 방금 고쳐졌다 — 그 안의 한 줄은 열흘 전, 한 줄은 한 시간 전
            (folder / "s.jsonl").write_text(line(10) + "\n" + line(1 / 24) + "\n",
                                            encoding="utf-8")
            saved = self.mod.TRANSCRIPTS
            self.mod.TRANSCRIPTS = Path(d)
            try:
                result = self.mod.measure(days=3)
            finally:
                self.mod.TRANSCRIPTS = saved
        total = sum(b["발행 호출"] for b in result["buckets"].values())
        self.assertEqual(1, total, "열흘 전 발행이 「최근 사흘」에 들어왔습니다")


class DocumentCountTests(unittest.TestCase):
    """문서 판으로 세는 쪽 — 호출 수로는 **어느 문서에 돌았는지**를 못 잇는다."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load()

    def setUp(self) -> None:
        self.store = Path(tempfile.mkdtemp()) / "store.jsonl"
        self.prev = os.environ.get("KOREAN_CHECK_RECORD")
        os.environ["KOREAN_CHECK_RECORD"] = str(self.store)

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("KOREAN_CHECK_RECORD", None)
        else:
            os.environ["KOREAN_CHECK_RECORD"] = self.prev

    def write(self, rows) -> None:
        self.store.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
            encoding="utf-8")

    @staticmethod
    def row(path, stage, digest="aaaa", verdict="pass"):
        return {"hash": digest, "path": path, "stage": stage,
                "verdict": verdict, "when": time.time(), "note": ""}

    def test_the_same_document_counts_once(self) -> None:
        """같은 판에 두 번 적어도 검사받은 문서는 하나다."""
        self.write([self.row("D:/a/doc.md", "judgment"),
                    self.row("D:/a/doc.md", "judgment")])

        out = self.mod.count_documents(days=1)

        self.assertEqual(out["문서 판"], 1)
        self.assertEqual(out["judgment"], 1)

    def test_a_changed_document_is_a_new_one(self) -> None:
        """내용이 바뀌면 다시 판단해야 하므로 별개로 센다."""
        self.write([self.row("D:/a/doc.md", "judgment", digest="aaaa"),
                    self.row("D:/a/doc.md", "structure", digest="bbbb")])

        out = self.mod.count_documents(days=1)

        self.assertEqual(out["문서 판"], 2)
        self.assertEqual(out["파일"], 1)
        self.assertEqual(out["2층 실행률"], 0.5)

    def test_probe_leftovers_do_not_inflate_the_denominator(self) -> None:
        """시험이 만든 것은 문서가 아니다 — 세면 실행률이 낮게 나온다."""
        self.write([self.row("P:/x/.gate-probe-abc/probe-target.md", "structure"),
                    self.row("C:/tmp/scratchpad/note.md", "structure"),
                    self.row("D:/a/doc.md", "judgment")])

        out = self.mod.count_documents(days=1)

        self.assertEqual(out["문서 판"], 1)
        self.assertEqual(out["2층 실행률"], 1.0)

    def test_no_record_at_all_is_not_a_rate(self) -> None:
        """분모가 0이면 비율을 지어내지 않는다."""
        self.write([])

        self.assertIsNone(self.mod.count_documents(days=1)["2층 실행률"])


if __name__ == "__main__":
    unittest.main()
