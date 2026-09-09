import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from google import genai

INPUT_FILE = Path('data/raw_news.json')
OUTPUT_FILE = Path('data/news.json')
API_KEY = os.getenv('GEMINI_API_KEY')
MODEL_NAME = 'gemini-3.6-flash'
MAX_ANALYSIS_NEWS = 80
BATCH_SIZE = 20
MAX_RETRIES_503 = 2
RETRY_DELAY_503 = 20
TITLE_ALIGNMENT_MIN_SCORE = 65

if not API_KEY:
    raise RuntimeError('GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다.')
client = genai.Client(api_key=API_KEY)

MAJOR_NEWS_DOMAINS = {
    'chosun.com','joongang.co.kr','donga.com','hani.co.kr','hankookilbo.com',
    'mk.co.kr','hankyung.com','sedaily.com','fnnews.com','newsis.com','yna.co.kr',
    'news1.kr','edaily.co.kr','heraldcorp.com','asiae.co.kr','mt.co.kr','seoul.co.kr',
    'khan.co.kr','nocutnews.co.kr','ytn.co.kr'
}
OTHER_INSURER_NAMES = [
    '현대해상','DB손해보험','메리츠화재','KB손해보험','한화손해보험','롯데손해보험',
    '흥국화재','NH농협손해보험','하나손해보험','AXA손해보험','악사손해보험','캐롯손해보험',
    '삼성생명','한화생명','교보생명','신한라이프','KB라이프','NH농협생명','미래에셋생명',
    '동양생명','흥국생명','DB생명','ABL생명','푸본현대생명','라이나생명','AIA생명',
    '메트라이프','처브라이프','KDB생명','iM라이프'
]
OTHER_INSURER_PROMO_TERMS = [
    '신상품','상품 출시','출시','보장 강화','보장확대','보장 확대','가입자','체결','판매',
    '판매 돌입','판매 개시','인기','히트상품','주력상품','대표상품','추천','특화상품',
    '배타적사용권','배타적 사용권','상품 경쟁력','흥행','완판','판매실적','판매 실적','시장점유율'
]

GENERIC = {
    '오늘','이번','관련','대한','통해','예상','전망','확대','강화','지원','부담','증가','감소',
    '문제','논란','우려','필요','가능','환자','건강','의료','질환','치료','발생','확인','정부',
    '당국','발표','정책','연구','조사','통계','기사','보험','보장','본인','부담금','최근',
    '내년','올해','등','대상','계획','방안','추진','시행','적용','혜택','관련해','있다','한다'
}

# 같은 실제 사건·정책을 식별하기 위한 핵심 이슈군.
ISSUE_GROUPS = {
    'rare_severe_policy': ['희귀질환','희귀·난치','희귀 난치','난치질환','중증희귀','중증·희귀','중증 난치','중증난치','중증질환'],
    'rare_copay_policy': ['본인부담 10','본인부담률','본인부담 5','본인부담 7','본인 부담 10','본인 부담률'],
    'inheritance': ['상속','유산','상속재산','유류분','20억','10억','30%','맏아들','삼형제','형제','아버지','어머니'],
    'miscarriage': ['자연유산','반복유산','계류유산','유산 경험','유산율','유산 위험','임신','임산부','산모','태아'],
    'caregiver': ['간병인','간병비','간병 비용','가족간병','가족 간병','돌봄 부담','간병 지원'],
    'noncovered': ['비급여','선별급여','비급여 진료비','본인부담금'],
    'cancer': ['암 치료비','암 의료비','암 치료','항암','방사선','표적항암','면역항암'],
    'cerebrovascular': ['뇌혈관','뇌졸중','뇌출혈','뇌경색'],
    'cardiovascular': ['심혈관','심근경색','심장질환','심장']
}


def clean(v):
    return re.sub(r'\s+', ' ', str(v or '').replace('\n', ' ').replace('\r', ' ').strip())


def load():
    with INPUT_FILE.open(encoding='utf-8') as f:
        d = json.load(f)
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ('items','news','articles'):
            if isinstance(d.get(k), list):
                return d[k]
    return []


