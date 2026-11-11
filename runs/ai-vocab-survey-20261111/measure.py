"""AI 한국어가 사람 업무 글보다 많이 쓰는 명사와 동사 — 형태소 원형 단위로 1만 자당 빈도를 견준다.

사용자(2026-11-11) 「판, 자리 같은 업무에서 잘 쓰지 않는 명사와, 풀다. 잇다. 같은 역시 업무 또는 일상에서 잘
사용하지 않는 동사도 많이 쓰는데 이런 정보는 없니? 조사해봐.」

말뭉치(저장소에는 집계만 남긴다 · 본문은 읽기만 함)
- claude — 이 PC 의 Claude Code 세션 기록에서 assistant 가 쓴 글(지시 파일과 대화가 실린 조건)
- user   — 같은 세션 기록에서 사용자가 쓴 글(도구 결과와 시스템 주입 제외)
- instr  — 지시 파일(전역 CLAUDE.md, 전역 references, 스킬, 이 저장소 지시와 판단 규칙)
- clean  — 문체 지시 없이 만든 AI 문서(인자로 받은 폴더의 *.md)
- 기준선 — data/catalog/work-korean-freq.json(사람 업무 글 4,793만 자, 41회 이상 낱말만 · 한 글자 명사와 부사는 없음)

    python -X utf8 runs/ai-vocab-survey-20261111/measure.py <clean 폴더> <세션 기록 폴더> [--max-chars N]
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import sys
from pathlib import Path

from kiwipiepy import Kiwi

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TAGS = ("NNG", "VV", "VA", "MAG")
FLOOR = 40          # 기준선이 싣지 않는 빈도(이하) — scripts/rare_words.py 와 같음
HANGUL = re.compile(r"[가-힣]")
#: 사용자가 물은 낱말과 대장(flagged-rounds)에 오른 같은 갈래 — 순위와 상관없이 표에 싣는다
WATCH = ["판/NNG", "자리/NNG", "결/NNG", "창/NNG", "층/NNG", "축/NNG", "갈래/NNG", "값/NNG", "곳/NNG",
         "풀/VV", "잇/VV", "짚/VV", "가르/VV", "갈리/VV", "훑/VV", "얹/VV", "닿/VV", "걸리/VV", "돌/VV", "붙/VV",
         "남/VV", "재/VV", "심/VV", "싣/VV", "걷/VV", "굳/VV", "깎/VV", "떼/VV", "거르/VV", "새/VV", "뜨/VV", "세우/VV",
         "짜/VV", "짜이/VV"]


def clean_text(t: str) -> str:
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    return re.sub(r"`[^`\n]*`", " ", t)


def korean_enough(t: str) -> bool:
    return len(t) >= 40 and len(HANGUL.findall(t)) * 2 >= len(re.sub(r"\s", "", t))


def session_texts(root: Path, max_chars: int, role: str):
    """세션 기록에서 한 쪽(assistant · user)이 쓴 글 — 최근 파일부터, 한글이 절반 넘는 블록만.
    코드 펜스와 인라인 코드는 빼고, user 쪽은 도구 결과와 시스템 주입(「<」로 시작)을 뺌."""
    files = sorted(glob.glob(str(root / "*" / "*.jsonl")), key=os.path.getmtime, reverse=True)
    total = 0
    for f in files:
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in fh:      # 한 번에 읽으면 큰 세션 기록에서 MemoryError(첫 실행)
            if len(raw) > 2_000_000:     # 그림이나 큰 도구 결과가 든 줄 — 글 블록이 아님
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            if rec.get("type") != role or rec.get("isMeta"):
                continue
            content = (rec.get("message") or {}).get("content")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                t = block.get("text") or ""
                # 사용자 쪽에 실리는 스킬 본문, 압축 요약, 예약 실행 지시는 사용자가 쓴 글이 아님
                if role == "user" and (t.lstrip().startswith("<") or any(k in t for k in (
                        "This session is being continued", "Base directory for this skill", "ARGUMENTS:",
                        "<<autonomous-loop"))):
                    continue
                # 사용자 쪽 긴 블록은 붙여 넣은 Claude 글, 다른 세션이 보낸 글이 대부분 — 손으로 친 짧은 말만(800자 이하)
                if role == "user" and len(t) > 800:
                    continue
                t = clean_text(t)
                if not korean_enough(t):
                    continue
                yield t
                total += len(t)
                if total >= max_chars:
                    return


def instruction_texts():
    home = Path.home() / ".claude"
    paths = [home / "CLAUDE.md", REPO / "AGENTS.md"] + sorted((home / "references").glob("*.md")) + \
        sorted((home / "skills").glob("*/SKILL.md")) + sorted((REPO / "skills").glob("*/references/*.md"))
    for p in paths:
        if p.is_file():
            yield clean_text(p.read_text(encoding="utf-8", errors="replace"))


def count(texts, kiwi: Kiwi) -> tuple[collections.Counter, int]:
    c, chars = collections.Counter(), 0
    for t in texts:
        chars += len(t)
        for tok in kiwi.tokenize(t):
            tag = tok.tag.split("-")[0]     # 불규칙 활용(VV-I · VV-R)도 같은 낱말 — 첫 실행에서 「잇다」가 0으로 셈
            if tag in TAGS:
                c[f"{tok.form}/{tag}"] += 1
    return c, chars


def comparable(word: str) -> bool:
    """기준선과 견줄 수 있는 낱말 — 한 글자 명사와 부사는 기준선에 없어 견주지 않는다."""
    form, tag = word.split("/")
    return not (len(form) < 2 and tag in ("NNG", "MAG"))


def main() -> int:
    clean_dir, sess_dir = Path(sys.argv[1]), Path(sys.argv[2])
    max_chars = int(sys.argv[sys.argv.index("--max-chars") + 1]) if "--max-chars" in sys.argv else 2_000_000
    data = json.loads((REPO / "data/catalog/work-korean-freq.json").read_text(encoding="utf-8"))
    base, base_chars = data["freq"], data["chars"]
    kiwi = Kiwi()
    corp = {
        "claude": count(session_texts(sess_dir, max_chars, "assistant"), kiwi),
        "user": count(session_texts(sess_dir, max_chars, "user"), kiwi),
        "instr": count(instruction_texts(), kiwi),
        "clean": count((p.read_text(encoding="utf-8") for p in sorted(clean_dir.glob("*.md"))), kiwi),
    }

    def rate(name: str, w: str) -> float:
        c, chars = corp[name]
        return round(c[w] / chars * 1e4, 2)

    def row(w: str) -> dict:
        b = base.get(w)
        h = (b if b else FLOOR) / base_chars * 1e4
        r = {"word": w, "human_per10k": round(h, 4), "human_absent": b is None, "comparable": comparable(w)}
        for name in corp:
            r[name] = rate(name, w)
            r[f"{name}_n"] = corp[name][0][w]
        r["claude_vs_human"] = round(r["claude"] / h, 1)
        return r

    c_claude = corp["claude"][0]
    top = [row(w) for w, n in c_claude.items() if n >= 30 and comparable(w)]
    top = [r for r in top if r["claude_vs_human"] >= 10]
    top.sort(key=lambda r: -r["claude_vs_human"])
    out = {"chars": {k: v[1] for k, v in corp.items()} | {"human": base_chars},
           "watch": [row(w) for w in WATCH], "top": top}
    # 순위표에 세션 기록의 명사(사내 과제와 도구 이름이 섞임)가 들어가므로 저장소 밖 작업 폴더에 둔다
    (clean_dir.parent / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print("글자 수", out["chars"])
    print("단어 · 사람 · Claude · 사용자 · 지시 · 지시없는AI (1만 자당)")
    for r in out["watch"]:
        mark = "" if r["comparable"] else " (사람 기준선 없음)"
        print(f"  {r['word']:10} {('≤' if r['human_absent'] else '')}{r['human_per10k']:<8} {r['claude']:<6} {r['user']:<6} "
              f"{r['instr']:<6} {r['clean']:<5}{mark}")
    for tag in TAGS:
        part = [r for r in top if r["word"].endswith("/" + tag)][:30]
        print(f"[{tag}] " + ", ".join(f"{r['word'].split('/')[0]} {r['claude_vs_human']}배(사{r['user']}·지{r['instr']})"
                                      for r in part))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
