---
form: structured
---

# AI 한글 교정기

**AI가 쓴 한글을 업무에서 낼 수 있는 글로** — 규칙은 **사람이 쓴** 사내 보고서 600여 개로 실측 · 형식과 무관한 오류가 있던 문서 8% · 개조식 규약까지 켜면 33% · 받아서 그대로 쓸 수 있음

- **표시 색** — 주묵(朱墨) · 원고를 고칠 때 쓰던 붉은 먹
- **사례집** — [`docs/showcase.html`](docs/showcase.html) · 수정 전후 74쌍 · 브라우저로 열면 됨 · [올릴 준비물](docs/site-listing.md)
- **사례 보내기** — [`CONTRIBUTING.md`](CONTRIBUTING.md) · 이슈로 문장 하나
- **필요한 것** — Python 3.11 이상 · 검사기 자체는 의존성 0

## AI 에게 시키는 법

이 절을 그대로 따라 하시면 됩니다. Claude Code 나 그 밖의 코딩 에이전트에게 이 저장소 주소와 함께 넘기시면 됩니다.

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

**나와야 하는 값** — 다르면 설치가 덜 된 것입니다.

| 명령 | 나와야 하는 것 |
|---|---|
| `exempt-fixture.md` 검사 | `오류 0 · 주의 0` |
| `violation-fixture.md` 검사 | `오류 10 · 주의 5` |
| `install.py --check` | `같음 17 · 다름 0 · 없음 0` |
| 시험 | `OK` · 건너뛰기 14건은 정상 |

**건너뛰기 14건이 정상인 까닭** — 작성자 기계에만 있는 연구 자료(사내 문서 복사본)를 대조하는 시험입니다. 검사기와 스킬을 재는 시험은 전부 돕니다.

**두 시료가 짝인 까닭** — 위반을 잡는 능력만 재면 「전부 지적」이 만점이 됩니다. 겉모습이 같은 정당한 표기 20종을 함께 돌려야 규칙이 쓸 만한지 갈립니다.

## 설치 세 갈래

받으시는 분이 어디까지 원하시는지에 따라 고르시면 됩니다. 위에서부터 가볍습니다.

| 갈래 | 되는 일 | 받는 것 |
|---|---|---|
| **파일 하나** | 명령줄로 문서 검사 | `assets/doc-style-check.py` 70KB 안팎 · 의존성 0 |
| **스킬 포함** | Claude Code 가 문서를 낼 때 문맥까지 읽어 고침 | `python install.py` |
| **훅 포함** | 발행 직전에 자동으로 걸림 | `python install.py --hooks` |

**파일 하나만 쓰는 법** — 저장소를 받으실 것도 없이 그 파일만 내려받으시면 됩니다.

```
python doc-style-check.py <파일…|디렉터리> [-v]
```

**훅이 하는 일** — Artifact 발행과 Edit·Write 뒤에 검사가 돌아 위반을 그 자리에서 알립니다. `--hooks` 는 `~/.claude/settings.json` 을 고치므로 백업을 먼저 뜹니다.

## 갈래를 골라 쓰기

**조직마다 문서 관행이 다름** — 표 머리 「비고」는 공문서 표의 표준 관례이고, 발표 대본은 산문이 정상입니다. 갈래를 끄거나 등급을 바꾸실 수 있습니다.

**기본으로 꺼진 갈래 하나** — 「반말 서술형」. 반말 자체는 잘못이 아니라서 꺼 두었습니다(실측 2026-09-08: 작업 기록과 규칙 문서는 서술 문장의 90%, 업무 보고서는 63%가 반말이고 그게 정상). **사람에게 내보이는 홍보·안내 자료에서만** `on = ["반말 서술형"]` 으로 켭니다.

```
python assets/doc-style-check.py --list-rules      # 갈래 29종 · 묶음 5종
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

**판정 3단계** — 「검사 불가」는 합격이 아니라 **안 본 것**입니다. 값 슬롯을 못 찾은 파일이 조용히 통과하면 아무도 그 문서를 다시 안 봅니다.

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
| `hooks/` | 발행 직전 검사 · 겹 역슬래시 차단 · 매일 건강 검사와 GitHub 반영 확인 |
| `install.py` · `repo_paths.py` | 설치와 경로 해석 |
| `scripts/check_publish_safety.py` | 공개하면 안 되는 것이 섞였는지 · CI 가 같이 돎 |
| `tests/` | 시험 파일 49개 · 시험 300여 건 |
| `docs/` | 설계·결정·조사 기록 |
| `data/` | 사람 판정 · 회귀 시료 · 받은 사례 |
| `runs/` | 실행별 입력·결과·요약 |

**정본이 여기 있음** — 예전에는 `~/.claude/` 가 정본이고 이 저장소가 그것을 불러다 썼습니다. 저장소만 받으신 분이 아무것도 못 돌려서 방향을 뒤집었습니다. 설치본을 직접 고치면 `tests/test_installed_copy_matches.py` 가 잡습니다.

**고친 것이 GitHub 까지 가는지도 봅니다** — 「설치본과 정본이 같다」와 「저장소가 GitHub 과 같다」는 다른 말입니다. 하루 첫 세션에 도는 점검이 정본 미커밋과 안 밀린 커밋을 함께 봅니다(`hooks/korean-gate-daily-check.py`). 깨끗하면 아무 말도 안 합니다.

## 라이선스

**MIT** — `LICENSE` · 받아서 고쳐 쓰고 다시 배포하셔도 됩니다

**심긴 서체는 별도** — 사례집(`docs/showcase.html`)에 들어 있는 서체 「Doc KR」은 MIT가 아니라 **SIL Open Font License 1.1** 입니다. Pretendard 1.3.9 의 KS X 1001 서브셋이고, 저작권자가 넷입니다. 전문은 `licenses/OFL-1.1.txt` · 상세는 `NOTICE`.

**보내 주시는 사례와 코드** — 저장소와 같은 MIT 조건으로 들어갑니다. 자세히는 `CONTRIBUTING.md`.

## 설계 문서

- [사용 안내](docs/user-guide.md) — 설치·실행·결과 읽는 법
- [시스템 구조와 역할](docs/architecture.md) — 부품·실행 시점·되먹임
- [현재 상태](docs/status.md)
- [판단이 필요한 것](docs/decisions-pending.md)
- [기존 검사기 조사](docs/existing-tools.md)
- [외부 한국어 작성 도구 검토](docs/external-korean-tools-review.md)
- [사용자 문체 피드백 반영](docs/user-feedback-workflow.md)
- [인수인계 설계](docs/design-handoff.md) — 2026-08-24에 멈춘 창립 문서 · 현재 상태 아님
