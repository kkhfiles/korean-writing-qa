"""검사기가 「반말 서술형」으로 짚은 문장의 끝 낱말만 합쇼체로 바꾼다.

    python -X utf8 scripts/make_polite.py <파일…>            바뀔 목록만 보인다
    python -X utf8 scripts/make_polite.py --apply <파일…>    실제로 쓴다

**왜 있나.** 2026-09-23 에 「문서에는 반말 금지 · 문서 전부」가 오류 등급으로
올라갔다. 그날 재 보니 다른 프로젝트 문서 88개에서 3,632줄이 걸렸다. 손으로 고치면
며칠이 걸리고, 고치는 사람마다 말투가 갈린다.

**어느 문장을 바꿀지는 검사기가 정한다.** `scan_md` 가 「반말 서술형」을 낸 줄만
본다 — 판정을 여기서 다시 짜면 검사기가 바뀔 때 둘이 어긋난다. 그 줄 안에서 문장을
나누고 반말 조각을 찾는 세 단계도 검사기 함수를 그대로 부른다.

**고치는 것은 끝 음절뿐이다.** 품사는 형태소 분석기(kiwipiepy)로 가른다.
  · 받침 있는 앞 음절 + 다  → 습니다   (가져왔다 → 가져왔습니다 · 없다 → 없습니다)
  · 받침 없는 어간 + 다     → ㅂ니다   (크다 → 큽니다)
  · 서술격(이다 · 체언+다)  → 입니다   (한국어다 → 한국어입니다 · 길이다 → 길입니다)
  · 는다                    → 습니다   (먹는다 → 먹습니다 · 않는다 → 않습니다)
  · 줄어든 ㄴ다             → ㅂ니다   (쓴다 → 씁니다 · 돈다 → 돕니다 · 한다 → 합니다)
처음에는 분석기의 결합 기능으로 되붙였는데 음절이 깨졌다(가져왔다 → 가져었습니다).
끝 음절을 직접 바꾸는 쪽으로 바꿨다.

**⛔ 안 건드리는 것** — 「」·『』·"" 인용과 `코드` 안(남의 말 원문은 글자가 같아야
한다) · **두 어절 이하의 굵은 덩이 안 낱말**(「**돈다** — …」처럼 정해진 값 이름일 수
있다 · 세 어절부터는 문장이라 바꾼다) ·
HTML(마크다운만 본다) · Claude 만 읽는 지시 파일(검사기가 애초에 안 짚는다).
**못 바꾼 문장은 따로 적는다** — 굵게 표시가 낱말을 가른 곳(「**배수**다」)이나
「라」·「냐」로 끝나는 문장은 사람이 고친다.

실측(2026-09-23)
  · 이 저장소 문서 18개 — 411곳 · 잘못 바꾼 곳 0 · 손으로 고친 곳 19(그때는 굵게
    표시가 가른 낱말을 못 찾았다 · 지금은 바꾸는 음절이 굵게 밖이면 바꾼다)
  · 다른 프로젝트 문서 3개 사본 — 2,069곳 · 바꾼 뒤 남은 반말 지적 487곳 → 42곳(짧은
    굵은 덩이 · 불규칙 활용 — 사람 몫)
  · ⚠️ 그때 「하나씩 대조해 어긋남 0」은 **기계 대조**였다 — 바뀐 낱말이 이 함수의 답과
    같은지, 끝 음절 밖을 안 건드렸는지만 봤다. **말이 맞는지는 못 본다.** 실제로 「바뀌기
    까지다」를 「바뀌기까집니다」로 틀리게 바꾸는 판이었다(다른 세션 제보로 고침). 바꾼 뒤
    문서를 사람이 한 번 읽는다.
"""
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(HERE, "..", "assets", "doc-style-check.py")

#: 원문에서 끝 낱말을 찾을 때 건너뛰는 구간 — 인용과 코드
SHIELD = re.compile(r"「[^」\n]*」|『[^』\n]*』|\"[^\"\n]*\"|“[^”\n]*”|`[^`\n]*`")

