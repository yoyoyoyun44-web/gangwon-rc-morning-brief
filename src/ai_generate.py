import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from google import genai

INPUT_FILE = Path("data/raw_news.json")
OUTPUT_FILE = Path("data/news.json")
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.6-flash"
MAX_ANALYSIS_NEWS = 50
BATCH_SIZE = 20
MAX_RETRIES_503 = 2
RETRY_DELAY_503 = 20

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다.")

client = genai.Client(api_key=API_KEY)

MAJOR_NEWS_DOMAINS = {
    "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr", "hankookilbo.com",
    "mk.co.kr", "hankyung.com", "sedaily.com", "fnnews.com", "newsis.com",
    "yna.co.kr", "news1.kr", "edaily.co.kr", "heraldcorp.com", "asiae.co.kr",
    "mt.co.kr", "seoul.co.kr", "khan.co.kr", "nocutnews.co.kr", "ytn.co.kr"
}

OTHER_INSURER_NAMES = [
    "현대해상", "DB손해보험", "메리츠화재", "KB손해보험", "한화손해보험",
    "롯데손해보험", "흥국화재", "NH농협손해보험", "하나손해보험", "AXA손해보험",
    "악사손해보험", "캐롯손해보험", "삼성생명", "한화생명", "교보생명",
    "신한라이프", "KB라이프", "NH농협생명", "미래에셋생명", "동양생명",
    "흥국생명", "DB생명", "ABL생명", "푸본현대생명", "라이나생명", "AIA생명",
    "메트라이프", "처브라이프", "KDB생명", "iM라이프"
]

OTHER_INSURER_PROMO_TERMS = [
    "신상품", "상품 출시", "출시", "보장 강화", "보장확대", "보장 확대",
    "가입자", "체결", "판매", "판매 돌입", "판매 개시", "인기", "히트상품",
    "주력상품", "대표상품", "추천", "특화상품", "특화 상품", "배타적사용권",
    "배타적 사용권", "상품 경쟁력", "흥행", "완판", "판매실적", "판매 실적",
    "시장점유율"
]


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
            "is_major_news": bool(news.get("is_major_news")) or source in MAJOR_NEWS_DOMAINS,
        })
    return prepared


def is_other_insurer_promo(article):
    text = f"{article.get('title', '')} {article.get('description', '')}"
    if not any(name in text for name in OTHER_INSURER_NAMES):
        return False
    if not any(term in text for term in OTHER_INSURER_PROMO_TERMS):
        return False
    medical_context = [
        "의료비", "치료비", "비급여", "본인부담", "간병비", "간병", "치료", "환자",
        "질환", "건강보험", "의료", "병원", "신약", "암", "뇌혈관", "심혈관"
    ]
    # 객관적인 의료비 기사에 타 보험사가 사례로 등장한 경우는 AI가 다시 판단하도록 살린다.
    return not any(term in text for term in medical_context)


