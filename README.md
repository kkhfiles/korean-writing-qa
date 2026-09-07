---
form: structured
---

# Korean Writing QA

**한국어 업무 문서를 기계로 검사하는 도구** — 사내 보고서 603개에서 지적 2,174건 · 세 편에 한 편꼴로 오류 · 받아서 그대로 쓸 수 있음

- **사례집** — [`docs/showcase.html`](docs/showcase.html) · 수정 전후 약 90쌍 · 브라우저로 열면 됨
- **사례 보내기** — [`CONTRIBUTING.md`](CONTRIBUTING.md) · 이슈로 문장 하나
- **필요한 것** — Python 3.11 이상 · 검사기 자체는 의존성 0

## AI 에게 시키는 법

이 절을 그대로 따라 하면 된다. Claude Code 나 그 밖의 코딩 에이전트에게 이 저장소 주소와 함께 넘기면 된다.

```
git clone https://github.com/<사용자>/korean-writing-qa.git
cd korean-writing-qa

# 1) 설치 없이 바로 도는지 확인 — 검사기는 파일 하나이고 의존성이 없다
python assets/doc-style-check.py tests/fixtures/paired/exempt-fixture.md
python assets/doc-style-check.py tests/fixtures/paired/violation-fixture.md

# 2) Claude Code 환경에 설치 (검사기 · 스킬 · 훅)
python install.py --hooks

# 3) 설치본이 정본과 같은지 확인
python install.py --check

# 4) 전체 시험
python -m pip install -r requirements.txt
python -X utf8 -m unittest discover -s tests
```

**나와야 하는 값** — 다르면 설치가 덜 된 것이다.

| 명령 | 나와야 하는 것 |
|---|---|
| `exempt-fixture.md` 검사 | `오류 0 · 주의 0` |
| `violation-fixture.md` 검사 | `오류 10 · 주의 5` |
| `install.py --check` | `같음 17 · 다름 0 · 없음 0` |
| 시험 | `OK` · 건너뛴 것 몇 개는 정상 |

**두 시료가 짝인 까닭** — 위반을 잡는 능력만 재면 「전부 지적」이 만점이 된다. 겉모습이 같은 정당한 표기 20종을 함께 돌려야 규칙이 쓸 만한지 갈린다.

## 설치 세 갈래

받는 사람이 어디까지 원하는지에 따라 고른다. 위에서부터 가볍다.

| 갈래 | 되는 일 | 받는 것 |
|---|---|---|
| **파일 하나** | 명령줄로 문서 검사 | `assets/doc-style-check.py` 60KB · 의존성 0 |
| **스킬 포함** | Claude Code 가 문서를 낼 때 문맥까지 읽어 고침 | `python install.py` |
| **훅 포함** | 발행 직전에 자동으로 걸림 | `python install.py --hooks` |

**파일 하나만 쓰는 법** — 저장소를 받을 것도 없이 그 파일만 내려받으면 된다.

```
python doc-style-check.py <파일…|디렉터리> [-v]
```

**훅이 하는 일** — Artifact 발행과 Edit·Write 뒤에 검사가 돌아 위반을 그 자리에서 알린다. `--hooks` 는 `~/.claude/settings.json` 을 고치므로 백업을 먼저 뜬다.

## 갈래를 골라 쓰기

**조직마다 문서 관행이 다름** — 표 머리 「비고」는 공문서 표의 표준 관례이고, 발표 대본은 산문이 정상이다. 갈래를 끄거나 severity 를 바꿀 수 있다.

```
python assets/doc-style-check.py --list-rules      # 갈래 26종 · 묶음 5종
cp korean-qa.example.toml korean-qa.toml           # 고쳐서 문서 위에 둔다
```

```toml
[rules]
off  = ["스캔 가치 없는 라벨", "구조"]   # 낱개 이름과 묶음 이름을 섞어 적는다
warn = ["절단형 의심"]                    # 오류에서 주의로 내린다
err  = []                                 # 주의에서 오류로 올린다
```

