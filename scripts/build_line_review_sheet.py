"""줄 단위 전수 판정 시트를 만든다.

**왜 필요한가.** 지금 회수율의 분모는 「누가 알아챈 것」이다. 라벨 13건이 전부
읽기 통과에서 나왔으므로, 아무도 못 본 문제는 미탐으로 세어지지 않는다. 분모를
참으로 만들려면 **모든 줄이 판정돼야** 한다 — 지적이 없는 줄도 「깨끗함」으로
판정된 것이라야 한다.

**시트를 두 부분으로 가른다.** 예전에는 한 표에 지적 붙은 줄과 안 붙은 줄을
섞고, 지적은 `ENGLISH_OVERUSE` 같은 영어 코드로만 적었다. 읽는 사람이
「지적이 없는데 뭘 판정하라는 건지」 알 수 없었다. 두 부분은 묻는 것이 다르다.

1. **지적 확인** — 나온 지적이 맞는지. 문제 구절·고칠 말·이유를 함께 보여 준다.
2. **빠진 것 찾기** — 아무도 안 잡은 줄에 어색한 데가 있는지. 이쪽이 본 일이다.
3. **이미 판정된 것** — 앞서 「문제 아님」으로 정해진 것. 뒤집을 때만 적는다.

③을 ①에 섞으면 **빈 칸이 정반대 두 뜻을 갖는다** — ①에서는 「이 지적이 맞다」,
③에서는 「문제가 아닌 게 맞다」. 섞어 두었더니 회수율이 한 건을 반대로 셌다(실측).

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

import repo_paths

SOURCE_DIR = REPO_ROOT / "data" / "raw" / "diagnostic-002"
GLOBAL_CHECKER = repo_paths.CHECKER
LABELS = REPO_ROOT / "data" / "annotations" / "diagnostic-002-review.jsonl"
LAYER2 = REPO_ROOT / "runs" / "eval-003" / "llm-findings.jsonl"
LINE_PREFIX = re.compile(r"^(\d+)행")
TABLE_RULE = re.compile(r"^\|[\s\-|:]+\|$")
URL_ONLY = re.compile(r"^[-\s]*\[?https?://\S+\]?\(?\S*\)?$")
# 한글이 든 어절 — 「검증을」은 세고 「R2026b」는 안 센다
HANGUL_WORD = re.compile(r"\S*[가-힣]\S*")
MIN_KOREAN_WORDS = 4
CLEAN_COLUMNS = 3        # 행 · 원문 · 판정
# 「누가」 칸에 이 값이 있으면 이미 「문제 아님」으로 판정된 지적이다
ALLOWED = "사람이 괜찮다 함"

# 시각 형식 지적 — 이 시스템이 보는 것은 한국어가 바로 쓰였는지다. 굵게·이모지·
# 강조 개수는 전역 문서 검사기의 서식 규칙이라 여기서는 안 보여 준다.
VISUAL_CATEGORIES = {"VISUAL_DECORATION", "EMPHASIS_NOISE"}
VISUAL_KINDS = ("값 안 굵게", "강조 과다", "묶음 과대")

# 갈래 이름을 한국어로 — 읽는 사람이 코드를 해독하게 두지 않는다.
# 새 갈래가 들어오면 시험이 잡는다(tests/test_line_review_sheet.py).
CATEGORY_KO = {
    "ENGLISH_OVERUSE": "불필요한 영어",
    "EVALUATIVE_MODIFIER": "평가 수식어",
    "REDUNDANT_MODIFIER": "겹치는 수식",
    "REDUNDANT_REPEAT": "같은 말 반복",
    "NOMINALIZATION": "명사로 굳힌 서술",
    "TRANSLATIONESE": "번역투",
    "VAGUE_VERB": "뜻 흐린 동사",
    "VAGUE_LABEL": "뭉뚱그린 라벨",
    "ABSTRACT_SUBJECT": "추상 주어",
    "UNNATURAL_METAPHOR": "어색한 비유",
    "LITERAL_PATH": "「경로」를 그대로 씀",
    "TYPO": "오탈자",
    "VISUAL_DECORATION": "시각 장식",
    "EMPHASIS_NOISE": "강조 남용",
    # 문서 검사기는 같은 것을 제 이름으로 부른다 — 한 이름으로 모아야 한 건이 된다
    "스캔 가치 없는 라벨": "뭉뚱그린 라벨",
}


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


def category_ko(code: str) -> str:
    """갈래 코드를 한국어 이름으로. 모르는 코드는 코드째 남긴다(조용히 감추지 않는다)."""
    return CATEGORY_KO.get(code, code)


def existing(document_id: str, lines: list[str]) -> list[dict]:
    """이미 나온 지적을 모은다 — 1층 규칙·전역 검사기·사람 라벨·2층 읽기.

    같은 구절을 여러 층이 잡으면 한 건으로 합치고 「누가」에 층을 나열한다.
    """
    found: dict[tuple, dict] = {}

    def add(number, source, category, original="", revised="", why=""):
        key = (number, original or category)
        row = found.setdefault(key, {
            "line": number, "sources": [], "category": category,
            "original": original, "revised": revised, "why": why,
        })
        if source not in row["sources"]:
            row["sources"].append(source)
        for field, value in (("revised", revised), ("why", why), ("original", original)):
            if value and not row[field]:
                row[field] = value

    source_path = SOURCE_DIR / f"{document_id}.md"
    check = skill_bridge.load("check")
    result = check.scan_files([source_path], check.load_rules(),
                              "general_it_business", False, "general")
    for finding in result["findings"]:
        number = finding.get("line_number")
        if number:
            add(int(number), "1층 규칙", finding.get("category") or finding.get("rule_id"),
                finding.get("original", ""), finding.get("revised", ""), "")

    errors, warnings, _ = load_global().scan_md(str(source_path))
    for items in (errors, warnings):
        for kind, message in items:
            match = LINE_PREFIX.match(message)
            if not match or kind in VISUAL_KINDS:
                continue
            # 검사기 사유는 「낱말」 앞뒤에 원문 줄을 통째로 붙인다 — 낱말만 뽑는다.
            # 앞에도 말이 붙는다(「표 머리 「비고」」) — 처음부터 찾으면 놓친다
            body = LINE_PREFIX.sub("", message).strip()
            quoted = re.search(r"「([^」]+)」", body)
            add(int(match.group(1)), "문서 검사기", kind,
                quoted.group(1) if quoted else "", "", "" if quoted else body)

    for row in read_jsonl(LABELS):
        if str(row["document_id"]) != document_id:
            continue
        head = row["original"].splitlines()[0]
        for number, line in enumerate(lines, 1):
            if head in line:
                verdict = "사람이 고치라 함" if row.get("human_label") == "revise" else ALLOWED
                add(number, verdict, row["category"], row["original"], row.get("revised", ""), "")
                break

    for row in read_jsonl(LAYER2):
        if str(row["document_id"]) == document_id:
            add(int(row["line_number"]), "2층 읽기", row["category"],
                row.get("original", ""), row.get("revised", ""), row.get("why", ""))

    rows = [r for r in sorted(found.values(), key=lambda r: (r["line"], r["category"]))
            if r["category"] not in VISUAL_CATEGORIES]
    return merge_overlapping(rows)


def merge_overlapping(rows: list[dict]) -> list[dict]:
    """같은 줄·같은 갈래에서 한쪽 구절이 다른 쪽에 들어 있으면 한 건이다.

    층마다 구절을 잡는 폭이 다르다 — 문서 검사기는 「강력한」, 2층은 「강력한
    `.claudeignore` 활용」을 낸다. 나란히 두면 읽는 사람이 두 번 판정해야 한다.
    긴 쪽을 남기고 「누가」만 합친다.

    갈래는 **한국어 이름으로 맞춰 본다** — 문서 검사기는 「평가 수식어」로,
    다른 층은 `EVALUATIVE_MODIFIER` 로 같은 것을 부른다. 코드로 대조하면
    같은 지적이 두 줄로 남는다(실측으로 걸렸다).
    """
    out: list[dict] = []
    for row in sorted(rows, key=lambda r: -len(r["original"])):
        for kept in out:
            if (kept["line"], category_ko(kept["category"])) != (
                    row["line"], category_ko(row["category"])):
                continue
            if not row["original"] or row["original"] in kept["original"]:
                for source in row["sources"]:
                    if source not in kept["sources"]:
                        kept["sources"].append(source)
                for field in ("revised", "why"):
                    if row[field] and not kept[field]:
                        kept[field] = row[field]
                break
        else:
            out.append(row)
    return sorted(out, key=lambda r: (r["line"], r["category"]))


def cell(text: str) -> str:
    return (text or "").strip().replace("|", "\\|").replace("\n", " ")


def quoted_cell(text: str) -> str:
    """원문에서 따온 글은 「」로 감싼다.

    이유 둘 — 읽는 사람에게 「이건 내가 쓴 말이 아니라 문서에서 따온 것」임을
    보이고, 문서 검사기가 그 칸을 자기 규칙으로 재지 않게 한다(원문은 글자가
    같아야 하므로 개조식으로 고칠 수 없다).
    """
    text = cell(text)
    return f"「{text}」" if text else "—"


def build(document_id: str, out: Path) -> tuple[int, int]:
    source = SOURCE_DIR / f"{document_id}.md"
    lines = source.read_text(encoding="utf-8").splitlines()
    numbers = judgeable(lines)
    all_findings = [f for f in existing(document_id, lines) if f["line"] in set(numbers)]
    # 이미 「문제 아님」으로 판정된 것은 따로 뺀다 — 한 표에 두면 빈 칸이 「이
    # 지적이 맞다」와 「문제가 아닌 게 맞다」 두 뜻을 갖는다(실측으로 계산이 틀렸다)
    findings = [f for f in all_findings if ALLOWED not in f["sources"]]
    allowed = [f for f in all_findings if ALLOWED in f["sources"]]
    flagged = {f["line"] for f in all_findings}
    clean = [n for n in numbers if n not in flagged]

    parts = [
        "---\nform: structured\n---\n",
        f"# 줄 단위 판정 — {document_id}\n",
        f"**한글 {len(numbers)}행이 바르게 쓰였는지 판정 요청** — "
        f"**「② 빠진 것 찾기」의 {len(clean)}행이 본 일** · "
        f"①은 이미 나온 지적 {len(findings)}건이 맞는지 보는 것 · "
        "빈 칸은 「고칠 데 없음」으로 읽음\n",
        "## 이 판정으로 얻는 것\n",
        "- **지금 세는 것**: 누군가 알아챈 문제뿐 — 검사기가 놓친 것은 안 세어짐\n"
        "- **판정 뒤에 셀 수 있는 것**: 문서에 실제로 있는 문제 대비 검사기가 잡는 비율\n",
        "## 쓰는 법\n",
        "| 어느 표 | 묻는 것 | 판정 칸에 적을 것 |\n|---|---|---|\n"
        "| ① 지적 확인 | 이 지적이 맞나 | 맞으면 `O` · 아니면 `X` · 헷갈리면 `?` |\n"
        f"| ② 빠진 것 찾기 | 어색한 데가 있나 | 어색한 **구절을 그대로** 적음 · 없으면 빈 칸 |\n"
        "| ③ 이미 판정된 것 | 그 판정이 맞나 | 뒤집을 것만 적음 · 그대로면 빈 칸 |\n",
        "**②의 보기** — 「멀티 에이전트 환경에서 세션 간 비동기 메시지 전달」 같은 줄이 걸린다면 "
        "판정 칸에 `비동기 메시지 전달` 이라고만 적으면 됨 · 고칠 말까지는 안 적어도 됨\n",
        "**대상 아닌 것** — 굵게·이모지·강조 개수는 이 검사가 보는 축이 아님 · "
        f"한글 어절 {MIN_KOREAN_WORDS}개 미만인 줄(제목·제품명·날짜·출처)은 목록에서 뺌\n",
        f"## ① 지적 확인 — {len(findings)}건\n",
        "| 행 | 갈래 | 지적한 구절 | 이렇게 고치자 | 왜 | 누가 | 판정 |\n"
        "|---|---|---|---|---|---|---|",
    ]
    # 구절과 고칠 말은 자르지 않는다 — 자르면 그 지적이 맞는지 판정할 수 없다
    for f in findings:
        parts.append("| {line} | {cat} | {orig} | {rev} | {why} | {who} | |".format(
            line=f["line"], cat=cell(category_ko(f["category"])),
            orig=quoted_cell(f["original"]),
            rev=quoted_cell(f["revised"]),
            why=cell(f["why"]) or "—",
            who=cell(" · ".join(f["sources"]))))

    parts += [
        f"\n## ② 빠진 것 찾기 — {len(clean)}행\n",
        "**아무도 지적하지 않은 줄** — 어색한 구절이 있으면 그것을 판정 칸에 적음\n",
        "| 행 | 원문 | 판정 |\n|---|---|---|",
    ]
    for number in clean:
        parts.append(f"| {number} | {quoted_cell(lines[number - 1])} | |")

    if allowed:
        parts += [
            f"\n## ③ 이미 「문제 아님」으로 판정된 것 — {len(allowed)}건\n",
            "**뒤집을 것만 적음** — 그대로 두려면 빈 칸\n",
            "| 행 | 갈래 | 구절 | 판정 |\n|---|---|---|---|",
        ]
        for f in allowed:
            parts.append(f"| {f['line']} | {cell(category_ko(f['category']))} | "
                         f"{quoted_cell(f['original'])} | |")

    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return len(findings), len(clean), len(allowed)


def answered(path: Path) -> bool:
    """판정 칸이 하나라도 채워져 있나.

    사람이 채운 시트를 덮어쓰면 그 판정은 되찾을 수 없다 — 실제로 한 번
    날렸다(다른 곳에 옮겨 적어 둔 덕에 되살렸다). 그래서 기본은 건너뛰기다.
    """
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in re.split(r"(?<!\\)\|", line)][1:-1]
        if len(cells) >= CLEAN_COLUMNS and cells[0].isdigit() and cells[-1]:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--documents", nargs="*", default=["doc-002", "doc-004", "doc-013"])
    parser.add_argument("--force", action="store_true",
                        help="판정이 들어 있는 시트도 다시 만든다 — 그 판정은 사라진다")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for document_id in args.documents:
        if not (SOURCE_DIR / f"{document_id}.md").is_file():
            continue
        out = args.out_dir / f"line-review-{document_id}.md"
        if answered(out) and not args.force:
            print(f"{out} · 판정이 들어 있어 건너뜀 (--force 로 덮어씀)")
            continue
        marked, clean, allowed = build(document_id, out)
        note = f" · 이미 판정 {allowed}건" if allowed else ""
        print(f"{out} · 지적 확인 {marked}건 · 빠진 것 찾기 {clean}행{note}")


if __name__ == "__main__":
    main()
