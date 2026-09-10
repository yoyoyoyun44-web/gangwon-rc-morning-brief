import json
import os
import re
import subprocess
import sys
from pathlib import Path
from google import genai

RAW_FILE = Path('data/raw_news.json')
NEWS_FILE = Path('data/news.json')
MODEL_NAME = 'gemini-3.6-flash'

TOPIC_TERMS = {
    'cancer': ['암 치료비', '암 의료비', '암 치료', '항암', '방사선', '표적항암', '면역항암', '암 수술'],
    'cerebrovascular': ['뇌혈관', '뇌졸중', '뇌출혈', '뇌경색', '뇌혈관질환'],
    'cardiovascular': ['심혈관', '심근경색', '심장질환', '심혈관질환', '심장 수술', '심장 시술'],
    'caregiver': ['간병비', '간병인 비용', '간병 비용', '간병인 지원', '간병인지원', '가족 간병', '간병 부담', '요양병원 간병'],
}

EXCLUDE = ['GA', '주가', '주식', '광고', '협찬', '자동차보험', '여행보험', '펫보험', '휴대폰보험']
PROMO = ['신상품', '상품 출시', '보장 강화', '가입자', '체결', '판매 돌입', '판매 개시', '배타적사용권', '판매실적', '시장점유율']


def clean(v):
    return re.sub(r'\s+', ' ', str(v or '').replace('\n', ' ').replace('\r', ' ').strip())


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with path.open(encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default


def current_articles(data):
    if not isinstance(data, dict):
        return []
    cats = data.get('categories', {})
    out = []
    for key in ('policy', 'medical', 'samsung_fire'):
        if isinstance(cats.get(key), list):
            out.extend(cats[key])
    return out


def has_topic(a, terms):
    s = clean(f"{a.get('title','')} {a.get('source_title','')} {a.get('core_topic','')} {a.get('summary','')} {a.get('why_it_matters','')}")
    return any(t in s for t in terms)


def is_bad(a):
    s = clean(f"{a.get('title','')} {a.get('description','')} {a.get('source','')}")
    if any(x in s for x in EXCLUDE):
        return True
    if any(x in s for x in PROMO) and not any(x in s for x in ['의료비', '치료비', '간병', '환자', '질환', '비급여']):
        return True
    return False


def candidate_pool(raw, topic, existing_urls):
    terms = TOPIC_TERMS[topic]
    pool = []
    seen = set(existing_urls)
    for a in raw:
        if not isinstance(a, dict) or is_bad(a):
            continue
        url = clean(a.get('source_url') or a.get('originallink') or a.get('url'))
        title = clean(a.get('title'))
        if not url or not title or url in seen:
            continue
        text = clean(f"{title} {a.get('description','')}")
        if not any(t in text for t in terms):
            continue
        pool.append({
            'title': title,
            'description': clean(a.get('description')),
            'source_url': url,
            'naver_url': clean(a.get('naver_url') or a.get('link')),
            'published_at': clean(a.get('published_at') or a.get('pubDate')),
            'source': clean(a.get('source') or a.get('publisher')),
            'group': clean(a.get('group')),
            'origin_type': clean(a.get('origin_type')) or 'news',
            'source_org_name': clean(a.get('source_org_name')),
            'is_major_news': bool(a.get('is_major_news')),
        })
        seen.add(url)
        if len(pool) >= 12:
            break
    return pool


def make_prompt(topic, candidates):
    label = {'cancer':'암', 'cerebrovascular':'뇌혈관', 'cardiovascular':'심혈관', 'caregiver':'간병'}[topic]
    body = ''.join(
        f"\n[NEWS_ID={i+1}] 제목={a['title']} 내용={a['description']} 출처={a['source']} 발행={a['published_at']} URL={a['source_url']}"
        for i, a in enumerate(candidates)
    )
    return f'''당신은 강원영업단 RC Morning Brief 편집자입니다.
이번 작업은 반드시 '{label}' 분야의 실제 뉴스가 현재 Morning Brief에 하나도 없을 때만 수행하는 보충 작업입니다.
후보 기사 중 고객의 의료비·치료비·간병 부담을 이해하는 데 가장 유용한 실제 기사 딱 1개만 선택하십시오.

중요 규칙:
1. 후보 원문 제목과 내용에 실제로 존재하는 사실만 사용하십시오.
2. 원문 핵심 이슈와 카드뉴스 제목이 정확히 일치해야 합니다. 후반부 보조 사례나 숫자를 메인 이슈로 만들지 마십시오.
3. 광고, 보험사 상품홍보, 단순 판매실적, GA 경쟁 뉴스는 제외하십시오.
4. 같은 사건을 다룬 재인용 기사보다 공식기관/메이저 언론의 원자료성 높은 기사를 우선하십시오.
5. '{label}' 자체가 핵심 주제인 기사만 선택하십시오. 단순히 기사 본문에 '{label}'이라는 단어가 한 번 나온 기사는 선택하지 마십시오.
6. sales_tip은 해당 기사에서 직접 도출한 고객 질문이어야 합니다. 범용 문구를 금지합니다.

JSON 객체 하나만 반환하십시오.
{{"article":{{"source_url":"정확한 후보 URL","category":"medical","source_title":"원문 제목","core_topic":"기사 핵심주제","title_topic":"카드 제목이 다루는 주제","issue_signature":"실제 사건/정책/연구를 식별하는 짧은 고유 서명","title_alignment_score":90,"title_alignment_pass":true,"title":"카드뉴스 제목","summary":"요약","why_it_matters":"고객에게 중요한 이유","sales_tip":"기사에 직접 연결된 오늘의 영업 Tip","source":"출처","published_at":"발행일"}}}}
{body}'''


def rescue_topic(client, topic, candidates):
    try:
        r = client.models.generate_content(model=MODEL_NAME, contents=make_prompt(topic, candidates))
        obj = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', (r.text or '').strip()))
        a = obj.get('article') if isinstance(obj, dict) else None
        if not isinstance(a, dict):
            return None
        url = clean(a.get('source_url'))
        src = next((x for x in candidates if x['source_url'] == url), None)
        if not src:
            return None
        a['source_url'] = url
        a['source_title'] = src['title']
        a['source'] = src['source']
        a['published_at'] = src['published_at']
        a['naver_url'] = src['naver_url']
        a['group'] = src['group'] or 'medical_cost'
        a['origin_type'] = src['origin_type']
        a['source_org_name'] = src['source_org_name']
        a['is_major_news'] = src['is_major_news']
        return a
    except Exception as e:
        print(f'[주제 보충 실패] {topic}: {e}')
        return None


def main():
    raw_data = load_json(RAW_FILE, {})
    raw = raw_data.get('articles', []) if isinstance(raw_data, dict) else raw_data
    news = load_json(NEWS_FILE, {'categories': {'policy': [], 'medical': [], 'samsung_fire': []}})
    cats = news.setdefault('categories', {})
    for key in ('policy', 'medical', 'samsung_fire'):
        cats.setdefault(key, [])
    existing = current_articles(news)
    existing_urls = {clean(a.get('source_url')) for a in existing}
    client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])

    rescued = []
    for topic in TOPIC_TERMS:
        if any(has_topic(a, TOPIC_TERMS[topic]) for a in existing):
            print(f'[주제 확보] {topic}: 기존 기사 있음')
            continue
        candidates = candidate_pool(raw, topic, existing_urls)
        if not candidates:
            print(f'[주제 보충] {topic}: 후보 없음')
            continue
        a = rescue_topic(client, topic, candidates)
        if a:
            cats['medical'].append(a)
            existing.append(a)
            existing_urls.add(a['source_url'])
            rescued.append(a)
            print(f'[주제 보충 완료] {topic}: {a.get("title")}')

    if rescued:
        news['article_count'] = sum(len(v) for v in cats.values())
        news.setdefault('quality', {})['protected_topic_rescue'] = True
        news['quality']['protected_topics'] = ['cancer', 'cerebrovascular', 'cardiovascular', 'caregiver']
        NEWS_FILE.write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[주제 보충] 추가 기사 {len(rescued)}개')


if __name__ == '__main__':
    main()
