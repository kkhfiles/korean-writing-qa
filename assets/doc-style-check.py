#!/usr/bin/env python
"""문서 서술 규칙 검사기 — 글로벌 CLAUDE.md 「문서 서술 규칙」이 실제로 지켜지는지 센다.

    python assets/doc-style-check.py <파일…|디렉터리> [--relaxed] [--html-only] [-v]
                                     [--form structured|prose]
                                     [--rules <파일>] [--no-rules] [--list-rules]

대상: .md · .html — 디렉터리를 주면 둘 다 본다(`--html-only` 로 html만).
판정 3단계
    ❌ 오류       확실한 위반. 공유 자료는 발행 전 0을 확인한다
    ⚠️ 주의       사람이 봐야 한다
    ⛔ 검사 불가   값 슬롯을 못 찾았다 — 합격이 아니라 **안 본 것**이다
`--relaxed`: 머리 없는 설명 문장을 주의로 낮춘다(작업 문서용). 공유 자료엔 쓰지 않는다.

갈래 고르기: 조직마다 문서 관행이 다르다. `korean-qa.toml` 로 갈래를 끄거나 severity 를
      바꾼다(`--list-rules` 로 이름 확인). **끈 것은 출력 맨 위와 합계에 적힌다** —
      안 보이면 「오류 0」이 통과인지 안 본 것인지 갈리지 않는다.
      발행 게이트는 `--no-rules` 로 설정을 무시하고 전부 본다.

원칙: 판단이 불가능하면 침묵한다. 오탐이 섞이면 아무도 안 본다.
      그래서 확실한 것만 「오류」로, 사람이 봐야 하는 것만 「주의」로 낸다.
"""
import io, os, re, sys, glob, collections

sys.stdout.reconfigure(encoding='utf-8')

# 서술형 종결 — 값·목록·표 칸에서는 개조식이어야 한다.
# 한국어 평서형은 사실상 전부 「…다」로 끝난다 → 「다」로 잡고, 비교·한정어만 제외한다.
NARRATIVE = re.compile(r'[가-힣]다\.?$')
# 「아니다」는 빼지 않는다 — 규칙 §1이 ❌"대체하지 않는다" → ✅"대체 아님"으로 든 바로 그 형태다
NOT_NARRATIVE = re.compile(r'(보다|마다|최다|과다)\.?$')
LIST_HEAD = re.compile(r'^(?:[-*]\s+|\d+[.)]\s+)')   # 불릿과 번호 목록은 같은 값 슬롯이다
CONCL_HEAD = re.compile(r'^[→⇒]\s*')                 # 「→」 결론줄도 값이다(문단이 아니다)
# 문단 검사에서 빼는 줄 — 값이 없는 줄이라 판정 대상이 아니다
PARA_SKIP = re.compile(r'^(?:-{3,}|={3,}|\*{3,}|<|!\[|\[[^\]]*\]\([^)]*\)\s*$|\|)')
# 굵은 머리는 구분자나 공백으로 끊겨야 라벨이다 — 「**…재요청**한다」처럼 붙으면 문장 중간이다.
# 굵게 뒤 괄호 보충(「**model-invoked**(description 보유): …」)은 머리에 딸린 것으로 본다.
BOLD_HEAD = re.compile(r'^\*\*(.+?)\*\*\s*(?:\([^)]*\))?\s*(?:[—–\-:·：.。]\s*|\s+|$)(.*)$', re.S)
# 줄머리 기호(⚠️ ★ 🔴 …)는 라벨이 아니다 — 떼고 나서 굵은 머리를 찾는다
LEAD_MARK = re.compile(r'^(?:[←-⯿☀-➿️\U0001F000-\U0001FAFF]+\s*)+')
LABEL_COLON = re.compile(r'^\*\*(.+?)\*\*\s*(?:\([^)]*\))?\s*[:：]\s*(.*)$')   # 「라벨: 값」
TAIL = re.compile(r'\s*(?:\([^)]*\)|\[[^\]]*\]|（[^）]*）)\s*$')   # 꼬리 괄호·상호참조
# 「굵은 결론 + 근거 문장」 구조의 분기점 — 규칙 §1 「왜·근거는 문장」이 목록 안에 들어온 형태.
# 값과 근거를 가르는 신호는 **마침표**다(값은 마침표로 문장을 이어 붙이지 않는다).
# 길이 하한은 두지 않는다 — 규칙에 없는 장치라 짧은 근거를 값으로 오판했다(실측).
EVIDENCE_END = re.compile(r'[.。]$')
# 대상을 흐리는 지시어
# 「이쪽·그쪽·저쪽」은 가리킬 이름이 늘 존재하는데 위치로만 부른 것이라 HARD.
#   실측(2026-08-18 · md 1,921개): 열 건뿐이고 전부 실제 위반 — 오탐 0 · 발행본 회귀 0.
# ⚠️ 「자기·자신·스스로」는 넣지 않는다 — 같은 실측에서 자기 257·자신 34·스스로 96건이
#   전부 「자기개선」·「자기선택 표본」·「CRIU 자신이」·「제품이 스스로」 같은 정당한 쓰임이었다.
#   주격 형태로 좁혀도(자기가/는/를 18건) 전부 정당해 규칙이 서지 않는다.
VAGUE_HARD = ['우리', '이들', '저들', '얘네', '쟤네', '이쪽', '그쪽', '저쪽']
# SOFT는 HTML에서만 검사한다 — md에 켜면 여기 506·아래 363·그것 142건이 쏟아진다(같은 실측)
VAGUE_SOFT = ['여기', '거기', '아래', '위쪽', '이것', '그것', '저것']
# 대상을 평가하는 수식어 — 사실이 아니라 자평이다. 정당한 쓰임이 있어 「주의」로만 낸다.
# 뒤 여섯은 과장 어휘(humanize-korean 분류 체계 D-4)에서 가져왔다. 「압도적」·「대대적」은
# 옮겨 적은 남의 공지에도 섞이므로, 인용인지 자평인지는 읽는 쪽이 가른다.
SELF_PRAISE = ['가벼운', '강력한', '유연한', '혁신적', '똑똑한', '직관적인',
               '손쉬운', '최적의', '풍부한', '탄탄한', '완벽한', '뛰어난',
               '압도적', '대대적', '획기적', '폭발적', '파격적', '막강한']
# ── 번역투 (humanize-korean 분류 체계 A) ─────────────────────────────────────
# **채택은 항목 자체로 판단한다.** 「지금 이 뭉치에서 몇 건 나오나」는 오탐을 재는
# 물음이지 넣을지 정하는 물음이 아니다. 시료가 없으면 시료를 만든다.
# 실측은 정밀도에만 쓴다 — 정상 한국어를 잡는가.
#
# 이중 피동 — 피동 접사에 피동 보조용언을 겹친 형태. 문법서가 오류로 다루므로 **오류**.
#   어간을 목록으로 고정한다. 「옮겨지다」·「만들어지다」는 능동 어간이라 정상이니 뺀다.
#   ⚠️ 어간에 「되」를 넣었더니 「구축되지는 않습니다」의 「되지는」을 잡았다 — 「-지 않다」
#      부정형이지 피동이 아니다(실문서 2건이 전부 이것). 「되」는 「되어진」 꼴로만 본다.
DOUBLE_PASSIVE = re.compile(
    r'(?:불리|쓰이|보이|나뉘|모이|짜이|갈리|닫히|열리|잊히|잘리)어[지진졌]'
    r'|(?:불려|쓰여|보여|나뉘어|모아|짜여|갈려|닫혀|열려|잊혀|잘려)지[다는며면고게]'
    r'|되어[지진졌]')
# 이중 조사 — 「-에서의·-으로의·-에의·-로부터의」. 영어 전치사구 직역이다. **주의**.
#   ⚠️ 「경로의」·「대로의」·「서로의」는 「로」가 낱말의 일부다. 절단형 검사의 `LO_WORD`와
#      같은 함정이라 같은 목록으로 막는다(실문서 20건 중 절반 넘게 이것).
DOUBLE_PARTICLE = re.compile(r'[가-힣](?:에서의|으로의|로의|에의|으로부터의|로부터의|에로의)')
# 「그녀」 — 업무 문서에서는 사실상 번역 흔적이다. 소설·인용은 있을 수 있어 **주의**.
SHE_PRONOUN = re.compile(r'그녀')
def particle_is_part_of_word(hit):
    """「경로의」·「대로의」·「서로의」 — 「로」가 조사가 아니라 낱말의 일부다."""
    return bool(LO_WORD.search(hit.group(0).rstrip('의')))


# (이름, 패턴, 등급, 고치는 법, 걸러낼 조건)
TRANSLATIONESE = [
    ('이중 피동', DOUBLE_PASSIVE, 'err', '피동을 한 번만', None),
    ('번역투 이중 조사', DOUBLE_PARTICLE, 'warn', '조사를 하나로 풀 것',
     particle_is_part_of_word),
    ('번역투 그녀', SHE_PRONOUN, 'warn', '이름이나 직책으로', None),
]


def translationese_hits(text):
    """줄이나 본문 하나에서 번역투를 찾는다 — 갈래마다 처음 하나만."""
    for kind, pattern, level, fix, skip in TRANSLATIONESE:
        for hit in pattern.finditer(text):
            if skip and skip(hit):
                continue
            yield kind, level, fix, hit
            break
