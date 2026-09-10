import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from google import genai

INPUT_FILE = Path("data/raw_news.json")
OUTPUT_FILE = Path("data/news.json")
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-3.6-flash"
MAX_ANALYSIS_NEWS = 80
BATCH_SIZE = 20
MAX_RETRIES = 2
RETRY_DELAY = 8
MIN_SALES_SCORE = 70

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다.")
client = genai.Client(api_key=API_KEY)

MAJOR_NEWS_DOMAINS = {
    "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr", "hankookilbo.com",
    "mk.co.kr", "hankyung.com", "sedaily.com", "fnnews.com", "newsis.com", "yna.co.kr",
    "news1.kr", "edaily.co.kr", "heraldcorp.com", "asiae.co.kr", "mt.co.kr", "seoul.co.kr",
    "khan.co.kr", "nocutnews.co.kr", "ytn.co.kr"
}

EXCLUDE_TERMS = [
    "기부", "기부금", "기부활동", "기부 활동", "후원", "후원금", "후원 활동", "성금", "기탁", "나눔", "모금",
    "의료인력", "의료 인력", "의료진 채용", "의료인력 채용", "간호인력", "간호 인력", "의사 부족",
    "인력 공백", "인력 확충", "채용 절차", "행정사무감사", "도의원", "시의원", "국회의원", "도지사",
    "시의회", "도의회", "군의회", "예산 감액", "예산 증액", "자동차보험", "여행보험", "반려동물보험",
    "휴대폰보험", "연금보험", "연금저축", "연금상품", "노후자금", "노후자산", "은퇴자금", "목돈마련",
    "저축보험", "저축성보험", "적립보험", "적금", "자산관리"
]

OTHER_INSURER_NAMES = [
    "현대해상", "DB손해보험", "메리츠화재", "KB손해보험", "한화손해보험", "롯데손해보험",
    "흥국화재", "NH농협손해보험", "하나손해보험", "AXA손해보험", "악사손해보험", "캐롯손해보험",
    "삼성생명", "한화생명", "교보생명", "신한라이프", "KB라이프", "NH농협생명", "미래에셋생명",
    "동양생명", "흥국생명", "DB생명", "ABL생명", "푸본현대생명", "라이나생명", "AIA생명",
    "메트라이프", "처브라이프", "KDB생명", "iM라이프"
]
OTHER_INSURER_PROMO_TERMS = [
    "신상품", "상품 출시", "출시", "보장 강화", "보장확대", "보장 확대", "가입자", "체결", "판매",
    "판매 돌입", "판매 개시", "인기", "히트상품", "주력상품", "대표상품", "추천", "특화상품",
    "배타적사용권", "배타적 사용권", "상품 경쟁력", "흥행", "완판", "판매실적", "판매 실적", "시장점유율"
]

MEDICAL_VALUE_TERMS = [
    "의료비", "치료비", "수술비", "본인부담", "비급여", "간병비", "간병 비용", "간병인", "간병인지원",
    "간병인 지원", "가족 간병", "간병 부담", "고액 치료", "고액 약제", "고가 치료", "신약", "보험급여",
    "건강보험 보장", "치료 부담", "의료비 부담", "치료비 부담", "환자 부담", "본인 부담"
]
DISEASE_TERMS = [
    "암", "항암", "표적항암", "면역항암", "뇌혈관", "뇌졸중", "뇌출혈", "뇌경색", "심혈관", "심근경색",
    "심장질환", "희귀질환", "희귀·난치", "희귀 난치", "난치질환", "중증질환", "중증·희귀", "중증난치"
]


