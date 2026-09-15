"""대장이 가리키는 스킬 단계 번호가 **실제로 그 단계인지** 본다.

**왜 있나.** 2026-09-16 에 2층 절차에 단계를 하나 넣자 「검사기가 못 잡는 것을
직접 찾는다」가 8번에서 9번이 됐다. 대장 열한 건이 `§8` 을 가리키고 있어 전부
엉뚱한 단계를 가리키게 됐는데, 기존 시험은 **스킬 파일이 있는지만** 봐서
조용히 통과했다. 번호로 가리키는 참조는 번호가 밀리면 조용히 썩는다.
"""
import io
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LEDGER = os.path.join(ROOT, "data", "cases", "flagged-rounds.jsonl")

#: 대장이 「2층」 주인에게 맡기는 단계 — 이 제목으로 찾는다
STEP_TITLE = "검사기가 못 잡는 것을 직접 찾는다"


def skill_text(name):
    p = os.path.join(ROOT, "skills", name, "SKILL.md")
    with io.open(p, encoding="utf-8") as f:
        return f.read()


class StepReferenceTests(unittest.TestCase):

    def test_every_referenced_step_exists(self) -> None:
        with io.open(LEDGER, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        refs = []
        for r in rows:
            for m in re.finditer(r"([a-z][a-z0-9-]+)\s*§(\d+)", r["note"]):
                refs.append((r["flag_id"], m.group(1), int(m.group(2))))
        if not refs:
            self.skipTest("단계를 가리키는 참조가 없다")
        for flag, skill, step in refs:
            text = skill_text(skill)
            # ⛔ 여러 줄 깃발이 없으면 `^` 가 글 전체의 첫 글자만 본다.
            self.assertIsNotNone(
                re.search(rf"^{step}\. ", text, re.M),
                f"{flag}: {skill} 에 {step}단계가 없습니다")

    def test_the_referenced_step_is_the_right_one(self) -> None:
        """번호만 맞는 것으로는 부족하다 — 그 번호가 **그 단계**여야 한다."""
        with io.open(LEDGER, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
        text = skill_text("finalize-korean-document")
        m = re.search(rf"^(\d+)\. {re.escape(STEP_TITLE)}", text, re.M)
        self.assertIsNotNone(
            m, f"스킬에 「{STEP_TITLE}」 단계가 없습니다 — 제목이 바뀌었으면 "
               "이 시험의 STEP_TITLE 도 같이 고칩니다")
        want = int(m.group(1))
        for r in rows:
            if r["owner"] != "2층":
                continue
            found = re.search(r"finalize-korean-document §(\d+)", r["note"])
            self.assertIsNotNone(found, f"{r['flag_id']}: 맡은 단계가 없습니다")
            self.assertEqual(
                want, int(found.group(1)),
                f"{r['flag_id']} 가 §{found.group(1)} 을 가리키는데 "
                f"「{STEP_TITLE}」 는 {want}단계입니다 — 번호가 밀렸습니다")


if __name__ == "__main__":
    unittest.main()
