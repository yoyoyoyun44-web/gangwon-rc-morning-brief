
import json
import os
import time
from pathlib import Path

from google import genai

INPUT_FILE = Path("data/raw_news.json")
OUTPUT_FILE = Path("data/news.json")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.6-flash"

BATCH_SIZE = 20
MAX_RETRIES = 4
RETRY_DELAYS = [30, 60, 120, 180]
MAX_ANALYSIS_NEWS = 80

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다.")

client = genai.Client(api_key=API_KEY)


def clean_text(value):
    return str(value or "").replace("\n", " ").replace("\r", " ").strip()


def load_news():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
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

        key = source_url

        if key in seen:
            continue

        seen.add(key)

        prepared.append({
            "id": len(prepared) + 1,
            "title": title,
            "description": description,
            "source_url": source_url,
            "naver_url": naver_url,
            "published_at": published_at,
            "source": source,
        })

    return prepared


# ============================================================
# Gemini 기본 편집 지침
# ============================================================

SYSTEM_PROMPT = """
당신은 '강원영업단 RC를 위한 Morning Brief' 전문 편집자입니다.

보험·의료 분야에서 삼성화재 RC의 고객 상담에 도움이 되는 뉴스만 선별합니다.

[카테고리]

policy
= 금융감독원·금융위원회·손해보험협회·보건복지부·건강보험공단·심평원 등의
보험 제도·정책 관련 뉴스

medical
= 의료비·비급여·실손·간병·암·뇌혈관·심혈관·중증질환·신의료기술 등
고객의 의료비 및 보장 설계와 관련된 뉴스

samsung_fire
= 삼성화재의 건강보험·어린이보험·실손보험·간병 등
장기보장성 보험 또는 관련 서비스 뉴스

[제외]

- 주가·주식시세
- 매출·영업이익·순이익·실적
- 자동차보험
- 휴대폰보험
- 여행자보험
- 펫보험 등 단기 일반보험
- 연예
- 사건
- 정치 일반 뉴스
- 삼성화재 RC 영업에 명백히 불리한 내용

기사 원문을 그대로 복사하지 말고 요약·재구성하십시오.
기사에 없는 사실을 만들지 마십시오.

각 기사에는 RC가 고객에게 실제로 던질 수 있는
자연스러운 'sales_tip'을 작성하십시오.

간병인 관련 기사에서는
'간병인 사용일당'이라는 표현을 사용하지 말고
'간병인 지원일당'이라는 표현을 사용하십시오.

중요:
source_url과 published_at은 입력값을 그대로 반환해야 합니다.
새로운 URL이나 날짜를 만들거나 수정하지 마십시오.

삼성화재 관련 적합한 뉴스가 없으면
samsung_fire 기사를 억지로 만들지 말고 빈 배열을 반환하십시오.
"""


# ============================================================
# 세일즈 팁 작성 규칙
# ============================================================

