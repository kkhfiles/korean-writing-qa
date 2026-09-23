#!/usr/bin/env python
"""`doc-style-check.py` 자체 시험.

**이 파일이 생긴 이유** — 2026-08-28 에 산문 형식 HTML(제품 소개 한 장)을 검사하다
두 가지가 드러났다. 둘 다 조용해서, 검사기를 믿고 넘어가면 알 길이 없었다.

1. `--form prose` 를 붙여도 「서술형 문단」이 그대로 났다. 그 검사는 개조식을
   전제하는데 `FORM_ONLY_STRUCTURED` 에서 빠져 있었다 — 산문 문서에서 90자 넘는
   문단은 정상이다.
2. 없는 플래그를 줘도 rc 0 으로 그냥 돌았다. `--relaxd` 처럼 한 글자 틀리면
   **끄려던 검사가 안 꺼진 채 통과로 읽힌다.**

시험은 임시 파일로만 돌고 실제 문서를 안 읽는다.
"""
import io
import os
import subprocess
import sys
import tempfile

CHECKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doc-style-check.py")
fails = []


def run(*args):
    r = subprocess.run([sys.executable, "-X", "utf8", CHECKER, *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def eq(label, got, want):
    if got == want:
        return
    fails.append(f"{label}\n    받음 {got!r}\n    기대 {want!r}")


def write(path, text):
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)
    return path


HOME = tempfile.mkdtemp(prefix="doc-style-test-")

# 산문 한 장 — 흐르는 문단이 뼈대다. 진입점(lede)과 90자 넘는 문단 둘.
PROSE_HTML = write(os.path.join(HOME, "prose.html"), """<title>소개</title>
<h1>무엇을 풀었나</h1>
<p class="lede">기록이 안 남는 원인은 게으름이 아니라 묻는 시점</p>
<section>
<h2>풀려던 문제</h2>
<p>완료한 업무에 실제로 몇 시간 걸렸는지 적는 칸이 있습니다. 체크인이 매일 물었지만
열닷새 동안 새로 적힌 것이 하나도 없었습니다. 사람이 게을러서가 아니라 묻는 시점이
일이 끝나고 몇 시간 뒤라 이미 기억이 흐렸습니다.</p>
<p>묻는 지점을 완료를 누르는 그 순간으로 옮기고, 안 적힌 완료 업무를 화면 맨 위에
가로로 늘어놓아 하나씩 치우게 했습니다. 더 자주 묻지 않았고 묻는 지점만 옮겼습니다.</p>
</section>
""")

# ── ① 산문 형식이면 「서술형 문단」을 안 낸다 ────────────────────────────
#
# **이것이 이 시험이 생긴 까닭이다.** 개조식을 전제하는 검사인데 형식에서 안 빠져
# 있어, 산문 문서에는 `--form prose` 를 붙여도 같은 지적이 그대로 났다.
rc_d, out_d = run(PROSE_HTML)
rc_p, out_p = run(PROSE_HTML, "--form", "prose")
eq("형식을 안 적으면 서술형 문단을 지적한다", "서술형 문단" in out_d, True)
eq("**산문이라고 적으면 지적하지 않는다**", "서술형 문단" in out_p, False)
eq("산문에서도 오류는 0", "오류 0" in out_p, True)

# **형식을 파일이 들고 있게 한다.** HTML 에는 머리말이 없어 플래그가 유일한 길인데,
# 그러면 검사할 때마다 사람이 기억해야 한다 — 기억해야 하는 구조는 실패한다.
META_HTML = write(os.path.join(HOME, "meta.html"),
                  '<meta name="form" content="prose">\n'
                  + io.open(PROSE_HTML, encoding="utf-8").read())
rc_m, out_m = run(META_HTML)
eq("**파일이 산문이라고 적어 두면 플래그 없이도 따른다**", "서술형 문단" in out_m, False)

# ── ② 모르는 플래그는 멈춘다 ─────────────────────────────────────────────
#
# 조용히 무시하면 **끄려던 검사가 안 꺼진 채 통과로 읽힌다.** 오타 하나로 그렇게 된다.
rc_t, out_t = run(PROSE_HTML, "--relaxd")
eq("오타 플래그는 rc 로 멈춘다", rc_t != 0, True)
eq("무엇이 틀렸는지 말한다", "--relaxd" in out_t, True)

rc_ok, _ = run(PROSE_HTML, "--relaxed")
eq("제대로 적은 플래그는 그대로 돈다", rc_ok in (0, 1), True)

rc_v, _ = run(PROSE_HTML, "-v")
eq("짧은 플래그도 그대로 받는다", rc_v in (0, 1), True)

# ── 「회기」 ─────────────────────────────────────────────────────────
#
# 규칙만으로는 안 막혔다 — 글로벌 「어려운 말로 쓰지 않음」이 있는데도 78곳을 썼고
# 전수 점검에서 **전부 틀렸다**(회귀 오타 46 · 「세션」 뜻 32 · 정당한 쓰임 0).
# 낱말 안에 우연히 든 것(조회기간·사회기여)과 회의체 회기는 안 걸려야 한다 —
# 오탐이 섞이면 아무도 안 본다.
HOEGI_MD = write(os.path.join(HOME, "hoegi.md"), """**진입점** — 검사기 시험용

- **틀린 값** — 분산 RRF 가 만든 -4.9pp 회기
- **또 다른 값** — 같은 회기에 양쪽 갱신
""")
rc_h, out_h = run(HOEGI_MD)
eq("회기를 오류로 잡는다", out_h.count("[「회기」]"), 2)

HOEGI_OK_MD = write(os.path.join(HOME, "hoegi-ok.md"), """**진입점** — 정당한 쓰임

- **조회 화면** — 상단 조회기간 시작일을 해당월 1일로 설정
- **이력서 항목** — 경력사항(조직 및 사회기여)
- **처리 지연** — 국회 회기 중에는 늦음
""")
rc_ok, out_ok = run(HOEGI_OK_MD)
eq("낱말 안의 회기·회의체 회기는 안 걸린다", out_ok.count("[「회기」]"), 0)

rc_f, out_f = run(PROSE_HTML, "--form", "산문")
eq("형식 값이 틀리면 멈춘다", rc_f != 0, True)

# ── HTML 제목 ────────────────────────────────────────────────────────────
#
# **왜 생겼나** — 규칙은 있는데 HTML 경로에만 안 걸려 있었다. 마크다운은
# `제목 서술형`·`제목 명사형 위반`을 보는데 `scan_html` 은 `<h1>` 을 진입점 찾는
# 데만 썼다. 그래서 값은 전부 개조식인 아티팩트가 **제목만 서술 문장인 채로**
# 오류 0 을 받았다(2026-09-02 실측 — 사용자가 읽고서야 걸렸다).
#
# 시험은 걸렸던 그 모양으로 짠다 — `<br>` 로 두 줄을 이은 제목이 원래 형태다.
# 홑줄로만 재 보면 「재현 안 됨」이 나와 맞는 진단을 지운다.
TITLE_BAD_HTML = write(os.path.join(HOME, "title-bad.html"), """<title>설명</title>
<h1>땅속에 깔린 실그물이<br>흩어진 자료를 잇는다</h1>
<p class="lede">한 줄 질문에 한 줄로 답하는 검색 비서</p>
<section>
<h2>자료는 여덟 군데에 흩어져 있고<br>합치는 일은 사람 몫이었다</h2>
<dl><dt>자료 있는 곳</dt><dd>메일 · 이슈 · 노션</dd></dl>
</section>
""")
rc_tb, out_tb = run(TITLE_BAD_HTML)
eq("**HTML 제목의 서술형 종결을 잡는다**", out_tb.count("[제목 서술형]"), 2)

# `<br>` 뒤가 명사구여도 앞 줄이 서술형이면 잡아야 한다 — 줄바꿈은 줄을 가른다.
# 통째로 이어 붙이면 끝만 보게 되어 앞 줄의 서술형이 통째로 빠진다.
TITLE_BR_HTML = write(os.path.join(HOME, "title-br.html"), """<title>설명</title>
<h1>흩어진 자료를 잇는다<br>땅속 실그물</h1>
<p class="lede">한 줄 질문에 한 줄로 답하는 검색 비서</p>
""")
rc_br, out_br = run(TITLE_BR_HTML)
eq("**줄바꿈 앞 줄의 서술형도 잡는다**", out_br.count("[제목 서술형]"), 1)

# 오탐 확인 — 명사구 제목·고유명 제목·의문형 라벨은 각각 제 판정을 받아야 한다.
TITLE_OK_HTML = write(os.path.join(HOME, "title-ok.html"), """<title>설명</title>
<h1>흩어진 회사 자료를 잇는<br>땅속 실그물</h1>
<p class="lede">한 줄 질문에 한 줄로 답하는 검색 비서</p>
<section>
<h2>자료는 여덟 군데 ·<br>합치는 일은 사람 몫</h2>
<h3>모음 · 이음 · 답함</h3>
<h3>찾는 방법 넷</h3>
<h3>「관찰한 사실은 LCT가 낸다」</h3>
<dl><dt>자료 있는 곳</dt><dd>메일 · 이슈 · 노션</dd></dl>
</section>
""")
rc_to, out_to = run(TITLE_OK_HTML)
eq("명사구·고유명 제목은 안 걸린다", out_to.count("[제목 서술형]"), 0)
eq("명사구 제목에 명사형 위반도 없다", out_to.count("[제목 명사형 위반]"), 0)

TITLE_Q_HTML = write(os.path.join(HOME, "title-q.html"), """<title>설명</title>
<h1>무엇을 보나</h1>
<p class="lede">한 줄 질문에 한 줄로 답하는 검색 비서</p>
""")
rc_tq, out_tq = run(TITLE_Q_HTML)
eq("의문문 제목은 명사형 위반으로 잡는다", out_tq.count("[제목 명사형 위반]"), 1)

# 산문 형식이면 끈다 — 개조식을 전제하는 검사라 소개 글·발표 대본에는 안 맞는다.
rc_tp, out_tp = run(TITLE_BAD_HTML, "--form", "prose")
eq("**산문이라고 적으면 제목을 지적하지 않는다**", "[제목 서술형]" in out_tp, False)

# 마크다운 제목도 같은 순서를 지켜야 한다 — 꼬리를 먼저 떼면 닫는 「」가 떨어져
# 인용이 열린 채 남고, 그 안의 서술형이 제목의 종결로 잡힌다. 고유명 제목은
# 정본과 글자가 같아야 해서 개조식으로 고칠 수 없다(규칙 §1).
TITLE_MD = write(os.path.join(HOME, "title.md"), """**진입점** — 검사기 시험용

## 「관찰한 사실은 LCT가 낸다」

## 검사기가 규칙을 대신 지켜 준다

- **값** — 메일 · 이슈
""")
rc_tm, out_tm = run(TITLE_MD)
eq("**고유명 제목은 서술형으로 안 잡는다**", out_tm.count("[제목 서술형]"), 1)
eq("고유명 제목에 명사형 위반도 없다", out_tm.count("[제목 명사형 위반]"), 0)
eq("서술형 제목은 그대로 잡는다", "검사기가 규칙을 대신 지켜 준다" in out_tm, True)

# ── ⑤ 「~하나」로 끝나는 의문문 라벨 ──────────────────────────────────────
#
# `QEND_HARD` 가 「하나」를 수사로 보고 통째로 제외했다. 그래서 **「왜 정해야 하나」
# 같은 진짜 의문문이 빠져나갔다** — 연구소장·실장이 읽는 페이지의 둘째 줄에서 실제로
# 새어 나갔다(2026-09-07). 실측 176개 문서에서 「의문사 + 하나」는 96건이었고 그중
# 수사는 1건뿐인데, 그 1건의 의문사가 **어느**였다. 관형사(어느·몇·얼마)는 뒤에
# 수사가 올 수 있고 서술어를 요구하지 않는다. 그래서 「하나」 종결에는
# **서술어를 요구하는 의문사**(무엇·왜·어떻게·어디·언제·누가)만 짝지어 본다.
HANA_MD = write(os.path.join(HOME, "hana.md"), """**진입점** — 검사기 시험용

- **왜 정해야 하나** — 저장소에는 라이선스가 반드시 붙음
- **무엇을 하나** — 연동 스킬 게시
- **선행 확인 하나** — 공개 코드와 특허의 관계
- **어느 쪽이든 지켜야 할 것 하나** — 법인 명의 저작권 표기
""")
rc_h, out_h = run(HANA_MD)
eq("**「왜 정해야 하나」를 의문문 라벨로 잡는다**", "왜 정해야 하나" in out_h, True)
eq("「무엇을 하나」도 잡는다", "무엇을 하나" in out_h, True)
eq("**수사 「하나」는 안 잡는다**", "선행 확인 하나" in out_h, False)
eq("**관형사 의문사 + 수사 하나도 안 잡는다**", "지켜야 할 것 하나" in out_h, False)
eq("잡힌 것은 의문문 라벨 사유로 난다", out_h.count("라벨을 의문문으로 썼다"), 2)

if fails:
    print(f"실패 {len(fails)}건\n")
    for f in fails:
        print("  ✗ " + f)
    sys.exit(1)
print("통과 — 문서 검사기 (산문 형식이 서술형 문단을 끔 · 파일이 형식을 들고 있음"
      " · 모르는 플래그는 멈춤 · 형식 값 검사 · 회기)")
