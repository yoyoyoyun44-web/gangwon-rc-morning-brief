import json
import os
import re
from pathlib import Path

RAW_FILE = Path('data/raw_news.json')
NEWS_FILE = Path('data/news.json')
MODEL_NAME = 'gemini-3.6-flash'

TOPIC_TERMS = {
    'cancer': ['암 치료비', '암 의료비', '암 치료', '항암', '방사선', '표적항암', '면역항암', '암 수술'],
    'cerebrovascular': ['뇌혈관', '뇌졸중', '뇌출혈', '뇌경색', '뇌혈관질환'],
    'cardiovascular': ['심혈관', '심근경색', '심장질환', '심혈관질환', '심장 수술', '심장 시술'],
    'caregiver': ['간병비', '간병인 비용', '간병 비용', '간병인 지원', '간병인지원', '가족 간병', '간병 부담', '요양병원 간병'],
}

TOPIC_LABEL = {'cancer': '암', 'cerebrovascular': '뇌혈관', 'cardiovascular': '심혈관', 'caregiver': '간병'}
EXCLUDE = ['GA', '주가', '주식', '광고', '협찬', '자동차보험', '여행보험', '펫보험', '휴대폰보험']
PROMO = ['신상품', '상품 출시', '보장 강화', '가입자', '체결', '판매 돌입', '판매 개시', '배타적사용권', '판매실적', '시장점유율']


def clean(v):
    return re.sub(r'\s+', ' ', str(v or '').replace('\n', ' ').replace('\r', ' ').strip())


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
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


def article_text(a):
    return clean(' '.join(str(a.get(k, '')) for k in ('title', 'source_title', 'core_topic', 'summary', 'description', 'why_it_matters', 'source')))


def has_topic(a, terms):
    return any(t in article_text(a) for t in terms)


def is_bad(a):
    s = article_text(a)
    if any(x in s for x in EXCLUDE):
        return True
    if any(x in s for x in PROMO) and not any(x in s for x in ['의료비', '치료비', '간병', '환자', '질환', '비급여']):
        return True
    return False


def candidate_pool(raw, topic, existing_urls):
    terms = TOPIC_TERMS[topic]
    seen = set(existing_urls)
    pool = []
    for a in raw:
        if not isinstance(a, dict) or is_bad(a):
            continue
        url = clean(a.get('source_url') or a.get('originallink') or a.get('url'))
        title = clean(a.get('title'))
        if not url or not title or url in seen:
            continue
        text = clean(f"{title} {a.get('description', '')}")
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
    return pool[:20]


def score_candidate(a, topic):
    s = 0
    text = article_text(a)
    title = clean(a.get('title'))
    terms = TOPIC_TERMS[topic]
    s += sum(10 for term in terms if term in title)
    s += sum(3 for term in terms if term in text)
    if a.get('origin_type') == 'official':
        s += 20
    if a.get('is_major_news'):
        s += 12
    if any(x in text for x in ['의료비', '치료비', '본인부담', '비급여']):
        s += 10
    if topic == 'caregiver' and any(x in text for x in ['간병비', '간병인 비용', '가족 간병', '간병 부담']):
        s += 12
    if topic in ('cancer', 'cerebrovascular', 'cardiovascular') and any(x in text for x in ['수술', '시술', '항암', '재활', '치료비']):
        s += 8
    return s


def build_deterministic_card(topic, src):
    label = TOPIC_LABEL[topic]
    title = src['title']
    description = src['description'] or f"{label} 관련 의료비·치료비 부담을 확인할 수 있는 주요 뉴스입니다."
    if topic == 'cancer':
        tip = f"기사의 핵심 내용과 관련해 고객에게 ‘{label} 진단 후 수술·항암·약물치료 과정에서 가장 걱정되는 비용이 무엇인지’ 물어보고 현재 보장을 점검해 보세요."
    elif topic == 'cerebrovascular':
        tip = f"기사의 핵심 내용과 관련해 고객에게 ‘{label}질환 발생 시 시술·수술·재활까지 이어지는 비용 중 무엇이 가장 부담스러운지’ 물어보고 보장을 점검해 보세요."
    elif topic == 'cardiovascular':
        tip = f"기사의 핵심 내용과 관련해 고객에게 ‘{label}질환으로 시술·수술을 받게 된다면 어떤 비용이 가장 걱정되는지’ 물어보고 보장을 점검해 보세요."
    else:
        tip = "기사의 핵심 내용과 관련해 고객에게 ‘입원이나 장기 치료가 필요할 때 간병비와 가족의 돌봄 부담을 어떻게 준비하고 있는지’ 물어보고 간병인지원 중심으로 보장을 점검해 보세요."
    return {
        'source_url': src['source_url'],
        'naver_url': src['naver_url'],
        'category': 'medical',
        'source_title': src['title'],
        'core_topic': f'{label} 관련 의료비·치료비 부담',
        'title_topic': label,
        'issue_signature': f'{label}|{src["title"]}',
        'title_alignment_score': 95,
        'title_alignment_pass': True,
        'title': title,
        'summary': description[:500],
        'why_it_matters': f'이번 기사는 {label} 분야의 실제 의료비·치료비 부담을 고객 관점에서 확인할 수 있는 상담 소재입니다.',
        'sales_tip': tip,
        'source': src['source_org_name'] or src['source'],
        'published_at': src['published_at'],
        'group': src['group'] or 'medical_cost',
        'origin_type': src['origin_type'],
        'source_org_name': src['source_org_name'],
        'is_major_news': src['is_major_news'],
    }


