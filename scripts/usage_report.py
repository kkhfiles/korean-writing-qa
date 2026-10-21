"""2층 판정의 실사용 주간 집계 — 판정 기록을 읽기만 한다(모델을 안 부르고 기록을 안 고친다).

    python -X utf8 scripts/usage_report.py                 # 지난 7일
    python -X utf8 scripts/usage_report.py --since 2026-10-14 --json out.json

**왜 두나.** 캐시 유지 시간(5분 · 1시간) · 재판정 문맥 · 묶음 경고처럼 판정 비용을 바꾸는 결정을 실험 몇
번으로 정했다. 실제로 세션이 어떻게 부르는지는 판정 기록(`layer2_coverage.LOG`)에만 남는다. 그 기록을
같은 칸으로 매주 세어 결정이 실사용에서도 맞는지 본다.

**보는 것**

- 전체 판정(대상 줄 없음)과 재판정(대상 줄 있음)의 호출 수와 환산 비용 비중 — 금액이 없는 행(Codex)은 0으로
  더하지 않고 건수와 토큰 합으로 따로 센다
- 캐시를 하나도 못 읽은 재판정의 수와 비용 비중
- 호출 간격 — 바로 앞 호출(문서 무관)과 같은 문서의 앞 호출, 캐시 유지 시간별 · 5분 캐시의 손익 분기점과 나란히
- 첫 재판정 때 다른 줄에 남은 고칠 지적 수(`open_elsewhere`) — 0인 비율이 세션이 지적을 모아 처리한 비율의 대리 지표
- 실패한 호출 수 — 모델별
- 판정기가 기록을 못 써 임시 폴더에 대신 적은 줄(`layer2_coverage.fallback_log`)도 넣고 따로 표시

⛔ 기록에는 문서 경로가 들어 있다 — 이 집계는 경로를 내지 않는다(문서 수와 호출 수만).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import layer2_coverage as coverage  # noqa: E402

#: 100만 토큰당 달러 — 판정 기록의 환산 금액(`cost_usd`)을 토큰 칸으로 회귀해 얻은 값(2026-10-21).
#: 기록이 쌓여 단가가 달라 보이면 같은 방법으로 다시 구해 여기만 고친다.
WRITE_1H = 7.94
WRITE_5M = 5.00
READ = 0.20
#: 5분 캐시가 손해로 돌아서는 「1시간 캐시라면 한 번 쓴 뒤 5~60분 간격으로 다시 읽는 횟수」 — 그 읽기마다 5분
#: 캐시는 다시 써야 해 (5분 쓰기 − 읽기)를 더 내고, 쓰기 한 번마다 (1시간 쓰기 − 5분 쓰기)를 덜 낸다.
BREAKEVEN = (WRITE_1H - WRITE_5M) / (WRITE_5M - READ)
#: 이보다 재판정이 적으면 비중이 몇 건에 흔들린다 — 맨 위에 표본 부족을 알린다
MIN_REJUDGES = 20
SHORT, LONG = 300, 3600         # 초 — 5분 · 60분
BUCKETS = ("≤5분", "5~60분", "60분 초과", "앞 호출 없음")
NO_TTL = "기록 없음"


def stamp(row: dict) -> float:
    """호출 시각(초) — `when` 이 없는 옛 행은 `at`(이 PC 시각)으로."""
    if row.get("when") is not None:
        return float(row["when"])
    return datetime.fromisoformat(row["at"]).timestamp()


def read_rows(p: Path) -> list[dict]:
    if not p.is_file():
        return []
    out = []
    for l in p.read_text(encoding="utf-8").splitlines():
        if l.strip():
            try:
                out.append(json.loads(l))
            except ValueError:
                continue        # 쓰다 끊긴 줄 — 셈에서 뺀다
    return out


def load(log: Path) -> tuple[list[dict], Path]:
    """판정 기록과 대신 적은 줄 — 대신 적은 줄에는 `_spare` 표시. 이미 본 기록에 있는 줄은 한 번만."""
    spare = coverage.fallback_log(log)
    rows = read_rows(log)
    have = {json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows}
    for r in read_rows(spare):
        if json.dumps(r, ensure_ascii=False, sort_keys=True) not in have:
            rows.append(dict(r, _spare=True))
    return rows, spare


def is_rejudge(row: dict) -> bool:
    return row.get("targets") is not None


def priced(row: dict) -> bool:
    """환산 금액이 있는 성공 행 — Claude. Codex 는 설계상 금액이 비고 캐시 단가도 다르다."""
    return bool(row.get("ok")) and row.get("cost_usd") is not None


def tokens(row: dict) -> int:
    return sum(int(row.get(k) or 0) for k in ("input_tokens", "cache_write", "cache_read", "output_tokens"))


def share(part: float, whole: float) -> float | None:
    return part / whole if whole else None


def bucket(gap: float | None) -> str:
    if gap is None:
        return BUCKETS[3]
    return BUCKETS[0] if gap <= SHORT else BUCKETS[1] if gap <= LONG else BUCKETS[2]


def kinds(rows: list[dict]) -> dict:
    total = sum(r["cost_usd"] for r in rows if priced(r))
    out = {}
    for name, want in (("full", False), ("rejudge", True)):
        mine = [r for r in rows if is_rejudge(r) == want]
        cost = sum(r["cost_usd"] for r in mine if priced(r))
        free = [r for r in mine if r.get("ok") and r.get("cost_usd") is None]
        out[name] = {"calls": len(mine), "failed": sum(1 for r in mine if not r.get("ok")),
                     "cost_usd": round(cost, 4), "cost_share": share(cost, total),
                     "unpriced": {"calls": len(free), "tokens": sum(map(tokens, free))}}
    return out


def cold(rows: list[dict]) -> dict:
    """캐시를 하나도 못 읽은 재판정 — 금액 있는 재판정(Claude) 안에서."""
    mine = [r for r in rows if is_rejudge(r) and priced(r)]
    miss = [r for r in mine if not int(r.get("cache_read") or 0)]
    cost, total = sum(r["cost_usd"] for r in miss), sum(r["cost_usd"] for r in mine)
    return {"calls": len(miss), "of": len(mine), "share": share(len(miss), len(mine)),
            "cost_usd": round(cost, 4), "cost_share": share(cost, total)}


def gaps(all_rows: list[dict], since: float, until: float) -> dict:
    """호출 간격 — 금액 있는 성공 행(Claude)만. 앞 호출은 기간 밖에서도 찾는다(기간 첫 호출도 간격이 있게)."""
    calls = sorted((r for r in all_rows if priced(r)), key=stamp)
    last_any, last_doc = None, {}
    table = {"any": {}, "same_doc": {}}
    for r in calls:
        t, key = stamp(r), r.get("key") or r.get("doc")
        if since <= t < until:
            ttl = r.get("cache_ttl") or NO_TTL
            for kind, prev in (("any", last_any), ("same_doc", last_doc.get(key))):
                row = table[kind].setdefault(ttl, dict.fromkeys(BUCKETS, 0))
                row[bucket(None if prev is None else t - prev)] += 1
        last_any, last_doc[key] = t, t
    # 1시간 캐시라면 쓰는 호출(앞 호출 없음 · 60분 초과) 한 번당 5~60분 뒤 다시 읽는 호출 수
    reread = {}
    for ttl, row in table["same_doc"].items():
        writes = row[BUCKETS[2]] + row[BUCKETS[3]]
        reread[ttl] = share(row[BUCKETS[1]], writes)
    return {**table, "breakeven": round(BREAKEVEN, 4), "same_doc_reread_per_write": reread,
            "over": sorted(t for t, v in reread.items() if v is not None and v > BREAKEVEN)}


def open_elsewhere(rows: list[dict]) -> dict:
    """첫 재판정(다시 판정하는 줄만이 아닌 재판정)의 `open_elsewhere` — 행 단위(한 판정이 창 여럿이면 여러 행)."""
    first = [r for r in rows if is_rejudge(r) and r.get("ok") and not r.get("rejudge_only")]
    got = [int(r["open_elsewhere"]) for r in first if r.get("open_elsewhere") is not None]
    dist = Counter("0" if n == 0 else "1~2" if n <= 2 else "3~9" if n <= 9 else "10 이상" for n in got)
    return {"rows": len(first), "recorded": len(got), "missing": len(first) - len(got),
            "zero": dist["0"], "zero_share": share(dist["0"], len(got)),
            "buckets": {b: dist[b] for b in ("0", "1~2", "3~9", "10 이상")}}


def summarize(all_rows: list[dict], since: float, until: float | None = None) -> dict:
    until = time.time() + 1 if until is None else until
    rows = [r for r in all_rows if since <= stamp(r) < until]
    k = kinds(rows)
    rejudges = k["rejudge"]["calls"]
    return {"since": datetime.fromtimestamp(since).isoformat(timespec="seconds"),
            "until": datetime.fromtimestamp(until).isoformat(timespec="seconds"),
            "rows": len(rows), "spare_rows": sum(1 for r in rows if r.get("_spare")),
            "docs": len({r.get("key") or r.get("doc") for r in rows}),
            "small_sample": rejudges < MIN_REJUDGES,
            "kinds": k, "cold_rejudge": cold(rows), "gaps": gaps(all_rows, since, until),
            "open_elsewhere": open_elsewhere(rows),
            "failures": dict(Counter(str(r.get("model")) for r in rows if not r.get("ok")).most_common())}


def pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def render(d: dict, spare: Path | None = None) -> str:
    out = []
    if d["small_sample"]:
        out.append(f"⚠️ 표본 부족 — 결론 내지 말 것(재판정 {d['kinds']['rejudge']['calls']}건 · {MIN_REJUDGES}건 미만)")
    out.append(f"2층 판정 실사용 집계 · {d['since'][:10]} ~ {d['until'][:10]} · 호출 {d['rows']}행 · 문서 {d['docs']}개")
    if d["spare_rows"]:
        out.append(f"  ⚠️ 판정기가 기록을 못 써 대신 적은 줄 {d['spare_rows']}행 포함 — {spare}")
    out.append("  환산 금액은 API 단가 기준 — 구독이라 청구액이 아님")

    out += ["", "전체 판정과 재판정",
            f"  {'구분':<8}{'호출':>6}{'실패':>6}{'환산(달러)':>12}{'비용 비중':>10}  금액 없음"]
    for name, label in (("full", "전체 판정"), ("rejudge", "재판정")):
        a = d["kinds"][name]
        free = a["unpriced"]
        note = f"{free['calls']}건 · 토큰 {free['tokens']:,}" if free["calls"] else "—"
        out.append(f"  {label:<8}{a['calls']:>6}{a['failed']:>6}{a['cost_usd']:>12.2f}{pct(a['cost_share']):>10}  {note}")

    c = d["cold_rejudge"]
    out += ["", "캐시를 못 읽은 재판정(금액 있는 재판정 기준)",
            f"  {c['calls']}/{c['of']}건({pct(c['share'])}) · 환산 {c['cost_usd']:.2f}달러 · 재판정 비용의 {pct(c['cost_share'])}"]

    g = d["gaps"]
    for kind, label in (("any", "바로 앞 호출(문서 무관)과의 간격"), ("same_doc", "같은 문서의 앞 호출과의 간격")):
        out += ["", f"{label} — 금액 있는 호출 기준 · 캐시 유지 시간별",
                f"  {'유지 시간':<10}" + "".join(f"{b:>10}" for b in BUCKETS)]
        for ttl in sorted(g[kind]):
            row = g[kind][ttl]
            out.append(f"  {ttl:<10}" + "".join(f"{row[b]:>10}" for b in BUCKETS))
        if not g[kind]:
            out.append("  (호출 없음)")
    out += ["", f"5분 캐시 손익 분기점 — 1시간 캐시라면 한 번 쓴 뒤 5~60분 간격으로 다시 읽는 횟수 {g['breakeven']:.2f}"
                f" (쓰기 1시간 {WRITE_1H} · 5분 {WRITE_5M} · 읽기 {READ}달러/100만 토큰)"]
    for ttl, v in sorted(g["same_doc_reread_per_write"].items()):
        out.append(f"  {ttl:<10} 같은 문서 · 쓰기 한 번당 5~60분 다시 읽기 {'—' if v is None else f'{v:.2f}'}")
    for ttl in g["over"]:
        out.append(f"  ⚠️ {ttl} 행이 분기점을 넘음 — 이 사용 형태에서는 5분 캐시가 1시간보다 비쌈")

    o = d["open_elsewhere"]
    out += ["", "첫 재판정 때 다른 줄에 남은 고칠 지적(행 단위)",
            f"  기록 {o['recorded']}행 · 0인 비율 {pct(o['zero_share'])} · 기록 없음(옛 행) {o['missing']}행",
            "  " + " · ".join(f"{b}: {n}" for b, n in o["buckets"].items())]

    out += ["", "실패한 호출 — 모델별"]
    out += [f"  {m}: {n}" for m, n in d["failures"].items()] or ["  없음"]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="2층 판정 실사용 주간 집계 — 판정 기록을 읽기만 함")
    ap.add_argument("--log", type=Path, default=coverage.LOG, help="판정 기록(기본은 판정기가 쓰는 곳)")
    when = ap.add_mutually_exclusive_group()
    when.add_argument("--days", type=int, default=7, help="지난 며칠(기본 7)")
    when.add_argument("--since", help="이 날짜(YYYY-MM-DD · 이 PC 시각 0시)부터")
    ap.add_argument("--json", metavar="경로", help="집계를 JSON 으로도 씀 · - 면 표준 출력")
    a = ap.parse_args(argv)
    if a.since:
        try:
            since = datetime.strptime(a.since, "%Y-%m-%d").timestamp()
        except ValueError:
            print(f"⛔ 날짜 형식이 아닙니다 — {a.since}(YYYY-MM-DD)")
            return 2
    else:
        since = time.time() - a.days * 86400
    rows, spare = load(a.log)
    if not rows:
        print(f"기록 없음 — {a.log}")
        return 0
    d = summarize(rows, since)
    if a.json == "-":
        print(json.dumps(d, ensure_ascii=False, indent=1))
        return 0
    print(render(d, spare))
    if a.json:
        Path(a.json).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
