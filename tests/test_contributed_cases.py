"""이슈로 들어온 사례를 매번 다시 돌린다.

**왜.** 사례가 이슈 본문에만 있으면 규칙을 고칠 때 아무도 그것을 다시 돌려 보지
않는다. 「고쳐 달라」는 말은 남지만 고쳐졌는지 확인하는 장치가 없다.

**상태 둘을 다르게 다룬다.**

| 상태 | 시험에서 | 왜 |
|---|---|---|
| `pinned` | 깨지면 실패 | 규칙이 되돌아간 것이다 |
| `open` | 실패가 예정된 것 | 아직 규칙이 없으니 실패가 정상이다 |

`open` 인 사례가 **통과하기 시작하면** unittest 가 「예정에 없던 통과」로 알린다.
그게 신호다 — `python scripts/add_case.py --recheck` 로 `pinned` 으로 올린다.
이 장치가 없으면 규칙이 들어간 뒤에도 사례가 `open` 인 채 남고, 나중에 그 규칙이
되돌아가도 아무도 모른다.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import add_case  # noqa: E402
import repo_paths  # noqa: E402

CASES = repo_paths.REPO / "data" / "cases" / "contributed.jsonl"


def load() -> list[dict]:
    if not CASES.is_file():
        return []
    return [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]


class ContributedCaseFileTests(unittest.TestCase):
    """파일 자체가 성한지 — 사례가 하나도 없어도 이 시험은 돈다."""

    def test_every_record_has_what_a_reviewer_needs(self) -> None:
        for record in load():
            with self.subTest(case=record.get("case_id")):
                for field in ("case_id", "text", "expect", "why", "status"):
                    self.assertTrue(record.get(field), f"{field} 가 비었습니다: {record}")
                self.assertIn(record["expect"], add_case.EXPECTS)
                self.assertIn(record["status"], ("open", "pinned"))

    def test_case_ids_are_unique(self) -> None:
        ids = [r["case_id"] for r in load()]
        self.assertEqual(len(ids), len(set(ids)), "사례 번호가 겹칩니다")

    def test_named_kinds_exist_in_the_checker(self) -> None:
        """없는 갈래 이름을 적어 두면 고칠 사람이 엉뚱한 곳을 본다."""
        kinds = {r["kind"] for r in load() if r.get("kind")}
        if not kinds:
            self.skipTest("갈래를 적은 사례가 없습니다")
        import importlib.util
        spec = importlib.util.spec_from_file_location("dsc", repo_paths.CHECKER)
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        for kind in sorted(kinds):
            with self.subTest(kind=kind):
                self.assertIn(kind, checker.ALL_KINDS)


def make_test(record: dict):
    def check(self):
        got, kinds = add_case.verdict(record["text"], record.get("form", "structured"))
        self.assertEqual(
            record["expect"], got,
            f'{record["case_id"]} 「{record["text"]}」\n'
            f'  바라는 판정 {record["expect"]} · 나온 판정 {got}'
            + (f' ({" · ".join(kinds)})' if kinds else "")
            + f'\n  근거 {record["why"]}',
        )
        # ★ 갈래까지 본다 (2026-09-10). 판정만 보면 **그 시료가 자기 규칙을 못
        #   고정한다** — 문장이 다른 규칙에도 걸리면 정작 지키려던 규칙을 통째로
        #   지워도 시험이 초록이다. 돌연변이로 실제로 그랬다(「한도를 먹」).
        #   시료 41건에 대 보니 어긋남 0건이라 그대로 켤 수 있었다.
        if record["expect"] == "finding" and record.get("kind"):
            self.assertIn(
                record["kind"], kinds,
                f'{record["case_id"]} 「{record["text"]}」\n'
                f'  이 시료가 지키려는 갈래 {record["kind"]} 가 안 나왔습니다'
                f' · 나온 것 {" · ".join(kinds) or "없음"}',
            )
    check.__doc__ = f'{record["case_id"]} — {record["text"][:40]}'
    return check if record["status"] == "pinned" else unittest.expectedFailure(check)


class ContributedCaseTests(unittest.TestCase):
    """사례마다 시험 하나. 어느 사례가 깨졌는지 이름으로 바로 보인다."""


for _record in load():
    setattr(ContributedCaseTests, f'test_{_record["case_id"].replace("-", "_")}',
            make_test(_record))


if __name__ == "__main__":
    unittest.main()