def promo(a):
    t = f"{a.get('title','')} {a.get('description','')}"
    medical = ['의료비','치료비','비급여','본인부담','간병','환자','질환','건강보험','병원','신약','암','뇌혈관','심혈관']
    return any(x in t for x in OTHER_INSURER_NAMES) and any(x in t for x in OTHER_INSURER_PROMO_TERMS) and not any(x in t for x in medical)


def prepare(items):
    out, seen = [], set()
    for n in items:
        if not isinstance(n, dict):
            continue
        u = clean(n.get('source_url') or n.get('originallink') or n.get('url'))
        t = clean(n.get('title'))
        if not u or not t or u in seen:
            continue
        seen.add(u)
        s = clean(n.get('source') or n.get('publisher'))
        out.append({
            'id': len(out)+1,
            'title': t,
            'description': clean(n.get('description')),
            'source_url': u,
            'naver_url': clean(n.get('naver_url') or n.get('link')),
            'published_at': clean(n.get('published_at') or n.get('pubDate') or n.get('publishedAt')),
            'source': s,
            'group': clean(n.get('group')),
            'is_major_news': bool(n.get('is_major_news')) or s in MAJOR_NEWS_DOMAINS,
            'origin_type': clean(n.get('origin_type')) or 'news',
            'source_org': clean(n.get('source_org')),
            'source_org_name': clean(n.get('source_org_name'))
        })
    return out


PROMPT = '''당신은 강원영업단 RC Morning Brief의 전문 편집자입니다.
고객의 실제 의료비 부담, 치료비, 간병비, 비급여와 보장 공백을 이해하는 데 도움이 되는 기사만 선별합니다.

[가장 중요한 원칙 1: 기사 제목과 원문 핵심 주제 일치]
카드뉴스 제목은 원문 기사의 '가장 중요한 핵심 이슈'를 정확히 반영해야 합니다. 기사 후반부에 잠깐 등장하는 보조 통계, 다른 사례, 부수적인 숫자를 제목의 주제로 끌어올리지 마십시오.

[가장 중요한 원칙 2: 동일 이슈 중복 금지]
질환명이 아니라 '실제로 발생한 하나의 사건/정책/발표/연구/조사/통계/시범사업/제도변경'을 기준으로 중복을 판단합니다.
같은 발표에서 치과·당뇨·임플란트처럼 예시만 달라진 기사는 같은 이슈입니다.
예를 들어 '중증·희귀질환 본인부담 10%→7%', '희귀·난치환자 본인부담 10→5%', '희귀·난치질환 본인부담 10%→5% + 당뇨/임플란트 사례'가 같은 정책 발표를 다룬다면 반드시 1개만 남깁니다.
'이미 20억을 받은 맏아들의 추가 10억 상속분쟁', '20억을 받은 형의 남은 10억 유산분쟁'처럼 금액·가족관계·사건이 같은 기사도 반드시 1개만 남깁니다.

동일 이슈 여부를 판단할 때 제목의 단어뿐 아니라 숫자/금액/비율/대상자 수/기관명/정책명/가족관계/사건의 고유 사실을 함께 비교하십시오.
각 기사에 issue_signature를 만들되, 같은 사건을 다른 표현으로 쓴 기사들은 같은 issue_signature가 되도록 하십시오.

[대표 기사 선택]
동일 이슈가 여러 기사에 있으면 공식기관 원자료 > 메이저 언론의 상세 기사 > 일반 재인용 순으로 선택합니다.
같은 정책을 다루는 기사 중에서는 정책 자체와 고객 부담을 가장 정확히 설명하는 기사를 선택합니다.
비급여·고액 신약·개인 의료비 부담·보장 공백이 실제 원문에 있으면 우선합니다.
원문에 없는 보험 필요성을 만들어내지 마십시오.

[오늘의 영업 Tip]
'sales_tip'은 반드시 해당 기사에서 바로 도출되어야 합니다.
1) 기사 핵심 사실을 한 문장으로 해석하고
2) 그 사실을 고객에게 확인하는 구체적인 질문을 만들고
3) 필요할 경우 현재 보장 점검으로 연결하십시오.
'최근 의료비 부담을 확인해 보세요', '보장 공백을 점검해 보세요'처럼 어느 기사에나 붙일 수 있는 범용 문구는 금지합니다.
기사의 핵심 숫자·제도·질환·비용·대상과 직접 연결된 질문을 포함하십시오.
뉴스가 보험 상담과 직접 연결되지 않는다면 억지로 상품 이야기를 만들지 말고, '영업 활용도가 낮음'에 가깝게 작성하십시오.

[절대 제외]
다른 보험사 상품홍보/신상품/가입/판매/실적/시장점유율/배타적사용권, GA 경쟁/이직/전환/수수료, 전속채널 위기, 주가/주식, 단순 실적, 자동차/여행/펫/휴대폰보험, 연예/정치 일반/사건사고, 광고/협찬.

출력은 JSON 객체 하나입니다.
각 기사 필드: category(policy|medical|samsung_fire), source_title, core_topic, title_topic, issue_signature, title_alignment_score, title_alignment_pass, title, summary, why_it_matters, sales_tip, source, published_at, source_url.
전체 최대 14개.
'''


