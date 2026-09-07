#!/usr/bin/env python
"""배포된 스킬 검사기를 저장소에서 불러온다. 탐지 논리의 정본은 스킬이다.

**왜 다시 구현하지 않나.** 같은 정규식을 두 벌 두면 한쪽만 고쳐진다. 실제로
갈라졌다 — 회귀시험은 저장소 사본을 지키는데 사용자에게 도는 것은 스킬 사본이라,
스킬 쪽이 망가져도 시험은 초록으로 남는다. 게이트에서 가장 나쁜 실패다.

**못 찾으면 바로 실패한다.** 조용히 저장소 사본으로 돌아가면 다시 갈라지고,
그때는 시험이 통과하므로 아무도 모른다.

다른 위치의 스킬을 쓰려면 `KOREAN_WRITING_SKILL_HOME` 에 그 디렉터리를 지정한다.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import repo_paths  # noqa: E402

ENV_HOME = "KOREAN_WRITING_SKILL_HOME"
DEFAULT_HOME = repo_paths.SKILL
_loaded: dict[str, ModuleType] = {}


def skill_home() -> Path:
    configured = os.environ.get(ENV_HOME)
    return Path(configured) if configured else DEFAULT_HOME


def load(module_name: str) -> ModuleType:
    """스킬의 `scripts/<module_name>.py` 를 불러온다."""
    if module_name in _loaded:
        return _loaded[module_name]

    home = skill_home()
    target = home / "scripts" / f"{module_name}.py"
    if not target.is_file():
        raise RuntimeError(
            f"배포된 스킬 검사기를 찾지 못했습니다: {target}\n"
            f"탐지 논리의 정본은 스킬입니다. 다른 위치라면 {ENV_HOME} 로 지정하십시오."
        )

    scripts_dir = str(home / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)

    spec = importlib.util.spec_from_file_location(f"deployed_{module_name}", target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"스킬 검사기를 불러오지 못했습니다: {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _loaded[module_name] = module
    return module
