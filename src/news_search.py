import os
import json
import re
import requests
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from difflib import SequenceMatcher

NAVER_CLIENT_ID = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
NAVER_API_BASE = "https://naverapihub.apigw.ntruss.com"
NAVER_NEWS_URL = f"{NAVER_API_BASE}/search/v1/news"
OUTPUT_FILE = "data/raw_news.json"

SEARCH_GROUPS = {
    "product": [
        "실손보험 보장", "건강보험 보장", "암 치료비", "암 치료", "암 통합치료",
        "암 의료비", "뇌혈관질환 치료비", "뇌혈관질환 의료비", "심혈관질환 치료비",
        "심혈관질환 의료비", "중증질환 치료비", "고액 치료비", "건강보험 상품",
        "간편보험", "어린이보험", "장기보험 보장"
    ],
    "medical_cost": [
        "의료비 부담", "가계 의료비 부담", "비급여 의료비", "비급여 치료비",
        "건강보험 본인부담", "본인부담금 의료비", "의료비 증가", "고액 의료비",
        "신의료기술 의료비", "혁신의료기술 의료비", "중증질환 의료비", "암 의료비",
        "뇌혈관 의료비", "심혈관 의료비", "선별급여 본인부담", "고가 신약 치료비",
        "비만 의료비"
    ],
    "caregiver": [
        "간병비", "간병 비용", "간병인 비용", "간병비 부담", "간병인 지원",
        "간병보험", "가족 간병", "간병서비스", "요양병원 간병비", "요양병원 간병",
        "간병 급여화", "간병 부담 가계"
    ],
    "policy": [
        "금융감독원 보험", "금융위원회 보험", "보험 보장 제도", "실손보험 제도",
        "건강보험 제도", "보건복지부 의료비", "건강보험공단 의료비",
        "건강보험심사평가원 비급여", "비급여 관리 의료비", "간병 급여화",
        "건강보험요율", "건강보험료율", "건강보험 국고지원", "국고지원 건강보험"
    ],
    "samsung_fire": [
        "삼성화재 건강보험", "삼성화재 장기보험", "삼성화재 실손보험",
        "삼성화재 간병", "삼성화재 건강", "삼성화재 보장"
    ],
}

CHANNEL_EXCLUDE_TERMS = [
    "GA 유리", "GA 장점", "GA 확대", "GA 성장", "GA 시장점유율",
    "전속 불리", "전속 설계사 불리", "전속 이탈", "전속 경쟁력 약화",
    "GA로 이동", "GA 이직", "GA 전환", "GA 채널 확대",
    "전속채널 약화", "전속채널 위기", "GA가 유리", "GA 수수료 경쟁",
    "보험대리점 수수료", "설계사 이직", "설계사 전환"
]

NAVER_SPECIAL_CATEGORY_HOSTS = {
    "entertainment": {"m.entertain.naver.com", "entertain.naver.com"},
    "sports": {"m.sports.naver.com", "sports.naver.com", "n.sports.naver.com"},
}

SEVERE_TREATMENT_TERMS = [
    "중증질환", "중증 질환", "암", "백혈병", "혈액암", "뇌종양", "뇌졸중",
    "뇌출혈", "뇌경색", "심근경색", "심장질환", "심혈관", "뇌혈관",
    "희귀질환", "희귀 질환", "난치병", "난치질환", "난치 질환", "말기",
    "투병", "투병중", "투병 중", "항암", "방사선", "중환자실",
    "신약", "면역항암", "표적항암", "고가 치료", "고액 치료", "고액의료비",
    "고액 의료비", "치료비", "치료 비용", "의료비"
]

PERSONAL_CASE_TERMS = [
    "투병", "진단받", "진단 받", "확진", "앓고", "앓아", "치료받", "치료 받",
    "수술받", "수술 받", "입원", "항암치료", "항암 치료", "치료 중", "치료중",
    "병원비", "치료비", "의료비", "본인", "가족", "직접", "겪어", "고백",
    "투병기", "건강상태", "건강 상태", "투병 사실", "투병 소식"
]

HIGH_COST_TREATMENT_TERMS = [
    "고가 치료", "고액 치료", "고액의료비", "고액 의료비", "치료비 수천", "치료비 수억",
    "수천만원", "수억원", "천만원대 치료비", "억대 치료비", "병원비 수천", "병원비 수억",
    "치료비 부담", "의료비 부담", "고비용 치료"
]

