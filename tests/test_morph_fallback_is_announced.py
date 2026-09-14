"""형태소 분석기 없이 좁게 본 것을 **말하는지** 확인한다.

**왜 시험이 필요한가.** 형태소가 없으면 「~는 때」를 용언 목록으로만 본다. 목록 밖
용언은 통째로 미탐이므로, 그 사실을 안 적으면 **좁게 본 것이 「오류 0」으로 읽힌다.**
이 저장소가 「끈 갈래를 출력에 적는다」로 지키는 것과 같은 원칙이다.

★ 처음에는 `importlib.util.find_spec` 으로 **예측**해 적었다. 명세는 있는데 불러오기가
터지는 환경에서 예측이 「있음」이라, 좁게 검사하고도 **아무 말을 안 했다** — 막으려던
실패가 그대로 났다. 그래서 예측이 아니라 **실제로 대비책을 쓴 사실**을 적는다.

⚠️ 후보가 없는 문서에서는 **아무 말도 하면 안 된다.** 판정이 안 깎였는데 경고를 내면
소음이고, 소음이 섞인 경고는 아무도 안 본다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

DOC = ("---\nform: prose\n---\n\n# 사례\n\n**검사 대상** — 한 줄\n\n"
       "- 메일을 보내는 때를 정합니다\n- 묻는 때를 옮겼습니다\n")
CLEAN = ("---\nform: prose\n---\n\n# 사례\n\n**검사 대상** — 한 줄\n\n"
         "- 필요할 때만 부릅니다\n")
NOTICE = "형태소 분석기 없음"


def run(doc: str, block: bool):
    """검사기를 돌린다. `block` 이면 형태소 분석기를 못 쓰게 만든다."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "t.md"
        path.write_text(doc, encoding="utf-8")
        env = dict(os.environ)
        if block:
            # 명세는 있고 불러오기만 터지는 환경 — 예측으로는 못 잡는 모양이다.
            Path(d, "kiwipiepy.py").write_text(
                "raise ImportError('시험이 막았습니다')", encoding="utf-8")
            env["PYTHONPATH"] = d + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(path), "--no-rules"],
            capture_output=True, text=True, encoding="utf-8", env=env).stdout


class MorphFallbackTests(unittest.TestCase):
    def test_it_says_when_it_looked_without_the_analyzer(self):
        """대비책을 쓴 검사는 그 사실을 본문과 합계 양쪽에 적는다."""
        out = run(DOC, block=True)
        self.assertIn(NOTICE, out, f"좁게 보고도 말하지 않았습니다:\n{out}")
        self.assertIn("형태소 분석기 없이 본 곳 있음", out,
                      f"합계 줄에 안 적혔습니다 — 합계만 잘라 보는 사람이 있습니다:\n{out}")

    def test_it_stays_quiet_when_nothing_was_narrowed(self):
        """후보가 없으면 판정이 안 깎였으므로 아무 말도 안 한다."""
        out = run(CLEAN, block=True)
        self.assertNotIn(NOTICE, out, f"깎인 것이 없는데 경고를 냈습니다:\n{out}")

    def test_it_stays_quiet_when_the_analyzer_works(self):
        out = run(DOC, block=False)
        self.assertNotIn(NOTICE, out, f"분석기가 있는데 없다고 했습니다:\n{out}")

    def test_the_analyzer_finds_what_the_word_list_cannot(self):
        """이 규칙을 형태소로 옮긴 까닭 — 목록 밖 용언은 글자로 못 잡는다."""
        wide = run(DOC, block=False).count("지어낸 명사구")
        narrow = run(DOC, block=True).count("지어낸 명사구")
        self.assertGreater(
            wide, narrow,
            "형태소 판정이 용언 목록보다 더 잡지 못했습니다 — 옮긴 이유가 사라집니다")

    def test_it_names_the_word_that_was_caught(self):
        """지적에 **어절 처음부터** 실어야 어느 말이 걸렸는지 보인다.

        어미부터 자르면 전부 「는 때」로 뭉개져 사람이 고칠 곳을 못 찾는다 —
        실측에서 15종이 한 종으로 뭉개졌다. 돌연변이가 이 시험의 빈자리를 짚었다.
        """
        out = run(DOC, block=False)
        self.assertIn("「보내는 때」", out,
                      f"어간이 빠진 채 지적했습니다 — 어느 말인지 안 보입니다:\n{out}")

    def test_the_word_list_still_works_on_its_own(self):
        """★ 대비책 경로도 시험한다.

        형태소가 들어오자 회귀 시료가 전부 형태소 경로만 타게 됐다. 돌연변이로
        확인하니 **용언 목록을 부숴도 시료가 안 깨졌다** — 대비책이 시험 밖으로
        나간 것이다. 안 쓰는 길은 조용히 썩는다.
        """
        doc = ("---\nform: prose\n---\n\n# 사례\n\n**검사 대상** — 한 줄\n\n"
               "- 묻는 때를 옮겼습니다\n"          # 목록에 있는 용언 → 잡아야 함
               "- 배포하는 때를 정합니다\n"        # 생산형 「~하는」 → 잡아야 함
               "- 이제는 때가 됐습니다\n"          # 체언 + 보조사 → 통과해야 함
               "- 그는 때를 기다립니다\n")         # 체언 + 보조사 → 통과해야 함
        out = run(doc, block=True)
        for hit in ("묻는 때", "배포하는 때"):
            self.assertIn(hit, out, f"대비책이 「{hit}」를 놓쳤습니다:\n{out}")
        for miss in ("이제는 때", "그는 때"):
            self.assertNotIn(miss, out, f"대비책이 「{miss}」를 잘못 잡았습니다:\n{out}")


if __name__ == "__main__":
    unittest.main()
