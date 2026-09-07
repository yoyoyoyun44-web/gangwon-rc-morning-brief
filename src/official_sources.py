import json
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

RAW_FILE = "data/raw_news.json"

# 공식기관 원문 수집 대상. 페이지 구조가 바뀌어도 가능한 한
# '보도자료' 목록에서 제목/링크/날짜를 찾아오도록 범용 파서로 구성한다.
OFFICIAL_SOURCES = [
    {
        "org": "HIRA",
        "name": "건강보험심사평가원",
        "url": "https://www.hira.or.kr/bbsDummy.do?pgmid=HIRAA020041000100&brdScnBltNo=4",
        "keywords": ["의료비", "비급여", "본인부담", "진료비", "건강보험", "암", "항암", "신약", "간병", "치료", "환자", "병원"],
    },
    {
        "org": "FSS",
        "name": "금융감독원",
        "url": "https://www.fss.or.kr/fss/bbs/B0000188/list.do?menuNo=200218",
        "keywords": ["보험", "실손", "보장", "보험금", "비급여", "의료비", "간병", "소비자", "본인부담"],
    },
    {
        "org": "KNIA",
        "name": "손해보험협회",
        "url": "https://www.knia.or.kr/data/news",
        "keywords": ["보험", "실손", "비급여", "의료비", "간병", "보험금", "소비자", "보상", "본인부담"],
    },
    {
        "org": "MOHW",
        "name": "보건복지부",
        "url": "https://www.mohw.go.kr/board.es?mid=a10503000000&bid=0027",
        "keywords": ["의료비", "비급여", "건강보험", "간병", "돌봄", "암", "중증", "환자", "치료", "의료", "보건"],
    },
    {
        "org": "NHIS",
        "name": "국민건강보험공단",
        "url": "https://www.nhis.or.kr/nhis/together/wbhaea01600m01.do",
        "keywords": ["건강보험", "보험료", "본인부담", "의료비", "건강검진", "중증", "질환", "환자", "간병"],
    },
    {
        "org": "KDCA",
        "name": "질병관리청",
        "url": "https://www.kdca.go.kr/kdca/2847/subview.do",
        "keywords": ["질환", "암", "뇌혈관", "심혈관", "중증", "치료", "환자", "의료", "건강", "만성질환", "감염병"],
    },
    {
        "org": "NECA",
        "name": "한국보건의료연구원",
        "url": "https://www.neca.re.kr/lay1/program/S1T1C38/recent/list.do",
        "keywords": ["의료기술", "신의료기술", "치료", "환자", "의료", "보건의료", "임상", "비급여", "비용"],
    },
]

# 기존 브리핑의 하드 제외 규칙과 동일하게 적용한다.
CHANNEL_EXCLUDE = [
    "GA 유리", "GA 장점", "GA 확대", "GA 성장", "GA 시장점유율", "GA 이직", "GA 전환",
    "전속 이탈", "전속 경쟁력 약화", "설계사 이직", "설계사 전환", "수수료 경쟁",
]
LIFE_ASSET = [
    "연금보험", "연금저축", "연금상품", "노후자금", "목돈마련", "목돈 마련", "자산관리",
    "저축보험", "저축성보험", "적립보험", "적금", "저축", "노후자산", "은퇴자금"
]
LIFE_INSURERS = [
    "삼성생명", "한화생명", "교보생명", "신한라이프", "KB라이프", "NH농협생명",
    "미래에셋생명", "동양생명", "흥국생명", "DB생명", "ABL생명", "푸본현대생명",
    "라이나생명", "AIA생명", "메트라이프", "KDB생명", "iM라이프"
]


def clean(value):
    return re.sub(r"\s+", " ", BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)).strip()


def parse_date(text):
    text = clean(text)
    m = re.search(r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None


def same_domain(url, base):
    try:
        return urlparse(url).netloc.lower().replace("www.", "") == urlparse(base).netloc.lower().replace("www.", "")
    except Exception:
        return False


def likely_title(text):
    text = clean(text)
    if len(text) < 8 or len(text) > 180:
        return False
    bad = ["로그인", "회원가입", "개인정보처리방침", "사이트맵", "다운로드", "첨부파일", "이전", "다음"]
    return not any(x in text for x in bad)


def fetch_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RC-MorningBrief/1.0; +https://yoyoyoyun44-web.github.io/gangwon-rc-morning-brief/)"
    }
    r = requests.get(url, headers=headers, timeout=25)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or r.encoding
    return r.text


