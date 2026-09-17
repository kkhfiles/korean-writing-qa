"""사용자가 짚어 준 지적이 **하나도 새지 않게** 지킨다.

**왜 필요한가.** 2026-09-15 에 「짚어 준 것을 다 고칠 수 있게 됐나」를 물었더니,
답을 내려고 **회차별 지적 38건을 대화 기억으로 손수 복원**해야 했다. 그렇게 재
보니 19건은 어느 장치도 안 짚고 있었고, 그동안 아무도 그 사실을 몰랐다.
사례집(`contributed.jsonl`)에는 **덮인 것만** 들어가 있었기 때문이다 — 안 덮인 것은
애초에 등록되지 않으니 빠졌다는 사실 자체가 사라졌다.

**그래서 대장을 따로 둔다.** `flagged-rounds.jsonl` 은 「짚어 준 것 전부」이고,
사례집은 「시험이 돌리는 것」이다. 둘은 목적이 다르다 — 대장은 **빠진 것을 보이게**
하고, 사례집은 **되돌아가는 것을 막는다.**

**주인 넷.** 모든 지적은 넷 중 하나를 가져야 한다. 「미정」이 없는 것이 이 시험의 핵심이다.

| 주인 | 뜻 | 이 시험이 보는 것 |
|---|---|---|
| `규칙` | 검사기가 잡는다 | 그 문장을 넣으면 실제로 지적이 난다 |
| `단어 점검` | 단어 점검이 그 말을 집는다 | 단어 점검 목록에 그 낱말의 원형이 오른다 |
| `2층` | 문맥을 봐야 갈린다 · 규칙집을 읽는 모델이나 사람이 본다 | 맡은 스킬 파일이 실제로 있고 그 대목을 적고 있다 |
| `대기` | 규칙으로 올릴 것 · 아직 안 올림 | 사례집에 `open` 으로 박혀 있다 |

⚠️ **「2층」을 도피처로 쓰지 않는다.** 기계로 못 가른다는 판정에는 근거가 필요하고,
   그 근거는 스킬에 적혀 있어야 한다. 스킬이 안 적고 있으면 이 시험이 깨진다.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

LEDGER = repo_paths.REPO / "data" / "cases" / "flagged-rounds.jsonl"
CASES = repo_paths.REPO / "data" / "cases" / "contributed.jsonl"
SWEEP = repo_paths.REPO / "scripts" / "rare_words.py"
OWNERS = {"규칙", "단어 점검", "2층", "대기"}

#: 「대기」는 **내려가기만 한다.** 새 지적을 대기로 밀어 넣어 쌓는 것을 막는다.
#: 올리려면 왜 늘어야 하는지를 사람이 판단해 이 수를 고친다.
WAITING_CEILING = 11


def load(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


LEDGER_ROWS = load(LEDGER)
HEAD = "---\nform: prose\n---\n\n# 대장\n\n**검사 대상** — 한 줄\n\n"
FIRST_LINE = HEAD.count("\n") + 1


def run_checker(sentences: list[str]) -> set[int]:
    """문장을 한 줄씩 넣고 **지적이 난 줄 번호**를 낸다."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.md"
        p.write_text(HEAD + "".join(f"- {s}\n" for s in sentences), encoding="utf-8")
        out = subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(p), "--no-rules", "-v"],
            capture_output=True, text=True, encoding="utf-8").stdout
    return {int(m) for m in re.findall(r"[❌⚠️]\s*\[[^\]]+\]\s*(\d+)행", out)}


def morph_ok() -> bool:
    try:
        import kiwipiepy  # noqa: F401
    except Exception:
        return False
    return True