# ⛔ 「~에 있어(서)」는 **안 넣는다.** 항목 자체는 정당한 번역투(일본어 における 직역)지만,
#    한국어에는 「저장소에 있어 접근이 안 된다」처럼 **있다가 진짜 서술어인** 쓰임이 섞이고
#    줄만 봐서는 안 갈린다. 실문서 8건이 **전부** 그쪽이었다.
#    폐기가 아니라 판단 층 소관이다 — 「불필요한 영어」와 같은 자리에 둔다.
# 글·코드·절차의 지점을 「자리」로 부르는 은유 — 수식어가 뜻을 다 지고 「자리」는 빈 그릇이다.
#   30일 실측 783건(터미널 응답 324 · 파일 산출물 459).
#   「의견을 받는 자리」·「격식 있는 자리」처럼 **사람이 모이는 상황**은 정당한 한국어라
#   용언을 가리지 않으면 그쪽이 함께 걸린다. 그래서 두 겹으로 나눈다.
#
#   왜 오류인가 — 사용자 한국어를 기준선으로 같은 구문을 세면 「자리」만 5.3배로 튄다
#   (사용자 1만자당 0.4 · 문서 산출물 2.4). 대시 1.7배·화살표 1.9배는 개조식 표기라
#   설명이 되지만 이것은 안 된다. 흔히 말하는 AI 티(「수 있」 0.4배·「것이다」 0.2배)는
#   오히려 더 적어, 문서 산출물에서 확인된 유일한 문체 결함이다.
#
#   JARI      — 문서·코드 은유에만 쓰이는 용언. 정당 5건 시험에서 오탐 0이라 「오류」.
#   JARI_ANY  — 그 밖의 관형형 + 자리. 사람이 모이는 뜻을 빼고 「주의」로만 낸다.
JARI = re.compile(
    r'(?:걸리는|걸린|새는|도는|터지는|터진|터졌을|끊기는|끊긴|거치는|거친|띄우는|띄운'
    r'|덧붙이는|지나가는|세는|갈리는|갈린|빠지는|빠진|쏟아지는|깨지는|깨진|멈추는|멈춘'
    r'|나가는|먹는|붙는|푸는|넣을|넣는'
    # 실문서 445개 재점검에서 주의로만 남아 있던 것들 — 사람이 모이는 뜻이 없어 오류로 올린다
    r'|가리키는|겹치는|섞이는|고치는|쉬운|비싼|어긋나는|튀는)\s*자리')
JARI_ANY = re.compile(r'[가-힣]{1,8}(?:는|은|던|을|린|긴|난|운|친|킨|싼)\s*자리')

# 「자리」의 일반형 — 관형형 뒤에 뜻이 옅은 명사를 붙여 새 말을 짓는 것.
#   판정은 **그 명사가 혼자 서는가**다. 「모으는 창」의 창은 떼어 놓으면 무엇인지
#   말할 수 없고, 「걸린 시간」의 시간은 말할 수 있다.
#   같은 함정에 세 번 걸려서 옮겨 왔다(자리 → 판·창 → 값). 글로 적어 둔 것으로는
#   안 막혔다 — 글로벌 CLAUDE.md 「같은 함정에 두 번 넘어가면 기계로 옮긴다」.
#
#   실문서 1,161개로 여섯 낱말을 따로 쟀다. 넣는 셋과 빼는 셋이 갈렸다.
#
#   | 낱말 | 발화 | 정당 | 처리 |
#   |---|---|---|---|
#   | 판·창 | 0 | — | 넣음 · 발화가 0이라 넣는 값이 안 든다 |
#   | 결   | 1(깨진 문자열) | 1 | 넣음 · 「같은 결」·「한 결」은 굳은 쓰임이라 뺀다 |
#   | 값   | 9 | 8 | **안 넣음** |
#   | 축   | 4 | 4 | **안 넣음** |
#   | 층   | 2 | 2 | **안 넣음** |
#
#   ⛔ 값·축·층을 뺀 까닭은 「이 뭉치에 안 나와서」가 아니다 — 나왔고, 그 명사가
#      이 분야에서 **혼자 서기 때문**이다(코드가 계산하는 값 · 못 보는 축 · 읽는 층).
#      빈도가 아니라 정밀도로 잘랐다. 판정이 갈리는 「잃는 값」 한 건은 판단 층 소관.
#      거꾸로 판·창은 0건인데도 넣는다 — 「안 나온다」는 채택을 접을 근거가 아니다.
#   차수를 「판」으로 부르는 것도 같은 갈래다(1판·2판 → 1차·2차 · 앞 판 → 앞 실험).
#   지시어형·숫자형 둘 다 실문서 0건이라 함께 넣는다. 「3판」이 책의 판본이거나
#   「이번 판」이 놀이의 한 회일 수 있어 오류로는 올리지 않는다.
#   꼬리를 한 벌만 두는 까닭 — 두 벌로 두면 한쪽만 고쳐진다. 조사가 붙는 형태
#   (「앞 판에서」)를 놓치지 않으면서 낱말 안쪽(판단·창구·결과)은 걸러야 한다.
_NOUN_TAIL = r'(?=[을를이가은는도만에서로라며\s·,.!?)\]」]|$)'
EMPTY_NOUN = re.compile(
    r'(?:[가-힣]{1,8}(?:는|은|던|을|린|긴|난|운|친|킨|싼)\s*(?:판|창|결)'
    r'|(?:앞|뒤|이번|저번|다음|지난|첫|새|매)\s*판'
    r'|(?<![0-9가-힣])[1-9]\s*판)' + _NOUN_TAIL)
# 굳은 쓰임과 실물 — 「결」이 방향·기미라는 제 뜻으로 서는 쓰임, 화면에 실제로 뜨는 창
#   「같은」·「다른」·「그」가 앞에 오면 그 명사는 **이미 있는 것을 가리킨다** — 지어낸 말이 아니다.
#   전역 규칙 문서에서 「수동 실행이 같은 창에 떨어진다」(터미널 창)가 걸려서 넣었다.
#   ⛔ 「판」에는 이 예외를 안 준다 — 사용자가 고친 말이 바로 지시어형(「앞 판에서」)이다.
EMPTY_NOUN_OK = re.compile(
    r'(?:같은|한|다른|비슷한|고운|거친)\s*결'
    r'|(?:뜨는|뜬|여는|연|닫는|닫은|띄우는|띄운|열리는|열린|닫히는|같은|다른|그)\s*창')

# 「회기」 — 규칙만으로는 안 막혔다. 2026-09-01 전수 점검에서 78곳이 나왔고 **전부 틀렸다.**
#   회귀(回歸)=regression 오타 46 · 「이번 작업 세션」 뜻 32 · 정당한 쓰임 0.
#   가장 나쁜 것은 코드 주석과 README 의 「-4.9pp 회기」였다 — 분산 RRF 가 만든 -4.9pp
#   회귀를 적은 자리인데 회기로 읽으면 문장이 뜻을 잃는다.
#
#   글로벌 규칙 「어려운 말로 쓰지 않음」이 이미 있었는데도 계속 썼다. 읽고 지키는
#   형태로는 안 되는 것이라 여기로 옮긴다(글로벌 CLAUDE.md 「같은 함정에 두 번
#   넘어가면 글이 아니라 기계로 옮긴다」).
#
#   낱말 안에 우연히 든 것은 뺀다 — 조회기간·사회기여·기회기반 같은 것들.
#   국회·이사회처럼 **회의체 이름 뒤의 회기**는 정당한 쓰임이라 함께 뺀다.
HOEGI = re.compile(r'회기')
HOEGI_OK = re.compile(
    r'(?:조회\s*기간|조회기간|사회기여|기회기반|기회\s*기반'
    r'|(?:국회|이사회|총회|의회|위원회|정기|임시)\s*회기)')
# 실제 좌석과 굳은 쓰임 — 은유가 아니라 그 뜻 그대로다
#
#   ⛔ 「모임 뜻」을 예외로 두던 어간 열 개를 뺐다(2026-09-04 사용자 판단).
#      뺀 것: 받는·묻는·말하는·듣는·나누는·모이는·이야기하는·보고하는·배우는·가르치는
#
#   두 가지가 걸렸다.
#   ① **모임을 「자리」로 부르는 것 자체가 권할 말이 아니다** — 「의견을 받는 자리」보다
#      「의견을 수렴하는 회의」가, 「보고하는 자리」보다 「보고 회의」·「발표 세미나」가
#      무엇인지를 밝힌다. 예외로 두면 그 표현을 권장하는 셈이 된다.
#   ② **모임 뜻을 넣으려다 은유까지 통과시켰다** — 실문서 2,551개 실측에서 이 목록이
#      통과시키던 것 28건 중 은유가 7건이었다. 가장 나쁜 것은 화면의 입력 칸을 가리키는
#      「'있나'를 묻는 자리」로, 예외 목록이 지적을 막고 있었다(미탐).
#
#   좁혀도 **오류는 하나도 안 는다** — JARI_OK 는 JARI(오류)가 아니라 JARI_ANY(주의)만
#   막는다. 실측으로도 오류 18건 그대로 · 새로 주의가 되는 것 9건(전부 정당한 지적).
#   판정이 갈리는 것은 사람이 본다 — 그래서 오류가 아니라 주의다.
JARI_OK = re.compile(
    r'(?:같은|제|자기|첫|앞|뒷|옆|빈|윗|아랫|앉는|드나드는)\s*자리')
