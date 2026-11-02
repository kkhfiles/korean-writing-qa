"""검토 화면 — 문서 하나의 지적(2층 고칠 지적, 사람 확인, 1층 검사기)을 원문 위에 표시하고 고르는 HTML 을 만든다.

    python -X utf8 scripts/review_screen.py <문서>                 # HTML 만 씀(저장소 밖)
    python -X utf8 scripts/review_screen.py <문서> --serve         # 이 PC 안에서 띄움

**왜 있나** (2026-11-02 사용자 결정) — 판정표(사람 확인 카드)를 대신한다. 원문과 지적 카드가 따로 스크롤되며
서로 따라가고(시안 A3, `draft-redline` 의 비교 화면과 같은 방식), 전체와 갈래별로 한꺼번에 고를 수 있다.
시안과 그 결정은 `runs/review-screen-proto-20261101/README.md`.

**지금 단계** — 1단계(보기만 함). 고른 결과는 화면 안에서만 바뀐다. 답 기록(2단계), 파일 반영(3단계),
신뢰 설정과 규칙 저장(4단계)은 뒤에 붙인다.

- **127.0.0.1 의 빈 포트에만 연다** — 화면에 문서 원문이 들어 있다
- **HTML 은 저장소 밖에 쓴다** — 판정 기록 옆 `korean-review/`(문서 원문이 들어 있어 커밋하지 않는다)
- **작성자 정보가 필요한 지적**(판정기의 「확인할 사실」이 있거나 사람 확인으로 넘어온 것)은 수정안을 미리 넣지 않고
  일괄 처리와 신뢰 스위치에서 뺀다(`docs/decisions-pending.md` 「지키는 조건」)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import layer2_coverage as coverage  # noqa: E402

TEMPLATE = HERE / "review_screen.html"
CHECKER = HERE.parent / "assets" / "doc-style-check.py"
FONT_TOOL = Path.home() / ".claude" / "assets" / "fonts" / "inline-korean-font.py"
L1_LINE = re.compile(r"^\s*(❌|⚠️)\s+\[(.+?)\]\s+(\d+)행\s+(.*)$")
#: 문체 규칙 묶음에 넣는 1층 갈래 — 사용자가 정한 문체(개조식)라 문서 종류에 따라 끌 수 있다
STYLE_KINDS = {"서술형 종결", "반말 서술형", "서술형 문단", "제목 서술형", "진입점 서술형"}
#: 화면에 안 싣는 1층 갈래 — 줄 하나에 붙지 않는 문서 전체 지적이라 원문 위에 표시할 곳이 없다
SKIP_KINDS = {"반복 블록 라벨 불일치", "형식 미표기", "형식 미정", "진입점 없음"}


def out_dir() -> Path:
    """판정 기록 옆 — 시험이 기록 경로를 돌리면 함께 따라간다."""
    return Path(os.environ.get("KOREAN_QA_JUDGE_LOG") or coverage.LOG).parent / "korean-review"


def widen(line: str, phrase: str) -> str:
    """1층 인용이 어절 중간에서 잘리면 어절 전체로 넓힌다 — 원문 위 표시가 낱말 가운데서 끊기지 않게."""
    i = line.find(phrase)
    if i < 0:
        return phrase
    a, b = i, i + len(phrase)
    while a > 0 and not line[a - 1].isspace():
        a -= 1
    while b < len(line) and not line[b].isspace():
        b += 1
    return line[a:b]


def layer1(path: Path, lines: list[str]) -> list[dict]:
    """1층 검사기 지적 — 그 사람의 설정(`korean-qa.toml`, 개인 규칙)을 따른다. 오류와 주의를 모두 싣는다."""
    out = subprocess.run([sys.executable, "-X", "utf8", str(CHECKER), "-v", str(path)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    items = []
    for raw in out.splitlines():
        m = L1_LINE.match(raw)
        if not m or m.group(2) in SKIP_KINDS:
            continue
        n, kind, body = int(m.group(3)), m.group(2), m.group(4)
        if not 0 < n <= len(lines):
            continue
        q = re.search(r"「(.+?)」", body)
        phrase = q.group(1) if q and q.group(1) in lines[n - 1] else lines[n - 1].strip().lstrip("-*# ")
        items.append({"layer": "1층", "level": "오류" if m.group(1) == "❌" else "주의", "line": n,
                      "phrase": widen(lines[n - 1], phrase), "fix": "", "cat": kind, "check": "",
                      "type": "style" if kind in STYLE_KINDS else "replace",
                      "why": body.split(" — ", 1)[1].strip() if " — " in body else ""})
    return items


def collect(path: Path) -> dict:
    """화면에 실을 자료 — 원문 줄과 지적. 지적마다 줄 해시를 붙여 2단계가 답을 그 줄에 단다."""
    lines = coverage.read_doc(path).splitlines()
    key = coverage.doc_key(path)
    items = []
    for n, fx in coverage.open_fixes(key, lines):
        items.append({"layer": "2층", "level": "고칠 지적", "line": n, "phrase": str(fx.get("phrase") or ""),
                      "fix": str(fx.get("fix") or ""), "cat": str(fx.get("category") or ""),
                      "check": str(fx.get("check") or ""), "why": str(fx.get("why") or ""),
                      "type": "info" if coverage.needs_check(fx) else "replace"})
    for n, ask in coverage.open_asks(key, lines):
        items.append({"layer": "2층", "level": "사람 확인", "line": n, "phrase": str(ask.get("phrase") or ""),
                      "fix": str(ask.get("fix") or ""), "cat": str(ask.get("category") or "사람 확인"),
                      "check": str(ask.get("check") or ask.get("note") or ""), "why": str(ask.get("why") or ""),
                      "type": "info"})
    items += layer1(path, lines)
    items.sort(key=lambda x: (x["line"], {"replace": 0, "info": 1, "style": 2}[x["type"]]))
    for i, x in enumerate(items, 1):
        x["id"] = i
        x["line_key"] = coverage.line_key(lines[x["line"] - 1]) or ""
    return {"title": path.name, "path": str(path.resolve()), "lines": lines, "items": items}


def render(data: dict) -> str:
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", blob)


def write_html(path: Path, out: Path | None = None) -> tuple[Path, dict]:
    data = collect(path)
    if out is None:
        tag = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:8]
        out = out_dir() / f"{path.stem}-{tag}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8", newline="\n")
    if FONT_TOOL.is_file():
        subprocess.run([sys.executable, "-X", "utf8", str(FONT_TOOL), str(out)], capture_output=True)
    return out, data


def serve(page: Path, timeout: float, open_browser: bool = True, ready=None) -> int:
    """화면을 띄운다 — 1단계라 받는 요청은 화면 하나뿐이다(제출은 2단계에서 붙임)."""
    body = page.read_bytes()
    stop = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 접속 기록을 출력하지 않음
            pass

        def do_GET(self):
            if self.path.split("?")[0] != "/":
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={secrets.token_urlsafe(6)}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"검토 화면 — {url}", flush=True)
    if ready:
        ready(url)
    if open_browser:
        webbrowser.open(url)
    stop.wait(timeout)
    srv.shutdown()
    srv.server_close()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="문서의 지적을 원문 위에 표시하고 고르는 검토 화면")
    ap.add_argument("doc", help="검토할 문서(md, html, txt)")
    ap.add_argument("--out", help="HTML 을 쓸 곳(기본: 판정 기록 옆 korean-review/)")
    ap.add_argument("--serve", action="store_true", help="이 PC 안에서 띄움")
    ap.add_argument("--timeout", type=float, default=4 * 3600, help="띄워 두는 초(기본 4시간)")
    ap.add_argument("--no-open", action="store_true", help="브라우저를 열지 않음")
    a = ap.parse_args(argv)
    path = Path(a.doc)
    if not path.is_file():
        print(f"⛔ 파일 없음 — {path}")
        return 2
    page, data = write_html(path, Path(a.out) if a.out else None)
    kinds = {t: sum(x["type"] == t for x in data["items"]) for t in ("replace", "info", "style")}
    print(f"지적 {len(data['items'])}건 — 바로 반영 {kinds['replace']}, 작성자 확인 {kinds['info']}, "
          f"문체 규칙 {kinds['style']} — {page.resolve().as_uri()}")
    if coverage.repo_of(page) is not None:
        print("  ⚠️ 화면이 git 저장소 안에 있습니다 — 문서 원문이 들어 있으니 커밋하지 않습니다")
    if a.serve:
        return serve(page, a.timeout, not a.no_open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
