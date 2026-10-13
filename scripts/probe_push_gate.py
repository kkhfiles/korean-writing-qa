"""push 게이트 부정 시험 — Claude Code 가 부르는 훅에 push 명령을 넣어, 막아야 할 상태를 막는지 본다.

    python -X utf8 scripts/probe_push_gate.py <빈 작업 폴더> [경우 이름 앞부분] [--repo-hook]

경우마다 임시 bare remote · 새 clone · 따로 떼어 낸 상태 파일을 쓴다(실제 기록을 안 건드림). 판정 기록은
판정기 코드(judge_layer2.judge)에 가짜 모델을 끼워 실제 경로로 만든다 — 모델은 안 부른다.
기본은 설치된 훅(~/.claude/hooks)을 본다 — 실제로 도는 것이 그것이다. `--repo-hook` 이면 저장소 훅.
결과는 <작업 폴더>/result.json · 종료 코드는 범위 안에서 기대와 어긋난 경우 수.

**왜 있나**(2026-10-13) — 단위 시험이 다 통과하는데도 실제 push 경로에서 여섯 갈래가 빠져나갔다
(HEAD 가 아닌 가지 push · 훅이 죽으면 통과 · 다른 저장소의 같은 이름 문서 · 지우기만 함 · 셸로 감싼 push).
게이트를 고치면 이것을 다시 돌린다 — 「막는다」는 주장은 이 시험이 반증하지 못했을 때만 쓴다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
if not ARGS:
    print(__doc__)
    raise SystemExit(2)
HOOK = (ROOT / "hooks" if "--repo-hook" in sys.argv else Path.home() / ".claude" / "hooks") / "doc-style-gate.py"
W = Path(ARGS[0]).resolve()
W.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import judge_layer2 as judge          # noqa: E402
import layer2_coverage as coverage    # noqa: E402
from test_judge_layer2 import FakeBackend  # noqa: E402

TOML = """[publish]
require = ["judgment"]
targets = ["README.md"]
base = "origin/main"
"""
CLAIM = "백업은 매일 새벽 두 시에 자동으로 실행됩니다."
COND = "단 백업 폴더가 비어 있지 않을 때만 실행합니다."
BASE = ["# 시험 문서", "", "업무 목록은 매일 오전 아홉 시에 갱신됩니다.", "", CLAIM, "",
        "알림은 담당자에게만 보냅니다.", ""]


def git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


class Case:
    def __init__(self, name: str, toml: str | None = TOML, base: list[str] = BASE):
        self.name = name
        self.dir = W / name
        self.dir.mkdir()
        self.state = self.dir / "state"
        self.state.mkdir()
        self.env = dict(os.environ,
                        KOREAN_QA_JUDGE_LOG=str(self.state / "judge.jsonl"),
                        KOREAN_QA_ANSWER_LOG=str(self.state / "answers.jsonl"),
                        KOREAN_QA_DECISION_LOG=str(self.state / "decisions.jsonl"),
                        KOREAN_QA_DISMISS_LOG=str(self.state / "dismissals.jsonl"),
                        KOREAN_CHECK_RECORD=str(self.state / "records.jsonl"))
        self.bind()
        remote = self.dir / "remote.git"
        git(self.dir, "init", "-q", "--bare", "-b", "main", str(remote))
        self.repo = self.dir / "work"
        git(self.dir, "clone", "-q", str(remote), str(self.repo))
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "config", "user.email", "t@t")
        git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")
        if toml is not None:
            (self.repo / "korean-qa.toml").write_text(toml, encoding="utf-8")
        self.write(base)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "push", "-q", "origin", "main")
        self.doc = self.repo / "README.md"

    def bind(self) -> None:
        """판정기·장부 모듈이 이 경우의 상태 파일을 쓰게 한다."""
        judge.LOG = coverage.LOG = Path(self.env["KOREAN_QA_JUDGE_LOG"])
        coverage.ANSWERS = Path(self.env["KOREAN_QA_ANSWER_LOG"])
        coverage.DECISIONS = Path(self.env["KOREAN_QA_DECISION_LOG"])
        coverage.DISMISSALS = Path(self.env["KOREAN_QA_DISMISS_LOG"])

    def write(self, lines: list[str]) -> None:
        (self.repo / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def commit(self, lines: list[str], msg: str = "change") -> None:
        self.write(lines)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)

    def judge(self, reply=None, fail: bool = False, since: bool = True, deletions: bool = True) -> dict:
        self.bind()
        base = coverage.base_lines(self.doc, "origin/main") if since else None
        targets, anchors = None, None
        if since:
            lines = coverage.read_doc(self.doc).splitlines()
            key = coverage.doc_key(self.doc)
            targets = coverage.open_lines(lines, base, coverage.judged(key, judge.LOG))
            if deletions and base:
                anchors = dict(coverage.open_deletions(lines, base, coverage.deleted_seen(key, judge.LOG)))
        return judge.judge(self.doc, "opus", 10, FakeBackend(reply or [], fail=fail).pair(),
                           targets, base, anchors)

    def record_judgment(self) -> None:
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "check_record.py"),
                        "record", str(self.doc), "--stage", "judgment", "--verdict", "pass",
                        "--note", "시험 — 판정 끝 · 남긴 지적 없음"],
                       env=self.env, capture_output=True, text=True, encoding="utf-8", check=True)

    def push_hook(self, cmd: str = "git push origin main", tool: str = "Bash",
                  cwd: Path | None = None) -> dict:
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
                   "tool_input": {"command": cmd}, "cwd": str(cwd or self.repo), "session_id": "e2e"}
        p = subprocess.run([sys.executable, str(HOOK), "--probe"], input=json.dumps(payload),
                           capture_output=True, text=True, encoding="utf-8", env=self.env)
        denied = '"permissionDecision": "deny"' in p.stdout
        reason = ""
        if denied:
            reason = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        return {"denied": denied, "rc": p.returncode, "reason": reason,
                "stderr": p.stderr.strip()[-600:]}


def fact(line: int, phrase: str) -> dict:
    return {"line": line, "phrase": phrase, "category": "근거 없는 단정", "fix": phrase,
            "why": "실제 실행 시각을 문서만으로 알 수 없음", "decide": "fix",
            "check": "백업 작업의 실제 실행 시각과 주기"}


def plain_fix(line: int, phrase: str) -> dict:
    return {"line": line, "phrase": phrase, "category": "업무에서 쓰는 말로 쓰기",
            "fix": phrase + "(고침)", "why": "시험", "decide": "fix"}


def ask(line: int, phrase: str) -> dict:
    return {"line": line, "phrase": phrase, "category": "사용자 결정", "fix": "",
            "why": "의도가 바뀌는지 문서만으로 못 가름", "decide": "ask"}


results = []


def run(name: str, expect: str, scope: str, fn) -> None:
    """expect — 안전한 결과(deny/allow) · scope — 보장 범위 안(in)인지 밖(out)인지."""
    try:
        got = fn()
        actual = "deny" if got["denied"] else "allow"
        if got["rc"] not in (0,) and not got["denied"]:
            actual = f"crash(rc={got['rc']})"
    except Exception as e:  # 시험 도구 자체의 실패 — 결과로 세지 않는다
        got, actual = {"error": f"{type(e).__name__}: {e}"}, "harness-error"
    ok = actual == expect
    results.append({"case": name, "expect": expect, "actual": actual, "ok": ok, "scope": scope,
                    "reason": (got.get("reason") or "")[:400], "stderr": got.get("stderr", ""),
                    "error": got.get("error", "")})
    print(f"{'OK  ' if ok else 'FAIL'} {name:52} 기대 {expect:5} · 실제 {actual}")


NEW = "마감이 가까운 업무를 맨 위에 표시합니다."


def with_new(lines: list[str]) -> list[str]:
    return lines[:-1] + [NEW, ""]


# ── 1. 열린 지적 · 미판정 ────────────────────────────────────────────────

def c_open_fix():
    c = Case("01-open-fix")
    c.commit(with_new(BASE))
    c.judge([plain_fix(8, "맨 위에 표시합니다")])
    c.record_judgment()
    return c.push_hook()


def c_open_ask():
    c = Case("02-open-ask")
    c.commit(with_new(BASE))
    c.judge([ask(8, "맨 위에 표시합니다")])
    c.record_judgment()
    return c.push_hook()


def c_unjudged():
    c = Case("03-unjudged")
    c.commit(with_new(BASE))
    return c.push_hook()


def c_no_record():
    c = Case("03b-judged-no-record")
    c.commit(with_new(BASE))
    c.judge([])
    return c.push_hook()


def c_clean():
    c = Case("04-clean-positive-control")
    c.commit(with_new(BASE))
    c.judge([])
    c.record_judgment()
    return c.push_hook()


def c_one_char():
    c = Case("05-one-char-after-pass")
    c.commit(with_new(BASE))
    c.judge([])
    c.record_judgment()
    first = c.push_hook()
    if first["denied"]:
        raise RuntimeError("통과해야 할 첫 push 가 막힘: " + first["reason"][:200])
    c.commit(with_new(BASE)[:-2] + [NEW.replace("가까운", "가까이 온"), ""])
    return c.push_hook()


# ── 2. 사실 확인 지적이 붙은 줄을 지우기 · 나누기 · 옮기기 ───────────────

def fact_case(name: str) -> Case:
    """기준 판의 주장 줄에 사실 확인 지적이 열린 채 push 된 상태에서 출발."""
    c = Case(name)
    c.judge([fact(5, "매일 새벽 두 시에 자동으로 실행됩니다")], since=False)
    return c


def c_fact_deleted_with_new_line():
    c = fact_case("06a-fact-line-deleted+new-line")
    c.commit(with_new([l for l in BASE if l != CLAIM]))
    c.judge([])
    c.record_judgment()
    return c.push_hook()


def c_fact_deleted_only():
    c = fact_case("06b-fact-line-deleted-only")
    c.commit([l for l in BASE if l != CLAIM])
    return c.push_hook()


def c_deleted_and_looked_at():
    c = fact_case("06b2-deleted-and-judged-clean")
    c.commit([l for l in BASE if l != CLAIM])
    c.judge([])
    return c.push_hook()


def c_fact_split():
    c = fact_case("06c-fact-line-split")
    split = BASE[:4] + ["백업은 매일 새벽 두 시에 실행됩니다.", "실행은 자동으로 합니다."] + BASE[5:]
    c.commit(split)
    c.judge([])
    c.record_judgment()
    return c.push_hook()


def c_fact_moved():
    c = fact_case("06d-fact-line-moved+new-line")
    moved = [l for l in BASE if l != CLAIM][:-1] + [NEW, "", CLAIM, ""]
    c.commit(moved)
    c.judge([])
    c.record_judgment()
    return c.push_hook()


def c_fact_edited():
    c = fact_case("06e-fact-line-edited")
    c.commit([l if l != CLAIM else "백업은 매주 월요일 새벽에 자동으로 실행됩니다." for l in BASE])
    c.judge([])
    c.record_judgment()
    return c.push_hook()


# ── 3. 일반 지적 줄을 필수 조건과 함께 지우기 ────────────────────────────

def c_fix_deleted_with_condition():
    base = BASE[:6] + [COND, ""] + BASE[6:]
    c = Case("07-fix-line-deleted-with-condition", base=base)
    c.judge([plain_fix(7, "비어 있지 않을 때만")], since=False)
    c.commit(with_new([l for l in base if l != COND]))
    c.judge([], deletions=False)          # 새 줄만 판정 — 지운 자리는 안 봄
    return c.push_hook()


def c_condition_loss_flagged():
    base = BASE[:6] + [COND, ""] + BASE[6:]
    c = Case("07b-condition-deleted-judge-flags-it", base=base)
    c.commit([l for l in base if l != COND])
    # 대표 줄(지운 자리 다음 한글 줄 = 7행 「알림은…」)에 판정기가 뜻 바뀜을 짚음
    c.judge([{"line": 7, "phrase": "알림은 담당자에게만 보냅니다", "category": "고치다 뜻이 바뀐 곳",
              "fix": "단 백업 폴더가 비어 있지 않을 때만 실행합니다. 알림은 담당자에게만 보냅니다.",
              "why": "실행 조건이 빠짐", "decide": "fix"}])
    return c.push_hook()


# ── 4. 판정 실패 · 깨진 기록 · 설정 ──────────────────────────────────────

def c_judge_failed():
    c = Case("08a-judge-call-failed")
    c.commit(with_new(BASE))
    try:
        c.judge(fail=True)
    except TimeoutError:
        pass                      # 판정기 실행체는 실패를 알리고 끝남 — 기록이 남든 말든 게이트가 막아야 함
    c.record_judgment()
    return c.push_hook()


def c_judge_log_garbage():
    c = Case("08b-judge-log-garbage-line")
    c.commit(with_new(BASE))
    c.judge([plain_fix(8, "맨 위에 표시합니다")])
    c.record_judgment()
    with open(c.env["KOREAN_QA_JUDGE_LOG"], "a", encoding="utf-8") as f:
        f.write("{깨진 줄\n")
    return c.push_hook()


def c_judge_log_bad_types():
    c = Case("08c-judge-log-bad-field-types")
    c.commit(with_new(BASE))
    c.judge([plain_fix(8, "맨 위에 표시합니다")])
    c.record_judgment()
    p = Path(c.env["KOREAN_QA_JUDGE_LOG"])
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows[-1]["fixes"] = "문자열"           # 목록이어야 할 칸이 다른 모양
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return c.push_hook()


def c_dismiss_log_garbage():
    c = Case("08d-dismiss-log-garbage")
    c.commit(with_new(BASE))
    c.judge([plain_fix(8, "맨 위에 표시합니다")])
    c.record_judgment()
    Path(c.env["KOREAN_QA_DISMISS_LOG"]).write_text("{깨진 줄\n", encoding="utf-8")
    return c.push_hook()


def c_record_store_garbage():
    c = Case("08e-record-store-garbage")
    c.commit(with_new(BASE))
    c.judge([])
    Path(c.env["KOREAN_CHECK_RECORD"]).write_text("{깨진 줄\n", encoding="utf-8")
    return c.push_hook()


def c_record_store_unreadable():
    c = Case("08f-record-store-is-a-folder")
    c.commit(with_new(BASE))
    c.judge([])
    Path(c.env["KOREAN_CHECK_RECORD"]).mkdir()
    return c.push_hook()


def c_broken_toml():
    c = Case("09a-broken-toml")
    (c.repo / "korean-qa.toml").write_text("[publish\nrequire = \n", encoding="utf-8")
    c.commit(with_new(BASE))
    return c.push_hook()


def c_no_toml():
    c = Case("09b-no-config", toml=None)
    c.commit(with_new(BASE))
    return c.push_hook()


# ── 5. push 명령 모양 ────────────────────────────────────────────────────

def variant(name: str, cmd_of, tool: str = "Bash", cwd_of=None):
    def fn():
        c = Case(name)
        c.commit(with_new(BASE))
        c.judge([plain_fix(8, "맨 위에 표시합니다")])
        c.record_judgment()
        cwd = cwd_of(c) if cwd_of else c.repo
        return c.push_hook(cmd_of(c), tool=tool, cwd=cwd)
    return fn


def c_other_ref():
    """HEAD 는 깨끗한 가지 · 미는 것은 열린 지적이 있는 가지."""
    c = Case("10f-push-other-ref-than-HEAD")
    git(c.repo, "checkout", "-q", "-b", "dirty")
    c.commit(with_new(BASE))
    c.judge([plain_fix(8, "맨 위에 표시합니다")])
    c.record_judgment()
    git(c.repo, "checkout", "-q", "main")
    return c.push_hook("git push origin dirty:main")


# ── 6. 다른 저장소의 같은 이름 문서 ──────────────────────────────────────

def c_cross_repo():
    """다른 저장소의 README.md 에 남긴 처리 기록이 이 저장소의 같은 글줄을 닫나."""
    a = Case("11-cross-repo-dismissal")
    a.commit(with_new(BASE))
    a.judge([plain_fix(8, "맨 위에 표시합니다")])
    a.record_judgment()
    # 같은 상태 파일을 쓰는 다른 저장소 — 같은 줄에 「확인함」을 남김
    other = a.dir / "other"
    git(a.dir, "init", "-q", "-b", "main", str(other))
    (other / "README.md").write_text((a.repo / "README.md").read_text(encoding="utf-8"),
                                     encoding="utf-8")
    a.bind()
    rc = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "judge_layer2.py"),
                         str(other / "README.md"), "--dismiss", "8", "--reason", "대상아님",
                         "--note", "다른 저장소의 화면 문구라 이 규칙 대상이 아님"],
                        env=a.env, capture_output=True, text=True, encoding="utf-8")
    # 열쇠에 저장소 식별자가 들어가 다른 저장소에서는 이 지적이 아예 안 보인다 — 처리 기록이 거절되면
    # 새는 길이 없는 것이다. 받아졌더라도 이 저장소 push 는 막혀야 한다.
    return a.push_hook()


CASES = [
    ("01 미해결 고칠 지적", "deny", "in", c_open_fix),
    ("02 답 없는 사람 확인", "deny", "in", c_open_ask),
    ("03 판정 안 한 새 줄", "deny", "in", c_unjudged),
    ("03b 판정했으나 손 판정 기록 없음(판정기 기록으로 계산)", "allow", "in", c_no_record),
    ("04 깨끗함(양성 대조)", "allow", "in", c_clean),
    ("05 통과 뒤 한 글자 변경", "deny", "in", c_one_char),
    ("06a 사실 확인 줄 삭제 + 다른 새 줄 · 지운 자리도 판정(문제 없음)", "allow", "in", c_fact_deleted_with_new_line),
    ("06b 사실 확인 줄 삭제만 · 판정 안 함", "deny", "in", c_fact_deleted_only),
    ("06b2 지우기만 함 · 판정기가 지운 자리를 봄(문제 없음)", "allow", "in", c_deleted_and_looked_at),
    ("06c 사실 확인 줄 나누기", "deny", "in", c_fact_split),
    ("06d 사실 확인 줄 옮기기 + 새 줄", "deny", "in", c_fact_moved),
    ("06e 사실 확인 줄 고쳐 쓰기", "deny", "in", c_fact_edited),
    ("07 필수 조건 줄 삭제 · 지운 자리 판정 안 함", "deny", "in", c_fix_deleted_with_condition),
    ("07b 필수 조건 줄 삭제 · 판정기가 뜻 바뀜을 짚음", "deny", "in", c_condition_loss_flagged),
    ("08a 판정 호출 실패", "deny", "in", c_judge_failed),
    ("08b 판정 기록에 깨진 줄", "deny", "in", c_judge_log_garbage),
    ("08c 판정 기록 칸 모양이 틀림", "deny", "in", c_judge_log_bad_types),
    ("08d 처리 기록이 깨짐", "deny", "in", c_dismiss_log_garbage),
    ("08e 통과 기록 저장소가 깨짐(판정기 기록으로 계산 · 저장소 안 봄)", "allow", "in", c_record_store_garbage),
    ("08f 통과 기록 저장소를 못 읽음(판정기 기록으로 계산 · 저장소 안 봄)", "allow", "in", c_record_store_unreadable),
    ("09a 설정 파일이 깨짐", "deny", "in", c_broken_toml),
    ("09b 설정 없음(켜지 않은 저장소)", "allow", "out", c_no_toml),
    ("10a git push(인자 없음)", "deny", "in", variant("10a-bare-push", lambda c: "git push")),
    ("10b git -C <경로> push", "deny", "in",
     variant("10b-dash-C", lambda c: f'git -C "{c.repo.as_posix()}" push origin main', cwd_of=lambda c: c.dir)),
    ("10c cd <경로> && git push", "deny", "in",
     variant("10c-cd-and", lambda c: f'cd "{c.repo.as_posix()}" && git push origin main', cwd_of=lambda c: c.dir)),
    ("10d PowerShell 도구", "deny", "in", variant("10d-powershell", lambda c: "git push origin main", tool="PowerShell")),
    ("10e git push origin HEAD:main", "deny", "in", variant("10e-head-refspec", lambda c: "git push origin HEAD:main")),
    ("10f HEAD 가 아닌 가지를 push", "deny", "in", c_other_ref),
    ("10g git commit && git push 한 줄", "deny", "in",
     variant("10g-commit-and-push", lambda c: 'git commit --allow-empty -m "x" && git push')),
    ("10h bash -c 로 감싼 push", "deny", "in", variant("10h-bash-c", lambda c: "bash -c 'git push origin main'")),
    ("11 다른 저장소의 같은 이름 문서 처리 기록", "deny", "in", c_cross_repo),
]

if __name__ == "__main__":
    only = ARGS[1] if len(ARGS) > 1 else ""
    for name, expect, scope, fn in CASES:
        if name.startswith(only):
            run(name, expect, scope, fn)
    (W / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in results if not r["ok"] and r["scope"] == "in"]
    print(f"\n{len(results) - len(bad)}/{len(results)} 기대대로 · 범위 안 어긋남 {len(bad)} · 훅 {HOOK}")
    raise SystemExit(len(bad))
