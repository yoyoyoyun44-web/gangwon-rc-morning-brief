
import json
import os
import time
from pathlib import Path

from google import genai


# ============================================================
# 설정
# ============================================================

INPUT_FILE = Path("data/raw_news.json")
OUTPUT_FILE = Path("data/news.json")

API_KEY = os.getenv("GEMINI_API_KEY")

# 현재 사용 중인 Gemini 모델
MODEL_NAME = "gemini-3.6-flash"

# 한 번에 Gemini에 보내는 뉴스 개수
BATCH_SIZE = 20

# 503 등 일시적 오류 발생 시 최대 재시도 횟수
MAX_RETRIES = 4

# 재시도 간격
RETRY_DELAYS = [30, 60, 120, 180]

# 최종적으로 AI가 검토할 뉴스 수
MAX_ANALYSIS_NEWS = 80


# ============================================================
# Gemini 클라이언트
# ============================================================

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다."
    )

client = genai.Client(
    api_key=API_KEY
)


# ============================================================
# 뉴스 텍스트 정리
# ============================================================

def clean_text(text):

    if not text:
        return ""

    return (
        str(text)
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
    )


# ============================================================
# 뉴스 데이터 정리
# ============================================================

def prepare_news(news_list):

    prepared = []

    seen_urls = set()

    for news in news_list:

        title = clean_text(
            news.get("title", "")
        )

        description = clean_text(
            news.get("description", "")
        )

        url = (
            news.get("originallink")
            or news.get("link")
            or ""
        )

        if not title:
            continue

        # URL 중복 제거
        if url and url in seen_urls:
            continue

        if url:
            seen_urls.add(url)

        prepared.append({
            "id": len(prepared) + 1,
            "title": title,
            "description": description,
            "url": url,
            "source": clean_text(
                news.get("source", "")
            ),
            "pubDate": clean_text(
                news.get("pubDate", "")
            )
        })

    return prepared


# ============================================================
# Gemini 프롬프트
# ============================================================

SYSTEM_PROMPT = """
당신은 삼성화재 강원영업단 RC를 위한
매일 아침 보험·의료 뉴스 브리핑을 만드는 전문 편집자입니다.

목표는 단순한 뉴스 요약이 아니라
삼성화재 RC가 고객과 실제 영업 대화를 시작할 수 있는
뉴스 소재를 선별하고 재구성하는 것입니다.

반드시 다음 원칙을 지키십시오.

[대상]

1. 보험 제도 및 정책
2. 의료비
3. 비급여
4. 실손보험
5. 건강보험
6. 간병
7. 암·뇌혈관·심혈관 등 중증질환
8. 신의료기술
9. 건강보험공단
10. 건강보험심사평가원
11. 금융감독원
12. 금융위원회
13. 손해보험협회
14. 삼성화재의 장기보장성 보험 및 서비스

[제외]

다음 내용은 절대 선정하지 마십시오.

- 주식 시세
- 주가
- 영업이익
- 순이익
- 매출
- 실적 전망
- 기업 실적 경쟁
- 자동차보험
- 휴대폰보험
- 여행자보험
- 펫보험
- 기타 만기 3년 이내 일반보험
- 단순 기업 홍보
- 연예·사건·정치 일반 뉴스
- 보험영업 조직에 부정적인 내용
- 삼성화재 RC의 영업활동에 불리하게 사용할 가능성이 높은 내용

[삼성화재 소식]

삼성화재 관련 뉴스는 장기보장성 보험,
건강보험, 어린이보험, 실손보험, 간병 관련 보장,
질병 관련 서비스 등 RC의 영업활동에 활용할 수 있는
내용을 우선합니다.

단순한 기업 실적 뉴스는 제외합니다.

[기사 처리]

기사 원문을 그대로 복사하지 마십시오.

제목과 내용을 바탕으로 핵심을 파악하고
RC가 이해하기 쉽도록 요약·재구성하십시오.

기사에 없는 사실을 만들어내지 마십시오.

[영업 Tip]

각 기사마다 반드시
"오늘 이 뉴스를 가지고 고객에게 어떤 질문을 할 것인가?"
라는 관점에서 실제 대화에 사용할 수 있는
짧은 영업 Tip을 작성하십시오.

상품을 무리하게 직접 판매하는 표현보다
뉴스 → 고객 관심 → 보장 필요성 확인
순서의 자연스러운 접근을 우선합니다.

[우선순위]

RC 영업활동에 도움이 되는 순서대로
각 카테고리의 기사를 우선 평가하십시오.

특히 다음을 높게 평가합니다.

- 고객이 쉽게 공감할 수 있는 내용
- 병원비 부담과 연결되는 내용
- 비급여와 연결되는 내용
- 실손보험과 연결되는 내용
- 간병비와 연결되는 내용
- 중증질환 치료비와 연결되는 내용
- 향후 보장 필요성을 설명하기 좋은 내용
- 고객에게 질문을 던지기 좋은 내용

[중요]

검색된 뉴스가 충분하지 않다면
억지로 기사를 만들어내지 마십시오.

기사에 없는 내용은 생성하지 마십시오.
"""


