"""2층에 넘긴 갈래를 2층이 실제로 잡는지 호출로 확인한다.

**무엇을 가르나.** 2026-09-16 에 기계로 못 가르는 열 갈래를 판단 층에 넘기고
`finalize-korean-document` 9단계에 적었다. **적었다는 것과 거기서 잡힌다는 것은
다른 말이다.** 이 저장소가 되풀이해 걸린 실패가 「규칙을 썼다 ≠ 규칙이 적용된다」다.

`probe_layer2_exemption.py` 는 **고치지 말라**는 예외가 지켜지는지 본다.
이쪽은 반대로 **고치라**고 적은 것이 잡히는지 본다.

**두 갈래로 부른다 — 차이가 곧 적어 둔 것의 값이다**

| 갈래 | 프롬프트에 넣는 것 | 재는 것 |
|---|---|---|
| `blind` | 핵심 규칙만 | 안 적어도 잡나 |
| `guided` | 핵심 규칙 + 9단계 열 갈래 | 적으면 더 잡나 |

**순환을 끊는 장치**

- 운반 문서는 1층에서 **오류 0 · 주의 0** 이다 — 짚는 것은 전부 2층 몫이다
- 어느 줄이 심은 것인지, 몇 건인지 알려 주지 않는다
- 시험이라는 사실도 알려 주지 않는다 — 발행 직전 호출과 같은 모양이다
- 정답은 대장에서 읽어 온다. 여기 적어 두면 두 곳이 되고, 두 곳이면 한쪽이 낡는다

**재현율만 잰다 · 정확도는 안 잰다.** 운반 문서의 나머지 줄은 이 저장소가 쓴
글이라, 심지 않은 곳을 짚은 것이 헛짚음인지 못 본 진짜인지 가릴 사람이 없다.
심은 열일곱 밖의 지적은 **세지 않고 그대로 보여 준다.**

    python -X utf8 scripts/probe_layer2_kinds.py [--arm blind|guided|both]
                                                 [--model sonnet] [--json 경로]
    python -X utf8 scripts/probe_layer2_kinds.py --from-json 경로

갈래당 호출 1회 · `claude-agent-sdk` OAuth(구독·크레딧 풀 · 과금 키 아님)

**2026-09-17 실측 · sonnet · temperature 0 · 운반 문서 두 벌 · 벌마다 두 회차**

운반 문서를 두 벌 돌렸다. 첫 벌은 대장 17건만, 둘째 벌은 **예비 예문 11건을
더** 심은 것이다. 예비는 9단계가 다루는 갈래인데 **규칙이 인용하지 않은** 예문이라,
「적힌 글자를 되찾나」와 「갈래를 알아보나」를 처음으로 갈라 낸다.

| 재는 것 | blind | guided |
|---|---|---|
| 대장 13건 · 까닭까지 · 17건 운반 | 0 · 0 | 11 · 11 |
| 대장 13건 · 까닭까지 · 29건 운반 | 0 · 0 | **10 · 7** |
| 예비 8건(의심 뺀 것) · 까닭까지 | 0 · 0 | **4 · 4** |

- **적어 두면 인용 안 한 같은 갈래도 절반쯤 알아본다** — 의심 뺀 예비 8건에서
  두 회차 다 4건. blind 는 두 회차 다 0이다. 9단계는 예시 목록으로만 도는 것이
  아니다. 다만 **절반은 못 잡는다.**
- **갈래마다 다르다**(의심 뺀 것 · 1차·2차) — 홀로 선 「자리」 1·1 / 1건 ·
  사물을 사람처럼 1·1 / 2건 · 동사구로 품 1·2 / 3건 · 진행형 1·0 / 2건.
  두 회차 다 잡은 것은 H-02·H-09·H-12 셋이다.
- **⚠️ 운반 문서를 늘리자 대장 재현율이 떨어졌다**(11·11 → 10·7). 심은 것이
  17개에서 29개로 늘자 놓치는 것이 생긴다 — **긴 문서에서 2층이 약해진다**는
  뜻이므로 회수율을 문서 길이와 함께 읽어야 한다.
- **blind 는 표현을 짚어도 까닭이 안 맞는다** — 두 벌 네 회차 전부 0이다.
  「업무에서 쓰는 말로 쓰기」·「막연한 비유 줄이기」 같은 이웃 규칙으로 걸린다.
  **표현만 보는 잣대로 기준선을 삼으면 같은 것을 재지 않는 둘을 견주게 된다.**
- **음성 대조** — 「고치지 않는 검사기입니다」는 예비에서 뺐다(검사기는 실제로
  안 고친다 · 결함이 아니다). 운반 문서에는 남겨 두었고 **두 갈래 다 안 짚었다.**
- **예비는 이 저장소가 지어낸 것이다.** 못 잡은 것이 예문 탓일 수 있어 셋에
  `doubt` 를 달았다. H-05 는 두 갈래 다 짚되 이웃 규칙 이름(「압축한 명사구
  풀기」)으로 냈다 — 표현은 맞고 까닭이 다른 경우다.

**정답이 바뀌면 `--from-json` 으로 다시 센다 — 부르지 않는다.** 2026-09-17 에
대장의 한 줄을 고치자 재현율이 11 에서 12 로 올랐다. 지적은 그대로였고 정답만
틀렸던 것이라 다시 부를 까닭이 없었다. 채점이 틀렸을 때 모델을 다시 부르면
**바뀐 것이 정답인지 모델인지 못 가른다.**
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import repo_paths  # noqa: E402

SKILL = repo_paths.SKILL
RULES = SKILL / "references" / "core-rules.md"
SKILL_MD = SKILL / "SKILL.md"
LEDGER = REPO_ROOT / "data" / "cases" / "flagged-rounds.jsonl"
# 운반 문서는 **시험 자료**라 tests 아래 둔다. data/raw 는 진짜 원문이 사는
# 곳이고 통째로 무시된다 — 거기 두면 공유받은 사람에게 안 간다.
CARRIER = (REPO_ROOT / "tests" / "fixtures" / "layer2-kinds" / "carrier.md")
HELD_OUT = CARRIER.parent / "held-out.jsonl"

#: 9단계를 제목으로 찾는다 — 번호로 찾으면 단계가 밀릴 때 조용히 엉뚱한 데를 읽는다
STEP_TITLE = "검사기가 못 잡는 것을 직접 찾는다"

SYSTEM = """당신은 한글 업무 문서를 전달 전에 최종 점검한다.

