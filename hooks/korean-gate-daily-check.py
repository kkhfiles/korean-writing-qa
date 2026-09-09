r"""SessionStart 훅: 하루 첫 세션에 한글 검사 시스템이 성한지 본다.

**왜 있나.** 이 시스템이 지키는 것은 배포된 전역 자산(`assets/doc-style-check.py`,
`hooks/doc-style-gate.py`, `skills/finalize-korean-document`)인데, 그 파일들은 **어느
프로젝트 세션에서든** 바뀐다. 시험은 `korean-writing-qa` 에 있어서, 그 저장소를 안 여는
날에는 아무도 안 돌린다. 실측(8/24~9/4): 자산이 바뀐 9일 중 9일이 덮였지만 그것은
마침 그 저장소에서 고쳤기 때문이고, 구조가 보장한 것이 아니다.

**보는 것 셋** — 고친 것이 GitHub 까지 가는 길에 끊길 지점이 셋이다.

| 끊기는 지점 | 무엇이 잡나 |
|---|---|
| 설치본만 고침 · 정본은 그대로 | 회귀 시험(`test_installed_copy_matches`) |
| 정본을 고치고 **커밋 안 함** | `check_git` — 아래 |
| 커밋하고 **push 안 함** | `check_git` — 아래 |

앞의 것 하나만 막혀 있었다(2026-09-09 확인). 「설치본과 정본이 같다」와 「저장소가
GitHub 과 같다」는 **다른 말인데**, 뒤엣것을 보는 곳이 저장소 전체에 없었다.
정본을 고친 뒤 `install.py` 를 다시 돌리면 설치본 대조는 통과하므로, 그때부터
미커밋 상태는 아무 소리도 안 낸다.

**설계**
- **하루 한 번**(첫 세션)만 돌린다. 그날 이미 봤으면 즉시 끝난다.
- **초록이면 아무 말도 안 한다.** 조용한 날에는 화면에 아무것도 안 나온다.
- **판단 불가면 침묵**(저장소 없음·pytest 없음·git 없음). 그날을 「봤다」로 적지
  않고, 다만 6시간 안에는 다시 시도하지 않는다 — 세션마다 재시도하면 그게 소음이다.
- **★ 판단 불가가 사흘 이어지면 그때는 말한다.** 하루치 침묵은 잠깐 못 본 것이고,
  사흘치 침묵은 **감시가 죽은 것**이다. 둘을 같이 묻으면 자산이 바뀌어도 아무도
  안 본다 — 이 저장소가 이미 한 번 겪고 닫은 결론이다(판단 A, 2026-09-03).
  단 **이 기계에서 한 번도 판정이 난 적이 없으면 잠자코 있는다** — 저장소 없이
  검사기만 받은 기계를 매일 찌르는 것은 오탐이다.
- 실패하면 **막지 않고 알린다.** 게이트가 아니라 건강 검진이다.
- 배치·예약 실행(`CLAUDE_BATCH_MODE`·`CLAUDE_SCHEDULED`)에서는 즉시 끝.

**CI 결과는 안 본다**(2026-09-09 판단) — `main` 이 빨간 채로 방치된 적이 없다
(실측: 최근 28회 중 실패 2회, 둘 다 같은 날 몇 분 만에 고침). 세션 시작에 네트워크
호출을 붙이는 값이 그만큼 안 나온다. 실패하면 GitHub 이 메일을 보낸다.

**왜 동기 스크립트에 안 붙였나** — `sync.sh` 는 하루 20~25번 돈다. 9초짜리 시험을
거기 붙이면 하루 4분을 막는다. 세션 시작은 하루 몇 번이고, 그중 첫 번만 돈다.

State: `~/.claude/state/korean-gate-check-state.json`
  - `last_checked_date`: "YYYY-MM-DD" — 판정이 난 날
  - `last_attempt_at`: ISO timestamp — 판단 불가로 끝난 마지막 시도

    python -X utf8 korean-gate-daily-check.py --self-test   # state·시험 안 씀
"""
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

REPO = Path(os.environ.get("KOREAN_WRITING_QA_HOME", "P:/github/korean-writing-qa"))
RETRY_HOURS = 6
TIMEOUT = 180
GIT_TIMEOUT = 10

#: 판단 불가가 이만큼 이어지면 감시가 죽은 것으로 보고 말한다.
STALE_DAYS = 3

