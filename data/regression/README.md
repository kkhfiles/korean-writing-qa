# 회귀시험 자료

**검사기 변경 전후에 반드시 유지할 판정** — 사용자 확정 표현 · 실제 path 정상 용례 · 추상 `경로` · 형식별 보호 구간

## 현재 구성

| 자료 | 시료 수 | 용도 |
|---|---:|---|
| `detector-cases.jsonl` | 68 | 사용자 확정 표현 25건 · 문서 종류 오용 방지 7건 · `경로` 분류 36건 |
| `runs/diagnostic-002/path-term-candidates.jsonl` | 33 | 사람이 정상으로 판정한 실제 path 문맥의 오탐 방지 |
| `data/annotations/user-confirmed-phrases.jsonl` | 8 | 사용자가 직접 확정한 수정 전후 문구 |
| `data/annotations/diagnostic-002-review.jsonl` | 14 | AI 보고서 세 개에서 사람이 판정한 수정 전후 문구 |
| `tests/fixtures/formats/` | 7개 형식 | 본문 추출 · 코드와 메타데이터 제외 · 논리 위치 보존 |

**중복 제외 총계**: 실행 가능한 탐지·분류 101건 · 수정 전후 22쌍 · 형식별 추출 fixture

## 판정 원칙

- **양성**: 사용자 확정 또는 출처가 기록된 후보만 사용
- **정상**: 실제 path 33건과 권장 수정문으로 거짓양성 방지
- **경계**: 자동 판정 근거가 부족한 `경로`는 `review` 유지
- **문서 종류**: 발표자 노트·특정 프로젝트 전용 규칙은 일반 보고서에 미적용
- **보호 구간**: Markdown 코드 펜스·인라인 코드와 HTML `pre`·`code`는 검사 제외
- **수정 안전**: 고유명사·영문 식별자·수치가 있는 수동 수정 14쌍의 보호 토큰 유지

## 실행

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

**자동 검사**: `tests/test_regression_corpus.py` · 시료 수·규칙별 최소 구성·예상 판정·실문서 오탐 대조
