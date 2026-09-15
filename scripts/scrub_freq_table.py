#!/usr/bin/env python
"""빈도표에서 신원 정보를 걷어낸다.

    python -X utf8 scripts/scrub_freq_table.py --dry-run   # 지울 것만 보여 준다
    python -X utf8 scripts/scrub_freq_table.py             # 실제로 지운다

**왜.** 이 표는 사용자 업무 글 4,790만 자에서 뽑았는데, 만들 때 품사를 안 걸러서
**고유명사가 통째로 들어갔다** — 동료 실명 · 고객사 · 사옥 주소 · 사내 조직.
공개 저장소라 그대로 노출됐다(2026-09-09 ~ 09-15).

**왜 다시 집계하지 않나.** 표는 `(낱말, 품사) → 횟수` 라 항목이 서로 독립이다.
집계에서 NNP 를 빼는 것과 표에서 NNP 항목을 지우는 것은 **같은 표**를 낸다.
원본을 다시 모아도 NNG 로 잘못 붙은 이름은 그대로 남으므로 얻는 것이 없다.

**세 갈래로 지운다.**

1. **훑개가 안 읽는 품사 전부** — `KEEP` 은 `{NNG, VV, VA, MAG, XR}` 이라 고유명사
   6,434종은 **한 번도 안 읽힌다.** 지워도 기능 손실이 0이고, 이름·회사·주소가
   대부분 여기 있다.
2. **회사·조직·사옥** — 품사를 안 따진다. 회사 이름은 어디에 붙든 신원이다.
3. **NNG 쪽 이름** — Kiwi 가 같은 말을 어디선 NNP, 어디선 NNG 로 붙인다
   (같은 이름이 두 품사로 갈려 들어간다).

**3번을 기계로만 하면 안 된다 — 두 번 다 실패했다.**

- **이름 꼴 정규식만으로 훑으면** 「고객사·이미지·서비스·전처리·하반기·노트북·
  문제점·이벤트·구조체·이야기」 같은 멀쩡한 말 800여 종이 함께 날아가 기준선이
  망가진다(실측). 그래서 **그 말뭉치에서 고유명사로도 쓰였을 것**을 함께 요구한다.
- **그 조건만으로는 이름을 놓친다** — Kiwi 가 한 번도 NNP 로 안 붙인 이름이 39개
  남았다. 낱말 하나만 떼어 물어도 안 갈린다
  (실측 35개 중 0개 적중 · 전부 NNG 로 읽음). **글자 모양이 「고객사」와 같아서**
  원리적으로 못 가른다 → `NAMES_SEEN` 에 사람이 훑어 적었다.

⚠️ **표를 다시 만들면 이 목록도 다시 봐야 한다.** 새 이름은 자동으로 안 걸린다 —
   `--dry-run` 의 「남긴 것」 목록을 사람이 읽는 것이 마지막 그물이다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE = os.path.normpath(os.path.join(HERE, "..", "data", "catalog", "work-korean-freq.json"))

#: 훑개가 실제로 읽는 품사 — 이 밖은 표에 둘 이유가 없다
KEEP_TAGS = {"NNG", "VV", "VA", "MAG", "XR"}

#: 이 횟수 **이하**는 표에서 뺀다 — 훑개가 없는 낱말과 똑같이 다루기 때문이다.
#   `rare_words.py` 는 `freq.get(key, 0) <= --max` 로 판정하고 `--max` 기본이 40이다.
#   그러니 40회 이하 항목은 있으나 없으나 같은 답이 나온다 — 기능은 0을 보태면서
#   **신원만 나른다.** 2026-09-15 2차 점검에서 항목 11,257 중 7,800이 여기 걸렸고,
#   그 안에 회사 이름 25종·학교 5종·사람 이름 다수가 있었다.
#   ⛔ 이 값을 올리면 훑개 판정이 바뀐다 — `rare_words.py` 의 기본 `--max` 와
#      같아야 하고, `tests/test_freq_table_has_no_identity.py` 가 둘을 대조한다.
FLOOR = 40

#: 글자 수가 이보다 적으면 뺀다 — 훑개가 `len(tok.form) < 2` 로 건너뛴다.
#   성씨와 이름 낱자(「박」·「홍」·「욱」·「혜」)가 여기 모여 있었다.
MIN_LEN = 2

_SURNAME = ("김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노"
            "하곽성차주우구민진지엄채원천방공함변염여추설마길연위표명기반왕")
#: 사람 이름 꼴 — 성 한 글자 + 이름 **두 글자**
#   ⛔ 두 글자 이름(성+한 글자)까지 받으면 「지원·유닛·유지·구성·고려·이동·한글·
#      장비·문자」가 통째로 걸린다(실측 — 「지원」만 26,822회다). 두 글자 이름은
#      드물고, 놓쳐도 아래 「남긴 것」 목록에 올라 사람이 본다.
NAME_SHAPE = re.compile(rf"^[{_SURNAME}][가-힣]{{2}}$")
#: 이름 + 직함이 한 낱말로 붙은 꼴 — 「<이름>책임님」 같은 것이 남아 있었다(실측).
#   이름 세 글자만 보면 못 잡고, 이름 목록으로도 못 잡는다(그 이름이 홑으로는
#   표에 없다). **이 모양 자체가 사람을 가리키므로** 증거를 더 안 따진다.
_TITLE = ("님|씨|책임|선임|연구원|사원|대리|과장|차장|부장|팀장|실장|소장|센터장"
          "|매니저|이사|상무|전무|부사장|사장|대표|교수|박사|프로")
NAME_TITLE = re.compile(rf"^[{_SURNAME}][가-힣]{{2}}(?:{_TITLE})님?$")
#: 신원 목록 — **저장소 밖 파일에서 읽는다.**
#   ⛔ 회사·조직 이름을 이 파일에 적지 않는다. 적는 순간 **그 코드가 곧 고객사
#      명단**이 된다 — 숨기려는 것을 검사기가 나열하는 꼴이다(2026-09-15 에 그렇게
#      적었다가 푸시 직전에 걷어냈다). 이름도 같은 이유로 밖에 둔다.
#   ⛔ Kiwi 는 이름을 낱말 하나만 떼어 줘도 NNG 로 읽는다(실측 35개 중 0개 적중).
#      「고객사·이미지·서비스」와 글자 모양이 같아 기계로는 안 갈린다 — 그래서 목록이다.
DENYLIST = os.path.join(os.path.dirname(TABLE), "local-identity-denylist.txt")


def load_denylist() -> dict[str, set[str]]:
    """절로 나뉜 신원 목록을 읽는다. 없으면 빈 것 — 부른 쪽이 알린다."""
    out: dict[str, set[str]] = {"이름": set(), "회사": set(), "조직": set()}
    if not os.path.exists(DENYLIST):
        return out
    section = None
    with open(DENYLIST, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line:
                continue
            head = re.fullmatch(r"\[(.+)\]", line)
            if head:
                section = head.group(1).strip()
                out.setdefault(section, set())
            elif section:
                out[section].add(line)
    return out


DENY = load_denylist()
NAMES_SEEN, ORGS, PLACE = DENY["이름"], DENY["회사"], DENY["조직"]


def identifying(form: str, proper: set[str]) -> str | None:
    """신원으로 읽히면 그 갈래를 낸다.

    `proper` 는 이 말뭉치에서 **고유명사로도 쓰인** 낱말이다. 이름 판정에만 쓴다 —
    「고객사·이미지·서비스」처럼 글자 모양이 이름과 같은 보통명사를 안 지우려는
    장치다. 회사·조직은 그 증거를 안 따진다(이름 자체가 신원이다).
    """
    if any(o in form for o in ORGS):
        return "회사·고객사"
    if form in PLACE:
        return "주소·조직"
    if form in NAMES_SEEN:
        # ⛔ 사람이 적어 준 이름은 **모양을 안 따진다.** 성씨 목록에 없는 성이 있다 —
        #    2026-09-15 2차 점검에서 옥·나·판으로 시작하는 이름 셋이 모양 판정을
        #    빠져나가 공개된 표에 그대로 남아 있었다. 목록에 적혔다는 것이 곧 판정이다.
        return "사람 이름"
    if NAME_TITLE.match(form):
        return "사람 이름"
    if NAME_SHAPE.match(form) and form in proper:
        return "사람 이름"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="빈도표에서 신원 정보를 걷어낸다")
    ap.add_argument("--dry-run", action="store_true", help="지울 것만 보여 준다")
    args = ap.parse_args()

    if not any(DENY.values()):
        print(f"⚠️ 신원 목록이 없습니다: {DENYLIST}\n"
              "   품사로 거르는 것만 됩니다 — NNG 로 붙은 이름·회사는 그대로 남습니다.\n")
    with open(TABLE, encoding="utf-8") as f:
        data = json.load(f)
    freq = data["freq"]
    before = len(freq)

    proper = {k.rsplit("/", 1)[0] for k in freq if k.endswith("/NNP")}

    # ① 이름을 먼저 모은다 — 직함이 붙은 꼴을 지우려면 이름 목록이 있어야 한다
    # 목록에 적힌 이름은 모양을 안 따진다 — 성씨 목록 밖의 성이 있다(옥·나·판).
    found = {form for k in freq
             for form in [k.rsplit("/", 1)[0]]
             if form in NAMES_SEEN or (NAME_SHAPE.match(form) and form in proper)}

    # ⛔ 이름 세 글자만 보면 **직함이 붙은 꼴이 살아남는다** — 「<이름>연구원님」·
    #    「<이름>선임」·「<이름>과장」이 NNG 로 남아 있었다(실측). 이름을 품은 말은
    #    모두 지운다. 이 이름들을 품은 보통명사는 없다.
    def carries_name(form: str) -> bool:
        return any(nm in form for nm in found)

    dropped_tag, dropped_name, dropped_floor = [], [], []
    kept = {}
    for key, n in freq.items():
        form, tag = key.rsplit("/", 1)
        if tag not in KEEP_TAGS:
            dropped_tag.append((key, n))
            continue
        if n <= FLOOR or len(form) < MIN_LEN:
            dropped_floor.append((key, n))
            continue
        kind = identifying(form, proper) or ("사람 이름" if carries_name(form) else None)
        if kind:
            dropped_name.append((key, n, kind))
            continue
        kept[key] = n

    print(f"표 {TABLE}")
    print(f"  항목 {before} → {len(kept)}")
    print(f"  품사로 뺌 {len(dropped_tag)}종 (훑개가 안 읽는 품사)")
    print(f"  {FLOOR}회 이하·{MIN_LEN}글자 미만이라 뺌 {len(dropped_floor)}종 "
          "(훑개가 안 읽거나 없는 낱말과 똑같이 봄)")
    print(f"  신원으로 뺌 {len(dropped_name)}종 (NNP 에도 있고 신원 꼴인 것)\n")

    for kind in ("사람 이름", "회사·고객사", "주소·조직"):
        rows = sorted((r for r in dropped_name if r[2] == kind), key=lambda r: -r[1])
        if rows:
            print(f"  [{kind}] {len(rows)}종 — "
                  + " · ".join(f"{k.rsplit('/', 1)[0]}({n})" for k, n, _ in rows[:14]))

    left = [k.rsplit("/", 1)[0] for k in kept
            if NAME_SHAPE.match(k.rsplit("/", 1)[0])]
    if left:
        print(f"\n  ⚠️ 신원 꼴인데 NNP 에 없어 남긴 것 {len(left)}종 — 사람이 볼 것")
        print("     " + " · ".join(sorted(set(left))[:30]))

    if args.dry_run:
        print("\n--dry-run 이라 안 고쳤습니다.")
        return 0

    data["freq"] = kept
    data["scrubbed"] = ("고유명사와 신원 정보를 뺌 — 동료 실명·고객사·주소. "
                        "훑개는 NNG·VV·VA·MAG·XR 만 읽는다.")
    with open(TABLE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"\n고쳤습니다 — 항목 {len(kept)}종")
    return 0


if __name__ == "__main__":
    sys.exit(main())
