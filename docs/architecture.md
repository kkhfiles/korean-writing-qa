---
form: structured
---

# 시스템 구조와 역할 — 2026-09-03

**한글 검사 시스템의 부품과 각 부품의 담당** — 실행 시점·되먹임까지 한 장 조망 · 지금 성적과 못 하는 것은 [현재 상태](status.md) · 시작 배경은 [인수인계 설계](design-handoff.md)

## 한눈에 — 층 셋과 그 사이

| 층 | 실행체 | 검사 대상 | 못 잡을 때 |
|---|---|---|---|
| **1층 · 낱말** | `skills/finalize-korean-document/scripts/check.py` | 사용자가 확정한 표현 8건 · `경로` 비유 | 2층이 맡음 |
| **1층 · 구조** | `assets/doc-style-check.py` | 개조식 서술·절단형·모호한 지칭·번역투·지어낸 명사구 | 2층이 맡음 |
| **2층 · 판단** | 사람이나 모델이 `core-rules.md`를 읽음 | 1층이 못 잡는 원칙 일곱 | 되먹임에 기록 |

**두 1층은 겹치지 않음** — 실측 380건에서 같은 줄을 둘 다 지적한 것이 5줄(2026-08-28 측정)

**분업 기준은 표면 모양** — 글자 대조로 갈리면 1층, 문맥을 읽어야 갈리면 2층. 그 경계는 취향이 아니라 실측으로 정해졌다([현재 상태](status.md)의 「결정 규칙으로 닫힌 경로 셋」).

## 부품별 역할

### 스킬 — 탐지 논리의 정본

**위치** `~/.claude/skills/finalize-korean-document` · 297KB

| 파일 | 역할 |
|---|---|
| `SKILL.md` | 열 단계 작업 순서 · 2층이 읽고 따르는 절차 |
| `references/core-rules.md` | 공통 원칙 11개 + 담당 표시(`[스킬]`·`[전역]`·`[사람]`) |
| `references/document-types.md` | 문서 종류별 규칙 묶음과 형식 축(산문형·구조형) |
| `references/confirmed-rules.jsonl` | 사용자가 확정한 교정 8건 · 1층이 글자로 찾는 것 |
| `references/context-cases.jsonl` | 문맥 판정 시료 14건 |
| `references/regression-cases.jsonl` | 회귀 시료 68건 |
| `scripts/check.py` | 확정 표현·`경로` 비유 탐지 |
| `scripts/check_meaning.py` | 고친 뒤 뜻이 빠졌는지 대조 |
| `scripts/record_feedback.py` | 오탐·미탐을 후보로 기록 |
| `scripts/promote_feedback.py` | 확인된 후보를 규칙과 시험으로 올림 |
| `scripts/self_test.py` | 스킬 자체 회귀 시험 |
| `scripts/source_text.py` | 형식별 원문 추출 |

### 전역 문서 검사기 — 구조와 낱말

**위치** `~/.claude/assets/doc-style-check.py` · 60KB · **바깥 의존성 0**(파이썬 기본 모듈만)

| 무게 | 갈래와 실측 건수 |
|---|---|
| **오류** · 발행을 막음 | 서술형 종결 1,324 · 스캔 가치 없는 라벨 208 · 모호한 지칭 68 · 제목·진입점 97 · 절단형 종결 43 |
| **주의** · 참고 | 절단형 의심 130 · 해설을 인용 부호로 씀 49 · 반복 블록 라벨 불일치 45 · 형식 미표기 43 · 평가 수식어 25 · 번역투 12 · 지어낸 명사구 0 |

*마크다운·HTML 601건 기준 · 2026-09-03*

**형식 축** — 산문 문서는 개조식 전제 검사를 끈다. 마크다운 머리말 `form: prose` · HTML `<meta name="form" content="prose">` · **파일이 형식을 들고 있게 한다**(플래그로만 두면 사람이 기억해야 한다).

**자체 시험** `python ~/.claude/assets/doc-style-check-test.py`

### 훅 — 검사기를 부르는 두 시점

**위치** `~/.claude/hooks/doc-style-gate.py` · 검사기 **둘 다** 부른다

| 시점 | 걸리는 도구 | 내는 것 |
|---|---|---|
| `PostToolUse` | Edit · Write · MultiEdit | 오류만 · 같은 파일은 세션에 한 번 |
| `PreToolUse` | Artifact · Bash · PowerShell | 오류와 주의 전부 |

**두 시점으로 나눈 까닭** — 발행 직전만 두면 다 써 놓은 뒤에 고치게 되고, 쓰기마다 전부 내면 초안까지 걸려 소음이 된다.

