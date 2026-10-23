"""판정 규칙 축약본 — 판정 기준과 예시는 두고 경위(날짜, 사용자 발언 인용, 실측 경과)만 걷어 낸다.

im-not-ai 2.3.2 의 「진단 슬림 인덱스」(분류표 74.8KB → 판정에 필요한 정의와 시그니처 13KB, 결정적 생성)를
본뜬 실험. 결정적이고 다시 돌려도 같은 글을 낸다. 판정기에 넣기 전에 정확도를 함정 운반 문서로 견준다.

    python -X utf8 runs/judge-rules-slim-20261023/slim.py      # 크기와 걷어 낸 문장 수
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: 경위 문장 표지 — 판정 기준이 아니라 「언제 누가 왜 넣었나」를 말하는 문장
HISTORY = re.compile(
    r"20\d\d-\d\d-\d\d|사용자 말로|사용자가 [^.]{0,20}짚|사용자 「|실측|재발|회차|인계|넘긴 것이다|"
    r"판정 기록에서|세션이 [^.]{0,10}넘|점검표|여섯 차례|(?:두|세|네) 번(?:째)?|측정 전|안 넣었다|"
    r"검사기에 넣지|이 판정문으로 잰 값")
#: 문장 끝 — 「」 안의 마침표에서 자르지 않는다
SENT = re.compile(r"(?<=[.다])\s+(?=[^\s」])")
#: 날짜가 든 괄호 덩어리
DATED_PAREN = re.compile(r"\s?\([^()]*20\d\d-\d\d(?:-\d\d)?[^()]*\)")


def split_sentences(body: str) -> list[str]:
    out, buf, depth = [], "", 0
    for ch in body:
        buf += ch
        depth += ch == "「"
        depth -= ch == "」"
        if depth <= 0 and ch == "." and buf.strip():
            out.append(buf)
            buf, depth = "", 0
    if buf.strip():
        out.append(buf)
    return out


def slim(text: str) -> tuple[str, int]:
    """(축약본, 걷어 낸 문장 수). 목록 머리(굵은 이름 — )와 「판정 —」 문장은 늘 남긴다."""
    dropped = 0
    out = []
    for line in text.splitlines():
        line = DATED_PAREN.sub("", line)
        m = re.match(r"^(\s*(?:[-*]|\d+\.)\s+\*\*[^*]+\*\*\s*(?:`[^`]*`\s*)*[:—-]?\s*)(.*)$", line)
        head, body = (m.group(1), m.group(2)) if m else ("", line)
        if not body.strip():
            out.append(line)
            continue
        keep = []
        for s in split_sentences(body):
            if "판정 —" in s or "⛔" in s or not HISTORY.search(s):
                keep.append(s)
            else:
                dropped += 1
        new = head + "".join(keep).strip()
        if new.strip() or not line.strip():
            out.append(new.rstrip())
    return "\n".join(out), dropped


def slim_hard(text: str) -> tuple[str, int]:
    """공격적 축약 — 목록 항목은 머리, 「판정 —」 문장, 「정상」을 말하는 문장만 남긴다(예문 대부분이 빠짐).
    목록 밖 줄(절 제목, 우선순위 표)은 경위만 걷어 낸 판과 같다."""
    dropped = 0
    out = []
    for line in slim(text)[0].splitlines():
        m = re.match(r"^(\s*(?:[-*]|\d+\.)\s+\*\*[^*]+\*\*\s*(?:`[^`]*`\s*)*[:—-]?\s*)(.*)$", line)
        if not m:
            out.append(line)
            continue
        keep = [s for s in split_sentences(m.group(2)) if "판정 —" in s or "정상" in s or "⛔" in s]
        dropped += len(split_sentences(m.group(2))) - len(keep)
        out.append((m.group(1) + "".join(keep).strip()).rstrip())
    return "\n".join(out), dropped


def current_rules() -> str:
    sys.path.insert(0, str(REPO / "scripts"))
    spec = importlib.util.spec_from_file_location("k", REPO / "scripts" / "probe_layer2_kinds.py")
    k = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(k)
    return k.rules_for("guided")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    now = current_rules()
    small, n = slim(now)
    print(f"지금 {len(now):,}자 → 축약 {len(small):,}자 ({1 - len(small) / len(now):.0%} 감소) · 걷어 낸 문장 {n}")
    Path(__file__).with_name("rules_slim.md").write_text(small, encoding="utf-8")
    hard, n2 = slim_hard(now)
    print(f"공격적 축약 {len(hard):,}자 ({1 - len(hard) / len(now):.0%} 감소) · 더 걷어 낸 문장 {n2}")
    Path(__file__).with_name("rules_hard.md").write_text(hard, encoding="utf-8")
