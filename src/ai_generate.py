import json
import os
import time
from pathlib import Path

from google import genai

INPUT_FILE = Path("data/raw_news.json")
OUTPUT_FILE = Path("data/news.json")

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.6-flash"

# 검색 결과는 상품/보장·의료비·간병 중심으로 들어오므로
# AI 분석 대상도 과도하게 늘리지 않는다.
MAX_ANALYSIS_NEWS = 40
BATCH_SIZE = 20
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
    return []


def prepare_news(news_list):
    prepared = []
    seen = set()
    for news in news_list:
        if not isinstance(news, dict):
            continue
        title = clean_text(news.get("title"))
        description = clean_text(news.get("description"))
        source_url = clean_text(news.get("source_url") or news.get("originallink") or news.get("url"))
        naver_url = clean_text(news.get("naver_url") or news.get("link"))
        published_at = clean_text(news.get("published_at") or news.get("pubDate") or news.get("publishedAt"))
        source = clean_text(news.get("source") or news.get("publisher"))
        group = clean_text(news.get("group"))
        if not title or not source_url or source_url in seen:
            continue
        seen.add(source_url)
        prepared.append({
            "id": len(prepared) + 1,
            "title": title,
            "description": description,
            "source_url": source_url,
            "naver_url": naver_url,
            "published_at": published_at,
            "source": source,
            "group": group,
        })
    return prepared


SYSTEM_PROMPT = """
당신은 '강원영업단 RC Morning Brief'의 전문 편집자입니다.

이 브리핑은 삼성화재 전속 RC가 아침에 3~5분 안에 읽고,
고객 상담과 보장 점검에 바로 활용하기 위한 자료입니다.

핵심 편집 원칙은 다음과 같습니다.

[콘텐츠 우선순위]
1. 상품·보장 변화 및 고객 보장 공백
2. 의료비 부담·비급여·고액 치료비·치료 과정
3. 간병비·간병인 비용·가족 간병 부담·간병인 지원
4. 삼성화재 건강보험·장기보험·간병 관련 소식
5. 보험 제도·정책 변화

보험 제도 뉴스는 고객의 보장이나 의료비 부담과 직접 연결되는 경우에만
선별하며, 단순 제도 설명은 우선순위를 낮춥니다.

[절대 제외]
다음과 같은 내용은 기사 내용이 사실이더라도 Morning Brief에 넣지 마십시오.

- GA의 장점이나 경쟁력을 긍정적으로 홍보하는 기사
- GA 확대·성장·시장점유율 확대를 긍정적으로 다루는 기사
- GA 이직·전환을 권유하거나 긍정적으로 묘사하는 기사
- 전속설계사에게 불리하다고 해석될 수 있는 기사
- 전속채널의 약화·위기·이탈을 강조하는 기사
- 전속설계사와 GA의 장단점을 비교하여 GA가 유리하다고 결론내리는 기사
- GA 수수료·조직구조·채널 경쟁 자체가 핵심인 기사
- 보험 판매채널 경쟁을 영업전략으로 다루는 기사

단, 채널 이야기가 포함되어 있더라도 고객의 실제 보장·보험료·의료비 부담에
직접 영향을 주는 중요한 사실이 있는 경우에는 채널 경쟁 부분은 제거하고
고객 관점의 핵심만 남길 수 있습니다.

[제외]
- 주가·주식시세
- 단순 매출·영업이익·순이익 실적
- 자동차보험
- 휴대폰보험
- 여행자보험
- 펫보험
- 연예·정치 일반·사건사고
- 단순 업계 인사·조직개편

기사 원문을 그대로 복사하지 말고 요약·재구성하십시오.
기사에 없는 사실이나 상품 보장 내용을 만들어내지 마십시오.
source_url과 published_at은 입력값을 그대로 유지하십시오.
"""


SALES_TIP_RULES = """
[세일즈 TIP 규칙]

1. 세일즈 TIP은 '뉴스 → 고객이 느낄 수 있는 부담 → 현재 보장 점검' 순서로 작성합니다.

2. 상품명을 억지로 넣지 말고 고객의 현재 보장을 확인하도록 유도합니다.

3. 암 뉴스:
진단비 하나만 권유하지 말고 수술·항암약물치료·항암방사선치료 등
치료 과정 전체의 비용을 살펴보는 '암 통합치료비' 관점으로 연결합니다.

4. 뇌혈관 뉴스:
진단비·수술비 하나만 강조하지 말고 진단 이후 시술·수술·치료 과정의
비용 부담을 살펴보는 '뇌혈관질환 통합치료비' 관점으로 연결합니다.

5. 심혈관 뉴스:
진단·시술·수술·약물치료 등 치료 과정 전체의 비용 부담을 살펴보는
'심혈관질환 통합치료비' 관점으로 연결합니다.

6. 간병 뉴스:
'간병인 사용일당'을 중심으로 표현하지 않습니다.
'간병인 지원', '간병인지원', '간병인 비용 부담', '가족의 간병 부담' 등
고객이 실제로 겪는 문제를 중심으로 대화합니다.

7. 의료비·비급여 뉴스:
'얼마가 더 든다'는 단순 공포 조장보다 어떤 상황에서 본인 부담이 커질 수 있는지
설명하고 현재 실손·건강보험 등 보장 구조를 점검하도록 합니다.

8. 고객에게 특정 담보 가입을 단정적으로 권유하지 않습니다.

9. 실제 RC가 고객에게 말할 수 있는 자연스러운 대화체로 작성합니다.

10. 뉴스와 연결성이 없는 담보나 상품을 억지로 언급하지 않습니다.
"""


