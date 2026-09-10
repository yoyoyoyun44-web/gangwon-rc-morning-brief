import json
import re
from pathlib import Path

NEWS_FILE = Path('data/raw_news.json')
BACKUP_FILE = Path('data/raw_news_before_sales_filter.json')

# AI 분석 후보에서 아예 제외할 저가치 기사.
# 목적은 '의료 뉴스'가 아니라 '보험 상담에 바로 활용할 수 있는 뉴스'만 AI 슬롯을 사용하게 하는 것.
DONATION_TERMS = [
    '기부', '기부금', '기부활동', '기부 활동', '후원', '후원금', '후원 활동',
    '성금', '기탁', '나눔', '모금', '기부했다', '후원했다', '성금을 전달'
]
CELEBRITY_TERMS = [
    '배우', '가수', '방송인', '연예인', '아이돌', '스타', '유명인', '셀럽', '미담', '투병'
]
MEDICAL_STAFFING_TERMS = [
    '의료인력', '의료 인력', '보건사업 인력', '인력 공백', '인력 부족', '의료인력 부족',
    '의사 부족', '의사 인력', '간호인력', '간호 인력', '채용 절차', '인력 채용',
    '의료진 확보', '의료진 부족', '의료인력 확보', '의료인력 정책', '보건사업 인력',
    '의료인력 확충', '인력 확충', '의료진 채용'
]
PUBLIC_SERVICE_GAP_TERMS = [
    '공공의료', '공공 의료', '취약지역 소아 진료', '소아 진료 공백', '진료 공백 해소',
    '지역 의료 공백', '의료 공백 해소', '공공병원 인력', '의료 취약지역'
]
POLITICAL_ADMIN_TERMS = [
    '도의원', '시의원', '국회의원', '도지사', '시의회', '도의회', '군의회', '시의원',
    '예산 감액', '예산 증액', '채용 절차', '행정사무감사'
]

# 단순 연예/유명인 개인사 기사도 보험 상담 후보에서 제외.
PERSONAL_CELEBRITY_TERMS = [
    '암투병', '투병 사실', '투병 중', '건강 이상', '병원에 입원', '개인사', '가족사'
]

MEDICAL_VALUE_TERMS = [
    '의료비', '치료비', '본인부담', '비급여', '간병비', '간병 비용', '간병인',
    '고액 치료', '고액 약제', '신약', '보험급여', '건강보험 보장', '질환 치료',
    '암 치료', '항암', '뇌혈관', '뇌졸중', '뇌출혈', '뇌경색', '심혈관', '심근경색',
    '심장질환', '희귀질환', '난치질환', '중증질환', '중증·희귀', '상속', '유산'
]


def clean(v):
    return re.sub(r'\s+', ' ', str(v or '').replace('\n', ' ').replace('\r', ' ').strip())


def text(n):
    # 검색 결과의 제목/요약/출처 중심으로 판단한다. URL의 우연한 문자열은 제외.
    return clean(' '.join(str(n.get(k, '')) for k in ('title', 'description', 'source', 'publisher'))).lower()


def has_any(s, terms):
    return any(t.lower() in s for t in terms)


def classify(n):
    s = text(n)
    donation = has_any(s, DONATION_TERMS)
    celebrity = has_any(s, CELEBRITY_TERMS)
    staffing = has_any(s, MEDICAL_STAFFING_TERMS)
    public_gap = has_any(s, PUBLIC_SERVICE_GAP_TERMS)
    political = has_any(s, POLITICAL_ADMIN_TERMS)
    personal = has_any(s, PERSONAL_CELEBRITY_TERMS)
    medical_value = has_any(s, MEDICAL_VALUE_TERMS)

    # 기부/후원 기사는 예외 없이 AI 후보에서 제거한다.
    # 의료비 지원이라는 표현이 있더라도 '기부 활동' 자체가 핵심인 기사는 제외한다.
    if donation:
        return 'donation'

    if celebrity and personal and not medical_value:
        return 'celebrity_personal'

    if staffing and not medical_value:
        return 'medical_staffing'

    if public_gap and not medical_value:
        return 'public_service_gap'

    if political and any(x in s for x in ('예산', '채용', '인력', '보건사업', '행정')) and not medical_value:
        return 'political_admin'

    return None


def main():
    if not NEWS_FILE.exists():
        print('[사전 영업활용도 필터] raw_news.json 없음')
        return

    data = json.loads(NEWS_FILE.read_text(encoding='utf-8'))
    if isinstance(data, list):
        items = data
        wrapper = 'list'
    elif isinstance(data, dict):
        key = next((k for k in ('items', 'news', 'articles') if isinstance(data.get(k), list)), None)
        if not key:
            print('[사전 영업활용도 필터] 기사 배열을 찾지 못함')
            return
        items = data[key]
        wrapper = key
    else:
        print('[사전 영업활용도 필터] 지원하지 않는 JSON 구조')
        return

    # 원본은 디버깅용으로 보존한다.
    BACKUP_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    kept = []
    removed = []
    for n in items:
        if not isinstance(n, dict):
            kept.append(n)
            continue
        reason = classify(n)
        if reason:
            removed.append((clean(n.get('title')), reason))
        else:
            kept.append(n)

    if wrapper == 'list':
        output = kept
    else:
        data[wrapper] = kept
        output = data

    NEWS_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[사전 영업활용도 필터] 원본 {len(items)}개 → {len(kept)}개 / 제거 {len(removed)}개')
    for title, reason in removed[:30]:
        print(f'  - {reason}: {title}')
    if len(removed) > 30:
        print(f'  ... 외 {len(removed)-30}개')


if __name__ == '__main__':
    main()