- **찾는 방법** — 검사 대상에서 위로 올라가며 `korean-qa.toml` 을 찾는다 · `--rules <파일>` 로 지정
- **★ 끈 것은 반드시 출력에 적힘** — 맨 위와 합계 줄 양쪽. 안 보이면 「오류 0」이 통과인지 안 본 것인지 갈리지 않는다.
- **발행 게이트** — `--no-rules` 로 설정을 무시하고 전부 봄
- **오타는 멈춤** — 모르는 갈래 이름을 적으면 rc 1. 조용히 넘기면 끄려던 검사가 안 꺼진 채 통과로 읽힌다.

## 두 층으로 나눔

**가르는 기준은 겉모습** — 글자만 대조해 갈리면 1층, 앞뒤를 읽어야 갈리면 2층.

| 층 | 맡는 갈래 | 위치 | 판정 |
|---|---|---|---|
| 1층 결정 규칙 | 글자만 보고 전수로 잡음 | `assets/doc-style-check.py` | 오류 · 주의 · 검사 불가 |
| 2층 읽는 판단 | 문맥을 읽어야 갈리는 것 | `skills/finalize-korean-document/` | 후보를 내고 사람이 확정 |

**판정 3단계** — 「검사 불가」는 합격이 아니라 **안 본 것**이다. 값 슬롯을 못 찾은 파일이 조용히 통과하면 아무도 그 문서를 다시 안 본다.

| 표시 | 뜻 |
|---|---|
| ❌ 오류 | 확실한 위반 · 공유 자료는 발행 전 0 |
| ⚠️ 주의 | 사람이 봐야 함 |
| ⛔ 검사 불가 | 값 슬롯 미인식 · 부분 검사만 됨 |

## 무엇을 보나

| 형식 | 검사하는 것 | 빼는 것 |
|---|---|---|
| Markdown | 일반 본문 | 앞부분 메타데이터 · 코드 블록 |
| HTML | 화면에 보이는 블록 | 스크립트 · 스타일 · 템플릿 · SVG |
| JSON · JSONL · YAML | 문자열 값 | 키 · 숫자 · 논리값 |
| properties | 속성값 | 키 · 주석 |
| 일반 텍스트 | 제어 문자 제거 후 각 줄 | 터미널 색상·제어 코드 |

- **산문 문서** — 머리말에 `form: prose`(HTML 은 `<meta name="form" content="prose">`) · 개조식 전제 검사가 꺼짐
- **검사 대상 아님** — PDF·PPTX 같은 변환 산출물. 편집 원본을 검사한다.
- **YAML 검사에만 의존성** — `python -m pip install -r requirements.txt`

## 저장소 구성

| 경로 | 담긴 것 |
|---|---|
| `assets/doc-style-check.py` | 1층 검사기 정본 |
| `skills/finalize-korean-document/` | 2층 스킬 정본 |
| `hooks/` | 발행 직전 검사 · 겹 역슬래시 차단 · 매일 건강 검사 |
| `install.py` · `repo_paths.py` | 설치와 경로 해석 |
| `tests/` | 시험 파일 44개 · 시험 320건 |
| `docs/` | 설계·결정·조사 기록 |
| `data/` | 사람 판정 · 회귀 시료 · 받은 사례 |
| `runs/` | 실행별 입력·결과·요약 |

**정본이 여기 있음** — 예전에는 `~/.claude/` 가 정본이고 이 저장소가 그것을 불러다 썼다. 저장소만 받은 사람이 아무것도 못 돌려서 방향을 뒤집었다. 설치본을 직접 고치면 `tests/test_installed_copy_matches.py` 가 잡는다.

## 설계 문서

- [사용 안내](docs/user-guide.md) — 설치·실행·결과 읽는 법
- [시스템 구조와 역할](docs/architecture.md) — 부품·실행 시점·되먹임
- [현재 상태](docs/status.md)
- [판단이 필요한 것](docs/decisions-pending.md)
- [기존 검사기 조사](docs/existing-tools.md)
- [외부 한국어 작성 도구 검토](docs/external-korean-tools-review.md)
- [사용자 문체 피드백 반영](docs/user-feedback-workflow.md)
- [인수인계 설계](docs/design-handoff.md) — 2026-08-24에 멈춘 창립 문서 · 현재 상태 아님
