# Korean Business Writing QA
## 회사 업무·공식 자료용 자연스러운 한국어 품질 검사기 설계 문서

> **⚠️ 2026-08-24에 멈춘 창립 문서 · 현재 상태 아님** — 지금 무엇이 도는지는 [현재 상태](status.md), 남은 판단은 [판단이 필요한 것](decisions-pending.md)
>
> **여기 적힌 것과 실제가 갈린 곳** — 「`~라는 점`」은 검토 뒤 미채택 · 「`~하는 자리`」는 채택돼 도는 중 · 검사기가 보는 원칙은 열한 개 중 셋
>
> 목적: 이 문서는 이후 Codex 세션에서 설계와 구현을 바로 이어가기 위한 인수인계 문서다.  
> 핵심 목표는 "AI가 쓴 글을 탐지"하는 것이 아니라, 회사 업무 및 공식 자료에서 어색한 한국어 표현을 찾아 자연스럽고 정확한 업무 한국어로 고치는 것이다.

---

# 1. 프로젝트 배경

최근 Claude, GPT 등 LLM이 작성한 한국어 문서에서 다음과 같은 표현이 반복적으로 나타난다.

- `~하는 자리`
- `~라는 점`
- `이를 통해`
- `단순히 A를 넘어 B`
- `의미 있는`
- `중요한 역할을 한다`
- `기반을 마련한다`
- `가능성을 보여준다`
- `문제 해결의 입구`
- `~하는 과정`
- `~하는 측면`
- `이러한 맥락에서`
- `~할 수 있을 것으로 판단됩니다`

이 표현들의 문제는 대부분 문법 오류가 아니라는 점이다.

예:

```text
이번 회의는 향후 방향을 함께 논의하는 자리가 될 것입니다.
```

문법적으로는 맞지만 실제 회사 업무에서는 다음이 더 자연스럽다.

```text
이번 회의에서 향후 방향을 논의합니다.
```

또는:

```text
이 질문은 문제를 이해하는 좋은 입구가 됩니다.
```

보다:

```text
이 질문부터 살펴보면 좋겠습니다.
```

또는:

```text
이 질문이 좋은 출발점입니다.
```

가 일반적인 업무 한국어에 가깝다.

따라서 본 프로젝트는 맞춤법 검사기나 AI 생성 탐지기가 아니라 **업무 한국어의 문체 품질 검사기**를 목표로 한다.

---

# 2. 프로젝트 목표

## 2.1 최종 목표

회사에서 작성하거나 외부에 배포하는 문서를 대상으로 다음 문제를 탐지하고 최소 수정한다.

1. 불필요한 추상화
2. 어색한 은유
3. 번역투
4. 과도한 명사화
5. AI 상투어
6. 홍보문·공공기관식 과장 표현
7. 과도한 완곡어
8. 메타 서술
9. 접속어 남용
10. 불필요한 3단 나열
11. 문서 목적에 맞지 않는 격식
12. 모호한 지시 표현
13. 중복 표현
14. 문장 전체의 인위적인 완결성
15. 회사 업무 문체와 맞지 않는 의례 표현

---

# 3. 이 프로젝트가 하지 않는 것

다음은 프로젝트의 1차 목적이 아니다.

## 3.1 AI 생성 탐지

다음과 같은 기능은 목표가 아니다.

```text
이 글은 AI가 작성했을 확률 87%
```

AI가 작성했는지는 중요하지 않다.

사람이 작성했더라도 어색하면 고쳐야 하고,
AI가 작성했더라도 자연스러우면 그대로 두면 된다.

---

## 3.2 전체 문서 재작성

LLM에게 다음과 같이 요청하지 않는다.

```text
이 문서를 사람처럼 자연스럽게 다시 써라.
```

이 방식은 다음 위험이 있다.

- 사실 변경
- 기술 용어 변경
- 의미 손실
- 새로운 주장 추가
- 불필요한 문체 변화
- 문서 전체의 표현 변동

본 프로젝트는 기본적으로:

```text
Detect
→ Judge
→ Minimal Fix
→ Recheck
```

방식을 따른다.

---

## 3.3 범용 맞춤법 검사기

맞춤법·띄어쓰기 기능을 나중에 포함할 수는 있지만,
프로젝트의 핵심 차별점은 맞춤법이 아니다.

핵심은:

> 문법적으로 맞지만 실제 업무 한국어에서는 부자연스러운 표현

을 탐지하는 것이다.

---

# 4. 제품 개념

가칭:

```text
Korean Business Writing QA
```

또는:

```text
Korean Writing QA
Korean Prose Lint
Business Korean Linter
Korean Style Check
```

`AI Humanizer`라는 이름은 가급적 피한다.

이유:

- AI 탐지 또는 AI 우회 도구처럼 보일 수 있음
- 모델이 전체 문서를 과도하게 재작성하게 만들기 쉬움
- 사람이 작성한 문서도 검사 대상이라는 목적과 맞지 않음

제품의 본질은:

> 회사의 문서 품질 기준을 코드와 규칙으로 관리하고 자동 검사하는 시스템

이다.

---

# 5. 가장 중요한 설계 원칙

## 5.1 전역 프롬프트에 모든 규칙을 넣지 않는다

잘못된 접근:

```text
CLAUDE.md / AGENTS.md / system prompt에
100~300개의 한국어 문체 규칙을 모두 넣는다.
```

문제:

- context 낭비
- 규칙 누락
- 모델이 일부만 기억
- 작성 품질 저하
- 생성할 때 지나치게 자기검열
- 유지보수 어려움
- 규칙 변경 시 전역 프롬프트 수정 필요

대신 전역에는 **언제 검사할지만** 기록한다.

예:

```text
외부 공개, 고객 전달, 정식 배포 문서를 최종화할 때
Korean Writing QA를 실행한다.
```

---

## 5.2 생성과 검수를 분리한다

권장 흐름:

```text
초안 작성
↓
내용 수정
↓
사람 또는 AI 검토
↓
배포/최종화 요청
↓
Korean Writing QA
↓
필요한 문장만 수정
↓
재검사
↓
최종 산출
```

