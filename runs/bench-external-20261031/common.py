"""비교 실험 공통 — 실행 결과 보관(이어 돌리기), 지적과 결함 구간 맞추기, 부트스트랩."""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import systems  # noqa: E402

DATA = Path.home() / ".local/share/korean-writing-qa/bench-external"


def hangul(text: str) -> int:
    return len(re.findall(r"[가-힣]", text))


def cached_run(name: str, lines: list[str], out: Path) -> dict:
    """한 시스템 × 한 문서 — 결과 파일이 있으면 다시 부르지 않음(실패한 것은 다시 부름)."""
    f = out / f"{name}.json"
    if f.exists():
        r = json.loads(f.read_text(encoding="utf-8"))
        if not r.get("error"):
            return r
    r = systems.run(name, lines, out / f"work-{name}").dict()
    out.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def quote_range(line: str, quote: str) -> tuple[int, int] | None:
    q = (quote or "").strip()
    if not q:
        return None
    i = line.find(q)
    if i < 0:   # 모델이 따옴표나 띄어쓰기를 조금 바꿔 인용한 경우 — 공백을 무시하고 다시 찾음
        squeeze = re.sub(r"\s+", "", q)
        flat, pos = [], []
        for k, ch in enumerate(line):
            if not ch.isspace():
                flat.append(ch)
                pos.append(k)
        j = "".join(flat).find(squeeze)
        if j < 0 or not squeeze:
            return None
        return pos[j], pos[j + len(squeeze) - 1] + 1
    return i, i + len(q)


def overlaps(a: tuple[int, int], b: tuple[int, int], slack: int = 2) -> bool:
    return a[0] < b[1] + slack and b[0] < a[1] + slack


def finding_range(f: dict, line: str) -> tuple[int, int] | None:
    if f.get("span"):
        a, b = f["span"]
        return a, max(b, a + 1)
    return quote_range(line, f.get("quote", ""))


def apply_fixes(line: str, fixes: list[dict]) -> str:
    """수정안을 뒤에서부터 적용 — 인용을 못 찾는 수정안은 건너뜀."""
    spots = []
    for f in fixes:
        if f.get("fix") is None:
            continue
        r = quote_range(line, f.get("quote", ""))
        if r:
            spots.append((r, str(f["fix"])))
    spots.sort(key=lambda x: x[0][0], reverse=True)
    last = len(line) + 1
    for (a, b), fix in spots:
        if b > last:        # 겹치는 수정안은 앞의 것만
            continue
        line = line[:a] + fix + line[b:]
        last = a
    return line


def boot(values_by_doc: dict[str, tuple[float, float]], n: int = 10000, seed: int = 7) -> tuple[float, float, float]:
    """비율 = 합(분자)/합(분모) 을 문서 단위로 다시 뽑아 95% 구간."""
    keys = list(values_by_doc)
    if not keys:
        return float("nan"), float("nan"), float("nan")
    num = sum(v[0] for v in values_by_doc.values())
    den = sum(v[1] for v in values_by_doc.values()) or 1
    rng = random.Random(seed)
    stats = []
    for _ in range(n):
        s = [values_by_doc[rng.choice(keys)] for _ in keys]
        d = sum(x[1] for x in s)
        stats.append(sum(x[0] for x in s) / d if d else 0)
    stats.sort()
    return num / den, stats[int(0.025 * n)], stats[int(0.975 * n) - 1]


def boot_diff(a: dict[str, tuple[float, float]], b: dict[str, tuple[float, float]], n: int = 10000,
              seed: int = 7) -> tuple[float, float, float]:
    """같은 문서 묶음에서 두 시스템 비율의 차이(a−b) — 짝지은 부트스트랩."""
    keys = [k for k in a if k in b]
    rng = random.Random(seed)

    def ratio(src, ks):
        d = sum(src[k][1] for k in ks)
        return sum(src[k][0] for k in ks) / d if d else 0
    point = ratio(a, keys) - ratio(b, keys)
    stats = []
    for _ in range(n):
        ks = [rng.choice(keys) for _ in keys]
        stats.append(ratio(a, ks) - ratio(b, ks))
    stats.sort()
    return point, stats[int(0.025 * n)], stats[int(0.975 * n) - 1]


def pct(x: float) -> str:
    return f"{100 * x:.0f}%"
