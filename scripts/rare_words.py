"""사람이 안 쓰는 단어를 문서에서 찾아 사람에게 보여 준다.

    python -X utf8 scripts/rare_words.py <파일…> [--max 40] [--top 25]

**왜 만들었나.** 단어 규칙은 이번에 걸린 말만 안다 — 「걷다」를 막았더니 다음에
「갈래·스스로·채점」이 나왔고, 그것도 사람이 눈으로 찾았다(2026-09-09 두 번).
같은 일이 되풀이되지 않으려면 **안 본 말도 걸리는 장치**가 있어야 한다.

**어떻게 가르나.** 어원이 아니라 **빈도**다. 드물게 쓰는 고유어는 흔한 한자어보다
어렵다 — 읽는 사람은 어원을 모르고 빈도만 안다. 기준선은 사람이 쓴 업무 한국어
4,790만 자(메일·사내 규정·지라·노션)이고, 거기서 몇 번 나오는지로 줄을 세운다.

⚠️ **판정하지 않는다 — 목록만 낸다.** 드문 것이 곧 틀린 것은 아니다(제품 이름·
전문 용어·숫자 단위가 드문 것은 정상이다). 이 도구가 하는 일은 **확인할 단어를
줄이는 것**이고, 고칠지는 사람이 정한다. 그래서 검사기 규칙이 아니라 단어 점검다.
"""
import argparse
import collections
import fnmatch
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

#: ── 둘째 축 · 과다 비율 ────────────────────────────────────────────────────
#
#   **첫째 축의 사각** — 절대 문턱(40회 이하)만 보면 **문턱 위에 있는데 사용자가
#   짚은 말**이 영영 안 보인다. 「갈래」 90 · 「담기」 106 · 「가리」 43 ·
#   「매일」 104 · 「기다리」 203 이 전부 그 구간이다(회차별 지적 다섯).
#
#   **재는 것** — 「이 문서가 기준선보다 몇 배 자주 쓰나」.
#       배수 = (이 문서 빈도 / 이 문서 글자수) ÷ (기준선 빈도 / 기준선 글자수)
#
#   **실측으로 고른 값**(2026-09-16)
#   | 문서 | 1위 | 배수 |
#   |---|---|---|
#   | `docs/status.md` | **갈래** | **1,107** |
#   | `docs/rule-candidates.md` | **갈래** | **784** |
#   | 업무 기록 TSK-10 | 공동 | 353 |
#   | 업무 기록 TSK-11 | 신설 | 461 |
#
#   평범한 업무 문서는 1위가 350배 안팎이고, 드문 고유어를 되풀이한 문서는 1,000배를
#   넘는다. 그 사이에 줄을 그었다.
#
#   ⛔ **판정이 아니라 볼 곳 좁히기다.** 상위에는 그 문서의 주제어가 섞인다
#      (이 저장소 글이면 판정·오탐·라벨). 걸러 낼 것은 `known-words.jsonl` 에
#      범위와 함께 등록한다.
#   ⛔ **한두 번 나온 말은 안 센다** — 1,800자 문서에서 1회짜리 낱말이 상위를
#      통째로 차지했다(실측). 짧은 글일수록 비율이 불안정하다.
#   ⛔ **기준선이 높은 말은 안 본다** — 시험이 잡았다. 같은 문장을 열두 번 되풀이한
#      글에서 「협의」(기준선 1,835)·「보고」(1,859)가 380배로 올라왔다. 흔한 말을
#      자주 쓰는 것은 그 글의 주제일 뿐이다. 사용자가 짚은 다섯은 전부 낮은 쪽이다
#      — 가리 43 · 갈래 90 · 매일 104 · 담기 106 · 기다리 203.
OVERUSE_RATIO = 350
OVERUSE_MIN_HITS = 3
OVERUSE_BASE_CAP = 300

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
        # ⛔ 「``` … ```」 로 적으면 **네 겹 펜스가 안 닫힌다** — 안쪽 세 겹이 바깥을
        #    닫아 코드가 본문으로 새어 나온다(검사기에서 같은 결함을 고쳤다 ·
        #    2026-09-16). 여는 개수를 기억해 그 이상으로만 닫는다.
        t = re.sub(r"^(?P<f>`{3,}|~{3,})[^\n]*\n.*?^(?P=f)`*[ \t]*$",
                   " ", t, flags=re.S | re.M)
        t = re.sub(r"`[^`]*`", " ", t)
    return t


