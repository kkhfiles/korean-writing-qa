"""카드형 판정표 — md 표가 카드 HTML 로 나가고, 띄운 판정표에서 「제출」한 답이 md 표의 「답」 칸에 바르게 적히는지 본다.

(2026-10-29 사용자 — 「답을 복사해서 붙여넣는건 좀 구식인데 내가 표현한 그대로 직접 읽을 수 없니?」)
모델과 브라우저는 안 부른다 — 페이지가 보내는 요청을 HTTP 로 그대로 보낸다.

**지키는 것**
- `ask_sheet.py` 가 만든 표의 행이 모두 카드가 되고, 짚은 표현이 지적 표시로 나오나
- 제출한 답이 `ask_sheet.parse` 가 읽는 꼴로 「답」 칸에 들어가나 — 「직접:」 글은 글자 그대로, `|` 는 칸을 안 깨고
- 열쇠 주석과 다른 칸은 글자 그대로 남나 — 남지 않으면 `--answers-from` 이 줄 해시 대조를 못 한다
- 127.0.0.1 에만 열고, 열쇠(token) 없는 요청은 거절하나
- 자동 저장만으로는 표를 안 바꾸고, 제출해야 표에 적고 끝나나
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ask_sheet  # noqa: E402
import ask_sheet_html as sheet_html  # noqa: E402

LINES = ["# 소개", "", "업무 목록은 매일 갱신됩니다.", "", "일주일이 지나면 작업 내용의 기억이 흐려집니다.", "",
         "마감이 가까운 업무를 맨 위에 표시합니다 | 표 기호가 든 줄."]
ASKS = [(5, {"phrase": "기억이 흐려집니다", "fix": "정확히 기억하기 어렵습니다", "why": "문맥에 따라 정상일 수 있음",
             "opinion": "고침"}),
        (7, {"phrase": "맨 위에 표시합니다", "fix": "맨 위에 | 둡니다", "why": "칸 기호 시험"})]


def make_sheet(d: Path) -> Path:
    md = d / "asks.md"
    md.write_text(ask_sheet.render([(d / "d.md", LINES, ASKS)], lambda l: f"k{len(l)}"), encoding="utf-8")
    return md


class RenderTests(unittest.TestCase):
    def test_every_row_becomes_a_card(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            text = sheet_html.render(sheet_html.parse(make_sheet(Path(d)).read_text(encoding="utf-8")))
        self.assertEqual(2, text.count('<article class="card"'))
        self.assertIn('<mark class="hit">기억이 흐려집니다</mark>', text)
        self.assertIn("맨 위에 | 둡니다", text, "칸 기호를 막은 글자를 되돌리지 못했습니다")
        self.assertIn("원문을 고칠까요?", text)
        self.assertIn("세션이 의견을 적지 않음", text, "의견 칸이 빈 행을 빈칸으로 두었습니다")

    def test_hand_written_sheet_is_read(self) -> None:
        md = ("# 판정 요청\n\n**묻는 것**: 원문을 고칠까요?\n\n**답 고르는 법**\n- `고침`: 원문이 결함\n- `그대로`: 정상\n\n"
              "## 문서\n\n| # | 원문 | 고친 말 | 고친 이유 | 제 의견 | 답 |\n|---|---|---|---|---|---|\n"
              "| 14 | 검사가 **꺼짐** | 비활성화됨 | 입말 | 직접: 「검사가 꺼짐」(흔한 말) | |\n")
        sheet = sheet_html.parse(md)
        row = sheet["groups"][0]["rows"][0]
        self.assertEqual("14", row["id"])
        self.assertEqual({"kind": "직접", "text": "검사가 꺼짐", "note": "흔한 말"}, row["op"])
        self.assertEqual(["고침", "그대로"], [k for k, _ in sheet["legend"]])


class FillTests(unittest.TestCase):
    def test_answers_land_where_ask_sheet_reads_them(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            md = make_sheet(Path(d))
            before = md.read_text(encoding="utf-8")
            after = sheet_html.fill_answers(before, {"1": {"kind": "그대로", "text": ""},
                                                     "2": {"kind": "직접", "text": "맨 위에 | 둠"}})
        keys, answers = ask_sheet.parse(after)
        self.assertEqual({"Q1": "그대로", "Q2": "직접: 맨 위에 | 둠"}, answers)
        self.assertEqual(before.split("<!--")[1], after.split("<!--")[1], "열쇠 주석이 바뀌었습니다")
        self.assertEqual(ask_sheet.opinions(before), ask_sheet.opinions(after), "답 말고 다른 칸이 바뀌었습니다")

    def test_a_short_table_row_with_the_same_number_is_left_alone(self) -> None:
        md = "## 집계\n\n| # | 건수 |\n|---|---|\n| 1 | 18 |\n"
        self.assertEqual(md, sheet_html.fill_answers(md, {"1": {"kind": "고침"}}),
                         "판정 행이 아닌 표의 칸을 답으로 바꿨습니다")


class ServeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.md = make_sheet(Path(self.tmp.name))
        self.urls: list[str] = []
        got = threading.Event()
        self.rc: list[int] = []

        def run():
            self.rc.append(sheet_html.serve(self.md, 30, open_browser=False,
                                            ready=lambda u: (self.urls.append(u), got.set())))
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        self.assertTrue(got.wait(10), "판정표 서버가 뜨지 않았습니다")
        page = urllib.request.urlopen(self.urls[0], timeout=5).read().decode("utf-8")
        self.token = json.loads(page.split("window.JUDGE_SERVE=")[1].split(";</script>")[0])["token"]

    def post(self, body: dict, token: str | None = None) -> int:
        req = urllib.request.Request(self.urls[0] + "save", data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "X-Judge-Token": token or self.token})
        try:
            return urllib.request.urlopen(req, timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code

    def test_listens_only_on_this_pc(self) -> None:
        self.assertTrue(self.urls[0].startswith("http://127.0.0.1:"))
        self.post({"answers": {}, "final": True})

    def test_request_without_token_is_refused(self) -> None:
        self.assertEqual(403, self.post({"answers": {"1": {"kind": "그대로"}}, "final": True}, token="x"))
        self.assertEqual("", ask_sheet.parse(self.md.read_text(encoding="utf-8"))[1]["Q1"])
        self.post({"answers": {}, "final": True})

    def test_autosave_keeps_the_sheet_and_submit_fills_it(self) -> None:
        self.assertEqual(200, self.post({"answers": {"1": {"kind": "그대로", "text": ""}}, "final": False}))
        self.assertEqual("", ask_sheet.parse(self.md.read_text(encoding="utf-8"))[1]["Q1"],
                         "제출하기 전에 표의 답 칸을 바꿨습니다")
        self.assertTrue(self.md.with_suffix(".answers.json").is_file(), "고른 답을 저장하지 않았습니다")
        self.assertEqual(200, self.post({"answers": {"1": {"kind": "그대로", "text": ""},
                                                     "2": {"kind": "직접", "text": "맨 위에 둠"}},
                                         "text": "그대로 1\n2 직접: 맨 위에 둠", "final": True}))
        self.thread.join(10)
        self.assertEqual([0], self.rc, "제출한 뒤 끝나지 않았습니다")
        self.assertEqual({"Q1": "그대로", "Q2": "직접: 맨 위에 둠"}, ask_sheet.parse(self.md.read_text(encoding="utf-8"))[1])


if __name__ == "__main__":
    unittest.main()
