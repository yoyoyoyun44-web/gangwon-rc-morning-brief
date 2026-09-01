
import json
import html
from datetime import datetime
from pathlib import Path


# ============================================================
# 설정
# ============================================================

INPUT_FILE = Path("data/news.json")
OUTPUT_FILE = Path("docs/index.html")


# ============================================================
# 기본 함수
# ============================================================

def esc(value):
    """HTML 특수문자 처리"""
    if value is None:
        return ""
    return html.escape(str(value))


def get_article_value(article, key, default=""):
    return article.get(key, default)


# ============================================================
# 기사 카드 생성
# ============================================================

def make_article_card(article, category):

    title = esc(get_article_value(article, "title"))
    summary = esc(get_article_value(article, "summary"))
    sales_tip = esc(get_article_value(article, "sales_tip"))
    why_it_matters = esc(
        get_article_value(article, "why_it_matters")
    )
    source = esc(get_article_value(article, "source"))
    published_at = esc(
        get_article_value(article, "published_at")
    )
    source_url = get_article_value(
        article,
        "source_url",
        "#"
    )

    if category == "policy":
        badge = "제도 동향"
        category_class = "policy"

    elif category == "medical":
        badge = "의료비 이슈"
        category_class = "medical"

    else:
        badge = "삼성화재 소식"
        category_class = "samsung"


    return f"""
    <article class="news-card {category_class}">

        <div class="category-badge">
            {badge}
        </div>

        <h2>{title}</h2>

        <div class="meta">
            {published_at}
            &nbsp;·&nbsp;
            {source}
        </div>

        <div class="summary">
            {summary}
        </div>

        <div class="why">
            <div class="label">WHY IT MATTERS</div>
            <div>{why_it_matters}</div>
        </div>

        <div class="sales-tip">
            <div class="tip-title">
                💡 오늘의 영업 Tip
            </div>
            <div>{sales_tip}</div>
        </div>

        <a
            class="source-button"
            href="{esc(source_url)}"
            target="_blank"
            rel="noopener noreferrer"
        >
            원문 기사 보기 →
        </a>

    </article>
    """


# ============================================================
# 카테고리 섹션
# ============================================================

def make_category_section(
    category_key,
    category_data
):

    name = category_data.get(
        "name",
        ""
    )

    articles = category_data.get(
        "articles",
        []
    )

    cards = ""

    for article in articles:
        cards += make_article_card(
            article,
            category_key
        )

    return f"""
    <section class="category-section">

        <div class="section-title">

            <span class="section-number">
                {get_section_number(category_key)}
            </span>

            <div>
                <div class="section-kicker">
                    MORNING BRIEF
                </div>

                <h1>{esc(name)}</h1>
            </div>

        </div>

        <div class="cards">
            {cards}
        </div>

    </section>
    """


def get_section_number(category):

    numbers = {
        "policy": "01",
        "medical": "02",
        "samsung_fire": "03"
    }

    return numbers.get(
        category,
        ""
    )


# ============================================================
# 오늘의 영업 포인트
# ============================================================

def make_sales_points(points):

    items = ""

    for index, point in enumerate(
        points,
        start=1
    ):

        items += f"""
        <div class="point">

            <div class="point-number">
                {index:02d}
            </div>

            <div class="point-text">
                {esc(point)}
            </div>

        </div>
        """

    return f"""
    <section class="closing-section">

        <div class="closing-stamp">
            TODAY'S SALES POINT
        </div>

        <h1>
            오늘의 영업 활용 포인트
        </h1>

        <p class="closing-subtitle">
            오늘 뉴스로 고객과 자연스럽게 대화를 시작해 보세요.
        </p>

        <div class="points">
            {items}
        </div>

        <div class="closing-message">

            <strong>
                뉴스가 곧 영업 소재입니다.
            </strong>

            <br>

            오늘 고객에게 던질 질문 하나를
            뉴스에서 찾아보세요.

        </div>

    </section>
    """


# ============================================================
# HTML 생성
# ============================================================

