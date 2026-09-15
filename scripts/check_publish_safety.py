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
               ".gif", ".ico", ".pdf", ".zip", ".webp", ".avif", ".mp4", ".webm",
               ".mp3", ".wasm", ".gz", ".db", ".sqlite"}


def published(repo):
    """이 저장소가 **실제로 밖으로 나가나.** (나감?, 한 줄 설명)

    ⛔ 안 나가는 저장소의 지적과 나가는 저장소의 지적을 **같은 무게로 내면 안 된다.**
       실측(2026-09-15) — 원격 없는 저장소에서 73건이 떴고 공개 저장소에서 4건이
       떴는데 머리글이 같았다. 앞엣것은 한 줄도 안 나가는데 뒤엣것만 나간다.
       못 가르는 지적이 섞이면 가르는 지적까지 안 읽힌다.
    """
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo,
                         capture_output=True, text=True, encoding="utf-8").stdout.strip()
    if not url:
        return False, "원격이 없다 — 이 저장소 자체는 안 나간다"
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        return True, f"원격 있음({url[:40]}) — 공개 여부를 못 봤다"
    got = subprocess.run(["gh", "repo", "view", m.group(1), "--json", "visibility",
                          "--jq", ".visibility"], cwd=repo, capture_output=True,
                         text=True, encoding="utf-8").stdout.strip()
    if got == "PUBLIC":
        return True, f"PUBLIC — {m.group(1)}"
    if got:
        return False, f"{got} — {m.group(1)}"
    return True, f"{m.group(1)} — 공개 여부를 못 물었다"


def identity_terms():
    """저장소 밖 신원 목록을 절별로 읽는다. 없으면 빈 것 — 부른 쪽이 알린다.

    ★ 사람 이름과 회사 이름은 **막는 세기가 달라야 한다**(2026-09-15 실측).
    회사 이름은 산문에 정당하게 나온다 — 「네이버 `Yeti`·다음 `Daum`·카카오톡」이
    크롤러 목록인데 고객사 언급으로 잡혔다. 사람 이름은 그런 쓰임이 없다.
    """
    out = {"이름": set(), "회사": set(), "조직": set()}
    if not DENYLIST.exists():
        return out
    section = None
    for line in DENYLIST.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        head = re.fullmatch(r"\[(.+)\]", line)
        if head:
            section = head.group(1).strip()
            out.setdefault(section, set())
        elif line and section:
            out[section].add(line)
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


