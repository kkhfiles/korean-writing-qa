"""지적을 둘로 가른다 — 문서 형식과 무관하게 틀린 것 · 개조식일 때만 걸리는 것.

**왜 갈랐나.** 사례집이 「문제의 크기」로 내세운 오류 문서 33%가 무엇으로 이뤄졌는지
아무도 세어 본 적이 없었다. 세어 보니 넷 중 셋이 개조식 규약이고, 개조식을 안 쓰는
곳에서 받아 돌리면 8%가 나온다. 읽는 사람이 **자기 숫자를 예측할 수 없는** 상태였다.

**가르는 기준은 검사기가 이미 들고 있다** — `FORM_ONLY_STRUCTURED` 는 머리말
`form: prose` 한 줄로 꺼지는 갈래다. 새 갈래가 늘면 여기도 따라 는다.
"""

import collections
import importlib.util
import json
import os
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("dsc", REPO / "assets" / "doc-style-check.py")
dsc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dsc)

COND = dsc.FORM_ONLY_STRUCTURED

#: 범위는 `measure.py` 와 같다 — 다르면 두 결과를 나란히 못 놓는다.
SKIP = {".git", "node_modules", "__pycache__", ".venv", "projects", "todos",
        "shell-snapshots", "backups", "file-history", "cache", "statsig", "runs", "data"}
REPORTS = pathlib.Path(os.environ.get("QA_REPORTS_DIR", "P:/github/claude-workflow/reports"))
CORPORA = {"보고서": [REPORTS], "규칙·기록": [pathlib.Path.home() / ".claude", REPO]}

print(f"개조식일 때만 걸리는 갈래 {len(COND)}종: {' · '.join(sorted(COND))}\n")

out = {"개조식 전용 갈래": sorted(COND)}
for name, roots in CORPORA.items():
    files = []
    for root in roots:
        if root.is_dir():
            for pat in ("*.md", "*.html"):
                files += [p for p in root.rglob(pat)
                          if not any(part in SKIP for part in p.parts)]
    files.sort()
    if not files:
        continue
    err_all = err_plain = any_all = any_plain = tot = cond = 0
    by_kind = collections.Counter()
    for f in files:
        scan = dsc.scan_md if f.suffix == ".md" else dsc.scan_html
        try:
            e, w, _ = scan(str(f), False, None)
        except Exception:                                       # noqa: BLE001
            continue
        ek = [it[1] if len(it) == 3 else it[0] for it in e]
        wk = [it[1] if len(it) == 3 else it[0] for it in w]
        tot += len(ek) + len(wk)
        for k in ek + wk:
            if k in COND:
                cond += 1
                by_kind[k] += 1
        err_all += bool(ek)
        err_plain += bool([k for k in ek if k not in COND])
        any_all += bool(ek or wk)
        any_plain += bool([k for k in ek + wk if k not in COND])
    n = len(files)
    out[name] = {
        "문서": n,
        "오류 문서 %": round(err_all * 100 / n),
        "오류 문서 % — 개조식 규약 뺀 뒤": round(err_plain * 100 / n),
        "지적 문서 %": round(any_all * 100 / n),
        "지적 문서 % — 개조식 규약 뺀 뒤": round(any_plain * 100 / n),
        "지적 총": tot, "개조식 규약 지적": cond,
        "개조식 규약 비중 %": round(cond * 100 / tot) if tot else 0,
        "갈래별": by_kind.most_common(),
    }
    d = out[name]
    print(f"{name}: 문서 {n} · 오류 문서 {d['오류 문서 %']}% → "
          f"{d['오류 문서 % — 개조식 규약 뺀 뒤']}% · "
          f"지적의 {d['개조식 규약 비중 %']}%가 개조식 규약")

(pathlib.Path(__file__).parent / "conditional-split.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