OTHER_INSURER_NAMES = [
    "현대해상", "DB손해보험", "메리츠화재", "KB손해보험", "한화손해보험",
    "롯데손해보험", "흥국화재", "NH농협손해보험", "하나손해보험",
    "AXA손해보험", "악사손해보험", "캐롯손해보험", "삼성생명", "한화생명",
    "교보생명", "신한라이프", "KB라이프", "NH농협생명", "미래에셋생명",
    "동양생명", "흥국생명", "DB생명", "ABL생명", "푸본현대생명",
    "라이나생명", "AIA생명", "메트라이프", "처브라이프", "KDB생명", "iM라이프"
]

OTHER_INSURER_PROMO_TERMS = [
    "신상품", "상품 출시", "출시", "보장 강화", "보장확대", "보장 확대",
    "가입자", "체결", "판매", "판매 돌입", "판매 개시", "인기", "히트상품",
    "주력상품", "대표상품", "추천", "특화상품", "특화 상품", "배타적사용권",
    "배타적 사용권", "상품 경쟁력", "흥행", "완판", "판매실적", "판매 실적",
    "시장점유율"
]

LIFE_ASSET_ACCUMULATION_TERMS = [
    "연금보험", "연금 저축", "연금저축", "연금상품", "연금 자산", "노후자금",
    "목돈마련", "목돈 마련", "자산관리", "자산 관리", "저축보험", "저축성보험",
    "저축성 보험", "적립보험", "적금", "저축", "연금 준비", "노후 준비",
    "노후자산", "노후 자산", "은퇴자금", "은퇴 자금"
]

LIFE_INSURER_NAMES = [
    "삼성생명", "한화생명", "교보생명", "신한라이프", "KB라이프", "NH농협생명",
    "미래에셋생명", "동양생명", "흥국생명", "DB생명", "ABL생명", "푸본현대생명",
    "라이나생명", "AIA생명", "메트라이프", "처브라이프", "KDB생명", "iM라이프"
]

POLITICAL_COUNTERARGUMENT_TERMS = [
    "대통령 주장 반박", "대통령 발언 반박", "대통령 발언을 반박", "대통령 주장에 반박",
    "대통령 발언에 반박", "대통령 주장 사실 아니다", "대통령 발언 사실 아니다",
    "대통령 주장 틀렸다", "대통령 발언 틀렸다", "대통령 주장 오류", "대통령 발언 오류",
    "국회의원 주장 반박", "국회의원 발언 반박", "국회의원 발언을 반박", "국회의원 주장에 반박",
    "국회의원 발언에 반박", "국회의원 주장 사실 아니다", "국회의원 발언 사실 아니다",
    "국회의원 주장 틀렸다", "국회의원 발언 틀렸다", "국회의원 주장 오류", "국회의원 발언 오류",
]
POLITICAL_SUBJECT_TERMS = ["대통령", "국회의원", "의원", "국회"]
POLITICAL_REBUTTAL_TERMS = [
    "반박", "정면 반박", "재반박", "틀렸다", "사실 아니다", "사실이 아니다", "오류",
    "허위", "팩트체크", "사실과 달라", "사실과 다르다", "거짓", "왜곡"
]

TOPIC_CLUSTERS = {
    "health_insurance_finance": [
        "건강보험요율", "건강보험료율", "보험료율", "건강보험료", "국고지원", "국고 지원",
        "건강보험 재정", "건보 재정", "건강보험 재정지원", "건강보험 재정 지원",
        "건강보험 국고", "건보 국고", "국고보조", "건강보험 재정 부담"
    ],
    "noncovered_burden": [
        "비급여", "선별급여", "본인부담", "본인 부담", "비급여 의료비", "비급여 치료비"
    ],
    "caregiver_burden": [
        "간병비", "간병 비용", "간병인 비용", "간병비 부담", "간병 부담", "가족 간병", "간병 지원"
    ],
    "cancer_treatment_cost": [
        "암 치료비", "암 의료비", "암 치료", "암 통합치료", "항암", "방사선", "표적항암", "면역항암"
    ],
    "cerebrovascular_cost": [
        "뇌혈관", "뇌졸중", "뇌출혈", "뇌경색", "뇌혈관질환"
    ],
    "cardiovascular_cost": [
        "심혈관", "심근경색", "심장질환", "심혈관질환"
    ],
}

MAJOR_NEWS_DOMAINS = {
    "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr", "hankookilbo.com",
    "mk.co.kr", "hankyung.com", "sedaily.com", "fnnews.com", "newsis.com",
    "yna.co.kr", "news1.kr", "edaily.co.kr", "heraldcorp.com", "asiae.co.kr",
    "mt.co.kr", "seoul.co.kr", "khan.co.kr", "nocutnews.co.kr", "ytn.co.kr"
}


