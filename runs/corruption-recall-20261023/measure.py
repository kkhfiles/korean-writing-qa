"""오염 시료로 1층 회수율 재기 — 사람 업무 문서 문단에 AI 꼴을 거꾸로 주입하고 검사기가 잡는지 센다.

im-not-ai corruption_engine 의 방식을 합쇼체 업무 문서에 맞게 다시 짰다. 로컬 전용 — 문서 원문은 출력하지 않고
갈래별 건수와 주입 문형만 낸다. 원문에 이미 있던 지적과 섞이지 않게, 주입 전 문단에서 그 갈래가 이미 나면 뺀다.
"""
import collections
import importlib.util
import random
import re
import sys

base = __file__.replace("corrupt_recall.py", "")
sys.argv = ["probe.py", "0", "ZZZ"]
s = importlib.util.spec_from_file_location("p", base + "probe.py"); p = importlib.util.module_from_spec(s); s.loader.exec_module(p)
s = importlib.util.spec_from_file_location("c", "P:/github/korean-writing-qa/assets/doc-style-check.py")
c = importlib.util.module_from_spec(s); s.loader.exec_module(c)
SENT_END = re.compile(r"(습니다|합니다|입니다|됩니다)\.")


def sents(t):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", t) if x.strip()]


# (이름, 기대하는 검사기 갈래, 주입 함수) — 주입 함수는 문단 → 바뀐 문단 또는 None
def inj_stock(phrase_fn):
    def f(t, rng):
        ss = sents(t)
        idx = [i for i, x in enumerate(ss) if SENT_END.search(x)]
        if not idx:
            return None
        i = rng.choice(idx)
        ss[i] = phrase_fn(ss[i], rng)
        return " ".join(ss) if ss[i] else None
    return f


def lead(words):
    return inj_stock(lambda x, rng: rng.choice(words) + x)


def tail_replace(x, rng, forms):
    m = SENT_END.search(x)
    return x[:m.start()] + rng.choice(forms) if m else ""


def inj_repeat(build):
    """한 문단을 세 문장으로 만들어 같은 꼴을 몰아 넣음."""
    def f(t, rng):
        ss = [x for x in sents(t) if SENT_END.search(x)]
        if len(ss) < 4:
            return None
        return " ".join(build(x, i, rng) for i, x in enumerate(ss[:4]))
    return f


INJ = [
    ("범위 상승", "상투 문형", lead(["단순한 비용 절감을 넘어 ", "단순한 기능 추가를 넘어 "])),
    ("평가 술어", "상투 문형", inj_stock(lambda x, r: x + " 이 방향이 옳다는 것은 명확합니다.")),
    ("기반 마련 은유", "상투 문형", inj_stock(lambda x, r: x + " 이 작업은 자동화의 발판을 마련합니다.")),
    ("완결 공식", "상투 문형", inj_stock(lambda x, r: x + " 이제 다음 단계로 나아가야 할 때입니다.")),
    ("분열문", "상투 문형", inj_stock(lambda x, r: x + " 지금 필요한 것은 일정 관리입니다.")),
    ("역방향 결산", "상투 문형", inj_stock(lambda x, r: x + " 담당자가 일정을 다시 잡은 이유입니다.")),
    ("반론 문패", "상투 문형", inj_stock(lambda x, r: x + " 그러나 과제도 남아 있습니다.")),
    ("무주체 판정", "상투 문형", inj_stock(lambda x, r: x + " 수요가 계속 늘 것이라는 분석입니다.")),
    ("에 있어서", "상투 문형", lead(["이 과제에 있어서 ", "운영에 있어서 "])),
    ("관련하여", "상투 문형", lead(["보안과 관련하여 ", "일정과 관련하여 "])),
    ("지어낸 은유", "상투 문형", inj_stock(lambda x, r: x + " 저가 제품이 시장을 잠식하고 있습니다.")),
    ("메타담화 서두", "상투 문형", lead(["이 문서에서는 변경 내용을 알아보겠습니다. "])),
    ("가 아니라 대구", "「~가 아니라」 반복",
     inj_stock(lambda x, r: x + " 목표는 속도가 아니라 정확도입니다. 바꿀 것은 도구가 아니라 순서입니다.")),
    ("에 대해 밀집", "반복 문형", inj_repeat(lambda x, i, r: f"항목 {i + 1}에 대해 " + x)),
    ("를 통해 밀집", "반복 문형", inj_repeat(lambda x, i, r: f"점검 {i + 1}을 통해 " + x)),
    ("할 수 있다 연속", "반복 문형",
     inj_repeat(lambda x, i, r: tail_replace(x, r, ["확인할 수 있습니다.", "처리할 수 있습니다."]) or x)),
    ("문두 접속사 밀집", "반복 문형", inj_repeat(lambda x, i, r: ["", "또한 ", "아울러 ", "나아가 "][i] + x)),
    ("되고 있다 밀집", "반복 문형",
     inj_repeat(lambda x, i, r: tail_replace(x, r, ["확대되고 있습니다.", "강화되고 있습니다."]) or x)),
]

random.seed(11)
docs = [d for d in p.human() if len(p.HANGUL.findall(d)) >= 300]
paras = [x.strip() for d in docs for x in re.split(r"\n\s*\n", d)
         if len(re.findall(r"[가-힣]", x)) >= 80 and len(SENT_END.findall(x)) >= 3 and "|" not in x]
print("후보 문단", len(paras))


def kinds_of(text):
    paras_ = [(i, c.mask(x)) for i, x in enumerate(re.split(r"\n\s*\n", text)) if x.strip()]
    got = {n for n, f, h in c.stock_hits(c.mask(text))}
    found = set()
    if got:
        found.add("상투 문형")
    if c.repeat_hits(paras_):
        found.add("반복 문형")
    if c.not_but_pileup([c.mask(text)])[0]:
        found.add("「~가 아니라」 반복")
    return found


res = collections.Counter()
for name, kind, fn in INJ:
    tried = hit = 0
    for para in random.sample(paras, min(120, len(paras))):
        if kind in kinds_of(para):
            continue      # 원문이 이미 그 갈래를 냄 — 주입 효과와 섞이지 않게 뺀다
        rng = random.Random(hash((name, para)) & 0xffff)
        new = fn(para, rng)
        if not new or new == para:
            continue
        tried += 1
        hit += kind in kinds_of(new)
        if tried >= 60:
            break
    print(f"{name:<14} {kind:<14} 주입 {tried:>3} · 잡음 {hit:>3} · 회수율 {hit / max(1, tried):.0%}")
