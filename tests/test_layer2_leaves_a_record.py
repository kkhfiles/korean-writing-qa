"""2층 절차가 **자기가 돌았다는 기록을 남기는지** 본다.

**왜 있나.** 기록기는 `words`·`judgment` 단계를 2026-09-16 에 만들고 「2층 절차가
적는다」고 제 문서에 적었는데, **그 절차 어디에도 기록기를 부르는 줄이 없었다.**
닷새 뒤 통과 기록을 세어 보니 문서 판 129개 중 두 단계 모두 0건이었다. 같은 기간
2층은 스물한 날에 열한 번 돌았다 — **돌긴 도는데 어느 문서에 돌았는지 이을 길이
없었다.** 그래서 발행 게이트는 `structure` 하나만 요구하는 자리에 머물렀고,
「2층 실행률」은 잴 수 없는 값으로 남았다.

**부르는 줄이 하나라도 빠지면 다시 그 상태가 된다.** 사람이 읽고 지키는 형태로는
닷새를 못 버텼으므로 기계로 옮긴다.
"""
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SKILL = os.path.join(ROOT, "skills", "finalize-korean-document", "SKILL.md")
RECORDER = os.path.join(ROOT, "scripts", "check_record.py")

#: 2층이 남겨야 하는 단계 — `structure` 는 게이트가 자동으로 적으므로 뺀다
OWNED = ("words", "judgment")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


class Layer2LeavesARecord(unittest.TestCase):

    def setUp(self):
        self.text = read(SKILL)

    def test_records_each_stage_it_owns(self):
        """두 단계를 적는 명령이 절차 안에 있다."""
        for stage in OWNED:
            with self.subTest(stage=stage):
                pattern = rf"check_record\.py record [^\n]*--stage {stage}\b"
                self.assertRegex(
                    self.text, pattern,
                    f"2층 절차에 `{stage}` 를 적는 명령이 없다 — 이 단계는 "
                    f"기록기에 정의만 되고 아무도 안 적는 상태가 된다")

    def test_verdict_comes_with_the_record(self):
        """판정 없이 적는 명령을 두지 않는다 — 시작을 완료로 세게 된다."""
        for line in self.text.split("\n"):
            if "check_record.py record" not in line:
                continue
            self.assertIn("--verdict", line,
                          f"판정 없이 적는 명령이 있다: {line.strip()}")

    def test_recorder_knows_the_stages(self):
        """기록기가 그 단계 이름을 실제로 받는다."""
        stages = read(RECORDER)
        m = re.search(r"^STAGES = \(([^)]*)\)", stages, re.M)
        self.assertIsNotNone(m, "기록기에서 STAGES 를 못 찾았다")
        known = set(re.findall(r'"([a-z]+)"', m.group(1)))
        for stage in OWNED:
            self.assertIn(stage, known,
                          f"절차는 `{stage}` 를 적는데 기록기가 모르는 이름이다")

    def test_the_stage_table_points_at_a_real_writer(self):
        """기록기 문서가 「누가 적나」를 적어 두므로 그 칸이 비면 안 된다."""
        doc = read(RECORDER)
        for stage in OWNED:
            row = re.search(rf"^\| `{stage}` \|[^|]*\|([^|]*)\|", doc, re.M)
            self.assertIsNotNone(row, f"`{stage}` 행을 못 찾았다")
            self.assertTrue(row.group(1).strip(),
                            f"`{stage}` 의 「누가 적나」 칸이 비었다")


if __name__ == "__main__":
    unittest.main()
