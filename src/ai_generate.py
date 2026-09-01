import json
import os
import time
from pathlib import Path

from google import genai

INPUT_FILE = Path("data/raw_news.json")
OUTPUT_FILE = Path("data/news.json")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.6-flash"

# 무료 Gemini 쿼터를 고려하여 호출 횟수를 최소화
MAX_ANALYSIS_NEWS = 40
BATCH_SIZE = 20

# 429(쿼터 초과)는 기다리지 않고 즉시 해당 배치를 건너뜀
MAX_RETRIES_503 = 2
RETRY_DELAY_503 = 20

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다.")

client = genai.Client(api_key=API_KEY)


def clean_text(value):
    return str(value or "").replace("\n", " ").replace("\r", " ").strip()


def load_news():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"{INPUT_FILE} 파일이 없습니다.")

    with INPUT_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("items", "news", "articles"):
            if isinstance(data.get(key), list):
                return data[key]

        result = []
        for value in data.values():
            if isinstance(value, list):
                result.extend(value)
        return result

    return []


def prepare_news(news_list):
    prepared = []
    seen = set()

    for news in news_list:
        if not isinstance(news, dict):
            continue

        title = clean_text(news.get("title"))
        description = clean_text(news.get("description"))

        source_url = clean_text(
            news.get("source_url")
            or news.get("originallink")
            or news.get("originalLink")
            or news.get("url")
        )

        naver_url = clean_text(
            news.get("naver_url")
            or news.get("link")
        )

        published_at = clean_text(
            news.get("published_at")
            or news.get("pubDate")
            or news.get("publishedAt")
        )

        source = clean_text(
            news.get("source")
            or news.get("publisher")
        )

        if not title or not source_url:
            continue

        if source_url in seen:
            continue

        seen.add(source_url)

        prepared.append(
            {
                "id": len(prepared) + 1,
                "title": title,
                "description": description,
                "source_url": source_url,
                "naver_url": naver_url,
                "published_at": published_at,
                "source": source,
            }
        )

    return prepared


SYSTEM_PROMPT = """
당신은 '강원영업단 RC를 위한 Morning Brief' 전문 편집자입니다.

목표:
보험·의료 분야에서 삼성화재 RC가 고객 상담에 활용하기 좋은 뉴스를 선별하고,
기사의 핵심 내용을 이해하기 쉽게 요약하며,
실제 고객 상담에 사용할 수 있는 자연스러운 세일즈 Tip을 작성합니다.

카테고리:

policy
= 금융감독원, 금융위원회, 손해보험협회, 보건복지부,
  건강보험공단, 건강보험심사평가원 등과 관련된
  보험 제도·정책·의료 제도 변화

medical
= 의료비, 비급여, 실손보험, 간병,
  암, 뇌혈관질환, 심혈관질환,
  중증질환, 신의료기술 등과 관련된 뉴스

samsung_fire
= 삼성화재의 건강보험, 어린이보험, 실손보험,
  간병, 장기보장성 보험 또는 관련 서비스 뉴스

제외:
- 주가·주식시세
- 매출·영업이익·순이익 등 단순 실적 기사
- 자동차보험
- 휴대폰보험
- 여행자보험
- 펫보험
- 연예
- 사건
- 정치 일반 뉴스

기사 원문을 그대로 복사하지 말고 요약·재구성하십시오.

기사에 없는 사실을 만들지 마십시오.

각 기사에는 RC가 고객에게 자연스럽게 질문하거나
보장 점검으로 연결할 수 있는 sales_tip을 작성하십시오.

중요:
source_url과 published_at은 반드시 입력값을 그대로 반환하십시오.
새 URL이나 날짜를 만들거나 수정하지 마십시오.

삼성화재 관련 적합한 뉴스가 없으면
samsung_fire 기사를 억지로 만들지 말고 빈 배열을 반환하십시오.
"""


