#!/usr/bin/env python
"""Report changes to protected facts between an original and revised document.

**사라진 것과 값이 바뀐 것을 가른다.** 둘을 같이 다루면 중복 제거·군더더기 삭제·
영어 낱말을 한국어로 바꾸기처럼 `core-rules.md` 가 하라고 적어 둔 수정이 전부
막힌다. 반대로 뭉뚱그려 통과시키면 숫자가 조용히 사라진다. 그래서 세 상태로 낸다.

| 상태 | 무엇이 일어났나 | `--strict` |
|---|---|---|
| `preserved` | 보호 표현 그대로 | 통과 |
| `removed_content` | 사라지기만 함 · 새로 생긴 것 없음 | 막음 · `--expect-removed` 로 하나씩 인정 |
| `changed_protected_content` | 값이 바뀜 · 새로 생김 · 명시 보호 표현이 사라짐 | 막음 |

`--expect-removed` 를 하나씩 적게 한 이유는 **무엇을 지웠는지 말하게 하려는 것**이다.
통째로 넘기는 옵션을 두면 확인 없이 그것부터 붙이게 되고 게이트가 사라진다.

`--protect` 로 사람이 직접 지목한 표현은 사라지기만 해도 오류다. 지목한 이유가
그것을 지키려는 것이기 때문이다.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


# humanize 파이프라인이 수정본 끝에 붙이는 요약 주석. 본문이 아니라 처리 기록이라
# 여기 든 수치·식별자를 본문 사실로 세면 통과할 수정이 통째로 막힌다(실측 3건).
SUMMARY_COMMENT = re.compile(r"\n<!-- HUMANIZE-SUMMARY\n.*?\n-->\s*$", re.DOTALL)
# 사람이 읽는 글이 아닌 덩어리. **빼지 않으면 대조가 끝나지 않는다** — 한글 폰트를
# data URI 로 심은 HTML 은 그 한 줄이 560KB 이고, `SequenceMatcher` 가 거기서
# 멈춘다(2026-08-28 실측: 590KB 두 장에 2분 초과). 게다가 그 덩어리는 원본과
# 수정본이 똑같아 **변경률을 0 쪽으로 눌러** 실제로 고친 양을 작게 보이게 한다.
NON_PROSE = [
    re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE),
    re.compile(r"data:[^;,\s\"')]+;base64,[A-Za-z0-9+/=]+"),
]
AUTO_PROTECTED = re.compile(
    r"https?://[^\s<>()]+"
    r"|`[^`\n]+`"
    r'|"[^"\n]+"|“[^”\n]+”|\'[^\'\n]+\'|‘[^’\n]+’'
    r"|「[^」\n]+」|『[^』\n]+』"
    r"|(?<![A-Za-z0-9])\d[\d.,~:+/%-]*(?:[A-Za-z%]+)?(?![A-Za-z0-9])"
    r"|(?<![A-Za-z0-9])(?:[A-Z]{2,}[A-Z0-9_.+-]*|"
    r"[A-Za-z_][A-Za-z0-9_.+-]*\d[A-Za-z0-9_.+-]*|"
    r"[A-Za-z0-9_.+-]+/[A-Za-z0-9_./+-]+)(?![A-Za-z0-9])"
)


# 낱말이 다 남아 있어도 뜻이 달라지는 곳이 있다. 「최초 실행 보고서로 재평가
# 대상 없음」을 「최초 실행 보고서 · 재평가 대상 없음」으로 줄이면 인과가
# 사라지는데 낱말 대조는 통과시킨다(실측 · 사용자가 맥락 소실로 판정한 사례).
# 그래서 뜻을 지탱하는 표지의 증감을 따로 센다. **막지는 않고 알리기만 한다** —
# 좋은 수정에서도 8%가 걸리므로 게이트로 쓰면 정상 수정이 멈춘다.
MEANING_MARKERS = {
    # 조건 어미 「~면」은 낱말 안에도 흔하므로(측면·면접) 용언 어미 자리에서만 센다
    "인과·조건": re.compile(
        r"(므로|라서|때문|덕분|탓에|니까|려면|할 때|경우|따라서|이므로|어서"
        r"|[가-힣](?:으면|면)(?=[\s,·)\]]|$))"
    ),
    "계획·진행": re.compile(r"(예정|계획|할 것|하고 있|하는 중|중이|진행 중)"),
    "완료·단정": re.compile(r"(완료|했다|됐다|되었|끝냈|마쳤)"),
    "부정·범위": re.compile(r"(않|못하|없|아니|모두|전부|일부|대부분|만 )"),
    "추정·유보": re.compile(r"(보인다|보임|듯|가능성|추정|일 수 있|것으로)"),
    # 주어가 사라지면 누가 하는 일인지 사라진다 — 낱말은 그대로라 낱말 대조로는 안 잡힌다
    "행위 주체": re.compile(r"[가-힣]{2,}(?:이|가)(?=\s)"),
}


def marker_drops(original: str, revised: str) -> list[dict[str, object]]:
    """뜻을 지탱하는 표지가 줄어든 갈래를 낸다. 늘어난 것은 보지 않는다."""
    drops = []
    for name, pattern in MEANING_MARKERS.items():
        before = len(pattern.findall(original))
        after = len(pattern.findall(revised))
        if after < before:
            drops.append({"marker": name, "before": before, "after": after})
    return drops


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = SUMMARY_COMMENT.sub("", text)
    for pattern in NON_PROSE:
        text = pattern.sub("", text)
    return text


def protected_counts(text: str, explicit: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter(
        f"auto:{match.group(0)}" for match in AUTO_PROTECTED.finditer(text)
    )
    for token in explicit:
        if token:
            counts[f"explicit:{token}"] = text.count(token)
    return counts


def display_tokens(values: Counter[str]) -> list[str]:
    return sorted(key.split(":", 1)[1] for key in values.elements())


def measure(
    original: str,
    revised: str,
    explicit: list[str],
    expected_removed: list[str] | None = None,
) -> dict[str, object]:
    original = normalize(original)
    revised = normalize(revised)
    before = protected_counts(original, explicit)
    after = protected_counts(revised, explicit)
    removed = before - after
    added = after - before

    # 사람이 `--protect` 로 지목한 표현은 인정으로 풀리지 않는다. 풀리게 두면 위 표의
    # 「명시 보호 표현이 사라짐 = 오류」가 거짓 보증이 된다 — 지키라고 지목한 것이다.
    acknowledged: Counter[str] = Counter()
    for token in expected_removed or []:
        for key in list(removed):
            if key.startswith("explicit:"):
                continue
            if key.split(":", 1)[1] == token:
                acknowledged[key] = removed[key]
    unacknowledged = removed - acknowledged
    lost_explicit = Counter({
        key: count
        for key, count in unacknowledged.items()
        if key.startswith("explicit:")
    })

    if added or lost_explicit:
        status = "changed_protected_content"
    elif unacknowledged:
        status = "removed_content"
    else:
        status = "preserved"

    return {
        "status": status,
        "original_chars": len(original),
        "revised_chars": len(revised),
        "change_rate": 1.0 - SequenceMatcher(
            None, original, revised, autojunk=False
        ).ratio(),
        "protected_removed": display_tokens(unacknowledged),
        "protected_added": display_tokens(added),
        "acknowledged_removed": display_tokens(acknowledged),
        "explicit_protected": explicit,
        # 상태를 바꾸지 않는다 — 사람이 볼 곳만 가리킨다
        "meaning_marker_drops": marker_drops(original, revised),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("revised", type=Path)
    parser.add_argument("--protect", action="append", default=[])
    parser.add_argument("--protect-file", type=Path)
    parser.add_argument(
        "--expect-removed",
        action="append",
        default=[],
        metavar="표현",
        help="일부러 지운 보호 표현. 하나씩 적는다 — 무엇을 지웠는지 말하게 하려는 것이다.",
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    explicit = list(args.protect)
    if args.protect_file:
        explicit.extend(
            line.strip()
            for line in args.protect_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    result = measure(
        args.original.read_text(encoding="utf-8"),
        args.revised.read_text(encoding="utf-8"),
        list(dict.fromkeys(explicit)),
        list(dict.fromkeys(args.expect_removed)),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.strict and result["status"] != "preserved" else 0


if __name__ == "__main__":
    raise SystemExit(main())
