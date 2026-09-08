---
form: structured
---

# dispatchflow.cc 에 올릴 준비물

**Vermilion 사례집을 dispatchflow.cc 에 붙일 때 손댈 곳 셋** — 다른 세션이 두 저장소를 쓰고 있어 **사용자 신호까지 대기** · 아래 값은 2026-09-07 에 실제 파일을 읽어 맞춘 것

## 이미 끝난 것

| 무엇 | 상태 |
|---|---|
| 사례집을 사이트 규격에 맞춤 | `color-scheme` · `description` · 파비콘 · 제목 넣음 |
| 사례집 검사 | **오류 0 · 주의 0** · 값 슬롯 324 |
| 08 절을 공개 저장소 기준으로 고침 | `git clone` 명령 · MIT · 갈래 고르기 · 이슈로 사례 보내기 |
| 저장소에서 이 페이지로 링크 | README 「사례집」 줄 · 주소는 올린 뒤에 바꿈 |

**사본 없음** — `work-assistant/docs` 의 다른 페이지와 같은 모양(자체 완결 HTML · 폰트 심음)이라 사례집 파일을 그대로 올린다. 두 벌을 두면 한쪽이 낡는다.

## 1. `artifact-host/sources.json` 에 넣을 항목

**구조 확인** — 최상위가 목록 9건 · 키는 `to` `title` `note` `from` `lang` `group` (`build` 는 선택). 아래 항목이 그 모양 그대로다.

```json
{
  "to": "vermilion/index.html",
  "title": "Vermilion — 보내기 전에 한 번 읽는 한글 검사기",
  "note": "사람에게 나갈 한글 문서를 기계가 먼저 읽는다 · 갈래별 수정 전후 사례",
  "from": "P:/github/korean-writing-qa/docs/showcase.html",
  "lang": "ko",
  "group": "vermilion"
}
```

- **`build` 없음** — 사례집은 정적 파일이다.
- **`title`·`note` 는 예비값** — 빌드가 파일 안의 `<title>`·`description` 을 먼저 쓴다(`metaOf`).

### `group` 이 하는 일 셋 — 앞서 하나로만 적었던 값

| 하는 일 | 근거 |
|---|---|
| 번역 짝 맺기 | `langGroups` 가 `group` → (`lang` → 주소) 로 모음 · hreflang 과 언어 전환에 씀 |
| 발행 여부 정하기 | `sitemapXml` 이 `group` 있는 것만 실음 · 없으면 `noindex` |
| 구조화 자료 갈래 붙이기 | `ABOUT[it.group]` 이 없으면 breadcrumb 과 앱 정보가 통째로 빠짐 |

- **한국어 한 벌만 넣어도 됨** — 짝이 없으면 hreflang 을 안 적을 뿐이고 오류가 아니다. 같은 묶음에 같은 `lang` 이 둘이면 그때 빌드가 멈춘다.
- **움직임 CSS 가 딸려 옴** — `group` 이 있고 `demo` 가 아니면 `motionStyle()` 이 붙는다. 사례집에는 `data-rv`·`data-draw` 가 **0개**라 아무 효과가 없다(확인함).

## 2. `artifact-host/scripts/build.mjs` 의 `ABOUT` 에 넣을 한 줄

**넣을 모양** — `dispatch`·`mycelium` 과 같다.

```js
vermilion: {
  type: 'SoftwareApplication', name: 'Vermilion',
  category: 'BusinessApplication',
  crumb: { ko: 'Vermilion', en: 'Vermilion' },
},
```

- **`crumb.en` 도 적음** — 한국어 전용 페이지지만 빌드가 `crumb[lang] || crumb.en` 으로 되짚는다.

## 3. `work-assistant/docs/home.html` 에 넣을 카드 — **지금 막힘**

**다른 세션의 미커밋 변경이 그 파일에 있음**(2026-09-07 15:32 이후) — 손대면 남의 작업과 섞여 한 커밋으로 나간다.

