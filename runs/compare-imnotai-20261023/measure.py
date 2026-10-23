"""im-not-ai 의 결정론적 지표(metrics_v2)와 우리 검사기를 같은 문서 묶음에 돌려 비교한다.

로컬 전용 — 문서 본문은 화면과 파일에 남기지 않고 문서별 점수만 적는다.
  사람: mycelium DB 의 2023년까지 고친 업무 문서 중 한글 300자 이상
  AI:   data/raw 진단 표본과 지시문 실험 산출물 중 한글 300자 이상

python -X utf8 runs/compare-imnotai-20261023/measure.py
"""
import collections
import importlib.util
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parents[1]
DB = r"P:\github\claude-workflow\mycelium\data\shared-test\mycelium.db"
AI_ROOT = REPO / "data/raw"
IMNOTAI = Path.home() / ".claude/plugins/cache/im-not-ai/humanize-korean/2.3.2/skills/humanize-korean/references"
HANGUL = re.compile(r"[가-힣]")
CODE = re.compile(r"```.*?```", re.S)


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


sys.path.insert(0, str(IMNOTAI))
mv2 = load("metrics_v2", IMNOTAI / "metrics_v2.py")
chk = load("chk", REPO / "assets/doc-style-check.py")


def human():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = ("SELECT content FROM documents WHERE source_type IN ('notion','product_docs','groupware','design_doc') "
         "AND substr(COALESCE(json_extract(metadata,'$.last_edited_time'),json_extract(metadata,'$.created_time'),created_at),1,4) <= '2023'")
    return [CODE.sub("", r[0] or "") for r in con.execute(q)]


def ai():
    out = []
    for d in ("diagnostic-001", "diagnostic-002", "diagnostic-003", "exp6-instruction-style"):
        for p in sorted((AI_ROOT / d).rglob("*")):
            if p.suffix in (".md", ".txt"):
                try:
                    out.append(CODE.sub("", p.read_text(encoding="utf-8")))
                except UnicodeDecodeError:
                    pass
    return out


def auc(pos, neg):
    """AI 문서 점수가 사람 문서 점수보다 높을 확률(동점은 절반)."""
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def score(text, tmp):
    h = len(HANGUL.findall(text))
    m = mv2.compute_all_v2(text, genre="report")
    tmp.write_text(text, encoding="utf-8")
    row = {"hangul": h, "imnotai_band": m["risk_band"], "imnotai_score": m["risk_score"],
           "antithesis": m["v2_metrics"]["antithesis_count"]}
    for form in ("auto", "prose"):
        err, warn, _ = chk.scan_md(str(tmp), form=None if form == "auto" else "prose")
        row[f"ours_{form}_err"] = len(err)
        row[f"ours_{form}_warn"] = len(warn)
        row[f"ours_{form}_kinds"] = sorted({k for k, _ in err} | {k for k, _ in warn})
    return row


def main():
    corp = {"human": human(), "ai": ai()}
    rows = collections.defaultdict(list)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "doc.md"
        for name, docs in corp.items():
            for t in docs:
                if len(HANGUL.findall(t)) >= 300:
                    rows[name].append(score(t, tmp))
    (HERE / "per_doc.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    H, A = rows["human"], rows["ai"]
    per10k = lambda r, f: (r[f"ours_{f}_err"] + r[f"ours_{f}_warn"]) / r["hangul"] * 1e4
    print(f"문서 수 — 사람 {len(H)} · AI {len(A)}")
    print("\n## im-not-ai metrics_v2 (genre=report) 위험 등급")
    for name, rs in (("사람", H), ("AI", A)):
        c = collections.Counter(r["imnotai_band"] for r in rs)
        print(f"  {name}: " + "  ".join(f"{b} {c[b]}편({c[b] / len(rs):.0%})" for b in ("low", "medium", "high")))
    print(f"  위험 점수 AUC(AI>사람) {auc([r['imnotai_score'] for r in A], [r['imnotai_score'] for r in H]):.3f}")
    print(f"  대구 개수 AUC {auc([r['antithesis'] / r['hangul'] for r in A], [r['antithesis'] / r['hangul'] for r in H]):.3f}")
    for form in ("auto", "prose"):
        print(f"\n## 우리 검사기 (form={form})")
        for name, rs in (("사람", H), ("AI", A)):
            e = sum(r[f"ours_{form}_err"] > 0 for r in rs)
            w = sum(r[f"ours_{form}_warn"] > 0 for r in rs)
            print(f"  {name}: 오류 있는 문서 {e}편({e / len(rs):.0%}) · 주의 있는 문서 {w}편({w / len(rs):.0%})")
        print(f"  지적 밀도 AUC(AI>사람) {auc([per10k(r, form) for r in A], [per10k(r, form) for r in H]):.3f}")
        kinds = {name: collections.Counter(k for r in rs for k in r[f"ours_{form}_kinds"]) for name, rs in (("사람", H), ("AI", A))}
        print("  갈래별 걸린 문서 비율 — 사람 / AI (상위 15)")
        top = sorted(set(kinds["사람"]) | set(kinds["AI"]), key=lambda k: -(kinds["사람"][k] / len(H) + kinds["AI"][k] / len(A)))
        for k in top[:15]:
            print(f"    {k:<22} {kinds['사람'][k] / len(H):6.1%} / {kinds['AI'][k] / len(A):6.1%}")


if __name__ == "__main__":
    main()
