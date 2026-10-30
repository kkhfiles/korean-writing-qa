"""문서 서술 규칙과 자연스러운 한글 검사기를 쓰는 순간과 발행 직전에 부른다.

**왜 두 곳인가.** 발행 직전만 두면 다 써 놓은 뒤에 고치게 되고, 쓰기마다 두면
초안까지 걸려 소음이 된다. 그래서 쓰기 시점은 **오류만·파일당 세션 1회**로 상한을
두고, 발행 시점은 전부 낸다(공유 자료는 발행 전 오류 0).

| 이벤트 | 무엇을 검사하나 | 무엇을 내나 |
|---|---|---|
| `PostToolUse` Write·Edit·MultiEdit | 방금 쓴 `.md`/`.html` | 오류만 · 같은 파일은 세션에 한 번 · 가운뎃점 새 줄은 매번 |
| `PreToolUse` Write·Edit·MultiEdit·apply_patch | 고치려는 `.md`/`.html` | 막지 않음 · 처음 고치는 문서의 가운뎃점 줄을 기존 줄로 적음 |
| `PreToolUse` Artifact·Bash·PowerShell | 발행 대상 파일 | 오류와 주의 전부 |
| `PreToolUse` Bash·PowerShell `git push` | `[publish]` 를 켠 저장소에서 이번 가지의 새 줄 | 2층 판정이 안 끝났으면 막음 |

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
# Claude Code 작업 트리 — `<저장소>/.claude/worktrees/<이름>/` 아래는 저장소 사본이다.
#   ⛔ `.claude/` 를 건너뛰는 뜻은 `~/.claude/` 같은 설정 자리인데, 작업 트리도 그 글자를
#      품고 있어 **작업 트리 세션의 쓰기가 전부 검사에서 빠졌다**(2026-09-23 다른 세션
#      제보 · 오류 11건짜리 HTML 을 고치는 동안 훅이 아무 말도 없었다). 작업 트리로만
#      고치는 저장소에서는 쓰는 순간 검사가 사실상 없었다. 떼고 남은 경로로 판정한다.
WORKTREE_PART = re.compile(r"[\\/]\.claude[\\/]worktrees[\\/][^\\/]+(?=[\\/])", re.I)


def skipped(path: str) -> bool:
    """검사에서 뺄 작업 문서인가 — 작업 트리 앞머리를 떼고 본다."""
    return bool(SKIP.search(WORKTREE_PART.sub("", path)))


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


#: 검사 통과를 내용 해시에 묶어 적는 도구. 없으면 조용히 건너뛴다 —
#   게이트가 그것 때문에 죽으면 안 된다.
RECORDER = _find(
    "KOREAN_QA_RECORDER",
    HOME / ".claude" / "assets" / "check_record.py",
    Path("scripts") / "check_record.py",
)


#: 발행을 막기 전에 통과해야 하는 단계.
#
# ⛔ **적을 길이 있는 것만 요구한다.** 2026-09-16 에 셋을 다 요구하게 만들고
#    `words`·`judgment` 를 적는 곳을 아무 데도 안 만들어, **모든 발행이 막히고
#    통로가 넘기기 하나뿐인 상태**로 전역에 배포했다. 넘기기가 습관이 되면
#    그 뒤로는 어떤 게이트도 안 듣는다 — 자물쇠가 없는 것보다 나쁘다.
#
# 올리는 조건 — 그 단계를 **적는 길이 실제로 있고**, 적히는 비율을 재 본 뒤.
#   `words` 는 올리지 않기로 했다(2026-10-23 사용자 결정) — 문서 판의 21.6%에만 적혀 요구하면
#   고무도장이 된다. 대신 판정기가 드문 낱말 목록을 함께 받고, 판정기 기록은 아래 경로가 이미 요구한다.
#   `KOREAN_PUBLISH_REQUIRE=structure,words,judgment` 로 시험해 볼 수 있다.
REQUIRE = tuple(
    s.strip() for s in
    (os.environ.get("KOREAN_PUBLISH_REQUIRE") or "structure").split(",")
    if s.strip()
)
#: 사람이 푸는 길. 명령 앞에 이 값을 붙이면 보류를 넘긴다 — **명령문에 남으므로
#  나중에 누가 왜 넘겼는지 되짚을 수 있다.** 조용히 넘기는 길은 두지 않는다.
FORCE = "KOREAN_PUBLISH_FORCE=1"


#: 확인 안 된 내용을 싣고 나가는 표시 — **발행을 막는다**(2026-09-29 사용자 「이건 한국어
#: 검사기가 고칠게 아니라 문서 만들고 배포하는 쪽에서 이런 불확실한 내용이 붙은 채로 배포하면
#: 안됨」). 말을 다듬을 문제가 아니라 확인하거나 지울 문제라서 문체 검사기가 아니라 여기서 막는다.
#:
#: 괄호 안 뒤쪽 글자는 **구분 기호로 시작할 때만** 받는다 — 문서 2,816개 실측에서
#: 「(미확인 아님)」·「(미검증이면 표기)」·「(TODO Ledger)」가 걸렸다. 「확인 중」은 뺀다 —
#: 「문의 3건(확인 중)」처럼 진행 상태를 적는 정당한 쓰임이다.
UNVERIFIED = re.compile(
    r"[(\[（]\s*(?:진위|사실|출처|수치|원문)?\s*"
    r"(?:미확인|미검증|미대조|확인\s?(?:필요|요망|전)|검증\s?(?:필요|전)|추후\s?확인|TBD|TODO)"
    r"(?:\s*[—\-·,;:][^)\]）\n]{0,40})?\s*[)\]）]"
    r"|\|\s*TBD\s*\|")
#: 표시를 찾기 전에 지우는 구간 — 코드와 인용. 이 규칙을 설명하는 글이 자기에게 걸리지 않게 한다.
_UNVERIFIED_SKIP = (
    re.compile(r"```.*?```", re.S),
    re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I),
)
_UNVERIFIED_INLINE = re.compile(r"`[^`\n]*`|「[^」\n]*」|\"[^\"\n]*\"|“[^”\n]*”")


def unverified_marks(path):
    """확인 안 된 내용 표시 — (줄 번호, 표시, 그 줄) 목록. 못 읽으면 빈 목록."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for pat in _UNVERIFIED_SKIP:        # 줄 수를 지키려고 같은 수의 줄바꿈으로 바꾼다
        text = pat.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        clean = _UNVERIFIED_INLINE.sub(" ", line)
        for m in UNVERIFIED.finditer(clean):
            out.append((n, m.group(0).strip("| "), re.sub(r"<[^>]+>", "", clean).strip()[:80]))
    return out


def unverified_block(payload, files):
    """발행 직전 — 확인 안 된 표시가 남은 문서를 막는 글. 없으면 빈 문자열.

    상태를 안 쓰므로 `--probe` 에서도 돈다. 검토 기록(`review`)으로는 안 열린다 —
    사람이 읽고 정상이라 볼 대상이 아니라, 확인하거나 지울 대상이다.
    """
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if FORCE in cmd:
        return ""
    found = [(fp, unverified_marks(fp)) for fp in files if os.path.exists(fp)]
    found = [(fp, marks) for fp, marks in found if marks]
    if not found:
        return ""
    lines = ["⛔ 발행 보류 — 확인 안 된 내용 표시가 남았습니다", ""]
    for fp, marks in found:
        for n, mark, line in marks[:8]:
            lines.append(f"  {os.path.basename(fp)} {n}행  {mark} — {line}")
    lines += [
        "",
        "  확인 안 된 사실은 확인하거나 지웁니다. 표시를 다른 말로 바꿔 다는 것은",
        "  고친 것이 아닙니다(「(진위 미확인)」→「(검증되지 않은 수치)」).",
        "  이 표시를 설명하는 글이면 표시를 「」 로 감쌉니다 — 인용은 안 봅니다.",
        "",
        f"  명령으로 발행하는 중이고 정말 그대로 내보내야 하면 앞에 `{FORCE}` 를 붙입니다.",
    ]
    return "\n".join(lines)


def ask_block(payload, files):
    """발행 직전 — 판정기가 사람에게 넘긴 지적 중 사용자 답을 못 받은 것이 남았으면 막는 글.

    (2026-10-06 사용자 — 「규칙으로 잡고 llm 판단으로 잡고, 그래도 애매하면 사람한테
    애스컬레이션」) 판정기가 `decide: ask` 로 낸 지적은 판정 기록에 남는다. 짚은 표현이
    지금 내용에 남아 있고 그 줄에 답 기록이 없으면 막는다. 기한은 없다 — 기다리기만 해도
    풀리면 안 된다. 판정기를 안 돌린 문서는 막지 않는다 — 판정을 요구하는 것은
    `publish_block`·`push_block` 의 몫이다.

    상태를 안 쓰므로 `--probe` 에서도 돈다. 검토 기록(`review`)으로는 안 열린다 —
    세션이 판단해 넘기면 사람에게 넘긴 뜻이 없어진다. 짚은 표현을 고치거나 답을 적으면 열린다.
    """
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if FORCE in cmd:
        return ""
    cov = load_coverage()
    if cov is None or not hasattr(cov, "open_asks"):
        return ""
    found = []
    for fp in files:
        if not os.path.exists(fp):
            continue
        p = Path(fp)
        try:
            left = cov.open_asks(cov.doc_key(p), cov.read_doc(p).splitlines())
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if left:
            found.append((fp, left))
    if not found:
        return ""
    lines = ["⛔ 발행 보류 — 판정기가 사람에게 넘긴 지적에 아직 사용자 답이 없습니다", ""]
    for fp, left in found:
        for n, ask in left[:8]:
            lines.append(f"  {os.path.basename(fp)} {n}행  「{ask.get('phrase')}」 → {ask.get('fix')}")
            if ask.get("why"):
                lines.append(f"      {ask['why']}")
        if len(left) > 8:
            lines.append(f"  … 그 밖 {len(left) - 8}건")
    script = judge_script()
    judge = script.as_posix() if script else "judge_layer2.py"
    lines += [
        "",
        "  사용자에게 물어 정합니다 — 세션이 대신 정하지 않습니다.",
        "  · 표를 만듭니다 — 10건 이하면 목록이 화면에 나오니 대화로 묻고, 넘으면 표 경로를 넘깁니다:",
        f"      python -X utf8 {judge} <파일…> --sheet <저장소 밖 경로>.md",
        "  · 답을 읽습니다 — 「그대로」는 답 기록에 남고, 고칠 것은 목록으로 나옵니다:",
        f"      python -X utf8 {judge} --answers-from <그 표> [--reply '의견대로, 단 3 그대로' …(대화로 받은 답)]",
        "  · 고친 줄은 이 목록에서 빠집니다.",
        "",
        f"  정말 그대로 내보내야 하면 명령 앞에 `{FORCE}` 를 붙입니다 — 명령문에 남습니다.",
    ]
    return "\n".join(lines)


