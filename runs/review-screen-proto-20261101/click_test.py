"""검토 화면 시안의 버튼이 동작하는지 눌러 본다 — 반영, 갈래 신뢰, 직접 채움, 문체 규칙 끄기, 규칙 남기기."""
from pathlib import Path
from playwright.sync_api import sync_playwright

html = Path.home() / ".local/share/korean-writing-qa/bench-external/review-proto/review-proto.html"
page_src = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"></head>' + html.read_text(encoding="utf-8") + "</html>")
tmp = html.with_name("proto_test.html")       # 저장소 밖(시안과 같은 폴더)에 둠
tmp.write_text(page_src, encoding="utf-8")

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(tmp.as_uri())
    final = lambda: pg.inner_text("#final")
    before = final()
    pg.click('#card-3 button[data-act="accept"]')
    assert "모놀리식 구조를 MSA로 단계적으로 전환하는 작업 참여" in final(), "반영이 최종 문서에 안 들어감"
    pg.check('input[data-trust="업무에서 쓰는 말로 쓰기"]')
    assert "TDD 적용 경험" in final(), "갈래 신뢰가 반영을 안 함"
    info = pg.locator('.card:has(.q)').first
    info.locator('button[data-act="own"]').click()
    box = pg.locator('.card:has(.q) input[type=text]').first
    box.fill("대용량 트래픽(일 평균 주문 320만 건)")
    box.dispatch_event("change")
    assert "일 평균 주문 320만 건" in final(), "직접 채움이 안 들어감"
    pg.check("#styleOff")
    pg.click('#card-7 button[data-rule="7"]')
    rules = pg.inner_text("#side")
    assert "채용 공고에는 문체 규칙" in rules and "코드 리뷰 문화" in rules, "규칙 목록이 안 쌓임"
    bar = pg.inner_text("#bar")
    print("요약 줄:", bar.replace("\n", " "))
    print("최종 문서 바뀜:", before != final(), "· 페이지 오류:", errors or "없음")
    b.close()