#: 굵게 표시 한 덩이 — 낱말이 통째로 이 안이면 안 바꾼다
BOLD = re.compile(r"\*\*[^*\n]+?\*\*")

FINAL_N, FINAL_B = 4, 17

_kiwi = None
_dsc = None


def checker():
    global _dsc
    if _dsc is None:
        spec = importlib.util.spec_from_file_location("doc_style_check", CHECKER)
        _dsc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_dsc)
    return _dsc


def kiwi():
    global _kiwi
    if _kiwi is None:
        import kiwipiepy
        _kiwi = kiwipiepy.Kiwi()
    return _kiwi


def _final(ch):
    return (ord(ch) - 0xAC00) % 28 if "가" <= ch <= "힣" else -1


def _set_final(ch, idx):
    return chr(ord(ch) - (ord(ch) - 0xAC00) % 28 + idx)


#: 분석기가 겉에 없는 용언을 지어 넣는 꼴 — 「바뀌기까지다」를 「까지/JX + 하/VX + 다」로 읽는다
PHANTOM_STEM = {"VV", "VA", "VX", "XSV", "XSA"}


def polite_word(word, before=""):
    """끝이 「다」인 낱말 하나를 합쇼체로. 못 가르면 None.

    `before` 는 문장에서 바로 앞 낱말이다. 있으면 **그 낱말과 함께** 분석한다 —
    낱말만 주면 「재고 만다」의 「만다」를 「만들어」로, 「착수 긴급도다」의 「긴급도다」를
    「긴급 + 도다」로 읽어 못 바꿨다(다른 세션 제보 2026-09-23). 함께 읽어서 못 가르면
    낱말만으로 다시 본다.
    """
    if before:
        got = _polite(word, before + " " + word)
        if got:
            return got
    return _polite(word, word)


def _polite(word, phrase):
    if not word.endswith("다") or len(word) < 2:
        return None
    # ⛔ 마침표를 붙여 넘긴다 — 낱말만 주면 분석기가 「간다」·「온다」·「나쁘다」의
    #    끝을 연결 어미(EC)로 읽어 못 바꿨다(업무 비서 문서 실측 2026-09-23).
    toks = [t for t in kiwi().tokenize(phrase + ".") if not t.tag.startswith("S")]
    if len(toks) < 2 or toks[-1].tag != "EF":
        return None
    ef, prev = toks[-1].form, toks[-2]
    # ⛔ 겉에 없는 용언은 믿지 않는다 — 「바뀌기까지다」를 「까지 + 하(VX) + 다」로 읽어
    #    받침 없는 어간으로 보고 「바뀌기까집니다」로 **틀리게 바꿨다.** 앞이 조사 · 명사면
    #    「이다」가 준 것이다(「바뀌기까지입니다」).
    if (ef == "다" and prev.tag in PHANTOM_STEM and len(toks) >= 3
            and not word[:-1].endswith(prev.form)
            and toks[-3].tag[:1] in ("J", "N", "X") and toks[-3].tag not in PHANTOM_STEM):
        return word[:-1] + "입니다"
    body = word[:-1]                      # 「다」를 뗀 앞
    last = body[-1]
    if ef == "는다":
        return body[:-1] + "습니다" if body.endswith("는") else None
    if ef in ("ᆫ다", "ㄴ다"):
        if _final(last) != FINAL_N:
            return None
        return body[:-1] + _set_final(last, FINAL_B) + "니다"
    if ef != "다":
        return None
    if prev.tag == "VCP":
        # 「길이다」는 이 를 살리고, 「한국어다」는 줄어든 이 를 되살린다
        return (body[:-1] if body.endswith("이") else body) + "입니다"
    if _final(last) > 0:
        return body + "습니다"
    if _final(last) == 0:
        return body[:-1] + _set_final(last, FINAL_B) + "니다"
    return None


