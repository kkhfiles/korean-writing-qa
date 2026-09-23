---
form: structured
---

# AI 한글 교정기

**AI가 쓴 한글을 업무에서 낼 수 있는 글로** — 규칙은 **사람이 쓴** 사내 보고서 600여 개로 실측 · 형식과 무관한 오류가 있던 문서 8% · 개조식 규약까지 켜면 33% · 받아서 그대로 쓸 수 있음

- **표시 색** — 주묵(朱墨) · 원고를 고칠 때 쓰던 붉은 먹
- **사례집** — <https://dispatchflow.cc/vermilion/> · 수정 전후 74쌍 · 눌러서 바로 봄 · 저장소 사본 [`docs/showcase.html`](docs/showcase.html)
- **사례 보내기** — [`CONTRIBUTING.md`](CONTRIBUTING.md) · 이슈로 문장 하나
- **필요한 것** — Python 3.11 이상 · 검사기는 파일 하나 · 형태소 판정만 `kiwipiepy`

## AI 에게 시키는 법

**넘기는 법** — 이 절을 그대로 복사해 Claude Code 나 그 밖의 코딩 에이전트에게 저장소 주소와 함께 전달

```
git clone https://github.com/<사용자>/korean-writing-qa.git
cd korean-writing-qa

# 1) 설치 없이 바로 도는지 확인 — 검사기는 파일 하나이고 없어도 돈다
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
| `violation-fixture.md` 검사 | `오류 16 · 주의 6` |
| `install.py --check` | `같음 27 · 다름 0 · 없음 0` (저장소 밖 목록을 둔 기계는 그만큼 늚 — 신원 목록 · 제품 이름 목록) |
| 시험 | `OK` · 건너뛰기와 「알려진 실패」가 함께 나오는 것이 정상 |

**`OK` 뒤에 붙는 것을 읽는 법** — 검사기와 스킬을 재는 시험은 전부 돕니다.

- **건너뛰기** — 그 기계에 없는 것을 대조하는 시험입니다. 작성자 기계에만 있는 연구 자료(사내 문서 복사본)를 보는 것, 그리고 대기 중인 지적이 없을 때 접히는 것입니다. **건수는 기계마다 다릅니다** — 받은 분 기계에서는 연구 자료가 없어 그만큼 더 건너뜁니다.
- **알려진 실패**(`expected failures`) — 아직 못 고친 구멍을 **지우지 않고 적어 둔 것**입니다. 하나하나에 무엇이 왜 안 되는지와 고칠 곳이 적혀 있습니다. **0 이 되는 것이 목표가 아닙니다** — 조용히 지우면 그 순간부터 아무도 안 봅니다.

⛔ **이 둘의 건수는 시험이 안 지킴** — 정상 변화로 움직이기 때문입니다(대기가 생기면 건너뛰기가 줄고, 구멍을 고치면 알려진 실패가 줍니다). 숫자를 못 박으면 정상 변화에 깨집니다.

**이 표를 지키는 시험** — `tests/test_readme_expected_values.py` 가 README 의 숫자를 읽어 실제로 돌려 봅니다. 예전에는 아무도 안 지켜서 `오류 10 · 주의 5`·`건너뛰기 14건`이 조용히 낡아 있었고, 그대로 따라 한 사람은 **설치가 깨졌다고 읽었을 것입니다**.

**두 시료가 짝인 까닭** — 위반을 잡는 능력만 재면 「전부 지적」이 만점이 됩니다. 겉모습이 같은 정당한 표기 20종을 함께 돌려야 규칙이 쓸 만한지 갈립니다.

## 설치 세 갈래

**고르는 기준** — 어디까지 필요한지에 따라 · 위에서부터 가벼움

| 갈래 | 되는 일 | 받는 것 |
|---|---|---|
| **파일 하나** | 명령줄로 문서 검사 | `assets/doc-style-check.py` 70KB 안팎 · 형태소 판정만 `kiwipiepy` |
| **스킬 포함** | Claude Code 가 문서를 낼 때 문맥까지 읽어 고침 | `python install.py` |
| **훅 포함** | 발행 직전에 자동으로 걸림 | `python install.py --hooks` |

**파일 하나만 쓰는 법** — 저장소를 받으실 것도 없이 그 파일만 내려받으시면 됩니다.

```
python doc-style-check.py <파일…|디렉터리> [-v]
```

**훅이 하는 일** — Artifact 발행과 Edit·Write 뒤에 검사가 돌아 위반을 그 자리에서 알립니다. `--hooks` 는 `~/.claude/settings.json` 을 고치므로 백업을 먼저 뜹니다.

## 갈래를 골라 쓰기

**조직마다 문서 관행이 다름** — 표 머리 「비고」는 공문서 표의 표준 관례이고, 발표 대본은 산문이 정상입니다. 갈래를 끄거나 등급을 바꾸실 수 있습니다.

**반말은 문서 전부에서 오류** — 「반말 서술형」은 모든 문서에 걸립니다(2026-09-23부터). 예전에는 업무 보고서에 반말이 흔하다는 이유로 꺼 두었는데, 흔하다는 것이 잘 쓴 글이라는 근거는 아니라서 켰습니다. Claude 만 읽는 지시 파일(`CLAUDE.md` · `AGENTS.md` · `SKILL.md` · `.claude/` · `skills/` 아래)만 빠집니다.

```
python assets/doc-style-check.py --list-rules      # 갈래 33종 · 묶음 5종
cp korean-qa.example.toml korean-qa.toml           # 고쳐서 문서 위에 둔다
```

```toml
[rules]
off  = ["스캔 가치 없는 라벨", "구조"]   # 낱개 이름과 묶음 이름을 섞어 적는다
warn = ["절단형 의심"]                    # 오류에서 주의로 내린다
err  = []                                 # 주의에서 오류로 올린다
```

- **찾는 방법** — 검사 대상에서 위로 올라가며 `korean-qa.toml` 을 찾는다 · `--rules <파일>` 로 지정
- **★ 끈 것은 반드시 출력에 적힘** — 맨 위와 합계 줄 양쪽. 안 보이면 「오류 0」이 통과인지 안 본 것인지 갈리지 않습니다.
- **발행 게이트** — `--no-rules` 로 설정을 무시하고 전부 봄
- **제품 이름은 저장소 밖 목록에 둠** — `data/catalog/local-brand-names.example.txt` 를 `local-brand-names.txt` 로 복사해 자사 제품 이름과 잘못 적은 꼴을 적음 · 복사본은 `.gitignore` 대상이라 안 올라감 · 목록이 없으면 그 갈래는 안 돌고 **안 봤다고 출력에 적음**
- **오타는 멈춤** — 모르는 갈래 이름을 적으면 rc 1. 조용히 넘기면 끄려던 검사가 안 꺼진 채 통과로 읽힙니다.

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

## 형식별 검사 범위

| 형식 | 검사하는 것 | 빼는 것 |
|---|---|---|
| Markdown | 일반 본문 | 앞부분 메타데이터 · 코드 블록 |
| HTML | 화면에 보이는 블록 | 스크립트 · 스타일 · 템플릿 · SVG |
| JSON · JSONL · YAML | 문자열 값 | 키 · 숫자 · 논리값 |
| properties | 속성값 | 키 · 주석 |
| 일반 텍스트 | 제어 문자 제거 후 각 줄 | 터미널 색상·제어 코드 |

- **산문 문서** — 머리말에 `form: prose`(HTML 은 `<meta name="form" content="prose">`) · 개조식 전제 검사가 꺼짐
- **검사 대상 아님** — PDF·PPTX 같은 변환 산출물. 편집 원본을 검사합니다.
- **의존성 둘** — `python -m pip install -r requirements.txt` · YAML 검사와 형태소 판정에 씀
- **형태소 판정** — 「보내는 때」(관형형 어미)와 「이제는 때가 됐다」(보조사)는 글자가 같아 품사 표지로만 갈립니다. `kiwipiepy` 가 없으면 그 갈래를 **글자만으로 좁게** 보고 **그 사실을 출력 맨 위와 합계에 적습니다** — 안 적으면 좁게 본 것이 통과로 읽힙니다.

## 저장소 구성

| 경로 | 담긴 것 |
|---|---|
| `assets/doc-style-check.py` | 1층 검사기 정본 |
| `skills/finalize-korean-document/` | 2층 스킬 정본 |
| `skills/fix-korean-finding/` | 지적 하나를 규칙까지 미는 유지보수 스킬 |
| `agents/` | 서브에이전트 정의 · 모델·사고 깊이·규칙 파일 적재 여부를 머리말로 고정 |
| `hooks/` | 발행 직전 검사 · 겹 역슬래시 차단 · 공개 저장소 푸시 게이트 · 매일 건강 검사와 GitHub 반영 확인 |
| `install.py` · `repo_paths.py` | 설치와 경로 해석 |
| `scripts/check_publish_safety.py` | 공개하면 안 되는 것이 섞였는지 · CI 가 같이 돎 |
| `tests/` | 규칙마다 잡을 것과 잡으면 안 될 것을 짝으로 · CI 가 매 푸시마다 전부 돌림 |
| `docs/` | 설계·결정·조사 기록 |
| `data/` | 사람 판정 · 회귀 시료 · 받은 사례 |
| `runs/` | 실행별 입력·결과·요약 |

**정본이 이 저장소** — 예전에는 `~/.claude/` 가 정본이고 저장소가 설치본을 불러다 썼습니다. 저장소만 받으신 분이 아무것도 못 돌려서 방향을 뒤집었습니다. 설치본을 직접 고치면 `tests/test_installed_copy_matches.py` 가 잡습니다.

**GitHub 까지 갔는지도 봄** — 「설치본과 정본이 같다」와 「저장소가 GitHub 과 같다」는 다른 말입니다. 하루 첫 세션에 도는 점검이 정본 미커밋과 안 밀린 커밋을 함께 봅니다(`hooks/korean-gate-daily-check.py`). 깨끗하면 아무 말도 안 합니다.

## 라이선스

**MIT** — `LICENSE` · 받아서 고쳐 쓰고 다시 배포해도 됨

**심긴 서체는 별도** — 사례집(`docs/showcase.html`)에 들어 있는 서체 「Doc KR」은 MIT가 아니라 **SIL Open Font License 1.1** 입니다. Pretendard 1.3.9 의 KS X 1001 서브셋이고, 저작권자가 넷입니다. 전문은 `licenses/OFL-1.1.txt` · 상세는 `NOTICE`.

**보내 주시는 사례와 코드** — 저장소와 같은 MIT 조건으로 들어갑니다. 자세히는 `CONTRIBUTING.md`.

## 설계 문서

- [사용 안내](docs/user-guide.md) — 설치·실행·결과 읽는 법
- [시스템 구조와 역할](docs/architecture.md) — 부품·실행 시점·되먹임
- [현재 상태](docs/status.md)
- [판단이 필요한 것](docs/decisions-pending.md)
- [재발방지 설계안](docs/prevention-design-20260915.md) — 탐지 넷과 호출 하나 · 외부 검토 반영
- [규칙 후보](docs/rule-candidates.md) — 규칙으로 올리기 전의 측정과 판단
- [DevRel 제안서 세션의 문체 피드백](docs/devrel-session-feedback-20260916.md) — 한 문서에서 나온 지적 전수 · 규칙 후보의 원자료
- [AI 오탐 소거 실험](docs/ai-filter-experiment-20260916.md) — 모델·사고 깊이별 실측
- [기존 검사기 조사](docs/existing-tools.md)
- [외부 한국어 작성 도구 검토](docs/external-korean-tools-review.md)
- [사용자 문체 피드백 반영](docs/user-feedback-workflow.md)
- [인수인계 설계](docs/archived/design-handoff.md) — 2026-08-24에 멈춘 창립 문서 · 현재 상태 아님
- **지난 기록** — [다중 형식 진단](docs/archived/diagnostic-003.md) · [스킬 구현 1차](docs/archived/skill-implementation-001.md) · [2차](docs/archived/skill-implementation-002.md) · 끝난 작업의 측정 기록
