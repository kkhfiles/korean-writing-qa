"""재판정 prefix 문맥이 앞서 보낸 묶음 글을 **글자까지 그대로** 첫 블록으로 다시 보내고, 바뀐 줄만 둘째 블록으로
붙이는지 본다 — 모델은 안 부른다.

(2026-10-20 실측) 프롬프트 캐시는 블록 경계에서 끝나는 앞부분만 다시 쓴다. 앞 묶음 + 꼬리 블록이면 앞 묶음을
읽기로 받아 한 호출 0.052 → 0.010달러였다. 캐시가 식었으면(5분) 처음부터 다시 쓰므로 그때는 쓰지 않는다.

**지키는 것**

- 전체 판정한 묶음이 앞 묶음으로 남고, 4분 안의 재판정은 [그 글 그대로, 바뀐 줄 · 대상 · 기준 판] 두 블록
- 앞 묶음이 식었으면 쓰지 않음 — 지금 방식(fixed)
- 사용자 답이 늘어도 앞 묶음을 만든 호출의 시스템 프롬프트 그대로 · 새 답은 꼬리에
- HTML 도 전체 판정 묶음을 다시 씀(앞 묶음은 전체 판정에서만 생김)
- 줄을 끼워 넣어 번호가 밀려도 대상 줄을 앞 묶음에 잇고, 바뀐 줄이 많으면 쓰지 않음
- 앞 묶음을 다시 보내면 쓴 시각이 새로 됨 · 오래된 앞 묶음 파일은 지워짐
"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import judge_layer2 as judge  # noqa: E402
import probe_layer2_kinds as probe  # noqa: E402
from test_rejudge_cap import _Base  # noqa: E402
from test_rejudge_context import Scripted  # noqa: E402

BASE = ["# 안내", "", "업무 목록은 매일 오전 아홉 시에 갱신됩니다.", "", "마감이 가까운 업무를 맨 위에 표시합니다.",
        "", "담당자는 목록에서 바로 바꿀 수 있습니다."]


class PrefixTests(_Base):

    def full(self, lines: list[str]) -> Scripted:
        self.write(lines)
        fake = Scripted([[]])
        judge.judge(self.doc, "opus", 10, fake.pair())
        return fake

    def rejudge_prefix(self, lines: list[str], targets: list[int], base=BASE) -> Scripted:
        self.write(lines)
        fake = Scripted([[]] * 3)
        judge.judge(self.doc, "opus", 10, fake.pair(), targets, base, context="prefix")
        return fake

    def test_a_fresh_chunk_rides_as_the_first_block(self) -> None:
        round0 = self.full(BASE)
        edited = BASE[:4] + ["마감이 가까운 업무를 맨 위에 둡니다."] + BASE[5:]
        fake = self.rejudge_prefix(edited, [5])
        user = fake.calls[0]["user"]
        self.assertIsInstance(user, list, "블록으로 나누지 않으면 캐시를 못 읽습니다")
        self.assertEqual(round0.calls[0]["user"], user[0], "앞 묶음이 0회차 글과 한 글자라도 다르면 캐시를 못 읽습니다")
        self.assertIn("위 판 5–5행을 고침", user[1])
        self.assertIn("    5 | 마감이 가까운 업무를 맨 위에 둡니다.", user[1])
        self.assertIn("이번에는 아래 줄만 점검한다", user[1])
        self.assertIn("5행 기준 판: 마감이 가까운 업무를 맨 위에 표시합니다.", user[1])
        self.assertEqual("prefix", self.last_row()["context"])
        self.assertIn(judge.coverage.line_key(edited[4]), self.last_row()["seen"], "고친 줄을 본 줄로 안 적었습니다")

    def test_a_stale_chunk_falls_back_to_fixed(self) -> None:
        self.full(BASE)
        edited = BASE[:4] + ["마감이 가까운 업무를 맨 위에 둡니다."] + BASE[5:]
        with mock.patch.object(judge, "PREFIX_FRESH", -1):
            fake = self.rejudge_prefix(edited, [5])
        self.assertIsInstance(fake.calls[0]["user"], str)
        self.assertEqual("fixed", self.last_row()["context"])

    def test_a_new_answer_keeps_the_old_system_and_rides_in_the_tail(self) -> None:
        """(2026-10-20 세션 흉내) 0회차 직후 답 하나로 시스템이 바뀌어 재판정 전부가 앞 묶음을 못 썼다."""
        round0 = self.full(BASE)
        judge.coverage.DECISIONS.write_text(json.dumps(
            {"when": time.time() + 1, "category": "업무에서 쓰는 말로 쓰기", "phrase": "갱신됩니다", "fix": "바뀝니다",
             "answer": "그대로"}, ensure_ascii=False) + "\n", encoding="utf-8")
        edited = BASE[:4] + ["마감이 가까운 업무를 맨 위에 둡니다."] + BASE[5:]
        fake = self.rejudge_prefix(edited, [5])
        self.assertIsInstance(fake.calls[0]["user"], list, "답이 늘었다고 앞 묶음을 버렸습니다")
        self.assertEqual(round0.calls[0]["system"], fake.calls[0]["system"], "앞 묶음과 다른 시스템이면 캐시를 못 읽습니다")
        self.assertNotIn("갱신됩니다", fake.calls[0]["system"])
        self.assertIn("새로 답한 것", fake.calls[0]["user"][1])
        self.assertIn("「갱신됩니다」 · 판정기 제안 「바뀝니다」 · 사용자: 그대로", fake.calls[0]["user"][1])

    def test_an_inserted_line_still_maps_to_the_chunk(self) -> None:
        round0 = self.full(BASE)
        edited = BASE[:3] + ["", "목록은 메일로도 보냅니다."] + BASE[3:]
        fake = self.rejudge_prefix(edited, [5, 9])
        user = fake.calls[0]["user"]
        self.assertEqual(round0.calls[0]["user"], user[0])
        self.assertIn("행 뒤에 줄을 넣음", user[1])      # 빈 줄 앞뒤 어느 쪽에 넣었다고 볼지는 diff 가 정한다
        self.assertIn("  5 | 목록은 메일로도 보냅니다.", user[1])
        self.assertEqual(1, len(fake.calls), "한 앞 묶음 안의 대상인데 나눠 불렀습니다")

    def test_a_tail_longer_than_the_window_uses_fixed(self) -> None:
        """고친 줄이 쌓인 뒤 대상이 한 줄이면 꼬리(바뀐 줄 31 + 읽기 몫 10)가 fixed 창(41줄)보다 길다."""
        long = ["# 긴 문서", ""] + [f"채움 문단 {i}번입니다." for i in range(98)]
        self.full(long)
        edited = list(long)
        for i in range(60, 90):
            edited[i] = edited[i] + " 고침"
        edited[20] = "채움 문단 열여덟번입니다."
        fake = self.rejudge_prefix(edited, [21], base=long)
        self.assertIsInstance(fake.calls[0]["user"], str, "꼬리가 창보다 긴데 앞 묶음을 썼습니다")
        self.assertEqual("fixed", self.last_row()["context"])
        fake = self.rejudge_prefix(edited, list(range(61, 91)) + [21], base=long)
        self.assertIsInstance(fake.calls[0]["user"], list, "대상이 많아 창이 길면 앞 묶음이 싸다")

    def test_reuse_refreshes_the_time(self) -> None:
        self.full(BASE)
        key = judge.coverage.doc_key(self.doc)
        data = judge.load_anchors(key)
        data["anchors"][0]["used"] -= 200
        judge._write_anchors(key, data)
        edited = BASE[:4] + ["마감이 가까운 업무를 맨 위에 둡니다."] + BASE[5:]
        self.rejudge_prefix(edited, [5])
        self.assertGreater(judge.load_anchors(key)["anchors"][0]["used"], time.time() - 60)

    def test_html_reuses_the_full_judgment_and_falls_back_to_chunk(self) -> None:
        """창을 못 잡는 HTML 이 가장 큰 몫이다(재판정 비용의 62%). 앞 묶음은 전체 판정에서만 생긴다 — [A, 꼬리] 호출은
        캐시 항목을 꼬리 끝에만 남겨 다음 호출이 A 를 못 읽는다(2026-10-20 실측)."""
        self.doc = self.dir / "d.html"
        html = ["<html><body>", "<h1>안내</h1>", "<p>업무 목록은 매일 갱신됩니다.</p>",
                "<p>마감이 가까운 업무를 맨 위에 표시합니다.</p>", "</body></html>"]
        self.doc.write_text("\n".join(html) + "\n", encoding="utf-8")
        text = judge.read_doc(self.doc).splitlines()
        n = next(i for i, l in enumerate(text, 1) if "표시합니다" in l)
        round0 = Scripted([[]])
        judge.judge(self.doc, "opus", 10, round0.pair())
        html[3] = "<p>마감이 가까운 업무를 맨 위에 둡니다.</p>"
        self.doc.write_text("\n".join(html) + "\n", encoding="utf-8")
        second = Scripted([[]])
        judge.judge(self.doc, "opus", 10, second.pair(), [n], text, context="prefix")
        self.assertEqual(round0.calls[0]["user"], second.calls[0]["user"][0], "전체 판정 묶음을 다시 쓰지 않았습니다")
        self.assertEqual("prefix", self.last_row()["context"])
        with mock.patch.object(judge, "PREFIX_FRESH", -1):
            stale = Scripted([[]])
            judge.judge(self.doc, "opus", 10, stale.pair(), [n], text, context="prefix")
        self.assertIsInstance(stale.calls[0]["user"], str, "식은 앞 묶음 대신 지금 방식(fixed)이어야 합니다")
        self.assertEqual("fixed", self.last_row()["context"])

    def test_old_anchor_files_are_removed(self) -> None:
        self.full(BASE)
        stale = judge.prefix_dir() / "0000000000000000.json"
        stale.write_text("{}", encoding="utf-8")
        old = time.time() - judge.PREFIX_KEEP - 10
        os.utime(stale, (old, old))
        self.full(BASE + ["", "한 줄 더 있습니다."])
        self.assertFalse(stale.exists(), "식은 앞 묶음 파일이 남았습니다 — 사내 원문이 오래 남습니다")

    def test_the_other_modes_send_one_string(self) -> None:
        self.full(BASE)
        edited = BASE[:4] + ["마감이 가까운 업무를 맨 위에 둡니다."] + BASE[5:]
        for mode in ("chunk", "fixed", "block"):
            self.write(edited)
            fake = Scripted([[]] * 3)
            judge.judge(self.doc, "opus", 10, fake.pair(), [5], BASE, context=mode)
            self.assertIsInstance(fake.calls[0]["user"], str, f"{mode} 의 입력이 바뀌었습니다")


if __name__ == "__main__":
    unittest.main()
