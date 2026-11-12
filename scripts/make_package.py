#!/usr/bin/env python
"""받은 사람이 코딩 에이전트에게 「설치해 줘」만 하면 되는 압축 꾸러미를 만든다.

    python -X utf8 scripts/make_package.py --out <저장소 밖 경로>.zip [--rev HEAD]

- **커밋된 판에서 만든다** — 작업 중인 파일이나 저장소 밖 목록(`local-*`)이 섞이지 않는다
- **빼는 것** — 실험 기록(`runs/`), 지난 문서(`docs/archived/`)와 연구 문서, CI 설정, 이 저장소의 개발 규칙
- **바꿔 넣는 것** — `AGENTS.md` 는 설치 안내(`scripts/package_agents.md`), `CLAUDE.md` 는 `@AGENTS.md` 한 줄.
  Claude Code 와 Codex 모두 폴더를 열자마자 안내를 읽는다
- **나가기 전 검사** — `check_publish_safety.py` 로 사람 이름, 고객사, 사내 주소, 열쇠를 본다. 오류가 있으면 zip 을 안 만든다.
- **익명 처리** — 저장소 주소를 빼고 설치 안내를 이 폴더 기준으로 바꾼다(`ANONYMIZE`). 무늬가 안 맞거나
  작성자를 드러낼 수 있는 표기가 남으면 zip 을 안 만든다
- **작성자 맥락 낱말** — 부서, 행사, 도구, 세션 이름을 저장소 밖 목록(`CONTEXT_LIST`)대로 꾸러미 안에서만
  일반 표현으로 바꾼다. 목록이 없거나 바꾼 뒤에도 원래 말이 남으면 zip 을 안 만든다
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
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
    # 꾸러미를 만드는 도구 자신 — 받는 사람에게 쓸모가 없고 가리는 무늬가 적혀 있다
    "scripts/make_package.py", "tests/test_make_package.py",
)
#: 남기는 문서 — 쓰는 사람이 보는 것만. 나머지 `docs/` 는 연구 기록이다
KEEP_DOCS = {"docs/user-guide.md", "docs/showcase.html", "docs/architecture.md", "docs/highlights.md"}
#: 작성자를 드러낼 수 있는 표기 — 아래 ANONYMIZE 를 거친 뒤에도 남으면 zip 을 안 만든다
IDENTIFYING = re.compile(r"dispatchflow\.cc|github\.com/(?!owner/)[A-Za-z0-9-]+/korean-writing-qa", re.I)
_URL = r"https://github\.com/[A-Za-z0-9-]+/korean-writing-qa[^\s\"')<]*"
#: 꾸러미는 익명 응모에 쓴다 — 저장소 주소를 빼고 설치 안내를 이 폴더 기준으로 바꾼다
#: (2026-11-03 사용자 결정 「꾸러미에서만 지움」, 공개 저장소는 그대로). 무늬는 적은 횟수(없으면 한 번)만큼 맞아야 한다
ANONYMIZE = {
    "docs/showcase.html": [
        (rf'\n *<p class="gorow"><a class="gobtn" href="{_URL}">[^<]*</a></p>', "", 2),
        (rf'<code class="cmd">git clone {_URL}</code>', '<code class="cmd">python bootstrap.py</code>'),
        # 사이트 바닥 메뉴 — 저장소 주소와 작성자의 다른 서비스 링크라 꾸러미에서는 죽은 링크다
        (r'\n *<nav class="fnav">.*?</nav>', ""),
        (r'\n *<span>개발자 [^<]*</span>', ""),
    ],
    # 작성자 사이트 이름 — 꾸러미에서는 일반 표현으로(2026-11-12 시험 빌드에서 막힘)
    "skills/fix-korean-finding/SKILL.md": [
        (r"dispatchflow\.cc 소개 페이지\(`/vermilion/` 등\)와 그 크롤러용 자료", "작성자의 소개 페이지와 그 크롤러용 자료"),
    ],
    "docs/user-guide.md": [
        (r"\*\*이 꾸러미만으로는 발행을 막지 않음\*\* — 이 꾸러미는",
         "**손으로 복사한 설치는 발행을 막지 않음** — 위 세 단계는"),
        (rf"\[korean-writing-qa 저장소\]\({_URL}\)를 내려받아 `python install\.py --hooks`로 설치하면",
         "이 폴더에서 `bootstrap.py`를 실행해 설치하면"),
        (r"\*\*Codex 는 저장소의 설치 명령으로 연결\*\*", "**Codex 는 이 폴더의 설치 명령으로 연결**"),
        (r"이 꾸러미만으로는 Codex 에서", "손으로 복사한 설치만으로는 Codex 에서"),
    ],
}


#: 작성자 맥락 낱말 목록 — 저장소 밖(gitignore). 목록이 곧 작성자의 부서와 도구 이름이라 코드에 적지 않는다
CONTEXT_LIST = REPO / "data" / "catalog" / "local-package-anonymize.txt"
_B64 = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")


def context_terms(path: Path = CONTEXT_LIST) -> list[tuple[str, str]]:
    """「원래 말 => 바꿀 말」 줄을 읽는다 — 긴 말부터 바꿔야 짧은 말이 긴 말을 먼저 깨지 않는다."""
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=>" in line:
            old, new = (s.strip() for s in line.split("=>", 1))
            pairs.append((old, new))
    return sorted(pairs, key=lambda p: -len(p[0]))


def in_blob(text: str, start: int, end: int) -> bool:
    """서체를 심은 base64 덩이 안인가 — 그 안에서 우연히 맞은 글자를 바꾸면 서체가 깨진다."""
    if not all(c in _B64 for c in text[start:end]):
        return False
    a, b = start, end
    while a > 0 and text[a - 1] in _B64:
        a -= 1
    while b < len(text) and text[b] in _B64:
        b += 1
    return b - a >= 40


def swap(text: str, pairs: list[tuple[str, str]]) -> tuple[str, int]:
    count = 0
    for old, rep in pairs:
        hits = [m for m in re.finditer(re.escape(old), text) if not in_blob(text, m.start(), m.end())]
        for m in reversed(hits):
            text = text[:m.start()] + rep + text[m.end():]
        count += len(hits)
    return text, count


def rehash_excerpts(old: str, new: str) -> str:
    """사례 줄이 원문 발췌의 해시를 들고 있으면 바꾼 발췌로 다시 잰다 — 안 그러면 스킬 자체 시험이 깨진다."""
    lines = new.split("\n")
    for i, (a, b) in enumerate(zip(old.split("\n"), lines)):
        if a == b or "source_line_hash" not in b:
            continue
        try:
            row = json.loads(b)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("source_excerpt") and row.get("source_line_hash"):
            fresh = hashlib.sha256(row["source_excerpt"].encode("utf-8")).hexdigest()
            lines[i] = b.replace(row["source_line_hash"], fresh)
    return "\n".join(lines)


def replace_context(dest: Path, pairs: list[tuple[str, str]]) -> tuple[int, list[str]]:
    """목록의 낱말을 내용과 경로에서 바꾼다 — 바꾼 곳 수와, 바꾼 뒤에도 남은 곳(파일:줄 원래 말)을 돌려준다."""
    count = 0
    for f in sorted(dest.rglob("*")):
        if not f.is_file():
            continue
        rel, n = swap(f.relative_to(dest).as_posix(), pairs)
        if n:   # 시험 자료 폴더 이름에도 들어 있다 — 내용만 바꾸면 그 폴더를 가리키는 코드와 어긋난다
            count += n
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            f = f.rename(target)
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new, n = swap(text, pairs)
        count += n
        if n:
            if f.suffix == ".jsonl":
                new = rehash_excerpts(text, new)
            f.write_text(new, encoding="utf-8", newline="")
    left = []
    for f in sorted(dest.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(dest).as_posix()
        left += [f"{rel} (경로) {old}" for old, _ in pairs if old in rel]
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for old, _ in pairs:
            for m in re.finditer(re.escape(old), text):
                if not in_blob(text, m.start(), m.end()):
                    line = text[:m.start()].count("\n") + 1
                    left.append(f"{f.relative_to(dest).as_posix()}:{line} {old}")
    return count, left


def owner_pattern() -> re.Pattern | None:
    """원격 주소의 계정 이름 — 주소 밖에 홀로 적힌 계정 이름(「개발자 …」)도 찾는다. 코드에 이름을 적지 않는다."""
    url = subprocess.run(["git", "-C", str(REPO), "remote", "get-url", "origin"],
                         capture_output=True, text=True).stdout.strip()
    m = re.search(r"github\.com[:/]([A-Za-z0-9-]+)/", url)
    # 「\b」는 한글도 낱말 글자로 봐서 「<계정>이」를 놓친다(2026-11-03 검토) — 영문과 숫자 기준 경계를 직접 씀
    return re.compile(rf"(?<![A-Za-z0-9-]){re.escape(m.group(1))}(?![A-Za-z0-9-])", re.I) if m else None


def anonymize(dest: Path) -> list[str]:
    """ANONYMIZE 를 적용한다 — 맞지 않은 무늬를 돌려준다(원문이 바뀌어 빠져나간 것)."""
    missed = []
    for rel, rules in ANONYMIZE.items():
        f = dest / rel
        text = f.read_text(encoding="utf-8")
        for pattern, repl, *want in rules:
            text, n = re.subn(pattern, repl.replace("\\", "\\\\"), text, flags=re.S)
            if n != (want[0] if want else 1):
                missed.append(f"{rel}: {pattern[:60]} ({n}번 맞음)")
        f.write_text(text, encoding="utf-8", newline="")
    return missed


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
        missed = anonymize(dest)
        hits = []
        if CONTEXT_LIST.is_file():
            changed, left = replace_context(dest, context_terms())
            print(f"작성자 맥락 낱말 {changed}곳을 바꿈")
            hits += left
        else:   # 목록이 없다고 건너뛰면 침묵이 합격이 된다
            hits.append(f"(작성자 맥락 낱말 목록 {CONTEXT_LIST.name} 이 없어 바꾸지 못함)")
        rc = safety(dest)
        owner = owner_pattern()
        if owner is None:   # 못 읽었다고 계정 검사를 건너뛰면 침묵이 합격이 된다
            hits.append("(원격 주소에서 계정 이름을 못 읽어 계정 표기를 확인하지 못함)")
        for f in sorted(dest.rglob("*")):
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
                for n, line in enumerate(text.splitlines(), 1):
                    if IDENTIFYING.search(line) or (owner and owner.search(line)):
                        hits.append(f"{f.relative_to(dest).as_posix()}:{n}")
        for m in missed:
            print(f"❌ 익명 처리 무늬가 안 맞음 — {m}")
        if hits:
            print(f"\n❌ 작성자를 드러낼 수 있는 표기 {len(hits)}줄 — ANONYMIZE 에 무늬를 더한다")
            for h in hits[:20]:
                print(f"  {h}")
            if len(hits) > 20:
                print(f"  … 외 {len(hits) - 20}줄")
        if missed or hits:
            print("\n❌ 익명 처리가 끝나지 않아 zip 을 만들지 않습니다")
            return 2
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