#: 사람이 「이 쓰임은 정상」이라고 판정한 것. **단어가 아니라 짝으로 적는다.**
#   ⛔ 단어 전체를 정상으로 등록하면 그 단어가 나쁘게 쓰인 경우까지 영영 가려진다
#      — 「갈래는 정상」으로 넣으면 「갈래 ① 변경 요청 단계」까지 통과한다
#      (2026-09-16 외부 검토 지적). 그래서 문맥을 함께 받는다.
#   문맥 `*` 는 **어디서나 정상**이라는 뜻이다. 근거를 반드시 적게 해서
#   나중에 누가 왜 열어 줬는지 되짚을 수 있게 한다.
KNOWN = os.path.join(HERE, "..", "data", "catalog", "known-words.jsonl")


def load_known(path):
    """{단어/품사: [(문맥, 범위)…]} — 없으면 빈 사전."""
    out = {}
    if not os.path.exists(path):
        return out
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        row = json.loads(line)
        out.setdefault(row["word"], []).append(
            (row.get("context") or "*", row.get("scope") or "*"))
    return out


def is_known(known, key, sentence, path):
    """이 자리의 이 단어가 이미 정상으로 판정됐나.

    ⛔ **범위를 안 보면 안 된다.** 「명사」·「동사」는 이 저장소 글에서는 정상이지만
       업무 보고서에 나오면 걸려야 한다 — 사람 글 4,790만 자에서 명사 12회 ·
       동사 9회로 진짜 드문 말이다. 단어만 열어 주면 그 구분이 사라진다.
    """
    full = os.path.abspath(path).replace(os.sep, "/")
    for ctx, scope in known.get(key, ()):
        if scope != "*" and not fnmatch.fnmatch(full, scope):
            continue
        if ctx == "*" or ctx in sentence:
            return True
    return False