**카드에 쓸 수 있는 실측값**

| 값 | 무엇 |
|---|---|
| 600여 개 | 검사한 사내 보고서 |
| 8% | 형식과 무관한 오류가 있던 문서 — 열두 편에 한 편꼴 |
| 33% | 개조식 규약까지 켰을 때 — 세 편에 한 편꼴 |
| 70% | 지적 가운데 개조식 규약 아홉 갈래가 차지하는 몫 |
| 2초 | 600여 개를 다 보는 데 걸린 시간 |
| 26갈래 | 결정 규칙이 보는 갈래 |
| 70KB 안팎 | 1단계로 받는 파일 하나 · 의존성 0 |

```html
<article>
  <p class="eyebrow">셋째 도구 · 주묵(朱墨)</p>
  <h3>Vermilion</h3>
  <p class="lede">사람에게 나갈 한글 문서를 <b>보내기 전에</b> 기계가 한 번 읽습니다.
    어색한 표기를 갈래로 짚고, 고친 문장을 함께 보여 줍니다.</p>
  <dl class="facts">
    <div><dt>보는 때</dt><dd>문서가 파일에 적히는 순간 — 터미널 대화는 대상 아님</dd></div>
    <div><dt>두 층</dt><dd>글자만 보고 갈리는 것은 규칙이 전수로 · 앞뒤를 읽어야 갈리는 것은 판단 층이 후보를 내고 사람이 확정</dd></div>
    <div><dt>안 건드리는 것</dt><dd>겉모습이 같아도 정당한 표기는 통과 — 정당 20종·위반 15종을 짝으로 넣어 규칙을 고칠 때마다 다시 잼</dd></div>
    <div><dt>골라 쓰기</dt><dd>조직마다 문서 관행이 달라 갈래를 끄고 낮출 수 있음 · 끈 것은 결과에 찍힘</dd></div>
    <div><dt>받는 법</dt><dd>MIT 공개 · 1단계는 파일 하나에 파이썬만</dd></div>
  </dl>
  <div class="figs">
    <div class="fig"><span class="v">603개</span><span class="k">검사한 사내 보고서</span></div>
    <div class="fig"><span class="v">2,174건</span><span class="k">그 안에서 나온 지적</span></div>
    <div class="fig"><span class="v">2.2초</span><span class="k">603개를 다 보는 데 걸린 시간</span></div>
  </div>
  <a class="golink" href="/vermilion/">Vermilion 자세히 보기 →</a>
</article>
```

## 풀린 물음 — 접근 제한

**사이트는 이미 공개** — `wrangler.jsonc` 의 `workers_dev` 가 `false`(2026-09-03 에 끔)라 Cloudflare Access 가 걸려 있던 주소는 살아 있지 않고, 산 도메인 `dispatchflow.cc` 로만 서비스한다. **한 장만 따로 여는 조치가 필요 없다.**

## 정하셔야 하는 것 셋

| 무엇 | 선택지 |
|---|---|
| **사이트 이름** | 지금은 「Dispatch & Mycelium」 · 구조화 자료·breadcrumb·`llms.txt` 가 다 이 글자를 씀 · 셋째 도구가 붙으면 낡음 → 바꿀지 · 그대로 둘지 |
| **「두 도구 비교」 표** | 셋으로 늘릴지 · 둘만 두고 Vermilion 은 카드로만 소개할지 |
| **경로** | 위 제안은 `/vermilion/` |

## 올린 뒤에 할 것

- **README 주소 바꾸기** — 지금은 저장소 안 파일을 가리킨다. 올라가면 공개 주소로.
- **`llms.txt`·`sitemap.xml`** — 빌드가 `sources.json` 에서 만드므로 따로 손댈 것 없음.
- **`artifact-host` 재배포** — 폰트 저작권 고지 수정이 파일에는 있고 서비스판에는 아직 없다.
