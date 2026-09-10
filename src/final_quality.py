import json
import re
from pathlib import Path
from difflib import SequenceMatcher

NEWS_FILE = Path("data/news.json")

GENERIC = {
    "오늘", "이번", "관련", "대한", "통해", "예상", "전망", "확대", "강화", "지원", "부담",
    "증가", "감소", "문제", "논란", "우려", "필요", "가능", "환자", "건강", "의료", "질환",
    "치료", "발생", "확인", "정부", "당국", "발표", "정책", "연구", "조사", "통계", "기사",
    "보험", "보장", "본인", "최근", "내년", "올해", "등", "대상", "계획", "방안", "추진",
    "시행", "적용", "혜택", "있다", "한다", "밝혔다"
}

ISSUE_FAMILIES = {
    "rare_copay": ["희귀질환", "희귀·난치", "희귀 난치", "중증희귀", "중증·희귀", "중증난치", "중증 난치", "난치질환", "중증질환"],
    "end_of_life": ["임종 전", "말기 의료비", "생애 말기", "생애말기", "사망 전 의료비", "죽기 전 의료비", "연명의료", "호스피스"],
    "high_cost": ["고액 치료비", "고액 치료", "고액 의료비", "고액의료비", "치료비 부담", "의료비 부담", "고비용 치료"],
    "noncovered": ["비급여", "선별급여", "비급여 진료비", "비급여 치료비", "본인부담", "본인 부담"],
    "surgery": ["수술비", "수술 비용", "수술", "시술", "중재시술"],
    "repeated_treatment": ["반복 치료", "장기 치료", "장기간 치료", "재활 치료", "반복치료", "장기치료"],
    "new_drug": ["신약", "고가 신약", "신약 치료비", "혁신신약", "표적항암", "면역항암", "세포치료", "유전자치료"],
    "new_technology": ["신의료기술", "혁신의료기술", "차세대 치료", "정밀의료", "유전자검사", "유전자 치료", "세포 치료"],
    "caregiver": ["간병인", "간병비", "간병 비용", "간병인 지원", "간병인지원", "가족 간병", "간병 부담", "돌봄 부담"],
    "cancer": ["암 치료", "암 치료비", "암 의료비", "항암", "표적항암", "면역항암"],
    "cerebrovascular": ["뇌혈관", "뇌졸중", "뇌출혈", "뇌경색"],
    "cardiovascular": ["심혈관", "심근경색", "심장질환"]
}

RELEVANCE_TERMS = [
    "치료비", "의료비", "병원비", "본인부담", "비급여", "신약", "신의료기술", "혁신의료기술",
    "수술비", "수술 비용", "시술", "항암", "재활", "간병비", "간병인", "반복 치료", "장기 치료",
    "중증질환", "희귀질환", "난치", "암", "뇌혈관", "심혈관"
]

RESEARCH_TERMS = ["연구", "규명", "발견", "개발", "임상", "치료법", "치료 전략", "치료제", "신약", "신의료기술", "혁신의료기술", "정밀의료", "유전자검사", "유전자 치료", "세포 치료"]
PROMO_TERMS = ["구매", "예약", "이벤트", "할인", "무료 상담", "상담 신청", "가입하세요", "출시 기념", "프로모션", "광고"]


