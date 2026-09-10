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

# 서로 다른 고객 질문을 만드는 경제·의료 이슈는 별도 family로 본다.
ISSUE_FAMILIES = {
    "rare_copay": ["희귀질환", "희귀·난치", "희귀 난치", "중증희귀", "중증·희귀", "중증난치", "중증 난치", "난치질환", "중증질환"],
    "end_of_life_medical_cost": ["임종 전", "말기 의료비", "생애 말기", "생애말기", "사망 전 의료비", "죽기 전 의료비", "연명의료", "호스피스"],
    "high_cost_treatment": ["고액 치료비", "고액 치료", "치료비 부담", "고액 의료비", "개인 의료비", "의료비 부담"],
    "surgery_cost": ["수술비", "수술 비용", "수술비용", "수술 부담", "시술비", "시술 비용"],
    "repeated_long_term_treatment": ["반복 치료", "반복치료", "장기 치료", "장기치료", "지속 치료", "지속치료", "재활치료", "통원치료", "추적 치료"],
    "caregiver": ["간병인", "간병비", "간병 비용", "가족간병", "가족 간병", "돌봄 부담", "간병 지원", "간병인지원"],
    "noncovered": ["비급여", "선별급여", "비급여 진료비", "비급여 치료비", "본인부담금"],
    "cancer": ["암 치료비", "암 의료비", "암 치료", "항암", "표적항암", "면역항암"],
    "cerebrovascular": ["뇌혈관", "뇌졸중", "뇌출혈", "뇌경색"],
    "cardiovascular": ["심혈관", "심근경색", "심장질환"]
}

PROTECTED_TOPIC_TERMS = {
    "cancer": ISSUE_FAMILIES["cancer"],
    "cerebrovascular": ISSUE_FAMILIES["cerebrovascular"],
    "cardiovascular": ISSUE_FAMILIES["cardiovascular"],
    "caregiver": ISSUE_FAMILIES["caregiver"]
}


