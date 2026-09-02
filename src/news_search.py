import os
import json
import requests
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

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
        "뇌혈관 의료비", "심혈관 의료비", "선별급여 본인부담", "고가 신약 치료비"
    ],
    "caregiver": [
        "간병비", "간병 비용", "간병인 비용", "간병비 부담", "간병인 지원",
        "간병보험", "가족 간병", "간병서비스", "요양병원 간병비", "요양병원 간병",
        "간병 급여화", "간병 부담 가계"
    ],
    "policy": [
        "금융감독원 보험", "금융위원회 보험", "보험 보장 제도", "실손보험 제도",
        "건강보험 제도", "보건복지부 의료비", "건강보험공단 의료비",
        "건강보험심사평가원 비급여", "비급여 관리 의료비", "간병 급여화"
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

    group_rank = {"product": 1, "medical_cost": 2, "caregiver": 3, "samsung_fire": 4, "policy": 5}
    # 그룹 우선순위는 유지하되, 같은 그룹에서는 최신 뉴스가 먼저 오도록 정렬한다.
    collected.sort(
        key=lambda x: (
            group_rank.get(x.get("group"), 99),
            -((parse_date(x.get("published_at")) or datetime.min.replace(tzinfo=None)).timestamp())
            if parse_date(x.get("published_at")) and parse_date(x.get("published_at")).tzinfo else 0
        )
    )

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