# 인용 블록의 출처 표기 — 이게 있어야 「남의 말 원문」이고, 그때만 검사에서 빠진다
ATTRIB = re.compile(
    r'`\[[^`]*\]`'
    r'|[\[(][^\])]{0,20}실장[^\])]{0,20}[\])]'
    r'|[\[(][^\])]{0,20}\d{1,2}/\d{1,2}[^\])]{0,20}[\])]'
    r'|[\[(](사내|근거|출처)[^\])]*[\])]')
HEAD_LINES = 6        # 문서 머리 「누가·언제·무엇을 위해 읽나」는 진입점 규칙 소관
# 이 낱말들은 열 이름만 봐서 안에 무엇이 있는지 알 수 없다. 다만 「비고」는
# 공문서 표의 표준 관례라 발행을 막을 근거가 못 된다 — 그래서 오류가 아니라 주의다.
BAD_LABEL = ['내용', '기타', '참고', '비고', '설명', '메모']
MD_HEADING = re.compile(r'^#{1,6}\s+(.+?)\s*#*$')

# ── 마스킹 — 검사에서 빼야 할 구간 ────────────────────────────────────────────
# 인라인 코드와 인용 부호 안은 「그 말을 언급한 것」이지 그렇게 쓴 것이 아니다.
CODE_SPAN = re.compile(r'`[^`]*`')
QUOTE_SPAN = re.compile(r'[「『][^」』]*[」』]|"[^"]*"|“[^”]*”')
# ❌/✅ 대조 예시 줄은 일부러 나쁜 예를 보여주는 자리다 — 위반으로 세지 않는다
CONTRAST = re.compile(r'[❌✅✗✓○×⭕]')


def is_example(s):
    """대조 예시인가 — ❌와 ✅가 한 줄에 함께 있거나, 기호와 인용이 함께 있으면 예시다.

    기호만 단독으로 쓴 칸(진행 상태 표의 ✅)은 예시가 아니라 **값**이다.
    이 구분이 없으면 상태 기호를 쓴 표가 통째로 검사에서 빠진다(실측)."""
    if not CONTRAST.search(s):
        return False
    if '❌' in s and '✅' in s:
        return True
    return bool(QUOTE_SPAN.search(s))


# ── 절단형·의사 의문문 ────────────────────────────────────────────────────────
# 개조식으로 줄이다 **조사에서 끊은** 형태 — 「해당 폴더에」·「코멘트로」·「그리기만」.
# 한국어는 조사 뒤에 서술어가 오길 기대하므로 미완성으로 읽힌다. 명사로 끝내야 완결된다.
# 명사 종결과 겹치지 않는 조사만 오류로 낸다(정의·주의·경로·국가처럼 조사 모양 명사가 많다).
JOSA_CUT = re.compile(r'[가-힣](?:에서|에게|한테|으로|로서|로써|를|는|에)$')
# 시점을 가리키는 부사구는 제목·구분선으로 자연스럽다 — 「코드를 쓰기 전에」·「병합 후에」.
# 「깊이는 10월에」처럼 서술어가 잘린 것과 달리 그 자체로 구간을 뜻한다(실측으로 갈라냄)
TIME_PHRASE = re.compile(r'(?:전|후|뒤|중|사이|동안)에$')
# 「만·까지·부터·로」는 정당한 값이 섞인다 — 「10/16까지」·「경로」·「워크플로」·「별로」.
# 앞 글자가 한글일 때만 본다(숫자 뒤 「10/16까지」는 기간 표기라 값이다)
JOSA_SOFT = re.compile(r'[가-힣](?:만|까지|부터|로)$')
# 「…로」로 끝나는 명사·부사 — 조사가 아니라 값이다
LO_WORD = re.compile(r'(?:경로|도로|회로|진로|통로|대로|선로|항로|수로|미로|플로|'
                     r'별로|서로|따로|새로|바로|주로|실로|종로)$')
# 라벨을 의문문으로 쓴 것 — 규칙 §2의 「라벨 = 독자가 품는 질문」을 의문형 **어미**로 오독한 형태
QWORD = re.compile(r'(무엇|뭐|어디|언제|누가|누구|왜|어떻게|얼마|몇|어느)')
QEND_HARD = re.compile(r'(?<!하)나$')                  # 「하나」는 수사라 제외
QEND_SOFT = re.compile(r'(?:까|는가|은가|인가|을까)$')  # 「왜 X인가」는 제목으로 관용적


def fragment(t):
    """값 하나를 보고 (오류 사유, 주의 사유)를 낸다. 해당 없으면 (None, None)."""
    t = t.strip()
    if not t or PROPER.match(t):
        return None, None
    if JOSA_CUT.search(t) and not TIME_PHRASE.search(t):
        return '조사로 끝나 서술어가 잘렸다 — 명사로 끝내거나 서술 명사를 붙일 것', None
    if QWORD.search(t) and QEND_HARD.search(t):
        return '라벨을 의문문으로 썼다 — 명사구로(「무엇을 보나」→「관측 대상」)', None
    if JOSA_SOFT.search(t) and not LO_WORD.search(t):
        return None, '조사 종결로 보인다 — 값이면 명사로 끝낼 것'
    if QWORD.search(t) and QEND_SOFT.search(t):
        return None, '의문형 라벨 — 명사구가 나은지 볼 것'
    return None, None


def mask(line):
    """지시어·수식어 검사용 — 코드·인용 구간을 지운다."""
    return QUOTE_SPAN.sub(' ', CODE_SPAN.sub(' ', line))


def strip(x):
    return re.sub(r'<[^>]+>', '', x).strip()


def drop_tail(t):
    """꼬리 괄호·상호참조·강조 표시를 뗀다 — 「…남는다 (부록 E)」의 서술형을 가리지 않도록.

    서술형 판정이 **끝 앵커**라 값 끝에 붙은 강조 표시가 그것을 가린다.
    「**…하나로 정해진다**」가 마크다운 표 칸에서 통과했다(2026-08-14 실측).
    split_value의 EVIDENCE_END 판정이 이미 같은 집합을 떼고 있다 — 여기와 맞춘다."""
    t = t.strip()
    while TAIL.search(t):
        t = TAIL.sub('', t).strip()
    return t.rstrip('"\'』」)*_`~”’')


PROPER = re.compile(r'^[「『][^」』]+[」』]$')   # 값 전체가 고유명 표기


def all_quoted(t):
    """값 전체가 인용·고유명 표기인가 — 그러면 개조식으로 고칠 수 없다(규칙 §1).

    「」로 감싼 값 = 고유명(원칙 이름·문서 제목·정해진 문구)이고,
    따옴표 안의 서술형은 **인용된 문구**다 — 값이 아니라 이름처럼 다룬다.
    인용을 지우고 남는 게 없으면 값 전체가 인용이다: 「"규칙을 썼다" ≠ "규칙이 적용된다"」
    drop_tail 이 닫는 따옴표를 떼기 **전에** 본다 — 떼고 나면 인용 안 서술형이 노출된다.
    강조 표시는 인용 바깥에 붙으므로 함께 뗀다 — 「*"어디에 물어보나"*」가 그 형태다.
    """
    base = strip(t).replace('**', '').strip(' *_`~')
    if PROPER.match(base):
        return True
    # 꼬리 괄호는 출처 표기다 — 「"…한다" (여러 블로그)」의 인용을 가리면 안 된다.
    # 인용 판정에서만 뗀다(값 판정은 drop_tail 이 따로 한다).
    for cand in (base, TAIL.sub('', base).strip(' *_`~')):
        if PROPER.match(cand) or QUOTE_SPAN.sub(' ', cand).strip(' ≠=·-—*_`~') == '':
            return True
    return False


def is_narrative(sent):
    """값의 종결이 서술형인가 — **인용 안의 서술형은 값의 종결이 아니다**(규칙 §1).

    drop_tail 이 닫는 괄호를 떼면 인용 안 서술형이 값의 끝으로 노출된다.
    「… 엔진팀 판단이 「도입 장벽이 가장 낮다」」가 그 형태다(2026-08-14 실측).
    인용을 지운 자리에서 종결을 본다 — 인용 밖이 명사형이면 값은 개조식이다.
    ★ 순서가 중요하다 — **인용을 먼저 지우고 꼬리를 뗀다.** 거꾸로 하면
    닫는 괄호가 먼저 떨어져 인용이 열린 채 남고 그 안의 서술형이 값의 끝이 된다."""
    probe = drop_tail(QUOTE_SPAN.sub(' ', sent))
    return bool(NARRATIVE.search(probe)) and not NOT_NARRATIVE.search(probe)


def sentences(t):
    """값 하나를 문장 단위로 쪼갠다 — 마지막 문장만 보면 앞 문장의 서술형을 놓친다."""
    if all_quoted(t):
        return []
    # 꼬리를 여기서 떼지 않는다 — 인용을 지우기 전에 닫는 괄호가 떨어지면
    # 인용 안 서술형이 값의 끝으로 노출된다(is_narrative 가 순서를 지킨다).
    out = []
    for chunk in re.split(r'(?<=다\.)\s+', strip(t)):
        c = chunk.strip()
        if c and not set(c) <= set('-: '):
            out.append(c)
    return out


