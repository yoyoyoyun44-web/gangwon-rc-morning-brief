import json
import re
from pathlib import Path
from difflib import SequenceMatcher

NEWS_FILE = Path("data/news.json")

GENERIC = {
    "오늘", "이번", "관련", "대한", "통해", "예상", "전망", "확대", "강화", "지원", "부담",
    "증가", "감소", "문제", "논란", "우려", "필요", "가능", "환자", "건강", "의료", "질환",
    "치료", "발생", "확인", "정부", "당국", "발표", "정책", "연구", "조사", "통계", "기사",
    "보험", "보장", "본인", "부담금", "최근", "내년", "올해", "등", "대상", "계획", "방안",
    "추진", "시행", "적용", "혜택", "있다", "한다", "전망이다", "밝혔다"
}

# 서로 다른 숫자나 사례가 붙어도 하나의 실제 이슈로 판단해야 하는 강한 이슈군
ISSUE_FAMILIES = {
    "rare_copay": ["희귀질환", "희귀·난치", "희귀 난치", "중증희귀", "중증·희귀", "중증난치", "중증 난치", "난치질환", "중증질환"],
    "inheritance_case": ["상속", "상속재산", "유류분", "유산", "맏아들", "삼형제", "형제", "아버지", "어머니", "20억", "10억", "30%"],
    "miscarriage": ["자연유산", "반복유산", "계류유산", "유산 경험", "유산율", "유산 위험", "임신", "임산부", "산모", "태아"],
    "caregiver": ["간병인", "간병비", "간병 비용", "가족간병", "가족 간병", "돌봄 부담", "간병 지원"],
    "noncovered": ["비급여", "선별급여", "비급여 진료비", "비급여 치료비"],
    "cancer": ["암 치료비", "암 의료비", "항암", "표적항암", "면역항암"],
    "cerebrovascular": ["뇌혈관", "뇌졸중", "뇌출혈", "뇌경색"],
    "cardiovascular": ["심혈관", "심근경색", "심장질환"]
}


