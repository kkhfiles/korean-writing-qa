#!/usr/bin/env python
"""설치된 스킬이 저장소의 도구를 부르는 입구 — 저장소를 어디에 풀었든 같은 명령으로 부른다.

    python -X utf8 "$HOME/.claude/assets/korean_qa_run.py" rare_words <대상>

`install.py` 가 `~/.claude/` 로 옮긴다. 스킬 문서가 `P:/github/…` 같은 작성자 PC 경로를
적어 두면 받은 사람 PC 에서는 설치가 성공하고 첫 사용에서 깨졌다(2026-10-29 확인, 11곳).

저장소 위치는 이 차례로 찾는다.
1. 환경 변수 `KOREAN_WRITING_QA_HOME`
2. 이 파일이 저장소 `scripts/` 안에 있으면 그 저장소
3. `install.py` 가 설치할 때 적은 `~/.claude/data/korean-writing-qa-home.txt`
"""

from __future__ import annotations

import os
import re
import runpy
import sys
from pathlib import Path

POINTER_NAME = "korean-writing-qa-home.txt"


def pointer_file() -> Path:
    home = os.environ.get("CLAUDE_HOME") or (Path.home() / ".claude")
    return Path(home) / "data" / POINTER_NAME


def qa_root() -> Path | None:
    env = os.environ.get("KOREAN_WRITING_QA_HOME")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parents[1]
    if (here / "install.py").is_file():
        return here
    pointer = pointer_file()
    if pointer.is_file():
        text = pointer.read_text(encoding="utf-8").strip()
        if text:
            return Path(text)
    return None


def main(argv: list[str]) -> int:
    if not argv or not re.fullmatch(r"[a-z0-9_]+", argv[0]):
        print("쓰는 법: korean_qa_run.py <도구 이름> [인자…]  예: rare_words 문서.md", file=sys.stderr)
        return 2
    root = qa_root()
    if root is None:
        print("저장소 위치를 모릅니다. 저장소 폴더에서 `python install.py` 를 한 번 실행하세요.",
              file=sys.stderr)
        return 2
    target = root / "scripts" / f"{argv[0]}.py"
    if not target.is_file():
        print(f"도구가 없습니다: {target.as_posix()}", file=sys.stderr)
        return 2
    sys.argv = [str(target), *argv[1:]]
    sys.path.insert(0, str(target.parent))
    try:
        runpy.run_path(str(target), run_name="__main__")
    except SystemExit as stop:
        code = stop.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