SYSTEM_PROMPT = """
당신은 '강원영업단 RC Morning Brief'의 전문 편집자입니다.

이 자료는 삼성화재 전속 RC에게 아침마다 배포하는 실전 영업용 브리핑입니다.
목적은 뉴스를 많이 보여주는 것이 아니라, RC가 3~5분 안에 읽고
고객의 의료비 부담과 보장 공백을 발견하여 삼성화재 장기보험 상담으로 연결할 수 있는
'좋은 상담 소재'를 제공하는 것입니다.

[가장 중요한 편집 원칙]
1. 고객의 의료비 부담을 이해시키는 뉴스
2. 암·뇌혈관·심혈관 등 중증질환의 실제 치료비와 치료과정 부담
3. 비급여·선별급여·고액 신약·신의료기술 등 본인부담이 커질 수 있는 영역
4. 간병비·간병인 비용·가족의 돌봄 부담
5. 삼성화재 건강보험·장기보험·간병 관련 객관적인 소식
6. 보험제도는 고객 보장에 직접 영향을 줄 때만

상품·보장 뉴스는 '다른 보험사가 무엇을 팔고 있는가'보다
'고객에게 어떤 보장 공백이 생길 수 있는가'를 중심으로 선택하십시오.

[삼성화재 RC 대상 배포자료이므로 절대 제외]
- 다른 보험사의 신상품 출시·특약 출시
- 다른 보험사의 보장 강화·보장 확대
- 다른 보험사의 상품 경쟁력·인기·판매 확대
- 다른 보험사의 가입·체결 사례
- 다른 보험사의 판매 실적·시장점유율
- 다른 보험사의 배타적사용권 획득 등 상품 홍보성 기사
- 다른 보험사의 관계자 발언을 통해 상품을 긍정적으로 홍보하는 기사
- 특정 보험사의 상품을 고객에게 소개하거나 비교 대상으로 추천하는 기사
- GA 장점·성장·확대·이직·전환을 긍정적으로 다루는 기사
- 전속 RC에게 불리하거나 전속채널 약화·위기를 강조하는 기사
- 전속과 GA를 비교해 GA가 유리하다고 결론내리는 기사
- GA 수수료·조직·채널 경쟁 자체가 핵심인 기사

단, 타 보험사명이 객관적인 의료비·치료비 기사에 단순 사례로 등장한 경우에는
기사의 의료비 핵심만 남길 수 있습니다. 타 보험사의 상품 홍보 내용은 절대 요약하지 마십시오.

[메이저 언론 우선]
네이버 뉴스 검색 결과 중 조선일보, 중앙일보, 동아일보, 한겨레, 한국일보,
매일경제, 한국경제, 서울경제, 파이낸셜뉴스, 연합뉴스, 뉴시스, 뉴스1, 이데일리,
헤럴드경제, 아시아경제, 머니투데이, 서울신문, 경향신문, YTN 등 주요 언론의
기사 중 고객 의료비·보장과 직접 연결되는 내용은 우선적으로 고려하십시오.
단, 메이저 언론이라는 이유만으로 선정하지 말고 내용의 실질적 가치가 있어야 합니다.

[제외]
- 주가·주식시세
- 단순 매출·영업이익·순이익 실적
- 자동차보험·휴대폰보험·여행자보험·펫보험
- 연예·정치 일반·사건사고
- 단순 업계 인사·조직개편
- 광고성·협찬성·홍보성 콘텐츠
- 보험상품 비교·추천 콘텐츠 중 타 보험사 상품을 긍정적으로 소개하는 내용

기사에 없는 사실이나 보장 내용을 만들어내지 마십시오.
기사 원문을 그대로 복사하지 말고 요약·재구성하십시오.
source_url과 published_at은 입력값을 그대로 유지하십시오.
"""

SALES_TIP_RULES = """
[RC 세일즈 TIP 규칙]

핵심은 '뉴스 → 고객의 실제 부담 → 보장 점검 → 상담 연결'입니다.

1. 의료비 뉴스는 단순히 '병원비가 비싸졌다'로 끝내지 말고,
   어떤 치료·상황에서 고객의 본인부담이 커질 수 있는지 설명하십시오.

2. 암 뉴스:
   암 진단비 하나가 아니라 수술·항암약물치료·항암방사선치료·표적/면역치료 등
   치료 과정 전체의 비용 부담을 살펴보는 '암 통합치료비' 관점으로 연결하십시오.

3. 뇌혈관 뉴스:
   진단 이후 시술·수술·재활·치료 과정에서 발생할 수 있는 비용 부담을 살펴보는
   '뇌혈관질환 통합치료비' 관점으로 연결하십시오.

4. 심혈관 뉴스:
   진단·시술·수술·약물치료 등 치료 과정 전체의 비용 부담을 살펴보는
   '심혈관질환 통합치료비' 관점으로 연결하십시오.

5. 비급여/선별급여 뉴스:
   건강보험이 적용된다는 사실만으로 환자 부담이 낮다고 단정하지 말고,
   실제 본인부담률과 보장 공백을 확인하도록 대화하십시오.

6. 간병 뉴스:
   '간병인 사용일당'을 중심으로 표현하지 않습니다.
   '간병인 지원', '간병인지원', '간병인 비용 부담', '가족의 간병 부담'을 중심으로
   실제 고객이 입원했을 때 가족이 무엇을 감당해야 하는지 대화하게 하십시오.

7. 삼성화재 장기보험 연결:
   뉴스와 직접 연결되는 경우에만 '현재 건강보험/장기보험 보장 내역을 한번 점검해 보자'는
   자연스러운 상담으로 연결하십시오. 특정 담보 가입을 단정적으로 권유하지 마십시오.

8. 고객 공포를 과장하지 말고 객관적인 사실과 보장 점검 중심으로 작성하십시오.

9. 실제 RC가 카카오톡이나 전화에서 그대로 활용할 수 있는 자연스러운 문장으로 작성하십시오.
"""