def split_value(c):
    """검사 대상 조각과 그 구조를 낸다 — (조각들, 굵은머리 있나).

    「굵은 결론 + 근거 문장」이면 결론만 본다. 표 칸에는 쓰지 않는다 —
    표는 그 자체가 값 슬롯이라 근거 문장이 올 자리가 아니다."""
    c = LEAD_MARK.sub('', c.strip())
    lm = LABEL_COLON.match(c)
    if lm:
        # 콜론 뒤는 값이다. 「굵은 결론 — 근거 문장」 예외를 콜론 값에 적용하면
        # 「**상태**: 공개자료를 확인한다.」 같은 서술형 값이 빠진다.
        return [x.replace('**', '') for x in (lm.group(1), lm.group(2)) if x.strip()], True
    m = BOLD_HEAD.match(c)
    if not m:
        return [c.replace('**', '')], False
    head, rest = m.group(1), m.group(2).strip()
    # 마침표 뒤에 강조 표시·닫는 따옴표가 붙으면 원문 그대로는 마침표를 못 찾는다.
    # 「… 하지 않는다.**」 「… 인가."*」 가 근거 문장으로 인정되지 않아 오탐이 났다(실측).
    if rest and EVIDENCE_END.search(rest.rstrip('*_`~"”’\'」』 ')):
        return [head.replace('**', '')], True
    return [x.replace('**', '') for x in (head, rest) if x.strip()], True


# ── HTML ─────────────────────────────────────────────────────────────────────
def scan_html(path, relaxed=False, form=None, rules=None):
    raw = io.open(path, encoding='utf-8').read()
    # base64 등 초장문 줄 제외 → 그 안의 우연한 일치를 오탐으로 세지 않는다
    body = '\n'.join(l for l in raw.split('\n') if len(l) < 800)
    body = re.sub(r'<style.*?</style>', ' ', body, flags=re.S)
    body = re.sub(r'<script.*?</script>', ' ', body, flags=re.S)   # 코드는 문서가 아니다
    # 코드는 문서가 아니다 — 마크다운은 코드펜스와 인라인 코드를 처음부터 뺐는데
    # HTML 경로만 안 빼서 **같은 내용이 형식에 따라 다르게 판정됐다**(2026-09-07).
    # 제목 검사(09-02)·문단 검사(09-04)에 이어 세 번째로 같은 모양의 결함이다.
    #
    # ⛔ **맨 `<pre>` 는 빼지 않는다.** 처음에 `<pre>` 를 통째로 뺐다가 업무 칸반 한 장에서
    #    지적 44건이 사라지는 것을 보고 좁혔다 — 그 파일의 `<pre>` 33개는 코드가 아니라
    #    공백을 살리려고 감싼 한국어 기록이었다. HTML 에서 코드 의미를 지는 것은 `<code>`
    #    이고, 마크다운 코드펜스에 대응하는 것은 `<pre><code>` 다.
    #
    # 빈칸이 아니라 표시를 남긴다 — 값이 코드뿐인 칸이 사라지면 슬롯 수가 줄고,
    # 0이 되면 「값 슬롯 미인식」으로 넘어간다. 그건 못 본 것이 아니라 정당하게 뺀 것이다.
    body = re.sub(r'(<pre[^>]*>)\s*<code[^>]*>.*?</code>\s*(</pre>)', r'\1code\2',
                  body, flags=re.S | re.I)
    body = re.sub(r'(<code[^>]*>).*?(</code>)', r'\1code\2', body, flags=re.S | re.I)
    err, warn = [], []
    slots = 0

    # 1. 값·목록·표 칸의 서술형 종결
    for tag in ('dd', 'li', 'td'):
        for x in re.findall(rf'<{tag}[^>]*>(.*?)</{tag}>', body, re.S):
            t = strip(x)
            if not t:
                continue
            slots += 1
            if is_example(t):
                continue
            # 「굵은 결론 — 근거 문장」이면 결론만 본다(규칙 §1).
            # **목록 항목에만** 적용한다 — 표 칸(td)·값 칸(dd)은 그 자체가 값 슬롯이라 예외가 없다
            if tag == 'li':
                m = re.match(r'\s*<(b|strong)[^>]*>(.*?)</\1>(.*)$', x.strip(), re.S)
                if m and EVIDENCE_END.search(strip(m.group(3))):
                    t = strip(m.group(2))
            # 값 하나에 문장이 둘이면 끝 문장만 봐서는 앞 문장을 놓친다.
            # 마크다운 경로는 sentences()로 쪼개는데 여기만 안 쪼개고 있었다(2026-08-14 실측).
            # sentences()가 고유명 「」·인용 전체 예외도 함께 처리한다 — 두 경로를 맞춘다.
            for sent in sentences(t):
                if is_narrative(sent):
                    err.append(('서술형 종결', f'<{tag}> {sent[:58]}'))
            fe, fw = (None, None) if all_quoted(t) else fragment(drop_tail(t))
            if fe:
                err.append(('절단형 종결', f'{t[:40]} — {fe}'))
            elif fw:
                warn.append(('절단형 의심', f'{t[:40]} — {fw}'))

    # 1b. 실측 관례 — 라벨/값을 `class="k"` / `class="v…"` 로 쓴 아티팩트가 다수다
    #     (로컬 아티팩트 58개 중 값 슬롯 미인식 31개, 그중 24개가 이 관례)
    for x in re.findall(r'<[a-zA-Z]+[^>]*class="v(?:\s[^"]*)?"[^>]*>(.*?)</[a-zA-Z]+>', body, re.S):
        t = strip(x)
        if not t:
            continue
        slots += 1
        if is_example(t):
            continue
        for sent in sentences(t):
            if is_narrative(sent):
                err.append(('서술형 종결', f'class=v {sent[:58]}'))
        fe, fw = (None, None) if all_quoted(t) else fragment(drop_tail(t))
        if fe:
            err.append(('절단형 종결', f'{t[:40]} — {fe}'))
        elif fw:
            warn.append(('절단형 의심', f'{t[:40]} — {fw}'))
    for lab in re.findall(r'<[a-zA-Z]+[^>]*class="k(?:\s[^"]*)?"[^>]*>(.*?)</[a-zA-Z]+>', body, re.S):
        if strip(lab) in BAD_LABEL:
            warn.append(('스캔 가치 없는 라벨', strip(lab)))

    # 2. 지시어·평가 수식어 — 코드·인용 구간은 뺀다
    text = mask(strip(body))
    for w in VAGUE_HARD:
        for m in re.findall(r'[^·\n]{0,26}' + w + r'[^·\n]{0,20}', text):
            if is_example(m):
                continue
            err.append(('모호한 지칭', f'「{w}」 … {m.strip()[:58]}'))
    for w in VAGUE_SOFT:
        n = len(re.findall(w, text))
        if n:
            warn.append(('지시어 확인', f'「{w}」 {n}회 — 가리키는 대상이 하나로 읽히는지'))
    for w in SELF_PRAISE:
        for m in re.findall(r'[^·\n]{0,20}' + w + r'[^·\n]{0,22}', text):
            warn.append(('평가 수식어', f'「{w}」 … {m.strip()[:56]} — 무엇을 하는지로 바꿀 것'))
    for kind, level, fix, hit in translationese_hits(text):
        near = ' '.join(text[max(0, hit.start() - 20):hit.end() + 20].split())
        (err if level == 'err' else warn).append(
            (kind, f'「{hit.group(0)}」 — {fix} · {near[:48]}'))
    # 문맥 조각은 **한 줄로 눌러서** 낸다 — HTML 본문에는 줄바꿈이 섞여 있어
    # 그대로 두면 보고서가 여러 줄로 쪼개지고, 훅이 첫 줄만 걷어 가 정작
    # 문제 문장이 사라진다(오류는 뜨는데 어디인지 모르는 상태가 된다).
    def around(m):
        return ' '.join(text[max(0, m.start() - 24):m.end() + 8].split())
    for m in JARI.finditer(text):
        err.append(('「~하는 자리」', f'{around(m)[:56]} — 지점·위치·사례·단계·시점 중 맞는 말로'))
    for m in JARI_ANY.finditer(text):
        if JARI.search(m.group(0)) or JARI_OK.search(m.group(0)):
            continue
        warn.append(('「~하는 자리」 의심', f'{around(m)[:56]} — 사람이 모이는 뜻이 아니면 바꿀 것'))
    for m in EMPTY_NOUN.finditer(text):
        if EMPTY_NOUN_OK.search(m.group(0)):
            continue
        warn.append(('지어낸 명사구',
                     f'{around(m)[:56]} — 그 명사가 혼자 서나 · 아니면 문장을 서술로'))
    for m in HOEGI.finditer(text):
        span = text[max(0, m.start() - 6):m.end() + 6]
        if HOEGI_OK.search(span):
            continue
        err.append(('「회기」', f'{around(m)[:56]} — regression 이면 「회귀」 · '
                               '작업 단위면 「세션」·「회차」'))

    # 3. 금지 라벨
    for lab in re.findall(r'<dt[^>]*>(.*?)</dt>', body, re.S):
        if strip(lab) in BAD_LABEL:
            warn.append(('스캔 가치 없는 라벨', strip(lab)))

    # 4. 서술형 문단 — 마크다운과 같은 판정을 쓴다.
    #
    #   ⛔ 2026-09-04 이전에는 **길이만 봤다**(`len(t) > 90` → 주의). 이름은
    #      「서술형 문단」인데 서술형인지를 안 본 것이다. 그래서 두 방향으로 틀렸다.
    #
    #      ① **미탐** — 짧은 서술 문단을 통째로 놓쳤다. 같은 내용을 두 형식에 넣어
    #         재니 마크다운은 오류 2, HTML 은 **오류 0 · 주의 0** 이었다
    #         (「이 문서는 설계 전용이다.」·「표는 그 자체가 값 슬롯이라 …이 아니다.」).
    #      ② **오탐** — 「굵은 결론 — 근거 문장」이 길다는 이유로 걸렸다. 규칙이
    #         허용하는 형태인데 지적이 나서 다른 주의를 덮었다(실측 251건).
    #
    #   고친 뒤 실측(HTML 전수) — 주의 319 → 68 · 오류 29 → 195. 새 오류 166건은
    #   파일 넷에 몰려 있고 127건이 발표 대본이다(산문이라 `form: prose` 소관).
    #   나머지는 **내가 쓴 굵은 결론이 서술형**이었던 것 — 규칙대로 걸린 것이다.
    #
    #   `<p` 뒤에 글자가 오면 <pre>·<path> 같은 다른 태그다 — 문단만 본다.
    for p in re.findall(r'<p(?![a-zA-Z])(?![^>]*class="(?:lede|sub)")[^>]*>(.*?)</p>', body, re.S):
        t = strip(p)
        if not t or is_example(t):
            continue
        # 「굵은 결론 — 근거 문장」이면 결론만 본다(규칙 §1) — 목록 항목과 같은 처리다.
        m = re.match(r'\s*<(b|strong)[^>]*>(.*?)</\1>(.*)$', p.strip(), re.S)
        if m and EVIDENCE_END.search(strip(m.group(3))):
            t = strip(m.group(2))
        for sent in sentences(t):
            if is_narrative(sent):
                err.append(('서술형 문단', sent[:58]))

    # 4b. 제목 — 마크다운과 같은 규칙을 HTML 에도 건다.
    #     규칙(§1 개조식)은 진작 있었는데 이 경로에만 안 걸려 있었다. 그래서 값은
    #     전부 개조식인 아티팩트가 **제목만 서술 문장인 채로** 오류 0 을 받았다
    #     (2026-09-02 실측 — 검사기가 아니라 사람이 읽고서야 걸렸다).
    #     `<br>` 은 줄을 가른다 — 통째로 이어 붙이면 끝만 보게 되어 앞 줄의
    #     서술형이 빠진다: 「…잇는다<br>땅속 실그물」이 그 형태다.
    #     서술형 판정은 `is_narrative` 를 쓴다 — 위 값 슬롯과 같은 함수이고,
    #     인용 안 서술형을 값의 종결로 오인하지 않는다(「결론은 「…낮다」」).
    #     ★ 두 검사의 단위가 다르다. 서술형은 **줄마다**, 절단형·의문형은
    #     **제목 전체**를 놓고 본다. 명사구 하나가 두 줄로 접힌 것뿐인데 줄마다
    #     절단형을 재면 「흩어진 회사 자료를 잇는 / 땅속 실그물」의 앞 줄이
    #     조사 종결로 잡힌다. 거꾸로 서술형을 이어 붙여 재면 앞 줄이 통째로 빠진다.
    #     ★ `sentences`·`is_narrative` 에는 **꼬리를 떼기 전** 원문을 넘긴다.
    #     `drop_tail` 이 닫는 「」를 먼저 떼면 인용이 열린 채 남아 그 안의
    #     서술형이 제목의 종결이 된다 — 「「관찰한 사실은 LCT가 낸다」」가 그 형태다.
    for inner in re.findall(r'<h[1-6][^>]*>(.*?)</h[1-6]>', body, re.S):
        pieces = [x for x in (strip(p).replace('**', '')
                              for p in re.split(r'<br\s*/?>', inner)) if x]
        for piece in pieces:
            if is_example(piece):
                continue
            for sent in sentences(piece):
                if is_narrative(sent):
                    err.append(('제목 서술형', sent[:56]))
        whole = ' '.join(pieces)
        if not whole or is_example(whole) or all_quoted(whole):
            continue
        # 마크다운 경로와 **같은 글자로** 낸다 — 꼬리 괄호를 뗀 뒤의 제목을 보여
        # 준다. 안 맞추면 같은 제목의 같은 판정이 두 경로에서 다른 문장으로 나와
        # 대조가 안 된다(실측 대조에서 어긋난 23건이 전부 이 표기 차이였다).
        shown = drop_tail(whole)
        fe, fw = fragment(shown)
        if fe:
            err.append(('제목 명사형 위반', f'{shown[:50]} — {fe}'))
        elif fw and '의문형' in fw:
            err.append(('제목 명사형 위반', f'{shown[:50]} — {fw}'))
        elif fw:
            warn.append(('제목 형태 확인', f'{shown[:50]} — {fw}'))

    # 5. 진입점 — 있어야 하고, 그 한 줄도 개조식이어야 한다.
    #    `class="lede"` 를 요구하지 않는다 — 그러면 다른 템플릿의 진입점을 못 본다
    ledes = re.findall(r'<p[^>]*class="lede"[^>]*>(.*?)</p>', body, re.S)
    if '<h1' in body:
        if not ledes:
            after = body.split('</h1>', 1)[1] if '</h1>' in body else ''
            first = re.search(r'<p(?![a-zA-Z])[^>]*>(.*?)</p>', after, re.S)
            if not first or not strip(first.group(1)):
                err.append(('진입점 없음', '맨 앞에 「이 문서를 읽고 무엇을 하게 되나」 한 줄'))
            else:
                ledes = [first.group(1)]
    for lede in ledes:
        for chunk in re.split(r'(?<=\.)\s+', strip(lede)):
            c = chunk.strip()
            if c and NARRATIVE.search(c) and not NOT_NARRATIVE.search(c):
                err.append(('진입점 서술형', c[:58]))

    # 6. 반복 블록의 라벨 대조 — 같은 슬롯에 다른 말이 오는지
    cards = re.findall(r'<(?:article|section)[^>]*>(.*?)</(?:article|section)>', body, re.S)
    sets = [[strip(x) for x in re.findall(r'<dt[^>]*>(.*?)</dt>', c, re.S)] for c in cards]
    sets = [s for s in sets if s]
    if len(sets) >= 3:
        cnt = collections.Counter(x for s in sets for x in s)
        once = [k for k, v in cnt.items() if v == 1]
        if len(once) > len(sets) / 2:
            warn.append(('반복 블록 라벨 불일치',
                         f'{len(sets)}개 블록에서 1회용 라벨 {len(once)}종: {", ".join(once[:6])}'))
    # HTML 에는 머리말이 없다. 플래그만 받으면 **검사할 때마다 사람이 기억해야 하고**,
    # 기억해야 하는 구조는 실패한다 — `<meta name="form" content="prose">` 로 파일이
    # 자기 형식을 들고 있게 한다. 플래그가 오면 그쪽이 이긴다(그 자리에서 뒤집어 봄).
    err, warn = apply_form(err, warn, form or declared_form(raw))
    err, warn = apply_selection(err, warn, rules) if rules else (err, warn)
    return err, warn, slots


