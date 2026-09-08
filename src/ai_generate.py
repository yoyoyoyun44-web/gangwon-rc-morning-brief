import json
import os
import re
import time
from pathlib import Path

from google import genai

INPUT_FILE = Path("data/raw_news.json")
OUTPUT_FILE = Path("data/news.json")
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.6-flash"
MAX_ANALYSIS_NEWS = 80
BATCH_SIZE = 20
MAX_RETRIES_503 = 2
RETRY_DELAY_503 = 20
TITLE_ALIGNMENT_MIN_SCORE = 65

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
            "origin_type": clean_text(news.get("origin_type")) or "news",
            "source_org": clean_text(news.get("source_org")),
            "source_org_name": clean_text(news.get("source_org_name")),
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

[공식기관 자료 우선 원칙]
- 출처가 건강보험심사평가원, 금융감독원, 손해보험협회, 보건복지부, 국민건강보험공단,
  질병관리청, 한국보건의료연구원 등 공식기관으로 표시된 입력은 신뢰도 높은 원자료입니다.
- 공식기관 자료 중 고객 의료비·비급여·본인부담·간병·중증질환 치료비·보험제도와 직접 관련된 자료는
  일반 뉴스보다 우선적으로 검토하십시오.
- 단, 공식기관이라는 이유만으로 무조건 카드로 만들지 말고 RC 상담 활용성이 있어야 합니다.

[기사-카드뉴스 제목 상관관계 원칙]
- 카드뉴스 제목은 반드시 연결된 원문 기사의 '핵심 주제'를 반영해야 합니다.
- 원문 제목과 본문에서 가장 먼저·크게 다뤄지는 이슈를 핵심 주제로 판단하십시오.
- 기사 후반부에 보조적으로 등장한 수치, 사례, 한 문장을 제목의 중심 소재로 끌어올리지 마십시오.
- 원문 제목이 '영상의학·정형외과 전문의 쏠림'인데 본문 후반에 '국민 의료비 225조원'이 언급되었다면,
  '국민 의료비 225조원'을 카드뉴스 제목의 핵심으로 만들면 안 됩니다.
- 카드뉴스 제목은 원문 제목의 핵심 문제·현상·대상 중 적어도 하나를 의미적으로 유지해야 합니다.
- 제목을 더 이해하기 쉽게 재구성할 수는 있지만, 기사에서 가장 비중이 낮은 보조 수치를 중심 제목으로 바꾸지 마십시오.
- 원문 제목과 제공된 내용만으로 핵심 주제를 명확하게 판단할 수 없다면 해당 기사를 선택하지 마십시오.

[다주제·종합 기사에 대한 추가 제외 원칙]
- 하나의 기사 안에서 여러 주제나 사례를 함께 다루는 종합·묶음형 기사는 엄격하게 판단합니다.
- 우리가 선택하려는 핵심 주제가 기사 전체 내용에서 1/3 미만만 차지한다면 제외합니다.
- 핵심 주제가 기사 전체 내용의 1/3 이상을 차지하더라도, 그 주제가 기사에서 첫 번째로 제시된 주제 또는 사실상 메인 주제가 아니라면 제외합니다.
- 기사 중간이나 후반부에 관련 키워드가 잠깐 등장하는 것만으로는 선정하지 않습니다.
- 제목에 관련 키워드가 들어 있더라도 본문에서 해당 주제가 부수적으로만 다뤄지면 제외합니다.
- 여러 주제를 다루는 기사에서는 '관련 키워드가 있는가'보다 '이 기사의 첫 번째/메인 주제'를 우선 판단합니다.
- 같은 주제를 여러 기사에서 반복 보도한 경우에는 가장 직접적이고 핵심적인 기사 1개만 남깁니다.
- 입력값에 제공된 제목·내용만으로 기사 전체의 비중을 신뢰성 있게 판단할 수 없다면 과도하게 추정하지 말고 핵심 주제가 명확한 기사만 선택합니다.

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
2. 암 뉴스: 암 진단비 하나가 아니라 수술·항암약물치료·항암방사선치료·표적/면역치료 등
   치료 과정 전체의 비용 부담을 살펴보는 '암 통합치료비' 관점으로 연결하십시오.
