"""「맞춤법」과 「맞춤법 의심」 갈래가 잡을 것은 잡고 맞는 말은 그대로 두는지 고정한다.

**왜 이 갈래가 생겼나**(2026-11-02). 1층에 맞춤법 규칙이 없어 「됬다」, 「역활」, 「금새」,
「보낼께」가 오류 0 으로 통과했다. 처음 써 보는 사람이 가장 먼저 기대하는 기능이다.

**지켜야 하는 것**
- 목록(`data/catalog/spelling-errors.tsv`)의 틀린 꼴과 문법 꼴(「ㄹ께」, 「-률/-율」, 낱자모)을 잡음
- **낱말 첫머리 조건** — 「지역활성화」 안의 「역활」, 「31일부로」의 「일부로」는 안 잡음
  (진단 2026-11-02 에서 조건 없이 돌렸을 때 실제로 난 오탐)
- 같은 글자가 맞는 말로 쓰이는 문장(적대 문장) — 「제작년도」, 「불길이 타올라」, 「15일께」,
  「선생님들께」, 「모읍니다」, 「ㄱ자 모양」, 「ㅋㅋ」
- 인용(「」), 코드, 대조 예시 줄은 기존 장치대로 빠짐
- 설치가 목록을 옮김 — 안 옮기면 다른 프로젝트의 검사에서 목록 항목이 조용히 빠진다
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install  # noqa: E402
import repo_paths  # noqa: E402

LIST = repo_paths.REPO / "data" / "catalog" / "spelling-errors.tsv"


def load_checker():
    spec = importlib.util.spec_from_file_location("chk_spelling", repo_paths.CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CHK = load_checker()


def words(text: str) -> dict[str, str]:
    """{걸린 글자: 등급}"""
    return {h[1]: h[0] for h in CHK.spelling_hits(text)}


#: (문장, 걸려야 할 글자, 등급)
CATCH = [
    ("어제 배포가 잘 됬다.", "됬", "err"),
    ("그 일은 안 되요.", "되요", "err"),
    ("이렇게 되서 다행입니다.", "되서", "err"),
    ("내일 찾아뵈요.", "뵈요", "err"),
    ("검토를 마쳤읍니다.", "읍니다", "err"),
    ("곧 끝날 거에요.", "거에요", "err"),
    ("그건 제 것이 아니예요.", "아니예요", "err"),
    ("설정이 바꼈습니다.", "바꼈", "err"),
    ("확인해 주십시요.", "십시요", "err"),
    ("팀장의 역활은 조율입니다.", "역활", "err"),
    ("회의가 금새 끝났습니다.", "금새", "err"),
    ("몇일 걸립니까?", "몇일", "err"),
    ("왠만하면 오늘 끝냅니다.", "왠만", "err"),
    ("곰곰히 생각했습니다.", "곰곰히", "err"),
    ("구지 그럴 필요는 없습니다.", "구지", "err"),
    ("작년과 제작년 실적을 비교합니다.", "제작년", "err"),
    # 외래어 표기는 주의 — 사내에 굳은 표기와 규범이 어긋나는 일이 많아 발행을 막지 않음(2026-11-02 사용자 결정)
    ("메세지를 보냈습니다.", "메세지", "warn"),
    ("신규 컨텐츠를 올립니다.", "컨텐츠", "warn"),
    ("배포 디렉토리를 정리합니다.", "디렉토리", "warn"),
    ("릴리즈 노트를 씁니다.", "릴리즈", "warn"),
    ("API메세지를 고칩니다.", "메세지", "warn"),  # 라틴 글자 뒤는 낱말 첫머리
    ("화면을 캡쳐해 붙입니다.", "캡쳐", "warn"),
    ("타올로 닦습니다.", "타올", "warn"),
    ("머릿말과 인삿말을 고칩니다.", "머릿말", "err"),
    ("갯수를 셉니다.", "갯수", "err"),
    ("뒷풀이는 생략합니다.", "뒷풀이", "err"),
    # 문법 꼴
    ("자료는 내일 보낼께요.", "낼께", "err"),
    ("제가 할께.", "할께", "err"),
    ("그럴 줄 알았으면 갈껄.", "갈껄", "err"),
    ("다음 주에 할꺼야.", "할꺼", "err"),
    ("될런지 모르겠습니다.", "될런지", "err"),
    ("자료를 받았구요, 확인했습니다.", "았구요", "err"),
    ("합격율이 올랐습니다.", "합격율", "err"),          # 목록 항목(오류)
    ("이행율과 정답율을 셉니다.", "행율", "warn"),       # 문법 꼴(주의)
    ("발견률을 높입니다.", "견률", "warn"),
    ("받으시ㄹ 분은 신청합니다.", "시ㄹ", "err"),
    ("아ㄴ녕하세요.", "아ㄴ", "err"),
    ("ㅅㅛ핑몰에서 샀습니다.", "ㅅㅛ핑", "warn"),
    # 주의 — 같은 글자가 맞는 말로도 쓰임
    ("성능에서 뒤쳐지지 않습니다.", "뒤쳐지", "warn"),
    ("그분의 바램대로 됐습니다.", "바램", "warn"),
    ("일부로 그런 것은 아닙니다.", "일부로", "warn"),
    ("개발자 포탈에 올립니다.", "포탈", "warn"),
]

#: 같은 글자가 맞는 말로 쓰인 문장 — 지적이 하나도 없어야 한다
CLEAN = [
    "지역활성화 투자펀드를 늘립니다.",            # 「역활」이 낱말 안에 있음
    "오는 31일부로 종료합니다.",                    # 숫자 뒤 「일부로」
    "시스템의 일부로 포함합니다.",                  # 「일부로」 제외 꼴
    "검토 범위 중 일부로 넣습니다.",
    "제작년도는 2020년입니다.",                     # 「제작년」 제외 꼴
    "불길이 타올라 하늘을 덮었습니다.",             # 「타올」 제외 꼴
    "불길이 타올랐습니다.",
    "구지침을 새 지침으로 바꿉니다.",               # 「구지」는 낱말 범위
    "오는 15일께 발표합니다.",                      # 「께」 접미사(무렵)
    "7월께 결과가 나옵니다.",
    "연말께 다시 봅니다.",
    "다음달께 정합니다.",
    "선생님들께 감사드립니다.",                     # 높임 조사 「께」
    "전원을 꺼요.",                                 # 「끄다」
    "나갈 때 불꺼요.",                              # 「불 꺼」를 붙여 쓴 꼴
    "스위치를꺼 두었습니다.",
    "자료를 모읍니다.",                             # 「모으다」
    "그건 연구요.",                                 # 받침 없는 말 뒤 「구요」
    "쌀 한 되요.",                                  # 단위 「되」
    "덤벨런지 동작을 반복합니다.",
    "법률, 효율, 선율, 확률, 비율, 일률적, 출산율, 백분율, 환율, 능률을 봅니다.",
    "ㄱ자 모양 책상과 ㄷ자형 배치를 씁니다.",       # 모양 자모
    "김ㅇㅇ 대리와 ㅇㅇ회사가 왔습니다.",           # 자리 표시
    "좋네요ㅋㅋ 고마워요ㅠㅠ",                     # 일부러 쓴 자모
    "어미 -(으)ㄹ게 와 ㄴ다 를 설명합니다.",        # 문법 표기
    "살이 찌게 됩니다.",                            # 「찌게」는 목록에 안 넣음
    "대나무 댓가지를 엮습니다.",                    # 「댓가」 제외 꼴
    "돼지고기와 돼지는 다릅니다.",
    "보낼게요, 할게요, 갈걸 그랬어요.",
    "메시지, 콘텐츠, 디렉터리, 릴리스, 워크숍, 타깃을 씁니다.",
    "조세 포탈 혐의를 조사합니다.",                 # 「포탈」 제외 꼴
    "역할과 며칠, 금세, 웬만하면, 곰곰이를 바르게 씁니다.",
]


class SpellingListTests(unittest.TestCase):
    def test_list_is_loaded_from_the_data_file(self) -> None:
        self.assertTrue(LIST.is_file(), "맞춤법 목록 파일이 없습니다")
        self.assertGreater(len(CHK.SPELLING), 100, "검사기가 목록을 못 읽었습니다")
        head = LIST.read_text(encoding="utf-8")[:1500]
        for notice in ("제2017-12호", "제2017-13호", "제2017-14호"):
            self.assertIn(notice, head, "목록 머리에 출처 고시 번호가 빠졌습니다")

    def test_every_row_is_well_formed(self) -> None:
        for wrong, right, scope, level, excepts, why in CHK.SPELLING:
            with self.subTest(wrong):
                self.assertNotEqual(wrong, right)
                self.assertIn(scope, CHK.SPELL_SCOPES)
                self.assertIn(level, ("err", "warn"))
                for e in excepts:
                    self.assertIn(wrong, e, f"제외 꼴 「{e}」에 틀린 꼴이 없어 아무것도 안 뺍니다")

    def test_install_copies_the_list(self) -> None:
        targets = {src.name for src, _ in install.pairs()}
        self.assertIn(LIST.name, targets, "install.py 가 맞춤법 목록을 안 옮깁니다")


class SpellingHitTests(unittest.TestCase):
    def test_catches(self) -> None:
        for text, word, level in CATCH:
            with self.subTest(text):
                got = words(text)
                self.assertIn(word, got, f"「{word}」를 못 잡았습니다 — {got}")
                self.assertEqual(level, got[word], "등급이 다릅니다")

    def test_clean_sentences_stay_clean(self) -> None:
        for text in CLEAN:
            with self.subTest(text):
                self.assertEqual({}, words(text))

    def test_the_fix_is_shown(self) -> None:
        hit = next(h for h in CHK.spelling_hits("배포가 잘 됬다.") if h[1] == "됬")
        self.assertEqual("됐", hit[2])
        hit = next(h for h in CHK.spelling_hits("내일 보낼께요.") if h[1] == "낼께")
        self.assertEqual("낼게", hit[2])

    def test_two_errors_on_one_line_are_two_findings(self) -> None:
        self.assertEqual({"됬", "역활"}, set(words("잘 됬고 역활도 했습니다.")))


def run(name: str, body: str, env: dict | None = None) -> str:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / name
        p.write_text(body, encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), str(p), "--no-rules", "-v"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, **(env or {})}).stdout


MD = "---\nform: prose\n---\n\n# 시험\n\n**검사 대상** — 한 줄\n\n"
HTML = '<h1>시험</h1>\n<p class="lede">검사 대상 — 한 줄</p>\n'


class SpellingInTheCheckerTests(unittest.TestCase):
    def test_markdown_and_html_both_report_it(self) -> None:
        out = run("a.md", MD + "어제 배포가 잘 됬다고 합니다.\n")
        self.assertIn("[맞춤법]", out)
        self.assertIn("「됬」 → 「됐」", out)
        out = run("a.html", HTML + "<dl><div><dt>결과</dt><dd>배포가 잘 됬음</dd></div></dl>")
        self.assertIn("[맞춤법]", out)

    def test_each_wrong_word_on_a_line_is_reported(self) -> None:
        """한 줄에 같은 갈래를 한 건으로 접는 장치가 있다 — 맞춤법은 낱말마다 고치므로 접지 않는다."""
        out = run("a.md", MD + "잘 됬고 역활도 했습니다.\n")
        self.assertIn("「됬」", out)
        self.assertIn("「역활」", out)

    def test_warning_level_is_its_own_kind(self) -> None:
        out = run("a.md", MD + "이행율을 셉니다.\n")
        self.assertIn("[맞춤법 의심]", out)
        self.assertNotIn("[맞춤법]", out)

    def test_quotes_code_and_contrast_lines_are_spared(self) -> None:
        body = ("「됬다」는 틀린 말입니다.\n\n`메세지` 는 코드 이름입니다.\n\n"
                "- ❌ 「역활」 ✅ 「역할」\n")
        out = run("a.md", MD + body)
        self.assertNotIn("맞춤법", out)

    def test_missing_list_is_announced(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            out = run("a.md", MD + "잘 됬다고 합니다. 역활도 했습니다.\n",
                      env={"KOREAN_QA_SPELLING": str(Path(d) / "없음.tsv")})
        self.assertIn("맞춤법 목록 안 봄", out)
        self.assertNotIn("「역활」", out, "목록을 끈 시험인데 목록 항목이 잡혔습니다")


if __name__ == "__main__":
    unittest.main()
