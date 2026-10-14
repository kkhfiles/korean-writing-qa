"""2층 판정이 어느 줄을 봤는지 — 판정기(`judge_layer2.py`)와 발행 게이트가 함께 쓴다.

**왜 따로 두나.** 판정기는 호출마다 그 묶음의 한글 줄 해시를 판정 기록에 남기고,
게이트는 push 직전에 「이번 가지에서 새로 생긴 줄을 판정기가 다 봤나」를 그 기록으로
가른다. 두 곳이 줄을 다르게 자르거나 다르게 해시하면 판정한 줄도 안 본 줄로 나온다.
그래서 글 뽑기 · 줄 해시 · 기록 읽기를 이 파일 한 곳에 둔다.

**한글이 든 줄만 센다.** 구분선 · 빈 줄 · 코드 줄은 2층이 판정할 글이 아니다.

**기록은 14일까지만 믿는다** — 통과 기록(`check_record.py`)과 같은 기한이다.

**사람 확인** (2026-10-06 사용자 — 「규칙으로 잡고 llm 판단으로 잡고, 그래도 애매하면
사람한테 애스컬레이션」) — 판정기가 `decide: ask` 로 낸 지적은 판정 기록의 `asks` 에
줄 해시와 함께 남는다. 사용자가 답하면 답 기록(`ANSWERS`)에 그 줄 해시가 남는다.
**답은 문서가 아니라 줄에 묶는다** — 다른 줄을 고쳐도 받은 답이 살아 있어야 한 번
물은 것을 또 묻지 않는다. 짚은 표현을 고치면 그 지적은 사라진다(고친 것이다).
사람 확인과 답에는 14일 기한을 걸지 않는다 — 걸면 기다리기만 해도 막힘이 풀린다.

**고칠 지적도 처리 기록이 있어야 닫힌다** (2026-10-12) — 판정기가 `fix` 로 낸 지적은 판정
기록의 `fixes` 에 남고, 짚은 표현이 그 줄에 남아 있는 동안 열려 있다. 닫는 길은 셋이다 —
고침(표현이 사라짐 · 고친 줄은 게이트의 「판정기가 안 본 줄」이 다시 판정을 요구) · 세션이
지적마다 사유 코드와 근거를 적어 받지 않음(`DISMISSALS`) · 사람 확인으로 올림. 전에는 고칠
지적이 남아도 발행이 됐고, 그 틈으로 사실 확인이 필요한 지적이 사용자에게 안 갔다(고리 재현
시험 — 갈래별 자동 전환 5건과 「확인 필요」를 적은 고칠 지적 10건).
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
#: 사람 확인 지적에 사용자가 답한 기록 — 비용 장부(`LOG`)와 따로 둔다(장부 합계에 안 섞이게)
ANSWERS = Path(os.environ.get("KOREAN_QA_ANSWER_LOG")
               or Path.home() / ".claude" / "state" / "korean-layer2-answers.jsonl")
#: 사람 확인 표에 사용자가 적은 답 전부(고침까지) — 판정기가 다음 판정에서 따른다.
#: `ANSWERS` 는 「그대로」만 받아 지적을 닫는 곳이고, 이것은 지적을 닫지 않고 배우는 곳이다.
DECISIONS = Path(os.environ.get("KOREAN_QA_DECISION_LOG")
                 or Path.home() / ".claude" / "state" / "korean-layer2-decisions.jsonl")
#: 고칠 지적을 세션이 받지 않기로 했거나 사람 확인으로 올린 기록 — 지적마다 사유 코드와 근거.
#: 사람 확인 답(`ANSWERS`)과 따로 둔다 — 세션이 적는 곳이라 사람 확인을 닫지 못해야 한다.
DISMISSALS = Path(os.environ.get("KOREAN_QA_DISMISS_LOG")
                  or Path.home() / ".claude" / "state" / "korean-layer2-dismissals.jsonl")
FRESH_DAYS = 14
HANGUL = re.compile(r"[가-힣]")
#: 근거에 이 말이 있으면 문서 밖 자료로 확인할 사실이 걸린 지적으로 본다 — 판정기가 `check`
#: 칸을 비웠을 때의 보조 장치다(외부 검토 「문자열 검사는 보조로만」 · 2026-10-12).
NEEDS_CHECK = re.compile(r"확인(?:이)?\s?필요|확인해야|확인할 수 없|원문에서 확인|사람이 정해야"
                         r"|확인되지 않|검증(?:이)?\s?필요|알 수 없어 사람")
#: 고친 줄을 예전 줄의 자손으로 보는 글자 유사도 — 표현이 그 자손에 남아 있으면 안 고친 것이다
SUCCESSOR = 0.5
#: 판정 때와 지금의 줄 순서를 맞대어 찾은 「바뀐 자리」 안에서 자손으로 보는 글자 유사도 —
#: 자리가 이미 좁혀졌으므로 낮게 둔다(git 이력의 1:1 고친 줄 178쌍 중 97% 가 0.3 이상 · 2026-10-13)
IN_PLACE = 0.3


class _Text(html.parser.HTMLParser):
    """HTML 에서 사람이 읽는 글만 줄 단위로 뽑는다 — script·style 은 뺀다."""

    # button — 단추 글자가 앞 문장에 붙어 「실제로 걸린 문장 넷멈춤」으로 읽혀 판정기가
    # 「작업 흔적」이라고 사람에게 넘겼다(2026-10-07 사례집의 슬라이드 멈춤 단추).
    BLOCK = {"p", "li", "dd", "dt", "td", "th", "tr", "h1", "h2", "h3", "h4",
             "h5", "h6", "div", "section", "article", "br", "pre", "blockquote", "button"}

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


#: 문서 열쇠에서 뿌리 기준 경로와 저장소 식별자를 가르는 표시
KEY_SEP = "::"


def repo_id(top: Path) -> str:
    """저장소 식별자 — git 공통 폴더의 해시라 작업 트리와 기본 checkout 이 같은 값이다."""
    got = _git(top, "rev-parse", "--git-common-dir")
    common = got.stdout.decode("utf-8").strip() if got.returncode == 0 else ""
    where = (Path(top) / common).resolve() if common else Path(top).resolve()
    return hashlib.sha256(where.as_posix().lower().encode("utf-8")).hexdigest()[:10]


def key_in(top: Path, rel: str) -> str:
    """저장소 `top` 안의 `rel` 문서 열쇠 — push 게이트처럼 파일 없이 커밋만 볼 때 쓴다."""
    return f"{rel}{KEY_SEP}{repo_id(top)}"


def doc_key(path: Path) -> str:
    """판정 기록에서 문서를 가르는 열쇠 — 저장소 안이면 「뿌리 기준 경로::저장소 식별자」, 밖이면 절대 경로.

    뿌리 기준 경로를 쓰는 까닭 — 작업 트리에서 판정하고 같은 가지를 기본 checkout 에서
    밀어도 같은 문서로 읽혀야 한다. 저장소 식별자를 붙이는 까닭 — 경로만 쓰면 다른 저장소의
    같은 이름 문서(`README.md`)에 남긴 처리 기록이 이 저장소의 같은 글줄 지적을 닫았다
    (2026-10-13 게이트 부정 시험).
    """
    found = repo_of(path)
    return key_in(*found) if found else path.resolve().as_posix()


def key_matches(row_key, key: str) -> bool:
    """기록 줄의 열쇠가 이 문서인가 — 저장소 식별자가 없던 옛 기록(2026-10-13 전)은 경로만 맞으면 읽는다.

    옛 기록을 버리면 그때까지의 판정 · 처리 기록이 모두 사라져 같은 줄을 다시 판정하고 다시
    닫아야 한다. 옛 기록끼리의 저장소 혼동은 남지만 새 기록부터는 안 섞인다.
    """
    if row_key == key:
        return True
    return (isinstance(row_key, str) and KEY_SEP not in row_key and KEY_SEP in key
            and key.split(KEY_SEP, 1)[0] == row_key)


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


def base_time(path: Path, ref: str) -> float | None:
    """`ref` 와 갈라진 지점 커밋의 시각 — 그보다 앞선 판정은 이미 합쳐진 작업이다 · git 밖이면 None."""
    found = repo_of(path)
    if not found:
        return None
    mb = _git(found[0], "merge-base", "HEAD", ref)
    if mb.returncode:
        return None
    got = _git(found[0], "log", "-1", "--format=%ct", mb.stdout.decode().strip())
    try:
        return float(got.stdout.decode().strip())
    except ValueError:
        return None


def _rows(key: str, log: Path, now: float | None, fresh: bool = True):
    """이 문서의 기록 줄 — `fresh` 면 14일 안 것만. 판정 기록과 답 기록이 같이 쓴다."""
    now = time.time() if now is None else now
    if not log.is_file():
        return
    for raw in log.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        if not key_matches(row.get("key"), key):
            continue
        try:
            age = now - float(row.get("when") or 0)
        except (TypeError, ValueError):
            continue
        if fresh and age > FRESH_DAYS * 86400:
            continue
        yield row


def judged(key: str, log: Path | None = None, now: float | None = None,
           fresh: bool = True) -> set[str]:
    """이 문서에서 판정기가 이미 본 줄 해시 — 성공한 호출 · `fresh` 면 14일 안 것만.

    `fresh=False` 는 사이트 배포 게이트가 쓴다 — 배포는 git 의 갈라진 지점이 없어
    「새 줄」을 「판정기가 한 번도 안 본 줄」로 가른다. 기한을 걸면 안 바뀐 페이지를
    14일마다 통째로 다시 판정해야 한다.
    """
    out: set[str] = set()
    for row in _rows(key, log or LOG, now, fresh):
        if row.get("ok"):
            out.update(row.get("seen") or [])
    return out | approved(key, now=now)


def answered(key: str, answers: Path | None = None, now: float | None = None) -> set[str]:
    """사용자가 답한 줄 해시 — 기한 없음(그 줄 글자가 같은 동안은 사용자가 정한 것이 그대로다)."""
    return {row["line_key"] for row in _rows(key, answers or ANSWERS, now, fresh=False)
            if row.get("line_key")}


def approved(key: str, answers: Path | None = None, now: float | None = None) -> set[str]:
    """사용자가 사람 확인에 답한 대로 고친 줄 해시 — 사람이 판정한 줄이라 판정기가 다시 보지 않는다.

    ⛔ 전에는 답대로 고친 줄도 새 줄이라 다시 판정했고, 상한을 넘은 줄은 그 판정의 지적이 모두 사람
       확인으로 갔다. 판정기는 판정마다 다른 것을 짚어서 한 줄에 네 번을 물었다(2026-10-14 lab-docs ·
       사람 확인 208건 중 101건이 상한 때문). 고친 글이 사용자가 고른 글과 글자까지 같을 때만 여기
       오른다 — 1층 검사기는 계속 본다.
    """
    return {row["line_key"] for row in _rows(key, answers or ANSWERS, now, fresh=False)
            if row.get("approved") and row.get("line_key")}


def decided(key: str, decisions: Path | None = None, answers: Path | None = None) -> set[tuple]:
    """사용자가 답한 사람 확인 지적 — (물은 줄 해시, 표현). 보류 · 빈칸은 결정 기록에 안 남는다.

    답 기록에 적힌 「이 답이 닫은 지적」도 넣는다 — 앞 판에서 물어 표현을 따라 뒤 판에 붙은 지적은 뒤 판에
    답해도 줄 해시가 달라, 줄이 또 바뀌면 다시 붙었다(2026-10-14 README).
    """
    out = {(row.get("line_key"), row.get("phrase"))
           for row in _rows(key, decisions or DECISIONS, None, fresh=False) if row.get("line_key")}
    for row in _rows(key, answers or ANSWERS, None, fresh=False):
        out.update(tuple(a) for a in row.get("asks") or [] if isinstance(a, list) and len(a) == 2)
    return out


def ask_rows(key: str, log: Path | None = None, now: float | None = None,
             dismissals: Path | None = None):
    """이 문서의 사람 확인 지적 — 판정기가 넘긴 것과 세션이 고칠 지적에서 올린 것."""
    for row in _rows(key, log or LOG, now, fresh=False):
        if row.get("ok"):
            yield from row.get("asks") or []
    for row in _rows(key, dismissals or DISMISSALS, now, fresh=False):
        if row.get("escalate"):
            yield row


def open_asks(key: str, lines: list[str], log: Path | None = None,
              answers: Path | None = None, now: float | None = None) -> list[tuple[int, dict]]:
    """아직 사용자 답을 못 받은 사람 확인 지적 — (지금 줄 번호, 지적) 목록.

    물은 줄이 그대로 있으면 그 줄에, 바뀌었으면 **짚은 표현이 남아 있는 줄**에 붙인다.
    표현까지 고쳤으면 뺀다 — 고친 것이다. ⛔ 줄 해시만 보면 같은 줄의 다른 낱말 하나만
    바꿔도 묻지 않고 지적이 사라진다(2026-10-06 돌연변이 시험이 짚은 빈틈).

    ⛔ **기한이 없다** — 판정 기록의 14일 기한을 여기에도 걸면 기다리기만 해도 막힘이
    풀린다. 판정한 줄(`judged`)은 기한이 지나면 「다시 판정하라」로 막는 쪽이지만, 사람
    확인은 기한이 지나면 조용히 사라지는 쪽이라 거꾸로 열린다(2026-10-06 재검토).
    """
    where: dict[str, int] = {}
    for n, line in enumerate(lines, 1):
        k = line_key(line)
        if k and k not in where:
            where[k] = n
    done = answered(key, answers, now)
    told = decided(key)
    out, seen = [], set()
    for ask in ask_rows(key, log, now):
        n = where.get(ask.get("line_key") or "")
        if n is None:
            # 사용자가 답한 지적은 물은 줄이 바뀌면 닫는다 — 고른 문구 안에 물은 표현이 그대로 들면
            # 답대로 고쳐도 다시 붙어 같은 것을 또 물었다(2026-10-14 「주제 문서」 → 「주제 문서(…)」).
            # 답과 다르게 고쳤으면 그 줄은 새 줄이라 판정기가 다시 본다.
            # `--answer` 로 답한 판도 같다 — 그 판의 줄 해시가 답 기록에 있다
            if (ask.get("line_key"), ask.get("phrase")) in told or ask.get("line_key") in done:
                continue
            phrase = str(ask.get("phrase") or "").strip()
            n = next((i for i, l in enumerate(lines, 1) if phrase and phrase in l), None)
        if n is None:
            continue
        k = line_key(lines[n - 1])
        if not k:
            continue            # 한글이 없는 줄 — 이 판정기의 몫이 아니고 답할 길도 없다
        if k in done or (n, ask.get("phrase")) in seen:
            continue
        seen.add((n, ask.get("phrase")))
        out.append((n, ask))
    return sorted(out, key=lambda x: x[0])


def needs_check(item: dict) -> bool:
    """문서 밖 자료로 확인할 사실이 걸린 지적인가 — 판정기의 `check` 칸 · 없으면 근거의 말로."""
    return bool(str(item.get("check") or "").strip()) or bool(NEEDS_CHECK.search(str(item.get("why") or "")))


def _plain(text: str) -> str:
    """강조 표시를 뺀 글 — 판정기는 `**굵게**` 를 빼고 표현을 옮겨 적는다(2026-10-12 고리 시험)."""
    return re.sub(r"[*_`]", "", text)


#: 링크 주소 — 줄이 비슷한지는 보이는 글로 가른다
LINK_TARGET = re.compile(r"\]\([^)\s]*\)|https?://\S+")


def _visible(text: str) -> str:
    """링크 주소를 뺀 글. ⛔ 같은 출처 주소를 담은 서로 다른 줄이 주소 길이 때문에 글자 절반 이상이
    같아져 한 계보로 묶였다 — 출처 소개 줄이 원문 목록 줄의 판정 횟수를 물려받아 상한에 일찍 닿고,
    기준 판도 그 줄로 잡혔다(2026-10-14 lab-docs · 주소를 넣으면 0.57 · 빼면 0.21)."""
    seen = LINK_TARGET.sub("", text)
    return seen if seen.strip() else text


def _similar(a: str, b: str) -> float:
    import difflib
    m = difflib.SequenceMatcher(None, _visible(a), _visible(b), autojunk=False)
    return m.ratio() if m.real_quick_ratio() >= SUCCESSOR and m.quick_ratio() >= SUCCESSOR else 0.0


def _ratio(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, _visible(a), _visible(b), autojunk=False).ratio()


def successor(seen, old_key: str, lines: list[str], text: str) -> int | None:
    """고친 줄(`old_key`)을 이어 받은 지금 줄 번호 · 지웠으면 None.

    판정 때의 줄 순서(`seen` — 그 묶음의 줄 해시 순서)와 지금 줄 순서를 맞대어, 그 줄이 바뀐
    자리 안에서만 찾는다. ⛔ 문서 전체에서 가장 비슷한 줄을 고르면 지운 줄의 지적이 내용이 다른
    줄에 붙었다 — 무관한 두 줄이 0.588 로 기준 0.5 를 넘었고(2026-10-13 게이트 부정 시험), git
    이력에서 지운 줄 18개 중 13개가 그렇게 엉뚱한 줄을 찾았다. 줄 순서가 없는 옛 기록만 전체에서 찾는다.
    """
    import difflib
    now = [(n, line_key(l)) for n, l in enumerate(lines, 1)]
    now = [(n, k) for n, k in now if k]
    if isinstance(seen, list) and old_key in seen:
        i = seen.index(old_key)
        sm = difflib.SequenceMatcher(None, seen, [k for _, k in now], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if not i1 <= i < i2:
                continue
            if tag != "replace":
                return None                 # 그 자리에서 지웠다
            block = [now[j][0] for j in range(j1, j2)]
            best = max(block, key=lambda n: _ratio(lines[n - 1], text))
            return best if _ratio(lines[best - 1], text) >= IN_PLACE else None
        return None
    best = max(range(1, len(lines) + 1), key=lambda n: _similar(lines[n - 1], text), default=None)
    return best if best is not None and _similar(lines[best - 1], text) >= SUCCESSOR else None


def dismissed(key: str, dismissals: Path | None = None, now: float | None = None) -> set[tuple]:
    """받지 않음 · 사람 확인으로 올림으로 닫은 고칠 지적 — (줄 해시, 표현)."""
    return {(row.get("line_key"), row.get("phrase"))
            for row in _rows(key, dismissals or DISMISSALS, now, fresh=False) if row.get("line_key")}


def open_fixes(key: str, lines: list[str], log: Path | None = None,
               dismissals: Path | None = None, now: float | None = None) -> list[tuple[int, dict]]:
    """아직 처리 안 된 고칠 지적 — (지금 줄 번호, 지적).

    **열림** — 그 줄이 그대로이거나, 그 줄을 고친 줄(글자가 절반 이상 같음)에 짚은 표현이 남아
    있음. 줄이 그대로면 표현이 안 맞아도 연다 — 판정기가 강조 표시를 빼고 옮겨 적어 표현이 글자로
    안 맞는 일이 있는데, 그때 닫으면 아무도 안 고친 지적이 사라진다.
    **닫힘** — 표현이 사라짐(고침) · 받지 않음이나 사람 확인으로 올림 기록(줄 해시 + 표현).
    받지 않음은 그 줄이 바뀌면 다시 열린다 — 근거가 바뀌었을 수 있다.
    **사실 확인 지적**(`needs_check`)은 고쳐도 안 닫힌다 — 고친 줄에 붙어 「확인함」이나 사람
    확인을 기다린다.
    ⛔ 기한이 없다 — 사람 확인과 같은 까닭이다.
    """
    where: dict[str, int] = {}
    for n, line in enumerate(lines, 1):
        k = line_key(line)
        if k and k not in where:
            where[k] = n
    done = dismissed(key, dismissals, now)
    out, seen = [], set()
    for row in _rows(key, log or LOG, now, fresh=False):
        if not row.get("ok"):
            continue
        for fx in row.get("fixes") or []:
            phrase = str(fx.get("phrase") or "").strip()
            n = where.get(fx.get("line_key") or "")
            if n is None:
                if not phrase:
                    continue
                text = str(fx.get("text") or "")
                cands = [i for i, l in enumerate(lines, 1) if _plain(phrase) in _plain(l)]
                if text:
                    cands = [i for i in cands if _similar(lines[i - 1], text) >= SUCCESSOR]
                if not cands and text and needs_check(fx):
                    # ⛔ 사실 확인 지적은 고쳐도 안 닫힌다 — 확인 없이 다른 수치로 바꿔도 표현은
                    #    사라진다(외부 검토 「표현 소멸은 해결 증거가 아님」). 고친 줄에 붙여 둔다.
                    #    줄을 통째로 지웠으면 닫는다 — 확인 안 된 주장이 안 나가는 쪽이다. 지워서
                    #    남은 글의 뜻이 바뀌었는지는 지운 자리 판정이 본다.
                    best = successor(row.get("seen"), fx.get("line_key") or "", lines, text)
                    if best is not None:
                        cands = [best]
                if not cands:
                    continue                # 표현이 사라짐 — 고쳤다
                hint = fx.get("line") if isinstance(fx.get("line"), int) else 0
                n = min(cands, key=lambda i: abs(i - hint))
            k = line_key(lines[n - 1])
            if not k or (k, fx.get("phrase")) in done or (n, phrase) in seen:
                continue
            seen.add((n, phrase))
            out.append((n, fx))
    return sorted(out, key=lambda x: x[0])


def deletions(lines: list[str], base: list[str] | None) -> list[tuple[int, list[str]]]:
    """새 줄 없이 지우기만 한 자리 — (그 자리를 대표할 지금 줄 번호, 지운 한글 줄들).

    대표 줄은 지운 자리 바로 다음의 한글 줄(없으면 앞의 한글 줄)이다. 다른 곳으로 옮긴 줄(지금 글에
    같은 줄이 있음)은 지운 것이 아니다. ⛔ 지우기만 하면 판정기가 아무것도 안 봐서, 필요한 조건을
    지워도 게이트를 통과했다(2026-10-13 게이트 부정 시험 · 외부 검토 「삭제는 재검증 대상」).
    """
    if not base:
        return []
    import difflib
    now = {k for k in map(line_key, lines) if k}
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, base, lines, autojunk=False).get_opcodes():
        if tag != "delete":
            continue
        gone = [b for b in base[i1:i2] if (k := line_key(b)) and k not in now]
        if not gone:
            continue
        after = next((n for n in range(j1 + 1, len(lines) + 1) if line_key(lines[n - 1])), None)
        before = next((n for n in range(j1, 0, -1) if line_key(lines[n - 1])), None)
        if after or before:
            out.append((after or before, gone))
    return out


def deleted_seen(key: str, log: Path | None = None, now: float | None = None) -> set[str]:
    """판정기가 지운 줄로 받아 본 기준 판 줄 해시 — 성공한 호출 · 14일 안 것만."""
    return {k for row in _rows(key, log or LOG, now) if row.get("ok")
            for k in row.get("deleted_seen") or []}


def open_deletions(lines: list[str], base: list[str] | None, seen: set[str]) -> list[tuple[int, list[str]]]:
    """판정기가 아직 안 본 지운 자리 — `deletions` 가운데 지운 줄이 하나라도 `seen` 에 없는 것."""
    return [(n, gone) for n, gone in deletions(lines, base)
            if not all(line_key(g) in seen for g in gone)]


def open_lines(lines: list[str], base: list[str] | None, seen: set[str]) -> list[int]:
    """판정이 필요한 줄 번호(1부터) — 한글이 들었고, 갈라진 지점에 없었고, 아직 안 본 줄."""
    old = {k for k in map(line_key, base or []) if k}
    return [n for n, line in enumerate(lines, 1)
            if (k := line_key(line)) and k not in old and k not in seen]