def make_prompt(batch):
    return PROMPT + ''.join(
        f"\n[NEWS_ID={x['id']}] 유형={x.get('origin_type')} 공식기관={x.get('source_org_name','')} 그룹={x.get('group')} 메이저={x.get('is_major_news')} 제목={x['title']} 내용={x['description']} 출처={x['source']} 발행={x['published_at']} URL={x['source_url']}"
        for x in batch
    )


def parse(t):
    t = (t or '').strip()
    t = re.sub(r'^```(?:json)?\s*', '', t)
    t = re.sub(r'\s*```$', '', t)
    return json.loads(t)


def analyze(batch, no, split=True):
    for i in range(MAX_RETRIES_503 + 1):
        try:
            r = client.models.generate_content(model=MODEL_NAME, contents=make_prompt(batch))
            a = parse(r.text).get('articles', [])
            if not isinstance(a, list):
                raise ValueError('articles 배열 아님')
            print(f'배치 {no}: {len(a)}개')
            return a
        except Exception as e:
            m = str(e)
            if '429' in m or 'RESOURCE_EXHAUSTED' in m:
                return []
            if ('503' in m or 'UNAVAILABLE' in m) and i < MAX_RETRIES_503:
                time.sleep(RETRY_DELAY_503)
                continue
            if split and len(batch) > 5:
                k = len(batch) // 2
                return analyze(batch[:k], f'{no}A', False) + analyze(batch[k:], f'{no}B', False)
            print(f'Gemini 오류 {no}: {m}')
            return []
    return []


def restore(a, by):
    o = by.get(clean(a.get('source_url')))
    if not o:
        return None
    for k in ('source_url','published_at','source','naver_url','group','source_org','source_org_name'):
        a[k] = o.get(k, '')
    a['source_title'] = o['title']
    a['origin_type'] = o.get('origin_type', 'news')
    a['is_major_news'] = o.get('is_major_news', False)
    return a


def title_check(items, by):
    if not items:
        return []
    q = '''원문 핵심주제와 카드뉴스 제목의 일치 여부를 엄격히 검수하십시오. 후반부 보조 수치나 사례를 메인 제목으로 만들면 불일치입니다. JSON checks 배열만 반환: {"source_url":"...","pass":true,"score":0,"reason":"..."}. 65 미만은 pass=false.'''
    data = [{
        'source_url': by[clean(a.get('source_url'))]['source_url'],
        'source_title': by[clean(a.get('source_url'))]['title'],
        'source_description': by[clean(a.get('source_url'))]['description'],
        'generated_title': clean(a.get('title')),
        'core_topic': clean(a.get('core_topic'))
    } for a in items if clean(a.get('source_url')) in by]
    try:
        r = client.models.generate_content(model=MODEL_NAME, contents=q + '\n' + json.dumps(data, ensure_ascii=False))
        checks = {clean(x.get('source_url')): x for x in parse(r.text).get('checks', [])}
    except Exception as e:
        raise RuntimeError(f'제목-기사 상관관계 검수 실패: {e}')
    out = []
    for a in items:
        c = checks.get(clean(a.get('source_url')))
        score = min(int(a.get('title_alignment_score', 0) or 0), int(c.get('score', 0))) if c else 0
        ok = bool(c and c.get('pass') is True and a.get('title_alignment_pass') is True and score >= TITLE_ALIGNMENT_MIN_SCORE)
        a['title_alignment_score'] = score
        a['title_alignment_pass'] = ok
        a['title_alignment_reason'] = clean(c.get('reason')) if c else '검수 결과 없음'
        if ok:
            out.append(a)
    return out


