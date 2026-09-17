"""제품 이름 목록의 음차가 **다른 낱말 안에 묻히는지** 본다.

**왜 있나.** 검사기는 음차를 **평문 부분 일치**로 잡는다. 그래서 짧은 한글
음차가 더 긴 낱말 안에 들어가면 헛짚는다. 2026-09-17 에 예방용으로 넣은
「아콘」이 실문서에서 「우아콘(WOOWACON)」에 걸렸다 — 목록에 「겹치는 말은
없나」라고 적어 두고도 넣기 전에 확인하지 않았다.

**이 갈래는 오류 등급이다.** 헛짚으면 발행이 막힌다. 목록을 늘릴 때마다 돌린다.

**가르는 신호 — 음차 **앞**에 한글이 붙나.** 뒤에 붙는 것은 조사·어미라 정상이다
(「디베라에서」·「알리라가」). 앞에 붙으면 **다른 낱말의 뒷부분**일 수 있다
(「우아콘」의 「아콘」).

    python -X utf8 scripts/check_brand_list.py <문서 경로…> [--quiet]

겹침이 있으면 종료 코드 1. 목록이 없으면 그렇다고 적고 0 으로 끝난다 —
목록은 각자 기계에만 있으므로 없는 것이 정상이다.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import os
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import repo_paths  # noqa: E402

#: 글로 쓴 문서만 본다 — 실행 파일·자료 파일은 음차 판단에 쓸모없다
SUFFIXES = (".md", ".txt", ".html")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}


def load_brands() -> dict[str, str]:
    """검사기에서 그대로 가져온다 — 목록 읽는 규칙을 두 벌로 두지 않는다."""
    spec = importlib.util.spec_from_file_location("dsc", repo_paths.CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.brand_pairs()


def walk(paths: list[str]):
    for root in paths:
        if os.path.isfile(root):
            yield root
            continue
        for base, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                if name.endswith(SUFFIXES):
                    yield os.path.join(base, name)


def buried(text: str, word: str) -> Counter:
    """음차 **앞**에 한글이 붙은 자리 — 다른 낱말의 뒷부분일 수 있다."""
    out = Counter()
    for m in re.finditer(re.escape(word), text):
        if m.start() and re.match(r"[가-힣]", text[m.start() - 1]):
            start = max(0, m.start() - 14)
            out[" ".join(text[start:m.end() + 10].split())] += 1
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="글로 쓴 문서가 있는 경로")
    parser.add_argument("--quiet", action="store_true",
                        help="겹치는 것만 낸다")
    args = parser.parse_args()

    brands = load_brands()
    if not brands:
        print("제품 이름 목록이 없습니다 — 볼 것이 없습니다.\n"
              "   만들려면 data/catalog/local-brand-names.example.txt 를 "
              "local-brand-names.txt 로 복사하십시오.")
        return 0
    if not args.paths:
        print("문서 경로를 주십시오 — 자기 글에 대고 봐야 뜻이 있습니다.")
        return 2

    files = sorted(set(walk(args.paths)))
    blob = []
    for path in files:
        try:
            blob.append(io.open(path, encoding="utf-8", errors="ignore").read())
        except OSError:
            continue
    text = "\n".join(blob)
    print(f"문서 {len(files)}개 · {len(text):,}자 · 목록 {len(brands)}짝\n")

    bad = {}
    for word in sorted(brands):
        hits = buried(text, word)
        total = len(re.findall(re.escape(word), text))
        if hits:
            bad[word] = hits
        elif not args.quiet:
            print(f"   ○ {word:<14} {total:>4}회 · 묻힌 곳 없음")

    if not bad:
        print("\n통과 — 묻힌 음차 없음")
        return 0

    print()
    for word, hits in bad.items():
        print(f"   ⛔ {word} → 「{brands[word]}」 — 다른 낱말 안에 "
              f"{sum(hits.values())}곳")
        for sample, n in hits.most_common(3):
            print(f"        {sample[:66]}  ({n}회)")
    print("\n이 갈래는 **오류** 등급이라 헛짚으면 발행이 막힙니다.\n"
          "   목록에서 그 음차를 빼거나, 더 긴 표기로 바꾸십시오.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
