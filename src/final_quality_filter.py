import json
import re
from pathlib import Path
from difflib import SequenceMatcher

NEWS_FILE = Path('data/news.json')

GENERIC = {
    '오늘','이번','관련','대한','통해','예상','전망','확대','강화','지원','부담','증가','감소',
    '문제','논란','우려','필요','가능','환자','건강','의료','질환','치료','발생','확인','정부',
    '당국','발표','정책','연구','조사','통계','기사','보험','보장','본인','부담금','최근',
    '내년','올해','등','대상','계획','방안','추진','시행','적용','혜택','관련해','있다','한다'
}

# 같은 정책/사건을 식별하는 핵심 키워드. 세부 사례가 달라도 같은 이슈로 묶는다.
ISSUE_GROUPS = {
    'rare_severe_policy': ['희귀질환','희귀·난치','희귀 난치','난치질환','중증희귀','중증·희귀','중증 난치','중증난치','중증질환'],
    'rare_copay_policy': ['본인부담 10','본인부담률','본인부담 5','본인부담 7','본인 부담 10','본인 부담률'],
    'inheritance': ['상속','유산','상속재산','유류분','20억','10억','30%','맏아들','삼형제','형제','아버지','어머니'],
    'miscarriage': ['자연유산','반복유산','계류유산','유산 경험','유산율','유산 위험','임신','임산부','산모','태아'],
    'caregiver': ['간병인','간병비','간병 비용','가족간병','가족 간병','돌봄 부담','간병 지원'],
    'noncovered': ['비급여','선별급여','비급여 진료비','본인부담금'],
    'cancer': ['암 치료비','암 의료비','암 치료','항암','방사선','표적항암','면역항암'],
    'cerebrovascular': ['뇌혈관','뇌졸중','뇌출혈','뇌경색'],
    'cardiovascular': ['심혈관','심근경색','심장질환','심장'],
}


def clean(v):
    s = str(v or '').lower()
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'[^0-9a-z가-힣% ]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def article_text(a):
    return ' '.join(clean(a.get(k)) for k in (
        'title','source_title','issue_signature','core_topic','summary','why_it_matters','sales_tip'
    ))


def numbers(a):
    return set(re.findall(r'\d+(?:\.\d+)?\s*(?:억|만원|조|만명|명|%|퍼센트)?', article_text(a)))


def keywords(a):
    s = article_text(a)
    out = set()
    for group, terms in ISSUE_GROUPS.items():
        hits = [t for t in terms if t in s]
        if hits:
            out.add(group)
            out.update(hits)
    words = {x for x in s.split() if len(x) >= 2 and x not in GENERIC}
    return out | words


def title_tokens(a):
    return {x for x in clean(a.get('title') or a.get('source_title')).split() if len(x) >= 2 and x not in GENERIC}


def similarity(a, b):
    x, y = title_tokens(a), title_tokens(b)
    return len(x & y) / max(1, min(len(x), len(y))) if x and y else 0.0


def strict_same_issue(a, b):
    ta, tb = article_text(a), article_text(b)
    na, nb = numbers(a), numbers(b)
    ka, kb = keywords(a), keywords(b)
    shared_num = len(na & nb)
    shared_kw = len(ka & kb)
    title_sim = similarity(a, b)
    raw_sim = SequenceMatcher(None, clean(a.get('title')), clean(b.get('title'))).ratio()

    # 1. 제목이 거의 같은 경우
    if title_sim >= 0.78 or raw_sim >= 0.86:
        return True, '제목 유사도'

    # 2. 같은 정책/사건 그룹 + 공통 핵심 숫자. 예: 10→7%, 10→5%처럼 목표 수치가 달라도 같은 정책.
    groups_a = {g for g, terms in ISSUE_GROUPS.items() if any(t in ta for t in terms)}
    groups_b = {g for g, terms in ISSUE_GROUPS.items() if any(t in tb for t in terms)}
    shared_groups = groups_a & groups_b

    if 'rare_severe_policy' in shared_groups and ('rare_copay_policy' in groups_a or 'rare_copay_policy' in groups_b):
        if shared_num >= 1 or ('본인부담' in ta and '본인부담' in tb):
            return True, '희귀·중증 본인부담 정책군'

    if 'inheritance' in shared_groups:
        # 20억/10억/30% 중 하나 이상 + 상속 핵심어가 겹치면 동일 사건으로 본다.
        if shared_num >= 1 and any(x in ta and x in tb for x in ['상속','유산','상속재산','유류분','맏아들','삼형제']):
            return True, '상속 동일 사건'
        if shared_kw >= 4:
            return True, '상속 핵심키워드'

    # 3. 동일 이슈군 + 키워드/숫자가 충분히 겹치면 동일 이슈
    if shared_groups and shared_num >= 1 and shared_kw >= 4:
        return True, '동일 이슈군 + 공통 사실'

    # 4. 제목과 원문 관련 키워드가 강하게 겹치면 동일 이슈
    if shared_kw >= 7 and (shared_num >= 1 or title_sim >= 0.55):
        return True, '공통 핵심키워드'

    return False, ''


def rep_score(a):
    s = 0
    if a.get('origin_type') == 'official': s += 100
    if a.get('is_major_news'): s += 30
    text = article_text(a)
    for term, points in [
        ('비급여',35),('고액 신약',35),('신약 치료비',35),('개인 의료비',30),
        ('치료비 부담',30),('본인부담',25),('간병비',25),('상속재산',15)
    ]:
        if term in text: s += points
    if a.get('title_alignment_pass') is True: s += 10
    return s


