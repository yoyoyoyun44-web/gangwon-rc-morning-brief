import json
import re
from pathlib import Path

NEWS_FILE = Path('data/news.json')

# 보험 상담 소재로 보기 어려운 뉴스 유형.
# 단순히 의료라는 이유만으로 제거하지 않고, 제목/핵심내용에서 패턴이 함께 나타날 때 제외한다.
DONATION_TERMS = ['기부', '기부금', '후원', '성금', '기탁', '모교에', '모교에 기부', '나눔']
CELEBRITY_TERMS = ['배우', '가수', '방송인', '연예인', '아이돌', '스타', '유명인', '미담', '투병', '도와줬다', '도왔다']
PERSONAL_STORY_TERMS = ['부모 암투병', '아버지 암투병', '어머니 암투병', '부모님 암투병', '가족의 투병', '개인 미담']
MEDICAL_STAFFING_TERMS = [
    '의료인력', '의료 인력', '보건사업 인력', '인력 공백', '인력 부족', '의료인력 부족',
    '의사 부족', '의사 인력', '간호인력', '간호 인력', '채용 절차', '인력 채용',
    '의료진 확보', '의료진 부족', '의료인력 확보', '의료인력 정책', '보건사업 인력'
]
PUBLIC_SERVICE_GAP_TERMS = [
    '공공의료', '공공 의료', '취약지역 소아 진료', '소아 진료 공백', '진료 공백 해소',
    '지역 의료 공백', '의료 공백 해소', '공공의 진료', '공공병원 인력'
]
POLITICAL_ADMIN_TERMS = ['도의원', '시의원', '국회의원', '도지사', '시의회', '도의회', '예산 감액', '예산 증액', '채용 절차']
LOW_VALUE_REASON = {
    'donation': '연예인·유명인의 기부/후원 활동',
    'celebrity_personal': '연예인 개인사·투병 미담',
    'medical_staffing': '의료인력·채용·인력정책 중심 기사',
    'public_service_gap': '공공의료·지역 진료공백 중심 기사',
    'political_admin': '정치인·지자체 행정/예산 중심 기사',
}


def clean(v):
    return re.sub(r'\s+', ' ', str(v or '').replace('\n', ' ').replace('\r', ' ').strip())


def article_text(a):
    return clean(' '.join(str(a.get(k, '')) for k in ('source_title', 'title', 'core_topic', 'summary', 'why_it_matters', 'sales_tip'))).lower()


def classify(a):
    s = article_text(a)
    celebrity = any(x.lower() in s for x in CELEBRITY_TERMS)
    donation = any(x.lower() in s for x in DONATION_TERMS)
    personal = any(x.lower() in s for x in PERSONAL_STORY_TERMS)
    staffing = any(x.lower() in s for x in MEDICAL_STAFFING_TERMS)
    public_gap = any(x.lower() in s for x in PUBLIC_SERVICE_GAP_TERMS)
    political = any(x.lower() in s for x in POLITICAL_ADMIN_TERMS)

    # 연예인/유명인의 기부나 개인 투병 미담은 보험상담 소재가 아니므로 제외.
    if donation and celebrity:
        return 'donation'
    if personal and celebrity:
        return 'celebrity_personal'
    # 의료인력·채용·예산 공백이 핵심인 정책기사는 제외.
    if staffing and (political or any(x.lower() in s for x in ['인력', '채용', '예산'])):
        return 'medical_staffing'
    if public_gap and not any(x in s for x in ['의료비', '치료비', '본인부담', '비급여', '간병비']):
        return 'public_service_gap'
    if political and any(x in s for x in ['예산', '채용', '인력', '보건사업']):
        return 'political_admin'
    return None


def main():
    if not NEWS_FILE.exists():
        print('[영업 활용도 필터] news.json 없음')
        return
    data = json.loads(NEWS_FILE.read_text(encoding='utf-8'))
    cats = data.get('categories', {}) if isinstance(data, dict) else {}
    removed = []
    for key in ('policy', 'medical', 'samsung_fire'):
        items = cats.get(key, [])
        if not isinstance(items, list):
            continue
        kept = []
        for a in items:
            reason = classify(a) if isinstance(a, dict) else None
            if reason:
                removed.append((key, clean(a.get('title')), LOW_VALUE_REASON[reason]))
                continue
            kept.append(a)
        cats[key] = kept
    if removed:
        data['article_count'] = sum(len(v or []) for v in cats.values())
        q = data.setdefault('quality', {})
        q['sales_relevance_filter'] = True
        q['sales_relevance_removed_count'] = len(removed)
        data['quality']['sales_relevance_removed_reasons'] = [r for _, _, r in removed]
        NEWS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for key, title, reason in removed:
        print(f'[영업 활용도 필터 제거] {key}: {title} / {reason}')
    print(f'[영업 활용도 필터] 제거 {len(removed)}개')


if __name__ == '__main__':
    main()
