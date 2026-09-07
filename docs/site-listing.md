---
form: structured
---

# dispatchflow.cc 에 올릴 준비물

**dispatchflow.cc 에 한글 검사기를 올릴 때 붙일 것 셋** — 다른 세션이 `artifact-host` 를 쓰고 있어 적용은 안 함 · 사례집 쪽 손질은 끝남

## 이미 끝난 것

| 무엇 | 상태 |
|---|---|
| 사례집을 사이트 규격에 맞춤 | `color-scheme` · `description` · 파비콘 · 제목 넣음 · 오류 0 |
| 08 절을 공개 저장소 기준으로 고침 | `git clone` 명령 · MIT · 갈래 고르기 · 이슈로 사례 보내기 |
| 저장소에서 이 페이지로 링크 | README 「사례집」 줄 · 주소는 올린 뒤에 바꿈 |

**사본 없음** — `work-assistant/docs` 의 다른 페이지와 같은 모양(자체 완결 HTML · 폰트 심음)이라 사례집 파일을 그대로 올릴 수 있다. 두 벌을 두면 한쪽이 낡는다.

## 1. `artifact-host/sources.json` 에 넣을 항목

**이름은 Vermilion 으로 정해짐**(2026-09-07) — 주묵(朱墨) · 원고를 고칠 때 쓰던 붉은 먹. 사례집의 붉은색이 그 뜻으로 바뀌었다.

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

- **★ `build.mjs` 의 `ABOUT` 표에 항목을 더해야 함** — `dispatch`·`mycelium` 처럼 `vermilion` 한 줄. 없으면 구조화 자료의 갈래와 breadcrumb 이 비어 나간다.

```js
vermilion: {
  type: 'SoftwareApplication', name: 'Vermilion',
  category: 'BusinessApplication',
  crumb: { ko: 'Vermilion', en: 'Vermilion' },
},
```

- **`group` 을 적으면 공개 대상이 됨** — 빌드가 `group` 있는 페이지만 sitemap 에 싣는다. 안 적으면 `noindex` 가 붙고 검색에서 빠진다. 번역 짝을 맺는 값이 아니라 **발행 여부를 정하는 값**이다.
- **`build` 필요 없음** — 사례집은 정적 파일이다.

## 2. `work-assistant/docs/home.html` 에 넣을 카드

**지금 소개 화면은 도구 둘** — 셋으로 늘리면 두 곳을 함께 고쳐야 한다.

- **도구 카드 하나 추가** — `<article>` 에 `figs` 통계 셋과 `golink`
- **「두 도구 비교」 표** — 제목과 열이 둘 기준이라 손봐야 함. 셋으로 늘리거나, 그 표는 Dispatch·Mycelium 둘만 두고 검사기는 카드로만 소개

**카드에 쓸 수 있는 실측값**

| 값 | 무엇 |
|---|---|
| 603개 | 검사한 사내 보고서 |
| 2,174건 | 그 안에서 나온 지적 |
| 32% | 오류가 하나라도 있던 문서 — 세 편에 한 편꼴 |
| 2.2초 | 603개를 다 보는 데 걸린 시간 |
| 26갈래 | 결정 규칙이 보는 갈래 |
| 68KB | 1단계로 받는 파일 하나 · 의존성 0 |

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

## 3. 올린 뒤에 할 것

- **README 주소 바꾸기** — 지금은 저장소 안 파일을 가리킨다. 올라가면 공개 주소로.
- **`llms.txt`·`sitemap.xml`** — 빌드가 `sources.json` 에서 만드므로 따로 손댈 것 없음.
- **접근 제한 확인** — `artifact-host` 는 Cloudflare Access 뒤에 있다. 이 페이지는 사내 내용이 없어 밖에 열어도 되지만, **사이트 전체 설정이라 한 장만 따로 열 수 있는지 확인이 필요**하다.

## 정하셔야 하는 것

- **경로** — 위 제안은 `/vermilion/`
- **비교 표** — 셋으로 늘릴지, 둘만 두고 카드로만 소개할지
