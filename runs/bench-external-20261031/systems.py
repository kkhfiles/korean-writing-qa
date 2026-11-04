"""비교 대상 도구를 같은 모양으로 부르는 어댑터 — 글 한 편을 받아 지적 목록이나 고친 글을 돌려준다.

모든 도구가 같은 입력(줄 단위 글)을 받고 같은 모양을 낸다.

- **지적형**: `findings` = [{line(1부터), quote, fix, kind}]
- **교정형**: `text_out` = 고친 글(줄 수 유지). 지적은 줄별 차이에서 만든다
- **잰 것**: 걸린 초, 환산 비용(SDK 가 주는 API 단가 환산 · 청구액 아님), 입력과 출력 토큰, 모델

    from systems import run, SYSTEMS
    r = run("plain-claude", text, workdir)
"""
from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "assets" / "doc-style-check.py"
JUDGE = REPO / "scripts" / "judge_layer2.py"
IMNOTAI = Path.home() / ".claude/plugins/cache/im-not-ai/humanize-korean/2.3.2/skills/humanize-korean/references/quick-rules.md"
HUNSPELL_DIR = Path.home() / ".local/share/korean-writing-qa/bench-external/dl/Standard_Korean_GEC/KAGAS/aff-dic"

OUT_SPEC = """출력은 JSON 배열 하나만 냅니다. 다른 말은 쓰지 않습니다.
[{"line": 줄 번호, "quote": "원문에서 고칠 부분을 글자 그대로", "fix": "고친 표현", "why": "짧은 까닭"}]
고칠 곳이 없으면 []를 냅니다."""

PLAIN_SYSTEM = """당신은 한국어 교정 전문가입니다. 사용자가 줄 번호를 붙인 글을 줍니다.
맞춤법, 띄어쓰기, 문장 부호, 문법, 어색하거나 부자연스러운 표현, 업무 글에 맞지 않는 표현,
앞뒤가 맞지 않는 내용처럼 고쳐야 할 곳을 모두 찾습니다. 고칠 필요가 없는 곳은 지적하지 않습니다.
""" + OUT_SPEC


def imnotai_system() -> str:
    rules = IMNOTAI.read_text(encoding="utf-8")
    return ("다음은 한국어 글에서 AI 티와 번역투를 찾는 규칙입니다(im-not-ai humanize-korean 2.3.2 quick-rules).\n\n"
            + rules + "\n\n사용자가 줄 번호를 붙인 글을 줍니다. 위 규칙으로 고쳐야 할 곳을 모두 찾습니다.\n" + OUT_SPEC)


@dataclass
class Result:
    system: str
    findings: list = field(default_factory=list)
    text_out: str | None = None
    seconds: float = 0.0
    cost_usd: float | None = None
    in_tok: int = 0
    out_tok: int = 0
    in_chars: int = 0
    out_chars: int = 0
    model: str = ""
    error: str = ""

    def dict(self) -> dict:
        return asdict(self)


def numbered(lines: list[str]) -> str:
    return "\n".join(f"{i}\t{x}" for i, x in enumerate(lines, 1))


def parse_findings(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text or "", re.S)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for x in arr if isinstance(arr, list) else []:
        if isinstance(x, dict) and str(x.get("line", "")).strip().lstrip("-").isdigit():
            out.append({"line": int(x["line"]), "quote": str(x.get("quote") or ""),
                        "fix": x.get("fix"), "kind": str(x.get("why") or "")[:80]})
    return out


def usage_tokens(u: dict | None) -> tuple[int, int]:
    u = u or {}
    i = sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                                          "prompt_tokens"))
    o = int(u.get("output_tokens") or u.get("completion_tokens") or 0)
    return i, o


# ── 모델 호출 ─────────────────────────────────────────────────────────────────
CODEX_WEEK_MAX = 93      # 주간 사용률이 이 값 이상이면 부르지 않음 — 사용자의 평일 Codex 작업 몫. 11-02 sol 재측정 때 한 번 풀었다가 주간 100%에 닿아 되돌림
_quota = {"at": 0.0, "q": None}