# ── Markdown ─────────────────────────────────────────────────────────────────
# 개조식을 전제하는 검사 — 산문 형식에서는 끈다. 나머지(절단형·모호한 지칭·
# 스캔 가치 없는 라벨·평가 수식어)는 형식과 무관하므로 그대로 돈다.
# 실측 근거: 산문 문서 73건에서 이 넷이 오류의 92%였고, 사용자가 쓴 안내 메일에서는
# 「안녕하세요 …입니다.」·「감사합니다.」까지 잡혀 아홉 건 전부 오탐이었다.
FORM_ONLY_STRUCTURED = {
    '서술형 종결', '제목 서술형', '제목 명사형 위반', '제목 형태 확인',
    '진입점 서술형', '진입점 명사형 위반', '진입점 없음',
    # 90자 넘는 문단은 **산문에서 정상이다**. 여기 빠져 있어 산문 HTML 에
    # `--form prose` 를 붙여도 같은 지적이 그대로 났다(2026-08-28 실측: 제품 소개
    # 한 장에서 주의 8건 중 7건). 붙였는데 아무것도 안 바뀌면 사람은 형식 선언이
    # 듣는 줄로 읽고 넘어간다.
    '서술형 문단',
}
FORM_VALUES = ('structured', 'prose')
# 따옴표는 YAML 도구가 자동으로 붙이기도 한다. 안 받아 주면 선언한 사람은
# 왜 계속 묻는지 모른 채 그대로 둔다.
FORM_KEY = re.compile(r'''^form\s*:\s*['"]?([A-Za-z_-]+)['"]?\s*$''', re.M)
# 형식을 안 적었는데 산문으로 보이면 한 줄로 물어본다. 임계는 실측으로 잡았다 —
# 0.15~0.30 구간은 표와 라벨이 뼈대인 문서에 근거 문단이 붙은 형태라 지적이 정당했다.
PROSE_ASK_THRESHOLD = 0.30
# 개조식 지적이 이만큼 넘게 쌓이고 그것이 지적의 절반 이상이면, 산문 비율이 낮아도
# 형식을 물어본다. 열 건 아래는 문서 하나에 몇 군데 고칠 곳이 있는 정상 상태다.
NARRATIVE_ASK_MIN = 10
_STRUCTURE_LINE = re.compile(r'^\s*(?:[-*+]\s|\d+[.)]\s|\||#{1,6}\s|>|```|:?-{3,})')
_SENTENCE_END = re.compile(r'[.!?。]\s*$')


HTML_FORM = re.compile(
    r'''<meta\s+name=["']form["']\s+content=["']([A-Za-z_-]+)["']''', re.I)