SALES_TIP_RULES = """
[세일즈 팁 작성 핵심 규칙]

1. 기본 원칙

뉴스의 내용을 보험 영업에 자연스럽게 연결하십시오.

상품명을 무조건 홍보하지 말고,
뉴스 → 고객의 걱정 → 현재 보장 점검 → 필요한 보장 준비
순서로 자연스럽게 연결하십시오.

세일즈 팁은 실제 RC가 고객에게 말할 수 있는
자연스러운 대화체로 작성하십시오.


2. 암 관련 뉴스

암 관련 뉴스에서는
'암 진단비' 또는 '암 수술비'를 단순히 별도로 권유하는 표현을
우선적으로 사용하지 마십시오.

암 진단 이후 발생할 수 있는

- 수술
- 항암약물치료
- 항암방사선치료
- 기타 치료 과정

전체를 고려하여

'암 통합치료비'
또는
'통합치료비'

관점으로 제안하십시오.

핵심은 특정 하나의 치료비를 권유하는 것이 아니라
암 치료 과정 전체에 필요한 비용을 통합적으로 준비하고 있는지
고객의 기존 보장을 점검하도록 하는 것입니다.


3. 뇌혈관질환 관련 뉴스

뇌혈관질환 관련 뉴스에서는

'뇌혈관 진단비'
또는
'뇌혈관 수술비'

만을 단독으로 강조하지 마십시오.

진단부터 수술 및 이후 치료 과정까지 발생할 수 있는 비용을 고려하여

'뇌혈관질환 통합치료비'
또는
'통합치료비'

관점으로 제안하십시오.

고객에게 현재 보장에서 치료 과정 전체가 충분히 준비되어 있는지
점검하도록 유도하십시오.


4. 심혈관질환 관련 뉴스

심혈관질환 관련 뉴스에서는

'심혈관 진단비'
또는
'심혈관 수술비'

만을 단독으로 강조하지 마십시오.

진단·시술·수술·약물치료 등
치료 과정 전체를 고려하여

'심혈관질환 통합치료비'
또는
'통합치료비'

관점으로 제안하십시오.


5. 항암약물치료 관련 뉴스

항암약물치료가 뉴스에 언급된 경우

'항암약물치료비를 가입하세요'
와 같이 단일 담보 가입을 직접 권유하지 마십시오.

암 치료 과정 전체를 고려한
'통합치료비' 관점으로 설명하십시오.


6. 항암방사선치료 관련 뉴스

항암방사선치료가 뉴스에 언급된 경우에도

'항암방사선치료비를 가입하세요'
와 같이 단일 담보 가입을 직접 권유하지 마십시오.

암 치료 과정 전체를 고려한
'통합치료비' 관점으로 설명하십시오.


7. 고객 중심 표현

좋은 방향의 표현:

'최근 암 치료는 진단 이후 수술뿐 아니라
항암약물치료와 항암방사선치료 등
다양한 치료가 이어질 수 있습니다.

이런 치료 과정에서 필요한 비용을
통합적으로 준비하고 있는지
현재 보장을 한번 점검해 보시는 것이 좋습니다.'


8. 피해야 할 표현

다음과 같은 표현을 사용하지 마십시오.

- '암 진단비를 준비하세요.'
- '암 수술비를 준비하세요.'
- '뇌혈관 진단비를 준비하세요.'
- '뇌혈관 수술비를 준비하세요.'
- '심혈관 진단비를 준비하세요.'
- '심혈관 수술비를 준비하세요.'
- '항암약물치료비를 가입하세요.'
- '항암방사선치료비를 가입하세요.'


9. 억지 연결 금지

모든 뉴스에 통합치료비를 억지로 언급하지 마십시오.

암·뇌혈관·심혈관질환 또는 관련 치료 내용과
실질적인 연결성이 있을 때만 자연스럽게 활용하십시오.


10. 간병 관련 뉴스

간병 관련 뉴스에서는
'간병인 사용일당'이라는 표현을 사용하지 마십시오.

대신

'간병인 지원일당'

이라는 표현을 사용하십시오.

고객이 실제 간병 상황에서
간병 서비스를 어떻게 준비할 수 있는지를 중심으로 설명하십시오.


11. 제도·정책 뉴스

policy 뉴스에서는
무조건 특정 보험상품을 권유하지 마십시오.

제도 변화가 고객의 보험료·보장·의료비 부담에
어떤 영향을 줄 수 있는지 설명한 후,

'현재 가입한 보험에서 해당 부분이 어떻게 준비되어 있는지
확인해 보자'

는 방향으로 연결하십시오.


12. 의료비 뉴스

medical 뉴스에서는
고객이 실제로 부담할 수 있는 의료비와 치료 과정에 초점을 맞추십시오.

특히 암·뇌혈관·심혈관질환과 관련된 경우
가능하면 치료 과정 전체를 바라보는
'통합치료비' 관점으로 연결하십시오.


13. 삼성화재 뉴스

samsung_fire 뉴스에서는
기사에 실제로 등장하는 상품·서비스·변화만 활용하십시오.

기사에 없는 상품이나 보장 내용을 만들어내지 마십시오.


14. 최종 원칙

세일즈 팁은 보험을 판매하기 위한 광고 문구가 아니라
RC가 고객과 대화를 시작하기 위한 질문과 상담 소재가 되어야 합니다.

따라서 다음과 같은 흐름을 가장 우선합니다.

'최근 이런 뉴스가 있습니다.'
→
'고객님도 이런 상황이 생기면 어떨까요?'
→
'현재 가입하신 보험에서 이런 치료 과정이 충분히 준비되어 있을까요?'
→
'한번 같이 점검해 보시죠.'

단, 기사 내용과 연결되지 않는 경우에는 억지로 이 흐름을 적용하지 마십시오.
"""


# ============================================================
# 배치 분석
# ============================================================