def plain_parts(path, raw):
    """(줄 번호, 반말 조각) — 검사기가 「반말 서술형」을 낸 줄에서만 찾는다."""
    dsc = checker()
    err, _, _ = dsc.scan_md(path)
    # 지적은 (갈래, "12행  …") 꼴이다 — 줄 번호는 설명 앞머리에 있다
    flagged = {int(m.group(1)) for kind, msg in err if kind == "반말 서술형"
               for m in [re.match(r"(\d+)행", msg)] if m}
    out = []
    for n, line in dsc.merge_wrapped(dsc.md_body(raw)):
        if n not in flagged:
            continue
        s = line.strip()
        if s.startswith("|"):
            speech = [c.strip() for c in s.strip("|").split("|")]
        else:
            speech = [dsc.LIST_HEAD.sub("", s, count=1) if dsc.LIST_HEAD.match(s) else s]
        # ⛔ 아래 세 줄은 `scan_md` 의 반말 판정과 같아야 한다 — 시험이 대조한다.
        #    하나만 다르다: 검사기는 문장마다 첫 조각만 내고 멈추지만 여기서는 대시
        #    뒤 조각까지 다 바꾼다. 멈추면 고친 뒤 다시 돌렸을 때 뒤 조각이 새로 걸린다.
        for text in speech:
            for sent in dsc.sentences(dsc.mask(dsc.strip(text).replace("**", ""))):
                for part in re.split(r"\s+[—–]\s+", sent):
                    if dsc.is_plain_speech(part):
                        out.append((n, part))
    return out


def convert(path, apply=False):
    """(바꾼 것 [(줄, 원래, 바뀐)], 못 바꾼 것 [(줄, 조각, 까닭)])."""
    with io.open(path, encoding="utf-8") as f:
        raw = f.read()
    starts = [0]
    for line in raw.split("\n"):
        starts.append(starts[-1] + len(line) + 1)
    done, missed, cursor = [], [], {}
    text, shift = raw, 0
    for n, part in plain_parts(path, raw):
        words = endings(part)
        if not words:
            missed.append((n, part, "끝 낱말 없음"))
        for w, before in words:
            got = _replace(text, w, cursor.get(n, starts[n - 1]) + shift, before)
            if isinstance(got, str):
                missed.append((n, part, got))
                continue
            text, a, grew = got
            shift += grew
            cursor[n] = a - shift
            done.append((n, w, polite_word(w, before)))
    if apply and done:
        with io.open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return done, missed


ENDING = re.compile(r"[가-힣]+다(?![가-힣])")


def endings(part):
    """이 조각에서 바꿀 끝 낱말 — 원문 순서대로.

    **본문의 끝 낱말**이 먼저다 — 검사기가 반말로 보는 것이 그것이다. 꼬리 괄호
    안이 반말로 끝나면(「덮어쓴다(더하지 않는다)」) 그것도 바꾼다.
    ⛔ 처음에는 조각의 마지막 「…다」 하나만 바꿨다. 꼬리 괄호가 있으면 괄호 안만
    바뀌고 정작 문장 끝(「덮어쓴다」)은 반말로 남았다(업무 비서 문서 실측 36곳).
    """
    body = checker().drop_tail(part)
    tail_text = part[len(body):]
    out = [(m.group(0), _word_before(body, m.start())) for m in ENDING.finditer(body)][-1:]
    tail = [(m.group(0), _word_before(tail_text, m.start()))
            for m in ENDING.finditer(tail_text)][-1:]
    return out + [(w, b) for w, b in tail if not w.endswith("니다")]


def _word_before(text, at):
    """`at` 바로 앞 낱말 — 분석기에 문맥으로 함께 넘긴다(굵게 · 괄호 같은 표시는 뺌)."""
    words = re.findall(r"[가-힣A-Za-z0-9]+", text[:at])
    return words[-1] if words else ""


