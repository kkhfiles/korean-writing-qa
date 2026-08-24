# Data

**검사 근거 데이터** — 원문 목록·진단 표본·사람 판정·수정 전후 문장 쌍 관리

| 경로 | 저장 대상 |
|---|---|
| `catalog/` | 출처 기준 상대 경로·해시·크기·수정 시각 |
| `raw/` | 원본을 바꾸지 않고 복사한 진단 표본 |
| `annotations/` | 규칙별 참·거짓 판정과 사람이 확정한 수정문 |

- **Git 제외**: 원문 복사본
- **커밋 대상**: 재현에 필요한 목록과 판정 데이터
- **Claude Code 규칙**: 전체 출처 목록은 `catalog/claude-rule-sources.jsonl` · 사람이 정리한 규칙은 `annotations/claude-korean-expression-rules.jsonl`
- **외부 도구**: 고정 커밋과 라이선스는 `catalog/external-korean-tools.jsonl` · 로컬 복제본은 `raw/external/`에 저장