def clean(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\n", " ").replace("\r", " ").strip())


def text(a):
    return clean(" ".join(str(a.get(k, "")) for k in (
        "source_title", "title", "issue_signature", "core_topic", "summary", "why_it_matters", "sales_tip"
    ))).lower()


def title(a):
    return clean(a.get("title") or a.get("source_title"))


def source_url(a):
    return clean(a.get("source_url") or a.get("naver_url") or a.get("url"))


def numbers(a):
    return set(re.findall(r"\d+(?:\.\d+)?\s*(?:억|만원|조|만명|명|%|퍼센트|년|개월|일)?", text(a)))


def tokens(a):
    words = set(re.findall(r"[0-9]+(?:\.[0-9]+)?[가-힣%]*|[가-힣]{2,}", text(a)))
    return {w for w in words if w not in GENERIC}


def family_set(a):
    s = text(a)
    return {family for family, terms in ISSUE_FAMILIES.items() if any(term in s for term in terms)}


def protected_topic(a):
    t = title(a).lower()
    for family in ("cancer", "cerebrovascular", "cardiovascular", "caregiver"):
        if any(term in t for term in PROTECTED_TOPIC_TERMS[family]):
            return family
    return None


def title_tokens(a):
    return {w for w in re.findall(r"[0-9]+(?:\.[0-9]+)?[가-힣%]*|[가-힣]{2,}", title(a).lower()) if w not in GENERIC}


def title_overlap(a, b):
    x, y = title_tokens(a), title_tokens(b)
    return len(x & y) / max(1, min(len(x), len(y)))


def same_url(a, b):
    ua, ub = source_url(a), source_url(b)
    return bool(ua and ub and ua == ub)


def same_signature(a, b):
    sa = clean(a.get("issue_signature")).lower()
    sb = clean(b.get("issue_signature")).lower()
    # AI가 실제 동일 사건/정책/연구라고 명시한 경우에만 사용한다.
    return bool(sa and sb and sa == sb and len(sa) >= 12)


def strong_numeric_overlap(a, b):
    shared = numbers(a) & numbers(b)
    # 숫자가 하나라도 같다는 이유만으로 합치지 않는다. 숫자 + 강한 제목/이슈 앵커가 필요하다.
    return len(shared) >= 2


def strong_event_anchor(a, b):
    sa, sb = text(a), text(b)
    anchors = [
        "보건복지부", "건강보험공단", "건강보험", "한국은행", "금융감독원", "질병관리청",
        "연구팀", "보고서", "연구 결과", "실태조사", "시행령", "고시", "개정안", "발표"
    ]
    return any(x in sa and x in sb for x in anchors)


def strict_same_issue(a, b):
    # 0. 같은 URL은 가장 확실한 중복이다.
    if same_url(a, b):
        return True, "동일 원문 URL"

    # 1. 서로 다른 보호 의료영역은 공통 단어가 많아도 절대 합치지 않는다.
    pa, pb = protected_topic(a), protected_topic(b)
    if pa and pb and pa != pb:
        return False, "서로 다른 보호 의료영역"

    # 2. AI가 동일 issue_signature를 부여한 경우에만 강하게 합친다.
    if same_signature(a, b):
        return True, "동일 issue_signature"

    sa, sb = text(a), text(b)
    fa, fb = family_set(a), family_set(b)
    shared_families = fa & fb
    shared_numbers = numbers(a) & numbers(b)
    ka, kb = tokens(a), tokens(b)
    shared_keywords = ka & kb
    raw_title = SequenceMatcher(None, title(a), title(b)).ratio()
    top_overlap = title_overlap(a, b)

    # 3. 동일 정책/보고서/연구의 재보도는 핵심 제목이 매우 유사하고 강한 사건 앵커가 있을 때만 제거.
    # 단순히 '건강보험/본인부담/의료비'가 같이 나온다는 이유로 제거하지 않는다.
    if strong_event_anchor(a, b) and raw_title >= 0.78 and top_overlap >= 0.55:
        return True, "동일 정책·보고서 재보도"

    # 4. 희귀·중증 본인부담처럼 하나의 정책 패키지인 경우.
    # 서로 다른 정책 발표가 아니라 같은 발표를 다른 언론이 다룬 경우만 제거한다.
    if "rare_copay" in shared_families:
        copay_a = any(x in sa for x in ["본인부담", "본인 부담", "본인부담률", "부담률"])
        copay_b = any(x in sb for x in ["본인부담", "본인 부담", "본인부담률", "부담률"])
        if copay_a and copay_b and (strong_event_anchor(a, b) or strong_numeric_overlap(a, b)) and top_overlap >= 0.45:
            return True, "희귀·중증질환 동일 정책·수치"

    # 5. 같은 구체적 사건/연구에서 숫자와 제목 앵커가 함께 일치할 때만 제거.
    if shared_families and strong_numeric_overlap(a, b) and top_overlap >= 0.55:
        return True, "동일 이슈의 핵심 수치·제목 앵커 중복"

    # 6. 동일 연구/사건의 숫자 하나가 같고 제목도 사실상 같은 경우.
    if strong_numeric_overlap(a, b) and raw_title >= 0.86:
        return True, "동일 사건의 수치·제목 중복"

    # 7. 제목 유사도만으로는 절대 제거하지 않는다.
    # 특히 '의료비 급증', '본인부담 증가'처럼 흔한 문구는 별개 기사를 살린다.
    _ = shared_keywords
    return False, ""


def score(a):
    s = 0
    if a.get("is_major_news"):
        s += 80
    if a.get("origin_type") == "official":
        s += 70
    if a.get("title_alignment_pass") is True:
        s += 25

    t = text(a)
    for term, points in [
        ("비급여", 45), ("고액 신약", 40), ("신약 치료비", 40), ("개인 의료비", 40),
        ("치료비 부담", 35), ("본인부담", 30), ("간병비", 35), ("간병인지원", 35),
        ("수술비", 30), ("수술 비용", 30), ("반복 치료", 30), ("장기 치료", 30),
        ("임종 전", 35), ("말기 의료비", 35)
    ]:
        if term in t:
            s += points

    if a.get("sales_tip"):
        s += 20
    if protected_topic(a):
        s += 35
    return s


def dedup(items):
    winners = []
    for item in sorted(items, key=score, reverse=True):
        duplicate = None
        reason = ""
        for winner in winners:
            is_dup, why = strict_same_issue(item, winner)
            if is_dup:
                duplicate = winner
                reason = why
                break
        if duplicate:
            print(f"[최종 엄격중복 제거] {title(item)} -> {title(duplicate)} / {reason}")
            continue
        winners.append(item)
    return winners


def fallback_sales_tip(a):
    """AI sales_tip이 없을 때만 사용. 기사 내용과 직접 연결되지 않으면 일반론으로 밀어붙이지 않는다."""
    s = text(a)
    if any(x in s for x in ["간병인", "간병비", "간병인지원", "간병 비용"]):
        return "기사에서 언급한 간병 부담을 기준으로 고객에게 ‘입원했을 때 가족이 직접 간병하기 어려우면 간병 비용을 어떻게 마련할 계획인가요?’라고 질문해 보세요."
    if any(x in s for x in ["수술비", "수술 비용", "시술비", "시술 비용"]):
        return "기사의 수술·시술 비용이 실제 고객에게 발생할 수 있는지 확인한 뒤, ‘수술이나 시술을 받게 되면 어떤 비용이 가장 걱정되나요?’라고 질문해 보세요."
    if any(x in s for x in ["비급여", "선별급여", "본인부담"]):
        return "기사에서 다룬 본인부담 비용이 고객에게도 발생할 수 있는지 확인한 뒤, ‘건강보험이 적용되지 않거나 본인이 더 부담해야 하는 치료비까지 생각해 보셨나요?’라고 질문해 보세요."
    if any(x in s for x in ["임종 전", "말기 의료비", "생애 말기", "사망 전 의료비"]):
        return "기사의 생애 말기 의료비 부담을 기준으로 ‘큰 병으로 장기간 치료를 받거나 생애 말기에 의료비가 커진다면 그 비용을 어떻게 준비할 생각인가요?’라고 질문해 보세요."
    if any(x in s for x in ["반복 치료", "장기 치료", "재활치료", "통원치료"]):
        return "기사에서 언급한 반복·장기 치료가 고객에게 발생할 가능성을 확인하고, ‘한 번의 치료보다 치료가 길어질 때 비용을 어떻게 준비할지 생각해 보셨나요?’라고 질문해 보세요."
    if any(x in s for x in ["암 치료", "항암", "표적항암", "면역항암"]):
        return "기사의 암 치료 과정에서 실제 비용 부담이 어디에서 생기는지 확인한 뒤, ‘암 치료를 받는다면 수술·항암·약물치료 중 어떤 비용이 가장 걱정되나요?’라고 질문해 보세요."
    if any(x in s for x in ["뇌혈관", "뇌졸중", "뇌출혈", "뇌경색"]):
        return "기사의 뇌혈관질환 치료·재활 부담을 기준으로 ‘진단 후 시술·수술과 재활까지 이어질 경우 치료비를 어떻게 준비할 생각인가요?’라고 질문해 보세요."
    if any(x in s for x in ["심혈관", "심근경색", "심장질환"]):
        return "기사의 심혈관질환 치료비 부담을 기준으로 ‘시술이나 수술을 받게 된다면 치료비를 어떻게 준비하고 있나요?’라고 질문해 보세요."
    return ""


def main():
    if not NEWS_FILE.exists():
        raise FileNotFoundError(str(NEWS_FILE))

    data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
    categories = data.get("categories", {}) if isinstance(data, dict) else {}
    if not isinstance(categories, dict):
        return

    all_items = []
    for key in ("policy", "medical", "samsung_fire"):
        for item in categories.get(key) or []:
            if isinstance(item, dict):
                # AI가 만든 구체적 sales_tip을 우선한다. 임의의 일반론으로 덮어쓰지 않는다.
                if not clean(item.get("sales_tip")):
                    tip = fallback_sales_tip(item)
                    if tip:
                        item["sales_tip"] = tip
                all_items.append(item)

    filtered = dedup(all_items)

    out = {"policy": [], "medical": [], "samsung_fire": []}
    caps = {"policy": 2, "medical": 10, "samsung_fire": 2}
    for item in filtered:
        key = item.get("category") if item.get("category") in out else "medical"
        if len(out[key]) < caps[key]:
            out[key].append(item)

    data["categories"] = out
    data["sales_points"] = [
        x["sales_tip"] for k in ("policy", "medical", "samsung_fire")
        for x in out[k] if clean(x.get("sales_tip"))
    ][:5]
    data["article_count"] = sum(len(v) for v in out.values())
    data["quality"] = data.get("quality", {})
    data["quality"]["final_strict_issue_dedup"] = True
    data["quality"]["dedup_rule"] = "same URL / same issue_signature / demonstrably same event-policy-research with strong anchors only"
    data["quality"]["generic_title_similarity_is_not_duplicate"] = True
    data["quality"]["protected_medical_topics"] = ["cancer", "cerebrovascular", "cardiovascular", "caregiver"]
    data["quality"]["distinct_medical_cost_topics_can_coexist"] = True
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"최종 품질검수 완료: {data['article_count']}건")


if __name__ == "__main__":
    main()
