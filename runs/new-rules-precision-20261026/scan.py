"""최근 실제 문서에서 새 규칙이 어디서 걸리나 — 걸린 줄을 사람이 맞다·아니다로 가르기 위한 목록.

새 규칙: 「머리말 되풀이」, 「평가 수식어」의 수치 조건, 「상투 문형」, 「반복 문형」, 「「~가 아니라」 반복」
(2026-10-23 넣거나 넓힘). 문서 목록은 저장소 밖 파일로 받는다 — 경로에 다른 프로젝트 이름이 든다.
걸린 줄 발췌는 화면과 저장소 밖 파일에만 쓴다.

python -X utf8 runs/new-rules-precision-20261026/scan.py <문서 목록 파일> <발췌를 쓸 저장소 밖 경로>
"""
import collections
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KINDS = {"머리말 되풀이", "상투 문형", "반복 문형", "「~가 아니라」 반복"}


def load(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def main():
    chk = load("chk", REPO / "assets/doc-style-check.py")
    paths = [Path(l.strip()) for l in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if l.strip()]
    hits, per_kind_docs = [], collections.Counter()
    for p in paths:
        try:
            err, warn, _ = (chk.scan_html if p.suffix == ".html" else chk.scan_md)(str(p))
        except Exception as e:  # 읽지 못한 문서는 세지 않고 이름만 남긴다
            print(f"⛔ {p.name}: {type(e).__name__}")
            continue
        seen = set()
        for kind, msg in err + warn:
            if kind in KINDS or (kind == "평가 수식어" and "수치 옆에서" in msg):
                k = "수치 꾸미는 부사" if kind == "평가 수식어" else kind
                hits.append({"doc": str(p), "kind": k, "msg": msg})
                seen.add(k)
        per_kind_docs.update(seen)
    Path(sys.argv[2]).write_text(json.dumps(hits, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"문서 {len(paths)}편 · 걸린 줄 {len(hits)}")
    for k, n in per_kind_docs.most_common():
        print(f"  {k:<16} 문서 {n}편 · 줄 {sum(1 for h in hits if h['kind'] == k)}")


if __name__ == "__main__":
    main()