def fix_block(payload, files):
    """발행 직전 — 판정기가 낸 고칠 지적 중 처리 기록이 없는 것이 남았으면 막는 글.

    (2026-10-12) 전에는 고칠 지적이 남아도 발행이 됐다. 고리 재현 시험에서 갈래별 자동 전환
    5건과 「확인 필요」를 적은 고칠 지적 10건이 그 틈으로 사용자에게 안 갔다. 닫는 길은 셋 —
    고침(짚은 표현이 사라짐) · 지적마다 사유 코드와 근거(`--dismiss`) · 사람 확인으로 올림
    (`--escalate`). 판정기를 안 돌렸거나 이 기록이 생기기 전의 판정은 막지 않는다.
    상태를 안 쓰므로 `--probe` 에서도 돈다.
    """
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if FORCE in cmd:
        return ""
    cov = load_coverage()
    if cov is None or not hasattr(cov, "open_fixes"):
        return ""
    found = []
    for fp in files:
        if not os.path.exists(fp):
            continue
        p = Path(fp)
        try:
            left = cov.open_fixes(cov.doc_key(p), cov.read_doc(p).splitlines())
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if left:
            found.append((fp, left))
    if not found:
        return ""
    lines = ["⛔ 발행 보류 — 판정기가 낸 고칠 지적에 처리 기록이 없습니다", ""]
    for fp, left in found:
        for n, fx in left[:8]:
            tag = " [사실 확인]" if cov.needs_check(fx) else ""
            lines.append(f"  {os.path.basename(fp)} {n}행{tag}  「{fx.get('phrase')}」 → {fx.get('fix')}")
        if len(left) > 8:
            lines.append(f"  … 그 밖 {len(left) - 8}건")
    script = judge_script()
    judge = script.as_posix() if script else "judge_layer2.py"
    lines += [
        "",
        "  지적마다 셋 중 하나로 처리합니다.",
        "  · 고칩니다 — 지적을 다 처리한 뒤 --since 로 한 번에 다시 판정합니다",
        "  · 받지 않으면 사유와 근거를 적습니다(대상아님 · 오독 · 충족 · 규칙충돌 · 확인함):",
        f"      python -X utf8 {judge} <파일> --dismiss <행> --reason <사유> --note \"근거\"",
        "  · 세션이 정할 수 없으면 사람 확인으로 올립니다:",
        f"      python -X utf8 {judge} <파일> --escalate <행> --note \"무엇을 누가 확인해야 하는지\"",
        "  「[사실 확인]」 지적은 자료로 확인한 「확인함」이나 사람 확인으로만 닫힙니다.",
        f"  목록 — python -X utf8 {judge} <파일…> --fixes",
        "",
        f"  정말 그대로 내보내야 하면 명령 앞에 `{FORCE}` 를 붙입니다 — 명령문에 남습니다.",
    ]
    return "\n".join(lines)


