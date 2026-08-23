# 다중 형식 AI 원본 진단

**생성 이력이 확인된 편집 원본의 형식별 검사** — 후보 585개 · 진단 표본 149개 · 변환 산출물 제외

## 표본

| 원본 종류 | 생성 이력 근거 | 후보 | 표본 |
|---|---|---:|---:|
| Markdown 문서 | 앞부분의 `model`·`generated_at` | 66 | 30 |
| JSONL 레코드 | `llm-generated-raw` 원본 파일 | 500 | 100 |
| 일반 텍스트 | 모델 출력임을 나타내는 파일명 · 한국어 포함 | 19 | 19 |

- **출처**: `P:/github/claude-workflow/reports`
- **선정 방식**: 원본 종류·자료 출처·크기별 순환 선택 · SHA-256 순서
- **원본 검증**: 복사한 149개 단위의 SHA-256 일치
- **원문 보관**: `data/raw/diagnostic-003/` · Git 제외
- **후보 목록**: `data/catalog/multiformat-ai-units.jsonl` · 본문 제외
- **표본 목록**: `runs/diagnostic-003/sample-manifest.json`

## 형식 지원

- **공통 추출기**: Markdown · HTML · JSON · JSONL · YAML · YML · properties · 일반 텍스트
- **Markdown 처리**: 앞부분 메타데이터와 코드 블록 제외
- **HTML 처리**: 화면에 표시되는 제목·문단·목록·표 값 추출
- **구조화 자료 처리**: JSON·JSONL·YAML의 문자열 값과 properties 속성값 추출
- **위치 기록**: 원본 행 번호 또는 JSON Pointer 방식의 논리 위치
- **변환 산출물**: PDF·PPTX·XLSX 직접 검사 제외 · 변환 전 원본 검사

## 사용자 확정 표현 검사

- **검사 규칙**: 정확 치환 2개 · 문맥 재작성 6개
- **탐지 결과**: 0건
- **판정 범위**: 표본에 확정 원문 표현이 그대로 재등장하지 않음
- **판정 제외**: 검사기의 탐지율·문서 전체의 자연스러움
- **상세 결과**: `runs/diagnostic-003/user-feedback-findings.jsonl`

## `경로` 용례 검사

- **등장 문서**: 28개
- **등장 횟수**: 68건
- **실제 path 후보**: 67건
- **추상 비유 후보**: 1건 · `에이전트가 … 경로를 이탈`
- **초기 사람 검토 대상**: 44건
- **규칙 보완 후 사람 검토 대상**: 0건

### 분류 근거

- **정상 용례 보완**: Windows·import·권한·원격·소스·보고서·네트워크 공유의 실제 위치와 호출 흐름
- **판정 상태**: 후보 분류만 수행 · 자동 수정 없음
- **요약 결과**: `runs/diagnostic-003/path-summary.json`
- **상세 문맥**: `runs/diagnostic-003/raw/path-findings.jsonl` · Git 제외

## 재현

```powershell
python scripts/build_multiformat_ai_sample.py `
  --source-root P:\github\claude-workflow\reports `
  --project-root P:\github\korean-writing-qa `
  --run-id diagnostic-003 `
  --markdown-count 30 `
  --jsonl-count 100

python scripts/scan_user_feedback.py `
  --source data\raw\diagnostic-003 `
  --feedback data\annotations\user-confirmed-phrases.jsonl `
  --output runs\diagnostic-003\user-feedback-findings.jsonl

python scripts/scan_path_metaphor.py `
  --source-root data\raw\diagnostic-003 `
  --output runs\diagnostic-003\raw\path-findings.jsonl `
  --summary runs\diagnostic-003\path-summary.json
```