#: 정본이 사는 곳 — `install.py` 가 여기서 설치본으로 옮긴다. 네 번째가 생기면
#: `tests/test_daily_check_watches_github.py` 가 깨져서 여기를 고치라고 한다.
CANONICAL = ("assets", "hooks", "skills")


def state_path() -> Path:
    override = os.environ.get("KOREAN_GATE_CHECK_STATE")
    if override:
        return Path(override)
    return Path.home() / ".claude" / "state" / "korean-gate-check-state.json"


def read_state() -> dict:
    try:
        return json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(value: dict) -> None:
    try:
        target = state_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def due(state: dict, now: datetime) -> bool:
    """지금 시험을 돌릴 때인가. 하루 1회 + 판단 불가 뒤 6시간 유예."""
    if state.get("last_checked_date") == now.date().isoformat():
        return False
    last = state.get("last_attempt_at")
    if last:
        try:
            if now - datetime.fromisoformat(last) < timedelta(hours=RETRY_HOURS):
                return False
        except ValueError:
            pass
    return True


def run_suite():
    """(통과 여부, 사람이 읽을 요약). 못 돌렸으면 (None, 까닭)."""
    if not (REPO / "tests").is_dir():
        return None, f"시험 저장소가 없다 ({REPO})"
    try:
        done = subprocess.run(
            [sys.executable, "-X", "utf8", "-m", "pytest", "tests/", "-q", "--no-header"],
            cwd=str(REPO), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"시험을 돌리지 못했다 ({exc})"
    tail = [line for line in (done.stdout or "").splitlines() if line.strip()]
    return done.returncode == 0, "\n".join(tail[-12:])


def git(repo: Path, *args: str):
    """git 출력 한 덩이. 못 돌렸거나 rc 가 0 이 아니면 None — 그때는 판단 불가다."""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def check_git(repo: Path):
    """고친 것이 GitHub 까지 갔나. 문제 목록 · 판단이 안 서면 None.

    **미커밋은 정본만 본다**(`CANONICAL`). 문서·연구 기록까지 세면 작업 중인 날마다
    떠서, 정작 봐야 할 날에 아무도 안 읽는다. 정본이 하루를 넘겨 미커밋인 것은
    거의 사고다 — 그건 `install.py` 를 다시 돌리는 순간 설치본 대조에서도 사라진다.

    **미push 는 커밋 전부를 본다.** 커밋했다는 것은 그 단위가 끝났다는 뜻이라
    로컬에만 있을 까닭이 없다.

    ⚠️ 원격이 없으면 push 쪽만 판단 불가다 — 미커밋 판정까지 버리지 않는다.
    """
    # 저장소가 아니거나 git 이 없으면 이 한 줄이 실패한다 — 따로 물어볼 것이 없다.
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no", "--", *CANONICAL)
    if dirty is None:
        return None
    problems = []
    if dirty:
        # `XY 경로` — 앞의 두 글자가 상태다. 자리로 자르지 않는다: `git()` 이
        # 앞뒤 빈칸을 떼어 첫 줄만 한 글자 밀리고, 그러면 경로 첫 글자가 잘린다.
        names = [line.split(None, 1)[1] for line in dirty.splitlines()
                 if len(line.split(None, 1)) == 2]
        shown = " · ".join(names[:4]) + (" …" if len(names) > 4 else "")
        problems.append(f"정본 {len(names)}개가 커밋 안 됨 — {shown}")

    ahead = git(repo, "rev-list", "--count", "@{upstream}..HEAD")
    if ahead and ahead.isdigit() and int(ahead):
        problems.append(f"GitHub 에 안 올라간 커밋 {ahead}개")
    return problems


def stale_days(state: dict, now: datetime):
    """마지막 판정으로부터 며칠. 이 기계에서 한 번도 판정이 안 났으면 None."""
    last = state.get("last_checked_date")
    if not last:
        return None
    try:
        return (now.date() - date.fromisoformat(last)).days
    except (ValueError, TypeError):
        return None


def render_git(problems: list, repo: Path) -> str:
    return "\n".join([
        "⚠️ 한글 검사기를 고친 것이 GitHub 에 안 갔다 — 하루 첫 세션 점검",
        "",
        *[f"- {p}" for p in problems],
        "",
        "설치본 대조가 통과해도 저장소가 GitHub 과 다를 수 있다 — 둘은 다른 것이다.",
        f"보려면: `cd {repo.as_posix()} && git status --short && "
        "git log --oneline @{u}..HEAD`",
    ])


def render_dead(days: int, why: str) -> str:
    return "\n".join([
        f"⚠️ 한글 검사 점검이 {days}일째 못 돌았다 — 침묵은 합격이 아니다",
        "",
        f"까닭: {why}",
        "",
        "이 점검이 죽으면 전역 자산이 바뀌어도, GitHub 과 어긋나도 아무도 안 본다.",
    ])


def render(summary: str) -> str:
    return "\n".join([
        "⛔ 한글 검사 시스템 회귀 실패 — 하루 첫 세션 점검",
        "",
        "지키는 것: `assets/doc-style-check.py` · `hooks/doc-style-gate.py` · "
        "`skills/finalize-korean-document`",
        "이 셋 중 하나가 다른 곳에서 바뀌었을 수 있다.",
        "",
        summary,
        "",
        f"다시 보려면: `cd {REPO.as_posix()} && python -X utf8 -m pytest tests/ -q`",
    ])


def emit(text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart", "additionalContext": text}}, ensure_ascii=False))


def _self_test() -> int:
    now = datetime(2026, 9, 4, 10, 0)
    cases = [
        ("state 가 비면 돌린다", {}, True),
        ("오늘 이미 봤으면 안 돌린다", {"last_checked_date": "2026-09-04"}, False),
        ("어제 봤으면 돌린다", {"last_checked_date": "2026-09-03"}, True),
        ("방금 판단 불가였으면 참는다",
         {"last_attempt_at": (now - timedelta(hours=1)).isoformat()}, False),
        ("판단 불가한 지 오래면 다시 돌린다",
         {"last_attempt_at": (now - timedelta(hours=RETRY_HOURS + 1)).isoformat()}, True),
        ("망가진 시각은 막지 못한다", {"last_attempt_at": "그저께"}, True),
        ("본 날이 있으면 시각과 무관하게 안 돌린다",
         {"last_checked_date": "2026-09-04",
          "last_attempt_at": (now - timedelta(days=9)).isoformat()}, False),
    ]
    bad = 0
    for name, state, expected in cases:
        got = due(state, now)
        if got != expected:
            bad += 1
            print(f"  ❌ {name}: {expected} 여야 하는데 {got}")

    # ── 감시가 죽은 것을 언제 말하나 ─────────────────────────────────────────
    stale = [
        ("한 번도 판정이 안 났으면 잠자코 있는다", {}, None),
        ("어제 봤으면 하루", {"last_checked_date": "2026-09-03"}, 1),
        ("사흘 지났으면 사흘", {"last_checked_date": "2026-09-01"}, 3),
        ("망가진 날짜는 판단 불가", {"last_checked_date": "그저께"}, None),
    ]
    for name, state, expected in stale:
        got = stale_days(state, now)
        if got != expected:
            bad += 1
            print(f"  ❌ {name}: {expected} 여야 하는데 {got}")

    # ── git 판정 — 저장소가 아니면 침묵한다 ──────────────────────────────────
    got = check_git(Path(__file__).resolve().parent / "없는-디렉터리")
    if got is not None:
        bad += 1
        print(f"  ❌ 저장소가 아니면 판단 불가여야 하는데 {got}")

    print("통과 — 한글 검사 일일 점검" if not bad else f"실패 {bad}건")
    return 1 if bad else 0


def main() -> int:
    if "--self-test" in sys.argv:
        return _self_test()
    if os.environ.get("CLAUDE_BATCH_MODE") or os.environ.get("CLAUDE_SCHEDULED"):
        return 0
    try:
        sys.stdin.read()
    except (OSError, ValueError):
        pass

    now = datetime.now()
    state = read_state()
    if not due(state, now):
        return 0

    passed, summary = run_suite()
    if passed is None:
        # 판단 불가 — 그날을 「봤다」로 적지 않는다
        days = stale_days(state, now)
        state["last_attempt_at"] = now.isoformat(timespec="seconds")
        write_state(state)
        if days is not None and days >= STALE_DAYS:
            emit(render_dead(days, summary))
        return 0

    state["last_checked_date"] = now.date().isoformat()
    state.pop("last_attempt_at", None)
    write_state(state)

    notes = []
    if not passed:
        notes.append(render(summary))
    behind = check_git(REPO)
    if behind:
        notes.append(render_git(behind, REPO))
    if notes:
        emit("\n\n".join(notes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