def article_text(a):
    return ' '.join(clean(a.get(k)) for k in (
        'source_title','title','issue_signature','core_topic','summary','why_it_matters'
    )).lower()


def extract_numbers(a):
    return set(re.findall(r'\d+(?:\.\d+)?\s*(?:억|만원|조|만명|명|%|퍼센트)?', article_text(a)))


def extract_keywords(a):
    s = article_text(a)
    words = {x for x in re.sub(r'[^0-9a-z가-힣% ]', ' ', s).split() if len(x) >= 2 and x not in GENERIC}
    for group, terms in ISSUE_GROUPS.items():
        if any(term in s for term in terms):
            words.add(group)
            words.update(term for term in terms if term in s)
    return words


def title_similarity(a, b):
    x = extract_keywords({'title': a.get('title','')})
    y = extract_keywords({'title': b.get('title','')})
    return len(x & y) / max(1, min(len(x), len(y))) if x and y else 0.0


def strict_same_issue(a, b):
    sa, sb = article_text(a), article_text(b)
    na, nb = extract_numbers(a), extract_numbers(b)
    ka, kb = extract_keywords(a), extract_keywords(b)
    shared_numbers = na & nb
    shared_keywords = ka & kb
    ta = clean(a.get('title') or a.get('source_title'))
    tb = clean(b.get('title') or b.get('source_title'))
    raw_title_sim = SequenceMatcher(None, ta, tb).ratio()
    token_title_sim = title_similarity(a, b)

    groups_a = {g for g, terms in ISSUE_GROUPS.items() if any(t in sa for t in terms)}
    groups_b = {g for g, terms in ISSUE_GROUPS.items() if any(t in sb for t in terms)}
    shared_groups = groups_a & groups_b

    # 제목과 핵심 키워드가 거의 같은 기사
    if raw_title_sim >= 0.84 or token_title_sim >= 0.78:
        return True, '제목 핵심키워드 고유도 중복'

    # 희귀·중증 본인부담 정책은 세부 사례/최종 비율이 달라도 같은 발표 패키지로 묶는다.
    if 'rare_severe_policy' in shared_groups and '본인부담' in sa and '본인부담' in sb:
        if shared_numbers or '건강보험' in sa and '건강보험' in sb:
            return True, '희귀·중증 본인부담 동일 정책'

    # 상속 사건: 20억/10억/30% 및 가족관계가 일부만 겹쳐도 같은 사건으로 묶는다.
    if 'inheritance' in shared_groups:
        if len(shared_numbers) >= 1 and any(x in sa and x in sb for x in ['상속','유산','상속재산','유류분','맏아들','삼형제']):
            return True, '상속 동일 사건·금액'
        if len(shared_keywords) >= 6:
            return True, '상속 핵심키워드 중복'

    # 같은 이슈군 + 공통 숫자 + 핵심키워드. 예시만 달라진 기사도 포함.
    if shared_groups and len(shared_numbers) >= 1 and len(shared_keywords) >= 5:
        return True, '동일 이슈군·공통 숫자·키워드'

    # 숫자가 달라도 같은 정책/사건을 가리키는 강한 핵심어 중복
    if len(shared_keywords) >= 8 and token_title_sim >= 0.55:
        return True, '공통 핵심키워드 강한 중복'

    return False, ''


def representative_score(a):
    s = 0
    if a.get('origin_type') == 'official':
        s += 100
    if a.get('is_major_news'):
        s += 30
    t = article_text(a)
    for term, p in [('비급여',35),('고액 신약',35),('신약 치료비',35),('개인 의료비',30),('치료비 부담',30),('본인부담',25),('간병비',25),('상속재산',15)]:
        if term in t:
            s += p
    if a.get('title_alignment_pass') is True:
        s += 10
    return s


