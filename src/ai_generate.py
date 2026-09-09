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
    "신상품", "상품 출시", "출시", "보장 강화", "보장확대", "보장 확대", "가입자", "체결",
    "판매", "판매 돌입", "판매 개시", "인기", "히트상품", "주력상품", "대표상품", "추천",
    "특화상품", "특화 상품", "배타적사용권", "배타적 사용권", "상품 경쟁력", "흥행", "완판",
    "판매실적", "판매 실적", "시장점유율"
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
    prepared, seen = [], set()
    for news in news_list:
        if not isinstance(news, dict):
            continue
        title = clean_text(news.get("title"))
        description = clean_text(news.get("description"))
        source_url = clean_text(news.get("source_url") or news.get("originallink") or news.get("url"))
        if not title or not source_url or source_url in seen:
            continue
        seen.add(source_url)
        source = clean_text(news.get("source") or news.get("publisher"))
        prepared.append({
            "id": len(prepared) + 1,
            "title": title,
            "description": description,
            "source_url": source_url,
            "naver_url": clean_text(news.get("naver_url") or news.get("link")),
            "published_at": clean_text(news.get("published_at") or news.get("pubDate") or news.get("publishedAt")),
            "source": source,
            "group": clean_text(news.get("group")),
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
    medical_context = ["의료비", "치료비", "비급여", "본인부담", "간병비", "간병", "치료", "환자", "질환", "건강보험", "의료", "병원", "신약", "암", "뇌혈관", "심혈관"]
    return not any(term in text for term in medical_context)


SYSTEM_PROMPT = """
당신은 '강원영업단 RC Morning Brief'의 전문 편집자입니다.
이 자료는 삼성화재 전속 RC에게 아침마다 배포하는 실전 영업용 브리핑입니다.
목적은 뉴스를 많이 보여주는 것이 아니라 고객의 의료비 부담과 보장 공백을 발견할 수 있는 좋은 상담 소재를 제공하는 것입니다.

[우선순위]
1. 고객 의료비 부담
2. 암·뇌혈관·심혈관 등 중증질환의 치료과정 부담
3. 비급여·선별급여·고액 신약·신의료기술 등 본인부담
4. 간병비·간병인 비용·가족 돌봄 부담
5. 삼성화재 건강보험·장기보험·간병 관련 객관적 소식
6. 고객 보장에 직접 영향을 주는 보험제도

[공식기관]
건강보험심사평가원, 금융감독원, 손해보험협회, 보건복지부, 국민건강보험공단, 질병관리청, 한국보건의료연구원 등 공식기관 자료는 신뢰도 높은 원자료입니다.
고객 의료비·비급여·본인부담·간병·중증질환 치료비·보험제도와 직접 관련되면 우선 검토하십시오.

[기사-제목 상관관계]
카드뉴스 제목은 원문 기사 전체의 메인 주제를 반영해야 합니다. 본문 후반부의 보조 수치나 사례를 메인 제목으로 확대하지 마십시오.

[중복 방지 - 최우선]
같은 사건·정책·발표·연구 결과를 여러 언론이 거의 같은 내용으로 보도한 경우 1개만 선택하십시오.
같은 사건을 다른 표현으로 쓴 제목은 서로 다른 기사로 취급하지 마십시오.
특히 동일한 정책 발표, 동일한 연구, 동일한 통계, 동일한 정부 발표자료를 재인용한 기사들은 하나의 이슈로 묶으십시오.
'희귀·난치', '중증 희귀질환', '중증·희귀질환 지원', '희귀질환 건강보험 지원', '희귀질환 본인부담 경감' 등 표현이 달라도 동일 발표/정책이면 하나만 남기십시오.
'유산', '자연유산', '반복 유산', '유산 경험' 등 표현이 달라도 동일 연구·조사·통계·발표를 근거로 한 기사라면 하나만 남기십시오.
같은 날 '건보료 동결 + 중증·희귀·난치 보장 확대'처럼 하나의 정책 패키지/논쟁을 서로 다른 제목으로 보도한 경우도 하나로 묶으십시오.
단, 같은 질환군이라도 실제 사건·연구·정책·치료비 이슈가 다르면 별도 기사로 허용하십시오.

[같은 이슈일 때 남길 기사]
같은 사건/연구/정책 후보가 여러 개라면 고객 개인의 의료비 부담을 가장 구체적으로 보여주는 기사를 우선하십시오.
비급여, 고액 신약, 신약 치료비, 본인부담 증가, 개인 의료비 부담, 보장 공백, 민영보험/보험 준비 필요성처럼 고객의 추가 비용과 보장 점검으로 바로 연결되는 내용이 실제 원문에 있으면 그것을 우선 선택하십시오.
단순 제도 사실만 반복하는 기사는 후순위로 두십시오.
기사에 없는 민영보험 필요성을 새로 만들지 마십시오.

[절대 제외]
다른 보험사의 신상품·특약·보장강화·가입·판매·실적·시장점유율·상품홍보, GA 장점·성장·확대·이직·전환·수수료 경쟁, 전속채널 약화/위기, 주가·주식, 단순 실적, 자동차/여행/펫/휴대폰보험, 연예·정치 일반·사건사고, 광고·협찬·홍보성 콘텐츠.
기사에 없는 사실이나 보장 내용을 만들지 마십시오.
"""

SALES_TIP_RULES = """
[RC 세일즈 TIP]
뉴스 → 고객의 실제 부담 → 보장 점검 → 자연스러운 상담 연결 순서로 작성하십시오.
암: 진단금뿐 아니라 수술·항암약물·항암방사선·표적/면역치료 등 치료과정 전체 비용을 점검.
뇌혈관: 시술·수술·재활 등 치료과정 비용 부담을 점검.
심혈관: 시술·수술·약물치료 등 치료과정 비용 부담을 점검.
비급여/선별급여: 급여 여부만 보지 말고 실제 본인부담과 보장공백을 확인.
간병: 간병인 사용일당보다 간병인 지원·간병인지원·가족의 간병 부담 중심으로 대화.
특정 담보 가입을 단정적으로 권유하지 말고 현재 건강·장기보험 보장 점검으로 연결하십시오.
"""


def build_prompt(batch):
    rows = []
    for item in batch:
        rows.append(f"""
[NEWS_ID={item['id']}]
자료유형: {'공식기관 원자료' if item.get('origin_type') == 'official' else '일반 뉴스'}
공식기관: {item.get('source_org_name', '')}
검색그룹: {item['group']}
메이저언론 여부: {item['is_major_news']}
제목: {item['title']}
내용: {item['description']}
출처: {item['source']}
발행일: {item['published_at']}
원문URL: {item['source_url']}
""")
    return SYSTEM_PROMPT + SALES_TIP_RULES + """
[선별]
좋은 기사가 부족하면 억지로 채우지 마십시오.
동일 사건·정책·발표·연구의 반복 보도는 1개만 남기고 서로 다른 핵심 주제는 균형 있게 선택하십시오.
같은 연구·통계·정책을 서로 다른 언론사가 다시 쓴 기사도 동일 이슈로 처리하십시오.

[출력]
반드시 JSON 객체 하나만 출력하십시오. Markdown 코드블록 금지.
각 기사:
{
  "category":"policy|medical|samsung_fire",
  "source_title":"입력 원문 제목",
  "core_topic":"원문 핵심 주제",
  "title_topic":"카드뉴스 제목 핵심 주제",
  "title_alignment_score":0,
  "title_alignment_pass":true,
  "title":"재구성 제목",
  "summary":"2~3문장",
  "why_it_matters":"RC 상담 활용 의미",
  "sales_tip":"고객에게 말할 자연스러운 영업 Tip",
  "source":"출처",
  "published_at":"발행일",
  "source_url":"원문 URL"
}
전체 최대 14개, policy 최대 2개, medical 최대 10개, samsung_fire 최대 2개.
""" + "\n".join(rows)


def parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def analyze_batch(batch, batch_number, allow_split=True):
    for attempt in range(MAX_RETRIES_503 + 1):
        try:
            print(f"  Gemini 요청 (배치 {batch_number}, 시도 {attempt+1}/{MAX_RETRIES_503+1})")
            response = client.models.generate_content(model=MODEL_NAME, contents=build_prompt(batch))
            result = parse_json(response.text)
            articles = result.get("articles", [])
            if not isinstance(articles, list):
                raise ValueError("articles가 배열이 아닙니다.")
            print(f"  → 배치 {batch_number} 분석 완료: {len(articles)}개")
            return articles
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                print(f"  [Gemini 쿼터 초과] 배치 {batch_number} 건너뜀")
                return []
            if "503" in msg or "UNAVAILABLE" in msg:
                if attempt < MAX_RETRIES_503:
                    time.sleep(RETRY_DELAY_503)
                    continue
            print(f"  [Gemini 오류] 배치 {batch_number}: {msg}")
            if allow_split and len(batch) > 5:
                mid = len(batch) // 2
                print(f"  → 오류 배치를 {mid}개 + {len(batch)-mid}개로 분할 재시도")
                return analyze_batch(batch[:mid], f"{batch_number}A", False) + analyze_batch(batch[mid:], f"{batch_number}B", False)
            return []
    return []


def restore_metadata(article, source_by_url):
    url = clean_text(article.get("source_url"))
    original = source_by_url.get(url)
    if not original:
        return None
    article["source_url"] = original["source_url"]
    article["published_at"] = original["published_at"]
    article["source"] = original["source"]
    article["naver_url"] = original["naver_url"]
    article["source_title"] = original["title"]
    article["origin_type"] = original.get("origin_type", "news")
    article["source_org"] = original.get("source_org", "")
    article["source_org_name"] = original.get("source_org_name", "")
    article["group"] = original.get("group", "")
    article["is_major_news"] = original.get("is_major_news", False)
    return article


def deduplicate(articles):
    result, seen = [], set()
    for article in articles:
        url = clean_text(article.get("source_url"))
        if url and url not in seen:
            seen.add(url)
            result.append(article)
    return result


def validate_title_alignment(articles, source_by_url):
    candidates = []
    for article in articles:
        original = source_by_url.get(clean_text(article.get("source_url")))
        if original:
            candidates.append({
                "source_url": original["source_url"],
                "source_title": original["title"],
                "source_description": original["description"],
                "generated_title": clean_text(article.get("title")),
                "core_topic": clean_text(article.get("core_topic")),
            })
    if not candidates:
        return []
    prompt = """
당신은 뉴스 편집 품질검수자입니다. 원문 기사 핵심 주제와 카드뉴스 제목이 같은지 검수하십시오.
원문 후반부의 보조 수치/사례를 메인 제목으로 만든 경우 불일치입니다.
각 항목을 checks 배열의 JSON으로 반환하십시오: {"source_url":"...","pass":true,"score":0,"reason":"한 문장"}
90~100 동일, 80~89 명확히 동일, 60~79 일부 관련, 0~59 다른 주제. 65 미만은 pass=false입니다.
"""
    for attempt in range(MAX_RETRIES_503 + 1):
        try:
            response = client.models.generate_content(model=MODEL_NAME, contents=prompt + "\n검수 대상:\n" + json.dumps(candidates, ensure_ascii=False))
            checks = parse_json(response.text).get("checks", [])
            by_url = {clean_text(x.get("source_url")): x for x in checks}
            out = []
            for article in articles:
                c = by_url.get(clean_text(article.get("source_url")))
                try:
                    first = int(article.get("title_alignment_score", 0))
                except Exception:
                    first = 0
                score = min(first, int(c.get("score", 0))) if c else 0
                ok = bool(c and c.get("pass") is True and article.get("title_alignment_pass") is True and score >= TITLE_ALIGNMENT_MIN_SCORE)
                article["title_alignment_score"] = score
                article["title_alignment_pass"] = ok
                article["title_alignment_reason"] = clean_text(c.get("reason")) if c else "검수 결과 없음"
                if ok:
                    out.append(article)
            print(f"  → 제목-기사 상관관계 검수: {len(out)}개 통과 / {len(articles)-len(out)}개 제외")
            return out
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise RuntimeError("제목-기사 상관관계 검수 Gemini 쿼터 초과") from e
            if "503" in msg or "UNAVAILABLE" in msg:
                if attempt < MAX_RETRIES_503:
                    time.sleep(RETRY_DELAY_503)
                    continue
            raise RuntimeError(f"제목-기사 상관관계 검수 실패: {msg}") from e
    return []


MEDICAL_TOPIC_CLUSTERS = {
    "health_policy_medical_burden": [
        "건강보험료율", "건강보험요율", "건강보험료", "보험료율", "건강보험 재정",
        "중증 희귀 난치", "중증·희귀·난치", "중증 희귀질환", "중증·희귀질환",
        "희귀 난치질환", "희귀·난치질환", "희귀질환 지원", "희귀질환 건강보험",
        "희귀질환 본인부담", "희귀질환 치료비", "난치질환 지원", "중증질환 지원",
        "희귀질환 보장성", "희귀질환 본인 부담", "중증 희귀 난치질환"
    ],
    "miscarriage": [
        "유산", "자연유산", "반복 유산", "반복유산", "유산 경험", "유산율",
        "유산 위험", "유산 위험도", "유산 예방", "유산 원인", "유산 관련"
    ],
    "noncovered_burden": ["비급여", "선별급여", "본인부담", "본인 부담", "비급여 의료비", "비급여 치료비"],
    "caregiver_burden": ["간병비", "간병 비용", "간병인 비용", "간병비 부담", "간병 부담", "가족 간병", "간병 지원"],
    "cancer_treatment_cost": ["암 치료비", "암 의료비", "암 치료", "암 통합치료", "항암", "방사선", "표적항암", "면역항암"],
    "cerebrovascular_cost": ["뇌혈관", "뇌졸중", "뇌출혈", "뇌경색", "뇌혈관질환"],
    "cardiovascular_cost": ["심혈관", "심근경색", "심장질환", "심혈관질환"],
}

TOPIC_MAX = {"health_policy_medical_burden": 1, "miscarriage": 1}
BURDEN_PRIORITY_TERMS = [
    ("고액 신약", 70), ("신약 치료비", 70), ("신약", 60), ("비급여", 55),
    ("개인 의료비 부담", 55), ("고액 치료비", 50), ("개인 부담", 45),
    ("본인부담 증가", 45), ("본인 부담 증가", 45), ("의료비 부담", 45),
    ("치료비 부담", 45), ("보장 공백", 40), ("민영보험", 35),
    ("보험 준비", 30), ("보험 보장", 25), ("치료비", 25),
]


def infer_medical_topic(article):
    text = " ".join(clean_text(article.get(k)) for k in ("source_title", "title", "core_topic", "summary", "why_it_matters", "sales_tip"))
    rare_terms = MEDICAL_TOPIC_CLUSTERS["health_policy_medical_burden"]
    insurance_finance_terms = ["건강보험료율", "건강보험요율", "건강보험료", "보험료율", "건강보험 재정"]
    if any(t in text for t in rare_terms) or any(t in text for t in insurance_finance_terms):
        return "health_policy_medical_burden"
    if any(t in text for t in MEDICAL_TOPIC_CLUSTERS["miscarriage"]):
        return "miscarriage"
    for topic, terms in MEDICAL_TOPIC_CLUSTERS.items():
        if topic in ("health_policy_medical_burden", "miscarriage"):
            continue
        if any(term in text for term in terms):
            return topic
    return "other"


def burden_priority_score(article):
    text = " ".join(clean_text(article.get(k)) for k in ("source_title", "title", "summary", "why_it_matters", "sales_tip", "core_topic"))
    score = 0
    for term, points in BURDEN_PRIORITY_TERMS:
        if term in text:
            score += points
    score += 15 if article.get("origin_type") == "official" else 0
    score += 10 if article.get("is_major_news") else 0
    return score


def article_text(article):
    return " ".join(clean_text(article.get(k)) for k in ("source_title", "title", "core_topic", "summary", "why_it_matters"))


def normalized_tokens(text):
    text = clean_text(text).lower()
    text = re.sub(r"[^0-9a-z가-힣 ]", " ", text)
    return [x for x in text.split() if len(x) >= 2]


def token_overlap(a, b):
    sa, sb = set(normalized_tokens(article_text(a))), set(normalized_tokens(article_text(b)))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def title_similarity(a, b):
    na = re.sub(r"[^0-9a-z가-힣 ]", " ", clean_text(a).lower())
    nb = re.sub(r"[^0-9a-z가-힣 ]", " ", clean_text(b).lower())
    return SequenceMatcher(None, na, nb).ratio()


def core_topic_similarity(a, b):
    ta = clean_text(a.get("core_topic"))
    tb = clean_text(b.get("core_topic"))
    if not ta or not tb:
        return 0.0
    return SequenceMatcher(None, ta, tb).ratio()


def event_fingerprint(article):
    """기사 제목이 달라도 같은 연구/발표/정책을 다룬 경우 잡기 위한 핵심 토큰 묶음."""
    text = article_text(article)
    fingerprint_terms = [
        "정부", "보건복지부", "건강보험공단", "심평원", "질병관리청", "연구팀", "연구진", "연구",
        "조사", "조사결과", "통계", "발표", "보고서", "정책", "시범사업", "본인부담", "건강보험",
        "유산", "자연유산", "반복유산", "희귀질환", "중증질환", "난치질환"
    ]
    return {term for term in fingerprint_terms if term in text}


def same_core_topic(a, b):
    topic_a, topic_b = infer_medical_topic(a), infer_medical_topic(b)
    if topic_a != topic_b:
        return False
    if topic_a in ("health_policy_medical_burden", "miscarriage"):
        # 같은 클러스터라도 서로 다른 연구/사건을 무조건 합치지 않도록
        # 제목/핵심주제/본문의 공통 핵심어가 충분히 겹칠 때 동일 이슈로 본다.
        title_sim = title_similarity(a.get("source_title") or a.get("title"), b.get("source_title") or b.get("title"))
        core_sim = core_topic_similarity(a, b)
        overlap = token_overlap(a, b)
        fingerprints = event_fingerprint(a) & event_fingerprint(b)
        return title_sim >= 0.62 or core_sim >= 0.70 or (overlap >= 0.65 and len(fingerprints) >= 2)
    title_sim = title_similarity(a.get("source_title") or a.get("title"), b.get("source_title") or b.get("title"))
    core_sim = core_topic_similarity(a, b)
    overlap = token_overlap(a, b)
    return title_sim >= 0.72 or core_sim >= 0.72 or overlap >= 0.85


def issue_similarity(a, b):
    """클러스터가 다르게 분류된 기사까지 같은 사건인지 보조 판정한다."""
    title_sim = title_similarity(a.get("source_title") or a.get("title"), b.get("source_title") or b.get("title"))
    core_sim = core_topic_similarity(a, b)
    overlap = token_overlap(a, b)
    fingerprints = event_fingerprint(a) & event_fingerprint(b)
    return title_sim >= 0.80 or core_sim >= 0.80 or (overlap >= 0.82 and len(fingerprints) >= 2)


def representative_score(article):
    score = burden_priority_score(article)
    if article.get("origin_type") == "official":
        score += 25
    if article.get("is_major_news"):
        score += 10
    desc = clean_text(article.get("summary") or article.get("why_it_matters"))
    if len(desc) >= 80:
        score += 5
    return score


def select_balanced_medical(articles, limit=10, per_topic=2):
    selected, counts = [], {}
    grouped = {}
    for article in articles:
        topic = infer_medical_topic(article)
        grouped.setdefault(topic, []).append(article)

    for topic in ("health_policy_medical_burden", "miscarriage"):
        if topic in grouped:
            grouped[topic] = sorted(grouped[topic], key=representative_score, reverse=True)

    ordered = []
    for topic in ("health_policy_medical_burden", "miscarriage"):
        if topic in grouped:
            winner = grouped[topic][0]
            ordered.append(winner)
            counts[topic] = 1
            print(f"  [핵심이슈 대표기사] {topic}: {clean_text(winner.get('title'))}")
            for excluded in grouped[topic][1:]:
                print(f"  [동일 핵심이슈 제외] {topic}: {clean_text(excluded.get('title'))}")
            del grouped[topic]

    for topic, group in grouped.items():
        ordered.extend(sorted(group, key=representative_score, reverse=True))

    for article in ordered:
        topic = infer_medical_topic(article)
        cap = TOPIC_MAX.get(topic, per_topic)
        if counts.get(topic, 0) >= cap:
            print(f"  [동일 핵심주제 제외] {topic}: {clean_text(article.get('title'))}")
            continue
        if any(issue_similarity(article, existing) or same_core_topic(article, existing) for existing in selected):
            print(f"  [거의 동일 이슈 제외] {clean_text(article.get('title'))}")
            continue
        selected.append(article)
        counts[topic] = counts.get(topic, 0) + 1
        if len(selected) >= limit:
            break
    print(f"  의료 주제별 최종 분포: {counts}")
    return selected


def select_core_topic_winners(articles):
    """카테고리가 달라도 같은 핵심 이슈는 최종적으로 한 기사만 남긴다."""
    groups = {}
    others = []
    for article in articles:
        topic = infer_medical_topic(article)
        if topic == "other":
            others.append(article)
        else:
            groups.setdefault(topic, []).append(article)

    winners = []
    for topic, group in groups.items():
        if topic in ("health_policy_medical_burden", "miscarriage"):
            winner = max(group, key=representative_score)
            winners.append(winner)
            print(f"  [핵심이슈 1개로 통합] {topic} 대표: {clean_text(winner.get('title'))}")
            for item in group:
                if item is not winner:
                    print(f"  [중복 배제] {topic}: {clean_text(item.get('title'))}")
        else:
            kept = []
            for item in group:
                if any(same_core_topic(item, existing) for existing in kept):
                    print(f"  [거의 동일 기사 제외] {topic}: {clean_text(item.get('title'))}")
                    continue
                kept.append(item)
            winners.extend(kept)

    # 서로 다른 토픽으로 분류된 기사라도 동일 사건이면 하나만 남긴다.
    cross_checked = []
    for article in winners:
        duplicate = False
        for existing in cross_checked:
            if issue_similarity(article, existing):
                duplicate = True
                print(f"  [교차 이슈 중복 제외] {clean_text(article.get('title'))}")
                break
        if not duplicate:
            cross_checked.append(article)
    return cross_checked + [x for x in others if not any(issue_similarity(x, y) for y in cross_checked)]


def normalize_category(article):
    raw = clean_text(article.get("category")).lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "policy":"policy", "policies":"policy", "제도":"policy", "정책":"policy", "보험제도":"policy", "보험_제도":"policy",
        "medical":"medical", "medicine":"medical", "health":"medical", "의료":"medical", "의료비":"medical", "보장":"medical", "간병":"medical", "상품":"medical",
        "samsung_fire":"samsung_fire", "samsungfire":"samsung_fire", "samsung":"samsung_fire", "삼성화재":"samsung_fire"
    }
    if raw in aliases:
        return aliases[raw]
    text = " ".join(clean_text(article.get(k)) for k in ("source_title", "title", "summary", "core_topic"))
    if article.get("origin_type") == "official" and any(x in text for x in ["제도", "정책", "개편", "개정", "보험료", "건강보험", "보건복지", "금융감독", "비급여 관리"]):
        return "policy"
    if "삼성화재" in text:
        return "samsung_fire"
    if any(x in text for x in ["의료비", "치료비", "비급여", "본인부담", "간병", "암", "뇌혈관", "심혈관", "건강보험", "유산"]):
        return "medical"
    return "policy" if article.get("group") == "policy" else "medical"


def organize_articles(articles):
    categories = {"policy": [], "medical": [], "samsung_fire": []}
    for article in articles:
        category = normalize_category(article)
        if article.get("source_url"):
            article["category"] = category
            categories[category].append(article)
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
        score = 45 if item.get("origin_type") == "official" else 0
        score += 15 if item.get("is_major_news") else 0
        score += {"medical_cost": 40, "caregiver": 35, "product": 30, "samsung_fire": 25, "policy": 15}.get(item.get("group"), 0)
        if any(x in text for x in ["의료비", "치료비", "본인부담", "비급여", "간병비", "간병", "암", "뇌혈관", "심혈관", "유산"]):
            score += 20
        if is_other_insurer_promo(item):
            score -= 100
        return score

    official = sorted([x for x in raw_news if x.get("origin_type") == "official" and not is_other_insurer_promo(x)], key=candidate_score, reverse=True)
    general = sorted([x for x in raw_news if x.get("origin_type") != "official" and not is_other_insurer_promo(x)], key=candidate_score, reverse=True)
    candidates = (official[:12] + general)[:MAX_ANALYSIS_NEWS]
    print(f"공식기관 후보 우선 확보: {min(len(official), 12)}개")
    print(f"AI 분석 대상: {len(candidates)}개")

    if not candidates:
        output = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "categories": {"policy": [], "medical": [], "samsung_fire": []}, "sales_points": [], "article_count": 0}
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    source_by_url = {x["source_url"]: x for x in candidates}
    analyzed = []
    for start in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[start:start + BATCH_SIZE]
        analyzed.extend(analyze_batch(batch, (start // BATCH_SIZE) + 1, allow_split=True))
        if start + BATCH_SIZE < len(candidates):
            time.sleep(3)

    restored = [x for x in (restore_metadata(a, source_by_url) for a in analyzed) if x]
    restored = deduplicate(restored)
    restored = validate_title_alignment(restored, source_by_url)

    final = []
    for article in restored:
        original = source_by_url.get(clean_text(article.get("source_url")))
        if original and not is_other_insurer_promo(original):
            final.append(article)

    final = select_core_topic_winners(final)
    categories = organize_articles(final)
    output = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "categories": categories, "sales_points": make_sales_points(categories), "article_count": sum(len(v) for v in categories.values())}
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 60)
    print(f"최종 기사: {output['article_count']}개")
    print(f"상품·보장/의료비·간병: {len(categories['medical'])}개")
    print(f"삼성화재 소식: {len(categories['samsung_fire'])}개")
    print(f"제도 동향: {len(categories['policy'])}개")
    print("=" * 60)


if __name__ == "__main__":
    main()
