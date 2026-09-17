"""사용자가 확정한 교정이 **2층이 읽는 곳까지** 닿는지 본다.

**왜 있나.** `promote_feedback.py --apply` 는 정본(`user-confirmed-phrases.jsonl`)
과 확정 규칙·회귀 시료를 갱신하지만 **`core-rules.md` 의 표는 안 건드린다.**
2층이 읽는 것은 그 표뿐이고, 표에 그 줄이 「이 표가 그 교정들이 실제로 읽히는
유일한 곳」이라고 적혀 있다.

그래서 승격만 하고 표에 안 올리면 **기록은 남고 행동은 안 바뀐다** — 이
저장소가 되풀이해 걸린 「규칙을 썼다 ≠ 규칙이 적용된다」다.

**줄여 적은 것은 어긋난 것이 아니다.** 발표자 노트에서 온 긴 교정 셋은 표에
앞머리만 실려 있다(「갈래는 둘」 = 「갈래는 둘, 요구사항에서 …」). 그 셋은
이름으로 못 박고, **그 밖에 새로 빠지는 것이 생기면 멈춘다.**
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

ANNOTATIONS = (repo_paths.REPO / "data" / "annotations"
               / "user-confirmed-phrases.jsonl")
CORE_RULES = repo_paths.SKILL / "references" / "core-rules.md"

#: 표에 **줄여** 실린 교정 — 글자 그대로는 없지만 2층은 읽는다.
#: 새로 줄여 싣는 것이 생기면 여기 이름을 더한다. 줄이지 않고 올렸으면 뺀다.
SHORTENED = {
    "검증에서 사람이 가장 많이 붙는 곳이 테스트를 만드는 구간이고, 여기를 AI로 풉니다",
    "갈래는 둘, 요구사항에서 도출하는 것과 코드 구조를 훑어 커버리지를 채우는 것입니다",
    "검증은 코드가 바뀔 때마다 반복해서 도는 일이라",
}

ROW = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", re.M)


def annotations() -> list[dict]:
    return [json.loads(line)
            for line in ANNOTATIONS.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def table_rows() -> dict[str, str]:
    """표의 「수정 전 → 수정 후」. 머리줄과 구분줄은 뺀다."""
    text = CORE_RULES.read_text(encoding="utf-8")
    start = text.index("## 사용자가 확정한 대표 수정")
    body = text[start:]
    end = body.find("\n## ", 1)
    body = body[:end] if end > 0 else body
    rows = {}
    for before, after, _cond in ROW.findall(body):
        if before in ("수정 전", "---") or set(before) <= {"-"}:
            continue
        rows[before] = after
    return rows


class ConfirmedEditsReachLayer2Tests(unittest.TestCase):

    def test_the_table_is_not_empty(self) -> None:
        self.assertGreater(len(table_rows()), 5,
                           "대표 수정 표를 못 읽었습니다 — 절 제목이 바뀌었나 봅니다")

    def test_every_confirmed_edit_is_in_the_table(self) -> None:
        rows = table_rows()
        missing = {a["original"] for a in annotations()
                   if a["original"] not in rows}
        self.assertEqual(
            SHORTENED, missing,
            "정본과 표가 어긋납니다. 새로 빠진 것은 표에 올리고(2층이 읽는 "
            "유일한 곳입니다), 줄여 실은 것이면 이 시험의 SHORTENED 에 "
            f"이름을 더합니다.\n   빠진 것: {sorted(missing - SHORTENED)}\n"
            f"   이제 표에 있는데 목록에 남은 것: {sorted(SHORTENED - missing)}")

    def test_matching_rows_keep_the_same_fix(self) -> None:
        """글자 그대로 실린 줄은 **고친 말까지** 정본과 같아야 한다."""
        rows = table_rows()
        for a in annotations():
            if a["original"] not in rows:
                continue
            self.assertEqual(
                a["revised"], rows[a["original"]],
                f"「{a['original']}」 의 고친 말이 정본과 표에서 다릅니다 — "
                "두 곳이 되면 한쪽이 낡습니다")


if __name__ == "__main__":
    unittest.main()
