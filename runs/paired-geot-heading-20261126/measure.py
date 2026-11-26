"""python -X utf8 runs/paired-geot-heading-20261126/measure.py <적중 목록을 쓸 저장소 밖 폴더> <AI 기획 문서 폴더> <사람 문서 DB…>

「덜어낸 것과 남긴 것」처럼 관형형 + 「것」 둘을 대구로 이은 명사구가 사람 글과 AI 글에 얼마나 나오나.
두 가지를 잰다.
- 넓게(broad) — 「~ 것 + 이음 + 25자 안 + ~ 것」을 찾고 「것」 앞이 관형형 어미인지 형태소로 확인.
  놓인 곳(제목, 라벨, 본문)과 끝맺음(그 명사구로 끝남, 뒤에 이어짐)으로 나눈다.
- 규칙(rule) — 검사기의 `PAIR_GEOT` 를 그대로 댄다. 제목은 「대구 「것」 제목」(오류), 그 밖의 줄은
  「상투 문형」의 「대구 「~한 것과 ~한 것」」(주의)과 같은 판정이다.
적중 문장은 사내 글이라 저장소 밖에만 쓴다. 여기 남기는 것은 개수뿐이다.
"""
import collections
import importlib.util
import json
import re
import sqlite3
import sys
from pathlib import Path

from kiwipiepy import Kiwi

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("dsc", REPO / "assets" / "doc-style-check.py")
DSC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DSC)

OUT = Path(sys.argv[1])
WORK_AI = sys.argv[2]   # 이 PC 의 AI 기획 문서 폴더 — 저장소에 경로를 적지 않는다
DBS = [Path(p) for p in sys.argv[3:]]   # 사람 문서가 든 지식 검색 DB 파일들(SQLite documents 표)
HEAD = re.compile(r'^\s{0,3}#{1,6}\s+(.*)$')
HTML_H = re.compile(r'<h[1-6][^>]*>(.*?)</h[1-6]>', re.I)
ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+(.*)$')
DASH = re.compile(r'\s+[—–-]{1,2}\s+|:\s')
TAG = re.compile(r'<[^>]+>|\*\*|__|`')
SENT = re.compile(r'[^.!?\n]+[.!?]?')
PAIR = re.compile(r'([가-힣]+) 것(과|와|,|\s?/|\s?·|\s?vs\.?|\s대)\s?(.{1,25}?) 것(?![가-힣])')
AFTER = re.compile(r'^\s*($|[—–:)\]」』,.]|-\s)')   # 그 명사구로 끝남
kiwi = Kiwi()


def etm_before_geot(span):
    """span 안의 「것/NNB」 둘이 모두 관형형 어미 바로 뒤인가."""
    toks = kiwi.tokenize(span)
    hits = [i for i, t in enumerate(toks) if t.form == "것" and t.tag == "NNB"]
    return len(hits) >= 2 and all(i > 0 and toks[i - 1].tag == "ETM" for i in hits[:2])


def korean(text):
    return len(re.findall(r'[가-힣]', text))


def units(text):
    """(종류, 글) — 제목, 라벨 머리(대시나 쌍점 앞, 또는 40자 이하 항목), 본문 문장."""
    for line in text.splitlines():
        heads = [m.group(1) for m in HTML_H.finditer(line)]
        m = HEAD.match(line)
        if m:
            heads.append(m.group(1))
        for h in heads:
            yield "제목", TAG.sub('', h).strip()
        if heads:
            continue
        m = ITEM.match(line)
        if m:
            body = TAG.sub('', m.group(1)).strip()
            parts = DASH.split(body, maxsplit=1)
            if len(parts) > 1 or len(body) <= 40:
                yield "라벨", parts[0]
                if len(parts) > 1:
                    line = parts[1]
                else:
                    continue
            else:
                line = body
        for s in SENT.findall(TAG.sub('', line)):
            s = s.strip()
            if s:
                yield "본문", s


def rule_hits(text):
    """검사기 규칙 그대로 — (제목|그 밖, 줄)."""
    for line in text.splitlines():
        heads = [TAG.sub('', m.group(1)).strip() for m in HTML_H.finditer(line)]
        m = HEAD.match(line)
        if m:
            heads.append(TAG.sub('', m.group(1)).strip())
        if heads:
            for h in heads:
                if DSC.PAIR_GEOT.search(DSC.mask(DSC.drop_tail(h))):
                    yield "제목", h
            continue
        s = line.strip()
        if s.startswith('>') or DSC.is_example(s):
            continue
        if DSC.PAIR_GEOT.search(DSC.mask(TAG.sub('', line))):
            yield "그 밖", s


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
    work = []
    for p in sorted(Path(WORK_AI).rglob("*.md")):
        rel = p.relative_to(WORK_AI).as_posix()
        if rel.startswith("tmp/") or p.name in {"CLAUDE.md", "AGENTS.md", "SKILL.md"}:
            continue
        work.append((f"work/{rel}", p.read_text(encoding="utf-8", errors="replace")))
    return {"사람": human, "AI": ai, "AI 기획 문서": work}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, docs in corpora().items():
        chars = sum(korean(t) for _, t in docs)
        broad, broad_docs, total = collections.Counter(), collections.defaultdict(set), collections.Counter()
        rule, rule_docs = collections.Counter(), collections.defaultdict(set)
        hits = []
        for doc, text in docs:
            for unit, s in units(text):
                total[unit] += 1
                for m in PAIR.finditer(s):
                    if not etm_before_geot(m.group(0)):
                        continue
                    ends = bool(AFTER.match(s[m.end():]))
                    k = f"{unit} — {'명사구로 끝남' if ends else '뒤에 이어짐'}"
                    broad[k] += 1
                    broad_docs[k].add(doc)
                    hits.append({"doc": doc, "measure": "broad", "kind": k, "match": m.group(0), "text": s[:160]})
            for where, s in rule_hits(text):
                rule[where] += 1
                rule_docs[where].add(doc)
                hits.append({"doc": doc, "measure": "rule", "kind": where, "text": s[:160]})
        result[name] = {"docs": len(docs), "korean_chars": chars, "units": dict(total),
                        "broad": dict(sorted(broad.items())),
                        "broad_docs": {k: len(v) for k, v in sorted(broad_docs.items())},
                        "rule": dict(sorted(rule.items())),
                        "rule_docs": {k: len(v) for k, v in sorted(rule_docs.items())}}
        tag = {"사람": "human", "AI": "ai"}.get(name, "work")
        (OUT / f"hits-{tag}.jsonl").write_text(
            "\n".join(json.dumps(h, ensure_ascii=False) for h in hits) + "\n", encoding="utf-8")
    (Path(__file__).parent / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