def generate_html(data):

    generated_at = data.get(
        "generated_at",
        ""
    )

    model = data.get(
        "model",
        ""
    )

    content = data.get(
        "data",
        {}
    )

    policy = content.get(
        "policy",
        {}
    )

    medical = content.get(
        "medical",
        {}
    )

    samsung_fire = content.get(
        "samsung_fire",
        {}
    )

    sales_points = content.get(
        "sales_points",
        []
    )


    # 발행일

    today = datetime.now().strftime(
        "%Y.%m.%d"
    )


    # 카테고리 섹션

    sections = ""

    sections += make_category_section(
        "policy",
        policy
    )

    sections += make_category_section(
        "medical",
        medical
    )

    sections += make_category_section(
        "samsung_fire",
        samsung_fire
    )


    # 마무리

    closing = make_sales_points(
        sales_points
    )


    # ========================================================
    # 최종 HTML
    # ========================================================

    return f"""<!DOCTYPE html>

<html lang="ko">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width,
             initial-scale=1.0,
             maximum-scale=1.0,
             user-scalable=no"
>

<meta
    name="theme-color"
    content="#0b2a5b"
>

<title>
강원영업단 RC Morning Brief
</title>


<style>

* {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}}

html,
body {{
    width: 100%;
    height: 100%;
}}

body {{

    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Noto Sans KR",
        "Malgun Gothic",
        sans-serif;

    background:
        #071b3a;

    color:
        #172033;

    overflow-x:
        hidden;
}}


/* ==========================================================
   스와이프 컨테이너
   ========================================================== */

.brief-container {{

    width: 100%;
    height: 100vh;

    overflow-x: auto;
    overflow-y: hidden;

    display: flex;

    scroll-snap-type:
        x mandatory;

    -webkit-overflow-scrolling:
        touch;

    scrollbar-width:
        none;
}}

.brief-container::-webkit-scrollbar {{
    display: none;
}}


/* ==========================================================
   모든 페이지
   ========================================================== */

.page {{

    flex:
        0 0 100vw;

    width:
        100vw;

    height:
        100vh;

    overflow-y:
        auto;

    scroll-snap-align:
        start;

    background:
        #f6f7fa;

    position:
        relative;
}}


/* ==========================================================
   표지
   ========================================================== */

.cover {{

    background:
        linear-gradient(
            145deg,
            #071b3a 0%,
            #0b2f68 55%,
            #12264a 100%
        );

    color:
        white;

    display:
        flex;

    flex-direction:
        column;

    justify-content:
        space-between;

    padding:
        48px 28px 34px;

}}

.cover-top {{
    display:
        flex;

    justify-content:
        space-between;

    align-items:
        center;
}}

.brand {{
    font-size:
        13px;

    letter-spacing:
        2px;

    opacity:
        .85;
}}

.stamp {{

    border:
        1px solid
        rgba(212,175,55,.8);

    color:
        #e0bd55;

    padding:
        7px 10px;

    font-size:
        10px;

    letter-spacing:
        1px;

}}

.cover-main {{
    margin-top:
        auto;

    margin-bottom:
        auto;
}}

.cover-kicker {{

    color:
        #d7b34b;

    font-size:
        13px;

    letter-spacing:
        2px;

    margin-bottom:
        14px;

}}

.cover h1 {{

    font-size:
        clamp(32px, 9vw, 48px);

    line-height:
        1.12;

    letter-spacing:
        -1.5px;

}}

.cover h1 span {{
    color:
        #e2bf58;
}}

.cover-date {{

    margin-top:
        20px;

    font-size:
        15px;

    opacity:
        .9;

}}

.contents {{

    border-top:
        1px solid
        rgba(255,255,255,.2);

    padding-top:
        22px;

}}

.contents-title {{

    color:
        #d7b34b;

    font-size:
        11px;

    letter-spacing:
        2px;

    margin-bottom:
        13px;

}}

.contents-row {{

    display:
        flex;

    justify-content:
        space-between;

    padding:
        7px 0;

    border-bottom:
        1px solid
        rgba(255,255,255,.08);

    font-size:
        13px;

}}

.cover-footer {{

    font-size:
        10px;

    opacity:
        .55;

    text-align:
        center;

    margin-top:
        18px;

}}


/* ==========================================================
   카테고리
   ========================================================== */

.category-section {{

    padding:
        38px 18px 60px;

}}

.section-title {{

    display:
        flex;

    align-items:
        center;

    gap:
        14px;

    margin-bottom:
        22px;

}}

.section-number {{

    font-family:
        Georgia,
        serif;

    font-size:
        32px;

    color:
        #c4a34d;

}}

.section-kicker {{

    font-size:
        9px;

    letter-spacing:
        2px;

    color:
        #7b8495;

}}

.section-title h1 {{

    font-size:
        25px;

    letter-spacing:
        -1px;

}}


/* ==========================================================
   기사 카드
   ========================================================== */

.cards {{

    display:
        flex;

    flex-direction:
        column;

    gap:
        16px;

}}

.news-card {{

    background:
        white;

    border-radius:
        12px;

    padding:
        21px;

    box-shadow:
        0 4px 18px
        rgba(0,0,0,.07);

    border-left:
        4px solid
        #b59a45;

}}

.news-card.medical {{
    border-left-color:
        #2473a6;
}}

.news-card.samsung {{
    border-left-color:
        #0b4ea2;
}}

.category-badge {{

    display:
        inline-block;

    font-size:
        10px;

    font-weight:
        700;

    padding:
        5px 8px;

    border-radius:
        4px;

    background:
        #edf0f5;

    margin-bottom:
        11px;

}}

.news-card h2 {{

    font-size:
        18px;

    line-height:
        1.42;

    letter-spacing:
        -.5px;

    margin-bottom:
        8px;

}}

.meta {{

    font-size:
        10px;

    color:
        #8b92a0;

    margin-bottom:
        15px;

}}

.summary {{

    font-size:
        14px;

    line-height:
        1.7;

    color:
        #394153;

}}


/* ==========================================================
   WHY
   ========================================================== */

.why {{

    margin-top:
        15px;

    padding:
        12px;

    background:
        #f5f6f8;

    border-radius:
        7px;

    font-size:
        12px;

    line-height:
        1.6;

}}

.label {{

    font-size:
        9px;

    letter-spacing:
        1.5px;

    font-weight:
        700;

    color:
        #7c8493;

    margin-bottom:
        4px;

}}


/* ==========================================================
   영업 Tip
   ========================================================== */

.sales-tip {{

    margin-top:
        12px;

    padding:
        14px;

    border:
        1px solid
        #d8c47c;

    background:
        #fffdf5;

    border-radius:
        7px;

    font-size:
        13px;

    line-height:
        1.65;

}}

.tip-title {{

    color:
        #9b7a17;

    font-weight:
        800;

    margin-bottom:
        5px;

}}


/* ==========================================================
   원문 버튼
   ========================================================== */

.source-button {{

    display:
        block;

    text-align:
        center;

    margin-top:
        14px;

    padding:
        11px;

    border-radius:
        6px;

    background:
        #0b2f68;

    color:
        white;

    text-decoration:
        none;

    font-size:
        12px;

    font-weight:
        700;

}}


/* ==========================================================
   마무리
   ========================================================== */

.closing-section {{

    min-height:
        100vh;

    padding:
        55px 25px;

    background:
        linear-gradient(
            145deg,
            #071b3a,
            #0d356d
        );

    color:
        white;

}}

.closing-stamp {{

    display:
        inline-block;

    color:
        #d7b34b;

    border:
        1px solid
        #d7b34b;

    padding:
        7px 10px;

    font-size:
        10px;

    letter-spacing:
        1.5px;

    margin-bottom:
        22px;

}}

.closing-section h1 {{

    font-size:
        30px;

    line-height:
        1.3;

    margin-bottom:
        10px;

}}

.closing-subtitle {{

    color:
        rgba(255,255,255,.7);

    font-size:
        13px;

    line-height:
        1.6;

    margin-bottom:
        28px;

}}

.points {{

    display:
        flex;

    flex-direction:
        column;

    gap:
        12px;

}}

.point {{

    display:
        flex;

    gap:
        14px;

    align-items:
        flex-start;

    padding:
        15px;

    background:
        rgba(255,255,255,.07);

    border:
        1px solid
        rgba(255,255,255,.1);

    border-radius:
        8px;

}}

.point-number {{

    color:
        #d7b34b;

    font-family:
        Georgia,
        serif;

    font-size:
        20px;

}}

.point-text {{

    font-size:
        14px;

    line-height:
        1.6;

}}

.closing-message {{

    margin-top:
        28px;

    padding:
        20px;

    border-top:
        1px solid
        rgba(255,255,255,.2);

    font-size:
        13px;

    line-height:
        1.8;

    color:
        rgba(255,255,255,.75);

}}

.closing-message strong {{
    color:
        #e0bd55;
}}


/* ==========================================================
   PC
   ========================================================== */

@media (min-width: 768px) {{

    .page {{
        width:
            430px;

        flex-basis:
            430px;

    }}

    .brief-container {{
        justify-content:
            center;

    }}

}}

</style>

</head>


<body>


<div class="brief-container">


    <!-- =====================================================
         COVER
         ===================================================== -->

    <section class="page cover">

        <div class="cover-top">

            <div class="brand">
                SAMSUNG FIRE
            </div>

            <div class="stamp">
                INTERNAL BRIEF
            </div>

        </div>


        <div class="cover-main">

            <div class="cover-kicker">
                강원영업단 RC를 위한
            </div>

            <h1>
                Morning<br>
                <span>Brief</span>
            </h1>

            <div class="cover-date">
                {today}
            </div>

        </div>


        <div class="contents">

            <div class="contents-title">
                TODAY'S CONTENTS
            </div>

            <div class="contents-row">
                <span>01</span>
                <span>제도 동향</span>
            </div>

            <div class="contents-row">
                <span>02</span>
                <span>의료비 이슈</span>
            </div>

            <div class="contents-row">
                <span>03</span>
                <span>삼성화재 소식</span>
            </div>

            <div class="contents-row">
                <span>04</span>
                <span>오늘의 영업 포인트</span>
            </div>

        </div>


        <div class="cover-footer">
            SWIPE →  오늘의 뉴스를 확인하세요
        </div>

    </section>


    <!-- =====================================================
         NEWS
         ===================================================== -->

    <div class="page">
        {sections}
    </div>


    <!-- =====================================================
         CLOSING
         ===================================================== -->

    <div class="page">
        {closing}
    </div>


</div>


</body>

</html>
"""


# ============================================================
# 실행
# ============================================================

def main():

    print("=" * 60)
    print("HTML 카드뉴스 생성 시작")
    print("=" * 60)


    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"{INPUT_FILE} 파일을 찾을 수 없습니다."
        )


    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)


    print(
        f"뉴스 데이터 읽기 완료: {INPUT_FILE}"
    )


    html_content = generate_html(
        data
    )


    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )


    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(html_content)


    print(
        f"HTML 생성 완료: {OUTPUT_FILE}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()