**차단하지 않음** — 오탐 하나가 발행을 막으면 그다음부터 아무도 안 본다. `additionalContext`로 넘겨 그 자리에서 고치게 한다.

**검사에서 빼는 곳** — 스크래치패드 · 임시 디렉터리 · `~/.claude/` 자체 · `node_modules`

**★ Codex 도 같은 훅을 씀**(2026-09-04) — `codex-hook-adapter.py` 가 Codex 도구 이름을 이 훅이 읽는 모양으로 옮기고 훅을 그대로 돌린다. 검사 규칙은 훅 한 곳에만 있다.

### 이 저장소 — 재는 곳이지 도는 곳이 아님

**런타임에 안 낌** — 탐지 논리는 배포된 스킬이 정본이고 이 저장소의 스캐너가 그것을 불러다 쓴다. 스킬이 없으면 수집 단계에서 멈춘다.

| 디렉터리 | 역할 |
|---|---|
| `scripts/` | 측정·진단 실행체 19개 |
| `tests/` | 시험 파일 48개 · 배포본을 망가뜨리면 여기서 실패 |
| `runs/` | 실행 기록 25건 · 입력·결과·판정 |
| `data/annotations/` | 사람의 판정과 수정 전후 쌍 |
| `data/regression/` | 양성·정상·경계 시료 |
| `data/catalog/` | 원문 위치·해시 목록 |
| `data/feedback/` | 승격 대기 후보 |
| `docs/` | 설계·결정·조사 |

**사본을 안 두는 까닭** — 같은 정규식을 두 벌 두면 한쪽만 고쳐진다. 실제로 갈라져서 스킬을 망가뜨려도 저장소 시험이 전부 통과한 적이 있다.

## 글이 지나가는 길

| 단계 | 하는 일 |
|---|---|
| 1 | 문서 종류와 독자를 정함 · `document-types.md` |
| 2 | 편집 원본을 고름 · 변환 산출물(PDF·PPTX) 아님 |
| 3 | 1층 둘을 돌림 · `check.py` + `doc-style-check.py` |
| 4 | 고친 뒤 `check_meaning.py`로 뜻이 빠졌는지 대조 |
| 5 | 다시 돌려 오류 0 확인 |
| 6 | **2층이 읽음** · 검사기가 조용한 것은 그 규칙을 안 봤다는 뜻 |
| 7 | 오탐은 `record_feedback.py`로 기록 |

## 되먹임 — 오탐이 규칙으로 돌아오는 길

| 단계 | 실행체 | 남는 곳 |
|---|---|---|
| 오탐 판정 | `record_feedback.py --user-verdict false_positive` | `data/feedback/candidates.jsonl` |
| 사람 확인 | 사용자 | — |
| 규칙 반영 | `promote_feedback.py` 또는 `core-rules.md` 예외 | 스킬 |
| **적용 확인** | `scripts/probe_layer2_exemption.py` | `runs/eval-007` |

**마지막 단계가 있는 까닭** — 규칙을 썼다는 것과 규칙이 적용된다는 것은 다르다. 예외를 새로 적을 때마다 한 번 돌린다(호출당 0.3달러).

## 안 하는 것 — 경계

| 대상 아님 | 까닭 |
|---|---|
| 터미널 응답과 대화 | 문서로 나갈 때만 봄 · 응답 쪽 규율은 글로벌 `CLAUDE.md` 소관 |
| 시각 서식 · 굵게 개수 · 묶음 행 수 | 검사기 목적은 「한글이 똑바로 써졌나」 · 그 셋이 주의의 88%를 먹어 낱말 지적을 덮었다 |
| 변환 산출물 PDF · PPTX | 편집 원본을 검사 · 직접 만든 Word·PowerPoint는 표시 문구를 뽑아 검사 |
| 작업 문서의 오류 0 강제 | 공유 자료만 대상 |

## 밖에 줄 때 — 나눌 수 있는 세 단계

| 단계 | 주는 것 | 받는 쪽 준비 |
|---|---|---|
| **1** | `doc-style-check.py` 파일 하나 | 파이썬만 · Claude Code 불필요 |
| 2 | 스킬 폴더 전체 | Claude Code · `~/.claude/skills/`에 복사 |
| 3 | 위 + 훅 + `settings.json` 항목 둘 | 설정 편집 |

**1단계가 지적의 대부분을 냄** · 받는 사람이 읽을 것은 [사용 안내](user-guide.md) · 진행 상태는 [현재 상태](status.md)의 「부서원 공유」