def clean_html(text):
    return BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)


def parse_date(value):
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return None


def source_from_url(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def naver_special_category(url):
    try:
        host = urlparse(url or "").netloc.lower().replace("www.", "")
        for category, hosts in NAVER_SPECIAL_CATEGORY_HOSTS.items():
            if host in hosts:
                return category
    except Exception:
        pass
    return None


def is_allowed_special_category_article(title, description, category):
    if category not in {"entertainment", "sports"}:
        return True
    combined = f"{title} {description}"
    has_severe = any(term in combined for term in SEVERE_TREATMENT_TERMS)
    has_high_cost = any(term in combined for term in HIGH_COST_TREATMENT_TERMS)
    has_personal_case = any(term in combined for term in PERSONAL_CASE_TERMS)
    return has_personal_case and (has_severe or has_high_cost)


def is_life_asset_accumulation_article(title, description):
    combined = f"{title} {description}"
    has_asset_topic = any(term in combined for term in LIFE_ASSET_ACCUMULATION_TERMS)
    has_life_insurer = any(name in combined for name in LIFE_INSURER_NAMES)
    return has_asset_topic and has_life_insurer


def is_political_counterargument_article(title, description):
    combined = f"{title} {description}"
    if any(term in combined for term in POLITICAL_COUNTERARGUMENT_TERMS):
        return True
    has_political_subject = any(term in combined for term in POLITICAL_SUBJECT_TERMS)
    has_rebuttal = any(term in combined for term in POLITICAL_REBUTTAL_TERMS)
    return has_political_subject and has_rebuttal


def is_obesity_only_article(title, description):
    combined = f"{title} {description}"
    if "비만" not in combined:
        return False
    related_terms = [
        "뇌혈관", "뇌졸중", "뇌출혈", "뇌경색", "뇌심혈관", "뇌 심혈관",
        "심혈관", "심근경색", "심장질환", "심장 질환", "관상동맥",
        "혈관질환", "혈관 질환", "뇌·심혈관"
    ]
    return not any(term in combined for term in related_terms)


def normalize_title(title):
    title = title.lower()
    title = re.sub(r"\[[^\]]+\]", " ", title)
    title = re.sub(r"\((단독|속보|종합|영상|포토|그래픽)[^)]*\)", " ", title)
    title = re.sub(r"(단독|속보|종합|영상|포토|그래픽)", " ", title)
    title = re.sub(r"[^0-9a-z가-힣 ]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def topic_cluster(title, description):
    combined = f"{title} {description}"
    for topic, terms in TOPIC_CLUSTERS.items():
        if any(term in combined for term in terms):
            return topic
    return None


def are_duplicate_topics(article_a, article_b):
    title_a = normalize_title(article_a.get("title", ""))
    title_b = normalize_title(article_b.get("title", ""))
    if not title_a or not title_b:
        return False
    if title_a == title_b:
        return True
    if SequenceMatcher(None, title_a, title_b).ratio() >= 0.82:
        return True

    topic_a = topic_cluster(article_a.get("title", ""), article_a.get("description", ""))
    topic_b = topic_cluster(article_b.get("title", ""), article_b.get("description", ""))
    if topic_a and topic_a == topic_b:
        return True

    stopwords = {"관련", "대한", "대해", "정부", "보험", "건강", "질환", "의료", "기사", "전망", "논란"}
    words_a = {w for w in title_a.split() if len(w) >= 2 and w not in stopwords}
    words_b = {w for w in title_b.split() if len(w) >= 2 and w not in stopwords}
    if words_a and words_b:
        overlap = len(words_a & words_b) / max(1, min(len(words_a), len(words_b)))
        if overlap >= 0.75:
            return True
    return False


def is_other_insurer_promotional_article(title, description):
    combined = f"{title} {description}"
    if not any(name in combined for name in OTHER_INSURER_NAMES):
        return False
    if not any(term in combined for term in OTHER_INSURER_PROMO_TERMS):
        return False
    medical_context = [
        "의료비", "치료비", "비급여", "본인부담", "간병비", "간병", "치료", "환자",
        "질환", "건강보험", "의료", "병원", "신약", "암", "뇌혈관", "심혈관"
    ]
    return not any(term in combined for term in medical_context)


def search_naver(query):
    headers = {
        "X-NCP-APIGW-API-KEY-ID": NAVER_CLIENT_ID,
        "X-NCP-APIGW-API-KEY": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": 100, "start": 1, "sort": "date"}
    response = requests.get(NAVER_NEWS_URL, headers=headers, params=params, timeout=30)
    if response.status_code != 200:
        print(f"NAVER API 오류 HTTP {response.status_code}: {response.text}")
        response.raise_for_status()
    return response.json()


def deduplicate_topics(collected):
    result = []
    duplicates = 0

    def priority(article):
        dt = parse_date(article.get("published_at", ""))
        timestamp = dt.timestamp() if dt else 0
        major = 1 if article.get("is_major_news") else 0
        return (major, timestamp)

    candidates = sorted(collected, key=priority, reverse=True)
    for article in candidates:
        if any(are_duplicate_topics(article, existing) for existing in result):
            duplicates += 1
            print(f"  [중복 제외] 유사 주제 기사: {article.get('title', '')}")
            continue
        result.append(article)

    group_rank = {"product": 1, "medical_cost": 2, "caregiver": 3, "samsung_fire": 4, "policy": 5}
    result.sort(key=lambda x: (
        group_rank.get(x.get("group"), 99),
        -(parse_date(x.get("published_at", "")).timestamp() if parse_date(x.get("published_at", "")) else 0)
    ))
    print(f"유사 주제 중복 제거: {duplicates}개")
    return result


def main():
    now = datetime.now().astimezone()
    weekday = now.weekday()
    hours = 72 if weekday in (0, 1) else 48
    cutoff = now - timedelta(hours=hours)
    collected = []
    seen_urls = set()

    print("=" * 60)
    print("강원영업단 RC Morning Brief")
    print("NAVER API HUB 뉴스 수집 시작")
    print(f"수집 기준: 최근 {hours}시간")
    print("검색 우선순위: 상품/보장 > 의료비 부담 > 간병 > 삼성화재 > 제도")
    print("타 보험사 상품 홍보성 기사 및 GA/전속 채널경쟁 기사 제외")
    print("생명보험사 연금·적금·저축·목돈마련·자산관리 기사 제외")
    print("비만: 뇌·심혈관질환과의 연관성이 주된 기사만 허용")
    print("대통령/국회의원 주장 반박 목적 기사 제외")
    print("유사 주제 중복 기사 제거")
    print("네이버 엔터/스포츠: 본인 중증질환·고가치료 사례만 허용")
    print("=" * 60)

    for group, queries in SEARCH_GROUPS.items():
        print(f"\n### {group}")
        for query in queries:
            print(f"[검색] {query}")
            try:
                data = search_naver(query)
            except Exception as e:
                print(f"[오류] {e}")
                continue

            items = data.get("items", [])
            print(f"  → {len(items)}개 결과")

            for item in items:
                title = clean_html(item.get("title", ""))
                description = clean_html(item.get("description", ""))
                original_url = item.get("originallink") or item.get("link") or ""
                naver_url = item.get("link") or ""
                published_raw = item.get("pubDate", "")
                published = parse_date(published_raw)
                source = source_from_url(original_url)

                if not title or not original_url or original_url in seen_urls:
                    continue
                if published and published < cutoff:
                    continue

                category = naver_special_category(original_url) or naver_special_category(naver_url)
                if category and not is_allowed_special_category_article(title, description, category):
                    print(f"  [제외] 네이버 {category} 영역 비관련 기사: {title}")
                    continue

                if is_life_asset_accumulation_article(title, description):
                    print(f"  [제외] 생명보험사 목돈마련/자산관리 기사: {title}")
                    continue

                if is_obesity_only_article(title, description):
                    print(f"  [제외] 비만 단독/비관련 기사: {title}")
                    continue

                if is_political_counterargument_article(title, description):
                    print(f"  [제외] 정치인 주장 반박 목적 기사: {title}")
                    continue

                combined = f"{title} {description}"
                if any(term in combined for term in CHANNEL_EXCLUDE_TERMS):
                    continue
                if is_other_insurer_promotional_article(title, description):
                    print(f"  [제외] 타 보험사 홍보/상품 기사: {title}")
                    continue

                seen_urls.add(original_url)
                collected.append({
                    "title": title,
                    "description": description,
                    "source_url": original_url,
                    "naver_url": naver_url,
                    "published_at": published.isoformat() if published else published_raw,
                    "source": source,
                    "query": query,
                    "group": group,
                    "is_major_news": source in MAJOR_NEWS_DOMAINS,
                })

    collected = deduplicate_topics(collected)

    output = {
        "generated_at": now.isoformat(),
        "article_count": len(collected),
        "articles": collected,
    }

    os.makedirs("data", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"뉴스 {len(collected)}개 수집 완료")
    print(f"메이저 언론 기사: {sum(1 for x in collected if x.get('is_major_news'))}개")
    print(f"파일 생성: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