LLM이 처음부터 수십 개 문체 규칙을 생각하며 글을 쓰게 하지 않는다.

---

## 5.3 규칙은 Prompt가 아니라 Data로 관리한다

규칙은 YAML/JSON 등의 독립 파일로 관리한다.

예:

```yaml
id: KOR-ABSTRACT-001
name: abstract-jari
category: abstract_event_container
severity: warning
fix_mode: contextual

patterns:
  - "논의하는 자리"
  - "공유하는 자리"
  - "소통하는 자리"

description: >
  실제 장소나 행사 자체를 의미하지 않으면서
  동작을 '자리'로 명사화하는 표현.

preferred:
  - 동사를 직접 사용한다.
  - 의미가 같으면 '자리'를 삭제한다.

examples:
  - before: "향후 방향을 논의하는 자리입니다."
    after: "향후 방향을 논의합니다."

exceptions:
  - 실제 좌석 또는 위치
  - 일자리
  - 실제 행사 자체를 지칭하는 경우
  - 축사/기념행사 등 의례 문체
```

핵심:

> 모든 규칙을 매번 LLM에게 보내지 않는다.

검사기가 먼저 후보를 찾고,
해당 후보와 관련된 규칙만 LLM에게 전달한다.

---

# 6. 권장 시스템 구조

```text
                ┌─────────────────────┐
                │      Document       │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Candidate Detector  │
                │ regex / string /    │
                │ POS / statistics    │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │   Rule Matching     │
                │ Candidate → Rule ID │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Contextual Judge    │
                │ LLM                 │
                │ FIX / KEEP / REVIEW │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │   Minimal Fixer     │
                │ target only         │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │      Re-lint        │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Final Document / QA │
                └─────────────────────┘
```

---

# 7. 3단계 검사 모델

## 7.1 Layer 1 — Deterministic Linter

기계적으로 찾기 쉬운 표현.

예:

```text
~하는 자리
~라는 점
이를 통해
이러한 맥락에서
단순히 ~를 넘어
중요한 역할을 한다
기반을 마련한다
가능성을 보여준다
```

수단:

- 문자열 검색
- Regex
- 형태소 분석
- 문장 단위 통계
- 특정 표현 빈도

목표:

> 수정하는 것이 아니라 후보를 찾는 것

---

## 7.2 Layer 2 — Contextual LLM Judge

후보 표현이 실제로 문제인지 문맥을 판단한다.

예:

```text
"자리"가 물리적 장소, 좌석, 직위 또는
행사 자체를 의미하는가?

아니면 "~한다"로 직접 쓸 수 있는데
불필요하게 명사화한 표현인가?
```

출력 예:

```json
{
  "decision": "FIX",
  "confidence": 0.94,
  "reason": "자리 자체가 의미를 추가하지 않으며 동사로 직접 표현 가능"
}
```

가능한 decision:

```text
FIX
KEEP
REVIEW
```

---

## 7.3 Layer 3 — Minimal Rewrite

전체 문서를 재작성하지 않는다.

문제가 발견된 최소 범위만 보낸다.

예:

```text
Previous sentence:
...

Target:
이번 세미나는 향후 기술 방향을 논의하는 자리입니다.

Next sentence:
...

Rule:
KOR-ABSTRACT-001

Instruction:
의미와 사실을 변경하지 말고 이 finding만 해결하라.
수정할 필요가 없으면 KEEP을 반환하라.
```

---

# 8. 규칙 Taxonomy

단어별 규칙보다 **언어 현상별 규칙**이 중요하다.

---

## 8.1 ABSTRACT_EVENT_CONTAINER

동사나 사건을 추상 명사 안에 넣는 표현.

후보:

```text
자리
장
공간
기회
계기
과정
기반
토대
```

예:

```text
의견을 공유하는 자리
소통의 장
경험할 수 있는 기회
논의를 위한 공간
```

가능한 수정:

```text
의견을 공유한다
소통한다
경험한다
논의한다
```

단, 실제 행사나 공간 자체가 중요하면 유지한다.

---

## 8.2 UNNECESSARY_NOMINALIZATION

동사를 불필요하게 명사화.

예:

```text
검토를 수행하다
분석을 실시하다
개선을 추진하다
논의를 진행하다
지원 제공
활용을 통해
```

수정:

```text
검토하다
분석하다
개선하다
논의하다
지원하다
활용해
```

---

## 8.3 META_STATEMENT

사실을 직접 말하지 않고 사실에 대해 다시 설명.

예:

```text
장점은 ~라는 점입니다.
중요한 점은 ~입니다.
특징적인 점은 ~입니다.
주목할 점은 ~입니다.
```

예:

```text
장점은 기존 코드를 수정하지 않아도 된다는 점입니다.
```

수정:

```text
기존 코드를 수정하지 않아도 됩니다.
```

---

## 8.4 UNNATURAL_METAPHOR

한국 업무 문서에서 어색한 은유.

후보:

```text
입구
통로
문을 열다
문턱
여정
지평
무대
공간
축
```

예:

```text
문제 해결의 입구
이 기술은 새로운 가능성의 문을 연다
AI 전환의 여정
```

수정은 상황별 판단.

예:

```text
문제 해결의 입구
→ 문제를 이해하는 출발점
→ 이 문제부터 살펴본다
```

주의:

단순 치환보다 직접적인 동사 표현이 우선이다.

---

## 8.5 TRANSLATIONESE

영어나 기타 언어 구조의 직역 가능성이 높은 표현.

예:

```text
~에 있어
~에 대한 이해
~를 통해
~의 관점에서
~라는 측면에서
~를 기반으로
~를 바탕으로
```

모든 표현을 금지하지 않는다.

문장 의미가 더 직접적으로 표현 가능한 경우만 수정한다.

---

## 8.6 EMPTY_EVALUATION

구체적인 근거 없이 붙는 평가어.

후보:

```text
의미 있는
유의미한
중요한
핵심적인
효과적인
혁신적인
체계적인
종합적인
실질적인
본질적인
다양한
```

예:

```text
유의미한 성과를 도출했습니다.
```

가능한 수정:

```text
성과를 냈습니다.
```

가능하면 수치나 실제 결과를 쓰는 것이 더 좋다.

---

## 8.7 AI_CLICHE / MARKETING_CLICHE

LLM과 홍보 문서에서 반복되는 공식.

예:

```text
단순히 A가 아니라 B
A를 넘어 B
A에 그치지 않고 B
A뿐만 아니라 B
무엇보다 중요한 것은
특히 주목할 점은
핵심은
```

예:

```text
단순한 테스트 자동화를 넘어
개발 프로세스 전반의 혁신을 의미합니다.
```

수정:

```text
테스트 자동화는 개발 프로세스에도 영향을 줍니다.
```

---

## 8.8 EMPTY_CONTRIBUTION

정확한 동작 대신 추상적인 효과를 표현.

예:

```text
중요한 역할을 한다
기여한다
기반을 마련한다
토대를 마련한다
가능성을 보여준다
계기가 된다
```

원칙:

가능하면 실제 기능 또는 결과를 직접 기술한다.

---

## 8.9 EXCESSIVE_HEDGING

필요 이상의 완곡 표현.

예:

```text
~것으로 보입니다
~것으로 판단됩니다
~라고 볼 수 있습니다
~일 수 있습니다
~할 수 있을 것으로 예상됩니다
~하지 않을까 생각합니다
```

단, 실제 불확실성이 있다면 유지한다.

---

## 8.10 REDUNDANT_CONNECTOR

접속어 남용.

후보:

```text
또한
특히
따라서
한편
이에 따라
결과적으로
궁극적으로
더 나아가
아울러
```

검사 포인트:

- 문단마다 등장하는가?
- 삭제해도 의미가 유지되는가?
- 접속 관계가 실제로 필요한가?

---

## 8.11 CEREMONIAL_REGISTER

일반 회사 업무에 과도한 의례 문체.

예:

```text
뜻깊은 자리
귀중한 의견
깊이 있는 논의
활발한 논의
심도 있는 논의
많은 관심과 참여
적극적인 협조
성공적인 수행
```

단, 행사·축사·공식 인사말에는 자연스러울 수 있다.

---

## 8.12 TRIPLE_ENUMERATION

LLM이 선호하는 인위적 3단 나열.

예:

```text
효율성, 안정성, 확장성
빠르고 안정적이며 유연합니다.
분석하고, 평가하고, 개선합니다.
```

3개 모두 실제 필요하면 유지한다.

수를 맞추기 위해 의미가 겹치는 항목을 추가한 경우 수정한다.

---

## 8.13 AMBIGUOUS_REFERENCE

내용이 없는 추상 지시.

후보:

```text
해당 부분
관련 사항
이러한 측면
이러한 내용
이와 같은 부분
이러한 맥락
관련 내용
```

가능하면 실제 대상을 명시한다.

---

## 8.14 REDUNDANCY

중복 표현.

예:

```text
사전에 미리
지속적으로 계속
다시 재검토
현재 시점 기준으로 지금
```

---

## 8.15 OVER-COMPLETED_SENTENCE

사실 전달이 끝났는데 의미·평가·결론을 추가.

예:

```text
~하는 데 중요한 역할을 합니다.
~에 기여할 수 있습니다.
~에 도움이 될 것입니다.
~할 수 있을 것으로 기대됩니다.
~하는 계기가 될 것입니다.
~라는 점에서 의미가 있습니다.
```

원칙:

> 사실 전달이 끝났으면 문장도 끝낸다.

---

# 9. `자리` 규칙 상세

`자리`는 본 프로젝트의 대표적인 초기 규칙이다.

## 문제 패턴

```text
논의하는 자리
공유하는 자리
소통하는 자리
의견을 나누는 자리
고민하는 자리
되돌아보는 자리
모색하는 자리
소개하는 자리
경험하는 자리
~하는 자리가 될 것입니다
~할 수 있는 자리를 마련했습니다
```

## 좋은 수정 예

```text
이번 회의는 향후 방향을 논의하는 자리입니다.
→ 이번 회의에서 향후 방향을 논의합니다.
```

```text
서로의 의견을 공유하는 자리가 되었으면 합니다.
→ 서로 의견을 공유했으면 합니다.
```

```text
새로운 가능성을 모색하는 자리를 마련했습니다.
→ 새로운 가능성을 논의하려고 합니다.
```

## 수정하면 안 되는 경우

```text
자리에 앉다
자리를 비우다
좌석 자리
일자리
자리가 없다
회식 자리에서 있었던 일
```

또한 행사 자체가 핵심인 경우:

```text
창립 20주년을 기념하는 자리입니다.
```

는 문맥상 자연스러울 수 있다.

따라서 `자리`는 자동 치환 규칙이 아니라:

```text
candidate → contextual judgment
```

규칙으로 분류하는 것이 적절하다.

---

# 10. `입구` 규칙 상세

`입구`는 물리적 장소에는 정상 표현이다.

정상:

```text
건물 입구
사무실 입구
주차장 입구
```

문제 후보:

```text
문제 해결의 입구
논의의 입구
기술 이해의 입구
시장 진입의 입구
```

검사 질문:

```text
1. 실제 물리적 입구인가?
2. 추상 개념의 시작을 비유하고 있는가?
3. '출발점', '시작', '먼저', 직접 동사로 더 자연스럽게 표현 가능한가?
```

예:

```text
이 질문은 문제를 이해하는 좋은 입구입니다.
```

가능한 수정:

```text
이 질문이 문제를 이해하는 좋은 출발점입니다.
```

더 자연스러운 경우:

```text
이 질문부터 살펴보면 좋겠습니다.
```

---

# 11. 문서 Profile

좋은 한국어는 문서 목적에 따라 달라진다.

최소 다음 profile을 고려한다.

```text
internal
external-business
technical
marketing
executive
ceremonial
```

