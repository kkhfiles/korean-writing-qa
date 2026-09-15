"""사람이 안 쓰는 낱말을 문서에서 찾아 사람에게 보여 준다.

    python -X utf8 scripts/rare_words.py <파일…> [--max 40] [--top 25]

**왜 만들었나.** 낱말 규칙은 이번에 걸린 말만 안다 — 「걷다」를 막았더니 다음에
「갈래·스스로·채점」이 나왔고, 그것도 사람이 눈으로 찾았다(2026-09-09 두 번).
같은 일이 되풀이되지 않으려면 **안 본 말도 걸리는 장치**가 있어야 한다.

**어떻게 가르나.** 어원이 아니라 **빈도**다. 드물게 쓰는 고유어는 흔한 한자어보다
어렵다 — 읽는 사람은 어원을 모르고 빈도만 안다. 기준선은 사람이 쓴 업무 한국어
4,790만 자(메일·사내 규정·지라·노션)이고, 거기서 몇 번 나오는지로 줄을 세운다.

⚠️ **판정하지 않는다 — 목록만 낸다.** 드문 것이 곧 틀린 것은 아니다(제품 이름·
전문 용어·숫자 단위가 드문 것은 정상이다). 이 도구가 하는 일은 **사람이 볼 곳을
좁히는 것**이고, 고칠지는 사람이 정한다. 그래서 검사기 규칙이 아니라 단어 점검다.
"""
import argparse
import collections
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.join(HERE, "..", "data", "catalog", "work-korean-freq.json")
KEEP = {"NNG", "VV", "VA", "MAG", "XR"}

#: 빈도표가 담지 않는 구간 — `scripts/scrub_freq_table.py` 의 `FLOOR` 와 같아야 한다.
#   시험 `tests/test_freq_table_has_no_identity.py` 가 둘을 대조한다.
FLOOR = 40

#: ⛔ **한 글자 용언 어간도 본다.** 「걷다·굳다·재다·깎다·싣다」처럼 업무 글에
#   안 쓰는 고유어가 한 글자 어간에 몰려 있는데, 예전에는 `len < 2` 로 통째로
#   건너뛰어 **이 구간이 아예 안 보였다.** 실측 2026-09-15 — 문서 13개에서
#   지적이 448 → 483건(8% 증가)으로 늘고, 그날 사용자가 짚은 다섯 중 하나만
#   잡던 것이 넷으로 늘었다. 한 글자 **명사·부사**는 계속 건너뛴다(소음이 크다).
STEM_TAGS = {"VV", "VA", "XR"}

# 세지 않는 것 — 드문 것이 정상이라 목록에 있으면 소음이 된다.
SKIP = re.compile(r"^[A-Za-z0-9]+$")


def visible(path):
    t = io.open(path, encoding="utf-8").read()
    if path.lower().endswith((".html", ".htm")):
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S)
        t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
        t = re.sub(r"<[^>]+>", " ", t)
    else:
        t = re.sub(r"```.*?```", " ", t, flags=re.S)
        t = re.sub(r"`[^`]*`", " ", t)
    return t


def main():
    ap = argparse.ArgumentParser(description="사람이 안 쓰는 낱말을 찾아 보여 준다")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--max", type=int, default=40,
                    help="기준선에서 이보다 적게 나오면 목록에 올린다 (기본 40)")
    ap.add_argument("--top", type=int, default=25, help="몇 개까지 보일까")
    args = ap.parse_args()

    if not os.path.exists(TABLE):
        sys.exit(f"빈도표가 없습니다: {os.path.normpath(TABLE)}")
    data = json.loads(io.open(TABLE, encoding="utf-8").read())
    freq = data["freq"]

    from kiwipiepy import Kiwi
    kiwi = Kiwi()

    for path in args.paths:
        text = visible(path)
        seen = collections.Counter()
        where = {}
        for sent in kiwi.split_into_sents(text):
            for tok in kiwi.tokenize(sent.text):
                tag = tok.tag.split("-")[0]
                if tag not in KEEP or SKIP.match(tok.form):
                    continue
                if len(tok.form) < 2 and tag not in STEM_TAGS:
                    continue
                key = f"{tok.form}/{tag}"
                seen[key] += 1
                where.setdefault(key, " ".join(sent.text.split())[:56])

        rare = [(k, n, freq.get(k, 0)) for k, n in seen.items()
                if freq.get(k, 0) <= args.max]
        rare.sort(key=lambda x: (x[2], -x[1]))

        print(f"── {os.path.basename(path)} — 낱말 {len(seen)}종 · "
              f"기준선 {args.max}회 이하 {len(rare)}종")
        for key, mine, base in rare[:args.top]:
            form, tag = key.rsplit("/", 1)
            # ⛔ 표에 없는 낱말을 「0회」로 찍으면 **안 쓰는 말이라고 읽힌다.**
            #    표는 단어 점검이 안 읽는 구간(문턱 이하·한 글자)을 빼고 담으므로
            #    없다는 것은 「그 아래」라는 뜻이지 부재가 아니다. 전역 규칙의
            #    「부정 단정을 네 갈래로」가 그대로 걸린다 — 부재와 미기재를 가른다.
            shown = f"{base:>4}회" if key in freq else f"≤{FLOOR:<3}회"
            print(f"   {form:>10}/{tag:<3} 이 문서 {mine:>2}회 · 기준선 "
                  f"{shown}   {where[key]}")
        if len(rare) > args.top:
            print(f"   … 그 밖에 {len(rare)-args.top}종")
        print()

    print(f"기준선 — 사람이 쓴 업무 한국어 {data['docs']:,}건 · "
          f"{data['chars']:,}자 · 낱말 {len(freq):,}종")
    print(f"   표는 {FLOOR}회 이하와 한 글자를 안 담습니다 — 단어 점검이 그 둘을 "
          "없는 낱말과 똑같이 다루기 때문입니다(「≤{0}회」가 그 뜻).".format(FLOOR))
    print("⚠️ 드문 것이 곧 틀린 것은 아닙니다 — 볼 곳을 좁혀 줄 뿐입니다.")


if __name__ == "__main__":
    main()
