```python
import json
import html
from datetime import datetime
from pathlib import Path

INPUT_FILE = Path("data/news.json")
OUTPUT_FILE = Path("docs/index.html")


# ============================================================
# 카테고리별 색상 설정
# ============================================================

CATEGORY_INFO = {
    "policy": {
        "num": "01",
        "title": "제도 동향",
        "css": "policy",
        "main": "#B58900",
        "bg": "#FFF8E6",
        "text": "#5A4400",
        "subtext": "#7A6A44",
        "accent": "#B58900",
        "border": "#E8D7A3",
    },
    "medical": {
        "num": "02",
        "title": "의료비 이슈",
        "css": "medical",
        "main": "#1E6BB8",
        "bg": "#E8F2FF",
        "text": "#0B3A78",
        "subtext": "#4D6B8A",
        "accent": "#1E6BB8",
        "border": "#B9D5F2",
    },
    "samsung_fire": {
        "num": "03",
        "title": "삼성화재 소식",
        "css": "samsung",
        "main": "#1E8E3E",
        "bg": "#E8F7EC",
        "text": "#0B4D22",
        "subtext": "#4E7A5F",
        "accent": "#1E8E3E",
        "border": "#BFE3C9",
    },
}


COMMON_COLORS = {
    "cover_bg": "#071B3A",
    "cover_text": "#FFFFFF",
    "cover_subtext": "#BFC8D7",
    "cover_accent": "#E0BD58",
}


# ============================================================
# 안전한 HTML 처리
# ============================================================

def esc(value):
    return html.escape(str(value or ""), quote=True)


# ============================================================
# 날짜 처리
# ============================================================

def format_date(value):
    value = str(value or "").strip()

    if not value:
        return "발행일 미상"

    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
        return dt.strftime("%Y.%m.%d %H:%M")
    except (ValueError, TypeError):
        return value[:16].replace("T", " ")


# ============================================================
# 기사 원문 URL
#
# NAVER 원문 링크가 있으면 최우선 사용
# 없으면 source_url → url 순서로 사용
# ============================================================

def get_source_url(article):
    return (
        article.get("naver_url")
        or article.get("source_url")
        or article.get("url")
        or ""
    )


# ============================================================
# 기사 출처
# ============================================================

def get_source(article):
    return (
        article.get("source")
        or article.get("publisher")
        or article.get("press")
        or ""
    )


# ============================================================
# 기사 본문 필드 보정
# ============================================================

def get_text(article, *keys):
    for key in keys:
        value = article.get(key)

        if value is not None and str(value).strip():
            return str(value).strip()

    return ""


# ============================================================
# 기사 카드
# ============================================================

def article_page(article, category_key, number, total):
    info = CATEGORY_INFO[category_key]

    title = esc(
        get_text(article, "title", "headline")
    )

    summary = esc(
        get_text(article, "summary", "description", "content")
    )

    why = esc(
        get_text(
            article,
            "why_it_matters",
            "why",
            "importance"
        )
    )

    tip = esc(
        get_text(
            article,
            "sales_tip",
            "tip",
            "sales_point"
        )
    )

    source = esc(get_source(article))

    published = format_date(
        article.get("published_at")
        or article.get("pub_date")
        or article.get("published")
    )

    source_url = esc(get_source_url(article))

    # 값이 없는 경우에도 카드 구조가 깨지지 않도록 기본 문구
    if not title:
        title = "제목 정보 없음"

    if not summary:
        summary = "기사 요약 정보가 없습니다."

    if not why:
        why = "이 뉴스가 보험·의료비·고객 보장 점검에 어떤 영향을 줄 수 있는지 확인해 보세요."

    if not tip:
        tip = "이 뉴스와 연결하여 고객의 기존 보장 내용을 점검해 보세요."

    if not source:
        source = "원문 출처"

    # 원문 URL이 있을 때만 링크 활성화
    if source_url:
        source_button = (
            f'<a class="source {info["css"]}" '
            f'href="{source_url}" '
            f'target="_blank" '
            f'rel="noopener noreferrer">'
            f'NAVER 원문 기사 보기 →'
            f'</a>'
        )
    else:
        source_button = (
            '<div class="source disabled">'
            '원문 링크 없음'
            '</div>'
        )

    return f'''
<section
    class="page article-page {info["css"]}"
    style="
        --cat-main:{info["main"]};
        --cat-bg:{info["bg"]};
        --cat-text:{info["text"]};
        --cat-subtext:{info["subtext"]};
        --cat-accent:{info["accent"]};
        --cat-border:{info["border"]};
    "
>

  <div class="topline">
    <span>{info["num"]} / {number:02d}</span>
    <span class="stamp">MORNING BRIEF</span>
  </div>

  <div class="badge">
    <span class="badge-number">{info["num"]}</span>
    {info["title"]}
  </div>

  <h1>{title}</h1>

  <div class="meta">
    {published} · {source}
  </div>

  <div class="rule"></div>

  <div class="summary-box">
    <div class="label">요약</div>
    <p class="summary">{summary}</p>
  </div>

  <div class="why">
    <div class="label">
      💡 WHY IT MATTERS
    </div>
    <div>{why}</div>
  </div>

  <div class="tip">
    <div class="tip-title">
      💬 오늘의 영업 Tip
    </div>
    <div>{tip}</div>
  </div>

  {source_button}

  <div class="swipe">
    ← 좌우로 스와이프 →
  </div>

</section>
'''


# ============================================================
# 표지
# ============================================================

def cover_page(date_text, counts):

    toc_rows = []

    for key, info in CATEGORY_INFO.items():

        count = counts.get(key, 0)

        if count <= 0:
            continue

        toc_rows.append(
            f'''
            <div class="toc-row">
                <span>
                    <i
                        class="toc-dot"
                        style="background:{info["main"]}"
                    ></i>
                    {info["num"]}　{info["title"]}
                </span>
                <b>{count}건</b>
            </div>
            '''
        )

    toc = "".join(toc_rows)

    if not toc:
        toc = '''
        <div class="toc-row">
            <span>오늘의 뉴스가 없습니다.</span>
        </div>
        '''

    return f'''
<section class="page cover">

  <div class="cover-head">
    <span>GANGWON SALES DIVISION</span>
    <span class="stamp">DAILY DOSSIER</span>
  </div>

  <div class="cover-main">

    <div class="gold">
      강원영업단 RC를 위한
    </div>

    <h1>
      Morning<br>
      <span>Brief</span>
    </h1>

    <div class="date">
      {esc(date_text)}
    </div>

  </div>

  <div class="toc">

    <div class="toc-title">
      CONTENTS
    </div>

    {toc}

  </div>

  <div class="cover-foot">
    보험 · 의료 · 영업 인사이트　|　Swipe →
  </div>

</section>
'''


# ============================================================
# 마지막 영업 활용 페이지
# ============================================================

def closing_page(points):

    if not points:
        points = [
            "오늘 뉴스 중 고객의 건강·의료비 걱정과 연결할 수 있는 주제를 하나 골라 대화를 시작해 보세요."
        ]

    rows = ""

    for i, point in enumerate(points[:5], 1):

        rows += f'''
        <div class="point">
            <span>{i:02d}</span>
            <p>{esc(point)}</p>
        </div>
        '''

    return f'''
<section class="page closing">

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

</section>
'''


# ============================================================
# 데이터 구조 보정
# ============================================================

def get_categories(data):

    categories = data.get("categories", {})

    if isinstance(categories, dict):
        return categories

    # 과거 데이터 구조 대응
    old_data = data.get("data")

    if isinstance(old_data, dict):
        return old_data

    return {}


# ============================================================
# HTML 생성
# ============================================================

def generate_html(data):

    categories = get_categories(data)

    date_text = (
        data.get("date")
        or data.get("brief_date")
        or datetime.now().strftime("%Y.%m.%d")
    )

    counts = {
        key: len(categories.get(key) or [])
        for key in CATEGORY_INFO
    }

    pages = []

    # --------------------------------------------------------
    # 표지
    # --------------------------------------------------------

    pages.append(
        cover_page(
            date_text,
            counts
        )
    )

    # --------------------------------------------------------
    # 기사 페이지
    # --------------------------------------------------------

    for category_key in (
        "policy",
        "medical",
        "samsung_fire"
    ):

        articles = categories.get(category_key) or []

        # 삼성화재 뉴스가 없으면 해당 카테고리 자체를 생략
        if not articles:
            continue

        total = len(articles)

        for i, article in enumerate(
            articles,
            1
        ):

            pages.append(
                article_page(
                    article,
                    category_key,
                    i,
                    total
                )
            )

    # --------------------------------------------------------
    # 마지막 페이지
    # --------------------------------------------------------

    pages.append(
        closing_page(
            data.get("sales_points", [])
        )
    )

    body = "".join(pages)

    # ========================================================
    # 최종 HTML
    # ========================================================

    return f'''<!doctype html>
<html lang="ko">

<head>

<meta charset="utf-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1,
             viewport-fit=cover"
>

<meta
    name="theme-color"
    content="#071b3a"
>

<title>
강원영업단 RC Morning Brief
</title>


<style>

/* ==========================================================
   RESET
   ========================================================== */

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}


html,
body {{
    width: 100%;
    height: 100%;
    overflow: hidden;
}}


body {{
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Noto Sans KR",
        "Malgun Gothic",
        sans-serif;

    background: #071b3a;
    color: #172033;
}}


/* ==========================================================
   전체 카드뉴스
   ========================================================== */

.brief {{

    width: 100vw;
    height: 100vh;

    display: flex;

    overflow-x: auto;
    overflow-y: hidden;

    scroll-snap-type: x mandatory;

    -webkit-overflow-scrolling: touch;

    scrollbar-width: none;
}}


.brief::-webkit-scrollbar {{
    display: none;
}}


/* ==========================================================
   기본 페이지
   ========================================================== */

.page {{

    flex: 0 0 100vw;

    width: 100vw;
    height: 100vh;
    min-height: 100vh;

    scroll-snap-align: start;

    overflow-y: auto;

    padding:
        28px
        22px
        42px;

    position: relative;

    background: #f7f8fa;
}}


/* ==========================================================
   표지 / 마지막 페이지
   ========================================================== */

.cover,
.closing {{

    background:
        linear-gradient(
            145deg,
            #071b3a 0%,
            #0b2f68 58%,
            #13284c 100%
        );

    color: #fff;

    display: flex;
    flex-direction: column;

    justify-content: space-between;
}}


/* ==========================================================
   상단
   ========================================================== */

.cover-head,
.topline {{

    display: flex;

    justify-content: space-between;
    align-items: center;

    font-size: 10px;

    letter-spacing: 1.5px;

    color: #bfc8d7;
}}


.stamp,
.closing-stamp {{

    border:
        1px solid #d7b34b;

    color: #e0bd58;

    padding:
        6px 9px;

    font-size: 9px;

    letter-spacing: 1.3px;
}}


/* ==========================================================
   표지
   ========================================================== */

.cover-main {{
    margin: auto 0;
}}


.gold {{

    color: #e0bd58;

    font-size: 13px;

    letter-spacing: 2px;

    margin-bottom: 14px;
}}


.cover h1 {{

    font:
        600
        clamp(48px, 15vw, 78px)
        / .92
        Georgia,
        serif;

    letter-spacing: -3px;
}}


.cover h1 span,
.closing h1 span {{
    color: #e0bd58;
}}


.date {{

    margin-top: 22px;

    font-size: 16px;
}}


/* ==========================================================
   CONTENTS
   ========================================================== */

.toc {{

    border-top:
        1px solid
        rgba(255,255,255,.2);

    padding-top: 18px;
}}


.toc-title {{

    color: #d7b34b;

    font-size: 10px;

    letter-spacing: 2px;

    margin-bottom: 8px;
}}


.toc-row {{

    display: flex;

    justify-content: space-between;

    align-items: center;

    padding: 9px 0;

    border-bottom:
        1px solid
        rgba(255,255,255,.09);

    font-size: 13px;
}}


.toc-row span {{

    display: flex;

    align-items: center;
}}


.toc-dot {{

    display: inline-block;

    width: 10px;
    height: 10px;

    border-radius: 3px;

    margin-right: 7px;
}}


.cover-foot {{

    text-align: center;

    font-size: 9px;

    color: #aeb8c8;
}}


/* ==========================================================
   기사 페이지 공통
   ========================================================== */

.article-page {{

    display: flex;

    flex-direction: column;

    color: var(--cat-text);

    background:
        linear-gradient(
            180deg,
            var(--cat-bg) 0%,
            #ffffff 70%
        );

    border-top:
        7px solid
        var(--cat-main);
}}


/* ==========================================================
   카테고리별 배경
   ========================================================== */

.article-page.policy {{

    --cat-main: #B58900;
    --cat-bg: #FFF8E6;
    --cat-text: #5A4400;
    --cat-subtext: #7A6A44;
    --cat-accent: #B58900;
    --cat-border: #E8D7A3;
}}


.article-page.medical {{

    --cat-main: #1E6BB8;
    --cat-bg: #E8F2FF;
    --cat-text: #0B3A78;
    --cat-subtext: #4D6B8A;
    --cat-accent: #1E6BB8;
    --cat-border: #B9D5F2;
}}


.article-page.samsung {{

    --cat-main: #1E8E3E;
    --cat-bg: #E8F7EC;
    --cat-text: #0B4D22;
    --cat-subtext: #4E7A5F;
    --cat-accent: #1E8E3E;
    --cat-border: #BFE3C9;
}}


/* ==========================================================
   카테고리 배지
   ========================================================== */

.badge {{

    align-self: flex-start;

    margin-top: 24px;
    margin-bottom: 15px;

    padding:
        7px 11px;

    border-radius: 6px;

    background:
        var(--cat-main);

    color: #fff;

    font-size: 11px;

    font-weight: 800;

    letter-spacing: -.2px;

    box-shadow:
        0 3px 10px
        rgba(0,0,0,.08);
}}


.badge-number {{

    display: inline-flex;

    justify-content: center;
    align-items: center;

    width: 21px;
    height: 21px;

    margin-right: 5px;

    border-radius: 5px;

    background:
        rgba(255,255,255,.22);

    font-size: 10px;
}}


/* ==========================================================
   제목
   ========================================================== */

.article-page h1 {{

    color:
        var(--cat-text);

    font-size:
        clamp(
            25px,
            7vw,
            34px
        );

    line-height: 1.35;

    letter-spacing: -1.2px;
}}


/* ==========================================================
   날짜 / 출처
   ========================================================== */

.meta {{

    margin-top: 9px;

    color:
        var(--cat-subtext);

    font-size: 10px;
}}


/* ==========================================================
   구분선
   ========================================================== */

.rule {{

    height: 1px;

    background:
        var(--cat-border);

    margin:
        18px 0;
}}


/* ==========================================================
   요약
   ========================================================== */

.summary-box {{

    padding: 14px;

    background:
        rgba(255,255,255,.68);

    border:
        1px solid
        var(--cat-border);

    border-radius: 9px;
}}


.summary {{

    font-size: 14px;

    line-height: 1.75;

    color:
        var(--cat-text);
}}


/* ==========================================================
   공통 라벨
   ========================================================== */

.label {{

    font-size: 9px;

    letter-spacing: 1.4px;

    font-weight: 800;

    color:
        var(--cat-main);

    margin-bottom: 6px;
}}


/* ==========================================================
   WHY IT MATTERS
   ========================================================== */

.why {{

    margin-top: 14px;

    padding: 14px;

    background:
        rgba(255,255,255,.58);

    border-left:
        4px solid
        var(--cat-main);

    border-radius: 8px;

    font-size: 12px;

    line-height: 1.65;

    color:
        var(--cat-text);
}}


/* ==========================================================
   영업 Tip
   ========================================================== */

.tip {{

    margin-top: 12px;

    padding: 15px;

    background:
        rgba(255,255,255,.78);

    border:
        1px solid
        var(--cat-border);

    border-radius: 9px;

    font-size: 13px;

    line-height: 1.7;

    color:
        var(--cat-text);
}}


.tip-title {{

    color:
        var(--cat-main);

    font-weight: 800;

    margin-bottom: 6px;
}}


/* ==========================================================
   원문 버튼
   ========================================================== */

.source {{

    display: block;

    margin-top: auto;

    padding: 14px;

    text-align: center;

    text-decoration: none;

    color: #fff;

    background:
        var(--cat-main);

    border-radius: 8px;

    font-size: 12px;

    font-weight: 800;

    box-shadow:
        0 4px 12px
        rgba(0,0,0,.10);
}}


.source:hover {{
    opacity: .9;
}}


.source.disabled {{

    background: #aeb4bd;

    cursor: default;
}}


/* ==========================================================
   스와이프 안내
   ========================================================== */

.swipe {{

    text-align: center;

    color:
        var(--cat-subtext);

    font-size: 9px;

    margin-top: 12px;

    letter-spacing: 1px;
}}


/* ==========================================================
   마지막 페이지
   ========================================================== */

.closing-stamp {{

    align-self: flex-start;

    margin-bottom: 28px;
}}


.closing h1 {{

    font:
        600
        clamp(35px, 10vw, 52px)
        / 1.1
        Georgia,
        serif;

    letter-spacing: -2px;
}}


.closing-sub {{

    margin-top: 18px;

    color: #d7dfeb;

    font-size: 13px;

    line-height: 1.7;
}}


.points {{

    margin-top: 24px;
}}


.point {{

    display: flex;

    gap: 13px;

    padding: 13px 0;

    border-bottom:
        1px solid
        rgba(255,255,255,.13);
}}


.point span {{

    font:
        18px
        Georgia,
        serif;

    color: #d7b34b;
}}


.point p {{

    font-size: 13px;

    line-height: 1.6;

    color: #f0f3f8;
}}


.closing-message {{

    margin-top: auto;

    padding-top: 24px;

    border-top:
        1px solid
        rgba(255,255,255,.2);

    font-size: 14px;

    line-height: 1.7;

    color: #fff;
}}


/* ==========================================================
   PC 화면
   ========================================================== */

@media (min-width: 700px) {{

    .page {{

        padding-left:
            calc(
                (100vw - 620px) / 2
            );

        padding-right:
            calc(
                (100vw - 620px) / 2
            );
    }}

}}


/* ==========================================================
   작은 모바일 화면
   ========================================================== */

@media (max-width: 380px) {{

    .page {{

        padding:
            24px
            18px
            36px;
    }}


    .article-page h1 {{

        font-size: 24px;
    }}


    .summary {{

        font-size: 13px;
    }}


    .tip {{

        font-size: 12px;
    }}

}}


</style>

</head>


<body>

<div class="brief">

{body}

</div>

</body>

</html>
'''


# ============================================================
# HTML 검증
# ============================================================

def validate_html(html_text, data):

    if not html_text.strip():
        raise ValueError(
            "생성된 HTML이 비어 있습니다."
        )

    required_strings = [
        "<!doctype html>",
        '<html lang="ko">',
        '<div class="brief">',
        "</html>",
    ]

    for item in required_strings:

        if item not in html_text:

            raise ValueError(
                f"HTML 검증 실패: {item}"
            )

    # 기사 수 확인
    categories = get_categories(data)

    expected_articles = sum(
        len(categories.get(key) or [])
        for key in CATEGORY_INFO
    )

    actual_articles = html_text.count(
        'class="page article-page'
    )

    if actual_articles != expected_articles:

        raise ValueError(
            "기사 페이지 수가 데이터와 일치하지 않습니다. "
            f"예상={expected_articles}, "
            f"생성={actual_articles}"
        )


# ============================================================
# 실행
# ============================================================

def main():

    print("=" * 60)
    print("HTML 카드뉴스 생성 시작")
    print("=" * 60)

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"{INPUT_FILE} 파일이 없습니다."
        )

    # --------------------------------------------------------
    # news.json 읽기
    # --------------------------------------------------------

    with INPUT_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    # --------------------------------------------------------
    # HTML 생성
    # --------------------------------------------------------

    html_text = generate_html(data)

    # --------------------------------------------------------
    # HTML 검증
    # --------------------------------------------------------

    validate_html(
        html_text,
        data
    )

    # --------------------------------------------------------
    # docs 디렉터리 생성
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # HTML 저장
    # --------------------------------------------------------

    OUTPUT_FILE.write_text(
        html_text,
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # 결과 출력
    # --------------------------------------------------------

    categories = get_categories(data)

    policy_count = len(
        categories.get("policy") or []
    )

    medical_count = len(
        categories.get("medical") or []
    )

    samsung_count = len(
        categories.get("samsung_fire") or []
    )

    print()
    print("=" * 60)
    print("HTML 카드뉴스 생성 완료")
    print("=" * 60)

    print(
        f"입력 파일       : {INPUT_FILE}"
    )

    print(
        f"출력 파일       : {OUTPUT_FILE}"
    )

    print(
        f"제도 동향       : {policy_count}개"
    )

    print(
        f"의료비 이슈     : {medical_count}개"
    )

    print(
        f"삼성화재 소식   : {samsung_count}개"
    )

    if samsung_count == 0:

        print(
            "삼성화재 뉴스 0개 → "
            "해당 카테고리 자동 생략"
        )

    else:

        print(
            "삼성화재 뉴스 → "
            "초록색 카테고리로 표시"
        )

    print()
    print("카테고리 색상")
    print(
        "01 제도 동향     → 골드 / 아이보리"
    )
    print(
        "02 의료비 이슈   → 블루 / 연한 블루"
    )
    print(
        "03 삼성화재 소식 → 그린 / 연한 그린"
    )

    print()
    print("원문 링크 우선순위")
    print(
        "naver_url → source_url → url"
    )

    print()
    print("HTML 검증       : PASS")
    print("=" * 60)


if __name__ == "__main__":
    main()
```
