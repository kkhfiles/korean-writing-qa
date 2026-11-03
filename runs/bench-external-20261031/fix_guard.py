#!/usr/bin/env python
"""판정기 수정안을 사람 확인 없이 넣어도 되는지 기계로 가린다 — 막을 까닭 목록과 조사 맞춤.

**왜 있나** (2026-11-03) — Claude 단순 요청으로 다듬은 글 12편에 판정기 수정안을 「바로 반영」으로 넣었더니
두 판정자 모두 단순 요청보다 나빠졌다고 판정했다(`runs/bench-external-20261031/README.md` 「D3」). 진 까닭은
수정안이 원문에 없는 말을 넣거나(「보완 검증」 → 「원인을 보완한 뒤 다시 검증」), 내용을 지우거나(「개선이
필요하다」 삭제), 제목을 바꾸거나, 서식을 지우거나(굵게), 낱말을 바꿔 넣다 조사가 틀어진 것(「수단와」)이었다.
숫자와 따옴표 안 이름만 보는 `layer2_coverage.new_info` 로는 이것들이 빠져나간다.

**쓰는 곳** — `bench_e2e.py` 의 `revise_apply_guarded` 만. `fit_particle` 은 글자 그대로 넣을 때 뒤 조사를
받침에 맞춘다.

**제품에 안 넣은 까닭** (2026-11-03) — 가리개를 더해도 단순 요청보다 나아지지 않았다(README 「D3 재측정」).
검토 화면은 원래 수정안을 자동으로 넣지 않아 가리개가 막을 경로가 제품에 없다.

⛔ 판정하지 않는다 — 수정안이 틀렸다는 뜻이 아니라 사람이 보고 넣어야 한다는 뜻이다.
⛔ 형태소 분석기가 없으면 내용어 비교(새 명사, 빠진 내용어)는 못 하고 서식과 제목만 본다.
"""

from __future__ import annotations

import re

#: 내용어 — 명사, 동사, 형용사, 어근, 수
CONTENT_TAGS = ("NNG", "NNP", "VV", "VA", "XR", "SN", "SL")
#: 「원문에 없는 말」은 명사와 수만 본다 — 동사(「나오다」, 「바뀌다」)는 대개 같은 뜻을 풀어 쓴 것이다
NEW_TAGS = ("NNG", "NNP", "SN", "SL")
#: 서식과 인용 기호 — 수정안에서 개수가 달라지면 서식이 바뀐 것
MARKS = ("**", "`", "‘", "’", "“", "”", "「", "」", "[", "]")
#: 조사 짝 — (받침 있을 때, 없을 때)
PARTICLES = (("과", "와"), ("이", "가"), ("은", "는"), ("을", "를"), ("으로", "로"), ("이나", "나"), ("이랑", "랑"))

_KIWI = None
_TRIED = False


def _morph():
    global _KIWI, _TRIED
    if not _TRIED:
        _TRIED = True
        try:
            import kiwipiepy
            _KIWI = getattr(kiwipiepy, "_korean_qa_shared", None) or kiwipiepy.Kiwi()
            kiwipiepy._korean_qa_shared = _KIWI
        except Exception:
            _KIWI = None
    return _KIWI


def _content(text: str, tags=CONTENT_TAGS) -> set[str]:
    k = _morph()
    if k is None or not text.strip():
        return set()
    return {t.form for t in k.tokenize(text) if t.tag in tags and (len(t.form) > 1 or t.tag == "SN")}


def _jong(ch: str) -> int:
    o = ord(ch) - 0xAC00
    return o % 28 if 0 <= o < 11172 else -1


def reasons(phrase: str, fix: str, line: str, doc: str) -> list[str]:
    """수정안을 바로 넣으면 안 되는 까닭 — 비면 넣어도 됨."""
    out = []
    if not fix or not phrase:
        return out
    if any(phrase.count(m) != fix.count(m) for m in MARKS):
        out.append("서식이나 인용 기호가 바뀜")
    stripped = line.strip()
    if stripped.startswith("#") or (phrase in line and re.search(r"\*\*[^*]*" + re.escape(phrase) + r"[^*]*\*\*", line)):
        if _content(phrase) != _content(fix) or _morph() is None:
            out.append("제목이나 굵은 머리의 말을 바꿈")
    before, after = _content(phrase), _content(fix)
    if before or after:
        added, dropped = after - before, before - after
        new = sorted(w for w in _content(fix, NEW_TAGS) - _content(phrase, NEW_TAGS) if w not in doc)
        if new:
            out.append(f"원문에 없는 말을 넣음: {', '.join(new)}")
        if len(dropped) >= 2 and len(dropped) > len(added):
            out.append(f"내용어가 빠짐: {', '.join(sorted(dropped))}")
    return out


def fit_particle(line: str, phrase: str, fix: str) -> str:
    """`phrase` 를 `fix` 로 한 번 바꾸고, 바로 뒤 조사를 `fix` 끝 글자 받침에 맞춘다(「수단와」 → 「수단과」)."""
    i = line.find(phrase)
    if i < 0:
        return line
    rest = line[i + len(phrase):]
    j = _jong(fix[-1]) if fix else -1
    if j >= 0:
        for with_b, without in PARTICLES:
            for cur, want in ((without, with_b), (with_b, without)):
                if re.match(re.escape(cur) + r"(?![가-힣])", rest):
                    has = j != 0 and not (with_b == "으로" and j == 8)   # ㄹ 받침 뒤는 「로」
                    right = with_b if has else without
                    if cur != right:
                        rest = right + rest[len(cur):]
                    break
            else:
                continue
            break
    return line[:i] + fix + rest
