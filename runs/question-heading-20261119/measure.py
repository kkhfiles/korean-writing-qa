"""python -X utf8 runs/question-heading-20261119/measure.py <적중 목록을 쓸 저장소 밖 폴더> <AI 기획 문서 폴더> <사람 문서 DB…>

「~인가」, 「~는가」로 끝나는 제목과 라벨, 본문 자문자답이 사람 글과 AI 글에 얼마나 나오나.
갈래는 넘겨받은 다섯 가지 빈틈을 따른다. 끝맺음은 형태소로 가른다(「단가」, 「전문가」, 「사업 인가」는 명사).
적중 문장은 사내 글이라 저장소 밖에만 쓴다. 여기 남기는 것은 개수뿐이다.
"""
import collections
import json
import re
import sqlite3
import sys
from pathlib import Path

from kiwipiepy import Kiwi

REPO = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1])
WORK_AI = sys.argv[2]   # 이 PC 의 AI 기획 문서 폴더 — 저장소에 경로를 적지 않는다
DBS = [Path(p) for p in sys.argv[3:]]   # 사람 문서가 든 지식 검색 DB 파일들(SQLite documents 표)
QWORD = re.compile(r'(무엇|뭐|어디|언제|누가|누구|왜|어떻게|어떤|얼마|몇|어느)')
QEF = {"ᆫ가", "는가", "은가", "던가"}          # 넘겨받은 범위 — 「~인가」, 「~는가」 꼴
KKA = {"ᆯ까", "을까"}                          # 참고로만 셈
HEAD = re.compile(r'^\s{0,3}#{1,6}\s+(.*)$')
HTML_H = re.compile(r'<h[1-6][^>]*>(.*?)</h[1-6]>', re.I)
ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+(.*)$')
DASH = re.compile(r'\s+[—–-]{1,2}\s+|:\s')
TAG = re.compile(r'<[^>]+>|\*\*|__|`')
SENT = re.compile(r'[^.!?\n]+[.!?]?')
kiwi = Kiwi()


def ending(text):
    """끝맺음 어미 — 「가」로 끝나는 것만 형태소 분석기에 넘긴다(빠르게)."""
    t = text.strip().rstrip('?？').strip()
    if not re.search(r'(가|까)$', t):
        return None
    toks = kiwi.tokenize(t)
    return toks[-1].form if toks and toks[-1].tag == "EF" else None


def korean(text):
    return len(re.findall(r'[가-힣]', text))


def units(text):
    """(종류, 앞부분, 전체, 부제 있음, 물음표) — 제목과 라벨은 앞부분, 본문은 문장."""
    for line in text.splitlines():
        heads = [m.group(1) for m in HTML_H.finditer(line)]
        m = HEAD.match(line)
        if m:
            heads.append(m.group(1))
        for h in heads:
            h = TAG.sub('', h).strip()
            parts = DASH.split(h, maxsplit=1)
            yield "제목", parts[0], h, len(parts) > 1, parts[0].rstrip().endswith('?')
        if heads:
            continue
        m = ITEM.match(line)
        if m:
            body = TAG.sub('', m.group(1)).strip()
            parts = DASH.split(body, maxsplit=1)
            if len(parts) > 1 or len(body) <= 40:   # 라벨 머리, 또는 짧은 항목 하나
                yield "라벨", parts[0], body, len(parts) > 1, parts[0].rstrip().endswith('?')
                if len(parts) > 1:
                    line = parts[1]
                else:
                    continue
            else:
                line = body
        for s in SENT.findall(TAG.sub('', line)):
            s = s.strip()
            if s:
                yield "본문", s, s, False, s.endswith('?')


def corpora():
    seen = set()
    human = []
    for db in DBS:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT source_type, source_id, content FROM documents "
            "WHERE (source_type='notion' AND doc_date < '2024-01-01') OR source_type='groupware'")
        for st, sid, content in rows:
            if (st, sid) not in seen and content:
                seen.add((st, sid))
                human.append((f"{st}:{sid}", content))
    ai = []
    for d in ("diagnostic-001", "diagnostic-002", "diagnostic-003", "exp6-instruction-style"):
        for p in sorted((REPO / "data" / "raw" / d).rglob("*")):
            if p.is_file() and p.suffix in {".md", ".txt", ".html"}:
                ai.append((f"{d}/{p.name}", p.read_text(encoding="utf-8", errors="replace")))
    # 이 PC 에서 AI 가 작성한 기획 문서 — 사본 폴더와 지시 파일은 뺀다
    work = []
    for p in sorted(Path(WORK_AI).rglob("*.md")):
        rel = p.relative_to(WORK_AI).as_posix()
        if rel.startswith("tmp/") or p.name in {"CLAUDE.md", "AGENTS.md", "SKILL.md"}:
            continue
        work.append((f"work/{rel}", p.read_text(encoding="utf-8", errors="replace")))
    return {"사람": human, "AI": ai, "AI 기획 문서": work}


def kind(unit, head, has_dash, has_q):
    if unit == "본문":
        return "④ 본문 자문자답"
    if has_q:
        return "② 물음표"
    if not QWORD.search(head):
        return "③ 의문사 없음"
    if has_dash:
        return "① 대시 부제"
    return "지금 잡는 꼴(의문사, 부제 없음)"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, docs in corpora().items():
        chars = sum(korean(t) for _, t in docs)
        count, kka, docs_hit = collections.Counter(), collections.Counter(), collections.defaultdict(set)
        total = collections.Counter()
        hits = []
        for doc, text in docs:
            for unit, head, whole, has_dash, has_q in units(text):
                total[unit] += 1
                ef = ending(head)
                if ef in QEF:
                    k = kind(unit, head, has_dash, has_q)
                    count[k] += 1
                    docs_hit[k].add(doc)
                    hits.append({"doc": doc, "kind": k, "unit": unit, "text": whole[:160]})
                elif ef in KKA:
                    kka[unit] += 1
        result[name] = {"docs": len(docs), "korean_chars": chars,
                        "count": dict(count), "docs_hit": {k: len(v) for k, v in docs_hit.items()},
                        "per_10k": {k: round(v / chars * 1e4, 3) for k, v in count.items()},
                        "kka": dict(kka), "units": dict(total)}
        (OUT / f"hits-{ {'사람': 'human', 'AI': 'ai'}.get(name, 'work')}.jsonl").write_text(
            "\n".join(json.dumps(h, ensure_ascii=False) for h in hits) + "\n", encoding="utf-8")
    (Path(__file__).parent / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
