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

SEARCH_QUERIES = [
    "보험 제도", "금융감독원 보험", "금융위원회 보험", "손해보험협회",
    "실손보험", "건강보험", "간병보험", "간병인", "의료비", "비급여",
    "신의료기술", "혁신의료기술", "암 치료", "뇌혈관질환", "심혈관질환",
    "중증질환", "건강보험공단", "건강보험심사평가원", "보건복지부",
    "삼성화재 건강보험", "삼성화재 장기보험", "삼성화재 실손보험", "삼성화재 간병"
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
    print("=" * 60)

    for query in SEARCH_QUERIES:
        print(f"\n[검색] {query}")
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

            seen_urls.add(original_url)
            collected.append({
                "title": title,
                "description": description,
                "source_url": original_url,
                "naver_url": naver_url,
                "published_at": published.isoformat() if published else published_raw,
                "source": source_from_url(original_url),
                "query": query,
            })

    collected.sort(key=lambda x: x.get("published_at", ""), reverse=True)

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
