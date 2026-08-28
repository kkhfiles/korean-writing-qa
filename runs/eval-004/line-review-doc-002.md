---
form: structured
---

# 줄 단위 판정 — doc-002

**26행을 「깨끗함」이나 「고칠 것」으로 판정 요청** — 붙어 있는 지적을 확인하고 **빠진 것만** 적으면 됨 · 판정이 끝나야 회수율의 분모가 참이 됨

## 읽는 법

- **판정**: 붙은 지적이 맞으면 `O` · 틀리면 `X` · **아무도 안 잡았는데 한국어가 어색하면 그것을 적음**
- 손댈 곳이 없으면 비워 두면 됨 — 빈 칸은 「깨끗함」으로 읽음
- **굵게·이모지·강조 개수는 대상 아님** — 이 시스템이 보는 것은 한국어 표현
- **뺀 줄**: 제목·제품명·날짜·출처 링크 등 한글 어절 4개 미만

## 판정 대상 26행

| 행 | 원문 | 이미 나온 지적 | 판정 |
|---|---|---|---|
| 12 | ### Anthropic 2026 하반기 최신 모델 & 릴리즈 동향 |  | |
| 13 | 1. **Claude Opus 5 릴리즈 (2026년 7월 24일)** |  | |
| 14 | - 에이전틱 작업, 복잡한 시스템 아키텍처 설계, 코드베이스 리팩토링 능력이 비약적으로 상승한 플래그십 모델. | 2층: EVALUATIVE_MODIFIER · 2층: ENGLISH_OVERUSE | |
| 15 | - 장기 실행(long-running) 에이전트의 안정성과 논리 추론 일관성 개선. | 2층: ENGLISH_OVERUSE | |
| 17 | 2. **Claude Sonnet 5 릴리즈 (2026년 6월 30일)** |  | |
| 18 | - 100만(1M) 토큰 컨텍스트 윈도우 지원 및 128k 최대 출력 토큰(max output tokens) 제공. | 2층: ENGLISH_OVERUSE | |
| 19 | - Adaptive Thinking(가변 추론) 기능 도입으로 작업 난이도에 따른 동적 추론 깊이 조절 가능. | 라벨(지적): NOMINALIZATION | |
| 22 | - **Self-Hosted Runner 지원 (`claude self-hosted-runner`)**: 격리된 사내 환경 또는 로컬 실행 환경 구축 기능 추가. |  | |
| 23 | - **아카이브 플러그인 소스 (HTTPS)**: HTTPS URL을 통해 직접 플러그인 아카이브 패키지를 설치 및 관리하는 스펙 지원. | 라벨(지적): TRANSLATIONESE · 2층: TRANSLATIONESE | |
| 24 | - **에이전트 간 크로스 세션 메시징 (Cross-Session Messaging)**: 멀티 에이전트 환경에서 세션 간 비동기 메시지 전달 및 협업 지원. |  | |
| 25 | - **Interactive Tutorial (`/powerup`) 및 보안 샌드박스 강화**: 신규 튜토리얼 명령어 추가 및 권한 샌드박싱 세분화. |  | |
| 26 | - **No-Flicker 렌더링 엔진**: 터미널 UI 출력 시 화면 깜빡임 개선 및 렌더링 속도 향상. |  | |
| 32 | ### 2026년 최신 Claude Code 워크플로우 패턴 |  | |
| 34 | - **`CLAUDE.md` 중심의 메메틱 구조**: 프로젝트 메모리 및 핵심 엔지니어링 원칙을 명시하여 모델의 컨텍스트 오염 방지. | 2층: ENGLISH_OVERUSE | |
| 35 | - **강력한 `.claudeignore` 활용**: 대용량 데이터, 로그, 빌드 아티팩트를 적극 제외하여 컨텍스트 낭비를 50~70% 절감. | 주의: 평가 수식어 · 라벨(지적): EVALUATIVE_MODIFIER · 2층: EVALUATIVE_MODIFIER · 2층: REDUNDANT_MODIFIER | |
| 36 | - **주기적 `/compact` 및 `/clear` 활용**: 컨텍스트 윈도우가 비대해질수록 성능이 하락하는 현상을 방지하기 위해 컨텍스트 압축 및 세션 리셋 주기적 수… | 2층: NOMINALIZATION | |
| 39 | - 복잡한 코드 작성 전 `spec.md` 또는 scratch 공간에 명세 및 실행 계획을 수립하고 verification gate(테스트/빌드 스크립트)를 사전에 정의. | 2층: ENGLISH_OVERUSE | |
| 42 | - 테스트 코드 작성 -> 구현 -> 검증 단계를 에이전트가 자체적으로 돌 수 있도록 검증 수단(Verification Gate)을 명확히 제공. | 2층: VAGUE_VERB | |
| 48 | ### 즉시 (실제 위험 / 명확한 효율) |  | |
| 49 | - [ ] 🟢 `.claudeignore` 템플릿 최적화 검토 — `mycelium/data/`, `*.db-wal`, 대용량 로그 디렉터리 등의 컨텍스트 유입을 적극 차… |  | |
| 51 | ### 점진 정리 (잡음 청소, 작업 방해 없음) |  | |
| 52 | - [ ] 🟡 레거시 문서 및 아카이브 스캔 경로 정리 — `reports/scheduled-reports/` 내 중복 보고서 정리 및 아카이브 자동화 스케줄 유지 \| … | 라벨(허용): LITERAL_PATH · 2층: ENGLISH_OVERUSE | |
| 55 | - [ ] Adaptive Thinking 및 high effort 옵션 적용 검토 — Claude Sonnet 5 / Opus 4.8+ 환경에서 추론 깊이 조절 옵션(`… |  | |
| 56 | - [ ] 멀티 세션 크로스 메시징 패턴 적용 검토 — Claude Code 최신 에이전트 간 크로스 세션 메시징(Cross-Session Messaging) 기능을 my… |  | |
| 58 | ### 보류된 권고 (재평가 후 제외) |  | |
| 59 | - 이전 보고서 항목 없음 — 최초 실행 보고서로 재평가 대상 항목 없음. | 2층: REDUNDANT_REPEAT | |