def declared_form(raw):
    """머리말의 `form:` 을 읽는다. 안 적었으면 None — 짐작하지 않는다.

    **HTML 은 머리말이 없어 플래그가 유일한 길이었다.** 그러면 검사할 때마다
    사람이 `--form prose` 를 기억해야 하고, 기억해야 하는 구조는 실패한다.
    `<meta name="form" content="prose">` 한 줄로 파일이 자기 형식을 들고 있게 한다.
    """
    m = HTML_FORM.search(raw[:4096])
    if m and m.group(1).lower() in FORM_VALUES:
        return m.group(1).lower()
    lines = raw.split('\n')
    if not lines or lines[0].strip() != '---':
        return None
    for j in range(1, min(len(lines), 60)):
        if lines[j].strip() == '---':
            m = FORM_KEY.search('\n'.join(lines[1:j]))
            return m.group(1).lower() if m and m.group(1).lower() in FORM_VALUES else None
    return None


def prose_share(body):
    """본문에서 흐르는 문장이 차지하는 비율. 형식을 정하는 값이 아니라 물어볼지 정하는 값이다."""
    real = [l for _, l in body if l.strip()]
    if not real:
        return 0.0
    flowing = [l for l in real
               if not _STRUCTURE_LINE.match(l) and _SENTENCE_END.search(l.strip())]
    return len(flowing) / len(real)


def apply_form(err, warn, form):
    """산문 형식이면 개조식 전제 검사를 뺀다. 형식은 선언으로만 정해진다."""
    if form != 'prose':
        return err, warn
    keep = lambda items: [(k, m) for k, m in items if k not in FORM_ONLY_STRUCTURED]
    return keep(err), keep(warn)


# ── 갈래 고르기 ───────────────────────────────────────────────────────────────
# 문서 관행은 조직마다 다르다. 표 머리 「비고」는 공문서 표준 관례이고, 발표 대본은
# 산문이 정상이다. 남이 이 검사기를 받아 쓰려면 갈래를 끄고 낮출 길이 있어야 한다.
#
# ⛔ **끈 것은 반드시 출력에 적는다.** 조용히 끄면 「오류 0」이 무엇을 뜻하는지 알 수
#    없어진다. 이 검사기가 자기에게서 배운 「검사 불가는 합격이 아니라 안 본 것」이
#    설정에도 그대로 걸린다 — 껐다는 사실이 안 보이면 안 본 것과 구별이 안 된다.
#
# 갈래 이름은 지적에 찍히는 이름 그대로다. `--list-rules` 로 전부 볼 수 있다.
RULE_GROUPS = {
    '문장': ('한국어 문장 자체가 어긋난 갈래', [
        '서술형 종결', '서술형 문단', '절단형 종결', '절단형 의심',
        '결론 라벨 없는 설명',
    ]),
    '낱말': ('낱말 선택 — 지어낸 말과 뜻이 흐려지는 말', [
        '「~하는 자리」', '「~하는 자리」 의심', '지어낸 명사구', '평가 수식어',
        '모호한 지칭', '지시어 확인', '「회기」',
    ]),
    '번역투': ('번역에서 옮아온 문형', [
        '이중 피동', '번역투 이중 조사', '번역투 그녀',
    ]),
    '구조': ('찾아 읽기가 안 되는 갈래 — 문장은 멀쩡하다', [
        '제목 서술형', '제목 명사형 위반', '제목 형태 확인',
        '진입점 없음', '진입점 서술형', '진입점 명사형 위반', '진입점 형태 확인',
        '스캔 가치 없는 라벨', '반복 블록 라벨 불일치', '해설을 인용으로',
    ]),
    '안내': ('지적이 아니라 물음 — 형식을 안 적은 문서에 한 줄', [
        '형식 미표기',
    ]),
}
ALL_KINDS = {k: g for g, (_, kinds) in RULE_GROUPS.items() for k in kinds}
RULES_FILENAME = 'korean-qa.toml'


class Selection:
    """어느 갈래를 볼 것인가. `source` 가 None 이면 전부 본다."""

    def __init__(self, off=(), warn=(), err=(), source=None):
        self.off, self.warn, self.err = set(off), set(warn), set(err)
        self.source = source

    def __bool__(self):
        return bool(self.off or self.warn or self.err)

    def summary(self):
        bits = []
        if self.off:
            bits.append(f'끔 {len(self.off)}종')
        if self.warn:
            bits.append(f'주의로 낮춤 {len(self.warn)}종')
        if self.err:
            bits.append(f'오류로 올림 {len(self.err)}종')
        return ' · '.join(bits)


def _expand(names, where):
    """묶음 이름을 갈래로 편다. 모르는 이름은 오타이므로 멈춘다."""
    out, unknown = set(), []
    for name in names:
        if name in RULE_GROUPS:
            out |= set(RULE_GROUPS[name][1])
        elif name in ALL_KINDS:
            out.add(name)
        else:
            unknown.append(name)
    if unknown:
        raise ValueError(f'{where} 에 모르는 이름: {" · ".join(unknown)}')
    return out


def load_rules(path):
    """설정 파일 하나를 읽어 Selection 을 낸다."""
    import tomllib
    data = tomllib.loads(io.open(path, encoding='utf-8').read())
    rules = data.get('rules', {})
    return Selection(
        off=_expand(rules.get('off', []), f'{path} 의 off'),
        warn=_expand(rules.get('warn', []), f'{path} 의 warn'),
        err=_expand(rules.get('err', []), f'{path} 의 err'),
        source=path,
    )


def find_rules(targets):
    """대상 경로에서 위로 올라가며 설정 파일을 찾는다. 없으면 None."""
    starts = []
    for t in targets:
        p = os.path.abspath(t)
        starts.append(p if os.path.isdir(p) else os.path.dirname(p))
    starts.append(os.getcwd())
    seen = set()
    for start in starts:
        cur = start
        while True:
            if cur in seen:
                break
            seen.add(cur)
            candidate = os.path.join(cur, RULES_FILENAME)
            if os.path.isfile(candidate):
                return candidate
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return None


def apply_selection(err, warn, sel):
    """끄고 · 낮추고 · 올린다. 순서는 끄기가 먼저다."""
    if not sel:
        return err, warn
    err = [i for i in err if i[0] not in sel.off]
    warn = [i for i in warn if i[0] not in sel.off]
    demoted = [i for i in err if i[0] in sel.warn]
    err = [i for i in err if i[0] not in sel.warn]
    promoted = [i for i in warn if i[0] in sel.err]
    warn = [i for i in warn if i[0] not in sel.err]
    return err + promoted, warn + demoted


def list_rules():
    """갈래 목록을 낸다 — 설정 파일에 적을 이름이 이것이다."""
    print(f'설정 파일 이름: {RULES_FILENAME} (검사 대상에서 위로 올라가며 찾는다)\n')
    for group, (why, kinds) in RULE_GROUPS.items():
        print(f'[{group}] {why}')
        for k in kinds:
            print(f'    {k}')
        print()
    print('보기 — 표 머리 「비고」를 쓰는 조직, 제목 형식은 자유로 두는 조직\n')
    print('    [rules]')
    print('    off  = ["스캔 가치 없는 라벨", "구조"]')
    print('    warn = ["절단형 의심"]')
    print('\n묶음 이름을 적으면 그 묶음의 갈래가 모두 걸린다.')


def md_body(raw):
    """(행번호, 원문) — frontmatter·코드펜스 제외. frontmatter는 메타데이터지 본문이 아니다."""
    lines = raw.split('\n')
    start = 0
    if lines and lines[0].strip() == '---':
        for j in range(1, min(len(lines), 60)):
            if lines[j].strip() == '---':
                start = j + 1
                break
    out, fence = [], False
    for n in range(start, len(lines)):
        s = lines[n].strip()
        if s.startswith('```'):
            fence = not fence
            continue
        if fence:
            continue
        out.append((n + 1, lines[n]))
    return out


def merge_wrapped(body):
    """줄바꿈으로 이어진 목록 항목을 한 줄로 합친다.

    「… 노션 본문에」 다음 줄에 「로컬 절대경로 금지.」가 오는 형태를 줄 단위로 보면
    앞줄이 절단형으로 오판된다(실측). 행번호는 항목 첫 줄을 유지한다."""
    out = []
    for n, line in body:
        s = line.strip()
        prev_is_item = bool(out) and bool(LIST_HEAD.match(out[-1][1].strip()))
        cont = (prev_is_item and s and line[:1] in ' \t'
                and not LIST_HEAD.match(s) and s[0] not in '|>#')
        if cont:
            pn, pl = out[-1]
            out[-1] = (pn, pl.rstrip() + ' ' + s)
        else:
            out.append((n, line))
    return out


def wrapped_lines(body):
    """다음 줄이 본문으로 이어지는 줄의 번호를 모은다.

    `merge_wrapped` 는 **들여쓴** 목록 이어짐만 합친다. 들여쓰지 않은 문단 줄바꿈은
    남아서, 문장 중간에서 끊긴 줄이 절단형 종결로 잡힌다 — 실측으로 절단형 지적
    97건 중 49건(51%)이 이 형태였다.

    **합치지 않고 표시만 한다.** 합쳐서 다시 판정하면 오탐은 사라지지만 합친 안쪽의
    진짜 절단형이 영영 안 나온다. 없앨 수 없는 미탐을 만드는 쪽이라, 지우는 대신
    등급을 「의심」으로 내려 사람이 보는 칸으로 옮긴다.
    """
    marked = set()
    for i, (n, _) in enumerate(body[:-1]):
        nxt = body[i + 1][1].strip()
        if nxt and not _STRUCTURE_LINE.match(nxt):
            marked.add(n)
    return marked