아래 규칙을 읽고, 주어진 문서에서 고쳐야 할 표현을 찾는다.

{rules}

## 내는 형식

JSON 배열 하나만 낸다. 다른 말은 붙이지 않는다.

[{{"line": 줄번호, "phrase": "고칠 표현 원문 그대로", "category": "규칙 이름",
   "fix": "고친 말", "why": "한 줄 근거"}}]

고칠 것이 없으면 빈 배열 []을 낸다."""

USER = """다음 문서를 점검한다. 줄 번호는 1부터 센다.

```
{document}
```"""


def load_client():
    """정본은 `llm_playbook.backends` 하나다 — 옛 경로는 위임 shim 이다."""
    from llm_playbook.backends.claude_sdk import (
        call_messages, parse_json_from_text)
    return call_messages, parse_json_from_text


def step_body(text: str, title: str) -> str:
    """그 단계의 머리글부터 다음 단계 번호 앞까지를 떼어 낸다."""
    m = re.search(rf"^(\d+)\. {re.escape(title)}", text, re.M)
    if m is None:
        sys.exit(f"스킬에 「{title}」 단계가 없다 — 제목이 바뀌었으면 여기도 고친다")
    rest = text[m.end():]
    nxt = re.search(r"^\d+\. ", rest, re.M)
    body = (rest[:nxt.start()] if nxt else rest).strip()
    # 제목 뒤에 이어지는 문장의 마침표가 앞에 남는다 — 떼어 낸다
    return body.lstrip('. ')


def rules_for(arm: str) -> str:
    """그 갈래가 실제로 받는 규칙 글 전체."""
    text = RULES.read_text(encoding="utf-8")
    if arm == "guided":
        text += ("\n\n## 줄 하나만 봐서는 못 가르는 것\n\n"
                 + step_body(SKILL_MD.read_text(encoding="utf-8"), STEP_TITLE))
    return text


def cited_texts(arm: str = "guided") -> set[str]:
    """그 갈래의 규칙이 **글자 그대로 인용한** 표현을 모은다.

    인용된 것을 맞히는 데는 갈래를 알아볼 필요가 없다 — 적힌 글자를 문서에서
    되찾으면 된다. 그래서 인용된 것과 아닌 것을 섞어 한 숫자로 내면 **적어 둔
    것의 값이 부풀려진다.** 굵게 표시를 뺀 뒤 견준다(「담기는 **단계**」).

    **갈래마다 따로 본다**(2026-09-17 고침). 처음에는 9단계만 봤는데
    `core-rules.md` 도 넷을 인용한다. blind 는 9단계를 안 보므로 그 인용을
    blind 몫으로 세면 **본 적 없는 예문을 인용으로 세는 것**이 된다.
    """
    flat = rules_for(arm).replace("*", "")
    return {i["text"] for i in planted() if i["text"] in flat}


def planted() -> list[dict]:
    """대장에서 2층 몫만 읽어 온다 — 정답을 여기 적지 않는다."""
    rows = []
    with LEDGER.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                if row.get("owner") == "2층":
                    row["source"] = "대장"
                    rows.append(row)
    return rows


def held_out() -> list[dict]:
    """규칙이 **인용하지 않은** 같은 갈래의 예문.

    대장과 섞지 않는다 — 대장은 사용자가 짚어 준 것이고 이쪽은 같은 갈래로
    지어낸 것이다. 섞으면 「사람이 짚은 것」의 수가 부풀려진다. 지어낸 것이라
    **못 잡았을 때의 증거 무게가 대장 쪽보다 가볍다.**
    """
    rows = []
    if not HELD_OUT.is_file():
        return rows
    with HELD_OUT.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                row["flag_id"] = row.pop("id")
                row["source"] = "예비"
                rows.append(row)
    return rows


def carrier_sha() -> str:
    """운반 문서의 지문 — 바뀐 문서에 옛 결과를 대고 세는 것을 막는다."""
    return hashlib.sha256(CARRIER.read_bytes()).hexdigest()[:16]


def numbered(text: str) -> str:
    return "\n".join(f"{n:>3} | {line}"
                     for n, line in enumerate(text.splitlines(), 1))


def line_of(document: str, sentence: str) -> int | None:
    for n, line in enumerate(document.splitlines(), 1):
        if sentence in line:
            return n
    return None


def score(items: list[dict], findings: list, document: str,
          cited: set[str] | None = None) -> dict:
    """심은 것을 잡았는지 기계로 가른다.

    **두 잣대를 함께 낸다** — 둘의 차이가 「짚기는 했는데 다른 까닭으로」다.

    - `엄격` — 지적한 표현이 심은 표현과 서로를 품음
    - `느슨` — 그 문장이 있는 줄을 짚기는 함
    """
    said = [f for f in findings if isinstance(f, dict)]
    cited = cited_texts() if cited is None else cited
    graded = [i for i in items if i.get("kind")]
    rows = []
    for item in items:
        want = item["text"].strip()
        want_line = line_of(document, item["sentence"])
        tight, loose = None, None
        for f in said:
            phrase = str(f.get("phrase", "")).strip()
            if phrase and (want in phrase or phrase in want):
                tight = f
                break
        for f in said:
            try:
                if want_line is not None and int(f.get("line", -1)) == want_line:
                    loose = f
                    break
            except (TypeError, ValueError):
                continue
        # 대장이 항목 이름을 적었으면 **까닭까지** 본다. 표현만 맞고 까닭이
        # 다른 것을 잡음으로 세면 같은 것을 재지 않는 둘을 견주게 된다 —
        # blind 의 5건이 전부 그랬다(다른 규칙으로 걸렸다).
        kind = item.get("kind")
        why_ok = None
        if kind and tight:
            why_ok = kind[:8] in str(tight.get("category", ""))
        rows.append({"flag_id": item["flag_id"], "text": want,
                     "line": want_line, "tight": tight, "loose": loose,
                     "cited": want in cited, "kind": kind, "why_ok": why_ok,
                     "source": item.get("source", "대장"),
                     "doubt": item.get("doubt")})

    hit_lines = {r["line"] for r in rows if r["loose"] or r["tight"]}
    extra = [f for f in said
             if str(f.get("line", "")).isdigit()
             and int(f["line"]) not in hit_lines]
    def tally(want_cited):
        pick = [r for r in rows if r["cited"] is want_cited]
        return {"total": len(pick),
                "tight": sum(1 for r in pick if r["tight"]),
                "loose": sum(1 for r in pick if r["loose"] or r["tight"])}

    return {"rows": rows, "extra": extra,
            "tight": sum(1 for r in rows if r["tight"]),
            "loose": sum(1 for r in rows if r["loose"] or r["tight"]),
            "why": sum(1 for r in rows if r["why_ok"]),
            "gradable": len(graded),
            "total": len(rows), "said": len(said),
            "인용": tally(True), "비인용": tally(False)}


def run_arm(arm: str, model: str, timeout: float, document: str,
            items: list[dict]) -> dict:
    call_messages, parse_json = load_client()
    # 조립은 `rules_for` 한 곳에서만 한다. 두 곳이면 인용 채점이 보는 글과
    # 실제로 보낸 글이 어긋나고, 어긋나도 아무 데서도 안 걸린다.
    rules = rules_for(arm)

    result = call_messages(
        model=model,
        system=SYSTEM.format(rules=rules),
        user=USER.format(document=numbered(document)),
        max_tokens=4000,
        temperature=0,
        timeout=timeout,
    )
    findings = parse_json(result.get("text") or "") or []
    if not isinstance(findings, list):
        findings = []
    out = score(items, findings, document, cited_texts(arm))
    out.update({"arm": arm, "model": result.get("model"),
                "cost_usd": result.get("cost_usd"), "findings": findings,
                "rules_chars": len(rules), "carrier_sha": carrier_sha()})
    return out


def report(out: dict) -> None:
    print(f"\n── {out['arm']} · {out['model']} · 지적 {out['said']}건 "
          f"· 규칙 {out['rules_chars']:,}자 · {out.get('cost_usd') or 0:.4f}달러")
    print(f"   심은 {out['total']}건 중 — 엄격 {out['tight']} · 느슨 {out['loose']}")
    if out["gradable"]:
        print(f"      그중 **까닭까지 맞음** {out['why']} "
              f"(항목 이름이 적힌 {out['gradable']}건 기준)")
    for tag in ("대장", "예비"):
        pick = [r for r in out["rows"] if r["source"] == tag]
        if not pick:
            continue
        why = sum(1 for r in pick if r["why_ok"])
        note = ("사용자가 짚음" if tag == "대장"
                else "규칙이 인용 안 함 · 갈래는 9단계에 있음")
        print(f"      {tag} {len(pick):>2}건 — 까닭까지 {why:>2} ({note})")
    else:
        print("      까닭은 안 봤다 — 대장이 항목 이름을 안 적는다 "
              "(note 에 「§9 「항목 이름」」까지 적으면 본다)")
    for tag in ("인용", "비인용"):
        s = out[tag]
        print(f"      이 갈래 규칙이 {tag} — {s['tight']} / {s['total']}")
    for r in out["rows"]:
        mark = "○" if r["tight"] else ("△" if r["loose"] else "✕")
        got = r["tight"] or r["loose"]
        why = f"  ← {str(got.get('category'))[:18]}" if got else ""
        tag = "인용" if r["cited"] else "  · "
        print(f"   {mark} {tag} {str(r['line']):>3}행  "
              f"{r['text'][:24]:<26}{why}")
    if out["extra"]:
        print(f"   심지 않은 곳 지적 {len(out['extra'])}건 (세지 않음)")
        for f in out["extra"][:8]:
            print(f"       {str(f.get('line')):>3}행  "
                  f"{str(f.get('phrase'))[:30]:<32}{str(f.get('category'))[:18]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", default="both",
                        choices=("blind", "guided", "both"))
    parser.add_argument("--from-json", type=Path, dest="from_json",
                        help="앞서 낸 결과를 다시 채점한다 — 모델을 안 부른다")
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--json", type=Path)
    # 기본 120초로는 모자랐다 — SDK 가 Claude Code 를 띄우는 첫 회차가 느리다
    parser.add_argument("--timeout", type=float, default=420.0)
    args = parser.parse_args()

    for path in (RULES, SKILL_MD, LEDGER, CARRIER):
        if not path.is_file():
            sys.exit(f"없는 파일: {path}")

    document = CARRIER.read_text(encoding="utf-8")
    items = planted() + held_out()
    if not items:
        sys.exit("대장에 2층 몫이 없다 — 잴 것이 없다")

    if args.from_json:
        saved = json.loads(args.from_json.read_text(encoding="utf-8"))
        now = carrier_sha()
        stale = {o.get("carrier_sha") for o in saved} - {now}
        if stale:
            sys.exit(
                f"⛔ 그때와 운반 문서가 다르다(그때 {sorted(stale)} · 지금 {now}).\n"
                "   줄이 밀려 조용히 틀린 수가 나온다 — 다시 부르십시오.")
        results = []
        for old in saved:
            fresh = score(items, old.get("findings") or [], document,
                          cited_texts(old.get("arm") or "guided"))
            fresh.update({k: old.get(k) for k in
                          ("arm", "model", "cost_usd", "findings",
                           "rules_chars", "carrier_sha")})
            fresh["cost_usd"] = 0.0          # 다시 부르지 않았다
            results.append(fresh)
    else:
        arms = ("blind", "guided") if args.arm == "both" else (args.arm,)
        results = [run_arm(a, args.model, args.timeout, document, items)
                   for a in arms]
    for out in results:
        report(out)

    print()
    if len(results) == 2:
        blind, guided = results
        print(f"합계 — 엄격 기준 {blind['tight']} → {guided['tight']} "
              f"({guided['tight'] - blind['tight']:+d}건)")
        print("   ⚠️ 합계로 읽지 않는다 — 규칙이 인용한 표현은 갈래를 알아볼 "
              "필요 없이 글자로 되찾힌다")

        # 갈래마다 인용 목록이 다르다. 나란히 놓으려면 **분모가 같아야** 한다 —
        # 심은 것을 「어느 갈래가 인용했나」로 갈라야 칸마다 같은 것을 잰다.
        cb, cg = cited_texts("blind"), cited_texts("guided")
        buckets = (
            ("둘 다 인용", lambda x: x in cb and x in cg),
            ("guided 만 인용", lambda x: x not in cb and x in cg),
            ("둘 다 비인용", lambda x: x not in cb and x not in cg),
        )
        by_arm = {r["arm"]: {row["text"]: row for row in r["rows"]}
                  for r in results}
        cells = {}
        for name, pick in buckets:
            texts = [r["text"] for r in blind["rows"] if pick(r["text"])]
            got = tuple(sum(1 for x in texts if by_arm[a][x]["tight"])
                        for a in ("blind", "guided"))
            cells[name] = (len(texts), got)
            if texts:
                print(f"   {name:<14} {len(texts):>2}건 — "
                      f"blind {got[0]} · guided {got[1]}")

        n_new, hit_new = cells["guided 만 인용"]
        print(f"\n   적어 둔 것의 값 — guided 가 새로 인용한 {n_new}건에서 "
              f"{hit_new[0]} → {hit_new[1]} (표현 기준)")

        # ── 번지나 — **예비 예문 · 까닭까지**로만 가른다.
        # 표현만 보는 잣대는 여기서 거꾸로 나온다(blind 가 더 많이 짚는데
        # 까닭이 하나도 안 맞는다). 인용 안 된 같은 갈래를 **알아보는지**가
        # 물음이므로 까닭이 맞아야 잡은 것이다.
        def spread(out):
            pick = [r for r in out["rows"] if r["source"] == "예비"]
            sure = [r for r in pick if not r.get("doubt")]
            return (sum(1 for r in pick if r["why_ok"]), len(pick),
                    sum(1 for r in sure if r["why_ok"]), len(sure))

        gb, nb, sb, mb = spread(blind)
        gg, ng, sg, mg = spread(guided)
        if ng == 0:
            print("\n⛔ 판정 불가 — 예비 예문이 없다. 9단계가 다루는 갈래의 "
                  "인용 안 된 예문을 운반 문서에 심어야 잰다.")
        else:
            print(f"   글자 밖으로 번지나 — 예비 {ng}건에서 까닭까지 "
                  f"{gb} → {gg}")
            print(f"      의심 뺀 {mg}건만 — {sb} → {sg}")
            if gg > gb:
                print(f"\n적어 두면 인용 안 한 같은 갈래도 알아본다 — "
                      f"{ng}건 중 {gg}건. 전부는 아니다.")
            else:
                print("\n적어도 인용 안 한 같은 갈래는 못 알아본다 — "
                      "9단계는 예시 목록으로만 작동한다.")
            print("   ⚠️ 예비 예문은 이 저장소가 지어낸 것이라 **못 잡은 것이 "
                  "예문 탓일 수 있다** — `doubt` 칸을 읽는다.")
    for out in results:
        if out["tight"] < out["loose"]:
            print(f"   ⚠️ {out['arm']}: 줄은 짚었는데 표현이 다른 것 "
                  f"{out['loose'] - out['tight']}건 — 까닭이 다를 수 있다")

    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2,
                                        default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