# ============================================================
# Gemini에 뉴스 배치 전송
# ============================================================

def analyze_batch(batch, batch_number):

    news_text = []

    for item in batch:

        news_text.append(
            f"""
[NEWS {item["id"]}]
제목: {item["title"]}
내용: {item["description"]}
출처: {item["source"]}
발행일: {item["pubDate"]}
원문: {item["url"]}
"""
        )

    prompt = SYSTEM_PROMPT + """

다음 뉴스들을 검토하십시오.

각 뉴스의 적합성을 판단한 뒤
보험·의료 영업활용 가치가 높은 뉴스만 선별하십시오.

반드시 JSON만 출력하십시오.

출력 형식:

{
  "articles": [
    {
      "category": "policy",
      "title": "재구성한 제목",
      "summary": "핵심 내용을 2~3문장으로 요약",
      "why_it_matters": "RC가 이 내용을 알아야 하는 이유",
      "sales_tip": "고객에게 활용할 수 있는 실제 영업 Tip",
      "source": "언론사 또는 기관명",
      "published_at": "기사 발행일",
      "source_url": "원문 URL"
    }
  ]
}

category는 반드시 다음 중 하나만 사용하십시오.

policy
medical
samsung_fire

각 배치에서는 좋은 뉴스가 없는 경우
articles를 빈 배열로 반환해도 됩니다.

""" + "\n".join(news_text)

    for attempt in range(MAX_RETRIES):

        try:

            print(
                f"  Gemini 요청 "
                f"(배치 {batch_number}, "
                f"시도 {attempt + 1}/{MAX_RETRIES})"
            )

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )

            text = response.text.strip()

            # 혹시 ```json 형태로 반환되는 경우 제거
            if text.startswith("```"):
                text = text.replace(
                    "```json",
                    ""
                ).replace(
                    "```",
                    ""
                ).strip()

            result = json.loads(text)

            if not isinstance(result, dict):
                raise ValueError(
                    "Gemini 응답이 JSON 객체가 아닙니다."
                )

            articles = result.get(
                "articles",
                []
            )

            if not isinstance(
                articles,
                list
            ):
                raise ValueError(
                    "articles가 배열이 아닙니다."
                )

            print(
                f"  → 배치 {batch_number} "
                f"분석 완료: {len(articles)}개"
            )

            return articles

        except Exception as e:

            error_text = str(e)

            print(
                f"  [Gemini 오류] {error_text}"
            )

            # 마지막 시도라면 빈 배열 반환
            if attempt == MAX_RETRIES - 1:

                print(
                    f"  [경고] 배치 {batch_number} "
                    f"최종 실패 → 건너뜁니다."
                )

                return []

            delay = RETRY_DELAYS[
                min(
                    attempt,
                    len(RETRY_DELAYS) - 1
                )
            ]

            print(
                f"  → {delay}초 후 재시도합니다."
            )

            time.sleep(delay)

    return []


# ============================================================
# 기사 중복 제거
# ============================================================

def remove_duplicate_articles(
    articles
):

    result = []

    seen = set()

    for article in articles:

        title = clean_text(
            article.get("title", "")
        )

        url = clean_text(
            article.get("source_url", "")
        )

        key = (
            url
            if url
            else title
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)

        result.append(article)

    return result


# ============================================================
# 카테고리별 정리
# ============================================================

def organize_articles(
    articles
):

    categories = {
        "policy": [],
        "medical": [],
        "samsung_fire": []
    }

    for article in articles:

        category = article.get(
            "category"
        )

        if category not in categories:
            continue

        categories[category].append(
            article
        )

    # 카테고리별 최대 5개
    for category in categories:

        categories[category] = (
            categories[category][:5]
        )

    return categories