def md_blocks(body):
    """연속한 목록 줄을 한 묶음으로 모은다 — 묶음 상한·강조 밀도·라벨 대조의 단위."""
    blocks, cur = [], []
    for n, line in body:
        if LIST_HEAD.match(line.strip()):
            cur.append((n, line))
        else:
            if line.strip() == '' and cur:
                blocks.append(cur); cur = []
            elif line.strip() and cur:
                blocks.append(cur); cur = []
    if cur:
        blocks.append(cur)
    return blocks


def scan_md(path, relaxed=False, form=None, rules=None):
    raw = io.open(path, encoding='utf-8').read()
    body = merge_wrapped(md_body(raw))
    err, warn = [], []
    slots = 0

    # 진입점 줄은 7번이 따로 본다 — 여기서 또 세면 같은 곳이 두 번 나온다
    lede_n = None
    _h1 = next((i for i, (n, l) in enumerate(body) if l.strip().startswith('# ')), None)
    if _h1 is not None:
        for n, l in body[_h1 + 1:_h1 + 8]:
            if l.strip() and not l.strip().startswith('#'):
                lede_n = n
                break

    # 1. 값·목록·표 칸·본문 문단의 서술형 종결
    wrapped = wrapped_lines(body)
    prev_is_table = contrast_table = False
    for n, line in body:
        s = line.strip()
        if s.startswith('>'):        # 인용은 아래 「해설을 인용으로」에서 따로 본다
            continue
        is_table = s.startswith('|')
        # ❌/✅ 가 표 **머리**에만 있는 대조표 — 데이터 행이 곧 나쁜 예다. 표 단위로 뺀다
        if is_table and not prev_is_table:
            contrast_table = bool('❌' in s and '✅' in s)
        if not is_table:
            prev_is_table = False
        if is_example(s) or (is_table and contrast_table):
            prev_is_table = is_table
            continue
        if is_table:                 # 표 칸은 통째로 값이다 — 근거 문장이 올 자리가 아니다
            cells = [c.strip() for c in s.strip('|').split('|')]
            if set(''.join(cells)) <= set('-: '):
                prev_is_table = True
                continue
            parts, has_head = [[c.replace('**', '')] for c in cells], True
            # 표 머리의 금지 라벨
            if not prev_is_table:
                bad = [c.strip() for c in cells if c.replace('**', '').strip() in BAD_LABEL]
                if bad:
                    warn.append((n, '스캔 가치 없는 라벨',
                                 '표 머리 ' + ' · '.join(f'「{b}」' for b in bad)))
        elif LIST_HEAD.match(s):
            vals, has_head = split_value(LIST_HEAD.sub('', s, count=1))
            parts = [vals]
        elif CONCL_HEAD.match(s):
            vals, has_head = split_value(CONCL_HEAD.sub('', s, count=1))
            parts = [vals]
        elif s.startswith('#') or PARA_SKIP.match(s) or n == lede_n:
            # 제목은 아래 제목 검사, 진입점은 7번이 따로 본다.
            # 구분선·이미지·독립 링크는 값이 없는 줄이라 뺀다
            continue
        else:
            # 본문 문단도 값 슬롯이다 — 표·목록만 보면 규칙이 반만 적용된다.
            # 규칙 §형식 「왜·의도·근거는 문장 — 단 결론을 라벨 한 줄로 먼저」.
            # split_value가 그 구조를 이미 안다: 굵은 결론이 있으면 결론만 보고,
            # 뒤 근거 문장은 그대로 둔다. 결론이 없으면 문단 전체가 라벨 없는 설명이다.
            vals, has_head = split_value(s)
            parts = [vals]
        prev_is_table = s.startswith('|')
        for cell in parts:
            for v in cell:
                slots += 1
                fe, fw = (None, None) if all_quoted(v) else fragment(drop_tail(strip(v).replace('**', '')))
                if fe and n in wrapped:
                    # 다음 줄로 이어지는 문단이라 잘린 것인지 문장이 계속되는 것인지
                    # 줄만 봐서는 안 갈린다. **빼지 않고** 사람이 보는 칸으로 내린다.
                    warn.append((n, '절단형 의심',
                                 f'{v.strip()[:38]} — 다음 줄로 이어지는 문단이다 · '
                                 '문장이 계속되면 정상, 아니면 서술어가 빠진 것'))
                elif fe:
                    err.append((n, '절단형 종결', f'{v.strip()[:38]} — {fe}'))
                elif fw:
                    warn.append((n, '절단형 의심', f'{v.strip()[:38]} — {fw}'))
                for t in sentences(v):
                    if is_narrative(t):
                        # 머리 없이 마침표로 끝나는 항목 = 결론 라벨이 빠진 설명 문장.
                        # 규칙 §형식 「왜·근거는 문장 — 단 결론을 라벨 한 줄로 먼저」 위반이다.
                        bare = (not has_head) and EVIDENCE_END.search(t.strip())
                        msg = f'{t[:56]}'
                        if bare and relaxed:
                            warn.append((n, '결론 라벨 없는 설명', msg + ' — 결론을 라벨로 앞에'))
                        elif bare:
                            err.append((n, '서술형 종결', msg + ' — 결론 라벨을 앞에 두거나 개조식으로'))
                        else:
                            err.append((n, '서술형 종결', msg))

    # 2. 모호한 지칭 / 평가 수식어 — 코드·인용 구간과 대조 예시 줄은 뺀다
    for n, line in body:
        s = line.strip()
        if s.startswith('>') or is_example(s):
            continue
        m = mask(line)
        for w in VAGUE_HARD:
            if w in m:
                err.append((n, '모호한 지칭', f'「{w}」 — {strip(line).strip()[:52]}'))
        for w in SELF_PRAISE:
            if w in m:
                warn.append((n, '평가 수식어', f'「{w}」 — {strip(line).strip()[:50]}'))
        for h in HOEGI.finditer(m):
            if HOEGI_OK.search(m[max(0, h.start() - 6):h.end() + 6]):
                continue
            err.append((n, '「회기」',
                        f'regression 이면 「회귀」 · 작업 단위면 「세션」·「회차」 — '
                        f'{strip(line).strip()[:40]}'))
        j = JARI.search(m)
        if j:
            err.append((n, '「~하는 자리」',
                        f'「{j.group(0)}」 — {strip(line).strip()[:44]}'))
        else:
            for q in JARI_ANY.finditer(m):
                if JARI_OK.search(q.group(0)):
                    continue
                warn.append((n, '「~하는 자리」 의심',
                             f'「{q.group(0)}」 — {strip(line).strip()[:42]}'))
        for e in EMPTY_NOUN.finditer(m):
            if EMPTY_NOUN_OK.search(e.group(0)):
                continue
            warn.append((n, '지어낸 명사구',
                         f'「{e.group(0)}」 — 그 명사가 혼자 서나 · '
                         f'{strip(line).strip()[:36]}'))
        for kind, level, fix, hit in translationese_hits(m):
            note = f'「{hit.group(0)}」 — {fix} · {strip(line).strip()[:40]}'
            (err if level == 'err' else warn).append((n, kind, note))

    # 3. 금지 라벨 (목록의 「라벨: 값」)
    for n, line in body:
        m = LABEL_COLON.match(line.strip().lstrip('-*').strip())
        if m and m.group(1).strip() in BAD_LABEL:
            warn.append((n, '스캔 가치 없는 라벨', f'「{m.group(1).strip()}」'))

    # 4. 반복 블록의 라벨 대조 — 같은 슬롯에 다른 말이 오는지
    label_sets = []
    for blk in md_blocks(body):
        labels = []
        for n, line in blk:
            if is_example(line):
                continue
            lm = LABEL_COLON.match(LIST_HEAD.sub('', line.strip(), count=1))
            if lm:
                labels.append(lm.group(1).strip())
        if len(labels) >= 2:
            label_sets.append(labels)
    if len(label_sets) >= 3:
        cnt = collections.Counter(x for s in label_sets for x in s)
        once = [k for k, v in cnt.items() if v == 1]
        if len(once) > len(label_sets) / 2:
            warn.append((0, '반복 블록 라벨 불일치',
                         f'{len(label_sets)}개 묶음에서 1회용 라벨 {len(once)}종: {", ".join(once[:6])}'))

    # 5. 제목·진입점 — 둘 다 명사형이어야 한다
    for n, line in body:
        hm = MD_HEADING.match(line.strip())
        if not hm:
            continue
        # ★ 꼬리를 떼기 **전** 원문을 sentences·is_narrative 에 넘긴다.
        # drop_tail 이 닫는 「」를 먼저 떼면 인용이 열린 채 남아 그 안의 서술형이
        # 제목의 종결이 된다 — 「「관찰한 사실은 LCT가 낸다」」가 오류로 났다
        # (2026-09-02 실측). 고유명 제목은 규칙상 개조식으로 고칠 수 없다.
        # HTML 경로(4b)와 같은 순서다 — 두 경로를 맞춘다.
        raw_title = strip(hm.group(1)).replace('**', '')
        for t in sentences(raw_title):
            if is_narrative(t):
                err.append((n, '제목 서술형', t[:56]))
        if not raw_title or all_quoted(raw_title):
            continue
        title = drop_tail(raw_title)
        fe, fw = fragment(title)
        if fe:
            err.append((n, '제목 명사형 위반', f'{title[:50]} — {fe}'))
        elif fw and '의문형' in fw:
            err.append((n, '제목 명사형 위반', f'{title[:50]} — {fw}'))
        elif fw:
            warn.append((n, '제목 형태 확인', f'{title[:50]} — {fw}'))

    h1 = next((i for i, (n, l) in enumerate(body) if l.strip().startswith('# ')), None)
    if h1 is not None:
        lede = None
        for n, l in body[h1 + 1:h1 + 8]:
            s = l.strip()
            if not s or s.startswith('#'):
                continue
            lede = (n, s); break
        if lede is None:
            err.append((0, '진입점 없음', '맨 앞에 「이 문서를 읽고 무엇을 하게 되나」 한 줄'))
        else:
            n, s = lede
            t = drop_tail(strip(LIST_HEAD.sub('', s, count=1).replace('**', '')))
            vals, _ = split_value(t)
            for v in vals:
                fe, fw = (None, None) if all_quoted(v) else fragment(drop_tail(v))
                if fe:
                    err.append((n, '진입점 명사형 위반', f'{v[:48]} — {fe}'))
                elif fw and '의문형' in fw:
                    err.append((n, '진입점 명사형 위반', f'{v[:48]} — {fw}'))
                elif fw:
                    warn.append((n, '진입점 형태 확인', f'{v[:48]} — {fw}'))
            if not is_example(s) and NARRATIVE.search(t) and not NOT_NARRATIVE.search(t):
                err.append((n, '진입점 서술형', t[:56]))

    # 6. 출처 없는 인용 블록 = 해설이다. 인용 부호만 썼을 뿐 값과 같은 규칙을 받는다
    lines = raw.split('\n')
    i = 0
    while i < len(lines):
        if not lines[i].strip().startswith('>'):
            i += 1; continue
        start, blk = i, []
        while i < len(lines) and lines[i].strip().startswith('>'):
            blk.append(lines[i].strip().lstrip('>').strip()); i += 1
        if start < HEAD_LINES or ATTRIB.search(' '.join(blk)):
            continue
        for k, b in enumerate(blk):
            for chunk in re.split(r'(?<=다\.)\s+', b):
                c = strip(chunk).replace('**', '').strip()
                if c and NARRATIVE.search(c) and not NOT_NARRATIVE.search(c):
                    warn.append((start + k + 1, '해설을 인용으로', f'{c[:52]} — 라벨:값으로'))

    # 한 줄에서 같은 종류가 여러 번 나오면 한 건으로 센다 — 건수가 고칠 곳 수와 어긋나지 않게
    def dedupe(items):
        seen, out = set(), []
        for n, kind, msg in items:
            if (n, kind) in seen:
                continue
            seen.add((n, kind))
            out.append((kind, f'{n}행  {msg}' if n else msg))
        return out

    err, warn = dedupe(err), dedupe(warn)

    # 형식은 선언으로만 정한다. 산문 비율로 짐작하면 표와 라벨이 뼈대인 문서까지
    # 산문으로 넘어가 정당한 지적이 조용히 사라진다(실측 65건이 그 구간이다).
    #
    # 물어보는 조건은 둘이다. 산문 비율 하나로는 **물음이 필요한 문서를 놓친다** —
    # 표와 목록이 뼈대이고 그 안의 설명만 산문인 문서는 비율이 낮게 나오는데,
    # 정작 개조식 지적이 쏟아지는 것이 그런 문서다(실측 41건 · 문서의 10%).
    # 그래서 **지적 자체가 개조식 축으로 쏠렸는지**도 함께 본다.
    narrative = sum(1 for item in err if (item[1] if len(item) == 3 else item[0]) == '서술형 종결')
    form_axis_flood = narrative >= NARRATIVE_ASK_MIN and narrative >= 0.5 * max(len(err), 1)
    resolved = form or declared_form(raw)
    if resolved is None and (prose_share(body) >= PROSE_ASK_THRESHOLD or form_axis_flood):
        warn.append((
            '형식 미표기',
            '산문으로 보이는데 형식을 안 적었다 — 머리말에 `form: prose` 를 적으면 '
            '개조식 검사를 빼고 본다. 개조식이 맞다면 `form: structured`',
        ))
    err, warn = apply_form(err, warn, resolved)
    err, warn = apply_selection(err, warn, rules) if rules else (err, warn)
    return err, warn, slots


