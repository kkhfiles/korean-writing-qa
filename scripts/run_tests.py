"""시험을 돌려 **전체 출력은 로그 파일에**, 화면에는 실패한 시험 이름과 합계만 낸다.

    python -X utf8 scripts/run_tests.py                 # tests/ 전부
    python -X utf8 scripts/run_tests.py tests.test_x    # 모듈 · 클래스 · 시험 이름을 주면 그것만

**왜 있나.** 전체 시험은 9분 남짓 걸리고 출력이 길다. 화면 길이를 줄이려고 `| tail` 로
자르면 맨 끝 합계만 남고 **어느 시험이 실패했는지가 사라져** 9분을 다시 돌렸다
(2026-10-30). 파이프는 종료 코드도 가린다. 그래서 출력은 통째로 파일에 두고 요약만 낸다.

**종료 코드는 unittest 의 것 그대로** — 실패가 있으면 0 이 아니다.
**로그 자리** — 시스템 임시 폴더의 `korean-qa-tests/`(저장소 밖이라 커밋될 일이 없다).
시작할 때 그 경로를 먼저 찍는다 — 중간에 끊겨도 어디까지 돌았는지 볼 수 있다.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = Path(tempfile.gettempdir()) / "korean-qa-tests"

#: unittest 가 실패마다 내는 머리 줄 · 끝의 합계 줄
FAILED_LINE = re.compile(r"^(FAIL|ERROR): (.+)$")
RAN_LINE = re.compile(r"^Ran \d+ tests? in .+$")
RESULT_LINE = re.compile(r"^(OK|FAILED)\b.*$")


def summarize(text: str) -> list[str]:
    """로그에서 실패한 시험 이름 · 실행 건수 · 결과 줄만 뽑는다(같은 이름은 한 번)."""
    failed = list(dict.fromkeys(f"{m.group(1)}: {m.group(2)}"
                                for m in map(FAILED_LINE.match, text.splitlines()) if m))
    ran = [l for l in text.splitlines() if RAN_LINE.match(l)]
    result = [l for l in text.splitlines() if RESULT_LINE.match(l)]
    return failed + ran[-1:] + result[-1:]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / time.strftime("tests-%Y%m%d-%H%M%S.log")
    cmd = [sys.executable, "-X", "utf8", "-m", "unittest"]
    cmd += argv if argv else ["discover", "-s", "tests"]
    print(f"로그 — {log.as_posix()}", flush=True)
    with log.open("w", encoding="utf-8", errors="replace") as f:
        done = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
    lines = summarize(log.read_text(encoding="utf-8", errors="replace"))
    if not lines:
        lines = ["⚠️ 합계 줄을 못 찾았습니다 — 시험을 모으다 멈췄을 수 있습니다. 로그를 엽니다."]
    print("\n".join(lines))
    return done.returncode


if __name__ == "__main__":
    sys.exit(main())