def strict_dedup(items):
    winners = []
    for a in sorted(items, key=representative_score, reverse=True):
        duplicate = next((w for w in winners if strict_same_issue(a, w)[0]), None)
        if duplicate:
            print(f'[엄격 중복 제거] {clean(a.get("title"))} -> {clean(duplicate.get("title"))}')
        else:
            winners.append(a)
    return winners


def category(a):
    r = clean(a.get('category')).lower().replace(' ', '_').replace('-', '_')
    aliases = {
        'policy':'policy','policies':'policy','제도':'policy','정책':'policy','보험제도':'policy',
        'medical':'medical','medicine':'medical','health':'medical','의료':'medical','의료비':'medical','보장':'medical','간병':'medical',
        'samsung_fire':'samsung_fire','samsungfire':'samsung_fire','samsung':'samsung_fire','삼성화재':'samsung_fire'
    }
    if r in aliases:
        return aliases[r]
    t = article_text(a)
    if a.get('origin_type') == 'official' and any(x in t for x in ['제도','정책','개편','개정','보험료','건강보험','보건복지','금융감독']):
        return 'policy'
    if '삼성화재' in t:
        return 'samsung_fire'
    return 'medical'


def topic(a):
    s = article_text(a)
    for g, terms in ISSUE_GROUPS.items():
        if any(t in s for t in terms):
            return g
    return 'other'


def organize(items):
    items = strict_dedup(items)
    c = {'policy':[], 'medical':[], 'samsung_fire':[]}
    for a in items:
        c[category(a)].append(a)

    c['policy'] = sorted(c['policy'], key=lambda x: (x.get('origin_type') != 'official', not x.get('is_major_news', False), -representative_score(x)))[:2]

    medical = []
    counts = {}
    for a in sorted(c['medical'], key=representative_score, reverse=True):
        tg = topic(a)
        cap = 1 if tg in {'rare_severe_policy','rare_copay_policy','inheritance','miscarriage'} else 2
        if counts.get(tg, 0) >= cap:
            continue
        if any(strict_same_issue(a, x)[0] for x in medical):
            continue
        medical.append(a)
        counts[tg] = counts.get(tg, 0) + 1
        if len(medical) >= 10:
            break
    c['medical'] = medical
    c['samsung_fire'] = strict_dedup(c['samsung_fire'])[:2]
    return c


def main():
    raw = prepare(load())
    print(f'전체 수집 뉴스: {len(raw)}개')

    def score(x):
        t = x['title'] + ' ' + x['description']
        s = (45 if x.get('origin_type') == 'official' else 0) + (15 if x.get('is_major_news') else 0)
        s += {'medical_cost':40,'caregiver':35,'product':30,'samsung_fire':25,'policy':15}.get(x.get('group'),0)
        s += 20 if any(z in t for z in ['의료비','치료비','본인부담','비급여','간병','암','뇌혈관','심혈관','유산','상속']) else 0
        return s

    cand = sorted([x for x in raw if not promo(x)], key=score, reverse=True)[:MAX_ANALYSIS_NEWS]
    print(f'AI 분석 대상: {len(cand)}개')
    by = {x['source_url']: x for x in cand}
    analyzed = []
    for i in range(0, len(cand), BATCH_SIZE):
        analyzed += analyze(cand[i:i+BATCH_SIZE], i//BATCH_SIZE+1)

    restored = [x for x in (restore(a, by) for a in analyzed) if x]
    print(f'AI 생성 결과: {len(restored)}개')
    checked = title_check(restored, by)
    print(f'제목-기사 상관관계 통과: {len(checked)}개')

    # 제목 검수 직후, 카테고리 분류 전에 전 범위 엄격 중복 제거
    checked = strict_dedup(checked)
    cats = organize(checked)

    out = {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'categories': cats,
        'sales_points': [a.get('sales_tip','') for a in checked if clean(a.get('sales_tip'))][:5],
        'article_count': sum(len(v) for v in cats.values()),
        'quality': {
            'strict_keyword_issue_dedup': True,
            'title_alignment_min_score': TITLE_ALIGNMENT_MIN_SCORE
        }
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'최종 기사: {out["article_count"]}개')


if __name__ == '__main__':
    main()