def codex_guard() -> None:
    if time.time() - _quota["at"] > 300:
        from llm_playbook.backends import codex_sdk
        _quota["q"], _quota["at"] = codex_sdk.quota(), time.time()
    q = _quota["q"] or {}
    week = (q.get("secondary") or {}).get("used_percent")
    five = (q.get("primary") or {}).get("used_percent")
    if week is not None and week >= CODEX_WEEK_MAX:
        raise RuntimeError(f"Codex 주간 사용률 {week}% — 실험 상한 {CODEX_WEEK_MAX}% 이상이라 부르지 않음")
    if five is not None and five >= 100:
        raise RuntimeError("Codex 5시간 사용률 100% — 풀린 뒤 다시 돌림")


def call_model(vendor: str, model: str, system: str, user: str, timeout: float = 900) -> dict:
    if vendor == "claude":
        from llm_playbook.backends.claude_sdk import call_messages
        r = call_messages(model=model, system=system, user=user, max_tokens=16000, timeout=timeout)
        return {"text": r.get("text") or "", "model": r.get("model") or model,
                "cost_usd": r.get("cost_usd"), "usage": r.get("usage")}
    if vendor == "codex":
        codex_guard()
        from llm_playbook.backends import codex_http
        r = codex_http.call(user, model=model, system_prompt=system, fallback=False, timeout=timeout)
        if r.get("error"):
            raise RuntimeError(f"codex {r.get('error')} {r.get('detail') or ''}"[:300])
        return {"text": r.get("text") or "", "model": r.get("model") or model, "cost_usd": None, "usage": r.get("usage")}
    if vendor == "agy":
        from llm_playbook.backends import agy
        r = agy.call(user, model=model, system=system, fallback=False, timeout=timeout)
        if not r.get("ok", True) or not (r.get("text") or r.get("response")):
            raise RuntimeError(f"agy {r.get('error') or r}"[:300])
        return {"text": r.get("text") or r.get("response") or "", "model": r.get("model") or model,
                "cost_usd": None, "usage": r.get("usage")}
    raise ValueError(vendor)


MODEL_SYSTEMS = {
    "plain-claude": ("claude", "opus", PLAIN_SYSTEM),
    "plain-gpt": ("codex", "astra-medium", PLAIN_SYSTEM),
    "plain-argon": ("agy", "argon-medium", PLAIN_SYSTEM),
    "plain-sol": ("codex", "sol-high", PLAIN_SYSTEM),       # 2026-11-02 사용자 요청으로 더한 재측정
    "plain-flash": ("agy", "flash-high", PLAIN_SYSTEM),
    "imnotai-claude": ("claude", "opus", None),
}


def run_model(name: str, lines: list[str]) -> Result:
    vendor, model, system = MODEL_SYSTEMS[name]
    system = system or imnotai_system()
    res = Result(name, model=model)
    t = time.time()
    try:
        user = numbered(lines)
        r = call_model(vendor, model, system, user)
        res.in_chars, res.out_chars = len(system) + len(user), len(r["text"])
        res.findings = parse_findings(r["text"])
        res.model = r["model"]
        res.cost_usd = r.get("cost_usd")
        res.in_tok, res.out_tok = usage_tokens(r.get("usage"))
        if not res.findings and "[" not in r["text"]:
            res.error = "JSON 없음: " + r["text"][:200]
    except Exception as e:      # 한 편 실패가 실험 전체를 멈추지 않게
        res.error = f"{type(e).__name__}: {e}"[:400]
    res.seconds = time.time() - t
    return res


# ── 이 저장소 ─────────────────────────────────────────────────────────────────
L1_LINE = re.compile(r"^\s*(❌|⚠️)\s+\[(.+?)\]\s+(\d+)행\s+(.*)$")
FRONT = ["---", "form: prose", "---", ""]


def write_doc(lines: list[str], work: Path, front: list[str] = FRONT) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    p = work / "doc.md"
    p.write_text("\n".join(front + lines) + "\n", encoding="utf-8")
    return p


