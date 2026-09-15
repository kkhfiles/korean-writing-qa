"""공개되는 빈도표에 신원이 없는지, 줄인 것이 단어 점검 판정을 안 바꾸는지 본다.

**왜 있나.** 이 표로 두 번 샜다. 2026-09-15 1차에서 고유명사를 걷어냈는데
Kiwi 가 보통명사로 붙인 이름·회사가 남아 2차 점검에서 또 나왔다(사람 이름 3·
회사 6·사내 조직 4). 눈으로 훑는 것으로는 세 번째를 못 막는다.
"""
import io
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import scrub_freq_table as scrub  # noqa: E402


def table():
    with io.open(scrub.TABLE, encoding="utf-8") as f:
        return json.load(f)["freq"]


class FreqTableTests(unittest.TestCase):

    def test_the_floor_matches_what_the_sweep_asks_for(self) -> None:
        """문턱이 어긋나면 단어 점검 판정이 조용히 바뀐다.

        단어 점검은 `freq.get(key, 0) <= --max` 로 판정한다 — 표에 없는 낱말은 0이다.
        그러니 `--max` 기본값 이하 항목은 있으나 없으나 같은 답을 낸다. 거꾸로
        `FLOOR` 가 그보다 크면 **표에 있어야 할 낱말을 지운 것**이라 판정이 바뀐다.
        """
        with io.open(os.path.join(ROOT, "scripts", "rare_words.py"),
                     encoding="utf-8") as f:
            src = f.read()
        m = re.search(r'"--max",\s*type=int,\s*default=(\d+)', src)
        self.assertIsNotNone(m, "단어 점검의 --max 기본값을 못 찾았습니다")
        default = int(m.group(1))
        self.assertLessEqual(
            scrub.FLOOR, default,
            f"표를 {scrub.FLOOR}회에서 잘랐는데 단어 점검 기본 문턱은 {default}회입니다 — "
            "그 사이 낱말이 표에 없어 드문 것으로 잘못 잡힙니다")

    def test_nothing_below_the_floor_survives(self) -> None:
        """줄이기가 실제로 적용돼 있나 — 스크립트만 고치고 안 돌린 경우를 잡는다."""
        low = {k: n for k, n in table().items() if n <= scrub.FLOOR}
        self.assertEqual({}, low, f"{scrub.FLOOR}회 이하가 {len(low)}종 남았습니다 — "
                                  "`python -X utf8 scripts/scrub_freq_table.py` 를 돌리세요")

    def test_single_letter_nouns_are_gone(self) -> None:
        """한 글자 **명사·부사**는 뺀다 — 성씨와 이름 낱자가 거기 모인다."""
        short = [k for k in table()
                 if len(k.rsplit("/", 1)[0]) < scrub.MIN_LEN
                 and k.rsplit("/", 1)[1] not in scrub.STEM_TAGS]
        self.assertEqual([], short, f"한 글자 명사·부사 {len(short)}종이 남았습니다")

    def test_single_letter_stems_are_kept(self) -> None:
        """한 글자 **용언 어간**은 남는다 — 단어 점검이 그것을 읽기 때문이다.

        「걷다·굳다·재다」가 여기 산다. 표에서 빼면 단어 점검이 흔한 용언까지
        드문 것으로 잘못 잡는다(표에 없는 낱말은 0회로 읽힌다).
        """
        stems = [k for k in table()
                 if len(k.rsplit("/", 1)[0]) == 1
                 and k.rsplit("/", 1)[1] in scrub.STEM_TAGS]
        self.assertGreater(len(stems), 50,
                           "한 글자 용언 어간이 표에 거의 없습니다 — "
                           "`scripts/scrub_freq_table.py` 를 다시 돌리세요")

    def test_the_sweep_and_the_table_agree_on_stems(self) -> None:
        """단어 점검이 읽는 품사와 표가 남기는 품사가 같아야 한다 — 어긋나면 조용히 샌다."""
        import importlib
        sweep = importlib.import_module("rare_words")
        self.assertEqual(scrub.STEM_TAGS, sweep.STEM_TAGS)

    def test_only_the_tags_the_sweep_reads_are_kept(self) -> None:
        tags = {k.rsplit("/", 1)[1] for k in table()}
        self.assertTrue(tags <= scrub.KEEP_TAGS, f"단어 점검이 안 읽는 품사: {tags - scrub.KEEP_TAGS}")

    def test_no_word_on_the_identity_list_is_in_the_table(self) -> None:
        """저장소 밖 신원 목록이 있으면 그 이름·회사·조직이 표에 없어야 한다."""
        if not any(scrub.DENY.values()):
            self.skipTest("신원 목록이 없는 기계입니다 — 이 검사는 목록이 있어야 뜻이 있습니다")
        left = [w for w in {k.rsplit("/", 1)[0] for k in table()}
                if scrub.identifying(w, set())]
        self.assertEqual([], left, f"신원이 표에 남았습니다: {left[:20]}")

    def test_the_scrub_is_idempotent(self) -> None:
        """이미 지운 표에 다시 돌려도 지울 것이 없어야 한다 — 없으면 덜 지운 것이다."""
        done = subprocess.run(
            [sys.executable, "-X", "utf8",
             os.path.join(ROOT, "scripts", "scrub_freq_table.py"), "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        self.assertEqual(0, done.returncode, done.stdout + done.stderr)
        m = re.search(r"항목 (\d+) → (\d+)", done.stdout)
        self.assertIsNotNone(m, done.stdout)
        self.assertEqual(m.group(1), m.group(2),
                         "다시 돌리니 더 지울 것이 있습니다:\n" + done.stdout)


if __name__ == "__main__":
    unittest.main()
