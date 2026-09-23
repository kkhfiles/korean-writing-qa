"""반말 변환기가 검사기와 같은 문장을 보고, 끝 음절만 바꾸고, 인용은 안 건드리는지.

**왜 있나** — 2026-09-23 에 반말 금지가 오류 등급이 되면서 다른 프로젝트 문서
3,632줄이 걸렸다. 그 문서들을 이 변환기로 고치라고 넘긴다. 변환기가 검사기와 다른
문장을 보면 고친 뒤에도 게이트가 막고, 인용을 건드리면 남의 말 원문이 바뀐다.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

TOOL = repo_paths.REPO / "scripts" / "make_polite.py"
HAS_KIWI = importlib.util.find_spec("kiwipiepy") is not None

DOC = """# 변환 시험

변환기 시험 문서 · 반말 조각만 바꿈

- **결론 머리** — 이 규칙은 목록에서도 걸린다.
- 설명 문장만 있는 항목도 반말이면 바뀐다.

| 항목 | 설명 |
|---|---|
| 첫째 | 표 칸의 문장도 존댓말로 쓴다. |

본문 문단은 이 줄에서 끝난다. 사용자가 「그건 안 된다」라고 적었다.

`코드는 그대로다` 뒤 문장은 바뀐다.
"""


def load():
    spec = importlib.util.spec_from_file_location("make_polite", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(HAS_KIWI, "형태소 분석기(kiwipiepy)가 없어 안 봤습니다")
class MakePoliteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tool = load()

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def plain(self, path: Path) -> list:
        """검사기가 낸 반말 지적의 줄 번호 — 지적은 (갈래, "12행  …") 꼴이다."""
        err, _, _ = self.tool.checker().scan_md(str(path))
        return [int(msg.split("행")[0]) for kind, msg in err if kind == "반말 서술형"]

    # ── 끝 음절 ──────────────────────────────────────────────────────────────

    def test_each_ending_turns_into_the_polite_form(self) -> None:
        """분석기의 결합 기능으로 되붙이던 판은 「가져왔다 → 가져었습니다」로 깨졌다."""
        cases = {
            "가져왔다": "가져왔습니다", "없다": "없습니다", "크다": "큽니다",
            "한국어다": "한국어입니다", "길이다": "길입니다", "것이다": "것입니다",
            "아니다": "아닙니다", "먹는다": "먹습니다", "않는다": "않습니다",
            "쓴다": "씁니다", "돈다": "돕니다", "한다": "합니다", "된다": "됩니다",
            "읽힌다": "읽힙니다", "갈린다": "갈립니다", "잰다": "잽니다",
            # 낱말만 넘기던 판은 이 끝을 연결 어미로 읽어 못 바꿨다
            "간다": "갑니다", "돌아간다": "돌아갑니다", "온다": "옵니다",
            "고른다": "고릅니다", "실패한다": "실패합니다", "나쁘다": "나쁩니다",
        }
        for plain, polite in cases.items():
            self.assertEqual(polite, self.tool.polite_word(plain), plain)

    def test_an_invented_verb_after_a_particle_reads_as_a_dropped_copula(self) -> None:
        """분석기가 「바뀌기까지다」를 「까지 + 하 + 다」로 읽어 「바뀌기까집니다」로 틀리게
        바꿨다 — 빠뜨린 것이 아니라 **틀린 말을 만든 것**이다(다른 세션 제보 2026-09-23)."""
        self.assertEqual("바뀌기까지입니다", self.tool.polite_word("바뀌기까지다"))

    def test_the_word_before_settles_what_the_word_alone_cannot(self) -> None:
        """낱말만 주면 「만다」를 「만들어」로, 「긴급도다」를 「긴급 + 도다」로 읽는다."""
        self.assertEqual("맙니다", self.tool.polite_word("만다", "재고"))
        self.assertEqual("긴급도입니다", self.tool.polite_word("긴급도다", "착수"))

    def test_the_converter_passes_the_word_before(self) -> None:
        """함수가 맞아도 변환이 앞 낱말을 안 넘기면 실문서에서는 그대로 못 바꾼다."""
        text = ("# 시험\n\n시험 문서 · 앞 낱말\n\n- 열은 상태가 아니라 착수 긴급도다.\n"
                "- 지나가는 것 한 번에 한 번 재고 만다.\n")
        path = self.write("문서.md", text)
        done, missed = self.tool.convert(str(path), apply=True)
        self.assertEqual([], missed)
        got = path.read_text(encoding="utf-8")
        self.assertIn("착수 긴급도입니다.", got)
        self.assertIn("재고 맙니다.", got)

    def test_an_ending_it_cannot_read_is_left_to_a_person(self) -> None:
        self.assertIsNone(self.tool.polite_word("다"))
        self.assertIsNone(self.tool.polite_word("가라"))

    # ── 검사기와 같은 문장을 본다 ────────────────────────────────────────────

    def test_it_finds_a_part_on_every_line_the_checker_flags(self) -> None:
        """줄을 고르는 것은 검사기지만 줄 안의 조각은 여기서 다시 찾는다 — 어긋나면
        검사기가 짚은 줄을 변환기가 못 보고 지나간다."""
        path = self.write("문서.md", DOC)
        flagged = set(self.plain(path))
        self.assertTrue(flagged, "시료가 반말을 안 담고 있습니다")
        found = {n for n, _ in self.tool.plain_parts(str(path), DOC)}
        self.assertEqual(flagged, found)

    def test_after_the_rewrite_the_checker_finds_no_plain_speech(self) -> None:
        path = self.write("문서.md", DOC)
        done, missed = self.tool.convert(str(path), apply=True)
        self.assertEqual([], missed)
        self.assertEqual(6, len(done), done)
        self.assertEqual([], self.plain(path))

    # ── 안 건드리는 것 ───────────────────────────────────────────────────────

    def test_quotes_and_code_keep_their_words(self) -> None:
        """남의 말 원문은 글자가 같아야 한다."""
        path = self.write("문서.md", DOC)
        self.tool.convert(str(path), apply=True)
        text = path.read_text(encoding="utf-8")
        self.assertIn("「그건 안 된다」라고 적었습니다", text)
        self.assertIn("`코드는 그대로다` 뒤 문장은 바뀝니다", text)
        self.assertIn("존댓말로 씁니다", text)

    def test_without_apply_nothing_is_written(self) -> None:
        path = self.write("문서.md", DOC)
        done, _ = self.tool.convert(str(path))
        self.assertTrue(done)
        self.assertEqual(DOC, path.read_text(encoding="utf-8"))

    def test_an_instruction_file_is_left_alone(self) -> None:
        """Claude 만 읽는 지시 파일은 검사기가 반말을 안 짚는다 — 변환기도 따라간다."""
        path = self.write("CLAUDE.md", DOC)
        done, _ = self.tool.convert(str(path), apply=True)
        self.assertEqual([], done)

    def test_a_word_split_by_bold_keeps_its_bold(self) -> None:
        """「**배수**다」는 원문에 「배수다」가 없다. 이 저장소에서 손으로 고친 열아홉
        곳이 전부 이 꼴이었다 — 바꾸는 음절이 굵게 밖이면 굵게는 그대로 두고 바꾼다."""
        text = ("# 시험\n\n시험 문서 · 굵게 가른 낱말\n\n- 깊이를 올릴 때의 **배수**다.\n"
                "- 호출마다 **6만 토큰**이다.\n- 둘 다 같은 점수**다**.\n")
        path = self.write("문서.md", text)
        done, missed = self.tool.convert(str(path), apply=True)
        self.assertEqual([], missed)
        got = path.read_text(encoding="utf-8")
        self.assertIn("**배수**입니다.", got)
        self.assertIn("**6만 토큰**입니다.", got)
        self.assertIn("같은 점수**입니다**.", got)
        self.assertEqual([], self.plain(path))

    def test_the_sentence_end_changes_not_only_the_trailing_parenthesis(self) -> None:
        """처음 판은 마지막 「…다」 하나만 바꿔 괄호 안만 바뀌고 문장 끝은 반말로 남았다.

        실문서 세 개에서 36곳이 그 꼴로 남았다(2026-09-23).
        """
        text = ("# 시험\n\n시험 문서 · 꼬리 괄호\n\n- 설정은 덮어쓴다(더하지 않는다)\n"
                "- 날짜를 못 읽으면 막지 않는다(막히는 쪽이 더 나쁘다)\n"
                "- 판정은 여기서 끝난다(부록 E)\n")
        path = self.write("문서.md", text)
        self.assertEqual(3, len(self.plain(path)), "시료가 반말로 안 걸립니다")
        _, missed = self.tool.convert(str(path), apply=True)
        self.assertEqual([], missed)
        got = path.read_text(encoding="utf-8")
        self.assertIn("덮어씁니다(더하지 않습니다)", got)
        self.assertIn("막지 않습니다(막히는 쪽이 더 나쁩니다)", got)
        self.assertIn("끝납니다(부록 E)", got)
        self.assertEqual([], self.plain(path))

    def test_both_sides_of_a_dash_change_in_one_run(self) -> None:
        """검사기는 문장마다 첫 조각만 낸다. 변환기도 거기서 멈추면 고친 뒤 다시
        돌렸을 때 대시 뒤 조각이 새로 걸린다 — 실문서 세 개에서 451곳이 그렇게 남았다."""
        text = "# 시험\n\n시험 문서 · 대시 앞뒤\n\n본문은 앞에서 끝난다 — 뒤 조각도 반말로 남는다.\n"
        path = self.write("문서.md", text)
        done, _ = self.tool.convert(str(path), apply=True)
        self.assertEqual(2, len(done), done)
        self.assertEqual([], self.plain(path))

    def test_a_word_wholly_inside_bold_is_left_alone(self) -> None:
        """「돈다 / 안 돈다 / 안 봄」은 그 프로젝트가 정한 판정 값 이름이었다.

        알림에 「굵게 표시는 안 건드린다」고 적어 보냈는데 굵게 안의 낱말을 바꿨다
        (CT2612 세션이 사본으로 재현 · 2026-09-23). 값 이름이 조용히 다른 말이 된다.
        """
        text = ("# 시험\n\n시험 문서 · 판정 값 이름\n\n| 항목 | 설명 |\n|---|---|\n"
                "| **판정** | **돈다** — 프로젝트를 받아 분석을 돌리고 결과를 읽는 경로가 "
                "끝까지 보임 |\n"
                "| **판정** | **안 돈다** — 분석이 중간에 멈춤 |\n")
        path = self.write("문서.md", text)
        done, missed = self.tool.convert(str(path), apply=True)
        self.assertEqual([], done)
        self.assertEqual(2, sum("굵게 안의 낱말" in why for _, _, why in missed), missed)
        self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_a_bold_sentence_still_changes(self) -> None:
        """세 어절부터는 실문서에서 전부 문장이었다 — 굵게 안이라고 멈추면 700곳이 남는다."""
        text = "# 시험\n\n시험 문서 · 굵은 문장\n\n본문 앞 문장 뒤에 **속도를 실측으로 잡았다.** 그래서 늦다.\n"
        path = self.write("문서.md", text)
        self.tool.convert(str(path), apply=True)
        got = path.read_text(encoding="utf-8")
        self.assertIn("**속도를 실측으로 잡았습니다.**", got)
        self.assertIn("그래서 늦습니다.", got)

    def test_bold_cutting_the_changed_syllable_is_left_to_a_person(self) -> None:
        """「**쓴**다」를 「씁니다」로 바꾸면 굵게 표시가 깨진다 — 사람에게 넘긴다."""
        text = "# 시험\n\n시험 문서 · 굵게가 음절을 가름\n\n- 이 규칙은 표 칸에도 **쓴**다.\n"
        path = self.write("문서.md", text)
        done, missed = self.tool.convert(str(path), apply=True)
        self.assertEqual([], done)
        self.assertEqual(1, len(missed))
        self.assertEqual(text, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
