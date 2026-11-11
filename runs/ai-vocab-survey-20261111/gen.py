"""문체 지시 없이 AI 업무 문서를 만든다 — 모델 셋 × 문서 종류 열. 본문은 저장소 밖 작업 폴더에만 쓴다.

value-ai-docs-20261109 의 생성 경로(write_doc)를 그대로 쓴다 — Claude 는 시스템 지시 없음, GPT 는 빈 지시,
Gemini 는 로그인 파일만 둔 홈에서 실행(llm-playbook dc70788). 모델 호출은 모두 구독이다.

    python -X utf8 runs/ai-vocab-survey-20261111/gen.py <작업 폴더> <claude|gpt|gemini>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAIL = " 마크다운으로 1,000~1,500자. 문서 본문만 출력하세요."
TOPICS = {
    "weekly": "가상의 회사에서 사내 시험 자동화 도구를 만드는 개발팀의 주간 업무 보고서를 한국어로 써 주세요. 이번 주 한 일, 이슈, 다음 주 계획을 넣어 주세요.",
    "minutes": "가상의 회사에서 신규 결제 기능 출시 일정을 정하는 회의의 회의록을 한국어로 써 주세요. 참석자, 논의 내용, 결정 사항, 할 일을 넣어 주세요.",
    "incident": "가상의 회사에서 사내 서비스가 2시간 멈춘 장애의 장애 보고서를 한국어로 써 주세요. 경과, 원인, 영향, 재발 방지 대책을 넣어 주세요.",
    "proposal": "가상의 회사에서 고객 문의 응대에 AI 챗봇을 도입하자는 기획 제안서를 한국어로 써 주세요. 배경, 목표, 추진 방안, 일정, 기대 효과를 넣어 주세요.",
    "research": "가상의 회사에서 정적 분석 도구 세 가지를 비교한 기술 조사 보고서를 한국어로 써 주세요. 비교 기준, 결과, 권고를 넣어 주세요.",
    "notice": "가상의 회사에서 사내 보안 교육을 의무화한다는 전 직원 공지문을 한국어로 써 주세요. 일정, 대상, 방법, 문의처를 넣어 주세요.",
    "retro": "가상의 회사에서 6개월짜리 모바일 앱 개편 프로젝트를 마친 뒤 팀이 쓴 회고 문서를 한국어로 써 주세요. 잘된 점, 아쉬운 점, 다음에 바꿀 점을 넣어 주세요.",
    "review": "가상의 회사에서 로그인 모듈 코드 리뷰 결과를 정리한 문서를 한국어로 써 주세요. 주요 지적, 심각도, 조치 계획을 넣어 주세요.",
    "training": "가상의 회사에서 신입 개발자 4주 교육 계획서를 한국어로 써 주세요. 목표, 주차별 내용, 평가 방법을 넣어 주세요.",
    "status": "가상의 회사에서 사내 데이터 플랫폼 구축 프로젝트의 진행 현황 보고서를 한국어로 써 주세요. 진척, 위험, 필요한 의사결정을 넣어 주세요.",
}


def main() -> int:
    work, writer = Path(sys.argv[1]), sys.argv[2]
    s = importlib.util.spec_from_file_location("run", HERE.parent / "value-ai-docs-20261109" / "run.py")
    run = importlib.util.module_from_spec(s)
    s.loader.exec_module(run)
    (work / "docs").mkdir(parents=True, exist_ok=True)
    for topic, prompt in TOPICS.items():
        f = work / "docs" / f"{writer}-{topic}.md"
        if f.exists():
            continue
        try:
            text, info = run.write_doc(writer, prompt + TAIL)
        except Exception as e:  # 한 편이 실패해도 나머지는 만든다
            print(f"{writer}-{topic} 실패 {type(e).__name__}: {e}"[:300], flush=True)
            continue
        if not text.strip():        # 사용량 한도(429)면 빈 글이 rc 없이 돌아온다 — 빈 파일로 남기지 않음(첫 실행 GPT 10편)
            print(f"{writer}-{topic} 빈 답 {json.dumps(info, ensure_ascii=False)}", flush=True)
            continue
        f.write_text(run.imn.unfence(text).strip() + "\n", encoding="utf-8")
        print(f"{writer}-{topic}", json.dumps(info, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
