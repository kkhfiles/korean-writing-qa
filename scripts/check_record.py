"""검사 통과를 **내용 해시에 묶어** 기록하고, 지금 내용이 통과했는지 답한다.

**왜 해시인가.** 「검사했다」만 기록하면 옛 판을 검사한 뒤 고쳐서 내보내는 길이
열린다(2026-09-16 외부 검토 지적). 기록을 파일 경로가 아니라 **그 순간의 내용**에
묶으면 한 글자만 고쳐도 기록이 안 맞는다.

**왜 단계를 나누나.** 한 문서가 지나야 하는 검사가 셋이고 잡는 것이 다르다.

| 단계 | 무엇을 잡나 | 누가 기록하나 |
|---|---|---|
| `structure` | 개조식·절단형·지어낸 명사구 — 표면 모양 | 게이트가 자동 |
| `words` | 업무 글에서 드문 낱말 — 빈도 | 2층 절차 5단계 |
| `judgment` | 문맥을 읽어야 갈리는 것 | 2층 절차 9단계 |

⛔ **시작을 완료로 세지 않는다.** 기록은 **판정과 함께** 남긴다 — 실패·중단도
완료로 세면 그 기록이 거짓이 된다.

    python -X utf8 scripts/check_record.py record <파일> --stage structure --verdict pass
    python -X utf8 scripts/check_record.py status <파일>
    python -X utf8 scripts/check_record.py status <파일> --require structure,words,judgment
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

HOME = os.path.expanduser("~")
STORE = os.environ.get("KOREAN_CHECK_RECORD") or os.path.join(
    HOME, ".claude", "state", "korean-check-pass.jsonl")

#: ★ `review` — **주의를 읽고 정상으로 판단했다**는 기록 (2026-09-18 사용자 결정)
#
#   주의는 「사람이 보고 판단하라」는 등급인데, 그 판단을 받아 줄 곳이 없었다.
#   발행 직전 검사가 주의 한 건만 있어도 `structure: fail` 로 적어, 오탐이라고
#   판단해도 **문구를 지우거나 게이트를 통째로 넘기는 것**밖에 길이 없었다
#   (외부 검토 2026-09-18 · 실측으로 재현). 「사람이 본다」고 해 놓고 본 결과를
#   적을 곳이 없으면 그 말은 빈말이다.
#
#   ⛔ **고무도장이 되지 않게 하는 것 둘.**
#     · 내용 해시에 묶인다 — 한 글자만 고쳐도 다시 판단해야 한다.
#     · **까닭을 반드시 적는다**(`--note`). 나중에 누가 무엇을 왜 통과시켰는지
#       되짚을 수 있어야 한다. 까닭 없는 승인은 받지 않는다.
#
#   ⛔ **오류에는 안 듣는다** — 오류는 사람 판단 대상이 아니다. 게이트는 오류가
#      하나라도 있으면 이 기록을 보지 않는다.
STAGES = ("structure", "words", "judgment", "review")
#: 기록이 이보다 오래되면 안 믿는다 — 규칙이 그 사이에 바뀌었을 수 있다.
STALE_DAYS = 14


def digest(path: str) -> str:
    """파일 내용의 해시. 줄 끝 차이는 무시한다 — 같은 글이기 때문이다."""
    with io.open(path, "rb") as f:
        body = f.read().replace(b"\x0d\x0a", b"\x0a")
    return hashlib.sha256(body).hexdigest()[:16]


def _first(*candidates: str) -> str | None:
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def rules_version() -> str:
    """검사기가 바뀌면 옛 통과 기록을 믿을 수 없다.

    ⛔ **어느 사본에서 부르든 같은 값이 나와야 한다.** 저장소본과 설치본이
       각자 자기 옆의 검사기를 재면 두 값이 갈려, 게이트가 적은 기록을 저장소의
       도구가 「규칙이 바뀌었다」며 버린다(2026-09-16 실측으로 걸렸다).
       그래서 **찾는 순서를 고정**한다 — 환경 변수 · 설치본 · 저장소 순.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    parts = []
    for env, rel in (("KOREAN_QA_CHECKER", "assets/doc-style-check.py"),
                     ("KOREAN_QA_KNOWN_WORDS", "data/catalog/known-words.jsonl")):
        p = _first(os.environ.get(env, ""),
                   os.path.join(HOME, ".claude", "assets", os.path.basename(rel)),
                   os.path.normpath(os.path.join(here, "..", rel)))
        if p:
            with io.open(p, "rb") as f:
                parts.append(hashlib.sha256(f.read()).hexdigest())
    return hashlib.sha256("".join(parts).encode()).hexdigest()[:12]