3. 뇌혈관 뉴스: 진단 이후 시술·수술·재활·치료 과정에서 발생할 수 있는 비용 부담을 살펴보는
   '뇌혈관질환 통합치료비' 관점으로 연결하십시오.
4. 심혈관 뉴스: 진단·시술·수술·약물치료 등 치료 과정 전체의 비용 부담을 살펴보는
   '심혈관질환 통합치료비' 관점으로 연결하십시오.
5. 비급여/선별급여 뉴스: 건강보험이 적용된다는 사실만으로 환자 부담이 낮다고 단정하지 말고,
   실제 본인부담률과 보장 공백을 확인하도록 대화하십시오.
6. 간병 뉴스: '간병인 사용일당'을 중심으로 표현하지 않습니다.
   '간병인 지원', '간병인지원', '간병인 비용 부담', '가족의 간병 부담'을 중심으로
   실제 고객이 입원했을 때 가족이 무엇을 감당해야 하는지 대화하게 하십시오.
7. 삼성화재 장기보험 연결: 뉴스와 직접 연결되는 경우에만
   '현재 건강보험/장기보험 보장 내역을 한번 점검해 보자'는 자연스러운 상담으로 연결하십시오.
8. 고객 공포를 과장하지 말고 객관적인 사실과 보장 점검 중심으로 작성하십시오.
9. 실제 RC가 카카오톡이나 전화에서 그대로 활용할 수 있는 자연스러운 문장으로 작성하십시오.
"""


def build_prompt(batch):
    news_text = []
    for item in batch:
        news_text.append(f"""
[NEWS_ID={item['id']}]
검색그룹: {item['group']}
공식기관 자료 여부: {item.get('origin_type') == 'official'}
공식기관: {item.get('source_org_name', '')}
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

공식기관 자료가 고객 의료비·비급여·본인부담·간병·중증질환 치료비·보험제도와 직접 관련되면 우선 고려합니다.
다른 보험사 홍보성 기사와 채널 경쟁 기사는 점수와 관계없이 제외합니다.
좋은 기사가 부족하면 억지로 채우지 말고, 객관적으로 가치 있는 기사만 선택합니다.
서로 다른 핵심 주제는 균형 있게 배분하고, 같은 핵심 주제에서도 실질적으로 다른 기사라면 2개까지 허용합니다.

[기사-제목 상관관계 자기검수]
각 기사에 대해 출력하기 전에 반드시 스스로 검수하십시오.
① 원문 제목에서 가장 중요한 문제·현상·대상이 무엇인지 판단합니다.
② 기사 내용에서 실제로 가장 비중 있게 다뤄지는 핵심 주제를 판단합니다.
③ 재구성한 카드뉴스 제목이 ①과 ②를 모두 반영하는지 확인합니다.
④ 제목이 기사 후반부의 보조 수치·사례·한 문장만 가져와 만든 것은 아닌지 확인합니다.
⑤ 제목과 원문 핵심 주제가 다르면 해당 기사를 출력하지 않습니다.

title_alignment_score는 0~100점으로 평가하십시오.
- 90~100: 원문 제목과 기사 핵심 주제가 거의 동일하고 제목이 정확히 반영함
- 80~89: 표현은 재구성했지만 핵심 주제와 대상이 명확히 일치함
- 60~79: 관련성은 있으나 제목이 기사 일부 내용에 치우침
- 0~59: 핵심 주제가 다르거나 기사 후반부의 보조 내용을 중심으로 제목을 만듦
65점 미만은 반드시 출력하지 마십시오.

[다주제 기사 최종 검증]
① 이 기사의 핵심 주제가 무엇인가?
② 우리가 선택하려는 보험·의료비 관련 주제가 기사 전체의 1/3 이상인가?
③ 1/3 이상이라면 그 주제가 기사에서 첫 번째로 제시된 주제이거나 사실상 메인 주제인가?
④ 관련 내용이 기사 중간/후반부의 일부 사례에 불과한 것은 아닌가?
②가 아니면 무조건 제외합니다. ②를 충족해도 ③이 아니면 무조건 제외합니다.

