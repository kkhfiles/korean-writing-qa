"""D3 — AI가 쓴 업무 문서 초안을 도구마다 고쳐 쓰게 하고, 다른 회사 모델 셋이 블라인드로 견준다.

- **초안**: 공개 주제(가상 회사) 업무 문서 12편 — Claude Sonnet 과 GPT(sol)가 반씩 씀
- **고쳐 쓰기**
  - `ours`: 1층 검사기와 2층 판정기 지적을 Opus 세션이 반영(실사용 흐름) · 지적이 남으면 한 번 더(최대 2회)
  - `plain-*`: 같은 회사 모델에 「교정해 달라」만 부탁
  - `imnotai`: im-not-ai quick-rules 를 지시문으로 Opus 가 고쳐 씀
  - `none`: 초안 그대로(고쳐 쓰기가 나아지게 했는지 보는 기준)
- **비교**: `ours` 대 나머지를 판정자 셋(Claude Opus · GPT Astra · Gemini Argon)이 원문과 함께 보고 고름.
  A와 B 자리는 문서와 상대마다 고정 시드로 섞음
- 초안 주제는 가상이라 공개해도 되지만 글은 저장소 밖에 둠

    python -X utf8 runs/bench-external-20261031/bench_e2e.py drafts
    python -X utf8 runs/bench-external-20261031/bench_e2e.py revise <시스템…>
    python -X utf8 runs/bench-external-20261031/bench_e2e.py judge <판정자…>
    python -X utf8 runs/bench-external-20261031/bench_e2e.py score [--json 경로]
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, boot, hangul  # noqa: E402
import systems  # noqa: E402

OUT = Path(os.environ.get("BENCH_E2E_OUT") or DATA / "e2e")     # 1판 결과를 따로 채점할 때 바꿈
TOPICS = [
    "사내 공지: 다음 달부터 시행하는 정보보안 교육 의무화 안내",
    "주간 업무 보고: 고객 포털 개편 프로젝트 3주차 진행 상황",
    "회의록: 신규 협업 도구 도입 검토 회의",
    "제안서: 사내 문서 검색 시스템 도입 제안",
    "장애 사후 보고서: 결제 서버 40분 중단 원인과 재발 방지 대책",
    "고객 안내 메일: 정기 점검으로 인한 서비스 일시 중단 안내",
    "채용 공고: 백엔드 개발자 경력직 모집",
    "프로젝트 계획서: 모바일 앱 접근성 개선 프로젝트",
    "교육 결과 보고: 신입사원 온보딩 교육 결과와 개선점",
    "규정 변경 안내: 재택근무 규정 개정 주요 내용",
    "출장 결과 보고: 해외 전시회 참관 결과",
    "예산 요청서: 하반기 서버 증설 예산 요청",
]
WRITERS = [("claude", "sonnet"), ("codex", "sol-medium")]
DRAFT_SYSTEM = """회사 업무 문서를 씁니다. 가상의 회사 「한빛솔루션」 기준으로 그럴듯한 세부 내용(날짜, 숫자, 담당 부서)을 지어 넣습니다.
마크다운으로 한글 1,200~1,800자 분량을 씁니다. 문서 본문만 출력합니다."""
REWRITE_SYSTEM = """당신은 한국어 교정 전문가입니다. 사용자가 회사 업무 문서를 줍니다.
맞춤법, 띄어쓰기, 문법, 어색하거나 부자연스러운 표현, 업무 글에 맞지 않는 표현을 고칩니다. 원문의 사실과 뜻은 바꾸지 않습니다.
고친 문서 전체를 마크다운으로만 출력합니다. 다른 말은 쓰지 않습니다."""
OURS_REVISE = """당신은 회사 업무 문서를 고치는 작성자입니다. 사용자가 문서와 한국어 검사기의 지적 목록을 줍니다.
- [오류 …] 지적은 1층 검사기의 결정이라 반드시 고칩니다(실사용에서는 이 오류가 0이 될 때까지 발행이 막힘). 지적에 붙은 안내를 따릅니다
- 나머지 지적은 고칩니다. 수정안이 있으면 참고하되 더 나은 표현이 있으면 그것을 씁니다
- 나머지 지적이 틀렸다고 판단되면 그대로 둡니다
- 지적되지 않은 곳은 바꾸지 않습니다. 원문의 사실과 뜻은 바꾸지 않고, 원문에 없던 숫자나 사실을 더하지 않습니다
고친 문서 전체를 마크다운으로만 출력합니다. 다른 말은 쓰지 않습니다."""
JUDGE_SYSTEM = """당신은 회사 업무 문서 편집자입니다. 사용자가 원문과 두 수정본(A, B)을 줍니다. 다음 기준으로 견줍니다.
1. 원문의 사실과 뜻을 지켰는가 — 없던 내용 추가, 사실 변경, 빠뜨림은 크게 깎습니다
2. 맞춤법과 문법이 정확한가
3. 업무 문서로서 읽기 쉽고 간결하며 명확한가
4. 어색한 표현이나 AI가 쓴 티(상투적 표현, 과장된 수식, 번역투)가 남았는가
출력은 JSON 하나만: {"winner": "A" 또는 "B" 또는 "tie", "meaning_changes_A": 정수, "meaning_changes_B": 정수,
"defects_A": 정수, "defects_B": 정수, "why": "한두 문장"}"""
JUDGES = {"claude": ("claude", "opus"), "gpt": ("codex", "astra-medium"), "argon": ("agy", "argon-medium"),
          "sol": ("codex", "sol-high"), "flash": ("agy", "flash-high")}     # sol, flash 는 2026-11-02 재측정
RIVALS = ["none", "plain-claude", "plain-gpt", "plain-argon", "imnotai", "plain-sol", "plain-flash"]
REWRITERS = {"plain-claude": ("claude", "opus", REWRITE_SYSTEM), "plain-gpt": ("codex", "astra-medium", REWRITE_SYSTEM),
             "plain-argon": ("agy", "argon-medium", REWRITE_SYSTEM), "imnotai": ("claude", "opus", None),
             "plain-sol": ("codex", "sol-high", REWRITE_SYSTEM), "plain-flash": ("agy", "flash-high", REWRITE_SYSTEM)}


def strip_fence(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", t, re.S)
    return (m.group(1) if m else t).strip()


def log_cost(rec: dict, r: dict, seconds: float, system: str, user: str) -> None:
    rec["seconds"] = rec.get("seconds", 0) + seconds
    rec["cost_usd"] = (rec.get("cost_usd") or 0) + (r.get("cost_usd") or 0)
    i, o = systems.usage_tokens(r.get("usage"))
    rec["in_tok"] = rec.get("in_tok", 0) + i
    rec["out_tok"] = rec.get("out_tok", 0) + o
    rec["in_chars"] = rec.get("in_chars", 0) + len(system) + len(user)
    rec["out_chars"] = rec.get("out_chars", 0) + len(r.get("text") or "")
    rec["calls"] = rec.get("calls", 0) + 1


def drafts() -> None:
    (OUT / "drafts").mkdir(parents=True, exist_ok=True)
    for i, topic in enumerate(TOPICS):
        f = OUT / f"drafts/{i:02d}.json"
        if f.exists():
            continue
        vendor, model = WRITERS[i % 2]
        r = systems.call_model(vendor, model, DRAFT_SYSTEM, f"주제: {topic}")
        f.write_text(json.dumps({"topic": topic, "writer": f"{vendor}:{model}", "text": strip_fence(r["text"])},
                                ensure_ascii=False, indent=1), encoding="utf-8")
        print(i, model, hangul(r["text"]), flush=True)


def load_drafts() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / "drafts").glob("*.json"))]


def finding_list(findings: list[dict], lines: list[str]) -> str:
    out = []
    for f in findings:
        n = f["line"]
        line = lines[n - 1] if 0 < n <= len(lines) else ""
        fix = f" → 수정안: {f['fix']}" if f.get("fix") else (f" → 안내: {f['msg']}" if f.get("msg") else "")
        out.append(f"- {n}행 [{f['kind']}] 「{f['quote'][:120]}」{fix}\n  (그 줄: {line[:200]})")
    return "\n".join(out)


NOINVENT = """
- 지적을 고치려면 원문에 없는 정보(기준, 조건, 정의, 숫자, 담당, 일정 등)를 새로 넣어야 하면 고치지 않고 그대로 둡니다.
  그런 정보는 글쓴이만 압니다. 표현만 바꿔 고칠 수 있는 지적만 고칩니다"""


def revise_ours(text: str, work: Path, rounds: int = 2, mode: str = "ours") -> dict:
    """실사용 흐름(2판) — 공개판 기본 설정(개인 항목 끔)으로 검사하고, 사람 확인 지적은 고쳐 쓰기에 넘기지 않음
    (실사용에서는 사용자가 답함). 1판은 개인 엄격 모드에 사람 확인까지 자동 반영해 뜻 바뀜이 늘었다."""
    os.environ["KOREAN_QA_PERSONAL_RULES"] = "off"
    rec: dict = {"rounds": 0, "findings": [], "asks_left": []}
    cur = text
    for k in range(rounds):
        lines = cur.split("\n")
        l1 = systems.run_l1(lines, work / f"r{k}-l1", front=[])
        l2 = systems.run_l2(lines, work / f"r{k}-l2", front=[]) if mode != "l1only" else systems.Result("l2")
        for r in (l1, l2):
            rec["seconds"] = rec.get("seconds", 0) + r.seconds
            rec["cost_usd"] = (rec.get("cost_usd") or 0) + (r.cost_usd or 0)
            rec["in_tok"] = rec.get("in_tok", 0) + r.in_tok
            rec["out_tok"] = rec.get("out_tok", 0) + r.out_tok
            if r.error:
                rec["error"] = r.error
        asks = [f for f in l2.findings if f["kind"].startswith("사람 확인")]
        found = [f for f in l1.findings if f["kind"].startswith("오류")] + [f for f in l2.findings if f not in asks]
        rec["findings"].append(len(found))
        rec["asks_left"].append(len(asks))
        if not found:
            break
        user = cur + "\n\n## 검사기 지적\n" + finding_list(found, lines)
        prompt = OURS_REVISE.replace("\n고친 문서 전체를", NOINVENT + "\n고친 문서 전체를", 1) if mode == "ours-noinvent" \
            else OURS_REVISE
        t = time.time()
        r = systems.call_model("claude", "opus", prompt, user)
        log_cost(rec, r, time.time() - t, prompt, user)
        cur = strip_fence(r["text"])
        rec["rounds"] = k + 1
    rec["text"] = cur
    return rec


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import layer2_coverage as coverage  # noqa: E402


def for_author(f: dict, doc: str) -> bool:
    """작성자만 답할 수 있는 지적 — 사실 확인이 걸렸거나 수정안이 원문에 없는 정보를 들여옴(검토 화면의 「작성자 확인」)."""
    return coverage.needs_check(f) or bool(coverage.new_info(str(f.get("fix") or ""), doc))


def revise_ours2(text: str, work: Path, rounds: int = 2) -> dict:
    """지금 제품의 세션 흐름(2026-11-03) — 공개판 기본값으로 검사하고, 사람 확인과 작성자 확인(사실 확인, 새 정보)
    지적은 고쳐 쓰기에 넘기지 않음. 고쳐 쓰는 모델에는 정보를 지어내지 말라는 지시를 붙임(스킬 「확인 못 한 사실을
    짐작으로 고치지 않는다」)."""
    os.environ["KOREAN_QA_PERSONAL_RULES"] = "off"
    rec: dict = {"rounds": 0, "findings": [], "asks_left": [], "author_left": []}
    cur = text
    prompt = OURS_REVISE.replace("\n고친 문서 전체를", NOINVENT + "\n고친 문서 전체를", 1)
    for k in range(rounds):
        lines = cur.split("\n")
        l1 = systems.run_l1(lines, work / f"r{k}-l1", front=[])
        l2 = systems.run_l2(lines, work / f"r{k}-l2", front=[])
        for r in (l1, l2):
            rec["seconds"] = rec.get("seconds", 0) + r.seconds
            rec["cost_usd"] = (rec.get("cost_usd") or 0) + (r.cost_usd or 0)
            rec["in_tok"] = rec.get("in_tok", 0) + r.in_tok
            rec["out_tok"] = rec.get("out_tok", 0) + r.out_tok
            if r.error:
                rec["error"] = r.error
        asks = [f for f in l2.findings if f["kind"].startswith("사람 확인")]
        author = [f for f in l2.findings if f not in asks and for_author(f, cur)]
        found = [f for f in l1.findings if f["kind"].startswith("오류")] + \
                [f for f in l2.findings if f not in asks and f not in author]
        rec["findings"].append(len(found))
        rec["asks_left"].append(len(asks))
        rec["author_left"].append(len(author))
        if not found:
            break
        user = cur + "\n\n## 검사기 지적\n" + finding_list(found, lines)
        t = time.time()
        r = systems.call_model("claude", "opus", prompt, user)
        log_cost(rec, r, time.time() - t, prompt, user)
        cur = strip_fence(r["text"])
        rec["rounds"] = k + 1
    rec["text"] = cur
    return rec


def revise_apply(text: str, work: Path) -> dict:
    """검토 화면의 「바로 반영」만 — 모델이 다시 쓰지 않고, 판정기 수정안 가운데 글자 그대로 넣을 수 있는 것만 바꿈
    (`review_screen.literal`, 그 줄에 한 번만 나오는 표현, 작성자 확인이 아닌 것)."""
    import review_screen  # noqa: PLC0415
    os.environ["KOREAN_QA_PERSONAL_RULES"] = "off"
    lines = text.split("\n")
    l2 = systems.run_l2(lines, work / "r0-l2", front=[])
    rec = {"seconds": l2.seconds, "cost_usd": l2.cost_usd, "in_tok": l2.in_tok, "out_tok": l2.out_tok,
           "applied": 0, "skipped": 0}
    if l2.error:
        rec["error"] = l2.error
    for f in l2.findings:
        n, phrase, fix = f["line"], f["quote"], str(f.get("fix") or "")
        ok = (not f["kind"].startswith("사람 확인") and not for_author(f, text) and review_screen.literal(fix)
              and phrase and 0 < n <= len(lines) and lines[n - 1].count(phrase) == 1)
        if ok:
            lines[n - 1] = lines[n - 1].replace(phrase, fix, 1)
            rec["applied"] += 1
        else:
            rec["skipped"] += 1
    rec["text"] = "\n".join(lines)
    return rec


def revise_apply_guarded(text: str, log: Path) -> dict:
    """「바로 반영」에 수정안 가리개(`fix_guard.py`)를 더함 — 앞 변형이 남긴 판정 기록을 다시 써서 모델을
    부르지 않음(같은 지적에 가리개만 더한 효과를 봄). 넣을 때 뒤 조사를 받침에 맞춤."""
    import fix_guard  # noqa: PLC0415
    import review_screen  # noqa: PLC0415
    rows = [json.loads(l) for l in log.open(encoding="utf-8") if l.strip()]
    lines = text.split("\n")
    rec = {"applied": 0, "skipped": 0, "guarded": 0, "seconds": 0, "cost_usd": 0}
    for f in rows[-1].get("fixes") or []:
        n, phrase, fix = f["line"], str(f.get("phrase") or ""), str(f.get("fix") or "")
        if for_author(f, text) or not review_screen.literal(fix) or not phrase \
                or not 0 < n <= len(lines) or lines[n - 1].count(phrase) != 1:
            rec["skipped"] += 1
            continue
        if fix_guard.reasons(phrase, fix, lines[n - 1], text):
            rec["guarded"] += 1
            continue
        lines[n - 1] = fix_guard.fit_particle(lines[n - 1], phrase, fix)
        rec["applied"] += 1
    rec["text"] = "\n".join(lines)
    return rec


def revise(names: list[str]) -> None:
    for name in names:
        for i, d in enumerate(load_drafts()):
            f = OUT / f"revised/{name}/{i:02d}.json"
            if f.exists() and not json.loads(f.read_text(encoding="utf-8")).get("error"):
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            try:
                if name in ("ours", "ours-noinvent", "l1only"):
                    work = OUT / (f"work/{i:02d}" if name == "ours" else f"work-{name}/{i:02d}")
                    rec = revise_ours(d["text"], work, mode=name)
                elif name == "ours2":
                    rec = revise_ours2(d["text"], OUT / f"work-{name}/{i:02d}")
                elif name == "ours2-apply":
                    rec = revise_apply(d["text"], OUT / f"work-{name}/{i:02d}")
                elif name == "ours3-apply":
                    rec = revise_apply_guarded(d["text"], OUT / f"work-ours2-apply/{i:02d}/r0-l2/judge.jsonl")
                elif name == "plain-claude-apply3":
                    rec = revise_apply_guarded(revised("plain-claude", i, load_drafts()),
                                               OUT / f"work-plain-claude-apply/{i:02d}/r0-l2/judge.jsonl")
                elif name in ("plain-claude-ours2", "plain-claude-apply"):
                    # Claude 단순 요청으로 고친 글 위에 검사기를 얹음 — 검사기가 단순 요청에 더하는 몫을 잼(2026-11-03)
                    base = revised("plain-claude", i, load_drafts())
                    if base is None:
                        raise RuntimeError("plain-claude 결과 없음")
                    run = revise_ours2 if name == "plain-claude-ours2" else revise_apply
                    rec = run(base, OUT / f"work-{name}/{i:02d}")
                else:
                    vendor, model, system = REWRITERS[name]
                    system = system or (systems.imnotai_system().split("사용자가 줄 번호")[0]
                                        + "사용자가 글을 줍니다. 위 규칙으로 고쳐 쓴 글 전체를 마크다운으로만 출력합니다. "
                                          "원문의 사실과 뜻은 바꾸지 않습니다.")
                    rec = {}
                    t = time.time()
                    r = systems.call_model(vendor, model, system, d["text"])
                    log_cost(rec, r, time.time() - t, system, d["text"])
                    rec["text"] = strip_fence(r["text"])
            except Exception as e:
                rec = {"error": f"{type(e).__name__}: {e}"[:300]}
            f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
            print(name, i, rec.get("rounds", ""), rec.get("findings", ""), f"{rec.get('seconds', 0):.0f}초",
                  rec.get("error", "")[:80], flush=True)


def revised(name: str, i: int, drafts_: list[dict]) -> str | None:
    if name == "none":
        return drafts_[i]["text"]
    f = OUT / f"revised/{name}/{i:02d}.json"
    if not f.exists():
        return None
    rec = json.loads(f.read_text(encoding="utf-8"))
    return None if rec.get("error") else rec.get("text")


def ours_is_a(i: int, rival: str, judge: str) -> bool:
    return int(hashlib.sha256(f"{i}|{rival}|{judge}".encode()).hexdigest(), 16) % 2 == 0


VARIANT_RIVALS = ["none", "plain-claude", "ours"]      # 변형은 이 셋하고만 견줌(호출 수를 줄임)


def judged_dir(base: str) -> Path:
    return OUT / ("judged" if base == "ours" else f"judged-{base}")


def rivals_of(base: str) -> list[str]:
    return RIVALS if base == "ours" else [r for r in VARIANT_RIVALS if r != base]


def judge(names: list[str], base: str = "ours") -> None:
    ds = load_drafts()
    for jn in names:
        vendor, model = JUDGES[jn]
        for rival in rivals_of(base):
            for i in range(len(ds)):
                f = judged_dir(base) / f"{jn}/{rival}/{i:02d}.json"
                if f.exists() and not json.loads(f.read_text(encoding="utf-8")).get("error"):
                    continue
                ours, other = revised(base, i, ds), revised(rival, i, ds)
                if ours is None or other is None:
                    continue
                a_is_ours = ours_is_a(i, rival, jn)
                a, b = (ours, other) if a_is_ours else (other, ours)
                user = f"## 원문\n\n{ds[i]['text']}\n\n## 수정본 A\n\n{a}\n\n## 수정본 B\n\n{b}"
                rec = {"a_is_ours": a_is_ours}
                try:
                    t = time.time()
                    r = systems.call_model(vendor, model, JUDGE_SYSTEM, user)
                    log_cost(rec, r, time.time() - t, JUDGE_SYSTEM, user)
                    m = re.search(r"\{.*\}", r["text"], re.S)
                    rec["verdict"] = json.loads(m.group(0)) if m else None
                    if not rec["verdict"]:
                        rec["error"] = "JSON 없음"
                except Exception as e:
                    rec["error"] = f"{type(e).__name__}: {e}"[:300]
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                print(jn, rival, i, (rec.get("verdict") or {}).get("winner"), rec.get("error", "")[:60], flush=True)


def score(bases: tuple[str, ...] = ("ours",)) -> dict:
    ds = load_drafts()
    table: dict = {"판정": {}, "고쳐 쓰기 비용": {}}
    for base in bases:
        score_base(base, ds, table)
    for name in ["ours", "ours-noinvent", "l1only", "ours2", "ours2-apply", "plain-claude-ours2",
                 "plain-claude-apply", "ours3-apply", "plain-claude-apply3"] + RIVALS[1:]:
        c = collections.Counter()
        for i, d in enumerate(ds):
            f = OUT / f"revised/{name}/{i:02d}.json"
            if not f.exists():
                continue
            rec = json.loads(f.read_text(encoding="utf-8"))
            for k in ("seconds", "cost_usd", "in_tok", "out_tok", "in_chars", "out_chars", "calls"):
                c[k] += rec.get(k) or 0
            c["kchars"] += hangul(d["text"]) / 1000
            c["docs"] += 1
            c["errors"] += bool(rec.get("error"))
        if c["docs"]:
            table["고쳐 쓰기 비용"][name] = {k: round(v, 4) for k, v in c.items()}
    return table


def score_base(base: str, ds: list[dict], table: dict) -> None:
    for jn in JUDGES:
        for rival in rivals_of(base):
            win, tie, lose = {}, 0, 0
            mean_o, mean_r, def_o, def_r, n = 0, 0, 0, 0, 0
            for i in range(len(ds)):
                f = judged_dir(base) / f"{jn}/{rival}/{i:02d}.json"
                if not f.exists():
                    continue
                rec = json.loads(f.read_text(encoding="utf-8"))
                v = rec.get("verdict")
                if not v:
                    continue
                o, r = ("A", "B") if rec["a_is_ours"] else ("B", "A")
                w = v.get("winner")
                win[str(i)] = (1.0 if w == o else 0.5 if w == "tie" else 0.0, 1)
                tie += w == "tie"
                lose += w == r
                mean_o += int(v.get(f"meaning_changes_{o}") or 0)
                mean_r += int(v.get(f"meaning_changes_{r}") or 0)
                def_o += int(v.get(f"defects_{o}") or 0)
                def_r += int(v.get(f"defects_{r}") or 0)
                n += 1
            if n:
                table["판정"][f"{jn} · {base} 대 {rival}"] = {
                    "ours 승률(비김 0.5)": boot(win), "비김": tie, "짐": lose, "편": n,
                    "뜻 바뀜 합(ours/상대)": [mean_o, mean_r], "남은 결함 합(ours/상대)": [def_o, def_r],
                    "_per_doc": win}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("drafts")
    r = sub.add_parser("revise")
    r.add_argument("names", nargs="+")
    j = sub.add_parser("judge")
    j.add_argument("names", nargs="+")
    j.add_argument("--base", default="ours")
    s = sub.add_parser("score")
    s.add_argument("--json")
    s.add_argument("--bases", default="ours,ours-noinvent,l1only")
    a = ap.parse_args()
    if a.cmd == "drafts":
        drafts()
    elif a.cmd == "revise":
        revise(a.names)
    elif a.cmd == "judge":
        judge(a.names, a.base)
    else:
        t = score(tuple(a.bases.split(",")))
        for k, v in t["판정"].items():
            w = v["ours 승률(비김 0.5)"]
            print(f"{k:28s} 승률 {w[0]:.2f} [{w[1]:.2f}~{w[2]:.2f}] 비김 {v['비김']} 짐 {v['짐']} / {v['편']}  "
                  f"뜻 바뀜 {v['뜻 바뀜 합(ours/상대)']}  결함 {v['남은 결함 합(ours/상대)']}")
        if a.json:
            Path(a.json).write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
