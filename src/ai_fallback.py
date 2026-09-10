import json
import re
import time
from pathlib import Path

INPUT_FILE = Path("data/raw_news.json")
OUTPUT_FILE = Path("data/news.json")

EXCLUDE = [
    "기부", "후원", "성금", "기탁", "나눔", "모금", "의료인력", "의료진 채용",
    "채용", "국회의원", "도의원", "시의원", "자동차보험", "여행보험", "반려동물보험",
    "휴대폰보험", "연금보험", "연금저축", "노후자금", "노후자산", "은퇴자금", "목돈마련",
    "저축보험", "저축성보험", "적금", "자산관리"
]

VALUE = [
    "의료비", "치료비", "수술비", "수술", "본인부담", "비급여", "간병비", "간병인",
    "간병인지원", "간병 부담", "고액 치료", "고가 치료", "신약", "신의료기술",
    "혁신의료기술", "면역항암", "표적항암", "유전자 치료", "유전자검사", "치료 부담"
]
DISEASE = [
    "암", "항암", "뇌혈관", "뇌졸중", "뇌출혈", "뇌경색", "심혈관", "심근경색",
    "심장질환", "희귀질환", "난치질환", "중증질환", "말기"
]


def clean(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\n", " ").replace("\r", " ").strip())


def text(a):
    return clean(" ".join(str(a.get(k, "")) for k in ("title", "description", "source"))).lower()


def is_candidate(a):
    s = text(a)
    if any(x in s for x in EXCLUDE):
        return False
    if any(x in s for x in VALUE):
        return True
    return any(x in s for x in DISEASE) and any(x in s for x in ["치료", "수술", "입원", "비용", "부담"])


def make_tip(a):
    s = text(a)
    title = clean(a.get("title"))
    if any(x in s for x in ["간병비", "간병인", "간병인지원", "간병 부담"]):
        return "이 뉴스를 고객에게 보여드리며 입원 시 간병인 지원과 간병비 부담에 대한 준비가 되어 있는지 질문해 보세요."
    if any(x in s for x in ["신약", "신의료기술", "혁신의료기술", "면역항암", "표적항암", "유전자"]):
        return "이 뉴스를 고객에게 보여드리며 새로운 치료법이나 신약 치료가 필요할 때 치료비와 비급여 부담에 대한 보장이 준비되어 있는지 질문해 보세요."
    if any(x in s for x in ["수술", "수술비"]):
        return "이 뉴스를 고객에게 보여드리며 실제 수술이 필요한 상황에서 질병·상해 수술비 보장이 충분한지 확인해 보세요."
    if any(x in s for x in ["비급여", "본인부담"]):
        return "이 뉴스를 고객에게 보여드리며 건강보험 적용 후에도 남는 본인부담과 비급여 의료비에 대한 보장이 준비되어 있는지 질문해 보세요."
    return "이 뉴스를 고객에게 보여드리며 치료가 길어지거나 비용이 커질 경우 현재 보장으로 충분한지 함께 확인해 보세요."


def summary(a):
    d = clean(a.get("description"))
    return d[:180] if d else clean(a.get("title"))


def main():
    data = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    raw = data.get("articles", data) if isinstance(data, dict) else data
    candidates = []
    seen = set()
    for a in raw:
        if not isinstance(a, dict):
            continue
        url = clean(a.get("source_url") or a.get("originallink") or a.get("url"))
        title = clean(a.get("title"))
        if not url or not title or url in seen or not is_candidate(a):
            continue
        seen.add(url)
        item = dict(a)
        item["category"] = "policy" if any(x in text(a) for x in ["건강보험", "보건복지부", "심평원", "국민건강보험", "금융감독원"]) else "medical"
        item["source_title"] = title
        item["core_topic"] = title
        item["title"] = title
        item["summary"] = summary(a)
        item["why_it_matters"] = "치료비·수술비·본인부담·비급여·신약·신의료기술·간병 등 실제 고객의 의료비 부담과 보장점검에 연결할 수 있는 기사입니다."
        item["sales_tip"] = make_tip(a)
        item["title_alignment_score"] = 100
        item["title_alignment_pass"] = True
        item["sales_score"] = 80
        item["published_at"] = clean(a.get("published_at") or a.get("pubDate"))
        candidates.append(item)

    # AI quota 오류 시에도 시스템 전체가 중단되지 않도록 한다.
    # 서로 다른 연구·신약·신의료기술 기사는 URL만 다르면 보존한다.
    candidates.sort(key=lambda x: (x.get("published_at", ""), x.get("is_major_news", False)), reverse=True)
    candidates = candidates[:30]

    categories = {"policy": [], "medical": [], "samsung_fire": []}
    for a in candidates:
        categories[a["category"]].append(a)

    result = {
        "date": time.strftime("%Y.%m.%d"),
        "categories": categories,
        "article_count": len(candidates),
        "sales_points": [a["sales_tip"] for a in candidates[:5]],
        "quality": {
            "ai_sales_editor": False,
            "fallback_reason": "Gemini quota/resource exhaustion",
            "fallback_mode": "rule_based_preserve_medical_candidates",
            "raw_count": len(raw),
            "fallback_count": len(candidates),
            "topic_dedup": "URL only"
        }
    }
    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[AI Fallback] Gemini quota 오류 → 의료·보험 후보 {len(candidates)}개 보존")


if __name__ == "__main__":
    main()
