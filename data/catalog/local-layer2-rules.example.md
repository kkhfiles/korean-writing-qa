---
form: prose
---

<!--
개인 판정 기준 — 예시

이 파일을 `local-layer2-rules.md` 로 복사해서 사용합니다.

    cp data/catalog/local-layer2-rules.example.md data/catalog/local-layer2-rules.md
    python install.py

복사본은 `.gitignore` 대상이라 저장소에 커밋되지 않습니다. `python install.py` 가
`~/.claude/data/catalog/` 로 복사해, 이 저장소 밖 프로젝트의 판정에도 적용합니다.
다른 곳에 두려면 환경 변수 `KOREAN_QA_LOCAL_RULES` 에 경로를 지정합니다.

2층 판정기(`scripts/judge_layer2.py`)가 문서를 판정할 때마다 이 글을 판정 원칙 뒤에 추가합니다.
우선순위는 「프로젝트에서 정한 용어와 문서 형식」과 같고, 공통 원칙과 충돌하면 이 기준을 따릅니다.

1층 개인 낱말 목록(`local-personal-words.tsv`)과 구분해 사용합니다.
- 동사 하나를 바꾸면 끝나는 것(「결함을 잡다 → 검출」): 낱말 목록
- 문맥을 봐야 판단할 수 있는 것(용어 정의, 소속 조직의 문서 관례): 이 파일

이 주석 안의 글은 판정기에 전달하지 않습니다. 아래 예시 줄의 주석 표시를 삭제하고 수정해 사용합니다.
-->

<!--
- **영문 제품 이름은 영문 그대로**: 문서에서 한글로 옮기거나 소리 나는 대로 적으면 지적함
- **고객 보고서의 「검증」과 「확인」 구분**: 시험을 실행해 결과를 낸 것만 「검증」, 눈으로 본 것은 「확인」
-->
