"""사례집의 유형 표가 검사기의 갈래를 전부 싣는지 확인한다.

**왜 시험이 필요한가.** 2026-09-10 에 표가 **26행인데 페이지는 「29가지」라고**
적혀 있었다. 빠진 셋은 며칠 사이에 들어온 갈래였고, 사람이 세어 보고서야 걸렸다.

읽는 사람에게 이 표는 **「이 검사기가 무엇을 보는가」의 전부**다. 갈래가 빠지면
페이지가 실제보다 작아 보이고, 더 나쁘게는 **그 갈래를 안 본다고 읽힌다.**

「같은 함정에 두 번 넘어가면 글이 아니라 기계로 옮긴다」 — 갈래를 넣을 때마다
사람이 표를 기억해야 하는 구조라 실패한다. 여기서 막는다.

⚠️ **비중 숫자는 안 본다.** 실측은 뭉치를 다시 훑어야 나오므로 갈래가 들어온
그날 나올 수 없다. 표는 그런 갈래를 「측정 전」으로 적는다 — 0건과 미측정은
다르고, 이 시험이 요구하는 것은 **행의 존재**뿐이다.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "docs" / "showcase.html"
CHECKER = ROOT / "assets" / "doc-style-check.py"

# 표는 읽는 사람이 쓰는 말로 적고 검사기는 판정 이름으로 적는다. 그 둘의 다리.
ALIAS = {
    "은유 「자리」": "「~하는 자리」",
    "번역투 「그녀」": "번역투 그녀",
}


def table_types() -> list[str]:
    """사례집 유형 표의 첫 칸을 순서대로 낸다."""
    html = SHOWCASE.read_text(encoding="utf-8")
    rows = re.findall(r'<tr><td><span class="dot [ew]"></span>([^<]+)', html)
    return [re.sub(r"\s+", " ", r).strip() for r in rows]


def checker_types() -> list[str]:
    """`--list-rules` 가 내는 갈래 이름을 낸다."""
    done = subprocess.run(
        [sys.executable, "-X", "utf8", str(CHECKER), "--list-rules"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
    names = []
    for line in done.stdout.splitlines():
        if not line.startswith("    ") or not line.strip():
            continue
        name = re.sub(r"\s+", " ", line.strip().split("  ")[0]).strip()
        if re.match(r"^[가-힣「]", name):
            names.append(name)
    return names


class ShowcaseListsEveryRule(unittest.TestCase):
    def test_every_rule_has_a_row(self):
        """갈래를 넣고 표를 안 고치면 여기서 걸린다."""
        shown = {ALIAS.get(t, t) for t in table_types()}
        missing = sorted(set(checker_types()) - shown)
        self.assertEqual(
            [], missing,
            f"사례집 유형 표에 없는 갈래: {missing} — "
            f"docs/showcase.html 의 유형 표에 행을 넣습니다. "
            f"실측 비중이 아직 없으면 「측정 전」으로 적습니다(0건과 다릅니다).")

    def test_no_row_without_a_rule(self):
        """규칙을 뺐는데 표에 남아 있으면 걸린다 — 없는 것을 본다고 광고하게 된다."""
        known = set(checker_types())
        extra = sorted(t for t in {ALIAS.get(x, x) for x in table_types()}
                       if t not in known)
        self.assertEqual([], extra, f"검사기에 없는데 표에 실린 것: {extra}")

    def test_page_count_matches_the_checker(self):
        """페이지가 적어 둔 「N가지」가 실제 갈래 수와 같아야 한다."""
        html = SHOWCASE.read_text(encoding="utf-8")
        counts = {int(n) for n in re.findall(r"(\d+)\s*가지", html)}
        self.assertIn(
            len(checker_types()), counts,
            f"페이지가 적은 가짓수 {sorted(counts)} 에 실제 갈래 수 "
            f"{len(checker_types())} 가 없습니다.")


if __name__ == "__main__":
    unittest.main()
