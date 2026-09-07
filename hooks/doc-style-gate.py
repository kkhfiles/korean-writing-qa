"""문서 서술 규칙과 자연스러운 한글 검사기를 쓰는 순간과 발행 직전에 부른다.

**왜 두 곳인가.** 발행 직전만 두면 다 써 놓은 뒤에 고치게 되고, 쓰기마다 두면
초안까지 걸려 소음이 된다. 그래서 쓰기 시점은 **오류만·파일당 세션 1회**로 상한을
두고, 발행 시점은 전부 낸다(공유 자료는 발행 전 오류 0).

| 이벤트 | 무엇을 검사하나 | 무엇을 내나 |
|---|---|---|
| `PostToolUse` Write·Edit·MultiEdit | 방금 쓴 `.md`/`.html` | 오류만 · 같은 파일은 세션에 한 번 |
| `PreToolUse` Artifact·Bash·PowerShell | 발행 대상 파일 | 오류와 주의 전부 |

**차단하지 않는다.** 오탐 하나가 발행을 막으면 그 다음부터 아무도 안 본다.
`additionalContext`로 내용을 넘겨 그 자리에서 고치게 한다.

**검사에서 빼는 것** — 스크래치패드·임시 디렉터리·`~/.claude/` 자체·`node_modules`.
작업 문서에는 규칙을 강제하지 않는다는 원칙 그대로다.

상태 파일: `~/.claude/state/doc-style-seen.json`  `{세션키: {파일: 마지막검사시각}}`
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

HOME = Path.home()


def _find(env_name, installed, in_repo):
    """검사기를 찾는다 — 환경 변수 · 설치본 · 저장소 순.

    설치된 Claude Code 안에서는 두 번째가 맞다. 저장소를 클론만 한 기계에서
    시험을 돌릴 때는 설치본이 없으므로 세 번째(훅 파일의 형제)를 쓴다.
    셋째 길이 없던 동안 그런 기계에서 시험 18건이 「검사기 없음」으로 깨졌다.
    """
    from os import environ
    override = environ.get(env_name)
    if override:
        return Path(override)
    if installed.is_file():
        return installed
    sibling = Path(__file__).resolve().parent.parent / in_repo
    return sibling if sibling.is_file() else installed


CHECKER = _find(
    "KOREAN_QA_CHECKER",
    HOME / ".claude" / "assets" / "doc-style-check.py",
    Path("assets") / "doc-style-check.py",
)
KOREAN_CHECKER = _find(
    "KOREAN_QA_SKILL_CHECK",
    HOME / ".claude" / "skills" / "finalize-korean-document" / "scripts" / "check.py",
    Path("skills") / "finalize-korean-document" / "scripts" / "check.py",
)
STATE = HOME / ".claude" / "state" / "doc-style-seen.json"
TTL = 12 * 3600          # 세션키를 못 구할 때 기록이 영원히 쌓이지 않게 한다
DOC = re.compile(r"\.(?:md|html)$", re.I)
KOREAN_DOC = re.compile(r"\.(?:md|html|txt|json|jsonl|ya?ml|properties)$", re.I)
# 작업 문서 — 규칙을 강제하지 않는다
SKIP = re.compile(r"scratchpad|[\\/]\.claude[\\/]|[\\/]Temp[\\/]|node_modules|[\\/]\.git[\\/]", re.I)
# 검사기가 「값 슬롯을 못 찾았다」고 낼 때의 **줄 모양**. 검사기 973행이 정본이다.
#   예전에는 출력 전체에서 「검사 불가」라는 **문자열**을 찾았다. 그래서 문서 본문에
#   그 말이 든 줄이 지적으로 실리면 그 파일의 지적이 통째로 사라졌다(실측 재현).
#   이 저장소 문서 여럿이 그 말을 쓴다 — 자기 문서를 자기가 못 보게 만드는 함정이었다.
BLIND = re.compile(r"^⛔ .*값 슬롯 미인식", re.M)
# 발행 명령 — 사람이 보게 되는 순간.
#   notion.py 는 `--profile personal create` 처럼 **플래그가 서브커맨드 앞에 온다**.
#   서브커맨드를 바로 뒤에서 찾으면 그 형태를 놓친다(실제 SKILL.md 43행 용법).
PUBLISH = re.compile(
    r"notion\.py\b[^|;&\n]{0,120}?\s(?:create|append|row-create)\b"
    r"|notion_publish\.py\b"
    r"|marp-team[\\/]marp-cli|npx\s+@marp-team"
    r"|md-to-pdf[\\/]scripts[\\/]convert\.py",
    re.I,
)
# 미리보기라 아무것도 나가지 않는다 — 게이트를 걸 이유가 없다
DRYRUN = re.compile(r"--dry-run\b")


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save(data):
    now = time.time()
    kept = {k: v for k, v in data.items() if any(t > now - TTL for t in v.values())}
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(kept, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


# 매체를 가리지 않는 규칙 — 「어색한 한국어」 계열. 산문에 돌려도 오탐이 아니다.
# 쓰는 순간의 소음을 줄이는 데만 쓴다. 산문 판정에는 쓰지 않는다.
ALWAYS = ("「~하는 자리」", "절단형", "모호한 지칭", "지시어 확인", "평가 수식어")
# 검사기가 형식을 안 적은 산문으로 보고 물어보는 줄
FORM_ASK = "형식 미표기"


def is_always(line):
    return any(k in line for k in ALWAYS)


def call_checker(path, *extra):
    """검사기를 한 번 돌린다. 실행이 안 되면 None — 빈 결과로 바꾸지 않는다."""
    try:
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(CHECKER), str(path), *extra],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout or ""


def run_checker(path, errors_only):
    """검사기를 돌려 사람이 읽을 줄만 돌려준다. **못 돌린 것은 알린다.**

    **침묵하지 않는 까닭**(2026-09-03) — 예전에는 검사기가 없거나 죽거나 값 슬롯을
    못 찾으면 빈 문자열을 냈다. 발행하는 사람에게는 「지적 없음」과 구별이 안 돼
    합격으로 읽혔다. 스킬 검사기는 같은 상황을 경로까지 찍어 알리는데 지적의
    대부분을 내는 이쪽이 조용히 죽고 있었다.

    「판단 불가 시 침묵」은 **아무도 안 거르는 보고**에 쓰는 규칙이다. 이 보고는
    사람이 읽으므로 알리는 쪽이 맞다(`references/work-principles.md`
    「검사·규칙을 설계할 때」의 세 갈래).

    `errors_only`(쓰는 순간)에는 **매체 무관 규칙만** 낸다. 초안까지 걸리면 소음이다.

    **산문 판정은 훅이 하지 않는다.** 예전에는 서술형 지적 수를 세어 접었는데,
    실측하니 378건 중 44건에서 접혔고 그중 40건이 산문이 아니었다 — 표와 라벨이
    뼈대인 문서에 근거 문단이 붙은 형태였고, 그 문서에서 맞는 지적 1,043건이
    발행 직전에 가려졌다. 접는 기준을 검사기 한 곳으로 모은다.

    검사기가 「형식 미표기」로 물어보면 그때만 산문으로 한 번 더 물어본다.
    무엇을 뺄지는 검사기가 정한다 — 훅은 목록을 따로 갖지 않는다.
    """
    if not CHECKER.exists():
        return f"⚠️ 전역 문서 검사를 못 돌렸다 — 검사기 없음 ({CHECKER})"
    out = call_checker(path)
    if out is None:
        return "⚠️ 전역 문서 검사를 못 돌렸다 — 실행 실패 또는 25초 초과"
    # 부분 검사여도 **잡힌 것은 함께 낸다.** 알림만 내고 지적을 버리면 실제로
    # 잡은 오류가 사라진다(실측: 값 슬롯을 못 찾은 파일에서 오류 2건을 버리고 있었다).
    blind = BLIND.search(out)

    note = None
    if not errors_only and FORM_ASK in out:
        prose = call_checker(path, "--form", "prose")
        if prose is not None and not BLIND.search(prose):
            out = prose
            note = ("(형식을 안 적어 산문으로 보고 개조식 지적을 뺐다 — "
                    "머리말에 `form: prose` 를 적으면 확정되고, 개조식이 맞으면 "
                    "`form: structured`)")

    hits = [l for l in out.splitlines() if "❌" in l or (not errors_only and "⚠️" in l)]
    if errors_only:
        hits = [l for l in hits if is_always(l)]
    hits = condense(hits)[:12]
    if blind:
        hits.insert(0, "⚠️ 값 슬롯을 못 찾아 부분 검사만 됐다 — 합격이 아니라 "
                       "안 본 것이다 · 표·목록·「라벨: 값」으로 다시 쓸 것")
    if note:
        hits.append(note)
    return "\n".join(hits)


def run_korean_checker(path):
    """사용자 확정 표현을 검사한다. 실행 실패는 합격처럼 숨기지 않는다."""
    if not KOREAN_CHECKER.is_file():
        return f"한글 문서 자동 검사를 수행하지 못했습니다: 검사기 없음 ({KOREAN_CHECKER})"
    try:
        result = subprocess.run(
            [
                sys.executable, "-X", "utf8", "-B", str(KOREAN_CHECKER), str(path),
                "--profile", "general", "--format", "json",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"한글 문서 자동 검사를 수행하지 못했습니다: {exc}"
    if result.returncode:
        detail = (result.stderr or result.stdout or f"exit code {result.returncode}").strip()
        return f"한글 문서 자동 검사를 수행하지 못했습니다: {detail}"
    try:
        parsed = json.loads(result.stdout)
    except (TypeError, ValueError) as exc:
        return f"한글 문서 자동 검사를 수행하지 못했습니다: 잘못된 검사 결과 ({exc})"
    findings = parsed.get("findings") if isinstance(parsed, dict) else None
    if not isinstance(findings, list):
        return "한글 문서 자동 검사를 수행하지 못했습니다: 검사 결과 형식 오류"
    if not findings:
        return ""
    # 스킬을 부르라는 안내는 여기 두지 않는다 — 이 함수는 1층이 뭔가 잡았을
    # 때만 도달하는데, 1층 회수율이 0.057이라 안내도 그만큼만 떴다(발행 640회
    # 중 59회 · 9.2%). **1층이 아무것도 못 잡은 때가 2층이 가장 필요한 때다.**
    # 안내는 발행 경로에서 따로 낸다(아래 finalize_notice).
    lines = ["한글 문서 최종화 검사"]
    for finding in findings[:8]:
        if not isinstance(finding, dict):
            continue
        line_number = finding.get("line_number") or "?"
        action = finding.get("action") or "review_context"
        original = finding.get("original") or "?"
        suggestion = finding.get("suggestion")
        tail = f" → {suggestion}" if suggestion else " — 문맥에 맞는 표현 검토"
        lines.append(f"[{action}] {line_number}행 {original}{tail}")
    remaining = len(findings) - (len(lines) - 1)
    if remaining > 0:
        lines.append(f"그 밖의 지적 {remaining}건")
    return "\n".join(lines)


def condense(lines):
    """같은 지적이 여러 줄이면 한 줄로 접고 건수를 붙인다.

    같은 낱말이 열두 줄 반복되면 그 자체가 소음이라 정작 다른 지적을 가린다.

    **인용어가 없는 지적도 접는다.** 예전에는 `「낱말」` 이 실린 지적만 접어서,
    조언 문구가 매번 똑같은 「값 안 굵게」가 한 줄도 안 접혔다. 실측하니 발행
    직전 화면에 뜨는 것의 46%가 그 한 종류였고, 문서 9%는 화면이 그것만으로
    채워졌다. 줄 번호를 뗀 뒤 문구가 같으면 같은 지적으로 본다 — 문장이 실리는
    지적(서술형 종결 등)은 문구가 서로 달라 그대로 남는다.
    """
    seen, out = {}, []
    for l in lines:
        m = re.match(r"\s*[❌⚠️]+\s*\[([^\]]+)\]\s*(\d+행)?\s*(.*)$", l)
        if not m:
            out.append(l)
            continue
        quoted = re.match(r"\s*(「[^」]+」)", m.group(3) or "")
        # 인용어가 있으면 그것으로, 없으면 조언 문구 자체로 같음을 판정한다
        key = (m.group(1), quoted.group(1) if quoted else (m.group(3) or "").strip())
        if key in seen:
            seen[key][1] += 1
            continue
        seen[key] = [len(out), 1]
        out.append(l)
    for key, (idx, n) in seen.items():
        if n > 1:
            out[idx] = f"{out[idx]}  (같은 지적 {n}곳)"
    return out


def resolve(p):
    """명령줄에서 뽑은 경로를 이 PC에서 열리는 형태로 되돌린다.

    Bash 도구는 Git Bash라 `~/...`·`/c/Users/...` 형태가 섞여 온다. 그대로 두면
    `os.path.exists`가 거짓으로 False를 내고 **위반이 있어도 조용히 통과한다** —
    게이트에서 가장 나쁜 실패다.
    """
    p = os.path.expanduser(p)
    m = re.match(r"^/([a-zA-Z])/(.*)$", p)
    if m:
        p = f"{m.group(1).upper()}:/{m.group(2)}"
    return p


def targets(payload):
    """이번 호출에서 검사할 파일과 모드를 정한다."""
    ev = payload.get("hook_event_name") or ""
    name = payload.get("tool_name") or ""
    inp = payload.get("tool_input") or {}

    if ev == "PostToolUse" and name in ("Write", "Edit", "MultiEdit"):
        fp = str(inp.get("file_path") or "")
        if fp and DOC.search(fp) and not SKIP.search(fp):
            return [fp], True, "once"

    if ev == "PreToolUse":
        if name == "Artifact":
            fp = str(inp.get("file_path") or "")
            if fp and DOC.search(fp):
                return [fp], False, "always"
        if name in ("Bash", "PowerShell"):
            cmd = str(inp.get("command") or "")
            if PUBLISH.search(cmd) and not DRYRUN.search(cmd):
                found = [resolve(m) for m in
                         re.findall(r'["\']?([^\s"\']+\.(?:md|html))["\']?', cmd)]
                found = [m for m in found if m and not SKIP.search(m)]
                if found:
                    return found[:3], False, "always"
    return [], True, ""


def korean_targets(payload):
    """현재 호출에서 자연스러운 한글 검사를 적용할 편집 원본을 찾는다."""
    ev = payload.get("hook_event_name") or ""
    name = payload.get("tool_name") or ""
    inp = payload.get("tool_input") or {}

    if ev == "PostToolUse" and name in ("Write", "Edit", "MultiEdit"):
        fp = str(inp.get("file_path") or "")
        if fp and KOREAN_DOC.search(fp) and not SKIP.search(fp):
            return [fp]

    if ev == "PreToolUse":
        if name == "Artifact":
            fp = str(inp.get("file_path") or "")
            if fp and KOREAN_DOC.search(fp) and not SKIP.search(fp):
                return [fp]
        if name in ("Bash", "PowerShell"):
            cmd = str(inp.get("command") or "")
            if PUBLISH.search(cmd) and not DRYRUN.search(cmd):
                found = [resolve(match) for match in re.findall(
                    r'["\']?([^\s"\']+\.(?:md|html|txt|json|jsonl|ya?ml|properties))["\']?',
                    cmd,
                    re.I,
                )]
                return [match for match in found if match and not SKIP.search(match)][:3]
    return []


# 상태는 {세션: {열쇠: 시각}} 납작한 구조다 — 만료 정리가 값을 시각으로 읽는다.
# 중첩 사전을 넣었더니 그 정리가 죽어 훅이 통째로 조용히 실패했다(실측).
NOTICE_KEY = "안내:{}"
NOTICE = (
    "★ 발행 직전 — 이 문서에 finalize-korean-document 스킬을 돌린다\n"
    "   결정 규칙이 잡는 것은 표면 모양이 고정된 위반뿐이다. 낱말이 그 자리에\n"
    "   맞는지(불필요한 영어·평가 수식어·번역투·뜻 흐린 동사)는 읽어야 갈린다 —\n"
    "   실측 회수율 1층 0.057 대 2층 0.771.\n"
    "   위 지적이 없어도 돌린다. 못 잡은 것이 없다는 뜻이 아니다."
)


def finalize_notice(payload, files, state):
    """발행 순간에 2층을 부르라고 알린다 — 1층 발화와 무관하게.

    **왜 여기 두나.** 예전에는 이 안내가 1층 지적 목록의 머리줄이었다. 그래서
    1층이 뭔가 잡았을 때만 떴고, 실측으로 발행 640회 중 59회(9.2%)만 나왔다.
    1층 회수율이 0.057이니 당연한 결과다.

    **문서마다 세션에 한 번만.** 노션 발행 하나가 수십 번 호출되므로 호출마다
    내면 소음이 된다(발행 도구 호출 하루 46회 · 문서 단위로는 6.4건).
    """
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    fresh = [fp for fp in files if os.path.exists(fp)]
    if not fresh:
        return ""
    fresh = [fp for fp in fresh if NOTICE_KEY.format(fp) not in state]
    if not fresh:
        return ""
    for fp in fresh:
        state[NOTICE_KEY.format(fp)] = time.time()
    return NOTICE


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0

    files, errors_only, mode = targets(payload)
    korean_files = korean_targets(payload)
    if not files and not korean_files:
        return 0

    key = str(payload.get("session_id") or "-")
    # 안내는 발행 경로(always)에서도 문서마다 한 번만 내야 하므로 상태가 필요하다.
    # 노션 발행 하나가 수십 번 호출된다(하루 46회 · 문서로는 6.4건).
    state = load()
    seen = state.setdefault(key, {}) if mode == "once" else {}

    blocks = []
    for fp in files:
        if not os.path.exists(fp):
            continue
        if mode == "once" and fp in seen:
            continue
        body = run_checker(fp, errors_only)
        if mode == "once":
            seen[fp] = time.time()
        if body:
            blocks.append(f"{os.path.basename(fp)}\n{body}")

    korean_blocks = []
    for fp in korean_files:
        if not os.path.exists(fp):
            continue
        body = run_korean_checker(fp)
        if body:
            korean_blocks.append(f"{os.path.basename(fp)}\n{body}")

    notice = finalize_notice(payload, files, state.setdefault(key, {}))
    if mode == "once" or notice:
        save(state)
    if not blocks and not korean_blocks and not notice:
        return 0                        # 깨끗하면 아무 말도 하지 않는다

    parts = []
    if notice:
        parts.append(notice)
    if blocks:
        head = ("발행 전 점검 — 공유 자료는 오류 0이어야 한다"
                if mode == "always" else
                "문서 서술 규칙 위반 (쓰는 순간에 고치는 편이 싸다)")
        parts.append(head + "\n" + "\n".join(blocks))
    if korean_blocks:
        parts.append("자연스러운 한글 점검\n" + "\n".join(korean_blocks))
    msg = "\n\n".join(parts)
    ev = payload.get("hook_event_name") or ""
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": ev, "additionalContext": msg}
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
