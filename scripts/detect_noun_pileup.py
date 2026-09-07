"""「명사로 굳힌 서술」 탐지 실험 — **채택되지 않은 규칙**이다. 근거를 재현하려고 남긴다.

    python -X utf8 scripts/detect_noun_pileup.py --sweep
    python -X utf8 scripts/detect_noun_pileup.py --list 6 3

**왜 만들었나.** 전수 판정에서 참 문제 4건인데 1층이 0건 잡았다(`runs/eval-005`).
불필요한 영어와 달리 모양이 구조적이라 — 조사 없이 이어진 명사 덩어리 — 셀 수 있을
것 같았다.

**왜 안 넣었나.** 개조식 라벨이 곧 명사 나열이다. 「버그 수정 반영 확인」은 정상
값이고 「로컬 실행 환경 구축 기능 추가」는 잘못인데 **표면이 같다.** 느슨하게 잡으면
정밀도 15%, 좁히면 55%에 회수 1/3이다. 판정은 `runs/diagnostic-009`.

**지우지 않는 이유** — 다음에 같은 생각이 들 때 다시 만들지 않게 한다. 임계를 바꿔
보려면 여기서 바로 돌려 보면 된다.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HANGUL = re.compile(r"[가-힣]")
SKIP = re.compile(r"node_modules|[\\/]\.git[\\/]|scratchpad|__pycache__", re.I)
STRUCT = re.compile(r'^\s*(?:```|\||>|:?-{3,})')
CODE = re.compile(r'`[^`]*`')

# 조사·어미로 끝나면 관계가 살아 있다 — 덩어리가 거기서 끊긴다
PARTICLE_END = re.compile(
    r'(?:은|는|이|가|을|를|에|의|와|과|도|만|랑|나|든|든지|에서|에게|한테|께|보다'
    r'|으로|로|로서|로써|부터|까지|처럼|같이|마다|조차|밖에|뿐|이나|거나)$')
VERB_END = re.compile(
    r'(?:다|음|함|됨|임|한다|된다|이다|하는|되는|한|된|할|될|해|돼|하고|되고'
    r'|하며|되며|하여|되어|했다|됐다|하지|되지|시|중|후|전|뒤|간|내|외|별|당|용)$')

# 「하다」가 붙는 행위 명사 — 이 낱말이 곧 서술어였던 것이다
ACTION_NOUN = {
    '구축', '추가', '개선', '확장', '도입', '적용', '수행', '처리', '검증', '개발',
    '구현', '배포', '관리', '운영', '분석', '설계', '측정', '정리', '제거', '삭제',
    '생성', '변경', '수정', '갱신', '등록', '조회', '검색', '저장', '전송', '수집',
    '압축', '복구', '이관', '전환', '통합', '분리', '연동', '지원', '제공', '확인',
    '점검', '발표', '공유', '보고', '승인', '요청', '대응', '마련', '준비', '완료',
    '시작', '종료', '중단', '재개', '고도화', '최적화', '자동화', '표준화', '정규화',
    '활성화', '모니터링', '리셋', '조절', '유실', '누락', '개편', '재정립', '실행',
    '호출', '반영', '산출', '취합', '판정', '선정', '협의', '조사', '학습', '평가',
    '배치', '설정', '초기화', '동기화', '전파', '차단', '해제', '복원', '분류',
}

CORPUS_ROOTS = (Path("<설정 저장소>/reports"),
                Path("P:/github/korean-writing-qa/docs"))

# 사용자 판정으로 확인된 참 문제 — 규칙이 이것을 잡는지가 첫 관문
TRUE_CASES = [
    "로컬 실행 환경 구축 기능 추가",
    "컨텍스트 압축 및 세션 리셋 주기적 수행",
    "플랫폼 기능 고도화 발표",
]
# 정상 한국어 — 잡으면 안 된다
CLEAN_CASES = [
    "새 세션 진입 시 첫 메시지",
    "사용자 컨펌 게이트 장기 프로세스 디시플린",
    "기능 추가",
    "회의실 예약 자동화",
    "개발 재개",
    "검색 통합",
    "스킬 제거 완료",
    "갱신 여부 확인",
    "전역 등록 제거",
    "설정 도입",
]


def noun_runs(line: str):
    """조사·어미 없이 이어진 한글 토큰 덩어리를 낸다."""
    line = CODE.sub(' ', line)
    line = re.sub(r'^\s*(?:[-*+]|\d+[.)])\s+', '', line)
    line = re.sub(r'^#{1,6}\s+', '', line).replace('**', '')
    run = []
    for token in line.split():
        core = token.strip('·,()[]{}「」『』"\'—–:;')
        if (core and HANGUL.search(core)
                and not PARTICLE_END.search(core)
                and not VERB_END.search(core)
                and not re.search(r'[.!?]$', token)):
            run.append(core)
            continue
        if run:
            yield run
        run = []
    if run:
        yield run


def fires(text: str, min_len: int, min_act: int):
    for run in noun_runs(text):
        if len(run) >= min_len and sum(1 for t in run if t in ACTION_NOUN) >= min_act:
            return ' '.join(run)
    return None


def corpus_lines():
    for root in CORPUS_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if SKIP.search(str(path)):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if len(HANGUL.findall(text)) < 300:
                continue
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not STRUCT.match(stripped):
                    yield path.name, stripped


def sweep(lines):
    print(f"{'덩어리':>6}{'행위':>5}{'참 3건':>8}{'정상 오탐':>10}{'실문서':>9}")
    print("-" * 40)
    for min_len in (3, 4, 5, 6):
        for min_act in (2, 3):
            yes = sum(1 for t in TRUE_CASES if fires(t, min_len, min_act))
            no = sum(1 for t in CLEAN_CASES if fires(t, min_len, min_act))
            n = sum(1 for _, s in lines if fires(s, min_len, min_act))
            print(f"{min_len:>6}{min_act:>5}{yes:>8}{no:>10}{n:>9}")
    print("\n판정 — 어느 임계도 못 씀. 근거는 runs/diagnostic-009")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", action="store_true", help="임계 조합을 훑는다")
    parser.add_argument("--list", nargs=2, type=int, metavar=("덩어리", "행위"),
                        help="그 임계에서 걸린 것을 전수로 찍는다")
    args = parser.parse_args()
    if not (args.sweep or args.list):
        parser.error("--sweep 또는 --list 가 필요합니다")

    lines = list(corpus_lines())
    print(f"문서 뭉치 {len(lines):,}줄\n")
    if args.sweep:
        sweep(lines)
    if args.list:
        min_len, min_act = args.list
        hits = [(name, fires(s, min_len, min_act)) for name, s in lines]
        hits = [(n, h) for n, h in hits if h]
        print(f"덩어리 {min_len} · 행위 {min_act} · {len(hits)}건")
        for name, hit in hits:
            print(f"   {hit[:78]}")


if __name__ == "__main__":
    main()
