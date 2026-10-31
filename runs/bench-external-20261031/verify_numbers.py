"""README 와 보고서 HTML 의 표 숫자를 result.json · ledger.json 과 대조한다 — 손으로 옮긴 값이 어긋났는지 기계로 본다.

    python -X utf8 runs/bench-external-20261031/verify_numbers.py [보고서.html]
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
R = json.loads((HERE / "result.json").read_text(encoding="utf-8"))
LEDGER = json.loads((HERE / "ledger.json").read_text(encoding="utf-8"))
NAME = {"2층 판정기": "l2", "Claude 단순 요청": "plain-claude", "GPT 단순 요청": "plain-gpt",
        "Argon 단순 요청": "plain-argon", "im-not-ai 규칙": "imnotai-claude", "Kiwi 띄어쓰기": "kiwi-space",
        "KoBART 교정": "kobart-gec", "1층 검사기": "l1"}
bad: list[str] = []


def same(label: str, shown: str, want: float, digits: int) -> None:
    if shown in ("—", ""):
        return
    got = float(shown.replace(",", ""))
    if abs(got - want) > 10 ** -digits / 2 + 1e-9:     # 반올림 방식(0.975 → 0.98)과 상관없이 원래 값과의 거리로
        bad.append(f"{label}: 표 {shown} · 원본 {want:.4f}")


def md_rows(text: str, head: str) -> list[list[str]]:
    sec = text.split(head, 1)[1]
    rows = []
    for line in sec.splitlines()[1:]:
        if line.startswith("|") and not line.startswith("|---"):
            rows.append([c.strip().strip("`") for c in line.strip("|").split("|")])
        elif rows and not line.startswith("|"):
            break
    return rows[1:]


def check_readme() -> None:
    t = (HERE / "README.md").read_text(encoding="utf-8")
    for row in md_rows(t, "### D1 K-NCT"):
        v = R["D1 K-NCT"][row[0]]
        same(f"D1 {row[0]} 회수", row[1], v["회수율"][0], 2)
        same(f"D1 {row[0]} 교정", row[2], v["교정 정확도"][0], 2)
        same(f"D1 {row[0]} 정답 지적", row[3], v["정답 문장 지적/1천 자"][0], 1)
        if row[0] != "l1":
            same(f"D1 {row[0]} 초", row[4], v["비용"]["초/1천 자"], 1)
        if re.fullmatch(r"[\d.]+", row[5]) and row[5] != "0":
            same(f"D1 {row[0]} 달러", row[5], v["비용"]["환산 달러/1천 자(Claude만)"], 3)
    fams = ["F1", "F2", "F3", "F4", "F5", "F1~F4"]
    for row in md_rows(t, "### D2 공개 글 결함 삽입"):
        v = R["D2 결함 심기"][row[0]]
        for k, fam in enumerate(fams, 1):
            same(f"D2 {row[0]} {fam}", row[k], v["회수율"][fam][0], 2)
        same(f"D2 {row[0]} 보정", row[7], v["보정 회수율"]["F1~F4"][0], 2)
        same(f"D2 {row[0]} 원문 지적", row[8], v["원문 지적/1천 자"][0], 1)
        same(f"D2 {row[0]} 초", row[9], v["비용"]["초/1천 자"], 1 if v["비용"]["초/1천 자"] >= 0.1 else 2)
        if re.fullmatch(r"[\d.]+", row[10]) and row[10] != "0":
            same(f"D2 {row[0]} 달러", row[10], v["비용"]["환산 달러/1천 자(Claude만)"], 3)
    for row in md_rows(t, "### D2 정밀도"):
        v = R["D2 정밀도"][row[0]]
        same(f"정밀도 {row[0]} 모두", row[1].split()[0], v["두 판정자 모두 맞음"][0], 2)
        same(f"정밀도 {row[0]} 이상", row[2].split()[0], v["한 판정자 이상 맞음"][0], 2)
    lg = {r["arm"]: [] for r in LEDGER}
    for r in LEDGER:
        lg[r["arm"]].append(r)
    for row in md_rows(t, "### D4 사용자가 지적한 표현"):
        key = {"전체(삽입한 표현 152건)": "tight", "사용자 지적 대장 127건": "ledger_tight", "같은 갈래 예비 예문 25건": "heldout_tight",
               "판정 규칙 예문에 그대로 없는 56건": ("uncited", "tight")}.get(row[0])
        if not key:
            continue
        for col, arm in ((1, "l2"), (2, "plain-claude")):
            want = [r[key[0]][key[1]] if isinstance(key, tuple) else r[key] for r in lg[arm]]
            if [int(x) for x in row[col].split(", ")] != want:
                bad.append(f"D4 {row[0]} {arm}: 표 {row[col]} · 원본 {want}")


def check_html(path: Path) -> None:
    t = html.unescape(path.read_text(encoding="utf-8"))
    for tbl in re.findall(r"<table>.*?</table>", t, re.S):
        heads = [re.sub("<[^>]+>", "", h) for h in re.findall(r"<th[^>]*>(.*?)</th>", tbl)]
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S):
            cells = [re.sub("<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if not cells or cells[0] not in NAME:
                continue
            n = NAME[cells[0]]
            if heads[:3] == ["시스템", "맞춤법", "공공언어"]:
                v = R["D2 결함 심기"][n]
                for k, fam in enumerate(["F1", "F2", "F3", "F4", "F5", "F1~F4"], 1):
                    same(f"HTML D2 {n} {fam}", cells[k], v["회수율"][fam][0], 2)
                same(f"HTML D2 {n} 원문", cells[7], v["원문 지적/1천 자"][0], 1)
            elif heads[:2] == ["시스템", "회수율"]:
                v = R["D1 K-NCT"][n]
                same(f"HTML D1 {n} 회수", cells[1], v["회수율"][0], 2)
                same(f"HTML D1 {n} 교정", cells[2], v["교정 정확도"][0], 2)
                same(f"HTML D1 {n} 정답", cells[3], v["정답 문장 지적/1천 자"][0], 1)
            elif heads[:2] == ["시스템", "두 판정자 모두 맞음"]:
                v = R["D2 정밀도"][n]
                same(f"HTML 정밀도 {n} 모두", cells[1], v["두 판정자 모두 맞음"][0], 2)
                same(f"HTML 정밀도 {n} 이상", cells[2], v["한 판정자 이상 맞음"][0], 2)


if __name__ == "__main__":
    check_readme()
    if len(sys.argv) > 1:
        check_html(Path(sys.argv[1]))
    print("\n".join(bad) if bad else "어긋난 값 없음")
    raise SystemExit(1 if bad else 0)
