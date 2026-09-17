"""2층 갈래 탐침이 **잴 수 있는 상태인지** 본다 — 모델은 안 부른다.

탐침은 호출이 들어 재우지 않는다. 그래서 탐침이 조용히 망가져도 다음에 부를
때까지 아무도 모른다. 부르지 않고 확인되는 전제만 여기서 지킨다.

**지키는 것 넷**

- 운반 문서가 대장의 2층 몫을 **글자 그대로** 들고 있나 (없으면 딴 것을 잰다)
- 운반 문서가 1층에서 **오류 0 · 주의 0** 인가 (아니면 1층 지적이 섞여 들어온다)
- `guided` 가 `blind` 보다 **실제로 더 준다** (9단계를 못 찾으면 둘이 같아진다)
- 인용 갈림이 **한쪽으로 쏠리지 않았나** (전부 인용이면 갈림이 뜻을 잃는다)
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import repo_paths  # noqa: E402
import probe_layer2_kinds as probe  # noqa: E402


class CarrierTests(unittest.TestCase):

    def setUp(self) -> None:
        self.items = probe.planted()
        self.doc = probe.CARRIER.read_text(encoding="utf-8")

    def test_the_carrier_holds_every_handed_over_sentence(self) -> None:
        missing = [i["flag_id"] for i in self.items
                   if i["sentence"] not in self.doc]
        self.assertEqual(
            [], missing,
            f"운반 문서에 없는 예문 {len(missing)}건: {missing} — "
            "대장에 2층 몫이 늘면 운반 문서에도 심습니다")

    def test_every_flagged_span_sits_inside_its_line(self) -> None:
        """짚은 표현이 예문 안에 있어야 채점이 맞는다."""
        for item in self.items:
            self.assertIn(item["text"], item["sentence"],
                          f"{item['flag_id']}: 짚은 표현이 예문 밖입니다")
            self.assertIsNotNone(
                probe.line_of(self.doc, item["sentence"]),
                f"{item['flag_id']}: 운반 문서에서 줄을 못 찾습니다")

    def test_the_carrier_is_clean_at_layer_one(self) -> None:
        """1층이 조용해야 탐침이 짚는 것을 전부 2층 몫으로 읽을 수 있다."""
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER),
             str(probe.CARRIER)],
            capture_output=True, text=True, encoding="utf-8")
        out = done.stdout or ""
        self.assertIn("오류 0", out,
                      f"운반 문서에 1층 오류가 있습니다 — 2층 지적과 섞입니다\n{out}")
        self.assertIn("주의 0", out,
                      f"운반 문서에 1층 주의가 있습니다 — 2층 지적과 섞입니다\n{out}")


class PromptTests(unittest.TestCase):

    def test_guided_actually_adds_the_step(self) -> None:
        body = probe.step_body(
            probe.SKILL_MD.read_text(encoding="utf-8"), probe.STEP_TITLE)
        self.assertGreater(len(body), 500,
                           "9단계 본문이 너무 짧습니다 — 제목으로 잘못 찾았습니다")
        self.assertIn("판정", body,
                      "9단계 항목에 판정 방법이 없습니다")

    def test_the_prompt_does_not_name_the_answers(self) -> None:
        """어느 줄이 심은 것인지·몇 건인지 알려 주면 시험이 아니다."""
        rules = (probe.RULES.read_text(encoding="utf-8")
                 + probe.step_body(probe.SKILL_MD.read_text(encoding="utf-8"),
                                   probe.STEP_TITLE))
        prompt = probe.SYSTEM.format(rules=rules)
        for item in probe.planted():
            self.assertNotIn(item["flag_id"], prompt,
                             f"프롬프트가 깃발 {item['flag_id']} 를 부릅니다")
        for leak in ("심은", "정답", "탐침", "flagged-rounds"):
            self.assertNotIn(leak, prompt, f"프롬프트에 「{leak}」 가 샙니다")


class CitedSplitTests(unittest.TestCase):
    """인용 갈림이 뜻을 잃지 않았는지 본다.

    9단계는 예시를 글자 그대로 인용한다. 인용된 것을 맞히는 데는 갈래를
    알아볼 필요가 없으므로 **합계 하나만 내면 값이 부풀려진다.** 갈림이 한쪽으로
    다 쏠리면 그 경고가 작동하지 않는다.
    """

    def test_both_sides_of_the_split_have_members(self) -> None:
        cited = probe.cited_texts()
        items = probe.planted()
        other = [i for i in items if i["text"] not in cited]
        self.assertGreater(len(cited), 0,
                           "인용된 것이 0건 — 9단계를 못 읽었을 수 있습니다")
        self.assertGreater(
            len(other), 0,
            "인용 안 된 것이 0건 — 갈래를 알아보는지 잴 표본이 없습니다. "
            "운반 문서에 9단계가 인용하지 않은 예문을 심습니다")

    def test_scoring_separates_hit_from_miss(self) -> None:
        items = probe.planted()
        doc = probe.CARRIER.read_text(encoding="utf-8")
        want = items[0]
        line = probe.line_of(doc, want["sentence"])
        good = probe.score(items, [{"line": line, "phrase": want["text"],
                                    "category": "시험"}], doc)
        self.assertEqual(1, good["tight"], "맞힌 것을 못 셉니다")
        blank = probe.score(items, [], doc)
        self.assertEqual(0, blank["tight"], "빈 결과에 점수를 줍니다")
        self.assertEqual(len(items), blank["total"])


if __name__ == "__main__":
    unittest.main()