def clean(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\n", " ").replace("\r", " ").strip())


def article_text(a):
    return clean(" ".join(str(a.get(k, "")) for k in (
        "title", "description", "source", "publisher", "source_title", "core_topic", "summary", "why_it_matters", "sales_tip"
    ))).lower()


def has_any(s, terms):
    return any(t.lower() in s for t in terms)


def clearly_excluded(a):
    s = article_text(a)
    if has_any(s, EXCLUDE_TERMS):
        return True
    insurer = has_any(s, OTHER_INSURER_NAMES)
    promo = has_any(s, OTHER_INSURER_PROMO_TERMS)
    if insurer and promo:
        # 경쟁사 상품홍보라도 실제 의료비·환자부담 이슈가 핵심이면 AI가 다시 판단할 수 있도록 허용
        if not has_any(s, MEDICAL_VALUE_TERMS):
            return True
    celebrity = has_any(s, ["배우", "가수", "방송인", "연예인", "아이돌", "스타", "유명인", "셀럽"])
    personal = has_any(s, ["투병", "미담", "개인사", "가족사", "건강 이상"])
    if celebrity and personal and not has_any(s, MEDICAL_VALUE_TERMS):
        return True
    return False


def sales_candidate(a):
    if clearly_excluded(a):
        return False
    s = article_text(a)
    value = has_any(s, MEDICAL_VALUE_TERMS)
    disease = has_any(s, DISEASE_TERMS)
    treatment = has_any(s, ["치료", "수술", "입원", "재활", "항암", "시술", "치료과정", "치료 과정"])
    burden = has_any(s, ["부담", "비용", "본인", "비급여", "고액", "경제적", "지출"])
    caregiver = has_any(s, ["간병", "돌봄"])
    if value:
        return True
    if disease and treatment and burden:
        return True
    if caregiver and (treatment or burden):
        return True
    return False


def load_raw():
    with INPUT_FILE.open(encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "news", "articles"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def prepare(items):
    out, seen = [], set()
    for n in items:
        if not isinstance(n, dict):
            continue
        url = clean(n.get("source_url") or n.get("originallink") or n.get("url"))
        title = clean(n.get("title"))
        if not url or not title or url in seen or not sales_candidate(n):
            continue
        seen.add(url)
        source = clean(n.get("source") or n.get("publisher"))
        out.append({
            "id": len(out) + 1,
            "title": title,
            "description": clean(n.get("description")),
            "source_url": url,
            "naver_url": clean(n.get("naver_url") or n.get("link")),
            "published_at": clean(n.get("published_at") or n.get("pubDate") or n.get("publishedAt")),
            "source": source,
            "group": clean(n.get("group")),
            "is_major_news": bool(n.get("is_major_news")) or any(d in source for d in MAJOR_NEWS_DOMAINS),
            "origin_type": clean(n.get("origin_type")) or "news",
            "source_org": clean(n.get("source_org")),
            "source_org_name": clean(n.get("source_org_name"))
        })
    return out


MASTER_PROMPT = r'''당신은 삼성화재 RC의 실제 보장점검 영업을 지원하는 의료·보험 뉴스 편집자입니다.

목적은 일반 의료뉴스를 모으는 것이 아니라, 삼성화재 RC가 이 뉴스를 보고 고객에게 구체적인 질문을 하고 기존 보장을 점검할 수 있게 하는 것입니다.

[최우선 판단]
1. 이 뉴스를 본 RC가 고객에게 "혹시 이런 상황에 대한 보장은 준비되어 있으세요?"라고 구체적으로 질문할 수 있는가?
2. 그 질문이 기존 보험의 보장금액·보장공백 확인으로 이어질 수 있는가?
3. 다음 중 하나 이상과 직접 연결되는가?
- 중증질환 치료비 / 고액 치료비
- 질병·상해 수술비
- 반복·장기치료 비용
- 비급여 또는 본인부담 의료비
- 고가 신약·치료비
- 입원 간병 필요
- 간병인 비용 / 가족 간병 부담 / 간병인지원
명확한 연결이 없으면 제외하십시오.

[우선 주제]
암, 뇌혈관질환, 심혈관질환, 중증질환, 희귀질환, 난치질환, 반복·장기치료, 수술, 비급여·본인부담, 고액 치료, 간병비·간병인지원.
중증질환이 아니어도 실제 수술비가 발생하는 질환은 선정할 수 있습니다.

[정책·공식자료]
공식기관 자료를 우선 신뢰하되 공식자료라는 이유만으로 선정하지 마십시오. 환자의 실제 치료비·수술비·본인부담·비급여·간병비에 직접 영향을 주는 경우만 선정합니다.

[절대 제외]
기부·후원·성금·기탁·나눔·모금.
연예인·정치인·스포츠 선수의 단순 미담·투병·선행.
의료인력·채용·병원 운영·의료행정.
정치공방·지역의회·예산·행정 논쟁.
다른 보험사의 신상품·특약·판매·가입·실적·시장점유율·배타적사용권·홍보.
GA 경쟁·이직·전환·수수료·채널 실적.
연금·저축·자산관리·노후자금.
자동차·여행·펫·휴대폰보험.
단순 건강상식·연구성과·의료기술 소개만 있는 기사.

[유명인 예외]
원칙적으로 제외합니다. 예외는 실제 의료비·치료비·수술비·간병비 경제부담이 핵심이고, 유명인이라는 사실을 삭제해도 일반 고객에게 의미가 있으며, 보험 보장점검 질문이 가능한 경우뿐입니다.

[동일 이슈 중복]
질환명이 아니라 하나의 사건·정책·발표·연구·조사·통계·시범사업·제도변경을 기준으로 중복을 판단하십시오.
같은 정책을 다른 언론이 다르게 표현해도 하나만 남깁니다.
같은 사건의 금액·인물관계·기관·고유사실이 같으면 하나만 남깁니다.
같은 사건이 아니어도 고객에게 던지는 질문과 영업 메시지가 사실상 같으면 하나만 남깁니다.
issue_signature에는 사건/정책/연구의 핵심 고유사실을 짧게 담고, 같은 이슈라면 표현이 달라도 같은 의미가 되게 하십시오.

[대표 기사]
공식 원자료 > 내용이 가장 구체적인 주요 언론 > 일반 재인용 순으로 선택합니다.
환자 경제부담, 치료비, 수술비, 비급여, 본인부담, 간병비가 실제 원문에서 구체적인 기사를 우선합니다.

[영업 Tip]
sales_tip은 반드시 기사에서 직접 도출하십시오.
'기사의 사실 → 고객 상황 → 구체적인 질문 → 필요 시 기존 보장 점검' 순서로 작성하십시오.
"보장공백을 점검해 보세요" 같은 범용 문구만 쓰지 마십시오.
기사의 핵심 질환·비용·제도·숫자와 직접 연결된 질문을 포함하십시오.
원문에 없는 보험 필요성이나 보장내용을 만들어내지 마십시오.

[제목]
카드 제목은 원문의 가장 중요한 핵심 이슈와 일치해야 합니다. 기사 후반부의 보조 통계·사례·숫자를 기사 전체의 핵심처럼 제목화하지 마십시오.

[점수]
sales_score는 100점 기준: 중증질환 치료비 20 / 수술비 15 / 반복·장기치료 15 / 비급여·본인부담 15 / 간병 20 / 고객질문 구체성 10 / 삼성화재 RC 활용성 5.
70점 미만은 출력하지 마십시오. 80점 이상 우선, 90점 이상 최우선.
title_alignment_score 65 미만은 출력하지 마십시오.

[최종 질문 검증]
반드시 "이 뉴스를 본 삼성화재 RC는 고객에게 ______라고 질문할 수 있다"가 구체적으로 완성되어야 합니다. 구체적인 질문이 불가능하면 출력하지 마십시오.

[출력]
JSON 객체 하나만 출력하십시오.
{"articles":[{"category":"policy|medical|samsung_fire","source_title":"원문 제목","core_topic":"기사 핵심","title_topic":"제목 핵심","issue_signature":"동일 이슈 식별용 고유사실","title_alignment_score":0,"title_alignment_pass":true,"sales_score":0,"title":"카드 제목","summary":"2~3문장 요약","why_it_matters":"삼성화재 RC 관점의 의미","sales_tip":"기사 사실과 연결된 실제 고객 질문","source":"출처","published_at":"발행일","source_url":"원문 URL"}]}
최대 14개.
'''


def make_prompt(batch):
    rows = []
    for x in batch:
        rows.append(
            f"\n[NEWS_ID={x['id']}] 유형={x['origin_type']} 공식기관={x['source_org_name']} 그룹={x['group']} "
            f"메이저={x['is_major_news']} 제목={x['title']} 내용={x['description']} 출처={x['source']} "
            f"발행={x['published_at']} URL={x['source_url']}"
        )
    return MASTER_PROMPT + "".join(rows)


def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def analyze(batch, label, allow_split=True):
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=make_prompt(batch))
            data = parse_json(response.text)
            articles = data.get("articles", []) if isinstance(data, dict) else []
            if not isinstance(articles, list):
                raise ValueError("articles 배열이 아닙니다")
            print(f"Gemini 배치 {label}: {len(articles)}개")
            return articles
        except Exception as exc:
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                print(f"Gemini 배치 {label}: quota 오류")
                return []
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            if allow_split and len(batch) > 5:
                mid = len(batch) // 2
                print(f"Gemini 배치 {label}: 실패 → 분할 재시도")
                return analyze(batch[:mid], f"{label}A", False) + analyze(batch[mid:], f"{label}B", False)
            print(f"Gemini 배치 {label} 오류: {msg}")
            return []
    return []


def normalize_category(a):
    c = clean(a.get("category")).lower()
    if c in {"policy", "medical", "samsung_fire"}:
        return c
    s = article_text(a)
    if "삼성화재" in s:
        return "samsung_fire"
    if any(x in s for x in ["보건복지부", "건강보험", "심평원", "국민건강보험", "질병관리청", "금융감독원"]):
        return "policy"
    return "medical"


def article_tokens(a):
    text = clean(" ".join(str(a.get(k, "")) for k in ("source_title", "title", "core_topic", "summary", "issue_signature"))).lower()
    stop = {"오늘", "관련", "대한", "통해", "지원", "확대", "강화", "필요", "가능", "환자", "의료", "질환", "치료", "보험", "보장", "기사", "발표", "정부"}
    return {x for x in re.findall(r"[0-9]+(?:\.[0-9]+)?[가-힣%]*|[가-힣]{2,}", text) if x not in stop}


def numbers(a):
    text = clean(" ".join(str(a.get(k, "")) for k in ("source_title", "title", "core_topic", "summary", "issue_signature")))
    return set(re.findall(r"\d+(?:\.\d+)?\s*(?:억|조|만원|만명|명|%|퍼센트|개월|년|월)?", text))


def same_issue(a, b):
    sa = clean(a.get("issue_signature") or a.get("core_topic") or a.get("title")).lower()
    sb = clean(b.get("issue_signature") or b.get("core_topic") or b.get("title")).lower()
    if sa and sb and SequenceMatcher(None, sa, sb).ratio() >= 0.78:
        return True
    ta, tb = article_tokens(a), article_tokens(b)
    shared = ta & tb
    overlap = len(shared) / max(1, min(len(ta), len(tb)))
    title_ratio = SequenceMatcher(None, clean(a.get("title")), clean(b.get("title"))).ratio()
    shared_numbers = numbers(a) & numbers(b)
    if shared_numbers and len(shared) >= 4 and overlap >= 0.45:
        return True
    if overlap >= 0.72 or title_ratio >= 0.86:
        return True
    return False


def source_priority(a):
    score = 0
    if a.get("origin_type") == "official":
        score += 10000
    if a.get("is_major_news"):
        score += 1000
    score += int(a.get("sales_score") or 0) * 10
    score += int(a.get("title_alignment_score") or 0)
    text = article_text(a)
    for term, points in [("비급여", 100), ("본인부담", 90), ("치료비", 90), ("수술비", 80), ("간병비", 80), ("고액", 50)]:
        if term in text:
            score += points
    return score


def deduplicate(articles):
    winners = []
    for a in sorted(articles, key=source_priority, reverse=True):
        duplicate = next((w for w in winners if same_issue(a, w)), None)
        if duplicate:
            print(f"[AI 동일이슈 제거] {clean(a.get('title'))} -> {clean(duplicate.get('title'))}")
            continue
        winners.append(a)
    return winners


def valid_ai_article(a):
    if not isinstance(a, dict):
        return False
    if not clean(a.get("title")) or not clean(a.get("source_title")) or not clean(a.get("summary")) or not clean(a.get("sales_tip")):
        return False
    if int(a.get("sales_score") or 0) < MIN_SALES_SCORE:
        return False
    if int(a.get("title_alignment_score") or 0) < 65 or a.get("title_alignment_pass") is False:
        return False
    if clearly_excluded(a):
        return False
    tip = clean(a.get("sales_tip"))
    if not any(x in tip for x in ["고객에게", "물어보", "질문", "준비되어", "확인해"]):
        return False
    return True


def main():
    raw = load_raw()
    candidates = prepare(raw)
    print(f"원본 기사: {len(raw)}개 / 영업 후보: {len(candidates)}개")
    if not candidates:
        raise RuntimeError("영업 활용도가 높은 AI 후보가 없습니다.")

    candidates = sorted(candidates, key=lambda x: (
        x.get("origin_type") == "official",
        x.get("is_major_news"),
        has_any(article_text(x), MEDICAL_VALUE_TERMS),
        x.get("published_at", "")
    ), reverse=True)[:MAX_ANALYSIS_NEWS]

    all_articles = []
    for start in range(0, len(candidates), BATCH_SIZE):
        all_articles.extend(analyze(candidates[start:start + BATCH_SIZE], start // BATCH_SIZE + 1))

    by_url = {x["source_url"]: x for x in candidates}
    by_title = {x["title"]: x for x in candidates}
    normalized = []
    for a in all_articles:
        if not isinstance(a, dict):
            continue
        meta = by_url.get(clean(a.get("source_url"))) or by_title.get(clean(a.get("source_title")))
        if meta:
            for key in ("source_url", "naver_url", "published_at", "source", "origin_type", "source_org", "source_org_name", "is_major_news", "group"):
                if not a.get(key):
                    a[key] = meta.get(key, "")
        a["category"] = normalize_category(a)
        normalized.append(a)

    valid = [a for a in normalized if valid_ai_article(a)]
    valid = deduplicate(valid)

    categories = {"policy": [], "medical": [], "samsung_fire": []}
    for a in valid:
        categories[a["category"]].append(a)
    for key in categories:
        categories[key] = sorted(categories[key], key=source_priority, reverse=True)

    final_count = sum(len(v) for v in categories.values())
    if final_count == 0:
        raise RuntimeError("최종 검수 통과 뉴스가 없습니다.")

    sales_points = [clean(a.get("sales_tip")) for a in valid[:5] if clean(a.get("sales_tip"))]
    output = {
        "date": time.strftime("%Y.%m.%d"),
        "categories": categories,
        "article_count": final_count,
        "sales_points": sales_points,
        "quality": {
            "ai_sales_editor": True,
            "master_prompt_version": "2026-09-10-sales-first-v1",
            "raw_count": len(raw),
            "sales_candidate_count": len(candidates),
            "ai_generated_count": len(all_articles),
            "ai_valid_count": len(valid),
            "deduped_count": final_count,
            "min_sales_score": MIN_SALES_SCORE
        }
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"최종 Morning Brief: {final_count}개")
    for key, items in categories.items():
        print(f"  {key}: {len(items)}개")


if __name__ == "__main__":
    main()
