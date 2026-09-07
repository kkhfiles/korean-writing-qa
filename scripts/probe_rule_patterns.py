"""통문장 규칙에서 뽑은 짧은 후보가 실제로 도는지, 얼마나 시끄러운지 잰다.

**왜.** 확정 규칙 6건은 10~47자 통문장이라 다시 나올 수 없다. 사람이 읽는 표는
같은 교정을 5~13자로 줄여 놓았다. 그 짧은 형태를 규칙으로 올리기 전에
발화 수와 실제 문장을 본다 — 짧게 줄이면 오탐이 생긴다.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

CORPORA = {
    "보고서": Path("<설정 저장소>/reports"),
    "발표자료": Path("<설정 저장소>/reports/project-summary"),
    "AI원문": Path("P:/github/korean-writing-qa/data/raw"),
}

# (규칙, 좁은 후보, 넓은 후보) — 표가 뽑아 둔 형태와 그보다 한 겹 넓힌 형태
CANDIDATES = [
    ("PROCESS-001", r"AI로 풉니다", r"[가-힣]+(?:로|으로) (?:풉니다|푼다|푸는)"),
    ("PROCESS-001b", r"사람이 가장 많이 붙는", r"사람이 [가-힣 ]{0,6}붙는"),
    ("CLASSIFY-001", r"갈래는 둘", r"갈래는 [둘셋넷]"),
    ("RESULT-001", r"막대가 상반기 실측", r"(?:막대|그래프|표)가 [가-힣 ]{0,8}입니다"),
    ("PLAN-001", r"뒤의 것은", r"(?:뒤|앞)의 것은"),
    ("REASON-001", r"가치가 둘", r"가치가 [둘셋]"),
    ("ACTION-001", r"반복해서 도는 일", r"도는 일"),
]


def korean_md(root: Path) -> list[Path]:
    out = []
    for p in root.rglob("*.md"):
        if ".git" in str(p):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(re.findall(r"[가-힣]", text)) >= 200:
            out.append(p)
    return out


def main() -> None:
    files = {name: korean_md(root) for name, root in CORPORA.items()}
    for name, paths in files.items():
        print(f"{name}: 문서 {len(paths)}건")
    print()

    rows = []
    for rule, narrow, wide in CANDIDATES:
        record = {"rule": rule, "narrow": narrow, "wide": wide, "hits": {}, "samples": []}
        for label, paths in files.items():
            n_narrow = n_wide = 0
            for p in paths:
                text = p.read_text(encoding="utf-8", errors="ignore")
                for line in text.splitlines():
                    n_narrow += len(re.findall(narrow, line))
                    for m in re.finditer(wide, line):
                        n_wide += 1
                        if len(record["samples"]) < 5 and label != "발표자료":
                            record["samples"].append(
                                f"{p.name[:26]} :: {line.strip()[:76]}"
                            )
            record["hits"][label] = {"좁게": n_narrow, "넓게": n_wide}
        rows.append(record)

    print("%-14s %-30s %s" % ("규칙", "넓은 후보", "보고서 / 발표자료 / AI원문 (좁게·넓게)"))
    for r in rows:
        h = r["hits"]
        cells = " · ".join(
            f"{k} {h[k]['좁게']}·{h[k]['넓게']}" for k in ("보고서", "발표자료", "AI원문")
        )
        print("%-14s %-30s %s" % (r["rule"], r["wide"][:30], cells))
    print()
    for r in rows:
        if not r["samples"]:
            continue
        print(f"[{r['rule']}] 넓은 후보가 잡은 문장")
        for s in r["samples"]:
            print("   ", s)
    Path(sys.argv[1]).write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
