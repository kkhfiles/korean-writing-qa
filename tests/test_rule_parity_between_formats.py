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
    "「회기」": ("- **단위** — 회기 셋\n",
              "<dl><div><dt>단위</dt><dd>회기 셋</dd></div></dl>"),
    "업무 글에 없는 말": ("- **장소** — 새는 곳\n",
                    "<dl><div><dt>장소</dt><dd>새는 곳</dd></div></dl>"),
    "이중 피동": ("- **결과** — 값이 보여지는 화면\n",
                "<dl><div><dt>결과</dt><dd>값이 보여지는 화면</dd></div></dl>"),
    "번역투 이중 조사": ("- **대상** — 문서에의 접근\n",
                   "<dl><div><dt>대상</dt><dd>문서에의 접근</dd></div></dl>"),
    "번역투 그녀": ("- **담당** — 그녀가 맡음\n",
                 "<dl><div><dt>담당</dt><dd>그녀가 맡음</dd></div></dl>"),
    "제목 서술형": ("## 이것은 서술로 끝난다\n", "<h2>이것은 서술로 끝난다</h2>"),
    #: 2026-09-18 에 메운 구멍 둘 — 마크다운에만 있었다
    "스캔 가치 없는 라벨": ("| 항목 | 비고 |\n|---|---|\n| 가 | 나 |\n",
                     "<table><tr><th>항목</th><th>비고</th></tr>"
                     "<tr><td>가</td><td>나</td></tr></table>"),
    "해설을 인용 부호로 씀": ("> 사람이 조작할 대상이 아니다. 릴리즈 시점에 확인한다.\n",
                      "<blockquote>사람이 조작할 대상이 아니다. "
                      "릴리즈 시점에 확인한다.</blockquote>"),
}

#: 짝을 안 만든 갈래와 그 까닭. **「나중에」는 까닭이 아니다** — 여기 적으면
#: 그 갈래는 이 시험 밖이므로, 왜 밖인지가 읽혀야 한다.
UNPAIRED = {
    "서술형 문단": "두 형식의 문단 판정은 `test_html_paragraph_parity.py` 가 이미 전담",
    "결론 라벨 없는 설명": "`--relaxed` 에서만 나오는 강등 갈래 — 짝 시험의 축이 다름",
    "반말 서술형": "기본으로 꺼진 갈래 — 켜는 경로는 `test_global_checker_scope.py`",
    "말투 섞임": "서술 문장 12개가 있어야 판단 · 짧은 시료로는 두 형식 다 침묵(실측 확인)",
    "제품 이름 음차": "저장소 밖 목록이 있어야 돌아 시험 기계에서 재현 불가",
    "제목 명사형 위반": "제목 세 갈래는 `test_global_checker_form.py` 가 두 경로를 이미 대조",
    "제목 형태 확인": "위와 같음",
    "진입점 없음": "진입점 네 갈래도 같은 시험이 두 경로를 대조",
    "진입점 서술형": "위와 같음",
    "진입점 명사형 위반": "위와 같음",
    "진입점 형태 확인": "위와 같음",
    "반복 블록 라벨 불일치": "HTML 의 `article`·`section` 반복 구조가 전제라 마크다운에 같은 개념이 없음",
    "형식 미표기": "머리말이 없는 문서에만 나오는 안내 — 두 형식의 선언 방법 자체가 다름",
    "펜스 안 배포 문구": "코드펜스 안을 보는 갈래 — HTML 에는 그 개념이 없음",
}

#: ⛔ **아직 안 메운 구멍.** 까닭이 아니라 **미룬 것**이라 따로 둔다.
#:    비워 두는 것이 목표다 — 여기 항목이 있으면 그 갈래는 형식에 따라 갈린다.
KNOWN_SPLIT = {
    "지시어 확인": (
        "HTML 에만 있음 — 마크다운에 켜면 실문서 818개에서 주의 269건이 새로 난다"
        "(문서 196개 · 「아래」가 238회로 대부분). 켤지는 사용자 판단 대기"
        " · 실측 2026-09-18"),
}


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

    def test_every_kind_is_accounted_for(self) -> None:
        """갈래 하나도 이 시험 밖으로 조용히 빠지지 않는다.

        **이 검사가 본체다.** 짝을 늘리는 것보다, 새 갈래가 들어올 때
        **한쪽에만 붙였는지 그 자리에서 정하게** 하는 것이 값이다.
        """
        known = set(PAIRS) | set(UNPAIRED) | set(KNOWN_SPLIT)
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