SALES_TIP_RULES = """
[세일즈 팁 작성 핵심 규칙]

1. 뉴스 내용을 보험 영업에 자연스럽게 연결하십시오.

2. 암 관련 뉴스인 경우:

단순히
'암 진단비를 준비하세요'
'암 수술비를 준비하세요'
라고 권유하지 마십시오.

암 진단 이후 실제 치료 과정에서 발생할 수 있는
수술, 항암약물치료, 항암방사선치료 등
여러 치료 과정을 종합적으로 고려하는

'암 통합치료비'
또는
'통합치료비'

관점으로 설명하십시오.

고객에게 특정 담보 가입을 강요하기보다
현재 암 치료비를 통합적으로 준비하고 있는지
점검하도록 유도하십시오.


3. 뇌혈관질환 관련 뉴스인 경우:

'뇌혈관 진단비'
'뇌혈관 수술비'

만을 단독으로 강조하지 마십시오.

진단 이후 수술과 치료 과정에서 발생할 수 있는 비용을
종합적으로 고려하여

'뇌혈관질환 통합치료비'
또는
'통합치료비'

관점으로 제안하십시오.


4. 심혈관질환 관련 뉴스인 경우:

'심혈관 진단비'
'심혈관 수술비'

만을 단독으로 강조하지 마십시오.

진단, 시술, 수술, 약물치료 등
치료 과정 전체를 고려하여

'심혈관질환 통합치료비'
또는
'통합치료비'

관점으로 제안하십시오.


5. 항암약물치료 또는 항암방사선치료가
뉴스에 언급된 경우:

해당 치료비 하나만 가입하라는 식으로
표현하지 마십시오.

암 치료 과정 전체를 고려하는
'통합치료비' 관점에서 설명하십시오.


6. 상품명을 단정적으로 홍보하지 마십시오.

고객의 현재 보장 내용을 확인하고
부족한 부분이 있는지 점검하도록 유도하십시오.


7. 간병 관련 뉴스인 경우:

'간병인 사용일당'이라는 표현을 사용하지 마십시오.

가능하면
'간병인 지원'
'간병인지원'
'간병인 지원일당'

등의 표현을 사용하십시오.


8. 실제 RC가 고객에게 말할 수 있는
자연스러운 대화체로 작성하십시오.


9. 뉴스와 연결성이 없는 경우
억지로 통합치료비를 언급하지 마십시오.


10. 다음과 같은 표현은 피하십시오.

'암 진단비를 준비하세요.'
'암 수술비를 준비하세요.'
'뇌혈관 진단비를 준비하세요.'
'뇌혈관 수술비를 준비하세요.'
'심혈관 진단비를 준비하세요.'
'심혈관 수술비를 준비하세요.'
'항암약물치료비를 가입하세요.'
'항암방사선치료비를 가입하세요.'


11. 권장되는 방향:

'최근 치료는 진단 이후 수술뿐 아니라
항암약물치료와 항암방사선치료 등
여러 치료가 이어질 수 있습니다.
현재 이런 치료 과정에서 필요한 비용을
통합적으로 준비하고 있는지 한번 점검해 보시죠.'


12. 세일즈 Tip은 가능하면
'뉴스 → 고객의 걱정 → 현재 보장 점검'
순서로 자연스럽게 연결하십시오.
"""


def build_prompt(batch):
    news_text = []

    for item in batch:
        news_text.append(
            f"""
[NEWS_ID={item['id']}]
제목: {item['title']}
내용: {item['description']}
출처: {item['source']}
발행일: {item['published_at']}
원문URL: {item['source_url']}
"""
        )

    return (
        SYSTEM_PROMPT
        + "\n"
        + SALES_TIP_RULES
        + """

아래 뉴스 중 강원영업단 RC의 영업활용 가치가 높은 기사만 선별하십시오.

중요:
- 반드시 JSON 객체 하나만 출력하십시오.
- Markdown 코드블록을 사용하지 마십시오.
- 최대 5개의 기사만 선택하십시오.
- 카테고리별로 최대 5개입니다.
- 같은 기사나 사실상 동일한 기사는 중복 선택하지 마십시오.

JSON 형식:

{
  "articles": [
    {
      "category": "policy|medical|samsung_fire",
      "title": "재구성한 제목",
      "summary": "2~3문장 요약",
      "why_it_matters": "RC 관점의 의미",
      "sales_tip": "실제 고객에게 말할 수 있는 자연스러운 영업 Tip",
      "source": "입력된 출처",
      "published_at": "입력된 발행일",
      "source_url": "입력된 원문URL"
    }
  ]
}

좋은 뉴스가 없으면 articles를 빈 배열로 반환하십시오.

"""
        + "\n".join(news_text)
    )