def run_l1(lines: list[str], work: Path, front: list[str] = FRONT) -> Result:
    res = Result("l1", model="결정론")
    p = write_doc(lines, work, front)
    t = time.time()
    # 공개판 기본값으로 잰다 — 이 PC 의 개인 기준(반말 서술형 전부 오류)이 섞이지 않게(2026-11-03)
    env = {**os.environ, "KOREAN_QA_PERSONAL_RULES": "off"}
    out = subprocess.run([sys.executable, "-X", "utf8", str(CHECKER), "--no-rules", str(p)],
                         capture_output=True, text=True, encoding="utf-8", env=env)
    res.seconds = time.time() - t
    for raw in out.stdout.splitlines():
        m = L1_LINE.match(raw)
        if not m:
            continue
        n = int(m.group(3)) - len(front)
        body = m.group(4)
        q = re.search(r"「(.+?)」", body)
        res.findings.append({"line": n, "quote": q.group(1) if q else body.split(" — ")[0],
                             "fix": None, "kind": ("오류 " if m.group(1) == "❌" else "주의 ") + m.group(2),
                             "msg": body.split(" — ", 1)[1] if " — " in body else ""})
    return res


def run_l2(lines: list[str], work: Path, model: str = "opus", front: list[str] = FRONT,
           scope: str = "wide", thinking: str | None = None, name: str | None = None) -> Result:
    """2층 판정기를 격리한 기록 폴더로 부른다 — 쌓인 사용자 답이 프롬프트에 섞이지 않게.
    scope 는 고친 말의 범위(wide = 10-31 측정 때 판정기, narrow = 11-03 부터 기본값)."""
    res = Result(name or ("l2" if scope == "wide" else f"l2-{scope}"), model=model)
    p = write_doc(lines, work, front)
    env = dict(os.environ)
    env["KOREAN_QA_FIX_SCOPE"] = scope
    if thinking:
        env["KOREAN_QA_JUDGE_THINKING"] = thinking
    for k, f in (("KOREAN_QA_JUDGE_LOG", "judge.jsonl"), ("KOREAN_QA_ANSWER_LOG", "answers.jsonl"),
                 ("KOREAN_QA_DECISION_LOG", "decisions.jsonl"), ("KOREAN_QA_DISMISS_LOG", "dismissals.jsonl"),
                 ("KOREAN_QA_INSTRUCTION_LOG", "instructions.jsonl")):
        env[k] = str(work / f)
    t = time.time()
    out = subprocess.run([sys.executable, "-X", "utf8", str(JUDGE), str(p), "--backend", "claude",
                          "--model", model, "--json", str(work / "l2.json")],
                         capture_output=True, text=True, encoding="utf-8", env=env)
    res.seconds = time.time() - t
    if out.returncode not in (0, 1):
        res.error = (out.stderr or out.stdout)[-400:]
        return res
    log = work / "judge.jsonl"
    # 판정 기록이 없으면 실패 — 판정기가 예외로 끝나도 종료 코드 1이라 위 조건을 통과했다(2026-11-04 측정 도중
    # 판정기 파일을 고쳐 D2 160건 중 105건이 지적 0건으로 조용히 기록됨)
    if not log.exists() or not log.read_text(encoding="utf-8").strip():
        res.error = ("판정 기록 없음 — " + (out.stderr or out.stdout))[-400:]
        return res
    for row in (json.loads(l) for l in log.open(encoding="utf-8") if l.strip()) if log.exists() else []:
        res.cost_usd = (res.cost_usd or 0) + float(row.get("cost_usd") or 0)
        res.in_tok += sum(int(row.get(k) or 0) for k in ("input_tokens", "cache_write", "cache_read"))
        res.out_tok += int(row.get("output_tokens") or 0)
        for kind, items in (("고칠", row.get("fixes") or []), ("사람 확인", row.get("asks") or [])):
            for f in items:
                n = f.get("line")
                if isinstance(n, int):
                    res.findings.append({"line": n - len(front), "quote": str(f.get("phrase") or ""),
                                         "fix": f.get("fix"), "kind": f"{kind} {f.get('category') or ''}".strip(),
                                         "check": f.get("check"), "why": f.get("why")})
    return res


# ── 교정형 공개 도구 ──────────────────────────────────────────────────────────
_kiwi = None


def run_kiwi(lines: list[str]) -> Result:
    """Kiwi 띄어쓰기 교정(`space`) — 오타 교정은 형태소 분석 안에서만 돌아 글로 되돌리는 길이 없어 뺌."""
    global _kiwi
    from kiwipiepy import Kiwi
    _kiwi = _kiwi or Kiwi()
    res = Result("kiwi-space", model="kiwipiepy 0.23")
    t = time.time()
    res.text_out = "\n".join(_kiwi.space(x, reset_whitespace=False) if x.strip() else x for x in lines)
    res.seconds = time.time() - t
    res.findings = diff_findings(lines, res.text_out.split("\n"))
    return res


