"""판정기 흔들림이 반복 수정 회차를 얼마나 늘리나 — 실사용 판정 기록에서 센다(모델 호출 없음).

  수정안 다시 고침: 판정기가 앞서 제안했고 글자 그대로 반영된 문구를, 같은 줄의 뒤 판정이 다시 고침
  되돌아감: 같은 줄의 문장이 A → B → A 처럼 앞 판으로 돌아감

판정 기록은 저장소 밖(~/.claude/state/korean-layer2-judge.jsonl)에 있고 문서 글이 들어 있다.
이 스크립트는 건수만 result.json 에 적는다.

python -X utf8 runs/judge-flipflop-20261109/measure.py
"""
import collections
import json
import os
from pathlib import Path

HERE = Path(__file__).parent
LOG = Path(os.path.expanduser("~/.claude/state/korean-layer2-judge.jsonl"))
SINCE = "2026-10-13"   # rejudge_only 와 targeted 기록이 생긴 날


def main():
    rows = [json.loads(l) for l in LOG.open(encoding="utf-8")]
    rows = [r for r in rows if r.get("ok") and r.get("at", "") >= SINCE]
    rows.sort(key=lambda r: r["when"])

    by_doc = collections.defaultdict(list)
    for r in rows:
        by_doc[r["key"]].append(r)

    lineages = 0          # 다시 판정된 줄(기준 판 하나)
    fixes_total = 0
    rejudge_fixes = 0
    self_contra = 0       # 자기 모순 지적 수
    self_contra_lines = 0
    revert_lines = 0
    back_to_root = 0
    cap_asks = 0
    for doc, rs in by_doc.items():
        parent = {}                                # 같은 줄의 판끼리 잇는다(먼저 본 글이 대표)

        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for r in rs:
            for t in r.get("targeted") or []:
                union(t.get("root") or t["text"], t["text"])
            for f in r.get("fixes") or []:
                text, phrase, fx = f.get("text") or "", f.get("phrase") or "", f.get("fix") or ""
                if phrase and fx and phrase in text:   # 수정안을 그대로 넣었으면 다음 판이 이 글
                    union(text, text.replace(phrase, fx, 1))
        seq = collections.defaultdict(list)        # 줄 → 시간순 글
        applied = collections.defaultdict(list)    # 줄 → 앞서 낸 수정안
        contra_in = set()
        rejudged = set()
        for r in rs:
            for t in r.get("targeted") or []:
                lin = find(t["text"])
                rejudged.add(lin)
                if not seq[lin] or seq[lin][-1] != t["text"]:
                    seq[lin].append(t["text"])
            for a in r.get("asks") or []:
                if a.get("category") == "재판정 상한":
                    cap_asks += 1
            for f in r.get("fixes") or []:
                fixes_total += 1
                text = f.get("text") or ""
                lin = find(text)
                if lin in rejudged:
                    rejudge_fixes += 1
                phrase = (f.get("phrase") or "").strip()
                for prev in applied[lin]:
                    if len(prev) < 4 or len(phrase) < 4 or prev not in text:
                        continue
                    # 앞 수정안 안을 짚었거나, 앞 수정안을 거의 그대로 다시 짚은 것만 센다
                    if phrase in prev or (prev in phrase and len(phrase) <= len(prev) + 8):
                        self_contra += 1
                        contra_in.add(lin)
                        break
                fx = (f.get("fix") or "").strip()
                if fx and "○" not in fx:
                    applied[lin].append(fx)
        lineages += len(rejudged)
        self_contra_lines += len(contra_in & rejudged)
        for lin in rejudged:
            s = [lin] + [x for x in seq[lin] if x != lin or True]
            seen = []
            rev = False
            for x in s:
                if seen and x != seen[-1] and x in seen:
                    rev = True
                    if x == lin:
                        back_to_root += 1
                    break
                if not seen or x != seen[-1]:
                    seen.append(x)
            revert_lines += rev

    result = {
        "이름": "판정기 흔들림이 반복 수정 회차를 늘리는 몫 — 실사용 판정 기록",
        "잰 때": "2026-11-09 · 모델 호출 없음",
        "기간": f"{SINCE} ~ {rows[-1]['at'][:10]}",
        "성공 호출": len(rows),
        "문서": len(by_doc),
        "다시 판정된 줄(기준 판 기준)": lineages,
        "지적(고칠 것) 전체": fixes_total,
        "그중 다시 판정된 줄에 달린 지적": rejudge_fixes,
        "앞서 반영한 수정안을 다시 고친 지적": self_contra,
        "그런 지적이 한 번 이상 난 줄": self_contra_lines,
        "되돌아간 줄(A → B → A)": revert_lines,
        "그중 기준 판으로 돌아간 줄": back_to_root,
        "재판정 상한으로 사람 확인에 오른 지적": cap_asks,
    }
    if lineages:
        result["수정안을 다시 고친 줄 비율"] = round(self_contra_lines / lineages, 3)
        result["되돌아간 줄 비율"] = round(revert_lines / lineages, 3)
    if rejudge_fixes:
        result["다시 판정된 줄의 지적 중 수정안을 다시 고친 비율"] = round(self_contra / rejudge_fixes, 3)
    (HERE / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