class LedgerShapeTests(unittest.TestCase):
    """대장 자체가 성한지 — 한 건도 없어도 이 시험은 돈다."""

    def test_the_ledger_exists_and_is_not_empty(self) -> None:
        self.assertTrue(LEDGER.is_file(), f"대장이 없습니다: {LEDGER}")
        self.assertTrue(LEDGER_ROWS, "대장이 비었습니다 — 짚어 준 것이 하나도 안 적혔습니다")

    def test_every_entry_has_an_owner(self) -> None:
        """★ 이 시험의 핵심 — **주인 없는 지적이 없어야 한다.**"""
        for r in LEDGER_ROWS:
            for field in ("flag_id", "round", "text", "sentence", "owner", "note"):
                self.assertIn(field, r, f"{r.get('flag_id', '?')} 에 「{field}」 가 없습니다")
            self.assertIn(
                r["owner"], OWNERS,
                f"{r['flag_id']} 「{r['text']}」 의 주인이 {OWNERS} 밖입니다: {r['owner']} — "
                "짚어 준 것은 넷 중 하나가 맡아야 합니다")
            self.assertTrue(r["note"].strip(),
                            f"{r['flag_id']} 에 판단 근거가 없습니다")

    def test_ids_do_not_collide(self) -> None:
        ids = [r["flag_id"] for r in LEDGER_ROWS]
        self.assertEqual(len(ids), len(set(ids)), "대장 번호가 겹칩니다")

    def test_the_sentence_contains_the_flagged_words(self) -> None:
        """짚어 준 말이 예문 안에 **글자 그대로** 있어야 한다.

        **왜 전체를 보나**(2026-09-17 넓힘). 예전에는 첫 낱말만 봤다. F-036 의
        짚은 표현이 「물으면 기록하지 않습니다」였는데 예문은 「물으면 **아무도**
        기록하지 않습니다」라 한 낱말이 빠져 있었고, 첫 낱말 「물으면」이 있어서
        통과했다. 그 탓에 2층 탐침이 정답을 못 맞춰 재현율을 한 건 적게 셌다.
        대장 어느 줄에도 가운뎃점으로 여럿을 적은 것이 없어 나눌 까닭이 없다.
        """
        for r in LEDGER_ROWS:
            self.assertIn(
                r["text"], r["sentence"],
                f"{r['flag_id']}: 예문에 「{r['text']}」 가 글자 그대로 없습니다 — "
                f"{r['sentence']}")


class RuleOwnedTests(unittest.TestCase):
    """주인이 「규칙」이면 검사기가 실제로 잡아야 한다."""

    def test_the_checker_actually_catches_them(self) -> None:
        rows = [r for r in LEDGER_ROWS if r["owner"] == "규칙"]
        if not rows:
            self.skipTest("규칙이 맡은 지적이 없다")
        hit_lines = run_checker([r["sentence"] for r in rows])
        missed = [r for i, r in enumerate(rows) if FIRST_LINE + i not in hit_lines]
        self.assertFalse(
            missed,
            "규칙이 맡았다고 적혔는데 검사기가 안 잡습니다 — 규칙이 되돌아갔거나 "
            "대장이 틀렸습니다:\n" + "\n".join(
                f"  {r['flag_id']} 「{r['text']}」 — {r['sentence']}" for r in missed))


class SweepOwnedTests(unittest.TestCase):
    """주인이 「단어 점검」면 단어 점검 목록에 그 낱말이 올라야 한다."""

    def test_the_sweep_actually_surfaces_them(self) -> None:
        rows = [r for r in LEDGER_ROWS if r["owner"] == "단어 점검"]
        if not rows:
            self.skipTest("단어 점검이 맡은 지적이 없다")
        if not morph_ok():
            self.skipTest("형태소 분석기가 없어 단어 점검을 못 돌린다")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            p.write_text("# 대장\n\n" + "".join(f"- {r['sentence']}\n" for r in rows),
                         encoding="utf-8")
            out = subprocess.run(
                [sys.executable, "-X", "utf8", str(SWEEP), str(p), "--max", "400", "--top", "80"],
                cwd=repo_paths.REPO, capture_output=True, text=True, encoding="utf-8").stdout
        listed = set(re.findall(r"^\s+([가-힣]+)/[A-Z]{2,3}\s+이 문서", out, re.M))
        # 대장의 note 가 「없애/VV」처럼 어느 낱말로 잡히는지를 적고 있다
        missed = []
        for r in rows:
            want = {w.split("/")[0] for w in re.findall(r"[가-힣]+/[A-Z]{2,3}", r["note"])}
            self.assertTrue(want, f"{r['flag_id']}: note 에 「없애/VV」 꼴로 낱말을 적어야 합니다")
            if not (want & listed):
                missed.append((r, sorted(want)))
        self.assertFalse(
            missed,
            "단어 점검이 맡았다고 적혔는데 목록에 안 오릅니다 — 빈도표나 문턱이 바뀌었습니다:\n"
            + "\n".join(f"  {r['flag_id']} 「{r['text']}」 기대 {w}" for r, w in missed))