def analyze_batch(batch, batch_number):
    news_text = []

    for item in batch:
        news_text.append(
            f"[NEWS_ID={item['id']}]\n"
            f"제목: {item['title']}\n"
            f"내용: {item['description']}\n"
            f"출처: {item['source']}\n"
            f"발행일: {item['published_at']}\n"
            f"원문URL: {item['source_url']}\n"
        )

    prompt = (
        SYSTEM_PROMPT
        + "\n\n"
        + SALES_TIP_RULES
        + """
        
[기사 선별 및 출력 지침]

아래 뉴스 중 강원영업단 RC가
고객 상담에 활용할 가치가 높은 기사만 선별하십시오.

기사 내용과 보험 영업의 연결성이 낮으면 제외하십시오.

반드시 JSON 객체 하나만 출력하십시오.
Markdown 코드블록은 사용하지 마십시오.

출력 형식:

{
  "articles": [
    {
      "category": "policy|medical|samsung_fire",
      "title": "재구성한 제목",
      "summary": "2~3문장 요약",
      "why_it_matters": "RC 관점의 의미",
      "sales_tip": "고객에게 실제로 활용할 수 있는 자연스러운 영업 Tip",
      "source": "입력된 출처",
      "published_at": "입력된 발행일을 그대로 복사",
      "source_url": "입력된 원문URL을 그대로 복사"
    }
  ]
}

category는 반드시
policy,
medical,
samsung_fire
중 하나만 사용하십시오.

좋은 뉴스가 없으면
articles를 빈 배열로 반환하십시오.

특히 sales_tip은 위에서 제공한
[세일즈 팁 작성 핵심 규칙]을 반드시 준수하십시오.

암·뇌혈관·심혈관질환 관련 뉴스에서는
단순한 진단비·수술비 판매 문구보다
치료 과정 전체를 바라보는 '통합치료비' 관점을 우선하십시오.

그러나 기사 내용과 관련이 없는 경우
통합치료비를 억지로 언급하지 마십시오.
"""
        + "\n".join(news_text)
    )

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

            text = (response.text or "").strip()

            # Gemini가 혹시 Markdown 코드블록을 반환할 경우 제거
            if text.startswith("```"):
                text = text.replace("```json", "", 1)
                text = text.replace("```", "")
                text = text.strip()

            result = json.loads(text)

            articles = (
                result.get("articles", [])
                if isinstance(result, dict)
                else []
            )

            if not isinstance(articles, list):
                raise ValueError("articles가 배열이 아닙니다.")

            print(
                f"  → 배치 {batch_number} 분석 완료: "
                f"{len(articles)}개"
            )

            return articles

        except Exception as e:
            print(f"  [Gemini 오류] {e}")

            if attempt == MAX_RETRIES - 1:
                print(
                    f"  [경고] 배치 {batch_number} "
                    f"최종 실패 → 건너뜁니다."
                )
                return []

            delay = RETRY_DELAYS[
                min(attempt, len(RETRY_DELAYS) - 1)
            ]

            print(f"  → {delay}초 후 재시도합니다.")
            time.sleep(delay)

    return []


# ============================================================
# 원본 메타데이터 복구
# ============================================================

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


# ============================================================
# 중복 제거
# ============================================================

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


# ============================================================
# 카테고리 정리
# ============================================================

def organize_articles(articles):
    categories = {
        "policy": [],
        "medical": [],
        "samsung_fire": []
    }

    for article in articles:
        category = article.get("category")

        if (
            category in categories
            and article.get("source_url")
        ):
            categories[category].append(article)

    # 카테고리별 최대 5개
    for category in categories:
        categories[category] = categories[category][:5]

    return categories


# ============================================================
# 오늘의 영업 활용 포인트
# ============================================================

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
                points.append(
                    f"{label}: {tip}"
                )

            if len(points) >= 5:
                return points

    return points


# ============================================================
# 메인
# ============================================================

def main():
    print("=" * 60)
    print("Gemini 뉴스 분석 시작")
    print("=" * 60)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} 파일이 없습니다."
        )

    raw_news = prepare_news(
        load_news()
    )

    print(
        f"전체 수집 뉴스: "
        f"{len(raw_news)}개"
    )

    candidates = raw_news[:MAX_ANALYSIS_NEWS]

    print(
        f"AI 분석 대상: "
        f"{len(candidates)}개"
    )

    source_by_url = {
        item["source_url"]: item
        for item in candidates
    }

    analyzed = []

    for start in range(
        0,
        len(candidates),
        BATCH_SIZE
    ):
        batch = candidates[
            start:start + BATCH_SIZE
        ]

        analyzed.extend(
            analyze_batch(
                batch,
                start // BATCH_SIZE + 1
            )
        )

    restored = []

    for article in analyzed:
        fixed = restore_metadata(
            article,
            source_by_url
        )

        if fixed:
            restored.append(fixed)

    restored = deduplicate(restored)

    categories = organize_articles(
        restored
    )

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
        )
    }

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
            output,
            f,
            ensure_ascii=False,
            indent=2
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

    print(
        f"파일 생성: "
        f"{OUTPUT_FILE}"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
