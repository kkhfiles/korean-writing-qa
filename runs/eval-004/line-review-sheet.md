---
form: structured
---

# 줄 단위 전수 판정 — diagnostic-002

**모든 줄을 「깨끗함」이나 「고칠 것」으로 판정 요청** — 붙어 있는 지적을 확인하고 **빠진 것만** 적으면 됨 · 이 판정이 끝나야 회수율의 분모가 참이 됨

## 읽는 법

- **이미 나온 지적**: 검사기와 2층이 그 줄에서 낸 것 · 비어 있으면 아무도 안 잡은 줄
- **판정**: 붙은 지적이 맞으면 `O` · 틀리면 `X` · **아무도 안 잡았는데 문제가 있으면 그것을 적음**
- 손댈 곳이 없으면 비워 두면 됨 — 빈 칸은 「깨끗함」으로 읽음

## doc-002 — 판정 대상 35행

| 행 | 원문 | 이미 나온 지적 | 판정 |
|---|---|---|---|
| 8 | # AI 프랙티스 분석 보고서 — 2026-08-08 |  | |
| 10 | ## 릴리즈 / 변경사항 |  | |
| 12 | ### Anthropic 2026 하반기 최신 모델 & 릴리즈 동향 |  | |
| 13 | 1. **Claude Opus 5 릴리즈 (2026년 7월 24일)** |  | |
| 14 | - 에이전틱 작업, 복잡한 시스템 아키텍처 설계, 코드베이스 리팩토링 능력이 비약적으로 상승한 플래그십 모델. | 2층: EVALUATIVE_MODIFIER · 2층: ENGLISH_OVERUSE | |
| 15 | - 장기 실행(long-running) 에이전트의 안정성과 논리 추론 일관성 개선. | 2층: ENGLISH_OVERUSE | |
| 17 | 2. **Claude Sonnet 5 릴리즈 (2026년 6월 30일)** |  | |
| 18 | - 100만(1M) 토큰 컨텍스트 윈도우 지원 및 128k 최대 출력 토큰(max output tokens) 제공. | 2층: ENGLISH_OVERUSE | |
| 19 | - Adaptive Thinking(가변 추론) 기능 도입으로 작업 난이도에 따른 동적 추론 깊이 조절 가능. | 라벨(지적): NOMINALIZATION | |
| 21 | 3. **Claude Code CLI 주요 기능 업데이트** |  | |
| 22 | - **Self-Hosted Runner 지원 (`claude self-hosted-runner`)**: 격리된 사내 환경 또는 로컬 실행 환경 구축 기능 추가. |  | |
| 23 | - **아카이브 플러그인 소스 (HTTPS)**: HTTPS URL을 통해 직접 플러그인 아카이브 패키지를 설치 및 관리하는 스펙 지원. | 라벨(지적): TRANSLATIONESE · 2층: TRANSLATIONESE | |
| 24 | - **에이전트 간 크로스 세션 메시징 (Cross-Session Messaging)**: 멀티 에이전트 환경에서 세션 간 비동기 메시지 전달 및 협업 지원. |  | |
| 25 | - **Interactive Tutorial (`/powerup`) 및 보안 샌드박스 강화**: 신규 튜토리얼 명령어 추가 및 권한 샌드박싱 세분화. |  | |
| 26 | - **No-Flicker 렌더링 엔진**: 터미널 UI 출력 시 화면 깜빡임 개선 및 렌더링 속도 향상. |  | |
| 30 | ## 커뮤니티 베스트 프랙티스 |  | |
| 32 | ### 2026년 최신 Claude Code 워크플로우 패턴 |  | |
| 33 | 1. **Context Management (컨텍스트 제어)** |  | |
| 34 | - **`CLAUDE.md` 중심의 메메틱 구조**: 프로젝트 메모리 및 핵심 엔지니어링 원칙을 명시하여 모델의 컨텍스트 오염 방지. | 2층: ENGLISH_OVERUSE | |
| 35 | - **강력한 `.claudeignore` 활용**: 대용량 데이터, 로그, 빌드 아티팩트를 적극 제외하여 컨텍스트 낭비를 50~70% 절감. | 주의: 평가 수식어 · 라벨(지적): EVALUATIVE_MODIFIER · 2층: EVALUATIVE_MODIFIER · 2층: REDUNDANT_MODIFIER | |
| 36 | - **주기적 `/compact` 및 `/clear` 활용**: 컨텍스트 윈도우가 비대해질수록 성능이 하락하는 현상을 방지하기 위해 컨텍스트 압축 및 세션 리셋 주기적 수… | 2층: NOMINALIZATION | |
| 38 | 2. **Plan-Then-Build (계획 선행형 워크플로우)** |  | |
| 39 | - 복잡한 코드 작성 전 `spec.md` 또는 scratch 공간에 명세 및 실행 계획을 수립하고 verification gate(테스트/빌드 스크립트)를 사전에 정의. | 2층: ENGLISH_OVERUSE | |
| 41 | 3. **TDD Red-Green 루프 & Verification Gates** |  | |
| 42 | - 테스트 코드 작성 -> 구현 -> 검증 단계를 에이전트가 자체적으로 돌 수 있도록 검증 수단(Verification Gate)을 명확히 제공. | 2층: VAGUE_VERB | |
| 46 | ## 권장 액션 |  | |
| 48 | ### 즉시 (실제 위험 / 명확한 효율) |  | |
| 49 | - [ ] 🟢 `.claudeignore` 템플릿 최적화 검토 — `mycelium/data/`, `*.db-wal`, 대용량 로그 디렉터리 등의 컨텍스트 유입을 적극 차… | 라벨(지적): VISUAL_DECORATION · 2층: VISUAL_DECORATION | |
| 51 | ### 점진 정리 (잡음 청소, 작업 방해 없음) |  | |
| 52 | - [ ] 🟡 레거시 문서 및 아카이브 스캔 경로 정리 — `reports/scheduled-reports/` 내 중복 보고서 정리 및 아카이브 자동화 스케줄 유지 \| … | 라벨(지적): VISUAL_DECORATION · 라벨(허용): LITERAL_PATH · 2층: VISUAL_DECORATION · 2층: ENGLISH_OVERUSE | |
| 54 | ### 검토 (의사결정 필요) |  | |
| 55 | - [ ] Adaptive Thinking 및 high effort 옵션 적용 검토 — Claude Sonnet 5 / Opus 4.8+ 환경에서 추론 깊이 조절 옵션(`… |  | |
| 56 | - [ ] 멀티 세션 크로스 메시징 패턴 적용 검토 — Claude Code 최신 에이전트 간 크로스 세션 메시징(Cross-Session Messaging) 기능을 my… |  | |
| 58 | ### 보류된 권고 (재평가 후 제외) |  | |
| 59 | - 이전 보고서 항목 없음 — 최초 실행 보고서로 재평가 대상 항목 없음. | 2층: REDUNDANT_REPEAT | |

## doc-004 — 판정 대상 40행

| 행 | 원문 | 이미 나온 지적 | 판정 |
|---|---|---|---|
| 10 | # 경쟁사 동향 diff — 2026-08-01 |  | |
| 12 | ## 새로 발견된 변경 (7건) |  | |
| 15 | - **이전 확인**: VectorCAST 2026 SP2 (2026-05) (2026-07-04) |  | |
| 16 | - **이번 변경**: **VectorCAST 2026 SP3 정식 출시 (2026-07)** | 주의: 값 안 굵게 · 라벨(지적): EMPHASIS_NOISE · 2층: EMPHASIS_NOISE | |
| 17 | - 테스트 케이스 트리의 대용량 반복 카운트(repeat counts) 편집 시 발생하던 메모리 초과 클래시 수정 (최대 1,000,000으로 제약) | 2층: ENGLISH_OVERUSE | |
| 18 | - 문자열 형태 타입 내 임베디드 NULL 문자 처리 및 템플릿 파라미터 팩을 포함한 생성자 스텁의 컴파일 에러 수정 |  | |
| 19 | - 공유 템플릿 함수의 단위 이름이 커버리지 뷰어에서 잘못 표시되던 버그 수정 및 인라인 멤버 함수/SBF(Stub-by-Function) 기능 개선 |  | |
| 20 | - **출처**: [Vector Informatik Download Center](https://www.vector.com) |  | |
| 23 | - **이전 확인**: Cantata 26.01 (2026-02) (2026-07-04) |  | |
| 24 | - **이번 변경**: **Cantata 26.04 정식 릴리즈 (2026-07)** | 주의: 값 안 굵게 | |
| 25 | - CI/CD 파이프라인, 외부 스크립트, AI 워크플로우와의 유기적 연동을 위한 **Open JSON Interfaces** 전면 도입 | 주의: 값 안 굵게 · 라벨(지적): EVALUATIVE_MODIFIER · 2층: EVALUATIVE_MODIFIER | |
| 26 | - CLI(명령줄) 연동 및 Visual Studio Code Extension 사용자 인터페이스 고도화 | 라벨(지적): NOMINALIZATION · 2층: NOMINALIZATION | |
| 27 | - Eclipse 개발 환경 내 통합 테스팅 사용성 향상 | 2층: ENGLISH_OVERUSE | |
| 28 | - **출처**: [QA Systems Cantata Product Page](https://www.qa-systems.com/tools/cantata/) |  | |
| 31 | - **이전 확인**: TESSY v5.1.16 (2026-04-29) (2026-07-04) |  | |
| 32 | - **이번 변경**: **차세대 버전 TESSY 6.0 공식 릴리즈 및 공개 (2026-07)** | 주의: 값 안 굵게 | |
| 33 | - TESSY v5.x 시리즈(Test Cockpit, Code Access, Fault Injection 등)를 계승하고 차세대 임베디드 테스팅 파이프라인 대응 및 파트… | 2층: EVALUATIVE_MODIFIER | |
| 34 | - **출처**: [Razorcat News & Downloads](https://www.razorcat.com) |  | |
| 37 | - **이전 확인**: TASKING 통합 툴체인 (2026-02) / LDRA tool suite v10.6.0 (2026-07-04) |  | |
| 38 | - **이번 변경**: **TASKING Compiler & Inspector 업데이트 배포 (2026-07-29)** | 주의: 값 안 굵게 | |
| 39 | - Compiler TriCore v6.2r2 및 Inspector v1.0r9 출시 |  | |
| 40 | - 정적/동적 검출 정밀도 향상, 오탐(false positive)을 줄이는 어셈블리 자동 비교 기능 탑재 및 컴파일러 패치 레벨 선택 옵션 추가 |  | |
| 41 | - **출처**: [TASKING Press & Updates](https://www.tasking.com/news) |  | |
| 44 | - **이전 확인**: R2026a (2026-04-27) (2026-07-04) |  | |
| 45 | - **이번 변경**: **MathWorks R2026b Prerelease 공개 (2026-07 말)** | 주의: 값 안 굵게 | |
| 46 | - Polyspace Platform 및 버그 파인더/테스트 제품군을 포함한 MathWorks R2026b 프러리리스 배포 시작 | 라벨(지적): ENGLISH_OVERUSE · 2층: TYPO | |
| 47 | - **출처**: [MathWorks Polyspace](https://www.mathworks.com/products/polyspace.html) |  | |
| 50 | - **이전 확인**: BTC EmbeddedPlatform 25.3 (2026-04-27 TÜV 인증) (2026-07-04) |  | |
| 51 | - **이번 변경**: **AI 신제품 `BTC TestAgent` 최초 버전 인도 및 브랜드 재정립 (2026-07-14)** | 주의: 값 안 굵게 | |
| 52 | - "High-Tech Software Quality Company"로 기업 브랜딩 재정립 발표 |  | |
| 53 | - HIL(Hardware-in-the-Loop) 및 Virtual HIL 환경에서 safety-critical 시스템 단위/통합 테스팅을 자동화하는 신제품 `BTC Te… | 2층: ENGLISH_OVERUSE | |
| 54 | - **출처**: [BTC Embedded Systems News](https://www.btc-embedded.com/) |  | |
| 57 | - **이전 확인**: Ketryx ALM (2026-06) (2026-07-04) |  | |
| 58 | - **이번 변경**: **규제 대상 AI 소프트웨어 "AI 조립 라인" 플랫폼 전략 공개 (2026-07-31)** | 주의: 값 안 굵게 | |
| 59 | - Ketryx CEO Erez Kaminski 인터뷰를 통해 의료기기 및 안전 필수 AI 시스템의 지속적 검증(Agentic Continuous Compliance) 플… | 2층: TRANSLATIONESE · 2층: NOMINALIZATION | |
| 60 | - **출처**: [Ketryx Newsroom](https://www.ketryx.com/) |  | |
| 62 | ## 신규 발견 |  | |
| 63 | (이번 달 신규 추가 시드 없음 — 기존 시드 10종 및 최근 3종 신규 진입자의 기능/버전 업데이트 중심) |  | |
| 65 | ## 폐기/통합 |  | |
| 66 | (이번 달 새로 감지된 단종/M&A 없음) |  | |

## doc-013 — 판정 대상 32행

| 행 | 원문 | 이미 나온 지적 | 판정 |
|---|---|---|---|
| 10 | # 경쟁사 동향 diff — 2026-05-02 |  | |
| 12 | 조사 기간: 2026-04-19 ~ 2026-05-02 (직전 조사 2026-04-18 이후). |  | |
| 14 | ## 새로 발견된 변경 (1건) |  | |
| 17 | - **이전 확인**: R2026a — Bug Finder/Code Prover/Requirements Toolbox가 Polyspace Platform으로 통합, Pyt… | 주의: 묶음 과대 | |
| 18 | - **이번 변경**: 2026-04-21 R2026a 출시 블로그, 2026-04-27 공식 프레스릴리즈로 다음 신규 기능이 추가 공개됨. |  | |
| 19 | - **Polyspace Copilot** — 정적분석 결과 위에 LLM 기반 가이드(원인·수정안 제시). MathWorks의 "Trusted AI" 라인으로 포지셔닝. | 2층: ENGLISH_OVERUSE | |
| 20 | - **Polyspace as You Code** — IDE 내부에서 코딩 중 실시간 정적분석. AI 생성 코드(Copilot/LLM 산출물) 검증을 명시 타깃. | 라벨(지적): ENGLISH_OVERUSE · 2층: ENGLISH_OVERUSE | |
| 21 | - **Polyspace Test에 소프트웨어 새니타이저(software-sanitizing) 추가** — 동적 런타임 오류(메모리/오버플로우 등) 분석으로 유닛테스트 결… |  | |
| 22 | - **MISRA C/C++ 2023 전면 지원** + **사용자 정의 체커(custom checker)** 가 Bug Finder에 도입. | 주의: 값 안 굵게 | |
| 23 | - 기존에 알려진 Python API·AUTOSAR-aware 스텁은 같은 R2026a 패키지의 일부로 재확인됨. |  | |
| 24 | - **출처**: |  | |
| 25 | - https://www.morningstar.com/news/business-wire/20260427271191/mathworks-brings-trusted-ai-to-… |  | |
| 26 | - https://blogs.mathworks.com/matlab/2026/04/21/matlab-r2026a-has-been-released-whats-new/ (202… |  | |
| 29 | ## 신규 발견 |  | |
| 31 | 해당 사항 없음. 시드 목록 외 신규 진입 도구는 이번 조사 기간(2주)에 발견되지 않음. (BTC EmbeddedTester는 직전 조사에서 시드 후보로 메모됐으나 해당… |  | |
| 33 | ## 폐기/통합 |  | |
| 35 | 해당 사항 없음. 이번 조사 기간에 새로 감지된 단종·인수합병·리브랜딩은 없음. |  | |
| 37 | ## 변경 없음 — 직전 상태 유지 (참고) |  | |
| 39 | \| 도구 \| 직전 확인 상태 \| 비고 \| | 오류: 스캔 가치 없는 라벨 · 라벨(지적): VAGUE_LABEL · 2층: VAGUE_LABEL | |
| 41 | \| VectorCAST 2026 \| 2026-03-19 출시, Reqs2x \| 신규 발표 없음 \| |  | |
| 42 | \| Parasoft C/C++test 2026.1 \| embedded world 2026 (인증 GoogleTest, MCP) \| 신규 발표 없음 \| |  | |
| 43 | \| Cantata 26.01 \| 2026-02 Claude Code 통합 \| 2026-04-08 웹세미나(범위 외), 신규 릴리즈 없음 \| |  | |
| 44 | \| TESSY v5.1.15 \| 2026-03-26 \| 신규 발표 없음 \| |  | |
| 45 | \| LDRA (TASKING) \| 2026-02 Renesas 확대 \| 신규 프레스 없음 \| |  | |
| 46 | \| Rapita RVS 3.23 / Space \| 2025-08, RVS Space \| 신규 발표 없음 \| |  | |
| 47 | \| Testwell CTC++ 10.3 \| 2026-03 embedded world \| 신규 발표 없음 \| |  | |
| 48 | \| TPT 2025.09 (Synopsys) \| Ansys 2026 R1 통합 \| 독립 2026 릴리즈 미공지 \| |  | |
| 49 | \| Wind River Test Mgmt \| 2026 신규 활동 없음 \| 변동 없음 \| |  | |
| 51 | ## 시장 트렌드 메모 (이번 변경 시사점) |  | |
| 53 | - **MathWorks가 Polyspace Copilot으로 AI 정적분석/테스트 가이드 시장에 합류** — 직전 분기에 VectorCAST(Reqs2x), Cantat… | 주의: 값 안 굵게 · 2층: EMPHASIS_NOISE · 2층: ENGLISH_OVERUSE | |
| 54 | - **"AI가 생성한 코드를 정적분석으로 검증" 포지셔닝 확산** — Polyspace as You Code가 명시적으로 GitHub Copilot/LLM 산출물을 타깃… | 라벨(지적): ABSTRACT_SUBJECT · 라벨(지적): ENGLISH_OVERUSE · 2층: ABSTRACT_SUBJECT · 2층: ENGLISH_OVERUSE | |
| 55 | - **MISRA C/C++ 2023 지원이 표준화 단계** — 시드 도구들이 잇달아 2023판을 반영 중. 2026년 하반기에 MISRA 2023 미지원 도구는 경쟁력 … |  | |

## 합계

**판정 대상 107행** — 머리말·빈 줄·표 구분선·주소만 있는 줄은 뺐음

