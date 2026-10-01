"""2층 판정이 어느 줄을 봤는지 — 판정기(`judge_layer2.py`)와 발행 게이트가 함께 쓴다.

**왜 따로 두나.** 판정기는 호출마다 그 묶음의 한글 줄 해시를 판정 기록에 남기고,
게이트는 push 직전에 「이번 가지에서 새로 생긴 줄을 판정기가 다 봤나」를 그 기록으로
가른다. 두 곳이 줄을 다르게 자르거나 다르게 해시하면 판정한 줄도 안 본 줄로 나온다.
그래서 글 뽑기 · 줄 해시 · 기록 읽기를 이 파일 한 곳에 둔다.

**한글이 든 줄만 센다.** 구분선 · 빈 줄 · 코드 줄은 2층이 판정할 글이 아니다.

**기록은 14일까지만 믿는다** — 통과 기록(`check_record.py`)과 같은 기한이다.
"""

from __future__ import annotations

import hashlib
import html.parser
import json
import os
import re
import subprocess
import time
from pathlib import Path

LOG = Path(os.environ.get("KOREAN_QA_JUDGE_LOG")
           or Path.home() / ".claude" / "state" / "korean-layer2-judge.jsonl")
FRESH_DAYS = 14
HANGUL = re.compile(r"[가-힣]")


class _Text(html.parser.HTMLParser):
    """HTML 에서 사람이 읽는 글만 줄 단위로 뽑는다 — script·style 은 뺀다."""

    BLOCK = {"p", "li", "dd", "dt", "td", "th", "tr", "h1", "h2", "h3", "h4",
             "h5", "h6", "div", "section", "article", "br", "pre", "blockquote"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def visible_text(text: str, suffix: str) -> str:
    """판정에 넘기는 글 — HTML 은 보이는 글만, 나머지는 그대로."""
    if suffix.lower() in (".html", ".htm"):
        p = _Text()
        p.feed(text)
        lines = [re.sub(r"\s+", " ", l).strip() for l in "".join(p.parts).splitlines()]
        return "\n".join(l for l in lines if l)
    return text


def read_doc(path: Path) -> str:
    return visible_text(path.read_text(encoding="utf-8", errors="replace"), path.suffix)


def line_key(line: str) -> str | None:
    """한글이 든 줄의 해시 · 아니면 None. 앞뒤 공백과 공백 개수는 무시한다."""
    if not HANGUL.search(line):
        return None
    return hashlib.sha256(re.sub(r"\s+", " ", line).strip().encode("utf-8")).hexdigest()[:12]


def seen_keys(lines: list[str]) -> list[str]:
    """판정 기록에 남길 줄 해시 — 한 묶음에서 한글이 든 줄만, 겹치면 한 번."""
    return list(dict.fromkeys(k for k in map(line_key, lines) if k))


def _git(top: Path | str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(top), *args], capture_output=True, timeout=30)


def repo_of(path: Path) -> tuple[Path, str] | None:
    """(저장소 뿌리, 뿌리 기준 경로) · git 밖이면 None.

    작업 트리에서 부르면 그 작업 트리가 뿌리다 — 뿌리 기준 경로는 기본 checkout 과 같다.
    """
    got = _git(path.resolve().parent, "rev-parse", "--show-toplevel")
    if got.returncode:
        return None
    top = Path(got.stdout.decode("utf-8").strip())
    return top, path.resolve().relative_to(top.resolve()).as_posix()


def doc_key(path: Path) -> str:
    """판정 기록에서 문서를 가르는 열쇠 — 저장소 안이면 뿌리 기준 경로, 밖이면 절대 경로.

    뿌리 기준 경로를 쓰는 까닭 — 작업 트리에서 판정하고 같은 가지를 기본 checkout 에서
    밀어도 같은 문서로 읽혀야 한다.
    """
    found = repo_of(path)
    return found[1] if found else path.resolve().as_posix()


def base_lines(path: Path, ref: str) -> list[str] | None:
    """`ref` 와 갈라진 지점의 같은 문서 줄 · 그때 없던 문서면 빈 목록 · git 밖이면 None.

    ⛔ `ref` 를 못 풀면 ValueError — 갈라진 지점을 모르면 새 줄을 가를 수 없다.
    """
    found = repo_of(path)
    if not found:
        return None
    top, rel = found
    mb = _git(top, "merge-base", "HEAD", ref)
    if mb.returncode:
        raise ValueError(f"갈라진 지점을 못 찾았습니다 — {ref}: "
                         + mb.stderr.decode("utf-8", "replace").strip()[:200])
    show = _git(top, "show", f"{mb.stdout.decode().strip()}:{rel}")
    if show.returncode:
        return []
    return visible_text(show.stdout.decode("utf-8", "replace"), path.suffix).splitlines()


def judged(key: str, log: Path | None = None, now: float | None = None) -> set[str]:
    """이 문서에서 판정기가 이미 본 줄 해시 — 성공한 호출 · 14일 안 것만."""
    log = log or LOG
    now = time.time() if now is None else now
    out: set[str] = set()
    if not log.is_file():
        return out
    for raw in log.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if not row.get("ok") or row.get("key") != key:
            continue
        if now - float(row.get("when") or 0) > FRESH_DAYS * 86400:
            continue
        out.update(row.get("seen") or [])
    return out


def open_lines(lines: list[str], base: list[str] | None, seen: set[str]) -> list[int]:
    """판정이 필요한 줄 번호(1부터) — 한글이 들었고, 갈라진 지점에 없었고, 아직 안 본 줄."""
    old = {k for k in map(line_key, base or []) if k}
    return [n for n, line in enumerate(lines, 1)
            if (k := line_key(line)) and k not in old and k not in seen]