def main():
    argv = sys.argv[1:]
    if '--list-rules' in argv:
        list_rules(); return 0
    form, rules_path, taken = None, None, set()
    for i, a in enumerate(argv):
        if a == '--form' and i + 1 < len(argv):
            form = argv[i + 1].lower()
            taken.add(i + 1)          # 값이 파일 이름으로 새지 않게 뒤로 뺀다
        elif a.startswith('--form='):
            form = a.split('=', 1)[1].lower()
        elif a == '--rules' and i + 1 < len(argv):
            rules_path = argv[i + 1]
            taken.add(i + 1)
        elif a.startswith('--rules='):
            rules_path = a.split('=', 1)[1]
    if form is not None and form not in FORM_VALUES:
        print(f'--form 은 {" 또는 ".join(FORM_VALUES)} 만 받는다'); return 1
    # **모르는 플래그는 멈춘다.** 조용히 무시하면 `--relaxd` 처럼 한 글자 틀렸을 때
    # **끄려던 검사가 안 꺼진 채 통과로 읽힌다** — 사람은 껐다고 알고 있다.
    known = {'--html-only', '--relaxed', '-v', '--form',
             '--rules', '--no-rules', '--list-rules'}
    for i, a in enumerate(argv):
        if not a.startswith('-') or i in taken:
            continue
        if a in known or a.startswith('--form=') or a.startswith('--rules='):
            continue
        print(f'모르는 플래그 {a} — 쓸 수 있는 것: '
              f'{" · ".join(sorted(known))} · --form <structured|prose>')
        return 1

    args = [a for i, a in enumerate(argv) if not a.startswith('-') and i not in taken]
    html_only = '--html-only' in argv
    relaxed = '--relaxed' in argv
    verbose = '-v' in argv
    if not args:
        print(__doc__); return 1

    files = []
    for a in args:
        if os.path.isdir(a):
            files += glob.glob(os.path.join(a, '**', '*.html'), recursive=True)
            if not html_only:
                files += glob.glob(os.path.join(a, '**', '*.md'), recursive=True)
        else:
            files.append(a)

    # 갈래 설정 — 명시한 것이 먼저, 없으면 대상에서 위로 올라가며 찾는다.
    # `--no-rules` 는 발행 게이트용이다. 설정이 무엇을 끄든 전부 보게 한다.
    rules = None
    if '--no-rules' not in argv:
        found = rules_path or find_rules(args)
        if found:
            try:
                rules = load_rules(found)
            except (ValueError, OSError) as exc:
                print(f'갈래 설정을 못 읽었다 — {exc}'); return 1
            except ModuleNotFoundError:
                print('갈래 설정에는 Python 3.11 이상이 필요하다(tomllib)'); return 1
    elif rules_path:
        print('--rules 와 --no-rules 를 같이 줄 수 없다'); return 1

    # ⛔ 껐다는 사실이 안 보이면 「오류 0」이 무엇을 뜻하는지 알 수 없다.
    if rules:
        print(f'갈래 설정 {rules.source} — {rules.summary()}')
        for kind in sorted(rules.off):
            print(f'   ⊘ {kind} — 끔')
        for kind in sorted(rules.warn):
            print(f'   ↓ {kind} — 오류에서 주의로')
        for kind in sorted(rules.err):
            print(f'   ↑ {kind} — 주의에서 오류로')
        print()

    total_e = total_w = total_blind = 0
    for f in sorted(files):
        scan = scan_md if f.endswith('.md') else scan_html
        e, w, slots = scan(f, relaxed, form, rules)
        total_e += len(e); total_w += len(w)
        name = os.path.basename(f)
        if slots:
            if not e and not w:
                print(f'✅ {name}  (값 슬롯 {slots})'); continue
            head = f'\n── {name}  오류 {len(e)} · 주의 {len(w)}  (값 슬롯 {slots})'
        else:
            # 값 슬롯이 0이어도 지시어·진입점 검사는 돈다 — 그 결과를 숨기지 않는다
            total_blind += 1
            why = ''
            if not f.endswith('.md'):
                raw = io.open(f, encoding='utf-8', errors='ignore').read()
                if sum(len(m) for m in re.findall(r'<script.*?</script>', raw, re.S)) > 20000:
                    why = ' · JS 렌더로 보임(정적 검사의 한계 — 렌더된 화면으로 확인할 것)'
            head = f'\n⛔ {name} — 값 슬롯 미인식, 부분 검사만 됨. 합격이 아니다{why}'
            if not e and not w:
                print(head.lstrip('\n')); continue
        print(head)
        for kind, msg in e:
            print(f'   ❌ [{kind}] {msg}')
        for kind, msg in (w if verbose else w[:8]):
            print(f'   ⚠️  [{kind}] {msg}')
        if not verbose and len(w) > 8:
            print(f'   … 주의 {len(w)-8}건 더 (-v)')

    tail = f' · 검사 불가 {total_blind}' if total_blind else ''
    # 합계만 잘라 보는 사람이 많다. 설정으로 줄어든 수라는 것을 여기서도 적는다.
    if rules:
        tail += f' · 갈래 설정 적용({rules.summary()})'
    print(f'\n합계 — 오류 {total_e} · 주의 {total_w}{tail}')
    return 1 if total_e else 0


if __name__ == '__main__':
    sys.exit(main())