_gec = None


def run_kobart(lines: list[str]) -> Result:
    """Soyoung97/gec_kr(KoBART 문법 교정 · Kor-Native 등으로 학습) — 문장 단위로 CPU 에서 돌림."""
    global _gec
    import torch
    from transformers import AutoTokenizer, BartForConditionalGeneration
    if _gec is None:
        tok = AutoTokenizer.from_pretrained("Soyoung97/gec_kr")
        mdl = BartForConditionalGeneration.from_pretrained("Soyoung97/gec_kr").eval()
        _gec = (tok, mdl)
    tok, mdl = _gec
    res = Result("kobart-gec", model="Soyoung97/gec_kr")
    t = time.time()
    out = []
    for x in lines:
        if not x.strip():
            out.append(x)
            continue
        sents = re.split(r"(?<=[.!?])\s+", x)
        fixed = []
        for s in sents:
            ids = tok(s, return_tensors="pt", truncation=True, max_length=200).input_ids
            with torch.no_grad():
                g = mdl.generate(ids, max_length=256, num_beams=4)
            fixed.append(tok.decode(g[0], skip_special_tokens=True).strip())
        out.append(" ".join(fixed))
    res.seconds = time.time() - t
    res.text_out = "\n".join(out)
    res.findings = diff_findings(lines, out)
    return res


_hun = None


def run_hunspell(lines: list[str]) -> Result:
    """hunspell 한국어 사전(spellcheck-ko 0.7.92 · KAGAS 저장소에 든 것)으로 어절마다 철자 확인 — 지적만 함."""
    global _hun
    from spylls.hunspell import Dictionary
    _hun = _hun or Dictionary.from_files(str(HUNSPELL_DIR / "ko"))
    res = Result("hunspell-ko", model="spellcheck-ko 0.7.92")
    t = time.time()
    for i, x in enumerate(lines, 1):
        for w in re.findall(r"[가-힣]+", x):
            if not _hun.lookup(w):
                sug = next(iter(_hun.suggest(w)), None)
                res.findings.append({"line": i, "quote": w, "fix": sug, "kind": "철자"})
    res.seconds = time.time() - t
    return res


def diff_findings(before: list[str], after: list[str]) -> list[dict]:
    out = []
    for i, (a, b) in enumerate(zip(before, after), 1):
        if a == b:
            continue
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op != "equal":
                out.append({"line": i, "quote": a[max(0, i1 - 1):i2 + 1], "fix": b[j1:j2], "kind": "교정",
                            "span": [i1, i2]})
    return out


# hunspell-ko 는 뺐다(2026-10-31) — 순수 파이썬 구현(spylls)이 한국어 사전의 ICONV 를 못 읽어 「회의」도 철자 오류로
# 내고, 네이티브 바인딩(cyhunspell · hunspell)은 이 PC 에 컴파일러가 없어 설치가 안 됨. 함수는 다시 잴 때를 위해 둠
SYSTEMS = ["l1", "l2", "l2-narrow", "plain-claude", "plain-gpt", "plain-argon", "plain-sol", "plain-flash", "imnotai-claude", "kiwi-space", "kobart-gec"]


def run(name: str, lines: list[str], work: Path) -> Result:
    if name == "l1":
        return run_l1(lines, work)
    if name == "l2":
        return run_l2(lines, work)
    if name == "l2-narrow":
        return run_l2(lines, work, scope="narrow")
    if name.count("-") == 2 and name.startswith("l2-"):     # l2-<모델>-<사고 깊이>(2026-11-04 검사 단계 설정)
        _, m, t = name.split("-")
        return run_l2(lines, work, model=m, scope="narrow", thinking=t, name=name)
    if name in MODEL_SYSTEMS:
        return run_model(name, lines)
    if name == "kiwi-space":
        return run_kiwi(lines)
    if name == "kobart-gec":
        return run_kobart(lines)
    if name == "hunspell-ko":
        return run_hunspell(lines)
    raise ValueError(name)