def clean(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\n", " ").replace("\r", " ").strip())


def text(a):
    return clean(" ".join(str(a.get(k, "")) for k in (
        "source_title", "title", "core_topic", "summary", "why_it_matters", "sales_tip"
    ))).lower()


def title(a):
    return clean(a.get("title") or a.get("source_title")).lower()


def numbers(a):
    return set(re.findall(r"\d+(?:\.\d+)?\s*(?:억|만원|조|만명|명|%|퍼센트)?", text(a)))


def family_set(a):
    s = text(a)
    return {f for f, terms in ISSUE_FAMILIES.items() if any(term.lower() in s for term in terms)}


def title_tokens(a):
    return {w for w in re.findall(r"[0-9]+(?:\.[0-9]+)?[가-힣%]*|[가-힣]{2,}", title(a)) if w not in GENERIC}


def title_overlap(a, b):
    x, y = title_tokens(a), title_tokens(b)
    return len(x & y) / max(1, min(len(x), len(y)))


def research_or_new_technology(a):
    s = text(a)
    return any(x in s for x in RESEARCH_TERMS) and any(x in s for x in ["신약", "신의료기술", "혁신의료기술", "치료", "의료", "암", "질환", "유전자", "세포", "임상"])


def promotional_only(a):
    s = text(a)
    promo_hits = sum(1 for x in PROMO_TERMS if x in s)
    relevance_hits = sum(1 for x in RELEVANCE_TERMS if x in s)
    return promo_hits >= 2 and relevance_hits == 0


def strong_same_event(a, b):
    """같은 사건/정책/연구라는 근거가 충분할 때만 True."""
    ta, tb = title(a), title(b)
    sa, sb = text(a), text(b)
    na, nb = numbers(a), numbers(b)
    fa, fb = family_set(a), family_set(b)
    shared_f = fa & fb

    # URL은 호출부에서 먼저 처리한다.
    # AI가 만든 issue_signature가 동일하면 가장 강한 중복 근거다.
    sig_a = clean(a.get("issue_signature")).lower()
    sig_b = clean(b.get("issue_signature")).lower()
    if sig_a and sig_b and sig_a == sig_b:
        return True, "동일 issue_signature"

    # 서로 다른 연구/신약/신의료기술 기사는 같은 의료영역이라는 이유만으로 합치지 않는다.
    # 동일 연구기관/연구명/치료법 + 높은 제목 유사성이 있을 때만 같은 연구로 판단한다.
    if research_or_new_technology(a) or research_or_new_technology(b):
        research_anchors = [
            "서울대병원", "서울대학교병원", "고려대", "고려대학교", "연세대", "연세대학교",
            "연구팀", "연구진", "임상시험", "임상", "논문", "학술지", "연구 결과"
        ]
        shared_anchor = [x for x in research_anchors if x in sa and x in sb]
        if shared_anchor and title_overlap(a, b) >= 0.70:
            return True, "동일 연구/임상/발표로 판단"
        # 숫자·기관·제목이 모두 거의 같은 경우만 추가 판단
        if na and nb and na & nb and title_overlap(a, b) >= 0.82:
            return True, "동일 연구의 동일 수치·제목"
        return False, "서로 다른 연구·신약·신의료기술 기사"

    # 서로 다른 의료 이슈군은 중복으로 취급하지 않는다.
    if fa and fb and not shared_f:
        return False, "서로 다른 의료 이슈"

    # 동일 정책/제도: 정책명이나 구체 수치가 겹치고 제목이 충분히 유사한 경우.
    policy_anchors = ["건강보험료율", "건강보험요율", "본인부담률", "건강보험 개편", "비급여 관리", "간병 급여화", "건강보험 재정"]
    shared_policy = [x for x in policy_anchors if x in sa and x in sb]
    if shared_policy and ((na & nb) or title_overlap(a, b) >= 0.72):
        return True, "동일 정책/제도"

    # 같은 사건: 구체적인 숫자와 사건 고유어가 동시에 겹치는 경우.
    if na and nb and na & nb:
        unique_event = {w for w in title_tokens(a) & title_tokens(b) if w not in GENERIC}
        if len(unique_event) >= 3 and title_overlap(a, b) >= 0.60:
            return True, "동일 사건의 동일 수치·핵심어"

    # 제목이 거의 같은 재전송/재가공 기사만 제거한다.
    raw_ratio = SequenceMatcher(None, clean(a.get("title")), clean(b.get("title"))).ratio()
    if raw_ratio >= 0.94:
        return True, "사실상 동일 제목"

    return False, ""


def sales_relevance(a):
    s = text(a)
    return sum(1 for x in RELEVANCE_TERMS if x in s)


def score(a):
    s = sales_relevance(a) * 25
    if a.get("is_major_news"):
        s += 30
    if a.get("origin_type") == "official":
        s += 40
    if a.get("title_alignment_pass") is True:
        s += 15
    if research_or_new_technology(a):
        s += 35
    if clean(a.get("sales_tip")):
        s += 15
    return s


def dedup(items):
    winners = []
    seen_urls = set()
    for item in sorted(items, key=score, reverse=True):
        url = clean(item.get("source_url") or item.get("naver_url")).lower()
        if url and url in seen_urls:
            print(f"[최종 중복 제외] {clean(item.get('title'))} / 동일 URL")
            continue
        duplicate = None
        reason = ""
        for winner in winners:
            duplicate, reason = strong_same_event(item, winner)
            if duplicate:
                print(f"[최종 엄격중복 제거] {clean(item.get('title'))} -> {clean(winner.get('title'))} / {reason}")
                break
        if duplicate:
            continue
        winners.append(item)
        if url:
            seen_urls.add(url)
    return winners


def article_tip(a):
    existing = clean(a.get("sales_tip"))
    if existing:
        return existing

    s = text(a)
    if promotional_only(a):
        return ""
    if "end_of_life" in family_set(a):
        return "기사에서 제시한 말기 의료비 부담을 바탕으로 고객에게 ‘큰 치료비가 장기간 발생하거나 임종 전 의료비가 커질 경우 어떻게 준비하고 있나요?’라고 질문하고 기존 보장을 점검해 보세요."
    if "new_drug" in family_set(a) or "new_technology" in family_set(a):
        return "새로운 치료법·신약·신의료기술이 실제 환자 치료에 적용될 때 건강보험 급여 여부와 환자 본인부담이 어떻게 되는지 확인하고, 고객에게 ‘새 치료를 받게 될 경우 본인이 부담할 비용까지 준비돼 있나요?’라고 질문해 보세요."
    if "surgery" in family_set(a):
        return "기사의 수술·시술 내용을 기준으로 고객에게 ‘질병이나 사고로 수술 또는 시술을 받게 되면 치료비를 어떻게 준비하고 있나요?’라고 질문하고 관련 보장을 점검해 보세요."
    if "caregiver" in family_set(a):
        return "기사의 간병 부담을 기준으로 고객에게 ‘입원했을 때 가족이 직접 간병하기 어렵다면 간병 비용을 어떻게 마련할 계획인가요?’라고 질문하고 간병 관련 보장을 확인해 보세요."
    if "noncovered" in family_set(a):
        return "기사에서 다룬 비급여·본인부담 내용을 기준으로 고객에게 ‘병원에서 건강보험이 적용되지 않는 치료를 받게 되면 비용을 어떻게 준비하고 있나요?’라고 질문해 보세요."
    if sales_relevance(a) >= 2:
        return "기사에서 실제 환자에게 발생할 수 있는 치료비·의료비 부담을 한 가지 짚어 고객에게 질문하고, 그 비용이 현재 보장으로 충분한지 점검해 보세요."
    return ""


def main():
    if not NEWS_FILE.exists():
        raise FileNotFoundError(str(NEWS_FILE))
    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    categories = data.get("categories", {}) if isinstance(data, dict) else {}
    if not isinstance(categories, dict):
        return

    all_items = []
    original_category = {}
    for key in ("policy", "medical", "samsung_fire"):
        for item in categories.get(key) or []:
            if isinstance(item, dict):
                item["sales_tip"] = article_tip(item)
                all_items.append(item)
                original_category[id(item)] = key

    filtered = [x for x in dedup(all_items) if not promotional_only(x)]
    out = {"policy": [], "medical": [], "samsung_fire": []}
    caps = {"policy": 2, "medical": 10, "samsung_fire": 2}
    for item in filtered:
        key = item.get("category") if item.get("category") in out else original_category.get(id(item), "medical")
        if len(out[key]) < caps[key]:
            out[key].append(item)

    data["categories"] = out
    data["sales_points"] = [x["sales_tip"] for k in ("policy", "medical", "samsung_fire") for x in out[k] if clean(x.get("sales_tip"))][:5]
    data["article_count"] = sum(len(v) for v in out.values())
    quality = data.setdefault("quality", {})
    quality["final_strict_issue_dedup"] = True
    quality["dedup_policy"] = "same URL or demonstrably same event/policy/research only"
    quality["topic_similarity_alone_is_not_duplicate"] = True
    quality["research_new_drug_new_technology_preserved"] = True
    quality["different_numbers_or_customer_questions_preserved"] = True
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"최종 품질검수 완료: {data['article_count']}건")


if __name__ == "__main__":
    main()
