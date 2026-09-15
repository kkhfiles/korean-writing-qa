#!/usr/bin/env python
"""공개 저장소에 나가면 안 되는 것이 섞였는지 본다.

    python scripts/check_publish_safety.py [--all] [--repo <경로>] [--history]

**왜 필요한가.** 이 저장소는 공개 직전에 사람이 전수로 훑었다. 그런데 그 뒤에
들어온 파일은 아무도 안 봤고, 실제로 실행 기록의 측정 스크립트에 작성자 기계의
홈 경로가 박힌 채 올라갔다(2026-09-08). 일회성 점검은 그다음 커밋부터 무력하다.

**막는 것만 막는다.** 정당한 쓰임이 섞이는 갈래는 CI 에서 안 본다 —
`~/.claude` 는 설치 경로이고(80군데) `P:/github/...` 는 기본 위치다(29군데).
그것을 매번 찍으면 사람이 출력을 안 읽게 되고, 그러면 진짜 지적도 같이 묻힌다.
넓게 훑어보려면 `--all` 로 사람이 부른다.

**⚠️ 이 검사가 안 보는 것** — 사람 이름 · 고객사 이름 · 아직 안 알린 계획.
글자만으로는 안 갈린다. 그건 사람이 읽어야 한다.

★ **2026-09-15 — 그 「안 보는 것」이 그대로 났다.** 낱말 빈도표에 동료 실명 554종과
  고객사가 빈도까지 붙어 공개로 나가 있었고, 이 검사는 통과를 찍고 있었다. 그래서 둘을
  넓혔다.

  - **`--repo <경로>`** — 이 저장소만이 아니라 **아무 저장소**나 본다. PC 에 공개
    저장소가 하나뿐이라는 보장이 없다(실측: 소유한 공개 저장소 둘).
  - **`--history`** — 지금 파일만 보면 **지운 뒤에도 이력에 남은 것**을 못 본다.
    공개 저장소는 `git log` 로 옛 판을 누구나 받는다.
  - **신원 목록** — `data/catalog/local-identity-denylist.txt` 가 있으면 그 이름·회사를
    함께 본다. ⛔ 목록 자체는 저장소에 두지 않는다(적는 순간 그게 명단이다).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[1]

#: 저장소 밖에 두는 신원 목록 — 있으면 이름·회사도 함께 본다
DENYLIST = REPO / "data" / "catalog" / "local-identity-denylist.txt"

#: 자리표시자로 쓰는 이름 — 실제 계정이 아니다(문서와 시료가 예시로 쓴다).
#   2026-09-15 에 `yourname`·`your_name` 을 더했다 — 설치 안내서가 쓰는 꼴인데
#   막는 갈래로 잡혀 나왔다. 오탐이 섞이면 아무도 안 본다.
PLACEHOLDER = (r"(?:name|user|username|you|me|runner|your[_-]?name|your[_-]?user"
               r"|<[^/\\>]+>|%[^%]+%|\$\w+)")

#: 막는 갈래 — 오탐이 섞이면 안 된다. CI 가 이것만 본다.
BLOCK = [
    # 이름은 영숫자로 시작해야 한다 — 안 그러면 `/c/Users/...` 의 말줄임표가 이름으로 걸린다.
    ("홈 경로에 실제 계정 이름",
     re.compile(rf"(?:[A-Za-z]:[/\\]Users[/\\]|/home/|/Users/)(?!{PLACEHOLDER}\b)"
                r"[A-Za-z0-9][A-Za-z0-9._-]{1,}"),
     "계정 이름이 드러난다 — `Path.home()` 이나 환경 변수로 바꿀 것"),
    # ⛔ 메일이 아닌 둘을 뺀다 — 안 빼면 정당한 지적이 예시에 묻힌다.
    #    · 꾸러미 판 표기 「claude-agent-sdk@0.3.143」 — 뒤가 숫자와 점뿐이면 판 번호다
    #    · 대놓고 지어낸 주소 「a@b.co」·「me@example.com」 — 시료가 쓰는 꼴이다
    ("메일 주소",
     re.compile(r"(?![a-z]@[a-z]\.[a-z]{2,3}\b)[\w.+-]+@(?![\d.]+\b)"
                r"(?!example\.(?:com|org|net)\b|invalid\b|localhost\b)[\w-]+\.[\w.]{2,}"),
     "받는 사람이 스팸을 받는다 — 지우거나 역할 이름으로"),
    # ⛔ 안내서의 예시 열쇠를 안 잡는다 — 「xoxb-your-bot-token」이 걸렸다.
    #    진짜 슬랙 열쇠는 숫자와 영문이 섞인 토막이라 「your」·「example」이 안 들어간다.
    ("열쇠로 보이는 것",
     re.compile(r"(?:sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{20,}"
                r"|xox[baprs]-(?!(?:your|example|test|dummy|xxx)\b)[A-Za-z0-9-]{8,}"
                r"|AKIA[0-9A-Z]{12,})"),
     "자격 증명이다 — 즉시 폐기하고 이력에서도 지울 것"),
    ("사내 주소",
     re.compile(r"https?://[a-z0-9.-]*\.(?:local|internal|corp|lan)\b", re.I),
     "바깥에서 닿지 않는 주소다 — 내부 구조를 드러낸다"),
    # ⛔ 자리표시자는 안 잡는다 — 「C0123456789」처럼 **숫자만 이어진 것은 예시**다.
    #    진짜 아이디에는 영문자가 섞인다. 좁히기 전에 실측하니 96건 중 대부분이
    #    `.env.example` 의 예시였다 — 오탐이 섞이면 아무도 안 본다.
    ("메신저 사용자·채널 아이디",
     re.compile(r"\b[CDGUT]0(?=[A-Z0-9]{8,}\b)[0-9]*[A-Z][A-Z0-9]*\b"),
     "사람과 대화방을 가리킨다 — 실행 중 만들어지는 상태 파일이 딸려 올라가기 쉽다"),
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


def identity_terms():
    """저장소 밖 신원 목록. 없으면 빈 집합 — 부른 쪽이 알린다."""
    if not DENYLIST.exists():
        return set()
    out = set()
    for line in DENYLIST.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("["):
            out.add(line)
    return out


def tracked_files(repo):
    """공개되는 것은 Git 이 아는 것뿐이다 — 작업 디렉터리 전체가 아니다."""
    out = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    for rel in out.split("\n"):
        rel = rel.strip()
        if not rel:
            continue
        p = repo / rel
        if p.is_file() and p.suffix.lower() not in SKIP_SUFFIX:
            yield rel, p


def history_blobs(repo):
    """이력에 한 번이라도 들어간 모든 판. **지운 것도 공개 저장소에는 남는다.**"""
    out = subprocess.run(["git", "rev-list", "--all", "--objects"], cwd=repo,
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout
    for line in out.split("\n"):
        if " " not in line:
            continue
        sha, rel = line.split(" ", 1)
        if pathlib.Path(rel).suffix.lower() in SKIP_SUFFIX:
            continue
        body = subprocess.run(["git", "cat-file", "-p", sha], cwd=repo,
                              capture_output=True, encoding="utf-8",
                              errors="replace").stdout
        yield f"{rel}@{sha[:8]}", body


#: 이름·회사를 **막는 갈래로 보는** 파일 — 자료 파일이다.
#   ⛔ 산문·코드에서는 막지 않는다. 실측(artifact-host) — 「네이버 Yeti·다음 Daum·
#      카카오톡」이 **크롤러 이름 목록**인데 고객사 언급으로 잡혔다. 사람 이름과
#      회사 이름은 문맥이 있어야 갈리므로, 문맥이 없는 자료 파일에서만 막는다.
#      나간 사고가 바로 그 모양이었다 — 빈도표(`.json`)의 낱말 하나에 횟수만 붙은 꼴.
DATA_SUFFIX = {".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".toml"}


def scan(patterns, pairs, terms=(), data_only_terms=True):
    found = []
    for rel, text in pairs:
        is_data = pathlib.Path(rel.split("@")[0]).suffix.lower() in DATA_SUFFIX
        for t in terms if (is_data or not data_only_terms) else ():
            for m in re.finditer(re.escape(t), text):
                line = text[:m.start()].count("\n") + 1
                found.append(("신원 목록의 이름·회사", rel, line, t,
                              " ".join(text.splitlines()[line - 1].split())[:96],
                              "저장소 밖 목록에 적힌 사람·회사다"))
        for name, pattern, *fix in patterns:
            for m in pattern.finditer(text):
                line = text[:m.start()].count("\n") + 1
                src = " ".join(text.splitlines()[line - 1].split())[:96]
                found.append((name, rel, line, m.group(0)[:44], src,
                              fix[0] if fix else ""))
    return found


def read_files(pairs):
    for rel, path in pairs:
        try:
            yield rel, path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--all", action="store_true",
                    help="정당한 쓰임이 섞이는 갈래까지 본다 — 사람이 훑을 때")
    ap.add_argument("--repo", default=str(REPO),
                    help="볼 저장소 (기본: 이 저장소). 다른 공개 저장소에도 댄다")
    ap.add_argument("--history", action="store_true",
                    help="이력의 모든 판까지 본다 — 지운 뒤에도 공개 저장소에는 남는다")
    args = ap.parse_args(argv)

    repo = pathlib.Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"⛔ Git 저장소가 아닙니다: {repo}")
        return 2

    terms = identity_terms()
    files = list(read_files(tracked_files(repo)))
    pairs = list(files)
    if args.history:
        pairs += list(history_blobs(repo))

    print(f"저장소 {repo} · 추적 파일 {len(files)}개"
          + (f" · 이력 판 {len(pairs) - len(files)}개" if args.history else ""))
    if not terms:
        print(f"⚠️ 신원 목록이 없습니다({DENYLIST.name}) — 이름·회사는 안 봅니다")

    blocked = scan(BLOCK, pairs, terms)
    if blocked:
        print(f"\n⛔ 나가면 안 되는 것 {len(blocked)}건\n")
        seen = set()
        for name, rel, line, hit, src, fix in blocked:
            if (name, rel.split("@")[0], hit) in seen:
                continue
            seen.add((name, rel.split("@")[0], hit))
            print(f"  [{name}] {rel}:{line}  「{hit}」")
            print(f"      {src}")
            if fix:
                print(f"      → {fix}")
        print()
    else:
        print("통과 — 계정 이름·메일·열쇠·사내 주소·지라 키·메신저 아이디 없음"
              + (" (이름·회사 포함)" if terms else ""))

    print("⚠️ 아직 안 알린 계획은 이 검사가 안 봅니다 — 사람이 읽습니다")
    if not args.history:
        print("   이력은 안 봤습니다 — 공개 저장소는 `--history` 로 함께 봅니다")

    if args.all:
        # 산문·코드 속 이름·회사는 여기서 사람에게 보인다 — 막지는 않는다
        notes = scan(NOTE, pairs, terms, data_only_terms=False)
        notes = [n for n in notes
                 if n[0] != "신원 목록의 이름·회사"
                 or pathlib.Path(n[1].split("@")[0]).suffix.lower() not in DATA_SUFFIX]
        print(f"\n참고 {len(notes)}건 — 정당한 쓰임이 섞이므로 막지 않는다")
        seen = set()
        for name, rel, line, hit, src, _ in notes:
            key = (name, rel.split("@")[0])
            if key in seen:
                continue
            seen.add(key)
            print(f"  [{name}] {rel}:{line}  「{hit}」")

    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
