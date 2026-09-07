"""실제 문서 뭉치에서 산문 비율과 개조식 지적 수의 관계를 잰다.

**왜 필요한가.** 산문 백서 표본 하나로 전역 검사기가 쏟아진다고 판정했는데,
그 표본은 이 세션이 직접 썼다. 걸리게 쓴 것일 수 있으므로 사람이 실제로 쓴
문서에서 같은 일이 나는지 확인한다.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

CHECKER = repo_paths.CHECKER
CORPUS = Path("P:/github/claude-workflow/reports")

STRUCTURE = re.compile(r"^\s*(?:[-*+]\s|\d+[.)]\s|\||#{1,6}\s|>|```|:?-{3,})")
SENTENCE_END = re.compile(r"[.!?。]\s*$")


def load_checker():
    spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prose_share(text: str) -> tuple[float, int]:
    """머리말·코드펜스를 뺀 본문에서 흐르는 문장이 차지하는 비율."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), 0)
        lines = lines[end + 1:]
    body, fenced = [], False
    for line in lines:
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or not line.strip():
            continue
        body.append(line)
    if not body:
        return 0.0, 0
    flowing = [l for l in body if not STRUCTURE.match(l) and SENTENCE_END.search(l)]
    return len(flowing) / len(body), len(body)


def main() -> None:
    checker = load_checker()
    rows = []
    for path in sorted(CORPUS.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(re.findall(r"[가-힣]", text)) < 300:
            continue
        share, body_lines = prose_share(text)
        try:
            errors, warnings, slots = checker.scan_md(str(path))
        except Exception as exc:                      # noqa: BLE001
            print(f"검사 실패 {path.name}: {exc}", file=sys.stderr)
            continue
        structural = sum(
            1 for kind, _ in errors
            if kind in ("서술형 종결", "진입점 서술형", "진입점 없음", "제목 명사형 위반")
        )
        rows.append({
            "path": str(path.relative_to(CORPUS)).replace("\\", "/"),
            "prose_share": round(share, 3),
            "body_lines": body_lines,
            "errors": len(errors),
            "structural_errors": structural,
            "value_slots": len(slots) if hasattr(slots, "__len__") else int(bool(slots)),
        })
    Path(sys.argv[1]).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"문서 {len(rows)}건 기록")


if __name__ == "__main__":
    main()