def analyze_batch(batch, batch_number):
    prompt = build_prompt(batch)

    for attempt in range(MAX_RETRIES_503 + 1):
        try:
            print(
                f"  Gemini 요청 "
                f"(배치 {batch_number}, 시도 {attempt + 1}/{MAX_RETRIES_503 + 1})"
            )

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )

            text = (response.text or "").strip()

            if text.startswith("```"):
                text = text.replace("```json", "", 1)
                text = text.replace("```", "")
                text = text.strip()

            result = json.loads(text)

            if not isinstance(result, dict):
                raise ValueError("Gemini 응답이 JSON 객체가 아닙니다.")

            articles = result.get("articles", [])

            if not isinstance(articles, list):
                raise ValueError("articles가 배열이 아닙니다.")

            print(
                f"  → 배치 {batch_number} 분석 완료: "
                f"{len(articles)}개"
            )

            return articles

        except Exception as e:
            error_text = str(e)

            # 무료 쿼터 초과
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                print(
                    "  [Gemini 쿼터 초과] "
                    "추가 재시도를 하지 않고 해당 배치를 건너뜁니다."
                )
                return []

            # 서버 일시 오류
            if "503" in error_text or "UNAVAILABLE" in error_text:
                if attempt < MAX_RETRIES_503:
                    print(
                        f"  [Gemini 서버 일시 오류] "
                        f"{RETRY_DELAY_503}초 후 재시도합니다."
                    )
                    time.sleep(RETRY_DELAY_503)
                    continue

            print(f"  [Gemini 오류] {error_text}")
            print(
                f"  [경고] 배치 {batch_number} 분석 실패 → 건너뜁니다."
            )
            return []

    return []


def restore_metadata(article, source_by_url):
    url = clean_text(article.get("source_url"))

    original = source_by_url.get(url)

    if original is None:
        return None

    article["source_url"] = original["source_url"]
    article["published_at"] = original["published_at"]
    article["source"] = (
        original["source"]
        or clean_text(article.get("source"))
    )
    article["naver_url"] = original["naver_url"]

    return article


def deduplicate(articles):
    result = []
    seen = set()

    for article in articles:
        url = clean_text(article.get("source_url"))

        if not url or url in seen:
            continue

        seen.add(url)
        result.append(article)

    return result


def organize_articles(articles):
    categories = {
        "policy": [],
        "medical": [],
        "samsung_fire": [],
    }

    for article in articles:
        category = article.get("category")

        if (
            category in categories
            and article.get("source_url")
        ):
            categories[category].append(article)

    for category in categories:
        categories[category] = categories[category][:5]

    return categories


def make_sales_points(categories):
    points = []

    for label, key in (
        ("제도 동향", "policy"),
        ("의료비 이슈", "medical"),
        ("삼성화재 소식", "samsung_fire"),
    ):
        for article in categories[key]:
            tip = clean_text(article.get("sales_tip"))

            if tip:
                points.append(f"{label}: {tip}")

            if len(points) >= 5:
                return points

    return points


def main():
    print("=" * 60)
    print("Gemini 뉴스 분석 시작")
    print("=" * 60)

    raw_news = prepare_news(load_news())

    print(f"전체 수집 뉴스: {len(raw_news)}개")

    candidates = raw_news[:MAX_ANALYSIS_NEWS]

    print(f"AI 분석 대상: {len(candidates)}개")
    print(f"배치 크기: {BATCH_SIZE}개")

    if not candidates:
        print("[경고] 분석할 뉴스가 없습니다.")

        output = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "categories": {
                "policy": [],
                "medical": [],
                "samsung_fire": [],
            },
            "sales_points": [],
            "article_count": 0,
        }

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

        with OUTPUT_FILE.open("w", encoding="utf-8") as f:
            json.dump(
                output,
                f,
                ensure_ascii=False,
                indent=2,
            )

        return

    source_by_url = {
        item["source_url"]: item
        for item in candidates
    }

    analyzed = []

    for start in range(
        0,
        len(candidates),
        BATCH_SIZE,
    ):
        batch = candidates[
            start:start + BATCH_SIZE
        ]

        batch_number = (
            start // BATCH_SIZE
        ) + 1

        result = analyze_batch(
            batch,
            batch_number,
        )

        analyzed.extend(result)

        # 무료 API에 불필요한 연속 요청을 피함
        if start + BATCH_SIZE < len(candidates):
            time.sleep(3)

    restored = []

    for article in analyzed:
        fixed = restore_metadata(
            article,
            source_by_url,
        )

        if fixed:
            restored.append(fixed)

    restored = deduplicate(restored)

    categories = organize_articles(restored)

    output = {
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%S%z"
        ),
        "categories": categories,
        "sales_points": make_sales_points(
            categories
        ),
        "article_count": sum(
            len(items)
            for items in categories.values()
        ),
    }

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 60)
    print(
        f"최종 기사: "
        f"{output['article_count']}개"
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
    print(f"파일 생성: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()

