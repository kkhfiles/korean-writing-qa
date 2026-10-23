"""im-not-ai 새 패턴이 사람 업무 문서와 AI 원문에서 몇 번 나오는지 센다(로컬 전용, 표본은 화면만)."""
import random
import re
import sqlite3
import sys
from pathlib import Path

DB = r"P:\github\claude-workflow\mycelium\data\shared-test\mycelium.db"
AI_ROOT = Path("P:/github/korean-writing-qa/data/raw")
SHOW = int(sys.argv[1]) if len(sys.argv) > 1 else 0
ONLY = sys.argv[2:] if len(sys.argv) > 2 else None

P = {
    "A-20 피동 진행": r"[가-힣](?:되|지)고\s?있(?:다|습니다|으며|어|는|음)",
    "A-21 X를 넘어": r"단순(?:한|히)\s?[가-힣]{1,12}(?:을|를)\s?넘어",
    "A-21b 를 넘어(넓게)": r"[가-힣](?:을|를)\s?넘어(?:서)?\s",
    "A-22 평가 술어": r"(?:은|는|이|가)\s?(?:명확|분명|자명)(?:하다|합니다|해졌|해진다)",
    "A-23 발판·토대": r"(?:발판|토대|초석)(?:을|를)\s?(?:마련|다지|놓)|지평을\s?(?:열|넓)",
    "A-24 더 이상": r"더\s?이상\s?[^\n.]{0,20}?(?:않|아니|없|못)",
    "C-8 가 아니라": r"[가-힣](?:가|이)\s?아니라\s",
    "C-11 연결어미 쉼표": r"[가-힣](?:고|며|지만|면서|아서|어서|는데),\s",
    "D-6 할 때입니다": r"(?:할|갈|볼|나설)\s?(?:때|시점|순간)(?:입니다|이다)",
    "D-8 필요한 것은": r"(?:필요한|중요한)\s?것은\s",
    "D-8b 핵심은·관건은": r"(?:문제|핵심|관건)은\s",
    "D-9 로 이어진다": r"(?:으로|로)\s?이어(?:진다|집니다|질 것)|에\s?직결(?:된다|됩니다)",
    "D-9b 결국": r"(?:^|\s)결국\s",
    "D-10 하는 이유다": r"[가-힣]\s이유(?:다|입니다)(?:[.\s]|$)",
    "D-12 과제도 남아": r"(?:과제|한계|아쉬운\s?점)(?:도|가)\s?(?:남아\s?있|분명하|있)(?:다|습니다)",
    "I-7 다는 분석이다": r"다는\s?(?:분석|평가|관측|전망)(?:이다|입니다)",
    "I-1 것이다(참고)": r"것(?:이다|입니다)",
    "F-7 범용 정책동사": r"(?:확대|강화|개선|확보|마련|집중|유지|구축|지원)(?:하|해|합|했|할|된|되)",
}
RX = {k: re.compile(v, re.M) for k, v in P.items() if not ONLY or any(k.startswith(o) for o in ONLY)}
HANGUL = re.compile(r"[가-힣]")
CODE = re.compile(r"```.*?```", re.S)


def human():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    q = ("SELECT content FROM documents WHERE source_type IN ('notion','product_docs','groupware','design_doc') "
         "AND substr(COALESCE(json_extract(metadata,'$.last_edited_time'),json_extract(metadata,'$.created_time'),created_at),1,4) <= '2023'")
    return [CODE.sub("", r[0] or "") for r in con.execute(q)]


def ai():
    out = []
    for p in [q for d in ("diagnostic-001", "diagnostic-002", "diagnostic-003", "exp6-instruction-style") for q in (AI_ROOT / d).rglob("*")]:
        if p.suffix in (".md", ".txt"):
            try:
                out.append(CODE.sub("", p.read_text(encoding="utf-8")))
            except Exception:
                pass
    return out


random.seed(3)
corp = {"사람(≤2023 문서)": human(), "AI 원문": ai()}
size = {k: sum(len(HANGUL.findall(t)) for t in v) for k, v in corp.items()}
print({k: f"{len(corp[k])}편 한글 {size[k]:,}자" for k in corp})
print(f"{'패턴':<22}{'사람/1만자':>10}{'AI/1만자':>10}{'배수':>7}  사람건 AI건")
for name, rx in RX.items():
    hits = {k: [m.group(0) for t in v for line in t.splitlines() for m in rx.finditer(line)] for k, v in corp.items()}
    rate = {k: len(hits[k]) / size[k] * 10000 for k in corp}
    h, a = rate["사람(≤2023 문서)"], rate["AI 원문"]
    ratio = a / h if h else float("inf")
    print(f"{name:<22}{h:>10.2f}{a:>10.2f}{ratio:>7.1f}  {len(hits['사람(≤2023 문서)'])} {len(hits['AI 원문'])}")
    if SHOW:
        for k in corp:
            lines = [line.strip() for t in corp[k] for line in t.splitlines() if rx.search(line)]
            for s in random.sample(lines, min(SHOW, len(lines))):
                print(f"    [{k[:2]}] {s[:120]}")
