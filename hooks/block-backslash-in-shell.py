r"""PreToolUse: Bash 명령 문자열에 겹 역슬래시가 있으면 막는다.

**왜 훅인가.** 이 함정은 CLAUDE.md 에 이미 적혀 있는데 계속 걸린다. 적어 두는
것으로는 안 막히는 종류다 — 실수하는 순간이 규칙을 읽은 지 한참 뒤이고, 실패가
조용할 때가 있어 알아채지도 못한다.

**무엇이 일어나나.** Bash 도구로 넘긴 명령 문자열은 셸에 닿기 전에 역슬래시가
**한 겹 벗겨진다.** 실측(2026-08-27):

| 경로 | 두 겹을 적으면 |
|---|---|
| Write 도구 | 두 겹 그대로 도착 |
| Bash 명령 문자열 | **한 겹으로 도착** |

그래서 `re.compile(r"(?<!\\)\|")` 가 `(?<!\)\|` 로 도착해 정규식이 깨지고,
`replace("|", "\\|")` 로 치환하려던 것이 빗나간다. 파이썬이 문법 오류를 내면
그나마 낫고, **조용히 다른 문자열을 치환하면 못 알아챈다.**

**범위를 좁게 적지 않는다.** CLAUDE.md 는 이것을 「셸 히어독」 문제로 적었는데
히어독만의 문제가 아니다 — `-c` 로 넘겨도 똑같다. 히어독을 피하면 안전하다고
믿게 만드는 서술이라 여기서 바로잡는다.

**막는 조건** — 명령 문자열에 역슬래시가 둘 이상 붙어 있을 때. 한 겹은 살아서
도착하므로 대상이 아니다.

**같은 부류 하나 더 — 따옴표 없는 히어독의 백틱·`$(`.** `<<EOF` 처럼 구분자를
따옴표로 안 감싸면 본문의 백틱과 `$( )` 가 **명령으로 실행되고 그 출력으로 바뀐다.**
마크다운 인라인 코드가 그렇게 실행돼 문서가 깨졌다(2026-09-16 실사고 — 수십 번
다듬은 제안서). 역슬래시 건과 같이 「셸에 닿기 전에 글자가 바뀌는」 종류라 한 훅에
둔다. `<<'EOF'` 로 감싸면 본문이 글자 그대로 도착하므로 대상이 아니고, 히어독 밖의
백틱은 의도한 명령 치환이라 안 본다. `$이름` 전개는 안 막는다 — 히어독에서 일부러
쓰는 경우가 흔해 오탐이 커진다.

Exit 0 = 통과 · Exit 2 = 차단(stderr 가 이유로 보인다).
"""
import json
import re
import sys

try:
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# 겹 역슬래시 — 「역슬래시 한 글자를 실제로 넣고 싶다」는 뜻이고, 그 의도가
# 도구 경계에서 깨지는 유일한 형태다.
DOUBLE_BACKSLASH = re.compile(r"\\\\")

# 히어독 연산자. `<<<`(히어스트링)는 제외. q 가 있으면 구분자를 감싼 것이다.
HEREDOC = re.compile(r"(?<!<)<<-?\s*(?P<q>['\"\\])?(?P<tag>[A-Za-z_][A-Za-z0-9_]*)")
# 본문에서 명령으로 실행되는 것 — 백틱과 `$(`
EXECUTES = re.compile(r"`|\$\(")

HEREDOC_REASON = """BLOCKED [block-backslash-in-shell]: 따옴표 없는 히어독 본문에 백틱(`) 또는 $( 가 있습니다.

무엇이 일어나나 — <<EOF 처럼 구분자를 따옴표로 안 감싸면 본문의 백틱과 $( )가
  명령으로 실행되고 그 출력으로 바뀝니다. 마크다운의 인라인 코드가 그렇게
  실행돼 문서가 깨졌습니다(2026-09-16 실사고).

대신 이렇게 하십시오
  1) 파일 쓰기 → Write 도구 (글자 그대로 도착합니다)
  2) 히어독을 꼭 쓰면 → 구분자를 따옴표로: <<'EOF'

걸린 부분: {found}
"""


def unquoted_heredoc_hits(command: str) -> list[tuple[int, str]]:
    """따옴표 없는 히어독 본문 중 백틱·`$(` 가 든 줄을 (줄 번호, 줄) 로 낸다."""
    lines = command.splitlines()
    hits: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        ops = list(HEREDOC.finditer(lines[i]))
        i += 1
        for op in ops:                       # 한 줄에 둘이면 본문도 차례로 온다
            start = i
            while i < len(lines) and lines[i].strip() != op.group("tag"):
                i += 1
            body = range(start, i)
            i += 1                           # 종결자 줄
            if op.group("q"):
                continue
            hits.extend((n + 1, lines[n]) for n in body if EXECUTES.search(lines[n]))
    return hits

REASON = """BLOCKED [block-backslash-in-shell]: Bash 명령에 겹 역슬래시가 있습니다.

무엇이 일어나나 — Bash 도구로 넘긴 명령은 셸에 닿기 전에 역슬래시가 한 겹
  벗겨집니다. `\\\\` 로 적은 것이 `\\` 로 도착합니다(실측 2026-08-27).
  정규식이 깨지거나, 더 나쁘게는 **조용히 다른 문자열을 치환합니다.**

히어독만의 문제가 아닙니다 — `-c` 로 넘겨도 같습니다.

대신 이렇게 하십시오
  1) 코드 수정 → Edit 도구
  2) 스크립트를 돌려야 하면 → Write 도구로 파일에 쓴 뒤 그 파일을 실행
     (Write 경로는 역슬래시가 그대로 도착합니다)
  3) 정말 셸에서 역슬래시를 다뤄야 하면 → PowerShell 도구의 here-string

걸린 부분: {found}
"""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = (data.get("tool_input") or {}).get("command", "")
    if not command:
        sys.exit(0)

    if DOUBLE_BACKSLASH.search(command):
        # 어디서 걸렸는지 보여 준다 — 안 보여 주면 무엇을 고칠지 모른다
        lines = [
            f"    {number}: {line.strip()[:88]}"
            for number, line in enumerate(command.splitlines(), 1)
            if DOUBLE_BACKSLASH.search(line)
        ]
        print(REASON.format(found="\n" + "\n".join(lines[:5])), file=sys.stderr)
        sys.exit(2)

    hits = unquoted_heredoc_hits(command)
    if hits:
        lines = [f"    {number}: {line.strip()[:88]}" for number, line in hits]
        print(HEREDOC_REASON.format(found="\n" + "\n".join(lines[:5])), file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
