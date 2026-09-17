"""검사기·스킬·훅이 어디 있는지 한 곳에서 정한다.

**정본은 이 저장소다.** 예전에는 `~/.claude/` 에 있는 것이 정본이고 이 저장소는
그것을 불러다 썼다. 그래서 저장소만 받은 사람은 아무것도 못 돌렸다.

이제 방향이 반대다.

| 무엇 | 정본 | 설치본 |
|---|---|---|
| 검사기 | `assets/doc-style-check.py` | `~/.claude/assets/` |
| 스킬 | `skills/` 아래 전부 | `~/.claude/skills/` |
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

#: 스킬 전부가 사는 곳. 설치는 이 아래를 통째로 옮기므로 스킬을 새로 만들면
#: `install.py` 를 안 고쳐도 따라온다 — 고쳐야 하는 구조는 잊는다.
SKILLS = REPO / "skills"

#: 서브에이전트 정의. 머리말이 `model` · `effort` · `omitClaudeMd` 를 받는다
#: — 마지막 것이 프로젝트 `CLAUDE.md` 적재를 막아 판정 교란을 없앤다
#: (2026-09-16 실측 · `docs/ai-filter-experiment-20260916.md`).
AGENTS = REPO / "agents"

HOOKS = REPO / "hooks"


#: 설정 저장소 경로를 적어 두는 자리 — 값은 각자 기계에, 이름만 저장소에.
CONFIG_REPO_FILE = REPO / "data" / "catalog" / "local-config-repo.txt"


def config_repo() -> Path | None:
    """작성자의 설정 저장소 — 없으면 `None`.

    **왜 이 함수가 있나.** 2026-09-07 발행 정리가 절대 경로를 `<설정 저장소>`
    라는 글자로 가렸다. 가리는 것 자체는 맞았지만 **읽어 올 자리를 안 만들어**
    그 경로를 쓰던 파일 다섯이 통째로 망가졌다. 그중 하나는 시험이었고,
    실패가 아니라 **건너뛰기**를 골라 열흘 동안 아무 데도 안 나타났다.

    찾는 곳 둘 — `KOREAN_QA_CONFIG_REPO` 환경 변수 · 저장소 밖 쪽지 파일
    (`data/catalog/local-config-repo.txt` · `.gitignore` 대상).

    **없으면 `None` 을 낸다.** 부르는 쪽이 그 사실을 **소리 내어** 다뤄야 한다 —
    조용히 건너뛰면 그 순간부터 아무도 안 본다.
    """
    pinned = os.environ.get("KOREAN_QA_CONFIG_REPO", "").strip()
    if pinned:
        return Path(pinned)
    try:
        text = CONFIG_REPO_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return Path(line)
    return None


def config_path(*parts: str) -> Path | None:
    """설정 저장소 안의 경로 — 저장소를 못 찾으면 `None`."""
    root = config_repo()
    return root.joinpath(*parts) if root else None


#: 설정 저장소를 못 찾았을 때 사람에게 내는 말 — 부르는 쪽이 그대로 쓴다.
NO_CONFIG_REPO = (
    "설정 저장소를 못 찾았습니다 — 이 검사는 작성자 기계에서만 돕니다.\n"
    "   돌리려면 `KOREAN_QA_CONFIG_REPO` 를 지정하거나 "
    "`data/catalog/local-config-repo.txt` 에 경로 한 줄을 적으십시오.")


def hook(name: str) -> Path:
    """훅 파일 하나를 가리킨다 — 예: `hook("doc-style-gate.py")`."""
    return HOOKS / name


def installed(*parts: str) -> Path:
    """설치된 환경 안의 경로 — 그 기계에만 있는 것을 볼 때만 쓴다."""
    return INSTALLED.joinpath(*parts)