---

## 11.1 internal

대상:

- 사내 메일
- Slack/Teams
- 업무 보고
- 회의 자료

특성:

- 간결
- 직접적
- 불필요한 의례 표현 최소화

---

## 11.2 external-business

대상:

- 고객 이메일
- 제안서
- 공식 전달 자료

특성:

- 격식 유지
- 지나친 홍보 문체 억제
- 명확한 책임과 사실 표현

---

## 11.3 technical

대상:

- 기술 백서
- 매뉴얼
- 시험 보고서
- 인증 관련 자료

특성:

- 의미 보존 최우선
- 최소 수정
- 기술 용어 유지
- 추상적 평가어 최소화

---

## 11.4 marketing

대상:

- 홈페이지
- 브로슈어
- 제품 소개

특성:

- 일부 강조 표현 허용
- 하지만 AI 상투어와 빈 홍보 문구는 검사

---

## 11.5 executive

대상:

- 경영진 보고
- 의사결정 문서

특성:

- 핵심 우선
- 결론 직접 표현
- 완곡어와 추상 표현 최소화

---

## 11.6 ceremonial

대상:

- 축사
- 기념행사
- 공식 인사말

특성:

- `뜻깊은 자리`
- `귀중한 의견`
- `함께해 주신`

등을 다른 profile보다 넓게 허용한다.

---

# 12. Rule별 Profile 설정

예:

```yaml
rule: KOR-ABSTRACT-001

profiles:
  internal: warning
  external-business: warning
  technical: warning
  marketing: suggestion
  executive: warning
  ceremonial: disabled
```

이렇게 하면 동일 규칙을 여러 문서 유형에 재사용할 수 있다.

---

# 13. 수정 모드

규칙마다 수정 위험도를 정의한다.

```text
SAFE
CONTEXTUAL
REVIEW
```

---

## SAFE

자동 수정 가능성이 높은 표현.

예:

```text
검토를 수행하다 → 검토하다
분석을 실시하다 → 분석하다
```

단, 실제 구현에서는 초기에는 SAFE도 patch preview를 제공하는 것이 안전하다.

---

## CONTEXTUAL

문맥 판단이 필요한 표현.

예:

```text
~하는 자리
~라는 점
이를 통해
입구
기반
역할
```

LLM 판정을 거친다.

---

## REVIEW

사람의 판단을 우선하는 표현.

예:

```text
혁신적인
의미 있는
중요한
단순히 A를 넘어 B
```

경고만 표시하고 자동 수정하지 않을 수 있다.

---

# 14. Finding 데이터 모델 예시

```json
{
  "id": "finding-00231",
  "rule_id": "KOR-ABSTRACT-001",
  "severity": "warning",
  "fix_mode": "contextual",
  "profile": "technical",
  "file": "whitepaper.md",
  "line": 127,
  "target": "이번 세미나는 향후 기술 방향을 논의하는 자리입니다.",
  "context_before": "다음 분기 로드맵을 공유합니다.",
  "context_after": "제품팀과 연구팀이 함께 참석합니다.",
  "decision": null,
  "suggestion": null
}
```

---

# 15. LLM Judge Prompt의 원칙

Judge에는 전체 rule DB를 주지 않는다.

입력:

```text
- target sentence
- 앞뒤 1~2문장
- document profile
- 해당 Rule 1개
```

판정:

```text
FIX
KEEP
REVIEW
```

예시 출력 schema:

```json
{
  "decision": "FIX",
  "confidence": 0.92,
  "reason": "행사 자체보다 논의 행위를 설명하고 있으며 '자리'가 의미를 추가하지 않는다.",
  "suggested_scope": "sentence"
}
```

---

# 16. Fixer Prompt의 원칙

핵심 제약:

```text
- 원문의 정보와 사실을 변경하지 않는다.
- 수치, 제품명, 규격명, 고유명사를 유지한다.
- 해당 finding과 직접 관련된 부분만 수정한다.
- 표현을 더 화려하게 만들지 않는다.
- 새로운 평가를 추가하지 않는다.
- 새로운 주장이나 결론을 추가하지 않는다.
- 수정할 필요가 없으면 KEEP을 반환한다.
```

출력:

```json
{
  "action": "FIX",
  "replacement": "이번 세미나에서 향후 기술 방향을 논의합니다."
}
```

---

# 17. 전체 문서 Rewrite를 피해야 하는 이유

기술·공식 자료에서는 다음 위험이 특히 크다.

- 표준 용어 변경
- 제품 기능 과장
- 법적 의미 변경
- 인증 범위 변경
- 숫자 변경
- 조건 누락
- 제한 사항 누락

따라서 patch 기반 접근이 적합하다.

예:

```diff
- 이번 세미나는 향후 기술 방향을 논의하는 자리입니다.
+ 이번 세미나에서 향후 기술 방향을 논의합니다.
```

---

# 18. 권장 CLI UX

예:

```bash
korean-qa lint whitepaper.md --profile technical
```

출력:

```text
Korean Writing QA

File: whitepaper.md
Profile: technical

High    2
Medium  7
Low     11

KOR-ABSTRACT-001  line 127
"향후 기술 방향을 논의하는 자리입니다."

Reason:
'자리'가 별도의 의미를 추가하지 않고
행위를 불필요하게 명사화합니다.

Suggestion:
"향후 기술 방향을 논의합니다."
```

자동 수정:

```bash
korean-qa fix whitepaper.md --profile technical
```

Preview:

```bash
korean-qa fix whitepaper.md --profile technical --dry-run
```

CI:

```bash
korean-qa lint docs/ --profile technical --fail-on high
```

---

# 19. Codex / Claude Code에서의 사용

전역 규칙에는 다음 정도만 둔다.

```text
When finalizing documents intended for customers, external publication,
formal internal release, or official distribution, run Korean Writing QA
using the appropriate document profile.
Do not rewrite the whole document solely for style.
Apply only reviewed or safe patches.
```

구체적인 규칙은 외부 파일에 둔다.

---

