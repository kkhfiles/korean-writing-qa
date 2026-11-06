"""push 한 커밋의 GitHub 전체 시험이 끝날 때까지 기다렸다가 결과와 실패한 시험 이름을 낸다.

    python -X utf8 scripts/wait_ci.py            # 지금 HEAD 커밋 — push 직후 백그라운드로
    python -X utf8 scripts/wait_ci.py <커밋>
    python -X utf8 scripts/wait_ci.py --hook     # Claude Code push 직후 훅(.claude/settings.json)

**왜 있나.** 전체 시험은 이 PC 에서 통과해도 CI 에서 깨질 수 있다 — 개인 항목 스위치와 Claude 설치처럼
이 PC 에만 있는 조건에 기대는 시험이 그렇다. 2026-11-02~11-05 에 그런 시험 다섯 개 때문에 CI 가 나흘 동안
실패했는데, 알림이 하루 첫 세션에만 떠서 그 사이 커밋 스무 개 남짓이 실패한 채 쌓였다.

**종료 코드** — 0 통과 · 1 실패(실패한 시험 이름을 냄) · 2 판정 불가(`gh` 없음, 실행을 못 찾음, 시간 초과).
판정 불가를 통과로 읽지 않는다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time

APPEAR_WAIT = 180      # push 뒤 실행이 생길 때까지 기다리는 시간(초)
FINISH_WAIT = 1500     # 실행이 끝날 때까지(전체 시험은 7~10분)
POLL = 30
FAILED_NAME = re.compile(r"(?:FAIL|ERROR): (test_\w+) \(([\w.]+)\)")


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True).stdout


def failed_tests(log: str) -> list[str]:
    """CI 실패 기록에서 실패한 시험 이름을 순서대로, 겹침 없이."""
    seen: list[str] = []
    for name, where in FAILED_NAME.findall(log):
        full = f"{where}.{name}" if not where.endswith(name) else where
        if full not in seen:
            seen.append(full)
    return seen


def find_run(sha: str) -> dict | None:
    rows = json.loads(gh("run", "list", "--commit", sha, "--json", "databaseId,status,conclusion,url,workflowName"))
    return rows[0] if rows else None


def wait(sha: str) -> int:
    started = time.time()
    run = None
    while run is None:
        run = find_run(sha)
        if run is None:
            if time.time() - started > APPEAR_WAIT:
                print(f"⚠️ {sha[:7]} 의 GitHub 시험 실행을 {APPEAR_WAIT}초 안에 못 찾았습니다 — push 가 안 됐거나 "
                      "CI 가 꺼져 있습니다(판정 불가)")
                return 2
            time.sleep(POLL)
    while run["status"] != "completed":
        if time.time() - started > FINISH_WAIT:
            print(f"⚠️ {sha[:7]} 의 GitHub 시험이 {FINISH_WAIT}초 안에 안 끝났습니다(판정 불가) — {run['url']}")
            return 2
        time.sleep(POLL)
        run = find_run(sha) or run
    if run["conclusion"] == "success":
        print(f"✅ {sha[:7]} GitHub 전체 시험 통과 — {run['url']}")
        return 0
    names = failed_tests(gh("run", "view", str(run["databaseId"]), "--log-failed"))
    print(f"⛔ {sha[:7]} GitHub 전체 시험 {run['conclusion']} — {run['url']}")
    for n in names:
        print(f"  - {n}")
    if not names:
        print("  (실패한 시험 이름을 못 읽음 — 시험 밖 단계가 실패했을 수 있음)")
    print("  이 PC 에서만 통과하는 시험이면 개인 설정이나 설치된 도구에 기대는지 먼저 본다")
    return 1


def _push_target(command: str):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "public_push_gate", Path(__file__).resolve().parents[1] / "hooks" / "public-push-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.push_target(command)


def hook() -> int:
    """push 를 실행한 직후 세션에 대기 명령을 알린다 — 훅은 오래 기다릴 수 없어 대기는 세션이 백그라운드로 한다."""
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    command = (event.get("tool_input") or {}).get("command") or ""
    # push 판별의 정본(`hooks/public-push-gate.py`)을 쓴다 — 따옴표 안과 커밋 메시지 본문을 안 본다.
    # 손으로 짠 정규식은 `grep "git.*push"` 와 메시지 첫머리의 「push」에도 알렸다(2026-11-06)
    if _push_target(command) is None:
        return 0
    note = ("이 저장소에 push 했으면 GitHub 전체 시험 결과를 확인한다 — "
            "`python -X utf8 scripts/wait_ci.py` 를 백그라운드로 실행하고, 끝나면 결과(실패면 시험 이름)를 사용자에게 보고")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}},
                     ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--hook"]:
        return hook()
    try:
        # gh 는 전체 SHA 로만 실행을 찾는다 — 짧은 표기나 가지 이름도 여기서 풀어 둔다
        sha = subprocess.run(["git", "rev-parse", argv[0] if argv else "HEAD"], capture_output=True, text=True,
                             check=True).stdout.strip()
        return wait(sha)
    except FileNotFoundError:
        print("⚠️ gh 나 git 이 없어 GitHub 시험 결과를 못 봅니다(판정 불가)")
        return 2
    except subprocess.CalledProcessError as e:
        print(f"⚠️ {' '.join(e.cmd[:3])} 실패(판정 불가) — {(e.stderr or '').strip()[:200]}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
