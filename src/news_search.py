import os
import json
import requests
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup


# ============================================================
# NAVER API HUB 인증정보
# ============================================================

NAVER_CLIENT_ID = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]


# NAVER API HUB 기본 URL
NAVER_API_BASE = "https://naverapihub.apigw.ntruss.com"

# 뉴스 검색 API
NAVER_NEWS_URL = f"{NAVER_API_BASE}/search/v1/news"

OUTPUT_FILE = "data/raw_news.json"


# ============================================================
# 검색어
# ============================================================

SEARCH_QUERIES = [
    "보험 제도",
    "금융감독원 보험",
    "금융위원회 보험",
    "손해보험협회",
    "실손보험",
    "건강보험",
    "간병보험",
    "간병인",
    "의료비",
    "비급여",
    "신의료기술",
    "혁신의료기술",
    "암 치료",
    "뇌혈관질환",
    "심혈관질환",
    "중증질환",
    "건강보험공단",
    "건강보험심사평가원",
    "보건복지부",
    "삼성화재 건강보험",
    "삼성화재 장기보험",
    "삼성화재 실손보험",
    "삼성화재 간병"
]


# ============================================================
# HTML 태그 제거
# ============================================================

def clean_html(text):

    return BeautifulSoup(
        text or "",
        "html.parser"
    ).get_text(
        " ",
        strip=True
    )


# ============================================================
# 날짜 변환
# ============================================================

def parse_date(date_string):

    try:
        return parsedate_to_datetime(
            date_string
        )

    except Exception:

        return None


# ============================================================
# NAVER API HUB 뉴스 검색
# ============================================================

def search_naver(query):

    headers = {

        "X-NCP-APIGW-API-KEY-ID":
            NAVER_CLIENT_ID,

        "X-NCP-APIGW-API-KEY":
            NAVER_CLIENT_SECRET

    }

    params = {

        "query":
            query,

        "display":
            100,

        "start":
            1,

        "sort":
            "date"

    }

    response = requests.get(

        NAVER_NEWS_URL,

        headers=headers,

        params=params,

        timeout=30

    )


    # 오류 발생 시 응답 내용까지 표시
    if response.status_code != 200:

        print()
        print("NAVER API 오류")
        print(
            f"HTTP Status: {response.status_code}"
        )
        print(
            f"Response: {response.text}"
        )

        response.raise_for_status()


    return response.json()


# ============================================================
# 메인
# ============================================================

def main():

    now = datetime.now().astimezone()

    # 테스트 단계에서는 최근 72시간
    cutoff = now - timedelta(
        hours=72
    )

    collected = []

    seen_urls = set()


    print("=" * 60)

    print(
        "강원영업단 RC Morning Brief"
    )

    print(
        "NAVER API HUB 뉴스 수집 시작"
    )

    print("=" * 60)


    # --------------------------------------------------------
    # 검색
    # --------------------------------------------------------

    for query in SEARCH_QUERIES:

        print()
        print(
            f"[검색] {query}"
        )

        try:

            data = search_naver(
                query
            )

        except Exception as e:

            print(
                f"[오류] {e}"
            )

            continue


        items = data.get(
            "items",
            []
        )


        print(
            f"  → {len(items)}개 결과"
        )


        for item in items:

            title = clean_html(
                item.get(
                    "title",
                    ""
                )
            )

            description = clean_html(
                item.get(
                    "description",
                    ""
                )
            )


            original_url = (

                item.get(
                    "originallink"
                )

                or

                item.get(
                    "link"
                )

                or

                ""

            )


            published_raw = item.get(
                "pubDate",
                ""
            )


            published = parse_date(
                published_raw
            )


            # URL 없는 기사 제외

            if not original_url:

                continue


            # 중복 제거

            if original_url in seen_urls:

                continue


            seen_urls.add(
                original_url
            )


            # 최근 72시간 기사만
            if (

                published

                and

                published < cutoff

            ):

                continue


            collected.append({

                "title":
                    title,

                "description":
                    description,

                "source_url":
                    original_url,

                "naver_url":
                    item.get(
                        "link"
                    ),

                "published_at":
                    (

                        published.isoformat()

                        if published

                        else published_raw

                    ),

                "query":
                    query

            })


    # --------------------------------------------------------
    # 최신순 정렬
    # --------------------------------------------------------

    collected.sort(

        key=lambda x:
            x.get(
                "published_at",
                ""
            ),

        reverse=True

    )


    # --------------------------------------------------------
    # JSON 생성
    # --------------------------------------------------------

    output = {

        "generated_at":
            now.isoformat(),

        "article_count":
            len(collected),

        "articles":
            collected

    }


    os.makedirs(
        "data",
        exist_ok=True
    )


    with open(

        OUTPUT_FILE,

        "w",

        encoding="utf-8"

    ) as f:

        json.dump(

            output,

            f,

            ensure_ascii=False,

            indent=2

        )


    print()
    print("=" * 60)

    print(
        f"뉴스 {len(collected)}개 수집 완료"
    )

    print(
        f"파일 생성: {OUTPUT_FILE}"
    )

    print("=" * 60)


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":

    main()
