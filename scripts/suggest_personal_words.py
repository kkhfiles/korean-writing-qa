#!/usr/bin/env python
"""개인 낱말 목록에 넣을 후보 — 구어 글에 치우친 동사를 용례와 함께 보여 준다(판정은 안 함).

    python -X utf8 scripts/suggest_personal_words.py --informal <구어 글 폴더> --formal <문어 글 폴더>
                                                    [--top 60] [--min-docs 5]

**무엇을 하나** — 두 폴더의 글(.md·.txt·.html)을 형태소로 나눠, 동사 원형마다 그 동사가 나온
문서 비율을 구어·문어로 따로 센다. 구어 쪽 비율이 높은 동사를 위에서부터 용례와 함께 낸다.
사람이 골라 `data/catalog/local-personal-words.tsv`(저장소 밖 목록)에 옮긴다.

**왜 자동 경고가 아니라 후보인가** (2026-09-29 실험 1) — 사내 글로 재 보니 구어 치우침 상위에
「잡히다」·「죽다」·「날리다」·「돌리다」처럼 기술 행위의 입말이 오르지만, 「드리다」·「여쭈다」·
「헷갈리다」 같은 대화 말투도 같이 오른다. 일감 댓글과 설명서는 주제·목적이 달라 문체보다
업무 차이를 잡기도 한다. 그대로 경고하면 소음이 크고(상위 200 · 시험 문단 경고 31건 중 참 3),
사람이 고르면 그 소음이 걸러진다.

**(동사 × 명사) 결합을 안 쓰는 까닭** — 같은 실험에서 결합 목록은 대화 말투(「파일을 드리다」)만
잡았고, 정답 동사 대부분은 목적어가 드러나지 않아 후보에도 못 올랐다(7곳 중 1곳). 명사를 쓰지
않으니 동료 이름·고객사가 목록에 섞일 걱정도 없다.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

VERB = ("VV", "VV-R", "VV-I")


def texts(folder: str):
    for p in sorted(Path(folder).rglob("*")):
        if p.suffix.lower() in (".md", ".txt", ".html", ".htm") and p.is_file():
            t = p.read_text(encoding="utf-8", errors="replace")
            if p.suffix.lower().startswith(".htm"):
                t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S | re.I)
                t = re.sub(r"<[^>]+>", " ", t)
            yield t


def count(kiwi, folder: str):
    df, examples, n = Counter(), {}, 0
    for text in texts(folder):
        n += 1
        seen = set()
        for sent in kiwi.split_into_sents(text[:200000], return_tokens=True):
            forms = {t.form for t in sent.tokens if t.tag in VERB}
            seen |= forms
            s = " ".join(sent.text.split())
            if 15 <= len(s) <= 100:
                for f in forms:
                    examples.setdefault(f, [])
                    if len(examples[f]) < 2:
                        examples[f].append(s)
        df.update(seen)
    return df, examples, n


def main() -> int:
    ap = argparse.ArgumentParser(description="개인 낱말 목록 후보 — 구어 글에 치우친 동사")
    ap.add_argument("--informal", required=True, help="구어 글 폴더(메신저 · 일감 댓글 · 메모)")
    ap.add_argument("--formal", required=True, help="문어 글 폴더(설명서 · 보고서 · 공식 문서)")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--min-docs", type=int, default=5, help="구어 쪽에서 이만큼 이상 문서에 나온 동사만")
    args = ap.parse_args()
    try:
        from kiwipiepy import Kiwi
    except Exception:
        print("형태소 분석기가 없습니다 — python -m pip install kiwipiepy", file=sys.stderr)
        return 1
    # 검사기와 같은 한 벌을 쓴다(rare_words.py 와 같은 까닭)
    import kiwipiepy
    kiwi = getattr(kiwipiepy, "_korean_qa_shared", None) or Kiwi()
    kiwipiepy._korean_qa_shared = kiwi
    d1, ex1, n1 = count(kiwi, args.informal)
    d2, ex2, n2 = count(kiwi, args.formal)
    if not n1 or not n2:
        print(f"글이 없습니다 — 구어 {n1}건 · 문어 {n2}건", file=sys.stderr)
        return 1
    rate = lambda a, n: (a + 0.5) / (n + 1)
    ranked = sorted(((rate(c, n1) / rate(d2.get(v, 0), n2), v) for v, c in d1.items() if c >= args.min_docs),
                    reverse=True)
    print(f"구어 {n1}건 · 문어 {n2}건 — 구어 치우침 상위 {min(args.top, len(ranked))}개(판정 아님 · 사람이 고름)\n")
    for r, v in ranked[:args.top]:
        print(f"{v}다\t{r:.1f}배 · 구어 {d1[v]}건 · 문어 {d2.get(v, 0)}건")
        for e in ex1.get(v, [])[:1]:
            print(f"    구어 용례: {e}")
        for e in ex2.get(v, [])[:1]:
            print(f"    문어 용례: {e}")
    print("\n고른 동사는 data/catalog/local-personal-words.tsv 에 「동사<탭>명사<탭>바꿀 말<탭>까닭」으로 적습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