# 20. `/finalize-document` 개념

문서 최종화 명령에서만 검사한다.

사용 예:

```text
/finalize-document whitepaper.md
```

작업:

```text
1. 문서 구조 확인
2. Korean Writing QA lint
3. high-confidence finding 판정
4. 최소 patch 생성
5. patch 적용
6. 재 lint
7. 남은 REVIEW finding 보고
8. 최종 문서 생성
```

장점:

- 평소 대화 context를 오염시키지 않음
- 문서 초안 작성 단계에서 과도한 제약 없음
- 배포 품질만 일관되게 관리
- 규칙 DB를 독립적으로 개선 가능

---

# 21. Rule Directory 예시

```text
korean-writing-qa/
├── README.md
├── pyproject.toml
├── src/
│   └── korean_qa/
│       ├── cli.py
│       ├── detector.py
│       ├── judge.py
│       ├── fixer.py
│       ├── profiles.py
│       ├── findings.py
│       └── pipeline.py
│
├── rules/
│   ├── abstraction/
│   │   ├── abstract-jari.yml
│   │   ├── abstract-point.yml
│   │   ├── abstract-context.yml
│   │   └── abstract-process.yml
│   │
│   ├── nominalization/
│   │   ├── perform.yml
│   │   └── provide.yml
│   │
│   ├── translationese/
│   │   ├── through.yml
│   │   └── perspective.yml
│   │
│   ├── cliche/
│   │   ├── beyond.yml
│   │   ├── meaningful.yml
│   │   └── important-role.yml
│   │
│   ├── metaphor/
│   │   ├── entrance.yml
│   │   ├── journey.yml
│   │   └── doorway.yml
│   │
│   └── structure/
│       ├── connector-overuse.yml
│       └── triple-enumeration.yml
│
├── profiles/
│   ├── internal.yml
│   ├── external-business.yml
│   ├── technical.yml
│   ├── marketing.yml
│   ├── executive.yml
│   └── ceremonial.yml
│
├── prompts/
│   ├── judge.md
│   └── fixer.md
│
├── tests/
│   ├── rules/
│   ├── corpus/
│   └── regression/
│
└── samples/
    ├── before.md
    └── after.md
```

---

# 22. Rule Schema 초안

```yaml
id: KOR-ABSTRACT-001
version: 1

name: abstract-jari

category: abstract_event_container

description: >
  실제 장소 또는 행사 자체를 의미하지 않으면서
  동작을 '자리'라는 추상 명사로 감싸는 표현을 탐지한다.

severity: medium

fix_mode: contextual

detector:
  type: regex
  patterns:
    - '(논의|공유|소통|고민|모색|확인|소개|경험).*하는 자리'
    - '할 수 있는 자리'
    - '하는 자리가 될'

judge:
  required: true

preferred:
  - 동사를 직접 사용한다.
  - '자리'가 의미를 추가하지 않으면 삭제한다.

exceptions:
  - 실제 좌석 또는 위치
  - 일자리
  - 물리적 장소
  - 행사 자체가 핵심인 문장
  - ceremonial profile

examples:
  good:
    - "이번 회의에서 향후 방향을 논의합니다."

  bad:
    - "이번 회의는 향후 방향을 논의하는 자리입니다."

profiles:
  internal: warning
  external-business: warning
  technical: warning
  marketing: suggestion
  executive: warning
  ceremonial: disabled
```

---

# 23. 규칙 탐지기 종류

규칙마다 적절한 detector를 선택한다.

```text
literal
regex
morphological
frequency
document-level
llm-only
```

---

## literal

예:

```text
뜻깊은 자리
귀중한 의견
```

---

## regex

예:

```text
~하는 자리
~라는 점
단순히 .* 넘어
```

---

## morphological

형태소 정보가 필요한 경우.

예:

```text
동사 관형형 + 추상 명사
```

---

## frequency

문서 내 반복 탐지.

예:

```text
또한 12회
특히 18회
이를 통해 9회
```

절대 개수보다 문서 길이 대비 빈도가 중요할 수 있다.

---

## document-level

문서 전체 구조 검사.

예:

- 문단마다 `또한`
- 반복적인 3단 나열
- 모든 절의 동일한 구조
- 지나치게 동일한 종결 패턴

---

## llm-only

Regex로 찾기 어려운 경우.

예:

- 부자연스러운 은유
- 과도한 의례성
- 문서 목적과 안 맞는 어조

초기 버전에서는 llm-only 규칙을 최소화한다.

---

# 24. 한국어 형태소 분석 사용 여부

MVP에서는 Regex + 문자열 기반으로 시작하는 것이 좋다.

이유:

- 구현 빠름
- rule debugging 쉬움
- 어떤 규칙이 작동했는지 설명 가능
- 결과 reproducibility 높음

필요해지면 다음을 도입할 수 있다.

- Kiwi
- MeCab-ko
- khaiii 계열
- 기타 한국어 형태소 분석기

형태소 분석은 특히 다음 규칙에 유용하다.

```text
관형절 + 추상명사
명사화
연결어미 뒤 쉼표
조사 패턴
서술어 반복
```

---

# 25. 회사 자체 Corpus

장기적으로 가장 중요한 자산이다.

수집 대상:

```text
- 최종 승인된 백서
- 기술 자료
- 고객 전달 문서
- 제안서
- 홈페이지 문구
- 사내 공지
- 제품 설명
- 경영 보고 자료
```

특히 가치가 높은 데이터:

```text
AI 초안
→ 사람이 수정한 최종본
```

예:

```text
AI:
이번 회의는 향후 방향성을 함께 논의하는 자리가 될 것입니다.

Human:
이번 회의에서 향후 방향을 논의합니다.
```

이런 pair가 쌓이면 다음을 추출할 수 있다.

```text
자리 → 삭제 빈도
방향성 → 방향
~라는 점 → 직접 서술
이를 통해 → 삭제
진행하고자 합니다 → 진행합니다
```

---

# 26. 피드백 학습

모든 finding에서 사용자가 무엇을 했는지 기록한다.