def publish_base(cov, path):
    """판정 안 된 줄을 가를 기준 ref — (ref, 기준 판 줄 | None). git 밖이면 (None, None).

    ⛔ **게이트가 권하는 판정 명령과 같은 기준이어야 한다.** 판정기는 `--since <ref>` 로 갈라진 지점
       뒤 줄만 본다. 게이트가 다른 기준으로 세면 판정을 돌려도 안 풀리는 막힘이 된다.
       순서 — 저장소 설정의 발행 대상이면 그 `base` · 아니면 지금 가지가 따라가는 원격 가지 ·
       그것도 없으면 HEAD(커밋 안 한 줄만 셈).
    """
    found = cov.repo_of(path) if hasattr(cov, "repo_of") else None
    if not found:
        return None, None
    top, rel = found
    refs = []
    conf = publish_config(top)
    if isinstance(conf, dict) and matches(rel, conf["targets"]):
        refs.append(conf["base"])
    up = _git(top, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if up.returncode == 0 and up.stdout.decode().strip():
        refs.append(up.stdout.decode().strip())
    refs.append("HEAD")
    for ref in refs:
        try:
            return ref, cov.base_lines(path, ref)
        except ValueError:
            continue
    return "HEAD", None


def unjudged_block(payload, files):
    """발행 직전 — 판정기가 아직 안 본 한글 줄이 있으면 막는 글.

    (2026-10-13) 이 경로는 처리 안 된 고칠 지적과 사람 확인만 봤다. 판정 뒤에 고친 줄이 다시
    판정됐는지는 안 봐서 고친 문장이 판정 없이 나갈 수 있었다 — push 와 배포 게이트는 본다.
    재판정을 몰아서 하게 하면 「마지막 재판정」을 세션이 기억해야 해서 이 빈틈에 더 기댄다.

    **범위 — 발행하는 문서 전부**(2026-10-13 사용자 결정 「요구」). 처음에는 판정 기록이 있는 문서와
    설정의 발행 대상에만 걸었는데, 그러면 판정을 한 번도 안 받은 문서가 더 쉽게 나가는 역전이 생긴다
    (외부 검토 · 한 사이트에서 14일 동안 문서 62개가 나가고 판정 기록은 1건이었다).
    **기준 — 게이트가 권하는 판정 명령과 같게** — 판정 기록이 있거나 설정의 발행 대상인 git 문서는
    `--since <ref>` 의 갈라진 지점 뒤 줄만 센다. git 밖 문서는 판정 안 된 한글 줄 전부를 세고
    `--since HEAD`(판정기는 git 밖이면 판정 안 한 줄만 본다)를 권한다. 판정을 한 번도 안 받은 git
    문서는 기준 판 없이 전부를 세고 `--since` 없는 전체 판정을 권한다 — 기준이 어긋나면 판정을 돌려도
    안 풀리는 막힘이 된다.
    **판정 기록은 줄 해시에 묶인다** — 한 글자만 고쳐도 그 줄은 판정 안 된 줄이다. 기한은 없다
    (배포 게이트와 같다 · 안 바뀐 문서를 14일마다 통째로 다시 판정하지 않는다).
    **판정기를 못 부르는 PC** — 지금 내용의 손 판단 기록(`judgment`)으로 연다.
    상태를 안 쓰므로 `--probe` 에서도 돈다.
    """
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if FORCE in cmd:
        return ""
    cov = load_coverage()
    if cov is None or not hasattr(cov, "open_lines"):
        return ""
    judge = judge_command()
    found = []
    for fp in files:
        if not os.path.exists(fp):
            continue
        p = Path(fp)
        try:
            key = cov.doc_key(p)
            seen = cov.judged(key, cov.LOG, fresh=False)
            found_repo = cov.repo_of(p) if hasattr(cov, "repo_of") else None
            conf = publish_config(found_repo[0]) if found_repo else None
            # 설정을 못 읽으면 문자열(까닭)이 온다 — 그때는 발행 대상으로 안 본다(push 게이트가 그 까닭을 알린다)
            in_scope = isinstance(conf, dict) and matches(found_repo[1], conf["targets"])
            lines = cov.read_doc(p).splitlines()
            if seen or in_scope:
                ref, base = publish_base(cov, p)
                ref = ref or "HEAD"         # git 밖 — 판정기가 판정 안 한 줄만 본다
            else:
                # 판정을 한 번도 안 받은 문서 — 한글 줄 전부. git 문서는 전체 판정, git 밖은 --since HEAD
                ref, base = (None if found_repo else "HEAD"), None
            left = cov.open_lines(lines, base, seen)
            gone = (cov.open_deletions(lines, base, cov.deleted_seen(key, cov.LOG))
                    if base and hasattr(cov, "open_deletions") else [])
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if not left and not gone:
            continue
        if judge is None:
            if "judgment" in missing_stages(p, ("judgment",)):
                found.append((fp, ref, left, gone, lines, True))
            continue
        found.append((fp, ref, left, gone, lines, False))
    if not found:
        return ""
    script = judge_script()
    judge_path = script.as_posix() if script else "judge_layer2.py"
    out = ["⛔ 발행 보류 — 판정기가 아직 안 본 한글 줄이 있습니다", ""]
    manual = False
    for fp, ref, left, gone, lines, need_record in found:
        name = os.path.basename(fp)
        if left:
            n = left[0]
            out.append(f"  {name} — 새로 쓰거나 고친 뒤 판정 안 한 줄 {len(left)}개 · "
                       f"{n}행 「{lines[n - 1].strip()[:30]}」")
        if gone:
            n, lost = gone[0]
            out.append(f"  {name} — 판정 안 한 지운 자리 {len(gone)}곳 · {n}행 근처 「{lost[0].strip()[:30]}」")
        since = f" --since {ref}" if ref else ""
        out.append(f"      python -X utf8 {judge_path} \"{fp}\"{since}")
        manual = manual or need_record
    out += ["", "  판정에서 나온 지적을 처리(고침, 사유, 사람 확인)한 뒤 다시 발행합니다.",
            "  이 문서에 `finalize-korean-document` 스킬을 돌리면 판정부터 처리까지 이어서 합니다."]
    if manual:
        out += ["  이 PC 에서는 판정기를 부를 수 없습니다 — 규칙을 직접 읽고 판단한 뒤 지금 내용에 판단 기록(judgment)을 남깁니다:",
                "    python -X utf8 scripts/check_record.py record <파일> --stage judgment --verdict pass --note \"무엇을 봤나\""]
    out += ["", f"  정말 그대로 내보내야 하면 명령 앞에 `{FORCE}` 를 붙입니다 — 명령문에 남습니다."]
    return "\n".join(out)


def missing_stages(path, require=None):
    """지금 내용이 아직 통과하지 못한 단계. 도구가 없으면 빈 목록(막지 않는다)."""
    require = REQUIRE if require is None else require
    if not RECORDER or not RECORDER.exists():
        return []
    try:
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(RECORDER), "status", str(path), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        info = json.loads(done.stdout.strip() or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    stages = info.get("stages") or {}
    return [s for s in require if stages.get(s) != "pass"]


def publish_block(payload, files):
    """발행 직전에 통과 기록을 확인한다 — 없으면 막는 글을 낸다.

    **왜 안내가 아니라 막기인가.** 안내는 읽고 넘길 수 있다 — 실측 이행율 3.8%.
    발행은 되돌릴 수 없으므로 **허용 조건을 바꾸는 쪽**이 맞다(2026-09-16 외부 검토).

    **왜 해시에 묶나.** 「검사했다」만 보면 옛 판을 검사한 뒤 고쳐서 내보내는 길이
    열린다. 기록은 그 순간의 내용에 묶여 있어 한 글자만 고쳐도 안 맞는다.
    """
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if FORCE in cmd:
        return ""
    stuck, opened = [], 0
    for fp in files:
        if not os.path.exists(fp):
            continue
        opened += 1
        gaps = missing_stages(fp)
        if gaps:
            stuck.append((fp, gaps))
    # ⛔ **한 장도 못 열었으면 그 발행은 검사된 적이 없다.** 이 자리가 조용하면
    #    검사도 기록도 막기도 없이 나간다 — 게이트에서 가장 나쁜 실패다.
    #
    #    ⚠️ 못 연 것을 **하나라도** 막으면 안 된다. 발행 도구는 `.md` 를 읽어
    #       `.html` 을 **만들면서** 부르므로 그 산출물은 이 시점에 아직 없다.
    #       거기까지 막으면 정상 빌드마다 보류가 떠 넘기기가 습관이 된다.
    if not opened and files:
        return "\n".join([
            "⛔ 발행 보류 — 발행 대상을 한 장도 열지 못했습니다", "",
        ] + [f"  {fp}" for fp in files] + [
            "",
            "  검사하지 못했다는 뜻이지 깨끗하다는 뜻이 아닙니다.",
            "  절대 경로로 다시 부르면 그대로 검사합니다.",
            "",
            f"  이 경로가 맞고 그냥 내보내야 하면 명령 앞에 `{FORCE}` 를 붙입니다.",
        ])
    if not stuck:
        return ""
    lines = ["\u26d4 \ubc1c\ud589 \ubcf4\ub958 — 지금 내용으로 통과한 기록이 없습니다", ""]
    for fp, gaps in stuck:
        lines.append(f"  {os.path.basename(fp)} — 빠진 단계: {' · '.join(gaps)}")
    lines += [
        "",
        "  고치는 법 — 이 문서에 `finalize-korean-document` 스킬을 돌립니다.",
        "  그 절차가 낱말 점검과 문맥 판단을 마치고 통과를 기록합니다.",
        "",
        "  주의만 남았고 **읽어 보니 정상**이면 그 판단을 적습니다 —",
        "    python -X utf8 scripts/check_record.py record <파일> \\",
        "        --stage review --verdict pass --note \"무슨 주의를 왜 정상으로 봤나\"",
        "  내용 해시에 묶이므로 한 글자만 고쳐도 다시 판단해야 합니다."
        " 오류에는 안 듣습니다.",
        "",
        f"  정말 그대로 내보내야 하면 명령 앞에 `{FORCE}` 를 붙입니다 — 명령문에 남습니다.",
    ]
    return "\n".join(lines)


# ── push 직전 2층 판정 ────────────────────────────────────────────────────────
#
# **저장소가 스스로 켠다** — 뿌리의 `korean-qa.toml` 에 `[publish]` 절이 있을 때만 본다.
#
#     [publish]
#     require = ["judgment"]                       # 새 줄이 있는 문서에 요구할 기록
#     targets = ["*/docs/*.md", "*/pages/*.html"]  # 뿌리 기준 · 칸 수까지 맞아야 함
#     base = "origin/main"                         # 이 가지와 갈라진 뒤의 새 줄만 본다
#
# **왜 push 인가.** lab-docs 는 가지 push → PR → 병합 → 빌드로 나간다. 병합되는 것은
#   push 한 커밋이고, 빌드(Cloudflare)는 이 PC 의 통과 기록을 못 본다. 그래서 이 PC 에서
#   push 직전에 본다. 14일 동안 lab-docs 문서 62개가 이 길로 나갔고 2층 판정 기록은
#   1건이었다(2026-10-01 실측 · 발행 게이트가 보는 노션·아티팩트 길은 같은 기간 다섯 건).
# ⛔ **git 저장소 훅(pre-push)으로 두지 않는다** — 클론마다 설정이 필요하다(lab-docs 의
#   2026-09-23 결정). 이 훅은 korean-writing-qa 를 설치한 PC 의 AI 세션에서만 돈다.
# **커밋된 내용을 본다** — push 로 나가는 것은 작업 폴더가 아니라 `HEAD` 다.
# **새 줄이 없는 문서는 안 본다** — 지우기만 한 문서 · 갈라진 지점에 이미 있던 줄은
#   이 게이트의 몫이 아니다(묵은 문제는 따로 점검).
# **푸는 길** — 명령 앞에 `KOREAN_PUBLISH_FORCE=1`. 명령문에 남는다.
# ⚠️ `HEAD` 만 본다 — `git push origin 다른가지` 처럼 지금 가지가 아닌 것을 밀면
#   그 가지는 안 본다. lab-docs 절차는 `git push -u origin HEAD` 다.

#: 판정기가 본 줄을 가르는 모듈 — 판정기와 같은 것을 써야 판정한 줄이 판정한 줄로 읽힌다.
COVERAGE = _find(
    "KOREAN_QA_COVERAGE",
    HOME / ".claude" / "assets" / "layer2_coverage.py",
    Path("scripts") / "layer2_coverage.py",
)
#: 스킬 — 세션에게 부르라고 적어 둔 판정기 경로를 여기서 읽는다.
SKILL_MD = _find(
    "KOREAN_QA_SKILL_MD",
    HOME / ".claude" / "skills" / "finalize-korean-document" / "SKILL.md",
    Path("skills") / "finalize-korean-document" / "SKILL.md",
)


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=30)


def _push_parser():
    """push 판별 — **정본은 `public-push-gate.py` 하나다**(같은 폴더에 함께 설치된다).

    따옴표 안은 안 보고(`git commit -m "push"`), 앞서 옮긴 폴더(`cd`·`Set-Location`)와
    `git -C <경로>` 를 따라간다. 이 파일에 사본을 두었다가 cd 해석을 한쪽에만 고쳤다(2026-10-01).
    못 불러오면 None — push 를 가를 수 없다.
    """
    import importlib.util
    path = Path(__file__).resolve().parent / "public-push-gate.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("public_push_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def publish_config(repo):
    """`[publish]` 절 · 없으면 None · 못 읽으면 그 까닭(문자열)."""
    path = repo / "korean-qa.toml"
    if not path.is_file():
        return None
    try:
        import tomllib
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as e:              # 설정을 못 읽고 조용히 넘기면 켠 게이트가 꺼진다
        return f"{path.name} 을 못 읽었습니다 — {type(e).__name__}: {e}"[:300]
    conf = data.get("publish")
    if not isinstance(conf, dict):
        return None
    return {"require": [str(s) for s in conf.get("require") or ["judgment"]],
            "targets": [str(s) for s in conf.get("targets") or []],
            "base": str(conf.get("base") or "origin/main")}


def matches(rel, patterns):
    """뿌리 기준 경로가 무늬와 맞나 — 칸(`/`) 수까지 같아야 한다.

    `fnmatch` 를 통째로 쓰면 `*` 가 `/` 까지 삼켜 `*/docs/*.md` 가 하위 폴더의 초안까지
    잡는다(lab-docs 빌드는 `docs/` 맨 위 md 만 낸다).
    """
    from fnmatch import fnmatchcase
    parts = rel.split("/")
    for pat in patterns:
        pp = pat.split("/")
        if len(pp) == len(parts) and all(fnmatchcase(a, b) for a, b in zip(parts, pp)):
            return True
    return False


def judge_command():
    """이 PC 에서 세션이 부를 수 있는 판정기 · 없으면 None.

    **스킬이 세션에게 부르라고 적은 경로를 그대로 본다.** 게이트가 「판정기를 돌렸나」까지
    요구하는 것은 세션이 그 열쇠를 쓸 수 있을 때뿐이다 — 못 쓰는 PC 에서 요구하면 넘기기
    말고는 길이 없다(「열쇠 없는 자물쇠」). 판정기가 부를 모델(Claude Code 나 Codex)도 있어야 한다.
    `KOREAN_QA_JUDGE` 로 경로를 주면 그것을 믿는다(`-` 면 없음) — 시험이 쓴다.
    """
    override = os.environ.get("KOREAN_QA_JUDGE")
    if override:
        return None if override == "-" else (Path(override) if Path(override).is_file() else None)
    path = judge_script()
    if path is None:
        return None
    return path if judge_backend_ready() else None


def judge_script():
    """스킬이 세션에게 부르라고 적은 판정기 경로 · 없으면 None. 모델이 있는지는 안 본다 —
    답 기록(`--answer`)은 모델 없이 돈다.

    스킬은 판정기를 입구 형식(`korean_qa_run.py judge_layer2`)으로 부른다(2026-10-30). 그 꼴을
    못 읽으면 판정기가 있는 PC 를 없는 PC 로 보고 손으로 남기는 판정 기록을 요구해 push 를 막았다.
    """
    try:
        text = SKILL_MD.read_text(encoding="utf-8")
    except (OSError, AttributeError):
        return None
    m = re.search(r"python -X utf8 (\S+judge_layer2\.py)", text)
    if m:
        path = Path(os.path.expanduser(m.group(1)))
        return path if path.is_file() else None
    m = re.search(r'python -X utf8 "?(\S+?korean_qa_run\.py)"? judge_layer2\b', text)
    if not m:
        return None
    entry = Path(re.sub(r"^(\$HOME|~)", HOME.as_posix(), m.group(1)))
    root = entry_root(entry) if entry.is_file() else None
    path = root / "scripts" / "judge_layer2.py" if root else None
    return path if path and path.is_file() else None


def entry_root(entry):
    """입구(`korean_qa_run.py`)가 찾는 저장소 — 입구와 같은 차례(환경 변수, 저장소 안의 입구, 설치 기록)."""
    env = os.environ.get("KOREAN_WRITING_QA_HOME")
    if env:
        return Path(env)
    if (entry.resolve().parents[1] / "install.py").is_file():
        return entry.resolve().parents[1]
    pointer = Path(os.environ.get("CLAUDE_HOME") or HOME / ".claude") / "data" / "korean-writing-qa-home.txt"
    try:
        text = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return Path(text) if text else None


def judge_backend_ready():
    """판정기가 부를 모델이 이 PC 에 있나 — 판정기의 `pick_backend` 와 같은 것을 본다.

    `llm_playbook` 만 있고 Claude Code · Codex 가 둘 다 설치·로그인이 안 됐으면 판정기가
    못 돈다(종료 코드 3). 그때 판정을 요구하면 열쇠 없는 자물쇠다 — 2026-10-02 까지는
    `llm_playbook` 만 보고 요구해서 Claude 가 없는 PC 가 그 상태였다. 사다리가 없는 옛
    `llm_playbook` 은 전처럼 있다고 본다 — 판정기도 그때 Claude 를 부른다.
    """
    import importlib.util
    if importlib.util.find_spec("llm_playbook") is None:
        return False
    try:
        from llm_playbook.ladder import available
    except Exception:
        return True
    return any(available(name)[0] for name in ("claude", "codex"))


def load_coverage():
    if not COVERAGE or not COVERAGE.is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location("layer2_coverage", COVERAGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def push_gaps(repo, conf, judge, commit="HEAD"):
    """새 줄이 있는 대상 문서마다 빠진 것 — [(뿌리 기준 경로, [빠진 것…])].

    `commit` 은 push 가 내보내는 커밋 — HEAD 가 아닐 수 있다(`push_sources`).
    ⛔ 갈라진 지점을 못 찾으면 ValueError — 새 줄을 못 가르면 통과시킬 수 없다.
    """
    import tempfile
    mb = _git(repo, "merge-base", commit, conf["base"])
    if mb.returncode:
        raise ValueError(mb.stderr.decode("utf-8", "replace").strip()[:200])
    mb = mb.stdout.decode().strip()
    diff = _git(repo, "diff", "--name-only", "--no-renames", "--diff-filter=AM", mb, commit)
    changed = [l for l in diff.stdout.decode("utf-8", "replace").splitlines()
               if l and matches(l, conf["targets"])]
    cov = load_coverage()
    out = []
    for rel in changed:
        blob = _git(repo, "show", f"{commit}:{rel}").stdout
        suffix = Path(rel).suffix
        gaps = []
        if cov is not None:
            lines = cov.visible_text(blob.decode("utf-8", "replace"), suffix).splitlines()
            old = _git(repo, "show", f"{mb}:{rel}")
            base = (cov.visible_text(old.stdout.decode("utf-8", "replace"), suffix).splitlines()
                    if old.returncode == 0 else [])
            cut = cov.deletions(lines, base) if hasattr(cov, "deletions") else []
            if not cov.open_lines(lines, base, set()) and not cut:
                continue                    # 새 줄도 지운 자리도 없다 — 이미 있던 줄뿐
            key = cov.key_in(repo, rel) if hasattr(cov, "key_in") else rel
            if judge is not None:
                left = cov.open_lines(lines, base, cov.judged(key, cov.LOG))
                if left:
                    n = left[0]
                    gaps.append(f"판정기가 아직 안 본 새 줄 {len(left)}개 — "
                                f"{n}행 「{lines[n - 1].strip()[:30]}」")
                # 지우기만 한 자리 — 지워서 남은 글의 뜻이 바뀌었는지 판정기가 봐야 한다(2026-10-13)
                gone = cov.open_deletions(lines, base, cov.deleted_seen(key, cov.LOG)) if cut else []
                if gone:
                    n, lost = gone[0]
                    gaps.append(f"판정기가 아직 안 본 지운 자리 {len(gone)}곳 — "
                                f"{n}행 근처에서 지운 「{lost[0].strip()[:30]}」")
            if hasattr(cov, "open_asks"):
                asks = cov.open_asks(key, lines)
                if asks:
                    n, ask = asks[0]
                    gaps.append(f"사용자 답을 못 받은 사람 확인 지적 {len(asks)}개 — "
                                f"{n}행 「{str(ask.get('phrase') or '')[:30]}」")
            if hasattr(cov, "open_fixes"):
                fixes = cov.open_fixes(key, lines)
                if fixes:
                    n, fx = fixes[0]
                    gaps.append(f"처리 기록 없는 고칠 지적 {len(fixes)}개 — "
                                f"{n}행 「{str(fx.get('phrase') or '')[:30]}」 · 고치거나 --dismiss · --escalate")
        with tempfile.TemporaryDirectory() as tmp:
            # 기록은 내용 해시에 묶인다 — 커밋된 내용을 파일로 꺼내 그 해시로 묻는다
            probe_file = Path(tmp) / f"head{suffix}"
            probe_file.write_bytes(blob)
            missing = missing_stages(probe_file, conf["require"])
        if judge is not None and cov is not None:
            # ⛔ 손으로 남기는 판정 기록(judgment)을 요구하지 않는다 — 판정기 기록으로 「새 줄을 다
            #    봤나 · 지운 자리를 봤나」를 위에서 직접 보고, 남긴 지적은 지적마다 처리 기록이나
            #    사용자 답을 요구한다. 세션의 한 줄 메모는 겹치고, 잊으면 push 를 한 번 더 막을 뿐이다
            #    (2026-10-13 README push 에서 그 단계를 빠뜨림 · 외부 검토 「잃는 판단 정보 없음」).
            missing = [s for s in missing if s != "judgment"]
        gaps += [f"{s} 기록 없음(커밋된 내용 기준)" for s in missing]
        if gaps:
            out.append((rel, gaps))
    return out


def push_commits(repo, sources):
    """push 가 내보내는 쪽 이름을 커밋으로 — [(이름, 커밋)] · 못 풀면 그 까닭(문자열).

    `refs/heads/*` 같은 무늬는 그 아래 가지 · 꼬리표를 모두 편다. 같은 커밋은 한 번만 본다.
    """
    if sources is None:
        return "따옴표가 닫히지 않았습니다"
    out, seen = [], set()
    for src in sources:
        names = [src]
        if src.endswith("/*"):
            got = _git(repo, "for-each-ref", "--format=%(refname)", src[:-2])
            names = got.stdout.decode("utf-8", "replace").split()
        for name in names:
            got = _git(repo, "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}")
            sha = got.stdout.decode().strip()
            if got.returncode or not sha:
                return f"`{name}` 을 커밋으로 풀지 못했습니다"
            if sha not in seen:
                seen.add(sha)
                out.append((name, sha))
    return out


def push_block(payload):
    """push 직전 — `[publish]` 를 켠 저장소에서 새 줄의 2층 판정이 안 끝났으면 막는 글."""
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    if (payload.get("tool_name") or "") not in ("Bash", "PowerShell"):
        return ""
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    parser = _push_parser()
    target = parser.push_target(cmd) if parser else None
    if target is None or FORCE in cmd:
        return ""
    repo = parser._repo_root(payload.get("cwd") or "", target)
    conf = publish_config(repo) if repo else None
    if conf is None:
        return ""
    head = ["⛔ push 보류 — 이번 가지에서 새로 쓴 줄의 2층 판정이 끝나지 않았습니다",
            f"   ({repo.name} 의 korean-qa.toml [publish] 설정)", ""]
    tail = ["", f"  정말 그대로 올려야 하면 명령 앞에 `{FORCE}` 을 붙입니다 — 명령문에 남습니다."]
    if isinstance(conf, str):
        return "\n".join(head + [f"  {conf}"] + tail)
    sources = push_commits(repo, parser.push_sources(cmd) if hasattr(parser, "push_sources")
                           else ["HEAD"])
    if isinstance(sources, str):
        return "\n".join(head + [
            f"  push 가 내보내는 커밋을 명령에서 가르지 못했습니다 — {sources}",
            "  내보낼 가지를 이름으로 적어 다시 push 합니다(예: `git push origin <가지>`)."] + tail)
    judge = judge_command()
    gaps, seen_rel = [], set()
    try:
        for src, commit in sources:
            for rel, why in push_gaps(repo, conf, judge, commit):
                if rel not in seen_rel:
                    seen_rel.add(rel)
                    gaps.append((rel, why if src == "HEAD" else
                                 [f"push 하는 `{src}` 의 내용 — 그 가지를 체크아웃한 뒤 판정합니다"] + why))
    except ValueError as e:
        return "\n".join(head + [
            f"  `{conf['base']}` 와 갈라진 지점을 못 찾았습니다 — 새 줄을 가를 수 없습니다.",
            f"  {e}", "", "  `git fetch` 로 기준 가지를 받은 뒤 다시 push 합니다."] + tail)
    if not gaps:
        return ""
    lines = list(head)
    for rel, why in gaps:
        lines.append(f"  {rel}")
        lines += [f"    · {w}" for w in why]
    files = " ".join((repo / rel).as_posix() for rel, _ in gaps)   # 세션이 하위 폴더에 있어도 그대로 돈다
    lines += ["", "  고치는 법"]
    if judge is not None:
        lines += [f"    1. python -X utf8 {judge.as_posix()} {files} --since {conf['base']}",
                  "       새 줄만 판정합니다. 지적을 한 묶음 처리한 뒤 같은 명령을 한 번 더 부릅니다(지적 하나마다 부르지 않음)."]
    else:
        lines += ["    1. 이 PC 에서는 2층 판정기를 부를 수 없습니다 — finalize-korean-document",
                  "       9단계와 판단 규칙(core-rules.md)을 세션이 직접 읽고 새 줄을 판정합니다."]
    lines += ["    2. 사람 확인 지적은 표를 만들어 묻고(10건 이하면 대화로 · --reply 로 읽음), 답을 읽습니다:",
              f"       python -X utf8 {(judge_script() or Path('judge_layer2.py')).as_posix()} "
              "<파일…> --sheet <저장소 밖 경로>.md",
              f"       python -X utf8 {(judge_script() or Path('judge_layer2.py')).as_posix()} "
              "--answers-from <그 표>",
              "    3. 고칠 지적은 고치거나, 지적마다 사유와 근거를 적거나(--dismiss), 사람 확인으로 올립니다(--escalate):",
              f"       python -X utf8 {(judge_script() or Path('judge_layer2.py')).as_posix()} <파일…> --fixes",
              ]
    if judge is None:
        lines += ["    4. python -X utf8 ~/.claude/assets/check_record.py record <파일> \\",
                  "           --stage judgment --verdict pass --note \"남긴 지적과 까닭\""]
    lines += ["    5. 커밋한 뒤 다시 push 합니다 — 확인은 커밋된 내용으로 합니다."]
    return "\n".join(lines + tail)


# ── 사이트 배포 직전 ─────────────────────────────────────────────────────────
#
# **배포하는 저장소가 스스로 켠다** — 그 폴더(또는 위 폴더)의 `korean-qa.toml` 에 `[deploy]` 절.
#
#     [deploy]
#     manifest = "sources.json"          # 배포 원본 목록(JSON 배열) · 설정 파일 기준 상대 경로
#     field = "from"                     # 항목마다 원본 경로가 든 칸
#     exclude = ["*/.claude/state/*"]    # 사람이 쓴 글이 아닌 원본(개인 보드 등)
#     pages = []                         # 목록 밖에서 더 볼 원본
#
# **왜 생겼나**(2026-10-06 사용자 「디스패치 왜 검사 안함?? 검사하게 만드세요」) — 발행 게이트가
#   발행으로 보는 것은 노션 · 슬라이드 · PDF 명령과 Artifact 뿐이었다. 사이트 배포 명령은 대상
#   파일을 적지 않아 한 번도 안 걸렸다 — 7일에 19회 배포했고, 그 사이트에서 사용자가 한글 21건을
#   짚었다. push 게이트도 `[publish]` 를 둔 저장소(lab-docs)에서만 돌았다.
# **배포 목록을 그대로 읽는다** — 빌드가 쓰는 목록과 게이트가 보는 목록이 두 벌이면 한쪽이 낡는다.
# **무엇을 요구하나**
#   · 모든 원본 — 1층 오류 0 · 답을 못 받은 사람 확인 0
#   · 지난 통과 뒤 바뀐 원본 — 판정기가 한 번도 안 본 한글 줄 0 · 판단 기록(judgment) ·
#     주의가 있으면 검토 기록(review). 안 바뀐 원본까지 매번 다시 요구하면 기록이 고무도장이 된다.
# **통과하면 원본마다 내용 해시를 적는다**(`DEPLOY_PASS`) — 다음 배포는 바뀐 원본만 다시 요구한다.
# **푸는 길** — 명령 앞에 `KOREAN_PUBLISH_FORCE=1`. 명령문에 남는다.
# ⚠️ AI 세션의 명령만 본다 — 사람이 터미널에서 직접 배포하면 이 훅은 안 돈다.

DEPLOY = re.compile(r"\bnpm\s+(?:--prefix\s+\S+\s+)?run\s+(?:publish|deploy)\b"
                    r"|\bwrangler\s+(?:pages\s+)?deploy\b", re.I)
_DEPLOY_CD = re.compile(r'^\s*(?:cd|Set-Location)\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s&;|]+))\s*(?:&&|;)')
_DEPLOY_PREFIX = re.compile(r'--prefix\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))')
DEPLOY_PASS = Path(os.environ.get("KOREAN_QA_DEPLOY_PASS")
                   or HOME / ".claude" / "state" / "korean-deploy-pass.jsonl")


def deploy_dir(cmd, cwd):
    """배포 명령이 도는 폴더 — 세션 폴더에서 `cd`·`--prefix` 를 따라간다."""
    base = cwd or os.getcwd()
    for pat in (_DEPLOY_CD, _DEPLOY_PREFIX):
        m = pat.search(cmd) if pat is _DEPLOY_PREFIX else pat.match(cmd)
        if m:
            d = resolve(m.group(1) or m.group(2) or m.group(3))
            base = d if os.path.isabs(d) else os.path.join(base, d)
    return Path(base)


def deploy_config(start):
    """위로 올라가며 `[deploy]` 를 둔 `korean-qa.toml` 을 찾는다 — (설정 폴더, 절) · 없으면 None ·
    못 읽으면 그 까닭(문자열). 설정을 못 읽고 조용히 넘기면 켠 게이트가 꺼진다."""
    cur = Path(start).resolve()
    for d in (cur, *cur.parents):
        path = d / "korean-qa.toml"
        if not path.is_file():
            continue
        try:
            import tomllib
            conf = tomllib.loads(path.read_text(encoding="utf-8")).get("deploy")
        except Exception as e:
            return f"{path} 을 못 읽었습니다 — {type(e).__name__}: {e}"[:300]
        return (d, conf) if isinstance(conf, dict) else None
    return None


def deploy_pages(root, conf):
    """배포되는 원본 — 목록(`manifest`)과 `pages` 에서 · md·html 만 · `exclude` 는 뺀다."""
    from fnmatch import fnmatchcase
    items = list(conf.get("pages") or [])
    manifest = conf.get("manifest")
    if manifest:
        data = json.loads((root / manifest).read_text(encoding="utf-8"))
        field = conf.get("field") or "from"
        items += [it[field] for it in data if isinstance(it, dict) and it.get(field)]
    out = []
    for raw in items:
        p = Path(os.path.expanduser(str(raw)))
        p = p if p.is_absolute() else root / p
        if p.suffix.lower() not in (".html", ".htm", ".md"):
            continue
        if any(fnmatchcase(p.as_posix(), pat) for pat in conf.get("exclude") or []):
            continue
        out.append(p)
    return list(dict.fromkeys(out))


def content_hash(path):
    """통과 기록(`check_record.py`)과 같은 내용 해시 — 줄 끝 차이는 무시한다."""
    import hashlib
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def deploy_passed():
    out = set()
    try:
        for raw in DEPLOY_PASS.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            out.add((row.get("page"), row.get("hash")))
    except OSError:
        pass
    return out


def deploy_gaps(pages, judge):
    """원본마다 빠진 것 — [(원본, [빠진 것…])] · 다 갖췄으면 빈 목록."""
    cov = load_coverage()
    passed = deploy_passed()
    out = []
    for p in pages:
        if not p.is_file():
            out.append((p, ["원본이 없습니다 — 배포 목록과 실제 파일이 어긋남"]))
            continue
        gaps = []
        body = run_checker(str(p), False)
        if body.startswith("⚠️ 전역 문서 검사를 못 돌렸다"):
            gaps.append("1층 검사를 못 돌림 — 검사되지 않은 원본은 내보내지 않습니다")
        errs = [l.strip() for l in body.splitlines() if "❌" in l]
        if errs:
            gaps.append(f"1층 오류 {len(errs)}건 — {errs[0][:70]}")
        changed = (p.as_posix(), content_hash(p)) not in passed
        if cov is not None:
            lines = cov.read_doc(p).splitlines()
            key = cov.doc_key(p)
            if hasattr(cov, "open_asks"):
                asks = cov.open_asks(key, lines)
                if asks:
                    n, ask = asks[0]
                    gaps.append(f"사용자 답을 못 받은 사람 확인 지적 {len(asks)}개 — "
                                f"{n}행 「{str(ask.get('phrase') or '')[:30]}」")
            if hasattr(cov, "open_fixes"):
                fixes = cov.open_fixes(key, lines)
                if fixes:
                    n, fx = fixes[0]
                    gaps.append(f"처리 기록 없는 고칠 지적 {len(fixes)}개 — "
                                f"{n}행 「{str(fx.get('phrase') or '')[:30]}」 · 고치거나 --dismiss · --escalate")
            if changed and judge is not None:
                left = cov.open_lines(lines, [], cov.judged(key, cov.LOG, fresh=False))
                if left:
                    n = left[0]
                    gaps.append(f"판정기가 아직 안 본 한글 줄 {len(left)}개 — "
                                f"{n}행 「{lines[n - 1].strip()[:30]}」")
        if changed and (judge is None or cov is None):
            # 판정기를 부를 수 있으면 위에서 판정기 기록을 직접 본다 — push 게이트와 같은 까닭
            gaps += [f"{s} 기록 없음(지금 내용 기준)" for s in missing_stages(p, ["judgment"])]
        if changed:
            warns = [l for l in body.splitlines() if "⚠️" in l and "❌" not in l]
            if warns and not reviewed(p):
                gaps.append(f"주의 {len(warns)}건 검토 기록 없음 — {warns[0].strip()[:60]}")
        if gaps:
            out.append((p, gaps))
    return out


def note_deploy_pass(pages):
    DEPLOY_PASS.parent.mkdir(parents=True, exist_ok=True)
    with DEPLOY_PASS.open("a", encoding="utf-8", newline="\n") as f:
        for p in pages:
            if p.is_file():
                f.write(json.dumps({"page": p.as_posix(), "hash": content_hash(p),
                                    "when": time.time()}, ensure_ascii=False) + "\n")


def deploy_block(payload, probe=False):
    """사이트 배포 직전 — `[deploy]` 를 켠 저장소에서 배포 원본이 검사를 다 거치지 않았으면 막는 글."""
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    if (payload.get("tool_name") or "") not in ("Bash", "PowerShell"):
        return ""
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    # 따옴표 안(커밋 메시지 등)의 배포 명령은 배포가 아니다
    bare = re.sub(r'"[^"]*"|\'[^\']*\'', '""', cmd)
    if not DEPLOY.search(bare) or DRYRUN.search(bare) or FORCE in cmd:
        return ""
    found = deploy_config(deploy_dir(cmd, payload.get("cwd") or ""))
    if found is None:
        return ""
    head = ["⛔ 배포 보류 — 배포되는 원본이 한글 검사를 다 거치지 않았습니다", ""]
    tail = ["", f"  정말 그대로 배포해야 하면 명령 앞에 `{FORCE}` 를 붙입니다 — 명령문에 남습니다."]
    if isinstance(found, str):
        return "\n".join(head + [f"  {found}"] + tail)
    root, conf = found
    try:
        pages = deploy_pages(root, conf)
    except (OSError, ValueError, KeyError, TypeError) as e:
        return "\n".join(head + [f"  배포 목록을 못 읽었습니다 — {type(e).__name__}: {e}"[:300]] + tail)
    judge = judge_command()
    try:
        gaps = deploy_gaps(pages, judge)
    except Exception as e:
        # ⛔ 훅이 죽으면 명령은 그대로 돈다 — 검사를 못 한 배포가 나간다. 설치본의 판정 기록
        #    모듈이 옛 판이라 실제로 죽었다(2026-10-06 첫 시험). 못 돌렸으면 막고 까닭을 보인다.
        return "\n".join(head + [f"  배포 검사를 못 돌렸습니다 — {type(e).__name__}: {e}"[:300],
                                 "  설치본이 어긋났으면 korean-writing-qa 에서 `python install.py`."] + tail)
    if not gaps:
        if not probe:
            note_deploy_pass(pages)
        return ""
    lines = list(head) + [f"  ({root.name} 의 korean-qa.toml [deploy] · 원본 {len(pages)}개)", ""]
    for p, why in gaps:
        lines.append(f"  {p.as_posix()}")
        lines += [f"    · {w}" for w in why]
    script = (judge_script() or Path("judge_layer2.py")).as_posix()
    lines += ["", "  고치는 법 — 원본마다 finalize-korean-document 스킬을 돌립니다:",
              "    1. 1층 오류를 고칩니다.",
              (f"    2. python -X utf8 {script} <원본> — 판정기가 안 본 줄을 판정합니다."
               if judge is not None else
               "    2. 이 PC 에서는 판정기를 부를 수 없습니다 — 9단계와 core-rules.md 를 직접 읽고 판정합니다."),
              "    3. 사람 확인 지적은 표를 만들어 묻고(10건 이하면 대화로 · --reply 로 읽음), 답을 읽습니다 — "
              f"`{script} <원본…> --sheet <저장소 밖 경로>.md` · `{script} --answers-from <그 표>`",
              "    4. 고칠 지적은 고치거나, 지적마다 사유와 근거를 적거나(--dismiss), 사람 확인으로 올립니다"
              f"(--escalate) — 목록 `{script} <원본…> --fixes`",
              ]
    if judge is None:
        lines += ["    5. python -X utf8 ~/.claude/assets/check_record.py record <원본> "
                  "--stage judgment --verdict pass --note \"남긴 지적과 까닭\""]
    lines += ["    6. 주의는 읽고 정상이면 --stage review 로 까닭과 함께 적습니다."]
    return "\n".join(lines + tail)


def reviewed(path):
    """이 **내용**에 대한 검토 기록이 있나 — 주의를 읽고 정상으로 판단한 자국."""
    if not RECORDER or not RECORDER.exists():
        return False
    try:
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(RECORDER), "status", str(path), "--json"],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        info = json.loads(done.stdout.strip() or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return (info.get("stages") or {}).get("review") == "pass"


def blocking(path, body):
    """이 지적들이 발행을 막아야 하나.

    ★ **주의만 있고 검토 기록이 있으면 안 막는다** (2026-09-18 사용자 결정).
      주의는 「사람이 보고 판단하라」는 등급인데 그 판단을 받아 줄 곳이 없었다 —
      오탐이라고 봐도 문구를 지우거나 게이트를 통째로 넘기는 길뿐이었다.
      「사람이 본다」고 해 놓고 본 결과를 적을 곳이 없으면 그 말은 빈말이다.

    ⛔ **오류는 이 길로 안 열린다** — 오류는 사람 판단 대상이 아니다.
    ⛔ 검토 기록은 **내용 해시**에 묶여 있다 — 한 글자만 고쳐도 다시 판단한다.
    """
    if not body:
        return False
    if "❌" in body:
        return True
    return not reviewed(path)


def note_pass(path, stage, verdict):
    """판정을 기록한다. 실패해도 게이트를 멈추지 않는다."""
    if not RECORDER or not RECORDER.exists():
        return
    try:
        subprocess.run([sys.executable, "-X", "utf8", str(RECORDER), "record",
                        str(path), "--stage", stage, "--verdict", verdict],
                       capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass


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
# 「절 번호로 가리킴」은 사용자 지시가 「만들지 말 것」이라(2026-09-23) 발행 때가
# 아니라 **쓰는 순간**에 걸려야 한다 — 문서가 다 쓰인 뒤에는 번호가 수십 곳에 퍼져 있다.
# 「반말 서술형」도 같다 — 「문서에는 반말 금지 · 전부」(2026-09-23 사용자). 검사기가
# Claude 만 읽는 지시 파일은 알아서 뺀다.
ALWAYS = ("「~하는 자리」", "절단형", "모호한 지칭", "지시어 확인", "평가 수식어",
          "절 번호로 가리킴", "반말 서술형")
# 검사기가 형식을 안 적은 산문이나 공지로 보고 물어보는 줄
FORM_ASK = "형식 미표기"


def form_question(out):
    """형식을 사용자에게 물으라는 한 줄 — 검사기가 「형식 미표기」를 냈을 때만, 제안 형식을 붙여.

    ★ **형식은 사용자가 고른다** (2026-10-30 사용자 결정 — 「문서의 종류나 성격에 따라 제안하고
      물어본 뒤에 사용자의 선택에 따라 검사」). 예전에는 발행 순간에 산문으로 접어 검사했다 —
      판별이 틀리면 정당한 지적이 사용자 모르게 빠졌다. 묻는 때는 문서를 새로 쓰거나 고칠 때뿐이다
      (같은 날 사용자 「수정할 때, 새로 쓸 때에만」) — 훅은 쓰고 고치는 파일만 본다.
    """
    line = next((l for l in out.splitlines() if FORM_ASK in l), "")
    if not line:
        return None
    guess = "notice" if '"notice"' in line or "form: notice" in line else "prose"
    what = ("공지(인사말과 맺음말 문단만 개조식 검사에서 뺌)" if guess == "notice"
            else "산문(개조식 검사를 뺌)")
    return (f"형식 미정 — 검사기 제안은 {what}이다 · 사용자에게 산문, 공지, 개조식 중 무엇으로 "
            f"검사할지 묻고 답을 머리말 `form:`(HTML 은 `<meta name=\"form\">`)에 적는다 · "
            f"세션이 답을 정하지 않는다")


def is_always(line):
    return any(k in line for k in ALWAYS)


def call_checker(path, *extra):
    """검사기를 한 번 돌린다. 실행이 안 되면 None — 빈 결과로 바꾸지 않는다.

    ⛔ **죽은 것과 깨끗한 것을 가른다**(외부 검토 2026-09-18).
       예전에는 `done.stdout or ''` 만 냈다. 검사기가 터지면 `stdout` 이 비고
       `stderr` 에만 자취가 남는데, 부르는 쪽은 그 빈 문자열을 **「지적 없음」**
       으로 읽고 `structure: pass` 를 적었다 — **검사를 못 한 문서가 통과 기록을
       달고 발행됐다.** 이 저장소가 지키기로 한 것의 정반대다.

       종료 코드로 가른다 — `0`(깨끗함)과 `1`(지적 있음)만 결과로 받고,
       그 밖은 **못 돌린 것**이라 `None` 을 낸다. 부르는 쪽은 `None` 을 소리 내어
       다룬다(막지는 않되 「검사를 못 했다」고 말한다).
    """
    try:
        done = subprocess.run(
            [sys.executable, "-X", "utf8", str(CHECKER), str(path), *extra],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # ⛔ **종료 코드만으로는 못 가른다** — 검사기는 오류를 찾으면 `1` 로 끝내는데
    #    파이썬이 터져도 `1` 이다(검토자의 재현이 그 모양이었다: 검사기 경로를
    #    실행 불가능한 파일로 바꿈 → SyntaxError → rc 1 · stdout 빔).
    #    가르는 것은 **낸 말**이다 — 멀쩡히 돈 회차는 지적이 없어도 합계 줄을 낸다.
    if not (done.stdout or "").strip():
        tail = (done.stderr or "").strip().splitlines()
        sys.stderr.write(
            f"⛔ 한글 검사기가 아무 말도 없이 끝났습니다(종료 코드 "
            f"{done.returncode}) — {os.path.basename(str(path))} 는 "
            f"**검사되지 않았습니다**\n"
            + (f"   {tail[-1][:160]}\n" if tail else ""))
        return None
    return done.stdout


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

    검사기가 「형식 미표기」로 물어보면 사용자에게 형식을 물으라고 적는다(`form_question`).
    쓰는 순간에는 알리기만 하고, 발행 순간에는 형식을 적을 때까지 막는다 — 막는 줄이
    열쇠(머리말 한 줄)를 함께 적는다. 무엇을 뺄지는 검사기가 정한다.
    """
    if not CHECKER.exists():
        return f"⚠️ 전역 문서 검사를 못 돌렸다 — 검사기 없음 ({CHECKER})"
    # ⛔ **발행 순간에는 설정을 무시하고 전부 본다**(`--no-rules`). 전역 규칙과 검사기
    #    주석은 진작 「발행 게이트가 쓰는 것」이라 적어 뒀는데 이 줄이 없었다
    #    (2026-09-23 확인). 그동안 프로젝트 설정이 끈 갈래는 발행 때도 꺼진 채였다.
    #    쓰는 순간은 설정을 따른다 — 초안의 소음을 줄이는 쪽이 설정의 쓸모다.
    full = () if errors_only else ("--no-rules",)
    out = call_checker(path, *full)
    if out is None:
        return "⚠️ 전역 문서 검사를 못 돌렸다 — 실행 실패 또는 25초 초과"
    # 부분 검사여도 **잡힌 것은 함께 낸다.** 알림만 내고 지적을 버리면 실제로
    # 잡은 오류가 사라진다(실측: 값 슬롯을 못 찾은 파일에서 오류 2건을 버리고 있었다).
    blind = BLIND.search(out)

    ask = form_question(out)

    hits = [l for l in out.splitlines() if "❌" in l or (not errors_only and "⚠️" in l)]
    if errors_only:
        hits = [l for l in hits if is_always(l)]
    hits = condense(hits)[:12]
    if blind:
        hits.insert(0, "⚠️ 값 슬롯을 못 찾아 부분 검사만 됐다 — 합격이 아니라 "
                       "안 본 것이다 · 표·목록·「라벨: 값」으로 다시 쓸 것")
    if ask:
        hits.insert(0, f"❓ {ask}" if errors_only else f"❌ {ask}")
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


#: 명령 앞머리의 `cd <어디> &&` — 뒤따르는 상대 경로의 기준이다
CD_PREFIX = re.compile(r'^\s*cd\s+(?:"([^"]+)"|\'([^\']+)\'|([^\s&;|]+))\s*&&')
#: 같은 명령 안에서 정한 셸 변수 — `SP="C:/..." python ...` 의 그 자리
SHELL_VAR = re.compile(r'(?:^|[\s;&])([A-Za-z_][A-Za-z0-9_]*)='
                       r'(?:"([^"]*)"|\'([^\']*)\'|([^\s;&|]+))')
VAR_USE = re.compile(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?')


def in_command(cmd, p):
    """명령이 스스로 들고 있는 것으로 경로를 끝까지 푼다.

    ⛔ **왜 필요한가.** 발행 명령은 거의 늘 `cd <빌드 폴더> && <도구> <상대 경로>`
    이거나 `SP="..." <도구> $SP/문서.md` 꼴이다. 훅은 세션의 작업 디렉터리에서
    도는데 그 둘 다 **명령 안에서** 자리를 옮기므로, 뽑아 낸 상대 경로가 훅
    쪽에서는 열리지 않는다. 그러면 `os.path.exists` 가 False 를 내고 검사도
    막기도 안내도 통째로 건너뛴다.

    실측 2026-09-21 — 스물한 날치 발행 대상 35개 중 **32개가 이 이유로 안
    열렸다.** 마침 전부 작업 폴더(scratchpad) 파일이라 결과는 맞았지만, 그건
    건너뛸 것이라 건너뛴 것이 아니라 **못 찾아서 건너뛴 것**이다. 같은 침묵이
    진짜 발행도 삼킨다.

    ⚠️ **못 푸는 것 하나 — 앞선 호출에서 내보낸 셸 변수.** 같은 명령 안에서
       정한 값은 읽지만 `export` 로 먼저 내보낸 것은 못 본다. 그때는 빈 값을
       돌려 대상에서 뺀다 — 무엇을 가리키는지 모르면 작업 문서인지 공유 자료
       인지도 못 가르므로 막을 근거가 없다. **대신 측정기가 센다**
       (`measure_layer2_uptake.py` 의 「못 푼 대상」) — 안 적으면 그 순간부터
       미탐이다. 실측 21일에 다섯 건이고 전부 작업 폴더였다.
    """
    values = {}
    for m in SHELL_VAR.finditer(cmd or ""):
        values[m.group(1)] = m.group(2) or m.group(3) or m.group(4) or ""

    def swap(m):
        name = m.group(1)
        return values.get(name) or os.environ.get(name) or m.group(0)

    p = VAR_USE.sub(swap, p)
    if "$" in p:
        return ""                       # 못 푼 변수가 남았다 — 짐작하지 않는다
    p = resolve(p)
    if os.path.isabs(p):
        return p
    m = CD_PREFIX.match(cmd or "")
    base = resolve(m.group(1) or m.group(2) or m.group(3)) if m else ""
    return os.path.join(base, p) if base else p


#: Codex 는 파일을 `apply_patch` 로 쓴다 — 패치의 파일 머리에 경로가 있다(세션 cwd 기준).
#: **이 게이트가 Codex payload 를 직접 읽는다**(2026-10-01) — 전에는 설정 거울의 Codex 어댑터가
#: Claude 모양(`Write`)으로 옮겨 넣었다. 옮기는 사본이 따로 있으면 한쪽만 고쳐진다.
PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update) File: (.+?)\s*$", re.I)

#: 쓰기 도구 — Claude 는 Write · Edit · MultiEdit, Codex 는 apply_patch
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "apply_patch")
_CHECKER_MODULE = None


def checker_module():
    """검사기를 모듈로 불러온다 — 가운뎃점 대장은 검사기가 정본이라 판정을 따로 두지 않는다."""
    global _CHECKER_MODULE
    if _CHECKER_MODULE is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("doc_style_check_for_gate", CHECKER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _CHECKER_MODULE = module
    return _CHECKER_MODULE


def write_paths(payload):
    """이번 쓰기가 건드릴 파일 — **아직 없는 파일도** 낸다(새로 만드는 문서는 첫 줄부터 본다)."""
    inp = payload.get("tool_input") or {}
    raw = [str(inp["file_path"]).strip()] if str(inp.get("file_path") or "").strip() else []
    patch = inp.get("patch") or inp.get("command") or ""
    if isinstance(patch, str):
        raw += [m.group(1) for m in map(PATCH_FILE.match, patch.splitlines()) if m]
    base = Path(payload.get("cwd") or os.getcwd())
    return sorted({str(Path(r) if Path(r).is_absolute() else base / r) for r in raw})


def middot_track(payload):
    """쓰기 직전 — 처음 고치는 문서의 가운뎃점 줄을 기존 줄로 적는다. 막지 않는다.

    ★ 기존 발행 문서는 고치지 않는다(2026-10-13 사용자) — 그래서 고치기 **전** 모습을 적어 두고
      검사기가 그 뒤에 생긴 줄만 짚는다. 기록에 실패하면 그 문서는 대장 밖으로 남아 건수만
      알린다(덜 짚을 뿐 막지는 않는다 — 쓰기를 막을 일이 아니다).
    """
    if not CHECKER.exists():
        return
    for fp in write_paths(payload):
        if DOC.search(fp) and not skipped(fp):
            try:
                checker_module().middot_baseline(fp)
            except Exception:           # noqa: BLE001 — 기록 실패로 쓰기를 막지 않는다
                pass


def middot_report(fp):
    """방금 쓴 문서의 가운뎃점 새 줄 — 「파일당 세션 한 번」과 상관없이 쓸 때마다 낸다.

    ⛔ 그 상한을 따르면 같은 문서에 두 번째로 쓴 가운뎃점은 쓰는 순간에 안 보인다.
       새 줄만 짚으므로 초안의 소음이 아니다.
    """
    if not CHECKER.exists():
        return []
    try:
        found = checker_module().middot_errors(fp, None, numbered=fp.lower().endswith(".md"))
    except Exception:                   # noqa: BLE001 — 발행 직전 검사가 다시 본다
        return []
    return [f"   ❌ [띄어 쓴 가운뎃점] {msg}" for msg in found]


def patch_paths(payload):
    """Codex `apply_patch` 가 건드린 파일 중 실제로 있는 것 — 절대 경로."""
    inp = payload.get("tool_input") or {}
    raw = [str(inp["file_path"]).strip()] if str(inp.get("file_path") or "").strip() else []
    patch = inp.get("patch") or inp.get("command") or ""
    if isinstance(patch, str):
        raw += [m.group(1) for m in map(PATCH_FILE.match, patch.splitlines()) if m]
    base = Path(payload.get("cwd") or os.getcwd())
    out = []
    for r in raw:
        p = Path(r) if Path(r).is_absolute() else base / r
        if p.is_file():
            out.append(str(p.resolve()))
    return sorted(set(out))


def targets(payload):
    """이번 호출에서 검사할 파일과 모드를 정한다."""
    ev = payload.get("hook_event_name") or ""
    name = payload.get("tool_name") or ""
    inp = payload.get("tool_input") or {}

    if ev == "PostToolUse" and name in ("Write", "Edit", "MultiEdit"):
        fp = str(inp.get("file_path") or "")
        if fp and DOC.search(fp) and not skipped(fp):
            return [fp], True, "once"
    if ev == "PostToolUse" and name == "apply_patch":
        found = [fp for fp in patch_paths(payload) if DOC.search(fp) and not skipped(fp)]
        if found:
            return found, True, "once"

    if ev == "PreToolUse":
        if name == "Artifact":
            fp = str(inp.get("file_path") or "")
            if fp and DOC.search(fp):
                return [fp], False, "always"
        if name in ("Bash", "PowerShell"):
            cmd = str(inp.get("command") or "")
            if PUBLISH.search(cmd) and not DRYRUN.search(cmd):
                # ⛔ 건너뛸지 가르는 것은 **푼 뒤의 경로**다. 상대 경로 그대로
                #    보면 `scratchpad/데모.md` 가 `데모.md` 로 뽑혀 작업 문서가
                #    검사 대상으로 올라온다(그 반대로도 샌다).
                found = [in_command(cmd, m) for m in
                         re.findall(r'["\']?([^\s"\']+\.(?:md|html))["\']?', cmd)]
                found = [m for m in found if m and not skipped(m)]
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
        if fp and KOREAN_DOC.search(fp) and not skipped(fp):
            return [fp]
    if ev == "PostToolUse" and name == "apply_patch":
        return [fp for fp in patch_paths(payload) if KOREAN_DOC.search(fp) and not skipped(fp)]

    if ev == "PreToolUse":
        if name == "Artifact":
            fp = str(inp.get("file_path") or "")
            if fp and KOREAN_DOC.search(fp) and not skipped(fp):
                return [fp]
        if name in ("Bash", "PowerShell"):
            cmd = str(inp.get("command") or "")
            if PUBLISH.search(cmd) and not DRYRUN.search(cmd):
                found = [resolve(match) for match in re.findall(
                    r'["\']?([^\s"\']+\.(?:md|html|txt|json|jsonl|ya?ml|properties))["\']?',
                    cmd,
                    re.I,
                )]
                return [match for match in found if match and not skipped(match)][:3]
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


def deny(reason):
    """PreToolUse 에서 막는다 — `permissionDecision: deny` JSON 을 내고 종료 코드 0.

    ⛔ **종료 코드 2 로 막지 않는다** — Codex 0.159.1 은 그것을 막음이 아니라 「Failed」로 받고
       명령을 그대로 실행했다(2026-10-01 실측 · 공식 문서는 종료 코드 2 가 막는다고 적었다).
       이 JSON 은 Claude Code 와 Codex 둘 다 막음으로 받는다(둘 다 실측). `install.py --codex`
       로 설치한 PC 는 어댑터 없이 이 훅을 바로 부르므로 훅이 직접 이 모양으로 답해야 한다.
    """
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}},
                     ensure_ascii=False))
    return 0


def gate_error(payload, exc):
    """게이트가 예외로 죽었을 때 — push · 배포 · 발행이면 막는 글, 아니면 빈 글.

    ⛔ 훅이 예외로 끝나면(종료 코드 1) Claude Code 는 막지 않고 명령을 그대로 실행한다 — 비차단
       오류로 본다. 판정 기록 칸 하나의 모양이 틀린 것만으로 열린 지적이 있는 문서가 push 를
       통과했다(2026-10-13 게이트 부정 시험). 판정하지 못하면 막는다.
    ⛔ 무엇을 하는 명령인지조차 못 가르면 막지 않는다 — 그러면 Bash 명령 전부가 막힌다.
    """
    if (payload.get("hook_event_name") or "") != "PreToolUse":
        return ""
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    if FORCE in cmd:
        return ""
    gated = (payload.get("tool_name") or "") == "Artifact" or bool(DEPLOY.search(cmd))
    for probe in (lambda: _push_parser().push_target(cmd) is not None,
                  lambda: targets(payload)[2] == "always"):
        try:
            gated = gated or bool(probe())
        except Exception:               # noqa: BLE001 — 가르지 못한 쪽은 막는 근거가 아니다
            pass
    if not gated:
        return ""
    return "\n".join([
        "⛔ 보류 — 한글 게이트가 오류로 판정하지 못했습니다",
        f"   {type(exc).__name__}: {str(exc)[:300]}",
        "",
        "  판정하지 못하면 막습니다. 상태 기록(~/.claude/state/korean-layer2-*.jsonl ·",
        "  korean-check-pass.jsonl)에 깨진 줄이 없는지 먼저 보고, 오류를 고친 뒤 다시 실행합니다.",
        "",
        f"  정말 그대로 진행해야 하면 명령 앞에 `{FORCE}` 을 붙입니다 — 명령문에 남습니다."])


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    try:
        return _main(payload)
    except Exception as e:              # noqa: BLE001
        import traceback
        traceback.print_exc()
        stop = gate_error(payload, e)
        return deny(stop) if stop else 0


def _main(payload):
    # 쓰기 직전 — 가운뎃점 기존 줄을 적고 끝(막지 않는다) · 시험 통로에서는 상태를 안 쓴다
    if ((payload.get("hook_event_name") or "") == "PreToolUse"
            and (payload.get("tool_name") or "") in WRITE_TOOLS):
        if "--probe" not in sys.argv:
            middot_track(payload)
        return 0
    # push · 사이트 배포는 문서 파일을 명령에 적지 않으므로 먼저 본다 · 시험 통로에서도 돈다
    # (배포 통과 기록만 시험 통로에서 안 쓴다)
    stop = push_block(payload) or deploy_block(payload, probe="--probe" in sys.argv)
    if stop:
        return deny(stop)

    files, errors_only, mode = targets(payload)
    korean_files = korean_targets(payload)
    if not files and not korean_files:
        return 0

    # ⛔ **시험 통로.** 상태를 읽지도 쓰지도 않는다 — 「파일당 세션 1회」 때문에
    #    같은 파일로 두 번 재면 둘째가 조용하고, 그것을 「이 도구를 안 본다」로
    #    읽게 된다. 2026-09-15 에 그 오독을 **세 번** 했다. 재현 시험이 상태를
    #    공유하지 않게 이 통로로 부른다.
    probe = "--probe" in sys.argv

    key = str(payload.get("session_id") or "-")
    # 안내는 발행 경로(always)에서도 문서마다 한 번만 내야 하므로 상태가 필요하다.
    # 노션 발행 하나가 수십 번 호출된다(하루 46회 · 문서로는 6.4건).
    state = {} if probe else load()
    seen = state.setdefault(key, {}) if (mode == "once" and not probe) else {}

    blocks = []
    for fp in files:
        if not os.path.exists(fp):
            continue
        middot = middot_report(fp) if mode == "once" else []
        if mode == "once" and fp in seen:
            if middot:
                blocks.append(f"{os.path.basename(fp)}\n" + "\n".join(middot))
            continue
        body = run_checker(fp, errors_only)
        if mode == "once":
            seen[fp] = time.time()
        # ⛔ **기계가 낸 판정은 기계가 적는다.** 사람이 따로 기록하게 하면 또
        #    「기억해야 도는 구조」가 된다. 발행 게이트와 정지 장치가 이 기록을
        #    읽어 「지금 내용이 통과했나」를 판정한다(2026-09-16).
        if not probe:
            note_pass(fp, "structure", "fail" if (middot or blocking(fp, body)) else "pass")
        body = "\n".join([body] * bool(body) + middot)
        if body:
            blocks.append(f"{os.path.basename(fp)}\n{body}")

    korean_blocks = []
    for fp in korean_files:
        if not os.path.exists(fp):
            continue
        body = run_korean_checker(fp)
        if body:
            korean_blocks.append(f"{os.path.basename(fp)}\n{body}")

    # ⛔ **막는 것이 먼저다.** 지적을 보여 주고 나서 발행을 허용하면, 그 지적은
    #    발행된 뒤에 읽힌다. 통과 기록이 없으면 여기서 멈춘다.
    #    확인 안 된 표시는 상태를 안 쓰므로 시험 통로에서도 막는다.
    if mode == "always" or korean_files:
        stop = (unverified_block(payload, korean_files or files)
                or ask_block(payload, korean_files or files)
                or fix_block(payload, korean_files or files)
                or unjudged_block(payload, korean_files or files))
        if stop:
            if not probe:
                save(state)
            return deny(stop)
    if not probe:
        stop = publish_block(payload, korean_files or files)
        if stop:
            if mode == "once" or True:
                save(state)
            return deny(stop)

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
