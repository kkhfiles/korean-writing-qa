#!/usr/bin/env python
"""공개 저장소에 나가면 안 되는 것이 섞였는지 본다.

    python scripts/check_publish_safety.py [--all]

**왜 필요한가.** 이 저장소는 공개 직전에 사람이 전수로 훑었다. 그런데 그 뒤에
들어온 파일은 아무도 안 봤고, 실제로 실행 기록의 측정 스크립트에 작성자 기계의
홈 경로가 박힌 채 올라갔다(2026-09-08). 일회성 점검은 그다음 커밋부터 무력하다.

**막는 것만 막는다.** 정당한 쓰임이 섞이는 갈래는 CI 에서 안 본다 —
`~/.claude` 는 설치 경로이고(80군데) `P:/github/...` 는 기본 위치다(29군데).
그것을 매번 찍으면 사람이 출력을 안 읽게 되고, 그러면 진짜 지적도 같이 묻힌다.
넓게 훑어보려면 `--all` 로 사람이 부른다.

**⚠️ 이 검사가 안 보는 것** — 사람 이름 · 고객사 이름 · 아직 안 알린 계획.
글자만으로는 안 갈린다. 그건 사람이 읽어야 한다.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[1]

#: 자리표시자로 쓰는 이름 — 실제 계정이 아니다(문서와 시료가 예시로 쓴다).
PLACEHOLDER = r"(?:name|user|username|you|me|runner|<[^/\\>]+>|%[^%]+%|\$\w+)"

#: 막는 갈래 — 오탐이 섞이면 안 된다. CI 가 이것만 본다.
BLOCK = [
    # 이름은 영숫자로 시작해야 한다 — 안 그러면 `/c/Users/...` 의 말줄임표가 이름으로 걸린다.
    ("홈 경로에 실제 계정 이름",
     re.compile(rf"(?:[A-Za-z]:[/\\]Users[/\\]|/home/|/Users/)(?!{PLACEHOLDER}\b)"
                r"[A-Za-z0-9][A-Za-z0-9._-]{1,}"),
     "계정 이름이 드러난다 — `Path.home()` 이나 환경 변수로 바꿀 것"),
    ("메일 주소",
     re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"),
     "받는 사람이 스팸을 받는다 — 지우거나 역할 이름으로"),
    ("열쇠로 보이는 것",
     re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{8,}"
                r"|AKIA[0-9A-Z]{12,})"),
     "자격 증명이다 — 즉시 폐기하고 이력에서도 지울 것"),
    ("사내 주소",
     re.compile(r"https?://[a-z0-9.-]*\.(?:local|internal|corp|lan)\b", re.I),
     "바깥에서 닿지 않는 주소다 — 내부 구조를 드러낸다"),
    ("지라 키",
     re.compile(r"\b(?:TEAMMANAGE|CTS|DVERA|ALIRA)-\d+\b"),
     "사내 이슈 번호다 — 무슨 일을 하는지가 새어 나간다"),
]

#: 알리기만 하는 갈래 — 정당한 쓰임이 많아 CI 에서는 안 본다.
NOTE = [
    ("작성자 기계 경로", re.compile(r"[A-Za-z]:[/\\](?:github|bitbucket|management)")),
    ("회사 이름", re.compile(r"suresofttech", re.I)),
]

SKIP_SUFFIX = {".woff2", ".woff", ".ttf", ".otf", ".png", ".jpg", ".jpeg",
               ".gif", ".ico", ".pdf", ".zip"}


def tracked_files():
    """공개되는 것은 Git 이 아는 것뿐이다 — 작업 디렉터리 전체가 아니다."""
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    for rel in out.split("\n"):
        rel = rel.strip()
        if not rel:
            continue
        p = REPO / rel
        if p.is_file() and p.suffix.lower() not in SKIP_SUFFIX:
            yield rel, p


def scan(patterns):
    found = []
    for rel, path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for name, pattern, *fix in patterns:
            for m in pattern.finditer(text):
                line = text[:m.start()].count("\n") + 1
                src = " ".join(text.splitlines()[line - 1].split())[:96]
                found.append((name, rel, line, m.group(0)[:44], src,
                              fix[0] if fix else ""))
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--all", action="store_true",
                    help="정당한 쓰임이 섞이는 갈래까지 본다 — 사람이 훑을 때")
    args = ap.parse_args(argv)

    blocked = scan(BLOCK)
    if blocked:
        print(f"⛔ 나가면 안 되는 것 {len(blocked)}건\n")
        for name, rel, line, hit, src, fix in blocked:
            print(f"  [{name}] {rel}:{line}  「{hit}」")
            print(f"      {src}")
            if fix:
                print(f"      → {fix}")
        print()
    else:
        n = sum(1 for _ in tracked_files())
        print(f"통과 — 추적 파일 {n}개에 계정 이름·메일·열쇠·사내 주소·지라 키 없음")

    print("⚠️ 사람 이름·고객사 이름·안 알린 계획은 이 검사가 안 봅니다 — 사람이 읽습니다")

    if args.all:
        notes = scan(NOTE)
        print(f"\n참고 {len(notes)}건 — 정당한 쓰임이 섞이므로 막지 않는다")
        seen = set()
        for name, rel, line, hit, src, _ in notes:
            if (name, rel) in seen:
                continue
            seen.add((name, rel))
            print(f"  [{name}] {rel}:{line}  「{hit}」")

    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
