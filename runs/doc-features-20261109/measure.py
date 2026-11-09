"""연구에서 쓴 문서 단위 지표가 사람 업무 문서와 AI 업무 문서를 가르나 — 사전 기록은 plan.md.

모델 호출 없음. 문서 본문은 남기지 않고 지표 요약만 result.json 에 적는다.

python -X utf8 runs/doc-features-20261109/measure.py
"""
import importlib.util
import json
import random
import re
import statistics as st
from pathlib import Path

from kiwipiepy import Kiwi

HERE = Path(__file__).parent
REPO = HERE.parents[1]
HANGUL = re.compile(r"[가-힣]")
FORMAL = ("따라서", "또한", "즉", "그러므로", "게다가", "아울러", "나아가", "더불어", "결과적으로",
          "이처럼", "이에 따라", "한편", "반면", "무엇보다")
PLAIN = ("그리고", "그래서", "그런데", "하지만", "그러나", "근데")
SENT = re.compile(r"(?<=[.!?。])\s+|\n+")
LEAD = re.compile(r"^[\s>*#\-\d.)]*")


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def starts(sent, words):
    return any(sent.startswith(w) and (len(sent) == len(w) or not HANGUL.match(sent[len(w)])) for w in words)


def features(text, kiwi):
    h = len(HANGUL.findall(text))
    sents = [LEAD.sub("", s).strip() for s in SENT.split(text)]
    sents = [s for s in sents if len(HANGUL.findall(s)) >= 5]
    f = sum(starts(s, FORMAL) for s in sents)
    p = sum(starts(s, PLAIN) for s in sents)
    row = {
        "formal_per_1k": f / h * 1000,
        "formal_ratio": f / (f + p) if f + p else None,
        "comma_sent": sum("," in s for s in sents) / len(sents) if sents else None,
    }
    lens = [len(s) for s in sents]
    row["sent_len_cv"] = st.pstdev(lens) / st.mean(lens) if len(lens) >= 5 else None
    vx, nnb, nnb_sp = [], 0, 0
    for tok in kiwi.tokenize(text):
        if tok.tag == "VX":
            vx.append(tok.form)
        elif tok.tag == "NNB":
            nnb += 1
            nnb_sp += tok.start > 0 and text[tok.start - 1] == " "
    row["vx_diversity"] = len(set(vx)) / len(vx) if len(vx) >= 5 else None
    row["nnb_space"] = nnb_sp / nnb if nnb >= 5 else None
    return row


def auc(pos, neg):
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def main():
    src = load("src", REPO / "runs/compare-imnotai-20261023/measure.py")
    kiwi = Kiwi()
    corp = {k: [t for t in fn() if len(HANGUL.findall(t)) >= 300] for k, fn in (("human", src.human), ("ai", src.ai))}
    rows = {k: [features(t, kiwi) for t in docs] for k, docs in corp.items()}
    keys = list(rows["human"][0])
    random.seed(20261109)
    out = {}
    for k in keys:
        H = [r[k] for r in rows["human"] if r[k] is not None]
        A = [r[k] for r in rows["ai"] if r[k] is not None]
        a = auc(A, H)
        halves = []
        for _ in range(1):
            hi = H[:]; ai = A[:]
            random.shuffle(hi); random.shuffle(ai)
            halves = [auc(ai[: len(ai) // 2], hi[: len(hi) // 2]), auc(ai[len(ai) // 2:], hi[len(hi) // 2:])]
        cand = (a >= 0.70 or a <= 0.30) and all((x > 0.5) == (a > 0.5) for x in halves)
        out[k] = {"사람 문서": len(H), "AI 문서": len(A), "사람 중앙값": round(st.median(H), 4),
                  "AI 중앙값": round(st.median(A), 4), "AUC": round(a, 3),
                  "반씩 나눈 AUC": [round(x, 3) for x in halves], "후보": cand}
    result = {"이름": "연구 지표로 업무 문서의 AI 글 가르기", "사전 기록": "plan.md",
              "문서": {k: len(v) for k, v in corp.items()}, "지표": out}
    (HERE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
