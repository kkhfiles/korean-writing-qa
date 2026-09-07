#!/usr/bin/env python
"""정본을 Claude Code 환경(`~/.claude/`)에 설치한다.

    python install.py              # 검사기와 스킬 설치 · 훅은 안내만
    python install.py --hooks      # settings.json 에 훅까지 등록
    python install.py --check      # 설치본이 정본과 같은지만 확인 (아무것도 안 씀)
    python install.py --dry-run    # 무엇을 쓸지만 보여 줌

**설치 없이 쓰는 길** — 검사기 하나만 쓸 것이면 설치가 필요 없다.

    python assets/doc-style-check.py <파일…|디렉터리>

의존성 없는 파일 하나이고, Python 3.11 이상이면 그대로 돈다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows 기본 인코딩(CP949)으로 나가면 한글이 깨진다. 검사기와 같은 처리를 한다.
sys.stdout.reconfigure(encoding='utf-8')

import repo_paths  # noqa: E402

HOOK_FILES = ["doc-style-gate.py", "block-backslash-in-shell.py", "korean-gate-daily-check.py"]

#: 훅을 어느 사건에 걸 것인가. matcher 는 Claude Code 의 도구 이름 패턴이다.
HOOK_WIRING = [
    ("PreToolUse", "Bash|PowerShell", "block-backslash-in-shell.py"),
    ("PreToolUse", "Artifact|Bash|PowerShell", "doc-style-gate.py"),
    ("PostToolUse", "Edit|Write|MultiEdit", "doc-style-gate.py"),
    ("SessionStart", "", "korean-gate-daily-check.py"),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs() -> list[tuple[Path, Path]]:
    """정본과 설치 위치의 짝을 모두 낸다."""
    out = [(repo_paths.CHECKER, repo_paths.installed("assets", "doc-style-check.py"))]
    for name in HOOK_FILES:
        out.append((repo_paths.hook(name), repo_paths.installed("hooks", name)))
    for src in sorted(repo_paths.SKILL.rglob("*")):
        if src.is_file() and "__pycache__" not in src.parts:
            rel = src.relative_to(repo_paths.SKILL)
            out.append((src, repo_paths.installed("skills", "finalize-korean-document", *rel.parts)))
    return out


def report(rows: list[tuple[str, Path]]) -> None:
    for state, target in rows:
        print(f"  {state}  {target}")


def do_check() -> int:
    same, differ, missing = [], [], []
    for src, dst in pairs():
        if not dst.exists():
            missing.append(dst)
        elif digest(src) == digest(dst):
            same.append(dst)
        else:
            differ.append(dst)
    print(f"같음 {len(same)} · 다름 {len(differ)} · 없음 {len(missing)}")
    report([("다름", p) for p in differ] + [("없음", p) for p in missing])
    if differ or missing:
        print("\n`python install.py` 로 정본을 덮어쓴다.")
        return 1
    print("설치본이 정본과 같다.")
    return 0


def do_install(dry_run: bool) -> int:
    written = 0
    for src, dst in pairs():
        if dst.exists() and digest(src) == digest(dst):
            continue
        print(f"  {'쓸 것' if dry_run else '씀'}  {dst}")
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        written += 1
    print(f"{'쓸 파일' if dry_run else '쓴 파일'} {written}개 · 이미 같아서 건너뛴 것 {len(pairs()) - written}개")
    return 0


def wire_hooks(dry_run: bool) -> int:
    """settings.json 에 훅을 등록한다 — 이미 있으면 건드리지 않는다."""
    settings = repo_paths.installed("settings.json")
    if not settings.is_file():
        print(f"설정 파일이 없다: {settings}")
        print("Claude Code 를 한 번 실행한 뒤 다시 시도한다.")
        return 1

    data = json.loads(settings.read_text(encoding="utf-8"))
    hooks = data.setdefault("hooks", {})
    added = []

    for event, matcher, name in HOOK_WIRING:
        command = f'python "$HOME/.claude/hooks/{name}"'
        groups = hooks.setdefault(event, [])
        group = next((g for g in groups if g.get("matcher", "") == matcher), None)
        if group is None:
            group = {"matcher": matcher, "hooks": []}
            groups.append(group)
        if any(h.get("command") == command for h in group.get("hooks", [])):
            continue
        group.setdefault("hooks", []).append({"type": "command", "command": command})
        added.append(f"{event} · {matcher or '(전체)'} · {name}")

    if not added:
        print("훅 네 개가 이미 등록돼 있다.")
        return 0

    print("등록할 훅:")
    for line in added:
        print(f"  {line}")
    if dry_run:
        return 0

    backup = settings.with_suffix(".json.bak")
    shutil.copy2(settings, backup)
    settings.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"설정을 고쳤다 · 되돌릴 백업 {backup}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="정본을 ~/.claude 에 설치한다")
    ap.add_argument("--check", action="store_true", help="설치본이 정본과 같은지만 확인")
    ap.add_argument("--hooks", action="store_true", help="settings.json 에 훅까지 등록")
    ap.add_argument("--dry-run", action="store_true", help="쓰지 않고 무엇을 쓸지만 보여 줌")
    args = ap.parse_args()

    print(f"정본  {repo_paths.REPO}")
    print(f"설치처 {repo_paths.INSTALLED}\n")

    if args.check:
        return do_check()

    rc = do_install(args.dry_run)
    if args.hooks:
        print()
        rc |= wire_hooks(args.dry_run)
    else:
        print("\n훅은 등록하지 않았다 — 발행 직전 검사와 겹 역슬래시 차단을 걸려면 `--hooks`.")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