def extract_items(source, html, cutoff):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    keywords = source["keywords"]

    # 게시판의 a 태그를 중심으로 수집. 상세 페이지에서 다시 본문을 읽지 않고
    # 제목/목록 정보만 가져와 AI 단계에서 최종 검증하도록 한다.
    for a in soup.find_all("a", href=True):
        title = clean(a.get_text(" ", strip=True))
        if not likely_title(title):
            continue
        if "보도" not in title and not any(k in title for k in keywords):
            continue

        href = urljoin(source["url"], a.get("href"))
        if not same_domain(href, source["url"]):
            continue
        if href.startswith("javascript:") or href.startswith("mailto:"):
            continue

        parent_text = clean(a.parent.get_text(" ", strip=True)) if a.parent else ""
        context = clean((a.parent.parent.get_text(" ", strip=True) if a.parent and a.parent.parent else ""))
        combined_context = f"{parent_text} {context}"
        published = parse_date(combined_context)
        if published and published < cutoff:
            continue

        description = combined_context
        if len(description) > 500:
            description = description[:500]

        results.append({
            "title": title,
            "description": description,
            "source_url": href,
            "naver_url": "",
            "published_at": published.isoformat() if published else "",
            "source": urlparse(source["url"]).netloc.lower().replace("www.", ""),
            "query": f"OFFICIAL:{source['org']}",
            "group": "policy",
            "is_major_news": True,
            "origin_type": "official",
            "source_org": source["org"],
            "source_org_name": source["name"],
        })

    return results


def normalize_title(title):
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z가-힣 ]", " ", title.lower())).strip()


def is_hard_excluded(article):
    text = f"{article.get('title', '')} {article.get('description', '')}"
    if any(x in text for x in CHANNEL_EXCLUDE):
        return True
    if any(ins in text for ins in LIFE_INSURERS) and any(term in text for term in LIFE_ASSET):
        return True
    if "비만" in text and not any(x in text for x in ["뇌혈관", "뇌졸중", "뇌출혈", "뇌경색", "심혈관", "심근경색", "심장질환"]):
        return True
    return False


def dedup(existing, additions):
    all_items = list(existing)
    seen_urls = {str(x.get("source_url", "")).split("?", 1)[0].rstrip("/").lower() for x in existing if isinstance(x, dict)}
    for item in additions:
        url = str(item.get("source_url", "")).split("?", 1)[0].rstrip("/").lower()
        title = normalize_title(item.get("title", ""))
        if not url or url in seen_urls or not title:
            continue
        duplicate = False
        for old in all_items:
            old_title = normalize_title(old.get("title", ""))
            if title == old_title or SequenceMatcher(None, title, old_title).ratio() >= 0.84:
                duplicate = True
                break
        if duplicate:
            continue
        all_items.append(item)
        seen_urls.add(url)
    return all_items


def main():
    now = datetime.now().astimezone()
    cutoff = now - timedelta(hours=72 if now.weekday() in (0, 1) else 48)

    try:
        with open(RAW_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {"generated_at": now.isoformat(), "article_count": 0, "articles": []}

    if isinstance(raw, list):
        articles = raw
    else:
        articles = raw.get("articles", []) if isinstance(raw, dict) else []

    official_total = 0
    for source in OFFICIAL_SOURCES:
        try:
            html = fetch_html(source["url"])
            items = extract_items(source, html, cutoff)
            items = [x for x in items if not is_hard_excluded(x)]
            before = len(articles)
            articles = dedup(articles, items)
            added = len(articles) - before
            official_total += added
            print(f"[공식기관] {source['name']}: 후보 {len(items)}건 / 신규 {added}건")
        except Exception as e:
            print(f"[공식기관 오류] {source['name']}: {e}")

    output = {
        "generated_at": now.isoformat(),
        "article_count": len(articles),
        "official_article_count": sum(1 for x in articles if x.get("origin_type") == "official"),
        "articles": articles,
    }
    with open(RAW_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"공식기관 원문 신규 수집: {official_total}건")
    print(f"전체 원본 기사: {len(articles)}건")


if __name__ == "__main__":
    main()
