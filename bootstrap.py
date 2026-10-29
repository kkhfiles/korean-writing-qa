#!/usr/bin/env python
"""처음 쓰는 PC 에 한 번에 설치한다 — 확인, 설치, 검증, 요약을 명령 하나로.

    python bootstrap.py           # 형태소 판정 모듈 설치를 빼려면 --no-pip

코딩 에이전트에게 「설치해 줘」를 맡기면 확인, 설치, 검증 명령마다 실행 승인을 묻는다. 판단이
필요 없는 일은 이 파일 하나로 묶어 승인을 한 번으로 줄인다. 에이전트에게 남는 일은 Python 이
없을 때 사용자 동의를 받아 설치하는 것, 이 파일을 실행하는 것, 마지막 요약을 전하는 것이다.

이름이 `setup.py` 가 아닌 까닭 — `pip install .` 이 그 이름을 빌드 스크립트로 실행한다.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

REPO = Path(__file__).resolve().parent
MIN_PYTHON = (3, 11)
CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME") or (Path.home() / ".claude"))
CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
#: 형태소 판정 — 없어도 검사는 돌지만 몇 갈래를 글자만으로 본다(requirements.txt 와 같은 범위)
MORPH = "kiwipiepy>=0.20,<0.24"


def run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def last_line(text: str) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def main() -> int:
    py = sys.executable
    print(f"Python  {sys.version.split()[0]}  ({Path(py).as_posix()})")
    if sys.version_info < MIN_PYTHON:
        print(f"❌ Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 이상이 필요합니다 — 설치 뒤 그 Python 으로 다시 실행하세요.")
        return 2

    claude = CLAUDE_HOME.is_dir() or shutil.which("claude") is not None
    # Codex 는 한 번 실행해 설정 폴더가 생겨야 스킬과 훅을 걸 수 있다(install.py --codex)
    codex = CODEX_HOME.is_dir()
    targets = [name for name, ok in (("Claude Code", claude), ("Codex", codex)) if ok]
    if not targets:
        print("❌ Claude Code 와 Codex 를 찾지 못했습니다 — 둘 중 하나를 한 번 실행한 뒤 다시 실행하세요.")
        return 2
    print(f"설치 대상  {', '.join(targets)}")

    problems: list[str] = []

    # 형태소 판정 모듈 — 실패해도 설치는 계속한다(검사기가 그 사실을 출력에 적는다)
    got = None if "--no-pip" in sys.argv else run(
        [py, "-m", "pip", "install", "--disable-pip-version-check", "-q", MORPH])
    if got is None:
        print("건너뜀  형태소 판정 모듈 설치(--no-pip)")
    elif got.returncode == 0:
        print("✅ 형태소 판정 모듈(kiwipiepy) 준비")
    else:
        problems.append("형태소 판정 모듈을 설치하지 못했습니다 — 검사는 되지만 몇 갈래를 글자만으로 봅니다"
                        f" ({last_line(got.stderr or got.stdout)})")
        print(f"⚠️ {problems[-1]}")

    if claude:
        CLAUDE_HOME.mkdir(parents=True, exist_ok=True)
        settings = CLAUDE_HOME / "settings.json"
        if not settings.is_file():
            # 훅을 등록할 설정 파일 — Claude Code 는 처음에 이 파일을 안 만들 때가 있다
            settings.write_text("{}\n", encoding="utf-8")
    args = [py, "-X", "utf8", "install.py"] + (["--hooks"] if claude else []) + (["--codex"] if codex else [])
    got = run(args)
    print(got.stdout.rstrip())
    if got.returncode != 0:
        print(f"❌ 설치가 실패했습니다\n{got.stderr.rstrip()}")
        return 1

    # 검증 — 시료 두 개, 설치본 대조, 스킬이 저장소 도구를 찾는지
    checks = []
    clean = run([py, "-X", "utf8", "assets/doc-style-check.py", "tests/fixtures/paired/exempt-fixture.md"])
    checks.append(("정상 시료에 지적 없음", "오류 0 · 주의 0" in clean.stdout))
    dirty = run([py, "-X", "utf8", "assets/doc-style-check.py", "tests/fixtures/paired/violation-fixture.md"])
    checks.append(("위반 시료에서 오류를 잡음", "오류 0" not in dirty.stdout and "오류 " in dirty.stdout))
    same = run([py, "-X", "utf8", "install.py", "--check"])
    checks.append(("설치본이 원본과 같음", same.returncode == 0))
    if claude:
        runner = CLAUDE_HOME / "assets" / "korean_qa_run.py"
        tool = subprocess.run([py, "-X", "utf8", str(runner), "rare_words", "--help"], cwd=Path.home(),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        checks.append(("스킬이 저장소 도구를 찾음", tool.returncode == 0))
    for label, ok in checks:
        print(f"{'✅' if ok else '❌'} {label}")
    failed = [label for label, ok in checks if not ok]

    print("\n── 요약 ──")
    print(f"- 설치한 곳: {', '.join(targets)}")
    print("- 쓰는 법: 문서를 쓰면 자동으로 검사합니다. 직접 부르려면 「이 문서 한글 검사해 줘」라고 말합니다.")
    print(f"- 명령줄 검사: python \"{(REPO / 'assets' / 'doc-style-check.py').as_posix()}\" <파일>")
    print("- 지우는 법: 이 폴더에서 python install.py --uninstall" + (" --codex" if codex else ""))
    if codex:
        print("- Codex: 다시 열면 새 훅을 승인할지 묻습니다. 승인해야 자동 검사가 동작합니다.")
    print("- 이 폴더를 옮기거나 지우면 스킬이 도구를 못 찾습니다. 옮겼다면 새 위치에서 이 파일을 다시 실행합니다.")
    for note in problems:
        print(f"- 참고: {note}")
    if failed:
        print(f"- ❌ 검증 실패: {', '.join(failed)}")
        return 1
    print("- 결과: 설치와 검증 모두 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
