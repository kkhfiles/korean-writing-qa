---
form: structured
---

# 시스템 구조와 역할

**한글 검사 시스템의 부품과 각 부품의 담당** — 실행 시점·되먹임까지 한 장 조망 · 지금 성적과 못 하는 것은 [현재 상태](status.md) · 시작 배경은 [인수인계 설계](archived/design-handoff.md)

## 한눈에 — 세 단계 검사와 그 사이

| 층 | 실행체 | 검사 대상 | 못 잡을 때 |
|---|---|---|---|
| **1층(구조와 맞춤법)** | `assets/doc-style-check.py` | 개조식 서술, 절단형, 모호한 지칭, 번역투, 지어낸 명사구, 자주 틀리는 맞춤법과 띄어쓰기(`spelling-errors.tsv`) | 단어 점검 및 2층 담당 |
| **단어 점검** | `scripts/rare_words.py` | 사람이 쓴 업무 한국어 4,790만 자 기준선 대비 드문 낱말 추출 | 판정하지 않고 후보만 2층에 전달 |
| **2층 판단** | `scripts/judge_layer2.py` (AI 판정기 또는 사람) | `core-rules.md`, 사용자 확정 수정, 그 문서의 드문 낱말 목록, 개인 판정 기준(`local-layer2-rules.md`) | 되먹임에 기록. 판정기가 문제인지 못 가르면 「사람 확인」으로 사용자에게 넘김(답 전 발행 보류) |

**분업 기준은 표면 모양** — 글자 대조로 갈리면 1층, 문맥을 읽어야 갈리면 2층. 그 경계는 취향이 아니라 실측으로 정해졌습니다([현재 상태](status.md)의 「결정 규칙으로 닫힌 경로 셋」).

## 부품별 역할

### 스킬 — 탐지 논리의 정본

**정본 위치** 이 저장소의 `skills/finalize-korean-document` (설치기 `install.py` 가 `~/.claude/skills/` 와 `~/.agents/skills/` 로 설치·동기화)

| 파일 | 역할 |
|---|---|
| `SKILL.md` | 작업 순서(2층이 읽고 따르는 절차) |
| `references/core-rules.md` | 공통 원칙 11개 + 담당 표시(`[스킬]`·`[전역]`·`[사람]`) |
| `references/document-types.md` | 문서 종류별 규칙 묶음과 형식 축(산문형·구조형) |
| `references/confirmed-rules.jsonl` | 사용자가 확정한 교정 8건 · 1층이 글자로 찾는 것 |
| `references/context-cases.jsonl` | 문맥 판정 시험 데이터 |
| `references/regression-cases.jsonl` | 회귀 시험 데이터 |
| `scripts/check.py` | 확정 표현·`경로` 비유 탐지 |
| `scripts/check_meaning.py` | 고친 뒤 뜻이 빠졌는지 대조 |
| `scripts/record_feedback.py` | 오탐·미탐을 후보로 기록 |
| `scripts/promote_feedback.py` | 확인된 후보를 규칙과 시험으로 올림 |
| `scripts/self_test.py` | 스킬 자체 회귀 시험 |
| `scripts/source_text.py` | 형식별 원문 추출 |

### 전역 문서 검사기 — 구조와 낱말

**위치** `assets/doc-style-check.py` (설치 시 `~/.claude/assets/` 로 복사), 바깥 의존성 최소(파이썬 기본 모듈, 품사 판정 시 `kiwipiepy`)

| 무게 | 갈래 |
|---|---|
| **오류**(발행을 막음) | 서술형 종결, 서술형 문단, 제목·진입점 위반, 모호한 지칭, 절단형 종결, 이중 피동, 맞춤법 오류, 새로 쓴 띄어 쓴 가운뎃점 |
| **주의**(참고) | 절단형 의심, 해설을 인용 부호로 씀, 형식 미표기, 평가 수식어, 번역투 조사·그녀, 지어낸 명사구, 맞춤법 의심, 띄어쓰기 의심 |

**형식 축** — 산문 문서는 개조식 전제 검사를 끕니다. 마크다운 머리말 `form: prose`, 공지·안내 메일은 `form: notice`, HTML 은 `<meta name="form" content="prose|notice">`. **파일이 형식을 들고 있게 합니다**(플래그로만 두면 사람이 기억해야 합니다).

**규칙 제어** — 폴더나 상위 디렉터리의 `korean-qa.toml` 로 특정 규칙을 끄거나(`off`), 등급을 조정(`warn`, `err`)할 수 있습니다.

### 훅과 게이트 — 검사기를 부르는 시점

**위치** `~/.claude/hooks/doc-style-gate.py` (설치기 `install.py --hooks` 가 등록), Codex 는 `codex-hook-adapter.py` 연동