def build_prompt(batch):
    news_text = []
    for item in batch:
        news_text.append(f"""
[NEWS_ID={item['id']}]
검색그룹: {item['group']}
제목: {item['title']}
내용: {item['description']}
출처: {item['source']}
발행일: {item['published_at']}
원문URL: {item['source_url']}
""")

    return SYSTEM_PROMPT + "\n" + SALES_TIP_RULES + """

[선별 기준]
각 기사를 다음 관점으로 평가하십시오.
- 상품·보장 관련성: 40점
- 의료비/치료비 부담: 25점
- 간병비/간병 부담: 20점
- 고객 관심도: 10점
- 보험 제도 관련성: 5점

점수가 높은 기사부터 선별하되, 채널 경쟁 기사에 해당하면 점수와 관계없이 제외합니다.

최종 출력은 기존 HTML과 호환되어야 하므로 카테고리는 반드시 다음 3개 중 하나만 사용하십시오.
- policy: 보험 제도·정책 변화
- medical: 상품·보장·의료비·간병 관련 뉴스
- samsung_fire: 삼성화재 관련 뉴스

중요:
- 반드시 JSON 객체 하나만 출력하십시오.
- Markdown 코드블록을 사용하지 마십시오.
- 전체 최대 10개 기사만 선택하십시오.
- policy는 최대 2개까지만 선택하십시오.
- medical은 최대 6개까지 선택하십시오.
- samsung_fire는 최대 2개까지 선택하십시오.
- 같은 기사나 사실상 동일한 기사는 중복 선택하지 마십시오.
- 좋은 뉴스가 없으면 articles를 빈 배열로 반환하십시오.

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

""" + "\n".join(news_text)


def analyze_batch(batch, batch_number):
    prompt = build_prompt(batch)
    for attempt in range(MAX_RETRIES_503 + 1):
        try:
            print(f"  Gemini 요청 (배치 {batch_number}, 시도 {attempt + 1}/{MAX_RETRIES_503 + 1})")
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            text = (response.text or "").strip()
            if text.startswith("```"):
                text = text.replace("```json", "", 1).replace("```", "").strip()
            result = json.loads(text)
            articles = result.get("articles", [])
            if not isinstance(articles, list):
                raise ValueError("articles가 배열이 아닙니다.")
            print(f"  → 배치 {batch_number} 분석 완료: {len(articles)}개")
            return articles
        except Exception as e:
            error_text = str(e)
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                print("  [Gemini 쿼터 초과] 해당 배치를 건너뜁니다.")
                return []
            if "503" in error_text or "UNAVAILABLE" in error_text:
                if attempt < MAX_RETRIES_503:
                    time.sleep(RETRY_DELAY_503)
                    continue
            print(f"  [Gemini 오류] {error_text}")
            return []
    return []


def restore_metadata(article, source_by_url):
    url = clean_text(article.get("source_url"))
    original = source_by_url.get(url)
    if original is None:
        return None
    article["source_url"] = original["source_url"]
    article["published_at"] = original["published_at"]
    article["source"] = original["source"] or clean_text(article.get("source"))
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
    categories = {"policy": [], "medical": [], "samsung_fire": []}
    for article in articles:
        category = article.get("category")
        if category in categories and article.get("source_url"):
            categories[category].append(article)
    categories["policy"] = categories["policy"][:2]
    categories["medical"] = categories["medical"][:6]
    categories["samsung_fire"] = categories["samsung_fire"][:2]
    return categories


def make_sales_points(categories):
    points = []
    for label, key in (
        ("상품·보장/의료비", "medical"),
        ("삼성화재 소식", "samsung_fire"),
        ("제도 동향", "policy"),
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

    if not candidates:
        output = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "categories": {"policy": [], "medical": [], "samsung_fire": []},
            "sales_points": [],
            "article_count": 0,
        }
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_FILE.open("w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return

    source_by_url = {item["source_url"]: item for item in candidates}
    analyzed = []

    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start:start + BATCH_SIZE]
        batch_number = (start // BATCH_SIZE) + 1
        analyzed.extend(analyze_batch(batch, batch_number))
        if start + BATCH_SIZE < len(candidates):
            time.sleep(3)

    restored = []
    for article in analyzed:
        fixed = restore_metadata(article, source_by_url)
        if fixed:
            restored.append(fixed)

    categories = organize_articles(deduplicate(restored))
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "categories": categories,
        "sales_points": make_sales_points(categories),
        "article_count": sum(len(items) for items in categories.values()),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"최종 기사: {output['article_count']}개")
    print(f"상품·보장/의료비·간병: {len(categories['medical'])}개")
    print(f"삼성화재 소식: {len(categories['samsung_fire'])}개")
    print(f"제도 동향: {len(categories['policy'])}개")
    print(f"파일 생성: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
