"""홈페이지 소개 문구에서 「쉬운 우리말」 요청이 드문 고유어 동사를 늘리는지 — 모델 셋 × 제품 셋 × 요청 둘.

사용자(2026-11-11)가 짚은 「짜이고」, 「머물러요」, 「꾸리는」은 이 PC 밖의 홈페이지(다른 AI 가 쓴 글)에서 나옴.
지시 없이 쓴 업무 문서(gen.py)에는 이런 말이 거의 없어, 장르(소개 문구)와 「쉬운 말」 요청을 갈라 본다.
2026-09-15 에 전역 규칙 「어려운 말로 쓰지 않음 — 한자말 대신」이 같은 갈래의 말을 낳아 지운 일이 있다.

    python -X utf8 runs/ai-vocab-survey-20261111/landing.py <작업 폴더> gen <claude|gpt|gemini>
    python -X utf8 runs/ai-vocab-survey-20261111/landing.py <작업 폴더> count
"""
from __future__ import annotations

import collections
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PRODUCTS = {
    "agents": "집과 사무실의 여러 PC 에서 역할별 AI 에이전트를 나눠 실행하는 업무 자동화 도구",
    "checker": "AI 가 쓴 한국어 업무 문서의 어색한 표현을 찾아 고치는 검사 도구",
    "backup": "회사 문서를 사내 서버에만 보관하고 자동으로 백업하는 서비스",
}
ASK = {
    "plain": "다음 제품의 홈페이지 첫 화면 소개 문구를 한국어로 써 주세요. 제목 한 줄, 소개 두세 문장, 특징 세 가지. 문구만 출력하세요.\n\n제품: ",
    "easy": "다음 제품의 홈페이지 첫 화면 소개 문구를 한국어로 써 주세요. 어려운 한자어와 전문 용어 대신 쉬운 우리말로, 친근한 해요체로 써 주세요. 제목 한 줄, 소개 두세 문장, 특징 세 가지. 문구만 출력하세요.\n\n제품: ",
}


def gen(work: Path, writer: str) -> None:
    s = importlib.util.spec_from_file_location("run", HERE.parent / "value-ai-docs-20261109" / "run.py")
    run = importlib.util.module_from_spec(s)
    s.loader.exec_module(run)
    out = work / "landing"
    out.mkdir(parents=True, exist_ok=True)
    for cond, ask in ASK.items():
        for name, product in PRODUCTS.items():
            f = out / f"{cond}-{writer}-{name}.md"
            if f.exists():
                continue
            text, info = run.write_doc(writer, ask + product)
            if not text.strip():
                print(f"{f.stem} 빈 답 {json.dumps(info, ensure_ascii=False)}", flush=True)
                continue
            f.write_text(run.imn.unfence(text).strip() + "\n", encoding="utf-8")
            print(f.stem, json.dumps(info, ensure_ascii=False), flush=True)


def count(work: Path) -> None:
    """요청별로 기준선 40회 이하(또는 없음)인 용언과 일반 명사 — 1만 자당과 낱말 목록."""
    from kiwipiepy import Kiwi
    kiwi = Kiwi()
    freq = json.loads((REPO / "data/catalog/work-korean-freq.json").read_text(encoding="utf-8"))["freq"]
    for cond in ASK:
        chars, rare = 0, collections.Counter()
        files = sorted((work / "landing").glob(f"{cond}-*.md"))
        for f in files:
            t = f.read_text(encoding="utf-8")
            chars += len(t)
            for tok in kiwi.tokenize(t):
                tag = tok.tag.split("-")[0]
                if tag in ("VV", "VA") or (tag == "NNG" and len(tok.form) >= 2):
                    if f"{tok.form}/{tag}" not in freq:
                        rare[f"{tok.form}/{tag}"] += 1
        verbs = sum(n for k, n in rare.items() if not k.endswith("NNG"))
        print(f"== {cond} · {len(files)}편 · {chars:,}자 · 드문 용언 {verbs}개(1만 자당 {verbs / chars * 1e4:.1f})")
        print("   용언 " + ", ".join(f"{k.split('/')[0]}({n})" for k, n in rare.most_common() if not k.endswith("NNG")))
        print("   명사 " + ", ".join(f"{k.split('/')[0]}({n})" for k, n in rare.most_common(30) if k.endswith("NNG")))


if __name__ == "__main__":
    w = Path(sys.argv[1])
    gen(w, sys.argv[3]) if sys.argv[2] == "gen" else count(w)