def accept(path, word, context, why, scope="*"):
    """정상 판정을 목록에 더한다 — 근거 없이는 안 받는다."""
    import datetime
    row = {"word": word, "context": context, "scope": scope, "why": why,
           "added": datetime.date.today().isoformat()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def accept_file(known_path, rows_path):
    """여러 짝을 한 번에 등록한다 — 단어마다 명령 하나면 사람이 게이트를 끈다.

    파일은 JSONL 이고 줄마다 `{word, context, scope, why}` 다. `why` 가 빈 줄은
    **안 받는다** — 근거 없이 열어 준 짝은 나중에 왜 열렸는지 아무도 모른다.
    """
    import datetime
    today = datetime.date.today().isoformat()
    rows, skipped = [], []
    with io.open(rows_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            if not row.get("why"):
                skipped.append(row.get("word", "?"))
                continue
            rows.append({"word": row["word"],
                         "context": row.get("context") or "*",
                         "scope": row.get("scope") or "*",
                         "why": row["why"], "added": today})
    os.makedirs(os.path.dirname(os.path.abspath(known_path)), exist_ok=True)
    with io.open(known_path, "a", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows), skipped


def emit_template(rows, where, out_path, scope):
    """게이트가 막은 단어로 등록 서식을 만든다 — 사람이 `why` 만 채우면 된다."""
    folder = os.path.dirname(os.path.abspath(out_path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with io.open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# 이 문서에서 막힌 단어. **고칠 것은 문서를 고치고 그 줄을 지운다.**\n")
        f.write("# 정상인 것만 `why` 를 채운다 — 빈 줄은 안 받는다.\n")
        f.write("# 등록: python -X utf8 scripts/rare_words.py --accept-file "
                + out_path + "\n")
        for key, mine, base in rows:
            f.write(json.dumps({
                "word": key, "context": "*", "scope": scope, "why": "",
                "_이 문서": mine, "_기준선": base,
                "_보기": where.get(key, "")[:60]}, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="사람이 안 쓰는 단어를 찾아 보여 준다")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--max", type=int, default=40,
                    help="기준선에서 이보다 적게 나오면 목록에 올린다 (기본 40)")
    ap.add_argument("--top", type=int, default=25, help="몇 개까지 보일까")
    ap.add_argument("--overuse", type=int, default=OVERUSE_RATIO,
                    metavar="배수",
                    help="둘째 축 — 기준선보다 이 배수 이상 자주 쓴 말도 낸다 "
                         "(0 이면 끔)")
    ap.add_argument("--known", default=KNOWN,
                    help="이미 정상으로 판정한 짝 목록 (기본: data/catalog/known-words.jsonl)")
    ap.add_argument("--all", action="store_true",
                    help="정상으로 판정한 것까지 다 보인다 — 목록을 훑을 때")
    ap.add_argument("--accept", metavar="단어/품사",
                    help="이 짝을 정상으로 등록한다 — `--context` 와 `--why` 가 함께 있어야 한다")
    ap.add_argument("--context", help="정상인 문맥 · `*` 는 어디서나 정상")
    ap.add_argument("--why", help="왜 정상인지 한 줄")
    ap.add_argument("--scope", default="*",
                    help="어느 문서에서 정상인가 — 경로 무늬 · `*` 는 모든 문서")
    ap.add_argument("--accept-file", metavar="JSONL",
                    help="여러 짝을 한 번에 등록 — 줄마다 {word, context, scope, why}")
    ap.add_argument("--gate", action="store_true",
                    help="판정을 낸다 — 정상 등록이 안 된 드문 단어가 남으면 rc 1")
    ap.add_argument("--gate-max", type=int, default=60,
                    help="게이트가 보는 기준선 문턱 (기본 60) — 이보다 드문 단어는 "
                         "고치거나 근거를 적어 등록해야 통과")
    ap.add_argument("--emit-template", metavar="JSONL",
                    help="막힌 단어로 등록 서식을 만든다 — `why` 만 채우면 된다")
    args = ap.parse_args()

    if args.accept_file:
        took, skipped = accept_file(args.known, args.accept_file)
        print(f"정상으로 등록 {took}개")
        if skipped:
            print(f"⛔ 근거(`why`)가 비어 안 받은 것 {len(skipped)}개 — "
                  + " · ".join(skipped[:8]))
            return 1
        return 0

    if args.accept:
        if not args.context or not args.why:
            ap.error("--accept 에는 --context 와 --why 가 함께 있어야 합니다 — "
                     "근거 없이 열어 준 짝은 나중에 왜 열렸는지 아무도 모릅니다")
        row = accept(args.known, args.accept, args.context, args.why, args.scope)
        print(f"정상으로 등록 — {row['word']} · 문맥 「{row['context']}」 · "
              f"범위 「{row['scope']}」 · {row['why']}")
        return 0

    if not os.path.exists(TABLE):
        sys.exit(f"빈도표가 없습니다: {os.path.normpath(TABLE)}")
    data = json.loads(io.open(TABLE, encoding="utf-8").read())
    freq = data["freq"]
    base_chars = data["chars"]

    known = load_known(args.known)
    gate_rows, gate_where = [], {}

    from kiwipiepy import Kiwi
    kiwi = Kiwi()

    for path in args.paths:
        text = visible(path)
        chars = len(text)
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

        # ── 둘째 축 — 문턱 **위**에 있는데 이 문서가 지나치게 자주 쓰는 말
        over = []
        if args.overuse and chars:
            for key, mine in seen.items():
                base = freq.get(key, 0)
                if not FLOOR < base <= OVERUSE_BASE_CAP:
                    continue
                if mine < OVERUSE_MIN_HITS:
                    continue
                ratio = (mine / chars) / (base / base_chars)
                if ratio >= args.overuse and not is_known(
                        known, key, where.get(key, ""), path):
                    over.append((ratio, key, mine, base))
            over.sort(reverse=True)

        rare = [(k, n, freq.get(k, 0)) for k, n in seen.items()
                if freq.get(k, 0) <= args.max]
        hushed = 0
        if not args.all:
            kept = []
            for row in rare:
                if is_known(known, row[0], where.get(row[0], ""), path):
                    hushed += 1
                    continue
                kept.append(row)
            rare = kept
        rare.sort(key=lambda x: (x[2], -x[1]))

        if args.gate:
            # ⛔ 게이트는 **문턱이 따로다.** 목록을 보여 주는 문턱(기본 40)과
            #    막는 문턱(기본 60)이 같을 이유가 없다 — 「가리」(43회)처럼
            #    사용자가 짚은 말이 40 과 60 사이에 있다(2026-09-16 실측).
            blocked = [(k, n2, b) for k, n2, b in
                       [(k, seen[k], freq.get(k, 0)) for k in seen]
                       if b <= args.gate_max
                       and not is_known(known, k, where.get(k, ""), path)]
            blocked.sort(key=lambda x: (x[2], -x[1]))
            gate_rows.extend(blocked)
            gate_where.update(where)
            mark = "통과" if not blocked else f"막음 {len(blocked)}종"
            print(f"── {os.path.basename(path)} — {mark} "
                  f"(기준선 {args.gate_max}회 이하 · 정상 등록 안 된 것)")
            for key, mine, base in blocked[:args.top]:
                form, tag = key.rsplit("/", 1)
                print(f"   {form:>10}/{tag:<3} 이 문서 {mine:>2}회 · 기준선 "
                      f"{base:>4}회   {where[key]}")
            if len(blocked) > args.top:
                print(f"   … 그 밖에 {len(blocked) - args.top}종")
            continue

        print(f"── {os.path.basename(path)} — 단어 {len(seen)}종 · "
              f"기준선 {args.max}회 이하 {len(rare)}종"
              + (f" · 이미 본 것 {hushed}종 접음" if hushed else ""))
        for key, mine, base in rare[:args.top]:
            form, tag = key.rsplit("/", 1)
            # ⛔ 표에 없는 단어를 「0회」로 찍으면 **안 쓰는 말이라고 읽힌다.**
            #    표는 단어 점검이 안 읽는 구간(문턱 이하·한 글자)을 빼고 담으므로
            #    없다는 것은 「그 아래」라는 뜻이지 부재가 아니다. 전역 규칙의
            #    「부정 단정을 네 갈래로」가 그대로 걸린다 — 부재와 미기재를 가른다.
            shown = f"{base:>4}회" if key in freq else f"≤{FLOOR:<3}회"
            print(f"   {form:>10}/{tag:<3} 이 문서 {mine:>2}회 · 기준선 "
                  f"{shown}   {where[key]}")
        if len(rare) > args.top:
            print(f"   … 그 밖에 {len(rare)-args.top}종")
        if over:
            print(f"   ── 문턱 위인데 이 문서가 지나치게 자주 쓰는 말 {len(over)}종 "
                  f"(기준선 {FLOOR + 1}~{OVERUSE_BASE_CAP}회 · 이 문서가 "
                  f"{args.overuse}배 이상 · {OVERUSE_MIN_HITS}회 이상)")
            for ratio, key, mine, base in over[:args.top]:
                form, tag = key.rsplit("/", 1)
                print(f"   {form:>10}/{tag:<3} 이 문서 {mine:>2}회 · 기준선 "
                      f"{base:>4}회 · {ratio:>6,.0f}배   {where[key]}")
            if len(over) > args.top:
                print(f"   … 그 밖에 {len(over) - args.top}종")
        print()

    print(f"기준선 — 사람이 쓴 업무 한국어 {data['docs']:,}건 · "
          f"{data['chars']:,}자 · 단어 {len(freq):,}종")
    print(f"   표는 {FLOOR}회 이하와 한 글자를 안 담습니다 — 단어 점검이 그 둘을 "
          "없는 단어와 똑같이 다루기 때문입니다(「≤{0}회」가 그 뜻).".format(FLOOR))
    if args.gate:
        if args.emit_template:
            emit_template(gate_rows, gate_where, args.emit_template, args.scope)
            print(f"\n등록 서식을 만들었습니다 — {args.emit_template}")
        if not gate_rows:
            print("\n✅ 통과 — 정상 등록이 안 된 드문 단어가 없습니다")
            return 0
        print(f"\n⛔ 막힌 단어 {len(gate_rows)}종 — 둘 중 하나를 합니다")
        print("   ① 문서를 고친다 (업무에서 더 자주 쓰는 말로)")
        print("   ② 정상이면 근거를 적어 등록한다 — `--emit-template` 로 서식을 받고")
        print("      `why` 를 채운 뒤 `--accept-file` 로 한 번에 넣습니다")
        return 1

    if known:
        print(f"   이미 정상으로 판정한 짝 {sum(len(v) for v in known.values()):,}개를 "
              "접었습니다 — 전부 보려면 `--all`")
    print("⚠️ 드문 것이 곧 틀린 것은 아닙니다 — 확인할 단어를 줄여 줄 뿐입니다.")


if __name__ == "__main__":
    # ⛔ 종료 코드를 넘긴다. 안 넘기면 `--gate` 가 「막음 37종」이라 찍고도
    #    프로세스는 0으로 끝나, 게이트로 쓰는 쪽이 통과로 읽는다(2026-09-16 실측).
    sys.exit(main())