def build_prompt(batch):
    news_text = []
    for item in batch:
        news_text.append(f"""
[NEWS_ID={item['id']}]
검색그룹: {item['group']}
메이저언론 여부: {item['is_major_news']}
제목: {item['title']}
내용: {item['description']}
출처: {item['source']}
발행일: {item['published_at']}
원문URL: {item['source_url']}
""")

    return SYSTEM_PROMPT + "\n" + SALES_TIP_RULES + """

[선별 점수]
- 고객 의료비/치료비 부담: 35점
- 상품·보장 공백과의 연결성: 25점
- 간병비/돌봄 부담: 15점
- 메이저 언론 및 출처 신뢰도: 10점
- 고객 관심도: 10점
- 보험 제도 관련성: 5점

다른 보험사 홍보성 기사와 채널 경쟁 기사는 점수와 관계없이 제외합니다.
좋은 기사가 부족하면 억지로 10개를 채우지 말고, 객관적으로 가치 있는 기사만 선택합니다.
단, 최근 뉴스가 적은 날에는 직전 48~72시간의 관련성 높은 기사까지 활용할 수 있습니다.

최종 출력 카테고리:
- policy: 보험 제도·정책 변화
- medical: 상품·보장·의료비·간병 관련 뉴스
- samsung_fire: 삼성화재 관련 뉴스

중요:
- 반드시 JSON 객체 하나만 출력하십시오.
- Markdown 코드블록을 사용하지 마십시오.
- 전체 최대 10개 기사
- policy 최대 2개
- medical 최대 7개
- samsung_fire 최대 2개
- 동일 기사 중복 금지
- 타 보험사의 상품·특약·가입·판매 홍보 내용은 출력하지 마십시오.

JSON 형식:
{
  "articles": [
    {
      "category": "policy|medical|samsung_fire",
      "title": "재구성한 제목",
      "summary": "2~3문장 요약",
      "why_it_matters": "삼성화재 RC가 고객 상담에 활용할 수 있는 의미",
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
    categories["medical"] = categories["medical"][:7]
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

    # 메이저 언론 + 의료비/간병 관련성을 우선하여 AI 입력 후보를 구성한다.
    def candidate_score(item):
        text = f"{item['title']} {item['description']}"
        score = 0
        if item.get("is_major_news"):
            score += 15
        group_score = {"medical_cost": 40, "caregiver": 35, "product": 30, "samsung_fire": 25, "policy": 15}
        score += group_score.get(item.get("group"), 0)
        if any(term in text for term in ["의료비", "치료비", "본인부담", "비급여", "간병비", "간병", "암", "뇌혈관", "심혈관"]):
            score += 20
        if is_other_insurer_promo(item):
            score -= 100
        return score

    candidates = sorted(raw_news, key=candidate_score, reverse=True)[:MAX_ANALYSIS_NEWS]
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

    # 최종 안전장치: 타 보험사 홍보성 기사와 채널 경쟁 기사는 제거.
    final_articles = []
    for article in deduplicate(restored):
        original = source_by_url.get(clean_text(article.get("source_url")))
        if original and is_other_insurer_promo(original):
            continue
        final_articles.append(article)

    categories = organize_articles(final_articles)
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