def strict_dedup(items):
    # 대표성이 높은 기사를 먼저 배치하고, 이후 기사는 대표 기사와 비교해 제거한다.
    ordered = sorted(items, key=rep_score, reverse=True)
    winners = []
    for a in ordered:
        duplicate_of = None
        reason = ''
        for w in winners:
            same, why = strict_same_issue(a, w)
            if same:
                duplicate_of, reason = w, why
                break
        if duplicate_of:
            print(f'[최종 중복 제거] {a.get("title","")} -> {duplicate_of.get("title","")} / {reason}')
        else:
            winners.append(a)
    return winners


def topic_group(a):
    s = article_text(a)
    for group, terms in ISSUE_GROUPS.items():
        if any(t in s for t in terms):
            return group
    return 'other'


def relevant_sales_tip(a):
    # 뉴스와 직접 연결된 영업팁이 없거나 범용 문구면 기사 핵심 사실에서 다시 만든다.
    s = article_text(a)
    current = clean(a.get('sales_tip'))
    generic = [
        '뉴스 내용을 계기로', '최근 의료비 부담에 대한 고객의 걱정을 확인하고',
        '현재 건강 장기보험 보장을 점검해 보세요', '보장 공백을 점검해 보세요'
    ]
    if current and not any(x in current for x in generic):
        return a

    if '상속' in s or '유류분' in s or '20억' in s:
        a['sales_tip'] = '상속·유산 분쟁처럼 가족에게 실제 자산 이전이 필요한 상황을 고객이 어떻게 준비하고 있는지 확인하고, 보장과 재산 이전 계획을 구분해 상담해 보세요.'
    elif any(x in s for x in ['희귀질환','희귀·난치','난치질환','중증희귀','중증난치']) and '본인부담' in s:
        a['sales_tip'] = '건강보험의 본인부담이 낮아지는 내용과 별개로 고객이 부담할 수 있는 비급여·고액 치료비가 무엇인지 확인하는 질문으로 상담을 시작해 보세요.'
    elif any(x in s for x in ['유산','임신','임산부','산모','태아']):
        a['sales_tip'] = '유산 관련 위험과 치료 과정에서 실제로 어떤 비용 부담이 생기는지 먼저 확인하고, 임신·출산 관련 기존 보장의 범위를 함께 점검해 보세요.'
    elif any(x in s for x in ISSUE_GROUPS['caregiver']):
        a['sales_tip'] = '기사의 간병비 부담을 그대로 고객 상황에 대입해 입원 시 누가 간병할지, 간병비를 어떻게 마련할지 먼저 물어보고 간병 관련 보장을 점검해 보세요.'
    elif any(x in s for x in ISSUE_GROUPS['noncovered']):
        a['sales_tip'] = '이번 비급여 이슈를 계기로 고객이 최근 경험한 비급여 진료가 있었는지 묻고, 실제 본인부담금과 현재 보장의 차이를 확인해 보세요.'
    elif any(x in s for x in ISSUE_GROUPS['cancer']):
        a['sales_tip'] = '기사의 암 치료비 이슈를 바탕으로 진단 이후 수술·항암·약물치료 중 어떤 비용이 가장 걱정되는지 고객에게 물어보고 치료비 보장을 점검해 보세요.'
    elif any(x in s for x in ISSUE_GROUPS['cerebrovascular']):
        a['sales_tip'] = '뇌혈관질환의 진단 이후 시술·수술·재활 과정 중 고객이 가장 걱정하는 비용을 먼저 물어보고 현재 치료비 보장을 확인해 보세요.'
    elif any(x in s for x in ISSUE_GROUPS['cardiovascular']):
        a['sales_tip'] = '심혈관질환 진단 이후 실제 치료 과정에서 어떤 비용이 발생할 수 있는지 고객에게 질문하고 시술·수술 관련 보장을 함께 점검해 보세요.'
    elif '본인부담' in s or '의료비' in s or '치료비' in s:
        a['sales_tip'] = '기사에서 언급된 의료비 부담이 고객에게도 발생할 수 있는지 최근 진료 경험을 물어보고, 실제 본인부담과 현재 보장의 차이를 확인해 보세요.'
    return a


def main():
    if not NEWS_FILE.exists():
        raise SystemExit('data/news.json 없음')
    data = json.loads(NEWS_FILE.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise SystemExit('data/news.json 형식 오류')
    cats = data.get('categories', {})
    all_items = []
    for key in ('policy','medical','samsung_fire'):
        all_items.extend(cats.get(key, []) or [])

    before = len(all_items)
    all_items = strict_dedup(all_items)
    all_items = [relevant_sales_tip(x) for x in all_items]

    # 정책/의료/삼성화재 분류를 유지하되 최종적으로 이슈 중복이 없는 상태에서 다시 나눈다.
    policy, medical, samsung = [], [], []
    for a in all_items:
        if a.get('origin_type') == 'official' or any(x in article_text(a) for x in ['건강보험','보건복지부','금융감독원','제도 개선','제도개선','정책']):
            policy.append(a)
        elif '삼성화재' in article_text(a):
            samsung.append(a)
        else:
            medical.append(a)

    data['categories'] = {
        'policy': policy[:2],
        'medical': medical[:10],
        'samsung_fire': samsung[:2],
    }
    data['sales_points'] = []
    for a in all_items:
        tip = str(a.get('sales_tip') or '').strip()
        if tip and tip not in data['sales_points']:
            data['sales_points'].append(tip)
        if len(data['sales_points']) >= 5:
            break
    data['article_count'] = sum(len(v) for v in data['categories'].values())
    data['final_quality_filter'] = {
        'strict_issue_dedup': True,
        'before': before,
        'after': data['article_count'],
    }
    NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'최종 품질검수: {before}건 -> {data["article_count"]}건')


if __name__ == '__main__':
    main()
