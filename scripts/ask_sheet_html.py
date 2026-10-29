"""사람 확인 표(md)를 카드 HTML 로 바꾸고, 이 PC 안에서 띄워 사람이 고른 답을 표의 「답」 칸에 적는다.

    python -X utf8 scripts/ask_sheet_html.py <표.md>                 # <표>.html 만 씀(답은 「답 복사」로)
    python -X utf8 scripts/ask_sheet_html.py <표.md> --serve         # 띄우고 「제출」을 기다림

**왜 있나** (2026-10-29 사용자) — md 표는 읽기 힘들고(「md 표로 보기가 힘들다」), 답을 복사해 대화에
붙이는 것은 구식이다(「내가 표현한 그대로 직접 읽을 수 없니?」). 시안 다섯 가운데 고른 카드형이다.

**흐름** — `judge_layer2.py --sheet` 로 표를 만들고, 세션이 「제 의견」 칸을 채우고, 이 도구를 `--serve` 로
백그라운드에서 돌린다. 사람이 「제출」을 누르면 답이 표의 「답」 칸에 적히고 이 명령이 끝난다. 세션은 끝났다는
알림을 받고 `judge_layer2.py --answers-from <표.md>` 로 읽는다 — 답 처리는 md 표와 같은 길 하나다.

- **127.0.0.1 의 빈 포트에만 연다** — 표에 문서 원문이 들어 있어 다른 기계에서 못 열게 한다
- **고를 때마다 저장** — `<표>.answers.json` 에 쓴다. 다시 띄우면 불러온다
- **「직접:」에 적은 글은 글자 그대로** 답 칸에 들어간다(칸 경계 `|` 만 `\\|` 로)
- **종료 코드** — 0 제출됨 · 1 시간 초과(그때까지 고른 답은 json 에 남고 표에는 안 적음) · 2 표를 못 읽음
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KINDS = ["고침", "그대로", "직접", "보류"]
KCLS = {"고침": "fix", "그대로": "keep", "직접": "own", "보류": "hold"}
#: 한글 서체를 HTML 에 심는 전역 도구 — 없는 PC 에서는 서체 이름 목록의 안전망으로 그린다
FONT_TOOL = Path.home() / ".claude" / "assets" / "fonts" / "inline-korean-font.py"
ROW = re.compile(r"\s*\|\s*Q?(\d+)\s*\|")


# ── 읽기 ──────────────────────────────────────────────
def cells(line: str) -> list[str]:
    s = line.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def parse_opinion(text: str) -> dict:
    """「제 의견」 칸 — 「직접: 「고칠 말」(까닭)」이면 고칠 말과 까닭을 가른다."""
    m = re.match(r"(고침|그대로|직접|보류)\s*:?\s*(.*)$", text)
    if not m:
        return {"kind": "", "text": "", "note": text}
    kind, rest = m.group(1), m.group(2).strip()
    body, note = rest, ""
    pm = re.match(r"^(.*?)\((.+)\)$", rest)
    if pm:
        body, note = pm.group(1).strip(), pm.group(2).strip()
    if kind != "직접":
        note, body = (note or body), ""
    return {"kind": kind, "text": body.strip("「」"), "note": note}


def parse(md: str) -> dict:
    """판정표 md — `ask_sheet.py` 가 만든 표와 손으로 쓴 같은 형식의 표 둘 다 읽는다."""
    sheet = {"title": "", "ask": "", "use": "", "legend": [], "groups": []}
    group = None
    in_legend = False
    for line in md.split("<!--")[0].splitlines():
        if line.startswith("# "):
            sheet["title"] = line[2:].strip()
        elif re.match(r"\**묻는 것\**\s*:", line.lstrip("- ")):
            sheet["ask"] = line.split(":", 1)[1].strip()
        elif re.match(r"\**판정 결과의 쓰임\**\s*:", line.lstrip("- ")):
            sheet["use"] = line.split(":", 1)[1].strip()
        elif "**답 고르는 법**" in line:
            in_legend = True
            continue
        elif line.startswith("## "):
            in_legend = False
            group = {"name": line[3:].strip(), "rows": []}
            sheet["groups"].append(group)
        elif in_legend and re.match(r"\s*- `", line):
            m = re.match(r"\s*- `([^`]+)`\s*[:—-]?\s*(.*)", line)
            if m:
                sheet["legend"].append((m.group(1).split(":")[0].strip(), m.group(2)))
            continue
        elif ROW.match(line) and group is not None:
            c = cells(line)
            if len(c) < 6:
                continue
            sheet["groups"][-1]["rows"].append({"id": ROW.match(line).group(1), "was": c[1], "fix": c[2],
                                                "why": c[3], "op": parse_opinion(unescape(c[4]))})
        if in_legend and line.strip() and not re.match(r"\s*- ", line):
            in_legend = False
    sheet["groups"] = [g for g in sheet["groups"] if g["rows"]]
    return sheet


def unescape(s: str) -> str:
    """`ask_sheet.cell` 이 막아 둔 글자를 되돌린다(굵게 표시 `**` 는 그대로)."""
    return s.replace("\\|", "|").replace("\\`", "`").replace("&lt;", "<").replace("\\\\", "\\")


# ── 글자 꾸밈 ─────────────────────────────────────────
def inline(s: str, mark: bool = False) -> str:
    """표 칸 글을 HTML 로 — 줄바꿈 `<br>` 은 살리고, 굵게는 원문 칸이면 지적 표시로 바꾼다."""
    s = s.replace("<br>", "\0BR\0").replace("\\*", "\0AST\0")
    s = html.escape(unescape(s), quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", (r'<mark class="hit">\1</mark>' if mark else r"<b>\1</b>"), s)
    return s.replace("\0BR\0", "<br>").replace("\0AST\0", "*")


def op_html(row) -> str:
    op = row["op"]
    parts = [f'<span class="k k-{KCLS.get(op["kind"], "keep")}">{op["kind"]}</span>'] if op["kind"] else []
    if op["text"]:
        parts.append(f'<span class="own-text">「{html.escape(op["text"], quote=False)}」</span>')
    if op["note"]:
        parts.append(f'<span>{inline(op["note"])}</span>')
    if not parts:
        parts.append('<span>세션이 의견을 적지 않음</span>')
    return f'<p class="op"><span class="lbl">제 의견</span>{" ".join(parts)}</p>'


def picks(row) -> str:
    out = "".join(f'<button type="button" class="p-{KCLS[k]}" data-pick="{k}" aria-pressed="false">{k}</button>'
                  for k in KINDS)
    return (f'<div class="picks" role="group" aria-label="{row["id"]}번 답">{out}</div>'
            f'<input class="direct" data-direct type="text" aria-label="{row["id"]}번 직접 고칠 말" '
            'placeholder="고칠 말이나 지시를 적어 주세요">')


CSS = """
:root{color-scheme:light;
  --kr:"Doc KR",Pretendard,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",system-ui,sans-serif;
  --mono:Consolas,ui-monospace,"Cascadia Mono",monospace;
  --bg:#F1F4F7; --surface:#FFFFFF; --ink:#17202B; --muted:#55606E; --line:#D9DFE6; --soft:#E9EEF3;
  --del:#AE2A1F; --del-bg:#FBE7E4; --ins:#0B6A3C;
  --fix:#0B6A3C; --keep:#4A5563; --own:#8C5300; --hold:#5A4AB0; --accent:#1D5CB8;
  --fix-bg:#E1F2E7; --keep-bg:#ECEFF3; --own-bg:#FBEFD9; --hold-bg:#ECE9FA;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 var(--kr);word-break:keep-all;overflow-wrap:anywhere;padding-bottom:140px}
h1,h2,h3{line-height:1.35;letter-spacing:-.02em;text-wrap:balance;margin:0}
p{margin:0}
code{font-family:var(--mono);font-size:.88em;background:var(--soft);padding:.05em .35em;border-radius:4px}
button{font:inherit;color:inherit;cursor:pointer}
button:focus-visible,input:focus-visible{outline:2.5px solid var(--accent);outline-offset:2px}
mark.hit{background:var(--del-bg);color:var(--del);border-radius:3px;padding:0 .15em;font-weight:600}
.k{display:inline-flex;align-items:center;font-size:13px;font-weight:700;line-height:1;padding:.32em .6em;border-radius:999px;white-space:nowrap}
.k-fix{color:var(--fix);background:var(--fix-bg)} .k-keep{color:var(--keep);background:var(--keep-bg)}
.k-own{color:var(--own);background:var(--own-bg)} .k-hold{color:var(--hold);background:var(--hold-bg)}
.op{display:flex;flex-wrap:wrap;gap:.35em .5em;align-items:baseline;color:var(--muted);font-size:15px}
.op .own-text{color:var(--ink);font-weight:600}
.lbl{font-size:13px;font-weight:700;color:var(--muted)}
.wrap{max-width:960px;margin:0 auto;padding:0 16px}
.top{padding:40px 0 24px;display:grid;gap:14px}
.top h1{font-size:clamp(24px,3.4vw,32px);font-weight:750}
.meta{margin:0;display:grid;gap:6px}
.meta div{display:grid;grid-template-columns:8.5em 1fr;gap:12px}
.meta dt{font-weight:700;color:var(--muted);font-size:15px}
.meta dd{margin:0}
.legend{list-style:none;margin:4px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:8px 18px;font-size:14px;color:var(--muted)}
.legend li{display:flex;gap:8px;align-items:center}
.grp{margin-top:28px}
.grp>h2{font-size:18px;font-weight:700;display:flex;gap:10px;align-items:baseline;padding:0 2px 10px}
.grp>h2 small{font-size:14px;color:var(--muted);font-weight:500}
.cards{display:grid;gap:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 20px;display:grid;gap:14px}
.card[data-answer]{border-color:#B9C3CF}
.card[data-differs]{box-shadow:0 0 0 2px var(--own-bg)}
.c-head{display:flex;gap:12px;align-items:baseline}
.no{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:700;color:var(--muted);min-width:2ch}
.why{font-weight:650;font-size:17px}
.diff{border:1px solid var(--line);border-radius:10px;overflow:hidden}
.diff>div{display:grid;grid-template-columns:5.5em 1fr;gap:12px;padding:10px 14px}
.diff .was{background:#FCF6F5}
.diff .now{background:#F3FAF5;border-top:1px solid var(--line)}
.diff .now p{color:var(--ins);font-weight:600}
.diff .lbl{padding-top:.15em}
.c-foot{display:flex;flex-wrap:wrap;gap:12px 20px;align-items:center;justify-content:space-between}
.c-foot .op{flex:1 1 300px}
.c-foot .ans{flex:0 0 auto;width:min(100%,380px)}
.picks{display:inline-flex;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--surface)}
.picks button{border:0;background:none;padding:9px 14px;min-height:44px;font-size:15px;font-weight:600;color:var(--muted);border-left:1px solid var(--line)}
.picks button:first-child{border-left:0}
.picks button:hover{background:var(--soft)}
.picks button[aria-pressed=true].p-fix{background:var(--fix);color:#fff}
.picks button[aria-pressed=true].p-keep{background:var(--keep);color:#fff}
.picks button[aria-pressed=true].p-own{background:var(--own);color:#fff}
.picks button[aria-pressed=true].p-hold{background:var(--hold);color:#fff}
.direct{display:none;width:100%;margin-top:8px;font:inherit;font-size:15px;padding:10px 12px;border:1.5px solid var(--own);border-radius:8px;background:#fff}
[data-answer="직접"] .direct{display:block}
.bar{position:fixed;left:0;right:0;bottom:0;z-index:10;background:rgba(255,255,255,.96);backdrop-filter:blur(6px);border-top:1px solid var(--line);
  display:flex;gap:12px 18px;align-items:center;padding:12px max(16px,calc((100vw - 1200px)/2));flex-wrap:wrap}
.prog{font-size:15px;color:var(--muted);white-space:nowrap}
.prog b{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:18px;color:var(--ink)}
.out{flex:1 1 260px;min-width:0;font-size:14px;white-space:pre-line;max-height:4.8em;overflow:auto}
.acts{display:flex;gap:8px;flex-wrap:wrap}
.acts button{min-height:44px;padding:8px 14px;border-radius:10px;border:1px solid var(--line);background:#fff;font-size:15px;font-weight:600}
.acts .primary{background:var(--accent);border-color:var(--accent);color:#fff}
[data-act=submit]{display:none}
.served [data-act=copy]{display:none}
.served [data-act=submit]{display:inline-block}
.note{flex-basis:100%;font-size:14px;font-weight:600;color:var(--own)}
.note:empty{display:none}
.submitted .note{color:var(--fix)}
.submitted .picks,.submitted .acts,.submitted .direct{pointer-events:none;opacity:.55}
@media (max-width:620px){.diff>div{grid-template-columns:1fr;gap:2px}.picks{width:100%}.picks button{flex:1;padding:9px 6px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
"""

JS = r"""
(function(){
  var S = JSON.parse(document.getElementById('sheet-data').textContent);
  var KEY = 'judge-sheet:' + S.key, A = {};
  try { A = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { A = {}; }
  // --serve 로 띄웠으면 답을 고를 때마다 파일로 저장하고, 「제출」로 세션에 넘긴다
  var SV = window.JUDGE_SERVE || null, timer = null, armed = false;
  if (SV){ document.documentElement.classList.add('served'); if (SV.saved && !Object.keys(A).length) A = SV.saved; }
  var byId = {}; S.items.forEach(function(i){ byId[i.id] = i; });
  function post(final){
    return fetch('/save', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Judge-Token': SV.token},
      body: JSON.stringify({answers: A, text: text(), final: !!final})}).then(function(r){ if (!r.ok) throw new Error(r.status); });
  }
  function note(t){ document.querySelectorAll('[data-note]').forEach(function(e){ e.textContent = t; }); }
  function autosave(){ if (!SV) return; clearTimeout(timer); timer = setTimeout(function(){
    post(false).catch(function(){ note('저장하지 못했습니다 — 판정표를 띄운 창이 닫혔을 수 있습니다'); }); }, 400); }
  function save(){ try { localStorage.setItem(KEY, JSON.stringify(A)); } catch (e) {} autosave(); armed = false; note(''); }
  function els(id){ return document.querySelectorAll('[data-item="' + id + '"]'); }
  function same(i){ var a = A[i.id]; if (!a || a.kind !== i.op.kind) return false;
    return i.op.kind !== '직접' || (a.text || '') === (i.op.text || ''); }
  function paint(id){
    var a = A[id];
    els(id).forEach(function(el){
      if (a) el.setAttribute('data-answer', a.kind); else el.removeAttribute('data-answer');
      el.toggleAttribute('data-differs', !!a && !same(byId[id]));
      el.querySelectorAll('[data-pick]').forEach(function(b){ b.setAttribute('aria-pressed', String(!!a && b.dataset.pick === a.kind)); });
      var inp = el.querySelector('[data-direct]'); if (inp && a && document.activeElement !== inp) inp.value = a.text || '';
    });
  }
  function fmt(i){ var a = A[i.id]; return i.id + ' ' + (a.kind === '직접' ? '직접: ' + (a.text || '…') : a.kind); }
  function text(){
    var items = S.items, done = items.filter(function(i){ return A[i.id]; });
    if (!done.length) return '';
    if (done.length === items.length){
      var diff = items.filter(function(i){ return !same(i); });
      if (!diff.length) return '전부 의견대로';
      if (diff.length * 2 <= items.length) return '의견대로, 단 ' + diff.map(fmt).join(', ');
    }
    var lines = [];
    ['고침', '그대로', '보류'].forEach(function(k){
      var ids = done.filter(function(i){ return A[i.id].kind === k; }).map(function(i){ return i.id; });
      if (ids.length) lines.push(k + ' ' + ids.join(', '));
    });
    done.filter(function(i){ return A[i.id].kind === '직접'; }).forEach(function(i){ lines.push(i.id + ' 직접: ' + (A[i.id].text || '…')); });
    var rest = items.filter(function(i){ return !A[i.id]; }).map(function(i){ return i.id; });
    if (rest.length) lines.push('아직 안 고름 ' + rest.join(', '));
    return lines.join('\n');
  }
  function summary(){
    var n = S.items.filter(function(i){ return A[i.id]; }).length;
    document.querySelectorAll('[data-progress]').forEach(function(e){ e.textContent = n; });
    var t = text();
    document.querySelectorAll('[data-output]').forEach(function(e){ e.textContent = t || '아직 고른 답 없음'; });
  }
  function set(id, kind){
    if (kind === null) delete A[id];
    else A[id] = {kind: kind, text: kind === '직접' ? ((A[id] && A[id].text) || (byId[id].op.kind === '직접' ? byId[id].op.text : '')) : ''};
    save(); paint(id); summary();
  }
  document.addEventListener('click', function(ev){
    var b = ev.target.closest('[data-pick]');
    if (b){
      var id = b.closest('[data-item]').dataset.item, k = b.dataset.pick;
      set(id, A[id] && A[id].kind === k ? null : k);
      if (k === '직접' && A[id]){ var inp = b.closest('[data-item]').querySelector('[data-direct]'); if (inp) inp.focus(); }
      return;
    }
    var act = ev.target.closest('[data-act]'); if (!act) return;
    var a = act.dataset.act;
    if (a === 'fill'){ S.items.forEach(function(i){ if (!A[i.id] && i.op.kind) A[i.id] = {kind: i.op.kind, text: i.op.text || ''}; paint(i.id); }); save(); summary(); }
    if (a === 'clear'){ A = {}; save(); S.items.forEach(function(i){ paint(i.id); }); summary(); }
    if (a === 'copy'){
      var t = text() || '';
      var done = function(){ var o = act.textContent; act.textContent = '복사함'; setTimeout(function(){ act.textContent = o; }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(done, function(){ fallback(t); done(); });
      else { fallback(t); done(); }
    }
    if (a === 'submit' && SV){
      var left = S.items.filter(function(i){ return !A[i.id]; }).length;
      if (left && !armed){ armed = true; note(left + '건을 아직 안 골랐습니다 — 그대로 제출하려면 한 번 더 누릅니다'); return; }
      clearTimeout(timer);
      post(true).then(function(){ document.documentElement.classList.add('submitted'); note('제출했습니다 — 대화창으로 돌아가시면 됩니다'); },
                      function(){ note('제출하지 못했습니다 — 판정표를 띄운 창이 닫혔을 수 있습니다'); });
    }
  });
  function fallback(t){ var ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) {} ta.remove(); }
  document.addEventListener('input', function(ev){
    var inp = ev.target.closest('[data-direct]'); if (!inp) return;
    var id = inp.closest('[data-item]').dataset.item; A[id] = {kind: '직접', text: inp.value}; save();
    els(id).forEach(function(el){ el.toggleAttribute('data-differs', !same(byId[id])); }); summary();
  });
  S.items.forEach(function(i){ paint(i.id); }); summary();
})();
"""


def render(sheet: dict) -> str:
    rows = [r for g in sheet["groups"] for r in g["rows"]]
    legend = "".join(f'<li><span class="k k-{KCLS.get(k, "keep")}">{html.escape(k)}</span>{inline(v)}</li>'
                     for k, v in sheet["legend"])
    meta = f'<div><dt>묻는 것</dt><dd>{html.escape(sheet["ask"] or "원문을 고칠까요?")}</dd></div>'
    if sheet["use"]:
        meta += f'<div><dt>판정 결과의 쓰임</dt><dd>{inline(sheet["use"])}</dd></div>'
    out = [f'<div class="wrap"><header class="top"><h1>{html.escape(sheet["title"])}</h1>'
           f'<dl class="meta">{meta}</dl><ul class="legend">{legend}</ul></header>']
    for g in sheet["groups"]:
        out.append(f'<section class="grp"><h2>{html.escape(g["name"])}<small>{len(g["rows"])}건</small></h2><div class="cards">')
        for r in g["rows"]:
            out.append(f"""<article class="card" data-item="{r['id']}">
  <div class="c-head"><span class="no">{r['id']}</span><h3 class="why">{inline(r['why'])}</h3></div>
  <div class="diff">
    <div class="was"><span class="lbl">원문</span><p>{inline(r['was'], mark=True)}</p></div>
    <div class="now"><span class="lbl">고친 말</span><p>{inline(r['fix'])}</p></div>
  </div>
  <div class="c-foot">{op_html(r)}<div class="ans">{picks(r)}</div></div>
</article>""")
        out.append("</div></section>")
    out.append("</div>")
    data = json.dumps({"key": sheet["title"], "items": [{"id": r["id"], "op": r["op"]} for r in rows]},
                      ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(sheet["title"] or "판정 요청")}</title>
<style>{CSS}</style>
</head>
<body>
{"".join(out)}
<div class="bar" role="region" aria-label="답 정리">
  <p class="prog"><b data-progress>0</b> / {len(rows)} 답함</p>
  <output data-output class="out">아직 고른 답 없음</output>
  <div class="acts">
    <button type="button" data-act="fill">의견대로 채우기</button>
    <button type="button" data-act="clear">지우기</button>
    <button type="button" data-act="copy" class="primary">답 복사</button>
    <button type="button" data-act="submit" class="primary">제출</button>
  </div>
  <p class="note" data-note role="status"></p>
</div>
<script type="application/json" id="sheet-data">{data}</script>
<script>{JS}</script>
</body>
</html>
"""


def write_html(md_path: Path) -> Path:
    out = md_path.with_suffix(".html")
    out.write_text(render(parse(md_path.read_text(encoding="utf-8"))), encoding="utf-8")
    if FONT_TOOL.is_file():
        subprocess.run([sys.executable, "-X", "utf8", str(FONT_TOOL), str(out)], capture_output=True)
    return out


# ── 답을 표에 적기 ────────────────────────────────────
def answer_cell(a: dict) -> str:
    """고른 답을 표의 「답」 칸 글로 — `ask_sheet.kind_of` 가 읽는 꼴."""
    kind = str(a.get("kind") or "")
    if kind not in KINDS:
        return ""
    text = f"직접: {a.get('text') or ''}".strip() if kind == "직접" else kind
    return re.sub(r"\s+", " ", text).replace("|", "\\|")


def fill_answers(md: str, answers: dict) -> str:
    """번호가 맞는 행의 맨 오른쪽 칸(답)을 바꾼다 — 나머지 칸과 열쇠 주석은 글자 그대로 둔다."""
    head, sep, tail = md.partition("<!--")
    lines = []
    for line in head.split("\n"):
        m = ROW.match(line)
        if m and m.group(1) in answers:
            c = cells(line)
            c[-1] = answer_cell(answers[m.group(1)])
            line = "| " + " | ".join(c) + " |"
        lines.append(line)
    return "\n".join(lines) + sep + tail


# ── 띄우기 ────────────────────────────────────────────
def serve(md_path: Path, timeout: float, open_browser: bool = True, ready=None) -> int:
    page = write_html(md_path)
    store = md_path.with_suffix(".answers.json")
    token = secrets.token_urlsafe(18)
    saved = None
    if store.is_file():
        try:
            saved = json.loads(store.read_text(encoding="utf-8")).get("answers") or None
        except ValueError:
            saved = None
    boot = json.dumps({"token": token, "saved": saved}, ensure_ascii=False).replace("</", "<\\/")
    body_html = page.read_text(encoding="utf-8").replace(
        "</head>", f"<script>window.JUDGE_SERVE={boot};</script>\n</head>", 1).encode("utf-8")
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # 접속 기록을 출력하지 않음
            pass

        def reply(self, code: int, body: bytes = b"", kind: str = "text/plain; charset=utf-8") -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.split("?")[0] != "/":
                return self.reply(404)
            self.reply(200, body_html, "text/html; charset=utf-8")

        def do_POST(self):
            # 거절할 요청도 본문을 먼저 읽는다 — 안 읽고 닫으면 Windows 에서 응답 대신 연결이 끊긴다
            raw = self.rfile.read(min(int(self.headers.get("Content-Length", 0) or 0), 4 << 20))
            if self.path != "/save" or not secrets.compare_digest(self.headers.get("X-Judge-Token", ""), token):
                return self.reply(403)
            try:
                body = json.loads(raw.decode("utf-8"))
                answers = body["answers"]
                assert isinstance(answers, dict)
            except Exception:  # noqa: BLE001 — 형식이 틀린 요청은 거절만 한다
                return self.reply(400)
            row = {"sheet": md_path.name, "saved_at": datetime.now().isoformat(timespec="seconds"),
                   "final": bool(body.get("final")), "summary": str(body.get("text") or ""), "answers": answers}
            tmp = store.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, store)
            if row["final"]:
                md_path.write_text(fill_answers(md_path.read_text(encoding="utf-8"), answers),
                                   encoding="utf-8", newline="\n")
            self.reply(200, b"ok")
            if row["final"]:
                done.set()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"판정표 — {url}", flush=True)
    if ready:
        ready(url)
    if open_browser:
        webbrowser.open(url)
    ok = done.wait(timeout)
    srv.shutdown()
    srv.server_close()
    if not ok:
        print(f"시간 초과 — 제출 전에 끝남 · 그때까지 고른 답: {store}")
        return 1
    row = json.loads(store.read_text(encoding="utf-8"))
    print(f"제출됨 — 답 {len(row['answers'])}건을 표의 「답」 칸에 적음 · {md_path}")
    print(row["summary"])
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="사람 확인 표(md)를 카드 HTML 로 — --serve 로 띄워 답을 받음")
    ap.add_argument("sheet", help="judge_layer2.py --sheet 로 만든 표(md)")
    ap.add_argument("--serve", action="store_true", help="이 PC 안에서 띄우고 「제출」을 기다림")
    ap.add_argument("--timeout", type=float, default=4 * 3600, help="제출을 기다리는 초(기본 4시간)")
    ap.add_argument("--no-open", action="store_true", help="브라우저를 열지 않음")
    a = ap.parse_args(argv)
    md_path = Path(a.sheet)
    try:
        sheet = parse(md_path.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"⛔ {e}")
        return 2
    if not sheet["groups"]:
        print("⛔ 판정 행을 찾지 못했습니다 — 칸이 #, 원문, 고친 말, 고친 이유, 제 의견, 답인 표를 줍니다")
        return 2
    if a.serve:
        return serve(md_path, a.timeout, not a.no_open)
    print(f"판정표 HTML — {write_html(md_path).resolve().as_uri()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