최종 출력 카테고리:
- policy: 보험 제도·정책 변화
- medical: 상품·보장·의료비·간병 관련 뉴스
- samsung_fire: 삼성화재 관련 뉴스

중요:
- 반드시 JSON 객체 하나만 출력하십시오.
- Markdown 코드블록을 사용하지 마십시오.
- 전체 최대 14개 기사
- policy 최대 2개
- medical 최대 10개
- samsung_fire 최대 2개
- 동일 기사 중복 금지
- 동일 기사만 중복 제거하고, 서로 다른 관점·사례·정책 변화는 같은 핵심 주제라도 최대 2개까지 허용합니다.
- 타 보험사의 상품·특약·가입·판매 홍보 내용은 출력하지 마십시오.

JSON 형식:
{
  "articles": [
    {
      "category": "policy|medical|samsung_fire",
      "source_title": "입력된 원문 기사 제목",
      "core_topic": "원문 기사의 핵심 주제",
      "title_topic": "재구성한 카드뉴스 제목이 다루는 핵심 주제",
      "title_alignment_score": 0,
      "title_alignment_pass": true,
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


def analyze_batch(batch, batch_number, allow_split=True):
    prompt = build_prompt(batch)
    for attempt in range(MAX_RETRIES_503 + 1):
        try:
            print(f"  Gemini 요청 (배치 {batch_number}, 시도 {attempt + 1}/{MAX_RETRIES_503 + 1}, {len(batch)}개)")
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
            if allow_split and len(batch) > 5:
                mid = len(batch) // 2
                print(f"  [배치 복구] JSON/응답 오류로 {len(batch)}개 배치를 {mid}개 + {len(batch)-mid}개로 재시도합니다.")
                left = analyze_batch(batch[:mid], f"{batch_number}A", allow_split=False)
                time.sleep(2)
                right = analyze_batch(batch[mid:], f"{batch_number}B", allow_split=False)
                return left + right
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
    article["source_title"] = original["title"]
    article["origin_type"] = original.get("origin_type", "news")
    article["source_org"] = original.get("source_org", "")
    article["source_org_name"] = original.get("source_org_name", "")
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


def validate_title_alignment(articles, source_by_url):
    """생성된 카드뉴스 제목이 실제 원문 기사 핵심 주제와 일치하는지 2차 검수한다."""
    candidates = []
    for article in articles:
        url = clean_text(article.get("source_url"))
        original = source_by_url.get(url)
        if not original:
            continue
        candidates.append({
            "source_url": url,
            "source_title": original["title"],
            "source_description": original["description"],
            "generated_title": clean_text(article.get("title")),
            "summary": clean_text(article.get("summary")),
            "core_topic": clean_text(article.get("core_topic")),
        })

    if not candidates:
        return []

    prompt = """
당신은 뉴스 편집 품질검수자입니다.
아래 카드뉴스 후보 각각에 대해 '원문 기사 제목/내용의 핵심 주제'와 '카드뉴스 제목'이 실제로 같은 기사를 설명하는지 검수하십시오.

가장 중요한 기준:
- 원문 제목의 핵심 문제·현상·대상이 카드뉴스 제목에도 의미적으로 유지되어야 합니다.
- 원문 본문 후반부의 보조 수치나 사례가 기사 전체의 핵심인 것처럼 제목에 확대되어서는 안 됩니다.
- 단순 키워드 하나가 겹친다고 통과시키지 말고, 문제의 중심과 대상이 같은지 판단하십시오.
- 표현을 자연스럽게 바꾸거나 압축한 것은 허용하지만, 기사 전체의 메인 주제를 다른 주제로 바꾼 것은 불허합니다.

각 항목을 다음 JSON으로 평가하십시오.
{
  "checks": [
    {
      "source_url": "...",
      "pass": true,
      "score": 0,
      "reason": "한 문장 이유"
    }
  ]
}

score 기준:
90~100 = 핵심 주제와 대상이 사실상 동일
80~89 = 표현은 달라도 핵심 주제가 명확히 동일
60~79 = 일부 관련되지만 제목이 기사 일부에 치우침
0~59 = 다른 주제이거나 보조 정보를 메인 제목으로 왜곡
65점 미만은 pass=false입니다.
"""

    payload = json.dumps(candidates, ensure_ascii=False)
    for attempt in range(MAX_RETRIES_503 + 1):
        try:
            print(f"  제목-기사 상관관계 2차 검수 (시도 {attempt + 1}/{MAX_RETRIES_503 + 1})")
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt + "\n\n검수 대상:\n" + payload)
            text = (response.text or "").strip()
            if text.startswith("```"):
                text = text.replace("```json", "", 1).replace("```", "").strip()
            result = json.loads(text)
            checks = result.get("checks", [])
            if not isinstance(checks, list):
                raise ValueError("title alignment checks가 배열이 아닙니다.")
            by_url = {clean_text(item.get("source_url")): item for item in checks}
            validated = []
            rejected = 0
            for article in articles:
                url = clean_text(article.get("source_url"))
                check = by_url.get(url)
                model_pass = article.get("title_alignment_pass") is True
                try:
                    model_score = int(article.get("title_alignment_score", 0))
                except (TypeError, ValueError):
                    model_score = 0
                final_score = min(model_score, int(check.get("score", 0))) if check else 0
                final_pass = bool(check and check.get("pass") is True and model_pass and final_score >= TITLE_ALIGNMENT_MIN_SCORE)
                article["title_alignment_score"] = final_score
                article["title_alignment_pass"] = final_pass
                article["title_alignment_reason"] = clean_text(check.get("reason")) if check else "2차 상관관계 검수 결과가 없습니다."
                if final_pass:
                    validated.append(article)
                else:
                    rejected += 1
                    print(f"  [제목-기사 불일치 제외] {clean_text(article.get('title'))} / {article.get('title_alignment_reason')}")
            print(f"  → 상관관계 검수 완료: 통과 {len(validated)}개 / 제외 {rejected}개")
            return validated
        except Exception as e:
            error_text = str(e)
            if "429" in error_text or "RESOURCE_EXHAUSTED" in error_text:
                raise RuntimeError("제목-기사 상관관계 검수 Gemini 쿼터가 초과되어 안전하게 중단합니다.") from e
            if "503" in error_text or "UNAVAILABLE" in error_text:
                if attempt < MAX_RETRIES_503:
                    time.sleep(RETRY_DELAY_503)
                    continue
            raise RuntimeError(f"제목-기사 상관관계 검수 실패: {error_text}") from e
    return []


MEDICAL_TOPIC_CLUSTERS = {
    "health_insurance_finance": ["건강보험요율", "건강보험료율", "보험료율", "건강보험료", "국고지원", "국고 지원", "건강보험 재정", "건보 재정", "건강보험 국고", "국고보조"],
    "noncovered_burden": ["비급여", "선별급여", "본인부담", "본인 부담", "비급여 의료비", "비급여 치료비"],
    "caregiver_burden": ["간병비", "간병 비용", "간병인 비용", "간병비 부담", "간병 부담", "가족 간병", "간병 지원"],
    "cancer_treatment_cost": ["암 치료비", "암 의료비", "암 치료", "암 통합치료", "항암", "방사선", "표적항암", "면역항암"],
    "cerebrovascular_cost": ["뇌혈관", "뇌졸중", "뇌출혈", "뇌경색", "뇌혈관질환"],
    "cardiovascular_cost": ["심혈관", "심근경색", "심장질환", "심혈관질환"],
}


def infer_medical_topic(article):
    text = " ".join(clean_text(article.get(k)) for k in ("source_title", "title", "summary", "core_topic"))
    for topic, terms in MEDICAL_TOPIC_CLUSTERS.items():
        if any(term in text for term in terms):
            return topic
    return "other"


def select_balanced_medical(articles, limit=10, per_topic=2):
    selected = []
    counts = {}
    for article in articles:
        topic = infer_medical_topic(article)
        if counts.get(topic, 0) >= per_topic:
            continue
        selected.append(article)
        counts[topic] = counts.get(topic, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def normalize_category(article):
    raw = clean_text(article.get("category")).lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "policy": "policy", "policies": "policy", "제도": "policy", "정책": "policy", "보험제도": "policy", "보험_제도": "policy",
        "medical": "medical", "medicine": "medical", "health": "medical", "의료": "medical", "의료비": "medical", "보장": "medical", "간병": "medical", "상품": "medical",
        "samsung_fire": "samsung_fire", "samsungfire": "samsung_fire", "samsung": "samsung_fire", "삼성화재": "samsung_fire"
    }
    if raw in aliases:
        return aliases[raw]

    text = " ".join(clean_text(article.get(k)) for k in ("source_title", "title", "summary", "core_topic"))
    if article.get("origin_type") == "official":
        policy_terms = ["제도", "정책", "개편", "개정", "보험료", "건강보험", "보건복지", "금융감독", "비급여 관리"]
        if any(term in text for term in policy_terms):
            return "policy"
    if "삼성화재" in text:
        return "samsung_fire"
    if any(term in text for term in ["의료비", "치료비", "비급여", "본인부담", "간병", "암", "뇌혈관", "심혈관", "건강보험"]):
        return "medical"
    return "policy" if article.get("group") == "policy" else "medical"


def organize_articles(articles):
    categories = {"policy": [], "medical": [], "samsung_fire": []}
    for article in articles:
        category = normalize_category(article)
        if category in categories and article.get("source_url"):
            article["category"] = category
            categories[category].append(article)

    # 공식기관 자료는 최종 조직화 단계에서도 우선한다.
    categories["policy"] = sorted(categories["policy"], key=lambda x: (x.get("origin_type") != "official", not x.get("is_major_news", False)))[:2]
    categories["medical"] = select_balanced_medical(categories["medical"], limit=10, per_topic=2)
    categories["samsung_fire"] = categories["samsung_fire"][:2]
    return categories


def make_sales_points(categories):
    points = []
    for label, key in (("상품·보장/의료비", "medical"), ("삼성화재 소식", "samsung_fire"), ("제도 동향", "policy")):
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

    def candidate_score(item):
        text = f"{item['title']} {item['description']}"
        score = 0
        if item.get("origin_type") == "official":
            score += 45
        if item.get("is_major_news"):
            score += 15
        group_score = {"medical_cost": 40, "caregiver": 35, "product": 30, "samsung_fire": 25, "policy": 15}
        score += group_score.get(item.get("group"), 0)
        if any(term in text for term in ["의료비", "치료비", "본인부담", "비급여", "간병비", "간병", "암", "뇌혈관", "심혈관"]):
            score += 20
        if is_other_insurer_promo(item):
            score -= 100
        return score

    official_candidates = [x for x in raw_news if x.get("origin_type") == "official" and not is_other_insurer_promo(x)]
    general_candidates = [x for x in raw_news if x.get("origin_type") != "official" and not is_other_insurer_promo(x)]
    official_candidates = sorted(official_candidates, key=candidate_score, reverse=True)
    general_candidates = sorted(general_candidates, key=candidate_score, reverse=True)
    # 공식기관 후보를 먼저 확보하고, 나머지는 일반 뉴스로 채워 분석 폭을 유지한다.
    candidates = (official_candidates[:12] + general_candidates)[:MAX_ANALYSIS_NEWS]
    print(f"공식기관 후보 우선 확보: {min(len(official_candidates), 12)}개")
    print(f"AI 분석 대상: {len(candidates)}개")

    if not candidates:
        output = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "categories": {"policy": [], "medical": [], "samsung_fire": []}, "sales_points": [], "article_count": 0}
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT_FILE.open("w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return

    source_by_url = {item["source_url"]: item for item in candidates}
    analyzed = []

    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start:start + BATCH_SIZE]
        batch_number = (start // BATCH_SIZE) + 1
        analyzed.extend(analyze_batch(batch, batch_number, allow_split=True))
        if start + BATCH_SIZE < len(candidates):
            time.sleep(3)

    restored = []
    for article in analyzed:
        fixed = restore_metadata(article, source_by_url)
        if fixed:
            restored.append(fixed)

    restored = deduplicate(restored)
    restored = validate_title_alignment(restored, source_by_url)

    final_articles = []
    for article in restored:
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
    print("=" * 60)


if __name__ == "__main__":
    main()
