"""규칙 후보 판정표 — 「이 규칙을 넣을까요?」를 같은 양식으로 묻고, 받은 답을 종류별로 묶어 돌려준다.

    python -X utf8 scripts/rule_sheet.py template [--title <주제>] > <저장소 밖>/rules.md
    python -X utf8 scripts/ask_sheet_html.py <저장소 밖>/rules.md --serve      # 카드로 띄워 「제출」을 기다림
    python -X utf8 scripts/rule_sheet.py read <저장소 밖>/rules.md [--reply '의견대로, 단 2 개인 규칙'] [--json]

**왜 있나** (2026-10-29 사용자 — 「규칙을 추가할 때 포맷팅된 시안으로 사용자에게 정보를 받아서 반영」,
판정표 모양은 「규칙 전용 칸을 더함」을 고름) — 그전에는 규칙 후보를 `promote_feedback.py` 의 JSON
미리보기나 대화로 풀어 물었다. 사람 확인 표와 같은 카드형 판정표로 묻고 「제출」로 받는다.

**칸** — #, 규칙, 잡을 문장, 잡으면 안 될 문장, 실문서 오탐, 등급, 제 의견, 답(`ask_sheet_html.RULE_COLUMNS`).
**답** — 공통 규칙(검사기나 판정 기준에 넣음), 개인 규칙(이 PC 개인 파일에만 넣음), 넣지 않음, 보류.

**이 스크립트는 규칙을 넣지 않는다** — 답을 묶어 돌려줄 뿐이다. 넣는 일은 세션이 `fix-korean-finding`
스킬 절차(실측, 회귀 시험 데이터, 돌연변이)로 하고, 개인 규칙은 동사 짝이면 `local-personal-words.tsv`,
문맥 기준이면 `local-layer2-rules.md` 에 적는다.

종료 코드 — 0 모두 답함(보류 없음) · 1 보류나 빈칸이 남음 · 2 규칙 후보 표가 아니거나 답을 못 읽음
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ask_sheet  # noqa: E402
import ask_sheet_html as sheet_html  # noqa: E402

TEMPLATE = """# 규칙 후보 — {title}

**묻는 것**: 이 규칙을 넣을까요?

**답 고르는 법**
- `공통 규칙`: 이 검사기를 받아 쓰는 모든 사람에게 적용
- `개인 규칙`: 이 PC 의 개인 파일에만 넣음(동사 짝은 낱말 목록, 문맥 기준은 개인 판정 기준)
- `넣지 않음`: 규칙으로 막지 않음
- `보류`: 아직 못 정함

**짧게 답해도 됨**: 「전부 의견대로」, 「의견대로, 단 2 개인 규칙」

## {title}

| {head} |
|{sep}
| 1 | 「명사 + 잡다」 → 검출 | 시험 도구가 **결함을 잡습니다** | 균형을 잡습니다 | 실문서 600편 중 0편 | 주의 | 공통 규칙 |  |
"""


def template(title: str) -> str:
    cols = sheet_html.RULE_COLUMNS
    return TEMPLATE.format(title=title, head=" | ".join(cols), sep="---|" * len(cols))


def rows_of(md: str) -> tuple[dict, dict[str, list[str]]]:
    """(표 전체, 번호별 칸) — 규칙 후보 표가 아니면 ValueError."""
    sheet = sheet_html.parse(md)
    if sheet["kind"] != "rule" or not sheet["groups"]:
        raise ValueError("규칙 후보 표가 아닙니다 — 머리가 "
                         f"{', '.join(sheet_html.RULE_COLUMNS)} 인 표를 줍니다(`rule_sheet.py template`)")
    raw = {}
    for line in md.split("<!--")[0].splitlines():
        m = sheet_html.ROW.match(line)
        c = sheet_html.cells(line) if m else []
        if len(c) >= len(sheet_html.RULE_COLUMNS):
            raw[m.group(1)] = [sheet_html.unescape(x) for x in c]
    return sheet, raw


def read(md: str, replies: list[str] | None = None) -> dict:
    """답을 종류별로 묶는다 — 답 칸이 먼저이고, 대화로 받은 답(`replies`)이 그 위를 덮는다."""
    sheet, raw = rows_of(md)
    rules = {r["id"]: r for g in sheet["groups"] for r in g["rows"]}
    answers = {rid: cells[-1] for rid, cells in raw.items() if rid in rules}
    if replies:
        opinions = {f"Q{rid}": cells[-2] for rid, cells in raw.items() if rid in rules}
        said = ask_sheet.parse_replies(replies, opinions, kinds=sheet_html.RULE_KINDS)
        answers.update({q[1:]: a for q, a in said.items()})
    unknown = sorted(set(answers) - set(rules), key=int)
    if unknown:
        raise ValueError(f"표에 없는 번호 — {', '.join(unknown)}")
    out: dict[str, list[dict]] = {k: [] for k in [*sheet_html.RULE_KINDS, "안 고름", "알 수 없는 답"]}
    for rid, rule in sorted(rules.items(), key=lambda kv: int(kv[0])):
        a = answers.get(rid, "").strip()
        kind = next((k for k in sorted(sheet_html.RULE_KINDS, key=len, reverse=True) if a.startswith(k)), None)
        if not a:
            kind = "안 고름"
        elif kind is None:
            kind = "알 수 없는 답"
        out[kind].append({"id": rid, "rule": rule["rule"], "answer": a})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="규칙 후보 판정표 — 양식을 내거나 답을 읽음")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("template", help="빈 규칙 후보 표(md)를 표준 출력으로")
    t.add_argument("--title", default="이번 회차")
    r = sub.add_parser("read", help="답을 종류별로 묶어 냄")
    r.add_argument("sheet")
    r.add_argument("--reply", action="append", help="대화로 받은 답 — 사용자 원문 그대로")
    r.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "template":
        sys.stdout.write(template(a.title))
        return 0
    try:
        out = read(Path(a.sheet).read_text(encoding="utf-8"), a.reply)
    except (OSError, ValueError) as e:
        print(f"⛔ {e}")
        return 2
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        for kind, items in out.items():
            if items:
                print(f"── {kind} {len(items)}건")
                for it in items:
                    print(f"   {it['id']}. {it['rule']}" + (f" — {it['answer']}" if it['answer'] and it['answer'] != kind else ""))
    open_left = out["보류"] or out["안 고름"] or out["알 수 없는 답"]
    return 1 if open_left else 0


if __name__ == "__main__":
    sys.exit(main())
