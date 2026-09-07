r"""SessionStart 훅: 하루 첫 세션에 한글 검사 시스템의 회귀 시험을 돌린다.

**왜 있나.** 이 시스템이 지키는 것은 배포된 전역 자산(`assets/doc-style-check.py`,
`hooks/doc-style-gate.py`, `skills/finalize-korean-document`)인데, 그 파일들은 **어느
프로젝트 세션에서든** 바뀐다. 시험은 `korean-writing-qa` 에 있어서, 그 저장소를 안 여는
날에는 아무도 안 돌린다. 실측(8/24~9/4): 자산이 바뀐 9일 중 9일이 덮였지만 그것은
마침 그 저장소에서 고쳤기 때문이고, 구조가 보장한 것이 아니다.

**설계**
- **하루 한 번**(첫 세션)만 돌린다. 그날 이미 봤으면 즉시 끝난다.
- **초록이면 아무 말도 안 한다.** 조용한 날에는 화면에 아무것도 안 나온다.
- **판단 불가면 침묵**(저장소 없음·pytest 없음). 그날을 「봤다」로 적지 않고,
  다만 6시간 안에는 다시 시도하지 않는다 — 세션마다 재시도하면 그게 소음이다.
- 실패하면 **막지 않고 알린다.** 게이트가 아니라 건강 검진이다.
- 배치·예약 실행(`CLAUDE_BATCH_MODE`·`CLAUDE_SCHEDULED`)에서는 즉시 끝.

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
        state["last_attempt_at"] = now.isoformat(timespec="seconds")
        write_state(state)
        return 0

    state["last_checked_date"] = now.date().isoformat()
    state.pop("last_attempt_at", None)
    write_state(state)
    if not passed:
        emit(render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
