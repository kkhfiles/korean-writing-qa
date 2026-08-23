# Korean Writing QA

**회사 업무 한국어 검사기 개발** — 규칙·표본·검사 결과·수정 전후 데이터를 한 저장소에서 관리

## 현재 범위

- **입력 형식**: Markdown · HTML · 일반 텍스트 · JSON · JSONL · YAML · properties
- **검사 방식**: 결정 규칙으로 후보 탐지 · 필요한 후보만 문맥 판단
- **수정 방식**: 원문 의미를 보존하는 최소 변경 · 수정 전 미리보기
- **우선 기준**: 정상 문장을 지적하지 않는 정확도 우선
- **검사 단위**: 편집 가능한 원본 · PDF·PPTX 같은 변환 산출물 제외

## 디렉터리

| 경로 | 용도 |
|---|---|
| `docs/` | 설계·결정·기존 도구 조사 |
| `data/catalog/` | 원문 위치·해시·크기 목록 |
| `data/raw/` | 진단용 원문 복사본 · Git 제외 |
| `data/annotations/` | 사람의 판정과 수정 전후 문장 쌍 |
| `runs/` | 검사 실행별 입력 목록·결과·요약 |

## 운영 원칙

- **원본 보호**: 출처 문서 수정 금지 · 프로젝트 복사본만 실험
- **결과 추적**: 실행마다 입력 해시·도구 버전·검사 결과 기록
- **데이터 보관**: 원문과 중간 산출물은 프로젝트 디렉터리 내부 보관
- **외부 전송**: 유료 API나 외부 서비스 사용 전 사용자 확인

## 원본 추출

| 형식 | 검사할 내용 | 제외할 내용 |
|---|---|---|
| Markdown | 일반 본문 | 앞부분 메타데이터 · 코드 블록 |
| HTML | 화면에 표시되는 블록 | 스크립트 · 스타일 · 템플릿 · SVG |
| JSON · JSONL · YAML | 문자열 값 | 키 · 숫자 · 논리값 |
| properties | 속성값 | 키 · 주석 |
| 일반 텍스트 | 제어 문자 제거 후 각 줄 | 터미널 색상·제어 코드 |

**YAML 검사 의존성 설치**: `python -m pip install -r requirements.txt`

## 설계 문서

- [인수인계 설계](docs/design-handoff.md)
- [기존 검사기 조사](docs/existing-tools.md)
- [Claude Code 한글 표현 규칙 수집](docs/claude-korean-expression-inventory.md)
- [사용자 문체 피드백 반영](docs/user-feedback-workflow.md)
- [다중 형식 AI 원본 진단](docs/diagnostic-003.md)