예:

```json
{
  "rule_id": "KOR-ABSTRACT-001",
  "decision": "accepted",
  "original": "...",
  "suggested": "...",
  "final": "..."
}
```

가능한 사용자 행동:

```text
accepted
edited
ignored
false_positive
```

이 데이터로 rule precision을 측정한다.

---

# 27. 중요한 평가 지표

AI detection accuracy는 필요 없다.

대신 다음을 측정한다.

## Rule Precision

```text
해당 rule의 finding 중
실제 사람이 수정 필요하다고 판단한 비율
```

---

## Acceptance Rate

```text
제안된 수정 중
사용자가 그대로 채택한 비율
```

---

## Edit Distance After Suggestion

사용자가 제안을 다시 얼마나 수정했는지.

작을수록 suggestion 품질이 높다.

---

## False Positive Rate

정상 문장을 잘못 지적한 비율.

공식 문서 QA에서는 매우 중요하다.

---

## Semantic Preservation

수정 전후 의미가 보존되는지.

기술 문서에서는 가장 중요한 지표 중 하나다.

---

# 28. Severity 정의

예:

```text
HIGH
MEDIUM
LOW
INFO
```

초기에는 대부분 `MEDIUM` 또는 `LOW`로 시작하는 것이 안전하다.

`HIGH`는 매우 명확하고 조직적으로 금지된 표현에만 사용한다.

---

# 29. 초기 MVP 범위

처음부터 수백 개 규칙을 만들지 않는다.

## Phase 1

약 20~30개 규칙.

우선순위:

### A. 추상화

```text
자리
점
측면
맥락
관점
과정
기반
역할
계기
```

### B. AI/홍보 상투어

```text
단순히 A를 넘어 B
중요한 역할
의미 있는
유의미한
가능성을 보여준다
기반을 마련한다
```

### C. 번역투/명사화

```text
검토를 수행하다
분석을 실시하다
~를 통해
~에 대한
~의 관점에서
```

### D. 완곡어

```text
~것으로 보입니다
~것으로 판단됩니다
~라고 볼 수 있습니다
```

### E. 구조적 특징

```text
또한 남용
특히 남용
3단 나열 반복
```

---

# 30. MVP 동작

```text
1. Markdown/TXT 입력
2. 문장 분리
3. literal/regex 규칙 실행
4. finding 생성
5. contextual rule만 LLM judge
6. suggestion 생성
7. CLI에 결과 표시
8. --fix 옵션으로 선택적 수정
9. 다시 lint
```

초기에는 Word/PDF를 직접 지원하지 않아도 된다.

문서 원본 생성 시스템에서 Markdown을 intermediate format으로 사용하는 것도 고려할 수 있다.

---

# 31. Phase 2

- Profile 지원 강화
- 형태소 분석
- finding acceptance 기록
- 조직 corpus 연동
- 문서 전체 반복 패턴
- VS Code extension
- Codex/Claude Code Skill
- CI quality gate

---

# 32. Phase 3

- 조직별 style guide
- 제품/브랜드 용어 검사
- 기술 문서 claim 검사
- 공식 용어집 연결
- 과거 문서와 문체 일관성 검사
- 자동 rule mining
- human edit pair 분석

궁극적으로:

```text
Korean Writing QA
+
Company Style QA
+
Terminology QA
+
Document Quality Gate
```

로 확장 가능하다.

---

# 33. CI Quality Gate 전략

초기:

```text
모든 finding은 warning
```

어느 정도 데이터가 쌓이면:

```text
false positive가 거의 없는 rule만 error
```

예:

```bash
korean-qa lint docs/ --fail-on high
```

배포 차단은 매우 보수적으로 도입한다.

---

# 34. Rule 개발 방법

새 규칙을 느낌으로 바로 추가하지 않는다.

다음 절차 권장:

```text
1. 실제 어색한 사례 수집
2. 좋은 수정 예 수집
3. 반례 수집
4. detector 작성
5. regression corpus 추가
6. false positive 평가
7. profile별 적용 수준 결정
8. 배포
```

---

# 35. Rule Test Case 형식 예시

```yaml
rule: KOR-ABSTRACT-001

positive:
  - text: "향후 방향을 논의하는 자리입니다."
    expected: finding

  - text: "서로 의견을 공유하는 자리가 되길 바랍니다."
    expected: finding

negative:
  - text: "회의실에 자리가 없습니다."
    expected: no_finding

  - text: "그는 자리에서 일어났습니다."
    expected: no_finding

  - text: "창립 20주년을 기념하는 자리입니다."
    profile: ceremonial
    expected: no_finding
```

---

# 36. Regression Corpus

각 rule의 변경은 기존 결과를 깨지 않아야 한다.

구조 예:

```text
tests/corpus/
├── technical/
├── internal/
├── marketing/
├── ceremonial/
└── edge-cases/
```

모든 bug는 regression case로 추가한다.

---

# 37. LLM 선택과 역할

LLM은 rule engine을 대체하지 않는다.

역할:

```text
1. 후보의 문맥 적합성 판단
2. 최소 수정 제안
3. 의미 보존 확인
```

LLM에게 맡기지 않을 것:

```text
- 모든 rule discovery
- 모든 문장 검사
- 전체 문서 rewrite
- severity 임의 결정
```

---

# 38. Model-independent 설계

Claude, GPT, Gemini 등 특정 모델에 종속되지 않게 한다.

구조:

```text
JudgeProvider
FixProvider
```

예:

```python
class JudgeProvider:
    def judge(self, finding, rule, context, profile):
        ...
```

모델 교체가 가능해야 한다.

---

# 39. 비용 절감 전략

모든 문장을 LLM에 보내면 안 된다.

예:

100페이지 문서

잘못된 구조:

```text
100페이지 전체 → LLM
```

권장:

```text
deterministic scan
↓
47 candidates
↓
contextual rule 19개만 LLM
↓
12 fixes
```

따라서 LLM 사용량은 전체 문서 크기가 아니라 finding 수에 가까워진다.