def clean(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\n", " ").replace("\r", " ").strip())


def text(a):
    return clean(" ".join(str(a.get(k, "")) for k in (
        "source_title", "title", "issue_signature", "core_topic", "summary", "why_it_matters"
    ))).lower()


def numbers(a):
    return set(re.findall(r"\d+(?:\.\d+)?\s*(?:억|만원|조|만명|명|%|퍼센트)?", text(a)))


def tokens(a):
    s = text(a)
    words = set(re.findall(r"[0-9]+(?:\.[0-9]+)?[가-힣%]*|[가-힣]{2,}", s))
    words = {w for w in words if w not in GENERIC}
    for family, terms in ISSUE_FAMILIES.items():
        if any(term in s for term in terms):
            words.add(family)
            words.update(term for term in terms if term in s)
    return words


def family_set(a):
    s = text(a)
    return {family for family, terms in ISSUE_FAMILIES.items() if any(term in s for term in terms)}


def title_tokens(a):
    s = clean(a.get("title") or a.get("source_title")).lower()
    return {w for w in re.findall(r"[0-9]+(?:\.[0-9]+)?[가-힣%]*|[가-힣]{2,}", s) if w not in GENERIC}


def overlap(a, b):
    x, y = title_tokens(a), title_tokens(b)
    return len(x & y) / max(1, min(len(x), len(y)))


def strict_same_issue(a, b):
    sa, sb = text(a), text(b)
    fa, fb = family_set(a), family_set(b)
    shared_families = fa & fb
    shared_numbers = numbers(a) & numbers(b)
    ka, kb = tokens(a), tokens(b)
    shared_keywords = ka & kb
    raw_title = SequenceMatcher(None, clean(a.get("title")), clean(b.get("title"))).ratio()
    title_overlap = overlap(a, b)

    # 1. 희귀·중증질환 본인부담 정책: 5%, 7%, 치과, 당뇨 등 세부 사례가 달라도 동일 정책 발표로 본다.
    if "rare_copay" in shared_families:
        copay_a = any(x in sa for x in ["본인부담", "본인 부담", "본인부담률", "부담률"])
        copay_b = any(x in sb for x in ["본인부담", "본인 부담", "본인부담률", "부담률"])
        if copay_a and copay_b:
            return True, "희귀·중증질환 본인부담 동일 정책"

    # 2. 상속/유산 사건: 금액 또는 가족관계가 겹치면 표현이 달라도 동일 사건으로 묶는다.
    if "inheritance_case" in shared_families:
        money_overlap = bool(shared_numbers & {"20억", "10억", "30%"}) or len(shared_numbers) >= 1
        family_overlap = any(x in sa and x in sb for x in ["맏아들", "삼형제", "형제", "아버지", "어머니", "유류분", "상속재산"])
        if money_overlap and family_overlap:
            return True, "상속 동일 사건·금액·가족관계"
        if "20억" in sa and "20억" in sb and ("상속" in sa or "유산" in sa) and ("상속" in sb or "유산" in sb):
            return True, "상속 20억 동일 사건"

    # 3. 유산(임신) 이슈는 상속과 섞지 않고, 같은 임신/유산 사건이면 묶는다.
    if "miscarriage" in shared_families and "inheritance_case" not in shared_families:
        if len(shared_numbers) >= 1 or len(shared_keywords) >= 5:
            return True, "유산·임신 동일 이슈"

    # 4. 같은 이슈군 + 숫자 1개 + 핵심 키워드 4개 이상
    if shared_families and shared_numbers and len(shared_keywords) >= 4:
        return True, "공통 숫자·이슈군·핵심키워드"

    # 5. 제목 핵심어가 거의 같은 경우
    if raw_title >= 0.84 or title_overlap >= 0.72:
        return True, "제목 핵심키워드 중복"

    # 6. 제목이 조금 달라도 핵심 키워드가 6개 이상 겹치면 같은 이슈
    if len(shared_keywords) >= 6 and title_overlap >= 0.50:
        return True, "기사 핵심키워드 강한 중복"

    return False, ""


def score(a):
    s = 0
    if a.get("origin_type") == "official":
        s += 1000
    if a.get("is_major_news"):
        s += 100
    t = text(a)
    for term, points in [("비급여", 40), ("고액 신약", 35), ("신약 치료비", 35), ("개인 의료비", 30),
                         ("치료비 부담", 30), ("본인부담", 25), ("간병비", 25), ("상속재산", 20)]:
        if term in t:
            s += points
    if a.get("title_alignment_pass") is True:
        s += 10
    return s


def dedup(items):
    winners = []
    for item in sorted(items, key=score, reverse=True):
        dup = next((w for w in winners if strict_same_issue(item, w)[0]), None)
        if dup:
            reason = strict_same_issue(item, dup)[1]
            print(f"[최종 엄격중복 제거] {clean(item.get('title'))} -> {clean(dup.get('title'))} / {reason}")
            continue
        winners.append(item)
    return winners


def article_tip(a):
    s = text(a)
    title = clean(a.get("title") or a.get("source_title"))

    if "rare_copay" in family_set(a) and any(x in s for x in ["본인부담", "본인 부담", "부담률"]):
        if any(x in s for x in ["비급여", "신약", "고액"]):
            return "기사처럼 건강보험 본인부담이 낮아지는 경우에도 비급여·고액 신약 비용은 별개일 수 있습니다. 고객에게 ‘큰 치료비가 생기면 건강보험 외에 본인이 부담할 비용까지 생각해 본 적이 있나요?’라고 물어보세요."
        return "기사의 본인부담률 인하가 적용되는 급여 영역과 실제 치료비 부담을 구분해 보세요. 고객에게 ‘중증질환 치료를 받을 때 건강보험 혜택 외에 본인이 부담할 비용까지 확인해 보셨나요?’라고 질문하고 관련 보장을 점검해 보세요."

    if "inheritance_case" in family_set(a):
        if any(x in s for x in ["20억", "10억", "30%", "유류분"]):
            return "이번 기사는 20억을 이미 받은 상속인이 남은 재산에 추가 권리를 주장하는 상황입니다. 고객에게 ‘가족 간 재산 이전에서 나중에 분쟁이 생길 수 있는 부분까지 생각해 본 적이 있나요?’라고 물어보되, 상속 문제와 보험을 억지로 연결하지 말고 재산·가족관계 상담이 필요한 고객인지 확인해 보세요."
        return "상속재산과 가족관계에 관한 기사인 만큼 보험상품 이야기로 바로 연결하기보다, 고객의 가족관계와 재산 이전에 대한 고민이 있는지 먼저 확인해 보세요."

    if "miscarriage" in family_set(a):
        return "유산 관련 기사는 임신·출산 과정의 위험을 다룬 내용인지 확인하고, 고객에게 ‘임신·출산 과정에서 예상하지 못한 검사나 치료비가 생길 경우 어떻게 준비하고 있나요?’라고 물어보세요. 기사에서 실제 보장 근거가 확인되는 경우에만 보장 점검으로 연결하세요."

    if "caregiver" in family_set(a):
        return "기사에서 언급한 간병비·돌봄 부담을 기준으로 고객에게 ‘입원했을 때 가족이 직접 간병하기 어려우면 간병 비용을 어떻게 마련할 계획인가요?’라고 물어보세요. 이후 간병인 지원 여부와 기존 간병 관련 보장을 구체적으로 확인하세요."

    if "noncovered" in family_set(a):
        return "기사에서 다룬 비급여 항목을 중심으로 고객에게 ‘최근 병원에서 비급여 치료나 검사를 받아본 적이 있나요?’라고 물어보고, 실제 본인부담 가능 비용과 기존 보장의 연결 여부를 확인해 보세요."

    if "cancer" in family_set(a):
        return "기사의 암 치료 내용에서 진단 이후 어떤 치료비가 발생하는지가 핵심인지 확인하고, 고객에게 ‘암 치료를 받는다면 수술·항암·약물치료 중 어떤 비용이 가장 걱정되나요?’라고 물어보세요."

    if "cerebrovascular" in family_set(a):
        return "기사의 뇌혈관질환 치료 단계에 맞춰 고객에게 ‘진단 이후 시술·수술이나 재활까지 이어질 경우 치료비를 어떻게 준비할 생각인가요?’라고 물어보고 관련 보장을 확인해 보세요."

    if "cardiovascular" in family_set(a):
        return "기사의 심혈관질환 치료 내용에 맞춰 고객에게 ‘심혈관질환으로 시술이나 수술을 받게 된다면 치료비 부담을 어떻게 준비하고 있나요?’라고 물어보고 관련 보장을 확인해 보세요."

    return f"‘{title}’에서 실제로 고객 부담을 만드는 핵심 내용을 한 가지 골라, 그 비용이나 제도 변화가 고객에게 해당되는지 먼저 질문해 보세요. 기사와 직접 연결되는 경우에만 현재 보장을 점검하세요."


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
                item["sales_tip"] = article_tip(item)
                all_items.append(item)

    filtered = dedup(all_items)

    # 중복 제거 후 원래 카테고리를 유지하되, 각 카테고리 상한을 적용한다.
    out = {"policy": [], "medical": [], "samsung_fire": []}
    for item in filtered:
        key = item.get("category") if item.get("category") in out else None
        if not key:
            # 원본 데이터에서는 category가 없을 수 있으므로 기존 목록에서 찾는다.
            for k in out:
                if item in (categories.get(k) or []):
                    key = k
                    break
        if not key:
            key = "medical"
        cap = {"policy": 2, "medical": 10, "samsung_fire": 2}[key]
        if len(out[key]) < cap:
            out[key].append(item)

    data["categories"] = out
    data["sales_points"] = [x["sales_tip"] for k in ("policy", "medical", "samsung_fire") for x in out[k] if clean(x.get("sales_tip"))][:5]
    data["article_count"] = sum(len(v) for v in out.values())
    data["quality"] = data.get("quality", {})
    data["quality"]["final_strict_issue_dedup"] = True
    data["quality"]["article_specific_sales_tip"] = True
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"최종 품질검수 완료: {data['article_count']}건")


if __name__ == "__main__":
    main()