#: 회사 이름을 막는 갈래로 보는 파일 — 자료 파일이다.
DATA_SUFFIX = {".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".toml"}


def scan(patterns, pairs, deny=None, advisory=False):
    """`deny` 는 절별 신원 목록. `advisory` 면 막는 쪽에서 뺀 것만 낸다.

    ⛔ **사람 이름은 어느 파일에서든 막는다.** 처음에는 자료 파일로만 좁혔는데,
       근거가 「이번 사고가 자료 파일 모양이었다」라는 **한 건의 모양**이었다.
       심어서 재 보니 산문(`.md`)·코드(`.py`)의 실명이 통째로 빠져나갔다
       (다른 세션이 그 일반화를 짚어 줘서 확인했다).
    ⚠️ 회사 이름만 자료 파일로 좁힌다 — 산문에 정당하게 나오기 때문이다(크롤러 목록).
    """
    deny = deny or {}
    found = []
    for rel, text in pairs:
        is_data = pathlib.Path(rel.split("@")[0]).suffix.lower() in DATA_SUFFIX
        buckets = []
        if not advisory:
            buckets = [("사람 이름", deny.get("이름", ())),
                       ("사내 조직", deny.get("조직", ()))]
            if is_data:
                buckets.append(("회사·고객사", deny.get("회사", ())))
        elif not is_data:
            buckets = [("회사·고객사", deny.get("회사", ()))]
        for label, terms in buckets:
            for t in terms:
                # ⛔ 이름·조직은 **낱말 머리에서만** 찾는다 — 목록 파일이 스스로
                #    「낱말 전체가 이것과 같을 때만」이라 적어 뒀는데 검사기는 부분
                #    문자열로 찾고 있었다. 두 쪽이 어긋나 이름 끝 두 글자를 목록에
                #    넣으면 그 두 글자를 품은 보통 낱말이 통째로 막힌다.
                #    ⛔ 여기에 실제 예시를 적지 않는다 — 적는 순간 이 파일이 명단이다.
                #    앞 글자가 한글이면 다른 낱말의 속이다. 뒤는 안 본다 — 한국어
                #    이름 뒤에는 조사·직함이 바로 붙는다(「홍길동이」·「홍길동 책임」).
                pat = re.escape(t) if label == "회사·고객사" else r"(?<![가-힣])" + re.escape(t)
                for m in re.finditer(pat, text):
                    line = text[:m.start()].count("\n") + 1
                    found.append((f"신원 목록의 {label}", rel, line, t,
                                  " ".join(text.splitlines()[line - 1].split())[:96],
                                  "저장소 밖 목록에 적힌 것이다"))
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

    deny = identity_terms()
    files = list(read_files(tracked_files(repo)))
    pairs = list(files)
    if args.history:
        pairs += list(history_blobs(repo))

    goes_out, why = published(repo)
    print(f"저장소 {repo} · 추적 파일 {len(files)}개"
          + (f" · 이력 판 {len(pairs) - len(files)}개" if args.history else ""))
    print(f"   {'밖으로 나감' if goes_out else '안 나감'} — {why}")
    if not any(deny.values()):
        print(f"⚠️ 신원 목록이 없습니다({DENYLIST.name}) — 이름·회사는 안 봅니다")
    else:
        print(f"   신원 목록 — 이름 {len(deny['이름'])} · 회사 {len(deny['회사'])}"
              f" · 조직 {len(deny['조직'])} (사람 이름은 어느 파일에서든 막음)")

    blocked = scan(BLOCK, pairs, deny)
    if blocked and not goes_out:
        # 안 나가는 저장소다 — 같은 지적을 「나가면 안 되는 것」으로 내면 소음이 된다
        print(f"\n📋 지금은 안 나가지만 공개하면 걸릴 것 {len(blocked)}건"
              " — 급하지 않으나 종료 코드는 1이다\n")
    elif blocked:
        print(f"\n⛔ 나가면 안 되는 것 {len(blocked)}건\n")
        seen, folded = set(), 0
        for name, rel, line, hit, src, fix in blocked:
            if (name, rel.split("@")[0], hit) in seen:
                folded += 1
                continue
            seen.add((name, rel.split("@")[0], hit))
            print(f"  [{name}] {rel}:{line}  「{hit}」")
            print(f"      {src}")
            if fix:
                print(f"      → {fix}")
        # ⛔ **접은 것을 안 적으면 머리글과 목록이 어긋난다.** 「48건」이라 써 놓고 13줄만
        #    보이면 읽는 사람은 35건이 숨은 줄 안다. 이력을 볼 때 같은 파일의 옛 판이
        #    겹쳐 그 차이가 세 배까지 벌어졌다(2026-09-15 실측).
        if folded:
            print(f"  ↳ 같은 파일·같은 낱말이라 접은 것 {folded}건 — "
                  f"위 {len(seen)}줄이 전부입니다(이력의 옛 판이 여기 겹칩니다)")
        print()
    else:
        print("통과 — 계정 이름·메일·열쇠·사내 주소·지라 키·메신저 아이디 없음"
              + (" · 목록의 이름·조직 없음" if any(deny.values()) else ""))

    print("⚠️ 아직 안 알린 계획은 이 검사가 안 봅니다 — 사람이 읽습니다")
    if not args.history:
        print("   이력은 안 봤습니다 — 공개 저장소는 `--history` 로 함께 봅니다")

    if args.all:
        # 산문·코드 속 이름·회사는 여기서 사람에게 보인다 — 막지는 않는다
        notes = scan(NOTE, pairs, deny, advisory=True)
        print(f"\n참고 {len(notes)}건 — 정당한 쓰임이 섞이므로 막지 않는다")
        seen, folded = set(), 0
        for name, rel, line, hit, src, _ in notes:
            key = (name, rel.split("@")[0])
            if key in seen:
                folded += 1
                continue
            seen.add(key)
            print(f"  [{name}] {rel}:{line}  「{hit}」")
        if folded:
            print(f"  ↳ 같은 파일·같은 갈래라 접은 것 {folded}건 — "
                  f"위 {len(seen)}줄이 전부입니다")

    # ⛔ 안 나가는 저장소라도 **종료 코드는 그대로 1** 이다. 「원격이 없다」는 오늘의
    #    사실일 뿐 내일 생길 수 있고, 안전장치는 안전한 쪽으로 틀려야 한다.
    #    갈라 주는 것은 머리글이지 판정이 아니다 — 시험이 이 자리를 지킨다.
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