---

# 40. 문맥 Window

후보마다 기본적으로:

```text
앞 문장
대상 문장
뒤 문장
```

정도를 사용한다.

필요 시 paragraph 전체를 보낸다.

문서 전체는 보내지 않는다.

단, document-level rule에서는 요약된 통계 또는 해당 문단들을 전달한다.

---

# 41. 보존해야 할 요소

Fixer가 변경하면 안 되는 것:

```text
- 숫자
- 날짜
- 제품명
- 회사명
- 표준명
- 규격 번호
- API 이름
- 함수명
- 코드
- URL
- 파일명
- 명령어
- 인용문
```

이를 보호하기 위해 placeholder 처리도 고려한다.

예:

```text
CT 5.2 → __TERM_001__
DO-178C → __TERM_002__
```

수정 후 복원.

---

# 42. 문서 영역 제외

Markdown 기준으로 다음은 기본적으로 style lint에서 제외할 수 있다.

```text
code block
inline code
URL
table 내부 일부
quoted source
raw log
JSON/YAML
command examples
```

Rule에 따라 일부는 검사할 수도 있다.

---

# 43. 사용자 UX 원칙

사용자에게 AI스럽다는 표현을 강조하지 않는다.

나쁜 UX:

```text
AI 표현 감지됨
```

좋은 UX:

```text
불필요한 추상화
과도한 완곡 표현
번역투 가능성
문서 격식 불일치
```

---

# 44. Finding UI 예

```text
[MEDIUM] 불필요한 추상화
KOR-ABSTRACT-001

원문:
이번 워크숍은 향후 제품 전략을 함께 고민하는 자리입니다.

제안:
이번 워크숍에서 향후 제품 전략을 논의합니다.

이유:
'자리'가 독립적인 의미를 추가하지 않고
'논의한다'는 동작을 불필요하게 명사화합니다.

[적용] [수정] [무시] [False Positive]
```

---

# 45. 좋은 수정의 기준

좋은 수정은 반드시 더 짧을 필요는 없다.

우선순위:

```text
1. 의미 정확성
2. 자연스러움
3. 직접성
4. 명확성
5. 문서 profile 적합성
6. 간결성
```

---

# 46. 핵심 스타일 철학

다음 문장을 프로젝트의 기본 철학으로 볼 수 있다.

> 사실을 직접 말할 수 있으면 사실에 대한 설명을 덧붙이지 않는다.

예:

```text
장점은 실행 시간이 짧다는 점입니다.
→ 실행 시간이 짧습니다.
```

```text
이 기능은 자동화에 중요한 역할을 합니다.
→ 이 기능이 테스트를 자동화합니다.
```

```text
논의를 위한 자리를 마련합니다.
→ 논의합니다.
```

---

# 47. AI 표현의 근본적 분류

`자리`, `입구` 같은 단어를 단순 금칙어로 보지 않는다.

더 일반적인 현상은:

```text
1. 동작을 추상 명사로 감싼다.
2. 물리적 개념을 추상적 은유로 사용한다.
3. 사실을 직접 말하지 않고 평가 구조로 감싼다.
4. 불확실성이 없어도 완곡하게 말한다.
5. 문장을 끝내지 않고 의미/기여/가능성을 덧붙인다.
6. 과도하게 균형 있고 완결된 구조를 만든다.
```

따라서 장기적으로는 단어 사전보다 이런 언어 현상을 탐지해야 한다.

---

# 48. 중요한 설계 결정 요약

현재까지 합의된 방향을 정리하면 다음과 같다.

## 결정 1

`AI 말투 제거기`가 아니라:

```text
Korean Business Writing QA
```

를 만든다.

---

## 결정 2

전역 Prompt에 전체 규칙을 넣지 않는다.

---

## 결정 3

배포 또는 최종화 단계에서 검사한다.

---

## 결정 4

Rule은 YAML/JSON 등의 data로 관리한다.

---

## 결정 5

Regex/Rule Engine + LLM Judge + Minimal Fixer 조합을 사용한다.

---

## 결정 6

전체 문서를 재작성하지 않는다.

---

## 결정 7

문서 Profile을 지원한다.

---

## 결정 8

규칙은 단어가 아니라 언어 현상 taxonomy 중심으로 만든다.

---

## 결정 9

사용자 feedback과 human edit pair를 장기 자산으로 축적한다.

---

## 결정 10

초기에는 약 20~30개의 precision 높은 규칙으로 시작한다.

---

# 49. Codex에서 바로 진행할 다음 작업

다음 순서로 구현을 권장한다.

## Step 1 — Repository Skeleton

다음 구조 생성:

```text
src/
rules/
profiles/
prompts/
tests/
samples/
```

---

## Step 2 — Rule Schema 정의

Pydantic 또는 dataclass 등을 이용해 Rule schema를 코드로 정의한다.

필수 필드:

```text
id
name
category
description
severity
fix_mode
detector
preferred
exceptions
examples
profiles
```

---

## Step 3 — Finding Schema 정의

필수:

```text
rule_id
file
line
text
context
severity
fix_mode
```

---

## Step 4 — Literal/Regex Detector

첫 구현은 단순하게 유지한다.

---

## Step 5 — 초기 Rule 10개

추천:

```text
1. abstract-jari
2. abstract-point
3. abstract-context
4. abstract-role
5. entrance-metaphor
6. beyond-cliche
7. important-role
8. meaningful
9. excessive-hedging
10. connector-overuse
```

---

## Step 6 — Test Corpus

positive / negative test를 먼저 만든다.

특히 `자리` rule에서 false positive를 충분히 넣는다.

---

## Step 7 — CLI lint

```bash
korean-qa lint samples/test.md --profile technical
```

까지 구현한다.

---

## Step 8 — LLM Judge Interface

실제 provider와 분리된 interface부터 만든다.

테스트에서는 mock provider를 사용한다.

---

## Step 9 — Minimal Fix

patch 생성과 dry-run을 구현한다.

---

## Step 10 — Re-lint

