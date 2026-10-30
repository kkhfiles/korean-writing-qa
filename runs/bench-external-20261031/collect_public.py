"""정책브리핑(korea.kr) 정책뉴스 본문을 모아 비교 실험의 공개 기준 글로 쓴다.

- 공공누리 제1유형(출처표시) 표시가 있는 글만 받는다. 본문은 저장소 밖에 두고 저장소에는 수와 주소만 적는다.
- 보도자료 쪽은 본문이 첨부 문서 변환본(iframe)에만 있어 정책뉴스를 쓴다.
- robots.txt 가 전체를 허용한다(2026-10-31 확인). 요청 사이 2초를 둔다.
- 사진 설명 줄(ⓒ)과 문의 줄은 뺀다.

    python -X utf8 runs/bench-external-20261031/collect_public.py [--pages 8] [--want 40]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.request
from pathlib import Path

OUT = Path.home() / ".local/share/korean-writing-qa/bench-external/public"
LIST = "https://www.korea.kr/news/policyNewsList.do?pageIndex={}"
VIEW = "https://www.korea.kr/news/policyNewsView.do?newsId={}"
UA = {"User-Agent": "Mozilla/5.0 (benchmark; korean-writing-qa)"}


def get(url: str) -> str:
    time.sleep(2)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def body_of(page: str) -> tuple[str, str] | None:
    """제목과 본문 — `view_cont` 부터 공공누리 안내 앞까지."""
    if "공공누리 제1유형" not in page:
        return None
    m = re.search(r"<title>(.*?)</title>", page, re.S)
    title = html.unescape(m.group(1)).split(" - ")[0].strip() if m else ""
    i = page.find('class="view_cont"')
    if i < 0:
        return None
    s = page[i:]
    s = s[:s.find("kogl_wrap")]
    s = re.sub(r"<(script|style).*?</\1>", "", s, flags=re.S)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</(p|div|li|tr|h\d)>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    lines = [re.sub(r"[ \t ]+", " ", x).strip() for x in s.splitlines()]
    lines = [x for x in lines if x and "ⓒ" not in x and not x.startswith(("문의", "class=", "“이 자료는", "<"))
             and re.search(r"[가-힣]", x)]
    return title, "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--want", type=int, default=40)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "docs.jsonl"
    done = {json.loads(l)["id"] for l in path.open(encoding="utf-8")} if path.exists() else set()
    kept = len(done)
    with path.open("a", encoding="utf-8") as f:
        for p in range(1, a.pages + 1):
            if kept >= a.want:
                break
            for i in dict.fromkeys(re.findall(r"policyNewsView\.do\?newsId=(\d+)", get(LIST.format(p)))):
                if kept >= a.want or i in done:
                    continue
                done.add(i)
                got = body_of(get(VIEW.format(i)))
                if not got:
                    continue
                title, text = got
                hangul = len(re.findall(r"[가-힣]", text))
                if not 700 <= hangul <= 3500 or text.count("\n") < 5:
                    continue
                f.write(json.dumps({"id": i, "url": VIEW.format(i), "title": title, "text": text,
                                    "hangul": hangul, "license": "공공누리 제1유형(출처표시)"},
                                   ensure_ascii=False) + "\n")
                f.flush()
                kept += 1
                print(kept, i, hangul, title[:40])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
