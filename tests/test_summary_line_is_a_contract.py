"""검사기 출력의 **합계 줄은 바깥이 읽는 약속**이다 — 모양을 바꾸면 남의 빌드가 멈춘다.

**왜 있나.** 부서 공동 편집 저장소의 빌드가 검사기를 받아 와 돌리고, 출력에서
`합계 — 오류 (\\d+)` 한 줄만 읽어 머지를 막을지 정한다. 검사기는 판을 고정하지
않고 매번 최신을 받아 간다. 그런데 이 저장소에는 그 줄을 **실제 출력에서** 확인하는
시험이 없었다 — `test_run_existing_tools.py` 는 손으로 적은 문자열을 읽을 뿐이다.
문구를 「총계」로 바꾸거나 가운뎃점을 쉼표로 바꾸면 이 저장소 시험은 전부 초록이고
그쪽 빌드만 멈춘다(조용히 통과하지는 않는다 — 「합계 줄이 없다」로 실패한다).

**파일별 줄이 아니라 합계 줄이어야 하는 까닭** — 그쪽이 한 번 겪었다. 「오류 N」을
그냥 찾으면 파일별 줄의 첫 번째가 잡혀, 맨 앞 파일이 깨끗하면 뒤의 오류를 놓친다
(2026-09-21 실측 — 합계 3건인데 초록). 그래서 **맨 앞 파일을 깨끗하게** 두고 잰다.
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

#: 바깥 빌드가 쓰는 정규식 그대로 — 여기를 고치면 그쪽도 고쳐야 한다
CONTRACT = re.compile(r"합계 — 오류 (\d+)")

CLEAN = "---\nform: structured\n---\n\n# 점검 결과\n\n**점검 결과 요약** — 발행 전 확인\n\n- **결과**: 오류 0건\n"
DIRTY = ("---\nform: structured\n---\n\n# 점검 결과\n\n**점검 결과 요약** — 발행 전 확인\n\n"
         "- **산출물**: 해당 폴더에\n- **주체**: 우리 제품이 아님\n")


def run(*files):
    done = subprocess.run(
        [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), *map(str, files), "--no-rules"],
        capture_output=True, text=True, encoding="utf-8")
    return done.stdout


class SummaryLineContract(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        cls.clean = cls.dir / "a-clean.md"
        cls.dirty = cls.dir / "b-dirty.md"
        cls.clean.write_text(CLEAN, encoding="utf-8")
        cls.dirty.write_text(DIRTY, encoding="utf-8")

    def test_the_line_is_there_and_counts_every_file(self):
        """맨 앞 파일이 깨끗해도 합계는 뒤 파일의 오류까지 센다."""
        out = run(self.clean, self.dirty)
        per_file = [int(n) for n in re.findall(r"^── .*?오류 (\d+) · 주의", out, re.M)]

        m = CONTRACT.search(out)

        self.assertIsNotNone(m, f"합계 줄이 바깥이 읽는 모양이 아닙니다:\n{out[-300:]}")
        self.assertGreater(int(m.group(1)), 0, "뒤 파일의 오류를 합계가 안 셌습니다")
        self.assertEqual(int(m.group(1)), sum(per_file),
                         "합계가 파일별 오류의 합과 다릅니다")

    def test_a_clean_run_says_zero(self):
        """깨끗하면 0 — 그쪽은 0 일 때만 사이트를 만든다."""
        m = CONTRACT.search(run(self.clean))

        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "0")

    def test_the_summary_comes_last(self):
        """그쪽은 첫 매치를 쓴다 — 합계 줄보다 앞에 같은 모양이 있으면 그것을 읽는다."""
        out = run(self.clean, self.dirty)

        self.assertEqual(len(CONTRACT.findall(out)), 1, "합계 모양의 줄이 둘 이상입니다")


if __name__ == "__main__":
    unittest.main()
