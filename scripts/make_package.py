#!/usr/bin/env python
"""받은 사람이 코딩 에이전트에게 「설치해 줘」만 하면 되는 압축 꾸러미를 만든다.

    python -X utf8 scripts/make_package.py --out <저장소 밖 경로>.zip [--rev HEAD]

- **커밋된 판에서 만든다** — 작업 중인 파일이나 저장소 밖 목록(`local-*`)이 섞이지 않는다
- **빼는 것** — 실험 기록(`runs/`), 지난 문서(`docs/archived/`)와 연구 문서, CI 설정, 이 저장소의 개발 규칙
- **바꿔 넣는 것** — `AGENTS.md` 는 설치 안내(`scripts/package_agents.md`), `CLAUDE.md` 는 `@AGENTS.md` 한 줄.
  Claude Code 와 Codex 모두 폴더를 열자마자 안내를 읽는다
- **나가기 전 검사** — `check_publish_safety.py` 로 사람 이름, 고객사, 사내 주소, 열쇠를 본다. 오류가 있으면 zip 을 안 만든다.
  작성자를 드러낼 수 있는 표기(개인 도메인 등)는 지우지 않고 목록으로만 알린다 — 익명 처리 방식은 사람이 정한다
"""

from __future__ import annotations

import argparse
import io
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

REPO = Path(__file__).resolve().parents[1]
NAME = "korean-writing-qa"
#: 꾸러미에서 빼는 경로(앞부분 일치)
EXCLUDE = (
    "runs/", "docs/archived/", ".github/", "AGENTS.md", "CLAUDE.md", "korean-qa.toml", ".gitignore",
    "scripts/package_agents.md",
)
#: 남기는 문서 — 쓰는 사람이 보는 것만. 나머지 `docs/` 는 연구 기록이다
KEEP_DOCS = {"docs/user-guide.md", "docs/showcase.html", "docs/architecture.md", "docs/highlights.md"}
#: 작성자를 드러낼 수 있는 표기 — 지우지 않고 알리기만 한다
IDENTIFYING = re.compile(r"dispatchflow\.cc|github\.com/[A-Za-z0-9-]+/korean-writing-qa", re.I)


def wanted(path: str) -> bool:
    if any(path == e or path.startswith(e) for e in EXCLUDE):
        return False
    if path.startswith("docs/") and path not in KEEP_DOCS:
        return False
    return True


def export(rev: str, dest: Path) -> list[str]:
    tar = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", rev],
                         capture_output=True, check=True).stdout
    kept = []
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t.getmembers():
            if m.isfile() and wanted(m.name):
                target = dest / m.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(t.extractfile(m).read())
                kept.append(m.name)
    guide = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:scripts/package_agents.md"],
                           capture_output=True, check=True).stdout
    (dest / "AGENTS.md").write_bytes(guide)
    (dest / "CLAUDE.md").write_bytes(b"@AGENTS.md\n")
    return kept


def safety_tool() -> Path:
    """신원 목록을 읽을 수 있는 발행 검사기 — 목록은 저장소 밖(gitignore)이라 작업 트리에는 없다.

    검사기는 자기 위치 기준 `data/catalog/` 의 목록을 읽는다. 작업 트리에 목록이 없으면
    설치본(`~/.claude/assets/`, 목록은 `~/.claude/data/catalog/`)을 쓴다.
    """
    name = "local-identity-denylist.txt"
    if (REPO / "data" / "catalog" / name).is_file():
        return REPO / "scripts" / "check_publish_safety.py"
    sys.path.insert(0, str(REPO))
    import repo_paths  # noqa: PLC0415
    installed = repo_paths.installed("assets", "check_publish_safety.py")
    if installed.is_file() and repo_paths.installed("data", "catalog", name).is_file():
        return installed
    return REPO / "scripts" / "check_publish_safety.py"


def safety(dest: Path) -> int:
    """사본을 임시 저장소로 만들어 발행 검사를 돌린다 — 검사기는 추적 파일을 본다."""
    git = ["git", "-C", str(dest), "-c", "core.autocrlf=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    done = subprocess.run([sys.executable, "-X", "utf8", str(safety_tool()),
                           "--repo", str(dest)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    print(done.stdout.rstrip())
    shutil.rmtree(dest / ".git", onerror=lambda f, p, e: (Path(p).chmod(0o700), f(p)))
    return done.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="만들 zip 경로(저장소 밖)")
    ap.add_argument("--rev", default="HEAD", help="꾸러미로 만들 커밋")
    args = ap.parse_args()
    out = args.out.resolve()
    if REPO in out.parents:
        ap.error("zip 은 저장소 밖에 만든다 — 안에 두면 다음 꾸러미에 딸려 들어간다")

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / NAME
        dest.mkdir()
        kept = export(args.rev, dest)
        print(f"담은 파일 {len(kept) + 2}개 (설치 안내 AGENTS.md, CLAUDE.md 포함)")
        rc = safety(dest)
        hits = []
        for f in sorted(dest.rglob("*")):
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    if IDENTIFYING.search(line):
                        hits.append(f"{f.relative_to(dest).as_posix()}:{n}")
        if hits:
            print(f"\n⚠️ 작성자를 드러낼 수 있는 표기 {len(hits)}줄 — 익명으로 낼지 정한 뒤 처리")
            for h in hits[:20]:
                print(f"  {h}")
            if len(hits) > 20:
                print(f"  … 외 {len(hits) - 20}줄")
        if rc not in (0, 1):
            print("\n❌ 발행 검사가 막았습니다 — zip 을 만들지 않습니다")
            return rc
        out.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(dest.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(dest.parent).as_posix())
    print(f"\n만든 꾸러미 {out.as_posix()} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
