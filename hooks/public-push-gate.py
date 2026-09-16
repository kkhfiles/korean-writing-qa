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

**이력은 안 본다.** `--history` 는 66초라 푸시마다 돌릴 수 없고, 이미 이력에 있는 것은
푸시를 막아도 안 지워진다(이력 재작성이 따로 필요하다). 지금 나가는 파일만 3초에 본다.

**푸는 길** — `KOREAN_PUSH_FORCE=1` 을 붙여 부른다. 막힌 사유와 함께 화면에 남는다.
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

#: `git push` 만 본다. `--force` 는 `block-dangerous.py` 가 이미 막는다.
#   `&&` 로 이어 붙인 것도 잡으려고 줄 어디에 있든 찾는다.
#   ⛔ **값을 받는 옵션까지 넘겨야 한다** — 처음에 `(?:-[^\s]+\s+)*` 로 적었더니
#      `git -C <경로> push` 를 못 잡았다(시험이 잡음). `-C` 다음의 경로가 옵션이
#      아니라 값이라 그 자리에서 멈춘다.
#   ⛔ 「git 뒤 아무거나 + push」로 넓히지 않는다 — `git log --grep push` 가 걸린다.
PUSH = re.compile(r"(?:^|[\s;&|])git\s+(?:-\S+\s+\S+\s+|--?\S+\s+)*push\b")

HERE = Path(__file__).resolve().parent
ESCAPE = "KOREAN_PUSH_FORCE"


def _checker() -> Path | None:
    """설치본과 저장소본 어느 쪽에서 불려도 검사기를 찾는다."""
    for cand in (Path(os.environ.get("KOREAN_QA_PUBLISH_CHECK", "")),
                 Path.home() / ".claude" / "assets" / "check_publish_safety.py",
                 HERE.parent / "scripts" / "check_publish_safety.py"):
        if cand and cand.is_file():
            return cand
    return None


def _repo_root(cwd: str) -> Path | None:
    got = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd or None,
                         capture_output=True, text=True, encoding="utf-8")
    return Path(got.stdout.strip()) if got.returncode == 0 and got.stdout.strip() else None


def _is_public(repo: Path) -> tuple[bool, str]:
    """검사기의 판정을 그대로 쓴다 — 판정이 두 곳에 있으면 한쪽이 낡는다."""
    sys.path.insert(0, str(HERE.parent / "scripts"))
    try:
        import check_publish_safety as cps          # noqa: PLC0415
        return cps.published(repo)
    except Exception:                               # noqa: BLE001
        # 못 물었으면 **나가는 것으로 친다** — 모르면 막는 쪽이다.
        return True, "공개 여부를 못 물었다 — 나가는 것으로 본다"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    if not PUSH.search(command):
        return 0

    repo = _repo_root(data.get("cwd") or "")
    if repo is None:
        return 0

    goes_out, why = _is_public(repo)
    if not goes_out:
        return 0                                    # 개인 저장소는 그냥 보낸다

    if os.environ.get(ESCAPE) == "1":
        print(f"⚠️ 공개 저장소 푸시 게이트를 넘겼습니다({ESCAPE}=1) — {why}",
              file=sys.stderr)
        return 0

    checker = _checker()
    if checker is None:
        print("⛔ 공개 저장소인데 발행 안전 검사기를 못 찾았습니다.\n"
              f"   {why}\n"
              "   `python install.py` 로 설치하거나 `KOREAN_QA_PUBLISH_CHECK` 로 지정하십시오.\n"
              f"   정말 보내야 하면 `{ESCAPE}=1` 을 붙이십시오.", file=sys.stderr)
        return 2

    done = subprocess.run([sys.executable, "-X", "utf8", str(checker),
                           "--repo", str(repo)],
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode == 0:
        return 0

    print(f"⛔ 공개 저장소라 푸시를 멈췄습니다 — {why}\n\n"
          f"{(done.stdout or '').strip()[-2400:]}\n\n"
          "   고치고 다시 커밋하십시오. 이미 이력에 있는 것은 푸시를 막아도 안 지워집니다 —\n"
          "   `--history` 로 확인하고 필요하면 이력 재작성까지 가야 합니다.\n"
          f"   정말 보내야 하면 `{ESCAPE}=1` 을 붙이십시오.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
