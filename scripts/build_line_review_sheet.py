"""줄 단위 전수 판정 시트를 만든다.

**왜 필요한가.** 지금 회수율의 분모는 「누가 알아챈 것」이다. 라벨 13건이 전부
읽기 통과에서 나왔으므로, 아무도 못 본 문제는 미탐으로 세어지지 않는다. 분모를
참으로 만들려면 **모든 줄이 판정돼야** 한다 — 지적이 없는 줄도 「깨끗함」으로
판정된 것이라야 한다.

**사람의 품을 줄이는 방법.** 이미 나온 지적을 줄마다 붙여 둔다. 사람은 붙어
있는 것을 확인하고, **붙지 않은 줄에 문제가 있는지만** 본다.

**판정 대상에서 빼는 줄** — 머리말·빈 줄·표 구분선·주소만 있는 줄·한글이 거의
없는 줄. 한글 작성 규칙이 걸릴 수 없는 줄이다.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts import skill_bridge                                    # noqa: E402

SOURCE_DIR = REPO_ROOT / "data" / "raw" / "diagnostic-002"
GLOBAL_CHECKER = Path.home() / ".claude" / "assets" / "doc-style-check.py"
LABELS = REPO_ROOT / "data" / "annotations" / "diagnostic-002-review.jsonl"
LAYER2 = REPO_ROOT / "runs" / "eval-003" / "llm-findings.jsonl"
LINE_PREFIX = re.compile(r"^(\d+)행")
TABLE_RULE = re.compile(r"^\|[\s\-|:]+\|$")
URL_ONLY = re.compile(r"^[-\s]*\[?https?://\S+\]?\(?\S*\)?$")
# 한글이 든 어절 — 「검증을」은 세고 「R2026b」는 안 센다
HANGUL_WORD = re.compile(r"\S*[가-힣]\S*")
MIN_KOREAN_WORDS = 4

# 시각 형식 지적 — 이 시스템이 보는 것은 한국어가 바로 쓰였는지다. 굵게·이모지·
# 강조 개수는 전역 문서 검사기의 서식 규칙이라 여기서는 안 보여 준다.
VISUAL_MARKS = ("값 안 굵게", "강조 과다", "굵게", "VISUAL_DECORATION", "EMPHASIS_NOISE")


def load_global():
    spec = importlib.util.spec_from_file_location("doc_style_check", GLOBAL_CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def judgeable(lines: list[str], min_words: int = MIN_KOREAN_WORDS) -> list[int]:
    """한국어 문장으로 판정할 것이 있는 줄만 남긴다.

    한글 어절이 서너 개도 안 되는 줄은 제목·제품명·날짜·출처 링크다. 판정할
    문장이 없는데 목록에 넣으면 사람이 끝까지 안 본다 — 실측으로 한글 두 자
    기준이면 107행, 어절 넷이면 72행이다.
    """
    out, front = [], False
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if number == 1 and stripped == "---":
            front = True
            continue
        if front:
            if stripped == "---":
                front = False
            continue
        if not stripped or TABLE_RULE.match(stripped) or URL_ONLY.match(stripped):
            continue
        if len(HANGUL_WORD.findall(stripped)) < min_words:
            continue
        out.append(number)
    return out


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def existing(document_id: str, lines: list[str]) -> dict[int, list[str]]:
    """이미 나온 지적을 줄 번호별로 모은다 — 1층·2층·기존 라벨."""
    found: dict[int, list[str]] = {}
    check = skill_bridge.load("check")
    rules = check.load_rules()
    source = SOURCE_DIR / f"{document_id}.md"

    result = check.scan_files([source], rules, "general_it_business", False, "general")
    for finding in result["findings"]:
        number = finding.get("line_number")
        if number:
            found.setdefault(int(number), []).append(f"스킬: {finding.get('rule_id')}")

    errors, warnings, _ = load_global().scan_md(str(source))
    for tier, items in (("오류", errors), ("주의", warnings)):
        for kind, message in items:
            match = LINE_PREFIX.match(message)
            if match:
                found.setdefault(int(match.group(1)), []).append(f"{tier}: {kind}")

    for row in read_jsonl(LABELS):
        if str(row["document_id"]) != document_id:
            continue
        for number, line in enumerate(lines, 1):
            if row["original"].splitlines()[0] in line:
                verdict = "지적" if row.get("human_label") == "revise" else "허용"
                found.setdefault(number, []).append(f"라벨({verdict}): {row['category']}")
                break

    for row in read_jsonl(LAYER2):
        if str(row["document_id"]) == document_id:
            found.setdefault(int(row["line_number"]), []).append(f"2층: {row['category']}")
    return found


def visible(marks: list[str]) -> list[str]:
    """시각 형식 지적을 뺀다 — 이 시스템이 보는 것은 한국어 표현이다."""
    return [m for m in marks if not any(v in m for v in VISUAL_MARKS)]


def build(document_id: str, out: Path) -> int:
    source = SOURCE_DIR / f"{document_id}.md"
    lines = source.read_text(encoding="utf-8").splitlines()
    found = existing(document_id, lines)
    numbers = judgeable(lines)

    parts = [
        "---\nform: structured\n---\n",
        f"# 줄 단위 판정 — {document_id}\n",
        f"**{len(numbers)}행을 「깨끗함」이나 「고칠 것」으로 판정 요청** — "
        "붙어 있는 지적을 확인하고 **빠진 것만** 적으면 됨 · "
        "판정이 끝나야 회수율의 분모가 참이 됨\n",
        "## 읽는 법\n",
        "- **판정**: 붙은 지적이 맞으면 `O` · 틀리면 `X` · "
        "**아무도 안 잡았는데 한국어가 어색하면 그것을 적음**\n"
        "- 손댈 곳이 없으면 비워 두면 됨 — 빈 칸은 「깨끗함」으로 읽음\n"
        "- **굵게·이모지·강조 개수는 대상 아님** — 이 시스템이 보는 것은 한국어 표현\n"
        f"- **뺀 줄**: 제목·제품명·날짜·출처 링크 등 한글 어절 {MIN_KOREAN_WORDS}개 미만\n",
        f"## 판정 대상 {len(numbers)}행\n",
        "| 행 | 원문 | 이미 나온 지적 | 판정 |\n|---|---|---|---|",
    ]
    for number in numbers:
        text = lines[number - 1].strip().replace("|", "\\|")
        if len(text) > 96:
            text = text[:95] + "…"
        marks = " · ".join(visible(found.get(number, []))) or ""
        parts.append(f"| {number} | {text} | {marks} | |")
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return len(numbers)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--documents", nargs="*", default=["doc-002", "doc-004", "doc-013"])
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for document_id in args.documents:
        if not (SOURCE_DIR / f"{document_id}.md").is_file():
            continue
        out = args.out_dir / f"line-review-{document_id}.md"
        print(f"{out} · {build(document_id, out)}행")


if __name__ == "__main__":
    main()
