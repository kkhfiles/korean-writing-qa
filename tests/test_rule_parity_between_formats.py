"""같은 내용을 마크다운과 HTML 에 넣었을 때 **갈래마다** 판정이 같은지 고정한다.

**왜 필요한가 — 같은 실패 모양에 네 번 걸렸다.**

| 언제 | 무엇이 한쪽에만 있었나 | 어떻게 드러났나 |
|---|---|---|
| 2026-09-02 | 제목 검사가 마크다운에만 | 값이 전부 개조식인 아티팩트가 **제목만 서술 문장**인 채 오류 0 |
| 2026-09-04 | 문단 검사가 길이만 봄 | 같은 내용에 마크다운 오류 2 · HTML **오류 0** |
| 2026-09-07 | 인라인 코드 제외가 마크다운에만 | 같은 내용이 형식에 따라 다르게 판정됨 |
| 2026-09-18 | 「해설을 인용 부호로 씀」이 마크다운에만 · 표 머리 라벨이 마크다운에만 | 이 시험을 만들며 찾음 |

**네 번 다 그 갈래 하나만 고쳤다.** 전 갈래를 대조하는 검사가 없어서, 다음 갈래가
한쪽에만 붙어도 아무도 모른다. 여기서 막는다.

**형식이 판정을 바꾸면 사람은 통과한 쪽만 보고 발행한다** — 미탐은 조용해서
더 위험하다.

## 이 시험이 지키는 것 둘

1. **짝이 있는 갈래는 두 형식에서 같이 잡힌다** — 아래 `PAIRS`
2. **모든 갈래가 짝이 있거나 까닭이 적혀 있다** — `ALL_KINDS` 와 대조한다.
   새 갈래가 들어오면 여기서 걸려서, **한쪽에만 붙였는지 그 자리에서 정해야 한다.**
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

CHECKER = repo_paths.CHECKER

MD_HEAD = ("---\nform: structured\n---\n\n# 검토 결과\n\n"
           "**하반기 검토 범위** — 한 장 조망\n\n")
HTML_HEAD = ('<h1>검토 결과</h1>\n'
             '<p class="lede">하반기 검토 범위 — 한 장 조망</p>\n')

#: 반복 블록은 묶음이 셋 있어야 판단한다 — 「머리 + 본문」 한 벌로는 안 된다.
#: ⛔ 「마크다운에 같은 개념이 없다」고 **거짓 사유**를 적어 뒀다(외부 검토가 짚음).
#:    마크다운에도 구현이 있고(검사기 §4), 라벨을 `**라벨**: 값` 꼴로 쓰면 걸린다.
#: 코드펜스 · `<pre><code>` 안에 든 공지문 세 줄 — 사람에게 나가는 글인데 검사에서 빠진다
FENCE_NOTICE = ("안녕하세요, 이번 달 세미나 안내를 드립니다.\n"
                "신청은 금요일까지 받고 있습니다.\n"
                "자리가 한정되어 있어 빨리 신청해 주시기 바랍니다.\n")

REPEAT_BLOCK_MD ="".join(f"- **고유{i}**: 값\n- **공통**: 값\n\n" for i in (1, 2, 3))
REPEAT_BLOCK_HTML = "".join(
    f"<article><dl><div><dt>고유{i}</dt><dd>값</dd></div>"
    f"<div><dt>공통</dt><dd>값</dd></div></dl></article>" for i in (1, 2, 3))

#: 갈래 → (마크다운 본문, 같은 내용의 HTML 본문). **글자는 같고 슬롯 모양만 다르다.**
PAIRS = {
    "서술형 종결": ("- **기한** — 9월 4일까지 끝낸다\n",
                 "<dl><div><dt>기한</dt><dd>9월 4일까지 끝낸다</dd></div></dl>"),
    "절단형 종결": ("- **산출물** — 해당 폴더에\n",
                 "<dl><div><dt>산출물</dt><dd>해당 폴더에</dd></div></dl>"),
    "절단형 의심": ("- **범위** — 초안까지만\n",
                 "<dl><div><dt>범위</dt><dd>초안까지만</dd></div></dl>"),
    "「~하는 자리」": ("- **위치** — 실패 모드가 그대로 걸리는 자리\n",
                   "<dl><div><dt>위치</dt><dd>실패 모드가 그대로 걸리는 자리</dd></div></dl>"),
    "「~하는 자리」 의심": ("- **위치** — 의견을 받는 자리\n",
                      "<dl><div><dt>위치</dt><dd>의견을 받는 자리</dd></div></dl>"),
    "지어낸 명사구": ("- **차수** — 1판·2판으로 나눔\n",
                  "<dl><div><dt>차수</dt><dd>1판·2판으로 나눔</dd></div></dl>"),
    "평가 수식어": ("- **구성** — 가벼운 검증 실행체\n",
                 "<dl><div><dt>구성</dt><dd>가벼운 검증 실행체</dd></div></dl>"),
    "모호한 지칭": ("- **주체** — 우리 제품이 아님\n",
                 "<dl><div><dt>주체</dt><dd>우리 제품이 아님</dd></div></dl>"),
    #: 2026-09-18 에 마크다운으로 넓힌 갈래 — 그전에는 HTML 에만 있었다
    "지시어 확인": ("- **위치** — 여기에 둠\n",
                "<dl><div><dt>위치</dt><dd>여기에 둠</dd></div></dl>"),
    "「회기」": ("- **단위** — 회기 셋\n",
              "<dl><div><dt>단위</dt><dd>회기 셋</dd></div></dl>"),
    "업무 글에 없는 말": ("- **장소** — 새는 곳\n",
                    "<dl><div><dt>장소</dt><dd>새는 곳</dd></div></dl>"),
    "다른 낱말로 읽힘": ("- **검증 대상** — 설정 파일 두 종이 모두 통과\n",
                   "<dl><div><dt>검증 대상</dt><dd>설정 파일 두 종이 모두 통과</dd></div></dl>"),
    "절 번호로 가리킴": ("- **근거** — 결제 대상 미정(§5)\n",
                   "<dl><div><dt>근거</dt><dd>결제 대상 미정(§5)</dd></div></dl>"),
    #: 2026-09-23 문서 전부로 넓힌 갈래 — 그전에는 두 형식 다 문단만 봤다
    "반말 서술형": ("- **근거** — 사례는 모두 실제 문서에서 가져왔다\n",
                "<dl><div><dt>근거</dt><dd>사례는 모두 실제 문서에서 가져왔다</dd></div></dl>"),
    "이중 피동": ("- **결과** — 값이 보여지는 화면\n",
                "<dl><div><dt>결과</dt><dd>값이 보여지는 화면</dd></div></dl>"),
    "번역투 이중 조사": ("- **대상** — 문서에의 접근\n",
                   "<dl><div><dt>대상</dt><dd>문서에의 접근</dd></div></dl>"),
    "번역투 그녀": ("- **담당** — 그녀가 맡음\n",
                 "<dl><div><dt>담당</dt><dd>그녀가 맡음</dd></div></dl>"),
    "제목 서술형": ("## 이것은 서술로 끝난다\n", "<h2>이것은 서술로 끝난다</h2>"),
    #: 2026-09-18 — 「다른 시험이 대조한다」고 **거짓 사유**를 적어 둬서 일곱 갈래가
    #: 어디서도 안 대조되고 있었다. 그 시험(`test_global_checker_form.py`)은
    #: `scan_md` 만 쓴다. 짝을 만들어 보니 HTML 에 진짜 미탐이 있었다.
    "제목 명사형 위반": ("## 무엇을 보나\n", "<h2>무엇을 보나</h2>"),
    "제목 형태 확인": ("## 검토는 초안까지만\n", "<h2>검토는 초안까지만</h2>"),
    #: 2026-09-18 에 메운 구멍 둘 — 마크다운에만 있었다
    "스캔 가치 없는 라벨": ("| 항목 | 비고 |\n|---|---|\n| 가 | 나 |\n",
                     "<table><tr><th>항목</th><th>비고</th></tr>"
                     "<tr><td>가</td><td>나</td></tr></table>"),
    "해설을 인용 부호로 씀": ("> 사람이 조작할 대상이 아니다. 릴리즈 시점에 확인한다.\n",
                      "<blockquote>사람이 조작할 대상이 아니다. "
                      "릴리즈 시점에 확인한다.</blockquote>"),
    "반복 블록 라벨 불일치": (REPEAT_BLOCK_MD, REPEAT_BLOCK_HTML),
    #: 2026-09-23 — 「형식에 따라 갈리는 갈래」에서 옮김. HTML 은 `<pre><code>` 를 먼저
    #: 지워서 안내가 안 나왔다.
    "펜스 안 배포 문구": ("```\n" + FENCE_NOTICE + "```\n",
                    "<pre><code>" + FENCE_NOTICE + "</code></pre>"),
}

#: 진입점 갈래는 머리 자체를 바꿔야 해서 `PAIRS` 의 「머리 + 본문」 꼴에 안 맞는다.
#: (갈래, 마크다운 진입점 줄, HTML 진입점 줄) — 머리를 통째로 갈아 끼운다.
LEDE_PAIRS = {
    "진입점 서술형": ("이 문서는 하반기 범위를 한 장으로 본다.",
                 "이 문서는 하반기 범위를 한 장으로 본다."),
    "진입점 명사형 위반": ("**하반기 검토 범위** — 산출물은 해당 폴더에",
                    "<b>하반기 검토 범위</b> — 산출물은 해당 폴더에"),
    "진입점 형태 확인": ("**하반기 검토 범위** — 초안까지만",
                   "<b>하반기 검토 범위</b> — 초안까지만"),
}

#: 짝을 안 만든 갈래와 그 까닭. **「나중에」는 까닭이 아니다** — 여기 적으면
#: 그 갈래는 이 시험 밖이므로, 왜 밖인지가 읽혀야 한다.
UNPAIRED = {
    "서술형 문단": ("`test_html_paragraph_parity.py` 가 같은 내용을 두 형식에 넣어 "
                "판정을 대조한다 — 그 시험의 본체가 바로 이 갈래다"),
    "결론 라벨 없는 설명": ("**마크다운 전용 강등 갈래** — `--relaxed` 는 마크다운 값 "
                    "슬롯에만 걸린다(전역 규칙에 명시). HTML 의 대응은 "
                    "「서술형 문단」이고 그쪽은 위에서 대조된다"),
    "제품 이름 음차": "저장소 밖 목록이 있어야 돌아 시험 기계에서 재현 불가",
    "진입점 없음": ("두 형식의 **진입점 정의가 다르다** — 마크다운은 제목 다음의 "
                "빈 줄 아닌 첫 줄, HTML 은 첫 `<p>`. 마크다운에서는 목록 항목도 "
                "진입점이 되므로 같은 내용으로 짝을 못 만든다. 형식마다 맞는 정의다."),
    "형식 미표기": "머리말이 없는 문서에만 나오는 안내 — 두 형식의 선언 방법 자체가 다름",
}

#: ⛔ **아직 안 메운 구멍.** 까닭이 아니라 **미룬 것**이라 따로 둔다.
#:    비워 두는 것이 목표다 — 여기 항목이 있으면 그 갈래는 형식에 따라 갈린다.
#:
#:    2026-09-18 에 비웠다. 「지시어 확인」이 마지막 항목이었고, 넓히면서 판정도
#:    같이 고쳤다(자리 명사 뺌 · 조사와 꾸밈꼴만 봄 · 나온 자리마다 냄).
#:    2026-09-23 에 다시 비웠다 — 「펜스 안 배포 문구」가 HTML `<pre><code>` 에서 안
#:    나오던 것(내용을 먼저 지웠다). 지우기 전에 같은 함수로 센다 — 위 `PAIRS` 로 옮김.
KNOWN_SPLIT: dict[str, str] = {}


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuleParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CHECKER.is_file():
            raise unittest.SkipTest(f"전역 검사기가 없습니다: {CHECKER}")
        cls.checker = load_checker()

    def kinds(self, suffix: str, text: str) -> set[str]:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / f"doc{suffix}"
            target.write_text(text, encoding="utf-8")
            scan = (self.checker.scan_md if suffix == ".md"
                    else self.checker.scan_html)
            errors, warnings, _ = scan(str(target), False, "structured")
        name = lambda item: item[1] if len(item) == 3 else item[0]  # noqa: E731
        return {name(i) for i in errors} | {name(i) for i in warnings}

    def test_every_paired_kind_fires_in_both_formats(self) -> None:
        """같은 내용이면 형식이 달라도 같은 갈래가 나와야 한다."""
        for kind, (md, html) in PAIRS.items():
            with self.subTest(kind=kind):
                in_md = kind in self.kinds(".md", MD_HEAD + md)
                in_html = kind in self.kinds(".html", HTML_HEAD + html)
                self.assertTrue(
                    in_md, f"「{kind}」 이 마크다운에서 안 잡힙니다 — "
                           "시료가 낡았으면 시료를, 규칙이 빠졌으면 규칙을 고칩니다")
                self.assertTrue(
                    in_html, f"「{kind}」 이 HTML 에서 안 잡힙니다 — "
                             "같은 내용인데 형식에 따라 갈립니다")

    def test_register_mixing_is_judged_the_same(self) -> None:
        """말투 섞임은 서술 문장 12개가 있어야 판단한다 — 그 크기로 대조한다.

        짧은 시료로 재면 두 형식 다 침묵해서 **갈려 있어도 통과한다.**
        문턱을 넘는 크기로 넣어야 이 갈래를 실제로 본 것이다.
        """
        polite = [f"{n}번 항목은 검사팀이 확인합니다." for n in range(1, 14)]
        sents = polite + ["기한은 9월 4일이다."]
        got_md = self.kinds(
            ".md", "---\nform: prose\n---\n\n# 검토 결과\n\n"
                   "**하반기 검토 범위** — 한 장 조망\n\n" + "\n\n".join(sents) + "\n")
        got_html = self.kinds(
            ".html", '<meta name="form" content="prose">\n<h1>검토 결과</h1>\n'
                     '<p class="lede">하반기 검토 범위 — 한 장 조망</p>\n'
                     + "\n".join(f"<p>{s}</p>" for s in sents))
        for label, got in (("마크다운", got_md), ("HTML", got_html)):
            with self.subTest(형식=label):
                self.assertIn("말투 섞임", got, f"{label} 이 안 잡습니다: {got}")

    def test_the_lede_is_judged_the_same_in_both_formats(self) -> None:
        """진입점 한 줄도 두 형식에서 같은 판정을 받아야 한다.

        **2026-09-18 에 여기서 미탐을 찾았다.** HTML 경로가 진입점의 서술형만
        보고 **절단형·의문형을 안 봤다** — 아티팩트의 진입점이 「무엇을 보나」
        여도 통과했다. 마크다운은 진작 보고 있었다.
        """
        body_md, body_html = "- **기한** — 9월 4일\n", \
            "<dl><div><dt>기한</dt><dd>9월 4일</dd></div></dl>"
        for kind, (md, html) in LEDE_PAIRS.items():
            with self.subTest(kind=kind):
                got_md = self.kinds(
                    ".md", f"---\nform: structured\n---\n\n# 검토 결과\n\n{md}\n\n{body_md}")
                got_html = self.kinds(
                    ".html",
                    f'<h1>검토 결과</h1>\n<p class="lede">{html}</p>\n{body_html}')
                self.assertIn(kind, got_md, f"마크다운이 안 잡습니다: {got_md}")
                self.assertIn(kind, got_html, f"HTML 이 안 잡습니다: {got_html}")

    def test_every_kind_is_accounted_for(self) -> None:
        """갈래 하나도 이 시험 밖으로 조용히 빠지지 않는다.

        **이 검사가 본체다.** 짝을 늘리는 것보다, 새 갈래가 들어올 때
        **한쪽에만 붙였는지 그 자리에서 정하게** 하는 것이 값이다.
        """
        known = (set(PAIRS) | set(LEDE_PAIRS) | set(UNPAIRED)
                 | set(KNOWN_SPLIT) | {"말투 섞임"})
        real = set(self.checker.ALL_KINDS)

        missing = sorted(real - known)
        self.assertFalse(
            missing,
            f"새 갈래 {missing} 가 형식 짝 시험 밖에 있습니다 — "
            "PAIRS 에 시료를 넣거나 UNPAIRED 에 까닭을 적으십시오")

        gone = sorted(known - real)
        self.assertFalse(
            gone, f"없어진 갈래가 목록에 남아 있습니다: {gone}")

    def test_the_known_split_list_stays_small(self) -> None:
        """안 메운 구멍은 **하나하나 이름으로** 적혀 있어야 한다.

        목록을 비우는 것이 목표다. 늘어나면 그만큼 형식에 따라 판정이 갈린다.
        """
        for kind, why in KNOWN_SPLIT.items():
            with self.subTest(kind=kind):
                self.assertIn(kind, set(self.checker.ALL_KINDS),
                              f"「{kind}」 은 이제 없는 갈래입니다 — 목록에서 뺍니다")
                self.assertIn("실측", why,
                              "안 메운 까닭에는 **몇 건이 걸리는지**가 있어야 "
                              "합니다 — 수 없이 미루면 영영 안 봅니다")


if __name__ == "__main__":
    unittest.main()
