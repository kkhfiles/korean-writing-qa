"""줄 단위 전수 판정으로 층별 회수율을 낸다.

**예전 회수율은 무엇이었나.** 라벨이 전부 「누군가 읽다가 알아챈 것」이라
분모가 「사람이 찾아낸 것」이었다. 같은 종류의 읽기 통과가 만든 라벨을 같은
읽기가 얼마나 잡는지 재는 꼴이라 값이 부풀었다.

**지금은 무엇인가.** 판정 대상 줄을 전수로 판정했으므로 분모가
「그 줄들에 실제로 있는 문제」다. 다만 **그 세 문서 안에서만** 참이다.

**판정 읽는 법**
- ① 지적 확인 — 빈 칸은 동의(정탐) · `X`·「고치면 안」류는 오탐 · `?`는 보류
- ② 빠진 것 찾기 — 빈 칸은 깨끗함 · 적힌 것은 아무도 못 잡은 문제(미탐)

**보류는 분모에서 뺀다.** 참인지 아닌지 안 정해진 것을 참으로도 거짓으로도
세면 안 된다 — 어느 쪽으로 세든 그 수치는 판정이 아니라 가정이다.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHEET_DIR = REPO_ROOT / "runs" / "eval-004"
VERDICTS = REPO_ROOT / "data" / "annotations" / "eval-004-line-review.jsonl"

DOCUMENT = re.compile(r"^# 줄 단위 판정 — (doc-\d+)")
SECTION = re.compile(r"^## (①|②|③)")
CELL_SPLIT = re.compile(r"(?<!\\)\|")
FINDING_COLUMNS = 7
CLEAN_COLUMNS = 3

# 「누가」 칸의 값을 탐지기 층으로 묶는다. 사람 라벨은 탐지기가 아니다 —
# 예전 회수율을 부풀린 바로 그 출처라 층으로 세지 않는다.
DETECTORS = {"1층 규칙": "1층", "문서 검사기": "1층", "2층 읽기": "2층"}
NOT_A_DETECTOR = {"사람이 고치라 함", "사람이 괜찮다 함"}
# 이미 「문제 아님」으로 판정된 지적. ③ 표로 갈라 두었지만 옛 시트에는
# ① 안에 섞여 있어 「누가」 칸으로도 가른다.
ALLOWED = "사람이 괜찮다 함"


def parse_sheet(text: str):
    document, section, findings, clean = None, None, [], []
    for line in text.splitlines():
        head = DOCUMENT.match(line)
        if head:
            document = head.group(1)
            continue
        mark = SECTION.match(line)
        if mark:
            section = mark.group(1)
            continue
        if not line.startswith("| ") or document is None:
            continue
        cells = [c.strip() for c in CELL_SPLIT.split(line)][1:-1]
        if not cells or not cells[0].isdigit():
            continue
        if section == "①" and len(cells) == FINDING_COLUMNS:
            findings.append(cells)
        elif section == "②" and len(cells) == CLEAN_COLUMNS:
            clean.append(cells)
    return document, findings, clean


def load_verdicts(path: Path | None = None) -> dict:
    """자유롭게 적은 판정을 사람이 한 번 정리한 기록에서 읽는다.

    판정 칸의 글을 글자로 갈라 O/X를 정하지 않는다 — 「고치면 안됨」과
    「확인 필요」를 기계가 가르려 하면 조용히 틀린다.
    """
    path = path or VERDICTS
    if not path.is_file():
        return {}
    out = {}
    for row in path.read_text(encoding="utf-8").splitlines():
        if row.strip():
            r = json.loads(row)
            out[(r["document_id"], int(r["line_number"]), r["slot"], r.get("phrase", ""))] = r
    return out


def measure(sheet_dir: Path | None = None, verdict_file: Path | None = None) -> dict:
    verdicts = load_verdicts(verdict_file)
    true_problems, rejected, held, missed = [], [], [], []

    for path in sorted((sheet_dir or SHEET_DIR).glob("line-review-doc-*.md")):
        document, findings, clean = parse_sheet(path.read_text(encoding="utf-8"))
        for row in findings:
            number, phrase, note = int(row[0]), row[2].strip("「」"), row[6]
            # 이미 「문제 아님」으로 판정된 것은 참 문제가 아니다. 빈 칸이 여기서는
            # 「문제가 아닌 게 맞다」는 뜻이라, 함께 세면 분모가 한 건 부풀고
            # 어느 층도 못 잡은 것으로 잡힌다(실측으로 그렇게 틀렸다).
            if ALLOWED in row[5]:
                continue
            key = (document, number, "지적 확인", phrase)
            verdict = verdicts.get(key, {}).get("verdict", "동의" if not note else "미정리")
            sources = [s.strip() for s in row[5].split("·")]
            item = {"document_id": document, "line_number": number, "phrase": phrase,
                    "category": row[1], "sources": sources, "note": note}
            if verdict == "동의":
                true_problems.append(item)
            elif verdict == "오탐":
                rejected.append(item)
            else:
                held.append(item | {"verdict": verdict})

        for row in clean:
            number, note = int(row[0]), row[2]
            if not note:
                continue
            key = (document, number, "빠진 것 찾기", "")
            item = {"document_id": document, "line_number": number,
                    "note": note, "category": verdicts.get(key, {}).get("category", "")}
            missed.append(item)

    denominator = len(true_problems) + len(missed)
    by_layer = {"1층": 0, "2층": 0, "둘 중 하나": 0}
    for item in true_problems:
        layers = {DETECTORS[s] for s in item["sources"] if s in DETECTORS}
        for layer in layers:
            by_layer[layer] += 1
        if layers:
            by_layer["둘 중 하나"] += 1

    return {
        "판정 대상 문서": 3,
        "참 문제": denominator,
        "확인된 지적": len(true_problems),
        "아무도 못 잡은 것": len(missed),
        "오탐": len(rejected),
        "보류": len(held),
        "회수율": {k: round(v / denominator, 3) for k, v in by_layer.items()} if denominator else {},
        "층별 잡은 수": by_layer,
        "미탐 목록": missed,
        "오탐 목록": rejected,
        "보류 목록": held,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    result = measure()
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"참 문제 {result['참 문제']}건 "
          f"(확인된 지적 {result['확인된 지적']} + 아무도 못 잡은 것 {result['아무도 못 잡은 것']})")
    print(f"오탐 {result['오탐']} · 보류 {result['보류']}(분모에서 뺌)")
    print()
    for layer, rate in result["회수율"].items():
        print(f"  {layer:<8} {rate:.3f}  ({result['층별 잡은 수'][layer]}건)")
    print()
    for item in result["미탐 목록"]:
        print(f"  미탐 {item['document_id']}:{item['line_number']}  {item['note']}")
    for item in result["오탐 목록"]:
        print(f"  오탐 {item['document_id']}:{item['line_number']}  「{item['phrase']}」 {item['note']}")
    for item in result["보류 목록"]:
        print(f"  보류 {item['document_id']}:{item['line_number']}  「{item['phrase']}」 {item['note']}")


if __name__ == "__main__":
    main()