def _replace(text, w, begin, before=""):
    """`begin` 뒤에서 처음 나오는 `w` 의 끝 음절을 합쇼체로.

    (새 글, 바꾼 끝 위치, 늘어난 글자 수) · 못 바꾸면 까닭 한 줄.
    """
    new = polite_word(w, before)
    if not new:
        return f"못 바꿈 「{w}」"
    window = text[begin:begin + 2000]
    shields = [(m.start(), m.end()) for m in SHIELD.finditer(window)]
    hit = None
    # 굵게 표시가 낱말을 가를 수 있다(「**6만 토큰**이다」) — 글자 사이의 `**` 를 넘어 찾는다
    for m in re.finditer(r"(?:\*\*)?".join(map(re.escape, w)) + r"(?![가-힣])", window):
        if any(a <= m.start() < b for a, b in shields):
            continue
        if m.start() and "가" <= window[m.start() - 1] <= "힣":
            continue                     # 낱말 가운데서 시작하면 다른 낱말이다
        hit = m
        break
    if hit is None:
        return f"원문에서 「{w}」 못 찾음"
    # ⛔ 두 어절 이하의 굵은 덩이 안이면 안 바꾼다 — 「**돈다** — …」의 「돈다」는 그
    #    프로젝트가 정한 판정 값 이름이었다(CT2612 재현 2026-09-23 · 「돈다 / 안 돈다 /
    #    안 봄」). 값 이름인지 굵은 결론 머리인지는 사람이 가른다.
    #    처음에는 굵게 안이면 전부 건너뛰었는데 실문서 여섯에서 700곳 가까이가 멈췄다.
    #    세 어절부터는 전부 문장이었다(「속도를 실측으로 잡았다」) — 그건 바꾼다.
    #    굵게가 낱말을 가르기만 하면(「**6만 토큰**이다」) 바꾼다 — 끝 음절이 굵게 밖이다.
    for bold in BOLD.finditer(window):
        inside = bold.start() <= hit.start() and hit.end() <= bold.end()
        if inside and len(bold.group(0).strip("*").split()) <= 2:
            return (f"굵게 안의 낱말 「{bold.group(0)}」 — 값 이름이면 「」로 감싸고, "
                    "서술형 결론이면 개조식으로 고침")
    # 바꾸는 것은 끝 몇 음절뿐이다 — 같은 앞부분은 원문(굵게 표시 포함)을 그대로 둔다
    keep = next((i for i, (x, y) in enumerate(zip(w, new)) if x != y), len(w))
    span = hit.group(0)
    letters = [i for i, ch in enumerate(span) if ch != "*"]
    cut = letters[keep] if keep < len(letters) else len(span)
    if "*" in span[cut:]:
        return f"굵게 표시가 바꿀 음절을 가름 「{span}」"
    a = begin + hit.start() + cut
    tail = new[keep:]
    return (text[:a] + tail + text[a + len(span) - cut:], a + len(tail),
            len(tail) - (len(span) - cut))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    apply = "--apply" in argv
    files = [a for a in argv if a != "--apply"]
    if not files:
        print(__doc__.split("\n\n")[1])
        return 2
    try:
        kiwi()
    except ImportError:
        print("형태소 분석기가 없습니다 — `python -m pip install kiwipiepy`")
        return 2
    total = 0
    for f in files:
        if not f.endswith(".md"):
            print(f"── {f} · 건너뜀(마크다운만 바꿉니다)")
            continue
        done, missed = convert(f, apply)
        total += len(done)
        print(f"── {f} · 바꿈 {len(done)} · 못 바꿈 {len(missed)}")
        for n, w, new in done[:6]:
            print(f"   {n}행  {w} → {new}")
        if len(done) > 6:
            print(f"   … {len(done) - 6}곳 더")
        for n, part, why in missed:
            print(f"   ⚠ {n}행  {why} · {part[:60]}")
    print(f"\n합계 {total}곳" + (" · 씀" if apply else " · 안 씀(목록만 · 쓰려면 --apply)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
