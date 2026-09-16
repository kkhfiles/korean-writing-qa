"""PreToolUse 훅 — **공개 저장소로 푸시하기 직전에** 나가면 안 되는 것을 본다.

    통과 = 종료 코드 0 · 막음 = 종료 코드 2(stderr 가 사유로 보인다)

**왜 이 훅이 있나.** 2026-09-15 에 공개 저장소로 동료 실명 554종이 빈도수까지 붙어
엿새 동안 나가 있었다. 사람이 훑었고 전용 검사기도 있었는데 나갔다 — **부르는 것을
사람이 기억해야 하는 구조라서**다. 전역 규칙이 「같은 함정에 두 번 걸리면 글이 아니라
기계로 옮긴다」라 여기로 옮긴다.

**개인 저장소는 안 막는다**(2026-09-16 사용자 결정). 푸시는 기본으로 하고 **공개
저장소에만 게이트**를 둔다. 공개 여부는 `check_publish_safety.published()` 가 판정한다
— 원격이 없으면 안 나가는 것이고, 물어보지 못했으면 **나가는 것으로 친다**(모르면 막는
쪽 · 전역 규칙의 「막되 푸는 길을 함께」).

**어느 저장소를 보나.** 명령에 `git -C <경로> push` 가 있으면 그 경로, 없으면 세션
cwd 의 저장소다. 처음에는 cwd 만 봐서 `-C` 로 다른 저장소를 밀 때 엉뚱한 저장소를
검사했다(2026-09-16 실측 — slack-bot 을 밀려는데 claude-workflow 를 봤다).

**검사기는 실제로 돌릴 파일에서 불러온다.** 처음에는 `hooks/` 옆 `scripts/` 에서
import 했는데, 설치본(`~/.claude/hooks/`) 옆에는 `scripts/` 가 없어 **모든 저장소를
「공개 여부를 못 물었다」로 막았다**(2026-09-16 실측 — 개인 저장소 푸시가 전부 막혀
오늘 정한 「푸시는 기본」과 정반대가 됐다). 판정 함수와 검사 실행이 같은 파일이어야
한쪽만 낡지 않는다.

**따옴표 안은 안 본다.** `grep "git push 기본값"`·`git commit -m "push 뒤에"` 는
푸시가 아니다 — 문자열 안 `git push` 에 두 번 걸려 검사기를 헛돌렸다(2026-09-16).
대신 `bash -c "git push"` 는 못 잡는다. **이 훅은 잊는 것을 막지 우회를 막지 않는다**
— 우회는 `KOREAN_PUSH_FORCE` 로 하되 기록이 남게 한다.

**스크립트에서도 부른다.** `--repo <경로>` 로 부르면 stdin 없이 같은 판정을 한다.
`sync.sh` 처럼 스크립트 안에서 `git push` 하는 길은 훅이 못 보므로 스크립트가 직접
부른다.

**이력은 안 본다.** `--history` 는 66초라 푸시마다 돌릴 수 없고, 이미 이력에 있는 것은
푸시를 막아도 안 지워진다(이력 재작성이 따로 필요하다). 지금 나가는 파일만 본다.

**푸는 길** — `KOREAN_PUSH_FORCE=1` 을 붙여 부른다. 막힌 사유와 함께 화면에 남는다.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ⛔ 새 TextIOWrapper 로 갈아끼우지 않는다 — 한 프로세스에서 이 파일을 두 번 불러오면
#    버려진 옛 wrapper 가 같은 버퍼를 닫아 stderr 가 죽는다(시험에서 실측).
try:
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

#: `git push` 만 본다. `--force` 는 `block-dangerous.py` 가 이미 막는다.
#   `&&` 로 이어 붙인 것도 잡으려고 줄 어디에 있든 찾는다.
#   ⛔ **값을 받는 옵션까지 넘겨야 한다** — 처음에 `(?:-[^\s]+\s+)*` 로 적었더니
#      `git -C <경로> push` 를 못 잡았다(시험이 잡음). `-C` 다음의 경로가 옵션이
#      아니라 값이라 그 자리에서 멈춘다.
#   ⛔ 「git 뒤 아무거나 + push」로 넓히지 않는다 — `git log --grep push` 가 걸린다.
#   1군 = push 앞의 옵션 토막. `-C <경로>` 를 여기서 꺼낸다.
PUSH = re.compile(r"(?:^|[\s;&|(])git\s+((?:-\S+\s+\S+\s+|--?\S+\s+)*)push\b")

#: 따옴표로 감싼 토막. 길이를 지키며 가려서 위치가 안 밀리게 한다.
QUOTED = re.compile(r'"[^"]*"|\'[^\']*\'')

#: 옵션 토막 안의 `-C <경로>` — 경로는 따옴표로 감쌌을 수 있다.
C_OPT = re.compile(r"(?:^|\s)-C\s+(?:\"([^\"]*)\"|'([^']*)'|(\S+))")

HERE = Path(__file__).resolve().parent
ESCAPE = "KOREAN_PUSH_FORCE"


def mask_quoted(command: str) -> str:
    """따옴표 안을 같은 길이의 `x` 로 가린다 — 정규식이 그 안을 못 보게."""
    return QUOTED.sub(lambda m: m.group()[0] + "x" * (len(m.group()) - 2) + m.group()[-1],
                      command)


def push_target(command: str) -> str | None:
    """푸시가 아니면 None · 푸시면 `-C` 경로(없으면 빈 문자열)."""
    m = PUSH.search(mask_quoted(command))
    if not m:
        return None
    opts = command[m.start(1):m.end(1)]        # 원문에서 꺼내야 따옴표 친 경로가 산다
    c = C_OPT.search(opts)
    if not c:
        return ""
    return next(g for g in c.groups() if g is not None)


def _checker() -> Path | None:
    """설치본과 저장소본 어느 쪽에서 불려도 검사기를 찾는다.

    순서 — 지정한 것 · 훅 옆 `scripts/`(저장소 배치) · `~/.claude/assets/`(설치 배치).
    """
    for cand in (Path(os.environ.get("KOREAN_QA_PUBLISH_CHECK", "")),
                 HERE.parent / "scripts" / "check_publish_safety.py",
                 Path.home() / ".claude" / "assets" / "check_publish_safety.py"):
        if str(cand) not in ("", ".") and cand.is_file():
            return cand
    return None


def _repo_root(cwd: str, c_path: str = "") -> Path | None:
    """`-C` 경로가 있으면 그것을(상대면 cwd 기준), 없으면 cwd 의 저장소 루트."""
    base = Path(cwd) if cwd else Path.cwd()
    if c_path:
        base = Path(c_path) if Path(c_path).is_absolute() else base / c_path
    if not base.is_dir():
        return None
    got = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(base),
                         capture_output=True, text=True, encoding="utf-8")
    return Path(got.stdout.strip()) if got.returncode == 0 and got.stdout.strip() else None


def _is_public(repo: Path) -> tuple[bool, str]:
    """검사기의 판정을 그대로 쓴다 — 판정이 두 곳에 있으면 한쪽이 낡는다.

    **실제로 돌릴 검사기 파일에서** 불러온다. `sys.path` 로 `scripts/` 를 찾으면
    설치본에는 그 디렉터리가 없어 매번 「못 물었다」가 된다.
    """
    checker = _checker()
    if checker is None:
        return True, "검사기를 못 찾았다 — 나가는 것으로 본다"
    try:
        spec = importlib.util.spec_from_file_location("check_publish_safety", checker)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod.published(repo)
    except Exception as exc:                            # noqa: BLE001
        # 못 물었으면 **나가는 것으로 친다** — 모르면 막는 쪽이다.
        return True, f"검사기를 불러오지 못했다({type(exc).__name__}: {exc}) — 나가는 것으로 본다"


def gate(repo: Path) -> tuple[int, str]:
    """(종료 코드, 사유). 0 이면 보내도 된다."""
    goes_out, why = _is_public(repo)
    if not goes_out:
        return 0, ""                                    # 개인 저장소는 그냥 보낸다

    if os.environ.get(ESCAPE) == "1":
        return 0, f"⚠️ 공개 저장소 푸시 게이트를 넘겼습니다({ESCAPE}=1) — {why}"

    checker = _checker()
    if checker is None:
        return 2, ("⛔ 공개 저장소인데 발행 안전 검사기를 못 찾았습니다.\n"
                   f"   {why}\n"
                   "   `python install.py` 로 설치하거나 `KOREAN_QA_PUBLISH_CHECK` 로 지정하십시오.\n"
                   f"   정말 보내야 하면 `{ESCAPE}=1` 을 붙이십시오.")

    done = subprocess.run([sys.executable, "-X", "utf8", str(checker),
                           "--repo", str(repo)],
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode == 0:
        return 0, ""

    return 2, (f"⛔ 공개 저장소라 푸시를 멈췄습니다 — {why}\n\n"
               f"{(done.stdout or '').strip()[-2400:]}\n\n"
               "   고치고 다시 커밋하십시오. 이미 이력에 있는 것은 푸시를 막아도 안 지워집니다 —\n"
               "   `--history` 로 확인하고 필요하면 이력 재작성까지 가야 합니다.\n"
               f"   정말 보내야 하면 `{ESCAPE}=1` 을 붙이십시오.")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    # 스크립트 호출 — `--repo <경로>` 로 stdin 없이 같은 판정을 한다.
    if argv and argv[0] == "--repo":
        if len(argv) < 2:
            print("사용법: public-push-gate.py --repo <저장소 경로>", file=sys.stderr)
            return 2
        repo = _repo_root(argv[1])
        if repo is None:
            return 0                                    # 저장소가 아니면 볼 것이 없다
        rc, msg = gate(repo)
        if msg:
            print(msg, file=sys.stderr)
        return rc

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    c_path = push_target(command)
    if c_path is None:
        return 0

    repo = _repo_root(data.get("cwd") or "", c_path)
    if repo is None:
        return 0

    rc, msg = gate(repo)
    if msg:
        print(msg, file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
