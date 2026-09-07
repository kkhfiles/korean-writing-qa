"""검사기·스킬·훅이 어디 있는지 한 곳에서 정한다.

**정본은 이 저장소다.** 예전에는 `~/.claude/` 에 있는 것이 정본이고 이 저장소는
그것을 불러다 썼다. 그래서 저장소만 받은 사람은 아무것도 못 돌렸다.

이제 방향이 반대다.

| 무엇 | 정본 | 설치본 |
|---|---|---|
| 검사기 | `assets/doc-style-check.py` | `~/.claude/assets/` |
| 스킬 | `skills/finalize-korean-document/` | `~/.claude/skills/` |
| 훅 | `hooks/*.py` | `~/.claude/hooks/` |

`python install.py` 가 정본을 설치본으로 복사한다. 둘이 어긋나면
`tests/test_installed_copy_matches.py` 가 깨진다.

**설치된 환경만 볼 수 있는 것** — 대화 기록(`~/.claude/projects/`)과
설정(`~/.claude/settings.json`)은 그 기계에만 있다. 이 둘은 `INSTALLED` 로 본다.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parent

#: 설치된 Claude Code 환경. 다른 곳에 두었으면 `CLAUDE_HOME` 으로 지정한다.
INSTALLED = Path(os.environ.get("CLAUDE_HOME") or (Path.home() / ".claude"))

#: 결정 규칙 검사기 — 구조·서술형·낱말을 글자만 보고 판정한다.
CHECKER = Path(os.environ.get("KOREAN_QA_CHECKER") or (REPO / "assets" / "doc-style-check.py"))

#: 읽는 판단 층 — 문맥을 읽어야 갈리는 것을 맡는다.
SKILL = Path(os.environ.get("KOREAN_QA_SKILL") or (REPO / "skills" / "finalize-korean-document"))

HOOKS = REPO / "hooks"


def hook(name: str) -> Path:
    """훅 파일 하나를 가리킨다 — 예: `hook("doc-style-gate.py")`."""
    return HOOKS / name


def installed(*parts: str) -> Path:
    """설치된 환경 안의 경로 — 그 기계에만 있는 것을 볼 때만 쓴다."""
    return INSTALLED.joinpath(*parts)