class Layer2OwnedTests(unittest.TestCase):
    """주인이 「2층」이면 그 판단이 스킬에 적혀 있어야 한다.

    ⚠️ 「2층이 본다」는 **아무도 안 본다**로 쉽게 미끄러진다. 맡은 곳을 적게 하고,
       그 곳이 실제로 있는지 본다.
    """

    def test_the_named_place_exists_and_covers_it(self) -> None:
        """갈 곳은 둘 중 하나이고, 어느 쪽이든 실재해야 한다.

        - **스킬 단계** — 갈래를 알아보는 곳(`finalize-korean-document §9`)
        - **핵심 규칙의 절** — 확정된 짝을 읽는 곳
          (`core-rules.md 「사용자가 확정한 대표 수정」`)

        사용자가 고친 꼴을 확정해 준 것은 뒤쪽으로 간다(2026-09-17). 스스로
        알아낼 것이 아니라 표에서 읽을 것이기 때문이다.
        """
        rows = [r for r in LEDGER_ROWS if r["owner"] == "2층"]
        if not rows:
            self.skipTest("2층이 맡은 지적이 없다")
        core = (repo_paths.SKILL / "references"
                / "core-rules.md").read_text(encoding="utf-8")
        for r in rows:
            # 세 번째 상태 — **맥락 한정 선택**(2026-09-17). 그 문서에서
            # 끝났고 일반 규칙으로 안 올린 것이라 갈 곳이 없는 게 맞다.
            # 표시와 고른 문장이 **둘 다** 있어야 넘어간다 — 구멍이 되지 않게.
            if r.get("general_rule") is False and (r.get("revised") or "").strip():
                continue
            m = re.search(r"([a-z][a-z0-9-]+)\s*§", r["note"])
            if m is not None:
                skill = repo_paths.REPO / "skills" / m.group(1) / "SKILL.md"
                self.assertTrue(skill.is_file(),
                                f"{r['flag_id']}: 스킬이 없습니다 — {skill}")
                continue
            table = re.search(r"core-rules\.md 「(.+?)」", r["note"])
            self.assertIsNotNone(
                table,
                f"{r['flag_id']}: 「2층」이면 맡은 곳을 적어야 합니다 — "
                "「finalize-korean-document §9」 이거나 "
                f"「core-rules.md 「절 이름」」 꼴입니다 — {r['note']}")
            self.assertIn(
                f"## {table.group(1)}", core,
                f"{r['flag_id']} 가 core-rules.md 「{table.group(1)}」 를 "
                "가리키는데 그런 절이 없습니다")

    def test_the_skill_names_the_defect_kinds(self) -> None:
        """스킬 본문이 문맥 결함 갈래를 실제로 적고 있는지."""
        rows = [r for r in LEDGER_ROWS if r["owner"] == "2층"]
        if not rows:
            self.skipTest("2층이 맡은 지적이 없다")
        text = (repo_paths.REPO / "skills" / "finalize-korean-document"
                / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("고치다 논리를 깬 곳", text,
                      "문맥 층이 논리 결함 갈래를 안 적고 있습니다 — 「2층」이 빈 약속이 됩니다")


class WaitingOwnedTests(unittest.TestCase):
    """주인이 「대기」면 사례집에 `open` 으로 박혀 있어야 한다.

    박아 두면 규칙이 들어간 순간 unittest 가 「예정에 없던 통과」로 알린다.
    안 박아 두면 규칙이 생겨도 대기인 채로 남는다.
    """

    def test_every_waiting_entry_is_a_registered_case(self) -> None:
        rows = [r for r in LEDGER_ROWS if r["owner"] == "대기"]
        if not rows:
            self.skipTest("대기가 없다")
        by_text = {c["text"]: c for c in load(CASES)}
        for r in rows:
            case = by_text.get(r["sentence"])
            self.assertIsNotNone(
                case,
                f"{r['flag_id']} 「{r['text']}」 가 사례집에 없습니다 — "
                f"`python scripts/add_case.py --text \"{r['sentence']}\" "
                f"--expect finding --form prose` 로 박습니다")
            self.assertEqual(
                "open", case["status"],
                f"{r['flag_id']} 「{r['text']}」 는 사례집에서 이미 {case['status']} 입니다 — "
                "규칙이 들어갔으면 대장의 주인도 「규칙」으로 올립니다")

    def test_waiting_does_not_pile_up(self) -> None:
        """★ 대기는 **내려가기만 한다.**

        천장이 없으면 새 지적을 전부 대기로 밀어 넣고 「등록했다」고 말할 수 있다.
        그것이 바로 이 시험이 막으려는 것이다.
        """
        n = sum(1 for r in LEDGER_ROWS if r["owner"] == "대기")
        self.assertLessEqual(
            n, WAITING_CEILING,
            f"대기가 {n}건으로 천장 {WAITING_CEILING}건을 넘었습니다 — 규칙을 올리거나, "
            "정말 늘려야 하면 WAITING_CEILING 을 사람이 판단해 고칩니다")


if __name__ == "__main__":
    unittest.main()
