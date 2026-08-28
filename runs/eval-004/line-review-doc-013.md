---
form: structured
---

# 줄 단위 판정 — doc-013

**23행을 「깨끗함」이나 「고칠 것」으로 판정 요청** — 붙어 있는 지적을 확인하고 **빠진 것만** 적으면 됨 · 판정이 끝나야 회수율의 분모가 참이 됨

## 읽는 법

- **판정**: 붙은 지적이 맞으면 `O` · 틀리면 `X` · **아무도 안 잡았는데 한국어가 어색하면 그것을 적음**
- 손댈 곳이 없으면 비워 두면 됨 — 빈 칸은 「깨끗함」으로 읽음
- **굵게·이모지·강조 개수는 대상 아님** — 이 시스템이 보는 것은 한국어 표현
- **뺀 줄**: 제목·제품명·날짜·출처 링크 등 한글 어절 4개 미만

## 판정 대상 23행

| 행 | 원문 | 이미 나온 지적 | 판정 |
|---|---|---|---|
| 12 | 조사 기간: 2026-04-19 ~ 2026-05-02 (직전 조사 2026-04-18 이후). |  | |
| 14 | ## 새로 발견된 변경 (1건) |  | |
| 17 | - **이전 확인**: R2026a — Bug Finder/Code Prover/Requirements Toolbox가 Polyspace Platform으로 통합, Pyt… | 주의: 묶음 과대 | |
| 18 | - **이번 변경**: 2026-04-21 R2026a 출시 블로그, 2026-04-27 공식 프레스릴리즈로 다음 신규 기능이 추가 공개됨. |  | |
| 19 | - **Polyspace Copilot** — 정적분석 결과 위에 LLM 기반 가이드(원인·수정안 제시). MathWorks의 "Trusted AI" 라인으로 포지셔닝. | 2층: ENGLISH_OVERUSE | |
| 20 | - **Polyspace as You Code** — IDE 내부에서 코딩 중 실시간 정적분석. AI 생성 코드(Copilot/LLM 산출물) 검증을 명시 타깃. | 라벨(지적): ENGLISH_OVERUSE · 2층: ENGLISH_OVERUSE | |
| 21 | - **Polyspace Test에 소프트웨어 새니타이저(software-sanitizing) 추가** — 동적 런타임 오류(메모리/오버플로우 등) 분석으로 유닛테스트 결… |  | |
| 22 | - **MISRA C/C++ 2023 전면 지원** + **사용자 정의 체커(custom checker)** 가 Bug Finder에 도입. |  | |
| 23 | - 기존에 알려진 Python API·AUTOSAR-aware 스텁은 같은 R2026a 패키지의 일부로 재확인됨. |  | |
| 31 | 해당 사항 없음. 시드 목록 외 신규 진입 도구는 이번 조사 기간(2주)에 발견되지 않음. (BTC EmbeddedTester는 직전 조사에서 시드 후보로 메모됐으나 해당… |  | |
| 35 | 해당 사항 없음. 이번 조사 기간에 새로 감지된 단종·인수합병·리브랜딩은 없음. |  | |
| 37 | ## 변경 없음 — 직전 상태 유지 (참고) |  | |
| 39 | \| 도구 \| 직전 확인 상태 \| 비고 \| | 오류: 스캔 가치 없는 라벨 · 라벨(지적): VAGUE_LABEL · 2층: VAGUE_LABEL | |
| 41 | \| VectorCAST 2026 \| 2026-03-19 출시, Reqs2x \| 신규 발표 없음 \| |  | |
| 42 | \| Parasoft C/C++test 2026.1 \| embedded world 2026 (인증 GoogleTest, MCP) \| 신규 발표 없음 \| |  | |
| 43 | \| Cantata 26.01 \| 2026-02 Claude Code 통합 \| 2026-04-08 웹세미나(범위 외), 신규 릴리즈 없음 \| |  | |
| 45 | \| LDRA (TASKING) \| 2026-02 Renesas 확대 \| 신규 프레스 없음 \| |  | |
| 48 | \| TPT 2025.09 (Synopsys) \| Ansys 2026 R1 통합 \| 독립 2026 릴리즈 미공지 \| |  | |
| 49 | \| Wind River Test Mgmt \| 2026 신규 활동 없음 \| 변동 없음 \| |  | |
| 51 | ## 시장 트렌드 메모 (이번 변경 시사점) |  | |
| 53 | - **MathWorks가 Polyspace Copilot으로 AI 정적분석/테스트 가이드 시장에 합류** — 직전 분기에 VectorCAST(Reqs2x), Cantat… | 2층: ENGLISH_OVERUSE | |
| 54 | - **"AI가 생성한 코드를 정적분석으로 검증" 포지셔닝 확산** — Polyspace as You Code가 명시적으로 GitHub Copilot/LLM 산출물을 타깃… | 라벨(지적): ABSTRACT_SUBJECT · 라벨(지적): ENGLISH_OVERUSE · 2층: ABSTRACT_SUBJECT · 2층: ENGLISH_OVERUSE | |
| 55 | - **MISRA C/C++ 2023 지원이 표준화 단계** — 시드 도구들이 잇달아 2023판을 반영 중. 2026년 하반기에 MISRA 2023 미지원 도구는 경쟁력 … |  | |
