```python
import json
import html
from datetime import datetime
from pathlib import Path

INPUT_FILE = Path("data/news.json")
OUTPUT_FILE = Path("docs/index.html")

CATEGORY_INFO = {
    "policy": ("01", "제도 동향", "policy"),
    "medical": ("02", "의료비 이슈", "medical"),
    "samsung_fire": ("03", "삼성화재 소식", "samsung"),
}


# ============================================================
# 공통 유틸
# ============================================================

def esc(value):
    """HTML 특수문자 안전 처리"""
    return html.escape(str(value or ""), quote=True)


def get_naver_url(article):
    """
    NAVER 원문 URL을 최우선으로 사용한다.

    우선순위:
    1. naver_url
    2. source_url
    3. url

    AI가 생성한 URL이 아니라 news_search.py에서 확보한
    원문 URL을 그대로 사용하는 것이 핵심이다.
    """
    return (
        article.get("naver_url")
        or article.get("source_url")
        or article.get("url")
        or ""
    )


def get_published_at(article):
    """
    발행일 원본 필드를 우선적으로 가져온다.

    우선순위:
    1. published_at
    2. pubDate
    3. published
    4. date
    """
    return (
        article.get("published_at")
        or article.get("pubDate")
        or article.get("published")
        or article.get("date")
        or ""
    )


def format_date(value):
    """
    발행일을 모바일 카드에 표시하기 좋은 형식으로 변환한다.

    원본 데이터 자체는 변경하지 않고
    화면 표시용으로만 변환한다.
    """
    value = str(value or "").strip()

    if not value:
        return "발행일 미상"

    # ISO 형식
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y.%m.%d %H:%M")
    except (ValueError, TypeError):
        pass

    # NAVER API pubDate 형식
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y.%m.%d %H:%M")
        except (ValueError, TypeError):
            continue

    # 파싱할 수 없는 값은 원본을 최대한 유지
    return value[:19].replace("T", " ")


def get_source(article):
    """언론사 이름 표시"""
    return (
        article.get("source")
        or article.get("press")
        or article.get("publisher")
        or ""
    )


def get_text(article, *keys):
    """여러 후보 필드 중 첫 번째 값을 반환"""
    for key in keys:
        value = article.get(key)
        if value:
            return str(value)
    return ""


# ============================================================
# 기사 카드
# ============================================================

def article_page(article, category_key, number):
    num, badge, css = CATEGORY_INFO[category_key]

    title = esc(
        get_text(article, "title")
        or "제목 없음"
    )

    summary = esc(
        get_text(article, "summary", "description")
        or "요약 내용이 없습니다."
    )

    why = esc(
        get_text(article, "why_it_matters", "why")
        or "보험 영업 관점에서 확인할 필요가 있는 뉴스입니다."
    )

    tip = esc(
        get_text(article, "sales_tip", "salesTip", "tip")
        or "고객의 보장 점검과 연결할 수 있는 내용을 확인해 보세요."
    )

    source = esc(get_source(article))

    published_raw = get_published_at(article)
    published = esc(format_date(published_raw))

    # ========================================================
    # 중요:
    # NAVER 원문 URL을 최우선으로 사용
    # ========================================================
    source_url_raw = get_naver_url(article)
    source_url = esc(source_url_raw)

    # URL이 없는 경우에도 HTML이 깨지지 않도록 처리
    if source_url_raw:
        source_button = (
            f'<a class="source" href="{source_url}" '
            f'target="_blank" rel="noopener noreferrer">'
            f'NAVER 원문 기사 보기 →</a>'
        )
    else:
        source_button = (
            '<div class="source disabled">'
            '원문 링크 확인 필요'
            '</div>'
        )

    meta_source = f" · {source}" if source else ""

    return f'''<section class="page article-page {css}">
  <div class="topline">
    <span>{num} / {number:02d}</span>
    <span class="stamp">MORNING BRIEF</span>
  </div>

  <div class="badge">{badge}</div>

  <h1>{title}</h1>

  <div class="meta">
    {published}{meta_source}
  </div>

  <div class="rule"></div>

  <p class="summary">{summary}</p>

  <div class="why">
    <div class="label">WHY IT MATTERS</div>
    <div>{why}</div>
  </div>

  <div class="tip">
    <div class="tip-title">오늘의 영업 Tip</div>
    <div>{tip}</div>
  </div>

  {source_button}

  <div class="swipe">← 좌우로 스와이프 →</div>
</section>'''


# ============================================================
# 표지
# ============================================================

def cover_page(date_text, counts):
    rows = []

    for key, (num, label, _) in CATEGORY_INFO.items():
        count = counts.get(key, 0)

        # 삼성화재 소식 포함 모든 카테고리:
        # 0건이면 표지에서도 표시하지 않는다.
        if count > 0:
            rows.append(
                f'<div class="toc-row">'
                f'<span>{num}　{label}</span>'
                f'<b>{count}건</b>'
                f'</div>'
            )

    toc = "".join(rows)

    return f'''<section class="page cover">

  <div class="cover-head">
    <span>GANGWON SALES DIVISION</span>
    <span class="stamp">DAILY DOSSIER</span>
  </div>

  <div class="cover-main">
    <div class="gold">강원영업단 RC를 위한</div>

    <h1>
      Morning<br>
      <span>Brief</span>
    </h1>

    <div class="date">{esc(date_text)}</div>
  </div>

  <div class="toc">
    <div class="toc-title">CONTENTS</div>
    {toc}
  </div>

  <div class="cover-foot">
    보험 · 의료 · 영업 인사이트　|　Swipe →
  </div>

</section>'''


# ============================================================
# 마지막 영업 포인트
# ============================================================

def closing_page(points):

    if not points:
        points = [
            "오늘 뉴스 중 고객의 건강·의료비 걱정과 연결할 수 있는 주제를 하나 골라 대화를 시작해 보세요."
        ]

    rows = ""

    for i, point in enumerate(points[:5], 1):
        rows += (
            f'<div class="point">'
            f'<span>{i:02d}</span>'
            f'<p>{esc(point)}</p>'
            f'</div>'
        )

    return f'''<section class="page closing">

  <div class="closing-stamp">
    TODAY'S SALES POINT
  </div>

  <div class="gold">
    GANGWON SALES DIVISION
  </div>

  <h1>
    오늘의 영업<br>
    <span>활용 포인트</span>
  </h1>

  <p class="closing-sub">
    뉴스를 설명하는 것이 아니라,
    고객의 걱정을 묻는 소재로 활용하세요.
  </p>

  <div class="points">
    {rows}
  </div>

  <div class="closing-message">
    <b>
      오늘 고객에게 던질 질문 하나를<br>
      뉴스에서 찾아보세요.
    </b>
  </div>

</section>'''


# ============================================================
# 데이터 구조 보정
# ============================================================

def get_categories(data):

    categories = data.get("categories")

    if isinstance(categories, dict):
        return categories

    # 과거 포맷 호환
    legacy_data = data.get("data")

    if isinstance(legacy_data, dict):
        return legacy_data

    # 혹시 categories가 없는 경우
    return {
        "policy": data.get("policy") or [],
        "medical": data.get("medical") or [],
        "samsung_fire": data.get("samsung_fire") or [],
    }


# ============================================================
# HTML 생성
# ============================================================

def generate_html(data):

    categories = get_categories(data)

    counts = {
        key: len(categories.get(key) or [])
        for key in CATEGORY_INFO
    }

    # 현재 날짜
    date_text = datetime.now().strftime("%Y.%m.%d")

    pages = []

    # --------------------------------------------------------
    # 1. 표지
    # --------------------------------------------------------
    pages.append(
        cover_page(date_text, counts)
    )

    # --------------------------------------------------------
    # 2. 뉴스 카드
    # --------------------------------------------------------
    for category_key in (
        "policy",
        "medical",
        "samsung_fire",
    ):

        articles = categories.get(category_key) or []

        # 삼성화재 뉴스가 0건이면
        # 여기서 아무 페이지도 만들지 않는다.
        if not articles:
            continue

        for i, article in enumerate(articles, 1):

            pages.append(
                article_page(
                    article,
                    category_key,
                    i
                )
            )

    # --------------------------------------------------------
    # 3. 마지막 영업 포인트
    # --------------------------------------------------------
    pages.append(
        closing_page(
            data.get("sales_points", [])
        )
    )

    return f'''<!doctype html>
<html lang="ko">

<head>

<meta charset="utf-8">

<meta name="viewport"
      content="width=device-width,initial-scale=1,viewport-fit=cover">

<meta name="theme-color"
      content="#071b3a">

<title>
강원영업단 RC Morning Brief
</title>

<style>

*{{
  box-sizing:border-box;
  margin:0;
  padding:0
}}

html,
body{{
  width:100%;
  height:100%;
  overflow:hidden
}}

body{{
  font-family:
    -apple-system,
    BlinkMacSystemFont,
    "Noto Sans KR",
    "Malgun Gothic",
    sans-serif;

  background:#071b3a;
  color:#172033;
}}

.brief{{
  width:100vw;
  height:100vh;

  display:flex;

  overflow-x:auto;
  overflow-y:hidden;

  scroll-snap-type:x mandatory;

  -webkit-overflow-scrolling:touch;

  scrollbar-width:none;
}}

.brief::-webkit-scrollbar{{
  display:none
}}

.page{{
  flex:0 0 100vw;

  width:100vw;
  height:100vh;
  min-height:100vh;

  scroll-snap-align:start;

  overflow-y:auto;

  padding:
    32px
    24px
    42px;

  position:relative;

  background:#f7f8fa;
}}

.cover,
.closing{{
  background:
    linear-gradient(
      145deg,
      #071b3a 0%,
      #0b2f68 58%,
      #13284c 100%
    );

  color:#fff;

  display:flex;
  flex-direction:column;
  justify-content:space-between;
}}

.cover-head,
.topline{{
  display:flex;
  justify-content:space-between;
  align-items:center;

  font-size:10px;
  letter-spacing:1.5px;

  color:#bfc8d7;
}}

.stamp,
.closing-stamp{{
  border:1px solid #d7b34b;

  color:#e0bd58;

  padding:6px 9px;

  font-size:9px;

  letter-spacing:1.3px;
}}

.cover-main{{
  margin:auto 0;
}}

.gold{{
  color:#e0bd58;

  font-size:13px;

  letter-spacing:2px;

  margin-bottom:14px;
}}

.cover h1{{
  font:
    600
    clamp(48px,15vw,78px)/.92
    Georgia,
    serif;

  letter-spacing:-3px;
}}

.cover h1 span,
.closing h1 span{{
  color:#e0bd58;
}}

.date{{
  margin-top:22px;

  font-size:16px;
}}

.toc{{
  border-top:
    1px solid
    rgba(255,255,255,.2);

  padding-top:18px;
}}

.toc-title{{
  color:#d7b34b;

  font-size:10px;

  letter-spacing:2px;

  margin-bottom:8px;
}}

.toc-row{{
  display:flex;

  justify-content:space-between;

  padding:9px 0;

  border-bottom:
    1px solid
    rgba(255,255,255,.09);

  font-size:13px;
}}

.cover-foot{{
  text-align:center;

  font-size:9px;

  color:#aeb8c8;
}}

.article-page{{
  display:flex;

  flex-direction:column;
}}

.article-page.policy{{
  border-top:6px solid #b59a45;
}}

.article-page.medical{{
  border-top:6px solid #2473a6;
}}

.article-page.samsung{{
  border-top:6px solid #0b4ea2;
}}

.badge{{
  align-self:flex-start;

  margin-top:28px;

  margin-bottom:15px;

  padding:6px 9px;

  background:#edf0f5;

  border-radius:4px;

  font-size:10px;

  font-weight:800;
}}

.article-page h1{{
  font-size:
    clamp(25px,7vw,34px);

  line-height:1.35;

  letter-spacing:-1.2px;
}}

.meta{{
  margin-top:9px;

  color:#8b92a0;

  font-size:10px;
}}

.rule{{
  height:1px;

  background:#d9dde5;

  margin:19px 0;
}}

.summary{{
  font-size:15px;

  line-height:1.8;

  color:#394153;
}}

.why{{
  margin-top:17px;

  padding:13px;

  background:#eef1f5;

  border-radius:8px;

  font-size:12px;

  line-height:1.65;
}}

.label{{
  font-size:9px;

  letter-spacing:1.5px;

  font-weight:800;

  color:#778092;

  margin-bottom:5px;
}}

.tip{{
  margin-top:12px;

  padding:15px;

  border:
    1px solid
    #d8c47c;

  background:#fffdf5;

  border-radius:8px;

  font-size:13px;

  line-height:1.7;
}}

.tip-title{{
  color:#9b7a17;

  font-weight:800;

  margin-bottom:5px;
}}

.source{{
  display:block;

  margin-top:auto;

  padding:13px;

  text-align:center;

  text-decoration:none;

  color:#fff;

  background:#0b2f68;

  border-radius:8px;

  font-size:12px;

  font-weight:700;
}}

.source.disabled{{
  background:#9aa2b1;

  cursor:not-allowed;
}}

.swipe{{
  text-align:center;

  color:#9aa2b1;

  font-size:9px;

  margin-top:12px;

  letter-spacing:1px;
}}

.closing-stamp{{
  align-self:flex-start;

  margin-bottom:28px;
}}

.closing h1{{
  font:
    600
    clamp(35px,10vw,52px)/1.1
    Georgia,
    serif;

  letter-spacing:-2px;
}}

.closing-sub{{
  margin-top:18px;

  color:#d7dfeb;

  font-size:13px;

  line-height:1.7;
}}

.points{{
  margin-top:24px;
}}

.point{{
  display:flex;

  gap:13px;

  padding:13px 0;

  border-bottom:
    1px solid
    rgba(255,255,255,.13);
}}

.point span{{
  font:
    18px
    Georgia,
    serif;

  color:#d7b34b;
}}

.point p{{
  font-size:13px;

  line-height:1.6;

  color:#f0f3f8;
}}

.closing-message{{
  margin-top:auto;

  padding-top:24px;

  border-top:
    1px solid
    rgba(255,255,255,.2);

  font-size:14px;

  line-height:1.7;

  color:#fff;
}}

@media(min-width:700px){{
  .page{{
    padding-left:
      calc((100vw - 620px)/2);

    padding-right:
      calc((100vw - 620px)/2);
  }}
}}

</style>

</head>

<body>

<div class="brief">
{''.join(pages)}
</div>

</body>

</html>'''


# ============================================================
# HTML 검증
# ============================================================

def validate_html(html_text, data):

    errors = []

    categories = get_categories(data)

    # 1. 기본 HTML
    if "<!doctype html>" not in html_text.lower():
        errors.append("DOCTYPE 누락")

    if '<div class="brief">' not in html_text:
        errors.append("brief 컨테이너 누락")

    # 2. 실제 기사 수 확인
    expected_articles = sum(
        len(categories.get(key) or [])
        for key in CATEGORY_INFO
    )

    actual_articles = html_text.count(
        'class="page article-page'
    )

    if actual_articles != expected_articles:
        errors.append(
            f"기사 카드 수 불일치 "
            f"(예상 {expected_articles}, 실제 {actual_articles})"
        )

    # 3. 삼성화재 0건이면 삼성 섹션이 없어야 함
    samsung_count = len(
        categories.get("samsung_fire") or []
    )

    if samsung_count == 0:

        if 'article-page samsung' in html_text:
            errors.append(
                "삼성화재 뉴스 0건인데 삼성화재 섹션이 생성됨"
            )

        if "삼성화재 소식" in html_text:
            errors.append(
                "삼성화재 뉴스 0건인데 삼성화재 소식 문구가 남아 있음"
            )

    # 4. NAVER URL 검증
    for key in CATEGORY_INFO:

        for article in categories.get(key) or []:

            url = get_naver_url(article)

            if not url:
                errors.append(
                    f"NAVER 원문 URL 없음: "
                    f"{article.get('title', '제목 없음')}"
                )

    return errors


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("강원영업단 RC Morning Brief")
    print("HTML 카드뉴스 생성 시작")
    print("=" * 60)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} 파일이 없습니다."
        )

    with INPUT_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    categories = get_categories(data)

    html_text = generate_html(data)

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT_FILE.write_text(
        html_text,
        encoding="utf-8"
    )

    errors = validate_html(
        html_text,
        data
    )

    print()
    print("카테고리별 기사 수")
    print("-" * 60)

    for key, (_, label, _) in CATEGORY_INFO.items():

        print(
            f"{label}: "
            f"{len(categories.get(key) or [])}개"
        )

    print()
    print(
        f"총 기사 카드: "
        f"{sum(len(categories.get(k) or []) for k in CATEGORY_INFO)}개"
    )

    print(
        f"HTML 파일: {OUTPUT_FILE}"
    )

    print()

    if errors:

        print("⚠ HTML 검증에서 문제가 발견되었습니다.")

        for error in errors:
            print(f"  - {error}")

        raise RuntimeError(
            "HTML 검증 실패"
        )

    print("✓ HTML 구조 검증 완료")
    print("✓ NAVER 원문 URL 검증 완료")
    print("✓ 삼성화재 뉴스 조건부 표시 검증 완료")
    print("✓ 모바일 카드뉴스 생성 완료")

    print("=" * 60)


if __name__ == "__main__":
    main()
```