| 시점 | 걸리는 도구 | 내는 것 |
|---|---|---|
| `PostToolUse` | Edit · Write · MultiEdit | 오류만 · 같은 파일은 세션에 한 번 |
| `PreToolUse` | Artifact, Bash, PowerShell | 발행 직전 오류와 주의 전부 출력, 미해결 지적이 있으면 발행 보류 |

**차단하지 않고 해제 방법을 둠** — 오탐으로 판단한 지적은 사유를 기록(`check_record.py`)하면 통과할 수 있으며, 내용 해시에 묶여 한 글자만 고쳐도 다시 검사합니다.

### 이 저장소 — 정본 관리와 측정 및 시험

**정본의 자리** — 모든 규칙·스킬·검사기·맞춤법 사전의 정본은 이 저장소에 있으며, 배포 스크립트(`install.py`, `bootstrap.py`)를 통해 로컬 환경으로 복사·설치됩니다.

| 디렉터리 | 역할 |
|---|---|
| `skills/` | 스킬 정본(`finalize-korean-document`, `fix-korean-finding`) |
| `assets/` | 전역 문서 검사기(`doc-style-check.py`) 정본 |
| `scripts/` | 측정·진단·판정(`judge_layer2.py`, `rare_words.py`, `check_record.py` 등) 실행체 |
| `tests/` | 전체 단위 및 통합 시험 |
| `runs/` | 측정·실험·진단 실행 기록 |
| `data/` | 기준 낱말표, 확정 규칙, 회귀 시험 자료, 개인 설정 예시 |
| `docs/` | 구조·설계·현황 문서 |

## 글이 지나가는 길

| 단계 | 하는 일 |
|---|---|
| 1 | 문서 종류와 독자를 정함 · `document-types.md` |
| 2 | 편집 원본을 고름 · 변환 산출물(PDF·PPTX) 아님 |
| 3 | 1층 검사를 실행(`assets/doc-style-check.py`) |
| 4 | 고친 뒤 `check_meaning.py` 로 뜻이 빠졌는지 대조 |
| 5 | 다시 돌려 1층 오류 0 확인 |
| 6 | **단어 점검 및 2층 판정** — `scripts/rare_words.py` 의 드문 단어 목록과 함께 `scripts/judge_layer2.py` 가 판정 |
| 7 | 지적 처리(수정하거나 사유를 적고 반영하지 않음, 필요 시 `--why` 로 이유 조회) |
| 8 | 오탐이나 예외는 `check_record.py` 와 되먹임에 기록 |

## 되먹임 — 오탐이 규칙으로 돌아오는 길

| 단계 | 실행체 | 남는 곳 |
|---|---|---|
| 오탐 판정 | `record_feedback.py --user-verdict false_positive` | `data/feedback/candidates.jsonl` |
| 사람 확인 | 사용자가 카드형 판정표(`scripts/ask_sheet_html.py --serve`) 또는 검토 화면(`scripts/review_screen.py`)에서 답함 | 판정표 또는 검토 화면 |
| 규칙 반영 | `promote_feedback.py` 또는 `core-rules.md` 예외 | 스킬 |
| **적용 확인** | `scripts/probe_layer2_exemption.py` | `runs/eval-007` |

**마지막 단계가 있는 까닭** — 규칙을 썼다는 것과 규칙이 적용된다는 것은 다릅니다. 예외를 새로 적을 때마다 한 번 돌립니다(호출당 0.3달러).

## 안 하는 것 — 경계

| 대상 아님 | 까닭 |
|---|---|
| 터미널 응답과 대화 | 문서로 나갈 때만 봄 · 응답 쪽 규율은 글로벌 `CLAUDE.md` 소관 |
| 시각 서식 · 굵게 개수 · 묶음 행 수 | 검사기 목적은 「한글이 똑바로 써졌나」이고, 그 셋이 주의의 88%를 차지해 낱말 지적을 덮었음 |
| 변환 산출물 PDF · PPTX | 편집 원본을 검사 · 직접 만든 Word·PowerPoint는 표시 문구를 뽑아 검사 |
| 작업 문서의 오류 0 강제 | 공유 자료만 대상 |

## 설치와 배포

| 갈래 | 설치 대상 | 방법 |
|---|---|---|
| **파일 하나** | `assets/doc-style-check.py` 파일 하나만 내려받아 명령줄로 검사 | 파이썬만 있으면 실행 가능 |
| **스킬과 훅 자동 설치** | 형태소 모듈, 스킬, 훅, 시료 검사까지 한 번에 설치 | `python bootstrap.py` |
| **수동 설치** | 스킬 및 훅을 원하는 환경(Claude Code, Codex)에 맞추어 설치 | `python install.py --hooks` (Codex 는 `--codex` 추가) |
