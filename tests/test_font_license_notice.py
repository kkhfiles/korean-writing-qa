"""심긴 서체의 라이선스 고지가 살아 있는지 지킨다.

**무엇이 있었나.** 2026-09-07까지 사례집에 심긴 서브셋은 SIL OFL 1.1을 두 곳에서
어기고 있었다.

| 조항 | 요구 | 그때 상태 |
|---|---|---|
| 2 | 배포본에 저작권 표시와 라이선스 동반 | 서체 이름과 라이선스 약칭만 · 저작권자 없음 |
| 3 | Modified Version은 예약 이름 사용 불가 | CSS·폰트 내부 이름이 `Pretendard` |

**왜 시험으로 옮겼나.** 서브셋을 만드는 명령이 `--name-IDs=1,2,3,4,6`이라 저작권(0)과
라이선스(13·14)를 **구조적으로 버린다.** 되만들 때 사람이 한 단계를 더 기억해야 하고,
기억해야 하는 구조는 실패한다 — 실제로 실패해서 이 상태로 배포됐다.

**근거** — SIL 공식 FAQ 2.6은 서브셋을 modification으로 보고, 예외인 Functional
Equivalence(FAQ 2.8)는 같은 문자 인벤토리와 메타데이터 보존을 요구한다. 2,350자
서브셋은 둘 다 못 맞춘다. FAQ 1.11은 임베드를 「꺼내 쓰기 어렵게 넣은 것」으로
정의하는데, base64 data URI는 거기 해당하지 않아 배포로 본다.
"""

from __future__ import annotations

import base64
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

SHOWCASE = repo_paths.REPO / "docs" / "showcase.html"
OFL = repo_paths.REPO / "licenses" / "OFL-1.1.txt"
NOTICE = repo_paths.REPO / "NOTICE"

#: Pretendard는 세 폰트의 파생물이라 저작권 줄이 넷이다.
HOLDERS = ["Kil Hyung-jin", "Adobe", "The Inter Project Authors", "The M+ FONTS Project Authors"]
RESERVED = ["Pretendard", "Source", "Inter", "M PLUS 1"]

FACE = re.compile(r"@font-face\s*\{(.*?)\}", re.S)
FAMILY = re.compile(r"font-family\s*:\s*\"([^\"]+)\"")
DATA_URI = re.compile(r"url\(data:font/woff2;base64,([A-Za-z0-9+/=]+)\)")


class EmbeddedFontNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SHOWCASE.is_file():
            raise unittest.SkipTest(f"사례집이 없습니다: {SHOWCASE}")
        cls.html = SHOWCASE.read_text(encoding="utf-8")
        cls.faces = FACE.findall(cls.html)

    def test_a_font_is_actually_embedded(self) -> None:
        """안 심겨 있으면 아래 시험들이 아무것도 안 재고 통과한다."""
        self.assertTrue(self.faces, "@font-face 블록이 없습니다")
        self.assertTrue(DATA_URI.search(self.html), "data URI 로 심긴 폰트가 없습니다")

    def test_all_four_copyright_holders_are_named(self) -> None:
        """조항 2 — 저작권 표시가 배포본과 함께 가야 한다."""
        for holder in HOLDERS:
            with self.subTest(holder=holder):
                self.assertIn(holder, self.html, f"저작권자 표시가 없습니다: {holder}")

    def test_the_license_is_named_and_locatable(self) -> None:
        self.assertIn("SIL Open Font License", self.html)
        self.assertIn("openfontlicense.org", self.html)

    def test_the_license_text_ships_with_the_repo(self) -> None:
        """이름만 대고 전문이 없으면 받는 사람이 조건을 확인할 길이 없다."""
        self.assertTrue(OFL.is_file(), f"라이선스 전문이 없습니다: {OFL}")
        self.assertIn("SIL OPEN FONT LICENSE", OFL.read_text(encoding="utf-8").upper())

    def test_notice_file_explains_the_exception(self) -> None:
        """저장소는 MIT 인데 심긴 서체만 OFL 이다 — 안 적으면 MIT 로 읽힌다."""
        self.assertTrue(NOTICE.is_file(), "NOTICE 가 없습니다")
        body = NOTICE.read_text(encoding="utf-8")
        self.assertIn("SIL Open Font License", body)
        self.assertIn("MIT", body)

    def test_the_embedded_family_is_not_a_reserved_name(self) -> None:
        """조항 3 — 서브셋은 Modified Version 이라 예약 이름을 주 이름으로 못 쓴다."""
        for body in self.faces:
            match = FAMILY.search(body)
            if not match:
                continue
            family = match.group(1)
            with self.subTest(family=family):
                for name in RESERVED:
                    self.assertNotIn(name.lower(), family.lower(),
                                     f"예약 이름을 서체 이름으로 썼습니다: {family}")

    def test_the_font_binary_carries_its_own_notice(self) -> None:
        """CSS 주석만 있으면 폰트 파일만 꺼내 간 사람에게는 아무 표시가 없다."""
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            self.skipTest("fontTools 가 없습니다 — 폰트 안쪽 검사는 건너뜁니다")

        import io
        match = DATA_URI.search(self.html)
        font = TTFont(io.BytesIO(base64.b64decode(match.group(1))))
        names = font["name"]

        copyright_ = names.getDebugName(0) or ""
        for holder in HOLDERS:
            with self.subTest(field="저작권", holder=holder):
                self.assertIn(holder, copyright_, "폰트 안 저작권 항목이 비어 있습니다")
        self.assertIn("Open Font License", names.getDebugName(13) or "")

        for nid in (1, 4, 6, 16):
            got = names.getDebugName(nid)
            if not got:
                continue
            with self.subTest(field=f"name {nid}", value=got):
                for reserved in RESERVED:
                    self.assertNotIn(reserved.lower(), got.lower(),
                                     f"폰트 안 이름에 예약 이름이 남아 있습니다: {got}")


if __name__ == "__main__":
    unittest.main()
