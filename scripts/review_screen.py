"""검토 화면 — 문서 하나의 지적(2층 고칠 지적, 사람 확인, 1층 검사기)을 원문 위에 표시하고 고르는 HTML 을 만든다.

    python -X utf8 scripts/review_screen.py <문서>                 # HTML 만 씀(저장소 밖)
    python -X utf8 scripts/review_screen.py <문서> --serve         # 이 PC 안에서 띄움

**왜 있나** (2026-11-02 사용자 결정) — 판정표(사람 확인 카드)를 대신한다. 원문과 지적 카드가 따로 스크롤되며
서로 따라가고(시안 A3, `draft-redline` 의 비교 화면과 같은 방식), 전체와 갈래별로 한꺼번에 고를 수 있다.
시안과 그 결정은 `runs/review-screen-proto-20261101/README.md`.

**지금 단계** — 2단계(답 기록). `--serve` 로 띄운 화면에서 「제출」을 누르면 고른 답을 판정표의 답과 같은
기록에 남기고, 세션에는 요약만 낸다(`submit`). 파일은 아직 세션이 고친다 — 파일 반영(3단계), 신뢰 설정과
규칙 저장(4단계)은 뒤에 붙인다.

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
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ask_sheet  # noqa: E402
import judge_layer2 as judge  # noqa: E402
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


def literal(new: str) -> bool:
    """고친 말을 글자 그대로 넣을 수 있나 — 자리표시(「(…)」, 「○○」)나 여러 줄이면 세션이 고친다."""
    return bool(new) and not new.startswith("(") and "○○" not in new and "\n" not in new


def submit(path: Path, data: dict, picks: list[dict]) -> tuple[int, str]:
    """화면에서 고른 답을 판정 기록에 남긴다 — (종료 코드, 세션이 받을 요약).

    판정표의 답 처리(`judge_layer2.read_answers`)와 같은 기록에 같은 규칙으로 적는다.

    - **반영과 직접 고침** — 답 기록에 「고침」으로 남기고, 그 줄을 고른 글로 바꾼 결과를 사람이 판정한 줄로
      확정한다(`approve`). 세션이 그 글대로 고치면 판정기가 다시 보지 않는다. 판정표의 「직접」과 달리
      고친 말이 화면에서 글자로 오므로 고친 뒤 `--answer` 를 따로 부르지 않는다
    - **그대로** — 사람 확인은 그 줄의 사람 확인을 모두 그대로 골랐을 때 `answer` 로 닫는다. 고칠 지적은
      사유 「사용자답」으로 닫는다(세션이 쓰는 `--dismiss` 사유와 따로 둔다 — 세션이 고를 수 없는 사유다)
    - **세션에 맡김과 남음** — 둘 다 기록하지 않는다. 맡긴 것은 요약에 싣는다
    - **1층 지적** — 판정 기록이 아니라 검사기 몫이라 고칠 것과 그대로 둔 것을 요약에만 싣는다

    ⛔ 화면을 연 뒤 바뀐 줄의 답은 받지 않는다 — 사용자가 본 문장과 지금 문장이 다르다.
    ⛔ 판정기가 본 적 없는 줄은 확정하지 않는다 — 확정하면 판정기가 한 번도 안 본 글이 판정을 건너뛴다.
    종료 코드 — 0은 남은 사람 확인과 고칠 지적이 없음, 1은 남음
    """
    items = {x["id"]: x for x in data["items"]}
    lines = coverage.read_doc(path).splitlines()
    key = coverage.doc_key(path)
    seen = coverage.judged(key, fresh=False)
    src = f"검토 화면 {path.name}"
    by_line: dict[int, list[tuple[dict, str, str]]] = defaultdict(list)
    refused = []
    for p in picks:
        it, dec = items.get(int(p.get("id") or 0)), p.get("dec")
        own = str(p.get("own") or "").strip() if dec == "own" else ""
        if not it or dec not in ("accept", "own", "keep", "delegate") or (dec == "own" and not own):
            continue
        n = it["line"]
        if n > len(lines) or (coverage.line_key(lines[n - 1]) or "") != it["line_key"]:
            refused.append(f"#{it['id']} {n}행 — 화면을 연 뒤 그 줄이 바뀌었습니다. 화면을 다시 엽니다")
            continue
        by_line[n].append((it, dec, own))
    counts = defaultdict(int)
    edits, loose, delegated, l1_kept = [], [], [], []
    learned = closed = settled = 0
    for n, picked in sorted(by_line.items()):
        line, lk = lines[n - 1], coverage.line_key(lines[n - 1]) or ""
        target, exact = line, True
        for it, dec, own in sorted(picked, key=lambda t: line.find(t[0]["phrase"])):
            counts[dec] += 1
            two = it["layer"] == "2층"
            item = {"category": it["cat"], "phrase": it["phrase"], "fix": it["fix"]}
            if dec in ("accept", "own"):
                new = it["fix"] if dec == "accept" else own
                ok = literal(new) and bool(it["phrase"]) and it["phrase"] in target
                if ok:
                    target = target.replace(it["phrase"], new, 1)
                exact &= ok
                (edits if ok else loose).append(f"{n}행 「{it['phrase']}」 → 「{new}」")
                if two:
                    raw = ask_sheet.EDIT if dec == "accept" else f"{ask_sheet.DIRECT}: {own}"
                    learned += judge.record_decision(path, lk, raw, ask_sheet.EDIT, f"{src} #{it['id']}", line, [item])
            elif dec == "keep" and two:
                learned += judge.record_decision(path, lk, ask_sheet.KEEP, ask_sheet.KEEP, f"{src} #{it['id']}", line, [item])
                if it["level"] != "사람 확인":
                    judge._close_fix(path, lines, n, {**item, "why": it["why"], "check": it["check"]},
                                     {"reason": "사용자답", "note": f"사용자 답({src} #{it['id']}): 그대로"})
                    closed += 1
            elif dec == "keep":
                l1_kept.append(f"#{it['id']} {n}행 [{it['cat']}] {it['level']}")
            else:
                delegated.append(f"#{it['id']} {n}행 「{it['phrase'][:30]}」 — {it['check'] or it['cat']}")
        asks = [x for x in data["items"] if x["line"] == n and x["level"] == "사람 확인"]
        kept = {it["id"] for it, dec, _ in picked if dec == "keep"}
        if asks and target == line and all(x["id"] in kept for x in asks):
            judge.answer(path, [n], f"사용자 답({src}): 그대로")
            closed += len(asks)
        if target != line and exact and lk in seen and not any(d == "delegate" for _, d, _ in picked):
            judge.approve(path, target, f"사용자 답({src}): 고른 글로 확정", lk)
            settled += 1
    left_asks = len(coverage.open_asks(key, lines))
    left_fixes = len(coverage.open_fixes(key, lines))
    pending = len(items) - sum(counts.values()) - len(refused)
    out = [f"검토 화면 제출 — {path.name}: 반영 {counts['accept']}, 직접 {counts['own']}, 그대로 {counts['keep']}, "
           f"맡김 {counts['delegate']}, 남음 {pending}",
           f"  답 기록 {learned}건, 그대로로 닫은 지적 {closed}건, 다시 판정하지 않을 줄 {settled}개"]
    if edits:
        out.append(f"  고칠 것 {len(edits)}건 — 화면에서 고른 글자 그대로 고칩니다(확정한 줄은 다시 판정하지 않음)")
        out += [f"    {e}" for e in edits]
    if loose:
        out.append(f"  세션이 고칠 것 {len(loose)}건 — 글자로 넣을 수 없는 수정안이라 고친 뒤 --since 로 다시 판정")
        out += [f"    {e}" for e in loose]
    if delegated:
        out.append(f"  세션에 맡김 {len(delegated)}건 — 고친 뒤 --since 로 다시 판정")
        out += [f"    {d}" for d in delegated]
    if l1_kept:
        out.append(f"  1층 그대로 {len(l1_kept)}건 — 오류는 그대로 두면 발행이 막히고, 주의는 판단 기록"
                   "(check_record --stage review)을 남깁니다")
        out += [f"    {k}" for k in l1_kept]
    out += [f"  ⛔ {r}" for r in refused]
    out.append(f"  고치기 전 기준 — 남은 사람 확인 {left_asks}건, 처리 안 된 고칠 지적 {left_fixes}건")
    return (1 if left_asks or left_fixes or pending else 0), "\n".join(out)


def serve(page: Path, timeout: float, open_browser: bool = True, ready=None, on_submit=None) -> int:
    """화면을 띄운다 — 화면 하나와 제출(`POST /submit`)만 받는다. 제출을 받으면 요약을 내고 끝난다.

    제출은 화면 주소의 토큰과 이 PC 주소(Host)가 맞아야 받는다 — 다른 페이지가 이 포트로 답을 보내지 못하게.
    종료 코드 — 제출을 받으면 제출의 종료 코드, 제출 없이 시간이 다 되면 1
    """
    body = page.read_bytes()
    stop = threading.Event()
    token = secrets.token_urlsafe(12)
    result = {"code": 1}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 접속 기록을 출력하지 않음
            pass

        def _send(self, code: int, payload: dict) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            # 거절할 때도 본문을 먼저 읽는다 — 안 읽고 닫으면 Windows 가 연결을 끊어 응답이 안 닿는다
            try:
                size = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                size = 0
            raw = self.rfile.read(min(size, 2_000_000))
            if self.path != "/submit" or self.headers.get("Host") != f"127.0.0.1:{srv.server_address[1]}":
                return self._send(404, {"ok": False, "error": "없는 주소"})
            try:
                req = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"ok": False, "error": "제출 내용을 못 읽음"})
            if not secrets.compare_digest(str(req.get("t") or ""), token):
                return self._send(403, {"ok": False, "error": "화면 주소의 토큰이 맞지 않음 — 세션이 띄운 주소로 엶"})
            if stop.is_set() or on_submit is None:
                return self._send(409, {"ok": False, "error": "이미 제출했거나 제출을 받지 않는 화면"})
            try:
                result["code"], summary = on_submit(req.get("picks") or [])
            except (ValueError, OSError) as e:
                return self._send(500, {"ok": False, "error": str(e)})
            print(summary, flush=True)
            self._send(200, {"ok": True, "summary": summary})
            stop.set()

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
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={token}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"검토 화면 — {url}", flush=True)
    if ready:
        ready(url)
    if open_browser:
        webbrowser.open(url)
    if not stop.wait(timeout):
        print("제출 없이 시간이 다 됐습니다 — 고른 답은 기록되지 않았습니다", flush=True)
    srv.shutdown()
    srv.server_close()
    return result["code"]


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
        return serve(page, a.timeout, not a.no_open, on_submit=lambda picks: submit(path, data, picks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