수정 후 동일 rule이 남아 있는지 재검사한다.

---

# 50. Codex 시작 프롬프트

아래 내용을 새 Codex 세션에 그대로 사용할 수 있다.

```text
우리는 "Korean Business Writing QA"라는 도구를 설계하고 구현하려고 한다.

목적은 AI 생성 여부를 탐지하는 것이 아니라 회사 업무 및 공식 자료에서
문법적으로는 맞지만 실제 한국어 업무 문체에서 어색한 표현을 찾아
자연스럽고 정확한 한국어로 최소 수정하는 것이다.

대표적인 문제는 다음과 같다.

- "~하는 자리"
- "~라는 점"
- "이를 통해"
- "단순히 A를 넘어 B"
- "중요한 역할을 한다"
- "기반을 마련한다"
- "가능성을 보여준다"
- "문제 해결의 입구"
- 과도한 명사화
- 번역투
- 과도한 완곡어
- 접속어 남용
- 인위적인 3단 나열
- 문서 목적과 맞지 않는 의례적인 표현

중요한 설계 원칙은 다음과 같다.

1. 모든 규칙을 system prompt나 AGENTS.md에 넣지 않는다.
2. 규칙은 YAML/JSON 등의 외부 rule DB로 관리한다.
3. 배포 또는 문서 최종화 단계에서 QA를 실행한다.
4. deterministic detector가 먼저 후보를 찾는다.
5. 문맥 판단이 필요한 후보만 LLM Judge에 보낸다.
6. 관련 Rule 하나와 주변 문맥만 LLM에 전달한다.
7. LLM은 FIX / KEEP / REVIEW를 판단한다.
8. 전체 문서를 다시 쓰지 않고 finding과 관련된 최소 범위만 수정한다.
9. 수정 후 다시 lint한다.
10. internal / external-business / technical / marketing / executive / ceremonial 같은 document profile을 지원한다.
11. 규칙은 "자리 금지"와 같은 단어 단위가 아니라
    ABSTRACT_EVENT_CONTAINER, UNNECESSARY_NOMINALIZATION,
    UNNATURAL_METAPHOR, TRANSLATIONESE, EMPTY_EVALUATION,
    EXCESSIVE_HEDGING 같은 언어 현상 중심 taxonomy로 설계한다.
12. 향후 사람이 AI 초안을 수정한 before/after 데이터를 corpus로 축적한다.

MVP는 Python CLI로 시작한다.
Markdown/TXT를 우선 지원하고 약 20~30개의 precision 높은 규칙을 만든다.

우선 다음을 진행하자.

1. 적절한 repository 구조를 제안한다.
2. Rule schema와 Finding schema를 설계한다.
3. YAML rule format을 정의한다.
4. literal/regex detector 구조를 구현한다.
5. 첫 rule로 "abstract-jari"를 구현한다.
6. positive/negative regression test를 충분히 작성한다.
7. CLI에서 `korean-qa lint <file> --profile technical` 형태로 실행 가능하게 만든다.

중요:
- 코드보다 먼저 schema와 testability를 잘 설계한다.
- 전체 rewrite 방식은 사용하지 않는다.
- false positive가 낮은 방향을 우선한다.
- 기술 문서에서 의미 보존이 최우선이다.
- LLM provider는 특정 모델에 종속되지 않게 interface로 추상화한다.
```

---

# 51. Codex에게 추가로 전달할 판단 기준

구현 중 애매할 때 다음 원칙을 따른다.

```text
Rule precision > Rule recall
```

즉 놓치는 문장이 조금 있어도 정상 문장을 과도하게 지적하지 않는 것이 낫다.

특히 공식 자료에서는 false positive가 많으면 사용자가 검사기를 끄게 된다.

또한:

```text
Minimal Fix > Better Rewrite
```

더 멋진 문장보다 최소한의 안전한 수정을 선호한다.

그리고:

```text
Explicit Rule > Invisible Prompt Magic
```

왜 수정했는지 Rule ID로 추적할 수 있어야 한다.

---

# 52. 향후 논의가 필요한 Open Questions

Codex 구현 과정에서 다음을 결정해야 한다.

## 52.1 Rule Engine

직접 구현 vs Vale 활용.

초기 MVP는 직접 구현이 더 단순할 수 있다.

Vale를 활용할 경우 장점:

- YAML style rule
- lint ecosystem
- CI integration

단점:

- 한국어 문맥 판단은 별도 구현 필요
- 본 프로젝트의 custom workflow와 맞추는 비용

---

## 52.2 형태소 분석기

초기에는 도입하지 않고 Regex로 시작할지,
Kiwi 등을 초기에 포함할지 결정 필요.

권장:

> MVP는 Regex 중심, 필요 rule부터 형태소 분석 도입.

---

## 52.3 LLM API

초기 인터페이스:

```text
JudgeProvider
FixProvider
```

실제 구현은 OpenAI/Anthropic 등을 adapter로 추가한다.

---

## 52.4 파일 형식

초기:

```text
.md
.txt
```

후기:

```text
.docx
.html
.pptx text
```

PDF는 원본 편집 포맷이 아니므로 후순위가 적합하다.

---

## 52.5 자동 Fix 범위

초기에는:

```text
--fix
```

도 모든 수정 전에 preview를 제공하는 것이 안전하다.

향후 precision이 검증된 SAFE rule만 완전 자동화할 수 있다.

---

# 53. 최종 방향

이 프로젝트의 가장 중요한 문장은 다음이다.

> 우리는 AI 말투를 없애려는 것이 아니라,
> 회사에서 실제로 사용할 수 있는 자연스럽고 정확한 한국어를
> 일관된 기준으로 검사하려고 한다.

`자리`, `입구`, `점`, `측면`, `맥락`, `기반`, `역할` 등의 표현은
그 목적을 위한 초기 관찰 사례다.

궁극적으로는:

```text
Korean language quality rules
+
document profile
+
contextual LLM judgment
+
minimal patching
+
feedback corpus
```

를 결합한 회사 문서 품질 시스템을 지향한다.