# ============================================================
# 오늘의 영업 포인트
# ============================================================

def make_sales_points(
    categories
):

    points = []

    for category_name, articles in [
        ("제도 동향", categories["policy"]),
        ("의료비 이슈", categories["medical"]),
        ("삼성화재 소식", categories["samsung_fire"])
    ]:

        for article in articles:

            tip = article.get(
                "sales_tip",
                ""
            )

            if tip:

                points.append(
                    f"{category_name}: {tip}"
                )

            if len(points) >= 5:
                break

        if len(points) >= 5:
            break

    # 뉴스가 적은 경우 기본 문구
    if not points:

        points.append(
            "오늘 뉴스 중 고객의 병원비와 "
            "보장 필요성으로 연결할 수 있는 "
            "주제를 찾아 대화를 시작해 보세요."
        )

    return points[:5]


# ============================================================
# 메인
# ============================================================

def main():

    print("=" * 60)
    print("Gemini 뉴스 분석 시작")
    print("=" * 60)

    # --------------------------------------------------------
    # raw_news.json 읽기
    # --------------------------------------------------------

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"{INPUT_FILE} 파일이 없습니다."
        )

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        raw_data = json.load(f)

    # NAVER API 결과 구조 대응
    if isinstance(raw_data, dict):

        if "items" in raw_data:
            news_list = raw_data["items"]

        elif "news" in raw_data:
            news_list = raw_data["news"]

        else:
            # 여러 검색 결과가 배열 안에 들어있는 경우
            news_list = []

            for value in raw_data.values():

                if isinstance(value, list):
                    news_list.extend(value)

    elif isinstance(raw_data, list):

        news_list = raw_data

    else:

        news_list = []

    prepared_news = prepare_news(
        news_list
    )

    print(
        f"전체 수집 뉴스: "
        f"{len(prepared_news)}개"
    )

    # --------------------------------------------------------
    # AI 분석 대상 80개
    # --------------------------------------------------------

    analysis_news = prepared_news[
        :MAX_ANALYSIS_NEWS
    ]

    print(
        f"AI 분석 대상: "
        f"{len(analysis_news)}개"
    )

    # --------------------------------------------------------
    # 20개씩 배치
    # --------------------------------------------------------

    all_articles = []

    batches = [
        analysis_news[i:i + BATCH_SIZE]
        for i in range(
            0,
            len(analysis_news),
            BATCH_SIZE
        )
    ]

    print(
        f"Gemini 분석 배치: "
        f"{len(batches)}개"
    )

    for index, batch in enumerate(
        batches,
        start=1
    ):

        articles = analyze_batch(
            batch,
            index
        )

        all_articles.extend(
            articles
        )

        # 서버 부담을 줄이기 위한 짧은 간격
        if index < len(batches):
            time.sleep(3)

    print(
        f"Gemini 전체 분석 결과: "
        f"{len(all_articles)}개"
    )

    # --------------------------------------------------------
    # 중복 제거
    # --------------------------------------------------------

    all_articles = (
        remove_duplicate_articles(
            all_articles
        )
    )

    print(
        f"중복 제거 후: "
        f"{len(all_articles)}개"
    )

    # --------------------------------------------------------
    # 카테고리 구성
    # --------------------------------------------------------

    categories = organize_articles(
        all_articles
    )

    print(
        f"제도 동향: "
        f"{len(categories['policy'])}개"
    )

    print(
        f"의료비 이슈: "
        f"{len(categories['medical'])}개"
    )

    print(
        f"삼성화재 소식: "
        f"{len(categories['samsung_fire'])}개"
    )

    # --------------------------------------------------------
    # 최종 news.json
    # --------------------------------------------------------

    result = {

        "generated_at":
            time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),

        "model":
            MODEL_NAME,

        "data": {

            "policy": {
                "name": "제도 동향",
                "articles":
                    categories["policy"]
            },

            "medical": {
                "name": "의료비 이슈",
                "articles":
                    categories["medical"]
            },

            "samsung_fire": {
                "name": "삼성화재 소식",
                "articles":
                    categories["samsung_fire"]
            },

            "sales_points":
                make_sales_points(
                    categories
                )
        }
    }

    # --------------------------------------------------------
    # 저장
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("=" * 60)
    print(
        f"news.json 생성 완료: "
        f"{OUTPUT_FILE}"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()

