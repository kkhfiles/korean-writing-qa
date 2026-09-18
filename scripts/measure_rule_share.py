"""사례집의 「가지별 비중」 표를 다시 잰다 — 손으로 재지 않는다.

**왜 있나.** 그 표는 2026-09-08 에 한 번 재고 스크립트를 안 남겼다. 아흐레 뒤
새 가지 다섯을 채우려 하니 **뭉치 정의가 아무 데도 없었다.** 업무 보고서 쪽은
값이 그대로 재현돼 뭉치를 되찾았지만(설정 저장소의 `reports`), 규칙·기록 쪽은
후보를 세 곳 넣어 봐도 서명이 3/8 밖에 안 맞아 **되찾지 못했다.**

이 저장소가 스스로 적어 둔 교훈이 「한 번 재고 마는 수치는 다음에 또 손으로
재야 한다」다. 그 교훈에 핵심 표가 걸렸다.

**뭉치를 이름으로 적어 둔다** — 다음 사람은 이름만 대면 된다.

    python -X utf8 scripts/measure_rule_share.py 보고서
    python -X utf8 scripts/measure_rule_share.py <경로…> --label 이름

**되찾은 것을 확인하는 법** — 페이지에 적힌 값과 견준다. 업무 보고서 뭉치는
2026-09-17 에 상위 여덟 값(59·9·7·6·4·3·2·2)이 **한 자리도 안 틀리고**
재현됐다. 서명이 어긋나면 그 뭉치가 아니다.
"""

from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import repo_paths  # noqa: E402

#: 이름 붙은 뭉치 — 경로는 저장소 밖에서 읽는다(공개 저장소에 개인 경로를 안 적는다)
CORPORA = {
    "보고서": ("reports",),
}

#: 뭉치를 되찾았는지 가르는 서명 — 2026-09-18 갱신
#
# ⚠️ **검사기를 고치면 이 값도 바뀐다.** 서명은 「같은 뭉치인가」를 묻는 것이지
#    「같은 검사기인가」를 묻는 것이 아닌데, 비중은 둘 다에 걸린다. 2026-09-18 에
#    「지시어 확인」을 마크다운으로 넓히자 지적이 2,405 → 2,479 건으로 늘어
#    **분모가 커지면서** 서술형 종결이 59 → 57%, 서술형 문단이 7 → 6% 로 내려갔다.
#    뭉치는 그대로였다. 갈래를 고친 날에는 여기도 같이 고친다.
SIGNATURE = {
    "보고서": {"서술형 종결": 57, "스캔 가치 없는 라벨": 9, "서술형 문단": 6,
               "절단형 의심": 6, "해설을 인용 부호로 씀": 4, "모호한 지칭": 3},
}

FINDING = re.compile(r"[❌⚠️ℹ️]\s*\[([^\]]+)\]")
FILE_LINE = re.compile(r"^── ", re.M)


def run_checker(paths: list[str]) -> str:
    done = subprocess.run(
        [sys.executable, "-X", "utf8", str(repo_paths.CHECKER), *paths, "-v"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return done.stdout or ""


def share(text: str) -> tuple[collections.Counter, int, int]:
    hits = collections.Counter(FINDING.findall(text))
    return hits, sum(hits.values()), len(FILE_LINE.findall(text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", nargs="+",
                        help=f"이름 붙은 뭉치({' · '.join(CORPORA)}) 또는 경로")
    parser.add_argument("--label", help="경로를 줄 때 붙일 이름")
    args = parser.parse_args()

    if len(args.target) == 1 and args.target[0] in CORPORA:
        label = args.target[0]
        root = repo_paths.config_path(*CORPORA[label])
        if root is None:
            print(repo_paths.NO_CONFIG_REPO)
            return 2
        paths = [str(root)]
    else:
        label = args.label or "이름 없음"
        paths = args.target

    hits, total, files = share(run_checker(paths))
    if not total:
        print("지적이 하나도 없습니다 — 경로가 맞는지 보십시오.")
        return 1

    print(f"뭉치 {label} · 문서 {files}개 · 지적 {total:,}건\n")
    print(f"{'가지':<26}{'건수':>7}{'비중':>7}")
    print("-" * 42)
    for name, n in hits.most_common():
        pct = 100 * n / total
        shown = f"{pct:.0f}%" if pct >= 0.5 else "<1%"
        print(f"{name:<26}{n:>7}{shown:>7}")

    want = SIGNATURE.get(label)
    if not want:
        return 0

    print("\n서명 대조 — 이 뭉치가 맞나")
    off = []
    for name, expected in want.items():
        got = round(100 * hits.get(name, 0) / total)
        mark = "○" if abs(got - expected) <= 1 else "✕"
        if mark == "✕":
            off.append(name)
        print(f"   {mark} {name:<24}적힌 값 {expected:>3}%  ·  지금 {got:>3}%")
    if off:
        print(f"\n⛔ {len(off)}가지가 어긋납니다 — **그 뭉치가 아닐 수 있습니다.**\n"
              "   페이지 값을 고치기 전에 뭉치를 먼저 확인하십시오.")
        return 1
    print("\n통과 — 되찾은 뭉치가 맞습니다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
