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

# 강원영업단 RC Morning Brief의 우선순위에 맞춘 검색어
# 1순위: 상품/보장  2순위: 의료비 부담  3순위: 간병 비용/지원  4순위: 보험제도
SEARCH_GROUPS = {
    "product": [
        "실손보험", "실손보험 보장", "실손보험 개편", "건강보험 보장",
        "암 치료비", "암 치료", "암 통합치료", "뇌혈관질환 치료비",
        "심혈관질환 치료비", "중증질환 치료비", "건강보험 상품",
        "간편보험", "어린이보험", "장기보험 보장"
    ],
    "medical_cost": [
        "의료비 부담", "비급여", "비급여 의료비", "건강보험 본인부담",
        "본인부담금", "의료비 증가", "고액 의료비", "신의료기술",
        "혁신의료기술", "중증질환 의료비", "암 의료비", "뇌혈관 의료비",
        "심혈관 의료비"
    ],
    "caregiver": [
        "간병비", "간병 비용", "간병인 비용", "간병인 지원",
        "간병보험", "간병 부담", "가족 간병", "간병서비스",
        "간병인", "요양병원 간병비", "간병비 부담"
    ],
    "policy": [
        "금융감독원 보험", "금융위원회 보험", "보험 보장 제도",
        "실손보험 제도", "건강보험 제도", "보건복지부 의료비",
        "건강보험공단 의료비", "건강보험심사평가원 비급여"
    ],
    "samsung_fire": [
        "삼성화재 건강보험", "삼성화재 장기보험", "삼성화재 실손보험",
        "삼성화재 간병", "삼성화재 건강", "삼성화재 보장"
    ],
}

# 전속/GA 채널 경쟁을 다루는 기사는 Morning Brief의 목적과 맞지 않으므로
# 검색 단계에서도 가급적 배제한다. 상품·보장·고객 부담과 직접 연결되는 경우는
# AI 단계에서 다시 판단한다.
CHANNEL_EXCLUDE_TERMS = [
    "GA 유리", "GA 장점", "GA 확대", "GA 성장", "GA 시장점유율",
    "전속 불리", "전속 설계사 불리", "전속 이탈", "전속 경쟁력 약화",
    "GA로 이동", "GA 이직", "GA 전환", "GA 채널 확대",
    "전속채널 약화", "전속채널 위기", "GA가 유리"
]


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
    hours = 72 if weekday in (0, 1) else 24
    cutoff = now - timedelta(hours=hours)
    collected = []
    seen_urls = set()

    print("=" * 60)
    print("강원영업단 RC Morning Brief")
    print("NAVER API HUB 뉴스 수집 시작")
    print(f"수집 기준: 최근 {hours}시간")
    print("검색 우선순위: 상품/보장 > 의료비 부담 > 간병 > 제도")
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

                if not title or not original_url or original_url in seen_urls:
                    continue
                if published and published < cutoff:
                    continue

                combined = f"{title} {description}"
                if any(term in combined for term in CHANNEL_EXCLUDE_TERMS):
                    continue

                seen_urls.add(original_url)
                collected.append({
                    "title": title,
                    "description": description,
                    "source_url": original_url,
                    "naver_url": naver_url,
                    "published_at": published.isoformat() if published else published_raw,
                    "source": source_from_url(original_url),
                    "query": query,
                    "group": group,
                })

    # 검색 그룹 우선순위를 유지하면서 최신순 정렬
    group_rank = {"product": 1, "medical_cost": 2, "caregiver": 3, "samsung_fire": 4, "policy": 5}
    collected.sort(
        key=lambda x: (
            group_rank.get(x.get("group"), 99),
            x.get("published_at", "")
        ),
        reverse=False,
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
    print(f"파일 생성: {OUTPUT_FILE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
