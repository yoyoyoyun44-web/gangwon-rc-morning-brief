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
        source_url = clean_text(news.get("source_url") or news.get("originallink") or news.get("originalLink") or news.get("url"))
        naver_url = clean_text(news.get("naver_url") or news.get("link"))
        published_at = clean_text(news.get("published_at") or news.get("pubDate") or news.get("publishedAt"))
        source = clean_text(news.get("source") or news.get("publisher"))
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


SYSTEM_PROMPT = """
당신은 '강원영업단 RC를 위한 Morning Brief' 전문 편집자입니다.
보험·의료 분야에서 삼성화재 RC의 고객 상담에 도움이 되는 뉴스만 선별합니다.

카테고리:
policy = 금융감독원·금융위원회·손해보험협회·보건복지부·건강보험공단·심평원 등의 보험 제도·정책
medical = 의료비·비급여·실손·간병·암·뇌혈관·심혈관·중증질환·신의료기술 등
samsung_fire = 삼성화재의 건강보험·어린이보험·실손보험·간병 등 장기보장성 보험 또는 관련 서비스

제외: 주가·주식시세·매출·영업이익·순이익·실적, 자동차보험·휴대폰보험·여행자보험·펫보험 등 단기 일반보험, 연예·사건·정치 일반 뉴스.
삼성화재 RC 영업에 명백히 불리한 내용도 선정하지 않습니다.

기사 원문을 복사하지 말고 요약·재구성하십시오. 기사에 없는 사실을 만들지 마십시오.
각 기사에는 RC가 고객에게 던질 수 있는 실제적인 'sales_tip'을 작성하십시오.
암 심혈관 뇌혈관 근골격계와 관련된 'sales_tip'을 작성할 때는 진단비 또는 수술비를 대비하라는 표현 보다 "통합치료비"란 표현으로 작성해줘. 
간병인 관련 기사에는 간병인 사용일당 보다는 간병비 인상에 걱정 없는 간병인 지원일당을 추천해줘

중요: source_url과 published_at은 입력값을 그대로 반환해야 합니다. 새 URL이나 날짜를 만들거나 수정하지 마십시오.
삼성화재 관련 적합한 뉴스가 없으면 samsung_fire 기사를 만들지 말고 빈 배열을 반환하십시오.
"""


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

    prompt = SYSTEM_PROMPT + """

아래 뉴스 중 영업활용 가치가 높은 기사만 선별하십시오.
반드시 JSON 객체 하나만 출력하고 Markdown 코드블록은 사용하지 마십시오.

{
  "articles": [
    {
      "category": "policy|medical|samsung_fire",
      "title": "재구성한 제목",
      "summary": "2~3문장 요약",
      "why_it_matters": "RC 관점의 의미",
      "sales_tip": "고객에게 활용할 수 있는 영업 Tip",
      "source": "입력된 출처",
      "published_at": "입력된 발행일을 그대로 복사",
      "source_url": "입력된 원문URL을 그대로 복사"
    }
  ]
}

category는 policy, medical, samsung_fire 중 하나만 사용하십시오.
좋은 뉴스가 없으면 articles를 빈 배열로 반환해도 됩니다.
""" + "\n".join(news_text)

    for attempt in range(MAX_RETRIES):
        try:
            print(f"  Gemini 요청 (배치 {batch_number}, 시도 {attempt + 1}/{MAX_RETRIES})")
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
            text = (response.text or "").strip()
            if text.startswith("```"):
                text = text.replace("```json", "", 1).replace("```", "").strip()
            result = json.loads(text)
            articles = result.get("articles", []) if isinstance(result, dict) else []
            if not isinstance(articles, list):
                raise ValueError("articles가 배열이 아닙니다.")
            print(f"  → 배치 {batch_number} 분석 완료: {len(articles)}개")
            return articles
        except Exception as e:
            print(f"  [Gemini 오류] {e}")
            if attempt == MAX_RETRIES - 1:
                print(f"  [경고] 배치 {batch_number} 최종 실패 → 건너뜁니다.")
                return []
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            print(f"  → {delay}초 후 재시도합니다.")
            time.sleep(delay)
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
    for category in categories:
        categories[category] = categories[category][:5]
    return categories


def make_sales_points(categories):
    points = []
    for label, key in (("제도 동향", "policy"), ("의료비 이슈", "medical"), ("삼성화재 소식", "samsung_fire")):
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

    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"{INPUT_FILE} 파일이 없습니다.")

    raw_news = prepare_news(load_news())
    print(f"전체 수집 뉴스: {len(raw_news)}개")

    candidates = raw_news[:MAX_ANALYSIS_NEWS]
    print(f"AI 분석 대상: {len(candidates)}개")

    source_by_url = {item["source_url"]: item for item in candidates}
    analyzed = []

    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start:start + BATCH_SIZE]
        analyzed.extend(analyze_batch(batch, start // BATCH_SIZE + 1))

    restored = []
    for article in analyzed:
        fixed = restore_metadata(article, source_by_url)
        if fixed:
            restored.append(fixed)

    restored = deduplicate(restored)
    categories = organize_articles(restored)

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "categories": categories,
        "sales_points": make_sales_points(categories),
        "article_count": sum(len(items) for items in categories.values())
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"최종 기사: {output['article_count']}개")
    print(f"제도 동향: {len(categories['policy'])}개")
    print(f"의료비 이슈: {len(categories['medical'])}개")
    print(f"삼성화재 소식: {len(categories['samsung_fire'])}개")
    print(f"파일 생성: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