def load() -> list[dict]:
    if not os.path.exists(STORE):
        return []
    rows = []
    with io.open(STORE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def record(path: str, stage: str, verdict: str, note: str = "") -> dict:
    row = {"hash": digest(path), "path": os.path.abspath(path).replace(os.sep, "/"),
           "stage": stage, "verdict": verdict, "rules": rules_version(),
           "when": time.time(), "note": note}
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with io.open(STORE, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def status(path: str) -> dict:
    """지금 내용에 대해 단계별로 무엇이 남아 있나.

    ⚠️ **지금 내용**이 기준이다. 검사한 뒤 한 글자라도 고쳤으면 안 맞는다.
    """
    want, rules = digest(path), rules_version()
    now = time.time()
    out = {s: None for s in STAGES}
    for row in load():
        if row.get("hash") != want:
            continue
        if row.get("rules") != rules:
            continue                      # 검사기가 바뀌었다 — 옛 통과는 못 믿는다
        if now - float(row.get("when", 0)) > STALE_DAYS * 86400:
            continue
        stage = row.get("stage")
        if stage in out:
            # 같은 단계가 여러 번 기록되면 **나중 것**이 이긴다 — 고치고 다시 돌린 경우다
            out[stage] = row.get("verdict")
    return {"hash": want, "rules": rules, "stages": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="검사 통과를 내용 해시에 묶어 기록한다")
    sub = ap.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="한 단계의 판정을 남긴다")
    rec.add_argument("path")
    rec.add_argument("--stage", required=True, choices=STAGES)
    rec.add_argument("--verdict", required=True, choices=("pass", "fail"))
    rec.add_argument("--note", default="")

    st = sub.add_parser("status", help="지금 내용이 어느 단계까지 통과했나")
    st.add_argument("path")
    st.add_argument("--require", default="",
                    help="쉼표로 단계를 적으면 하나라도 통과가 아닐 때 rc 1")
    st.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if not os.path.exists(args.path):
        print(f"⛔ 파일이 없습니다: {args.path}")
        return 2

    if args.cmd == "record":
        # ⛔ **까닭 없는 승인은 받지 않는다** — 고무도장이 되면 이 기록은
        #    「넘기기」와 같아진다. 나중에 누가 무엇을 왜 통과시켰는지 남아야 한다.
        if args.stage == "review" and args.verdict == "pass" and not args.note.strip():
            print("review 통과에는 --note 로 까닭을 적어야 합니다 — "
                  "「무슨 주의를 왜 정상으로 봤나」")
            return 1
        row = record(args.path, args.stage, args.verdict, args.note)
        mark = "통과" if row["verdict"] == "pass" else "실패"
        print(f"기록 — {os.path.basename(args.path)} · {row['stage']} · {mark} "
              f"· 내용 {row['hash']}")
        return 0

    info = status(args.path)
    if args.json:
        print(json.dumps(info, ensure_ascii=False))
    else:
        print(f"{os.path.basename(args.path)} · 내용 {info['hash']} "
              f"· 규칙 {info['rules']}")
        for stage in STAGES:
            got = info["stages"][stage]
            mark = {"pass": "✅ 통과", "fail": "⛔ 실패", None: "— 기록 없음"}[got]
            print(f"   {stage:<10} {mark}")
    need = [s.strip() for s in args.require.split(",") if s.strip()]
    if need:
        missing = [s for s in need if info["stages"].get(s) != "pass"]
        if missing:
            print(f"\n⛔ 통과 기록이 없는 단계 — {' · '.join(missing)}")
            print("   지금 내용으로 검사를 다시 돌리고 기록하십시오.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