def make_prompt(topic, candidates):
    label = TOPIC_LABEL[topic]
    body = ''.join(
        f"\n[NEWS_ID={i+1}] 제목={a['title']} 내용={a['description']} 출처={a['source']} 발행={a['published_at']} URL={a['source_url']}"
        for i, a in enumerate(candidates)
    )
    return f'''당신은 강원영업단 RC Morning Brief 편집자입니다. '{label}'이 핵심 주제인 후보 중 고객 의료비 부담 상담에 가장 유용한 기사 1개만 선택하십시오. 원문에 없는 사실을 만들지 말고, 카드 제목은 원문 핵심 이슈와 정확히 일치시켜야 합니다. 광고·보험사 상품홍보·GA 경쟁·단순 판매실적은 제외하십시오. JSON 객체 하나만 반환하십시오.\n{{"article":{{"source_url":"정확한 후보 URL","category":"medical","source_title":"원문 제목","core_topic":"기사 핵심주제","title_topic":"카드 제목 주제","issue_signature":"실제 사건/정책/연구 서명","title_alignment_score":90,"title_alignment_pass":true,"title":"카드뉴스 제목","summary":"요약","why_it_matters":"고객에게 중요한 이유","sales_tip":"기사에 직접 연결된 고객 질문","source":"출처","published_at":"발행일"}}}}\n{body}'''


def rescue_with_gemini(topic, candidates):
    api_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not api_key:
        return None
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=MODEL_NAME, contents=make_prompt(topic, candidates))
        raw = (response.text or '').strip()
        raw = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw).strip()
        obj = json.loads(raw)
        article = obj.get('article') if isinstance(obj, dict) else None
        if not isinstance(article, dict):
            return None
        url = clean(article.get('source_url'))
        src = next((x for x in candidates if x['source_url'] == url), None)
        if not src:
            return None
        article['source_url'] = url
        article['source_title'] = src['title']
        article['source'] = src['source']
        article['published_at'] = src['published_at']
        article['naver_url'] = src['naver_url']
        article['group'] = src['group'] or 'medical_cost'
        article['origin_type'] = src['origin_type']
        article['source_org_name'] = src['source_org_name']
        article['is_major_news'] = src['is_major_news']
        return article
    except Exception as e:
        print(f'[Gemini 주제 보충 실패] {topic}: {e}')
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

    rescued = []
    for topic in TOPIC_TERMS:
        if any(has_topic(a, TOPIC_TERMS[topic]) for a in existing):
            print(f'[주제 확보] {topic}: 기존 기사 있음')
            continue
        candidates = candidate_pool(raw, topic, existing_urls)
        if not candidates:
            print(f'[주제 보충] {topic}: 후보 없음')
            continue
        candidates.sort(key=lambda a: score_candidate(a, topic), reverse=True)
        article = rescue_with_gemini(topic, candidates[:12])
        if article is None:
            article = build_deterministic_card(topic, candidates[0])
            print(f'[주제 보충] {topic}: GEMINI_API_KEY 없음/실패 → 원문 기반 안전 보충')
        if article:
            cats['medical'].append(article)
            existing.append(article)
            existing_urls.add(article['source_url'])
            rescued.append(article)
            print(f'[주제 보충 완료] {topic}: {article.get("title")}')

    if rescued:
        news['article_count'] = sum(len(v or []) for v in cats.values())
        quality = news.setdefault('quality', {})
        quality['protected_topic_rescue'] = True
        quality['protected_topics'] = ['cancer', 'cerebrovascular', 'cardiovascular', 'caregiver']
        quality['gemini_rescue_fallback'] = True
        NEWS_FILE.write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[주제 보충] 추가 기사 {len(rescued)}개')


if __name__ == '__main__':
    main()
