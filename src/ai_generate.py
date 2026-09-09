import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from google import genai

INPUT_FILE=Path('data/raw_news.json'); OUTPUT_FILE=Path('data/news.json')
API_KEY=os.getenv('GEMINI_API_KEY'); MODEL_NAME='gemini-3.6-flash'
MAX_ANALYSIS_NEWS=80; BATCH_SIZE=20; MAX_RETRIES_503=2; RETRY_DELAY_503=20; TITLE_ALIGNMENT_MIN_SCORE=65
if not API_KEY: raise RuntimeError('GEMINI_API_KEY 환경변수가 설정되어 있지 않습니다.')
client=genai.Client(api_key=API_KEY)
MAJOR_NEWS_DOMAINS={'chosun.com','joongang.co.kr','donga.com','hani.co.kr','hankookilbo.com','mk.co.kr','hankyung.com','sedaily.com','fnnews.com','newsis.com','yna.co.kr','news1.kr','edaily.co.kr','heraldcorp.com','asiae.co.kr','mt.co.kr','seoul.co.kr','khan.co.kr','nocutnews.co.kr','ytn.co.kr'}
OTHER_INSURER_NAMES=['현대해상','DB손해보험','메리츠화재','KB손해보험','한화손해보험','롯데손해보험','흥국화재','NH농협손해보험','하나손해보험','AXA손해보험','악사손해보험','캐롯손해보험','삼성생명','한화생명','교보생명','신한라이프','KB라이프','NH농협생명','미래에셋생명','동양생명','흥국생명','DB생명','ABL생명','푸본현대생명','라이나생명','AIA생명','메트라이프','처브라이프','KDB생명','iM라이프']
OTHER_INSURER_PROMO_TERMS=['신상품','상품 출시','출시','보장 강화','보장확대','보장 확대','가입자','체결','판매','판매 돌입','판매 개시','인기','히트상품','주력상품','대표상품','추천','특화상품','배타적사용권','배타적 사용권','상품 경쟁력','흥행','완판','판매실적','판매 실적','시장점유율']

def clean(v): return str(v or '').replace('\n',' ').replace('\r',' ').strip()
def load():
    with INPUT_FILE.open(encoding='utf-8') as f:d=json.load(f)
    if isinstance(d,list):return d
    if isinstance(d,dict):
        for k in ('items','news','articles'):
            if isinstance(d.get(k),list):return d[k]
    return []
def promo(a):
    t=f"{a.get('title','')} {a.get('description','')}"
    med=['의료비','치료비','비급여','본인부담','간병','환자','질환','건강보험','병원','신약','암','뇌혈관','심혈관']
    return any(x in t for x in OTHER_INSURER_NAMES) and any(x in t for x in OTHER_INSURER_PROMO_TERMS) and not any(x in t for x in med)
def prepare(items):
    out=[];seen=set()
    for n in items:
        if not isinstance(n,dict):continue
        u=clean(n.get('source_url') or n.get('originallink') or n.get('url'));t=clean(n.get('title'))
        if not u or not t or u in seen:continue
        seen.add(u);s=clean(n.get('source') or n.get('publisher'))
        out.append({'id':len(out)+1,'title':t,'description':clean(n.get('description')),'source_url':u,'naver_url':clean(n.get('naver_url') or n.get('link')),'published_at':clean(n.get('published_at') or n.get('pubDate') or n.get('publishedAt')),'source':s,'group':clean(n.get('group')),'is_major_news':bool(n.get('is_major_news')) or s in MAJOR_NEWS_DOMAINS,'origin_type':clean(n.get('origin_type')) or 'news','source_org':clean(n.get('source_org')),'source_org_name':clean(n.get('source_org_name'))})
    return out

PROMPT='''당신은 강원영업단 RC Morning Brief의 전문 편집자입니다. 고객 의료비 부담과 보장 공백에 도움이 되는 기사만 선별합니다. 공식기관 원자료를 우선 검토합니다. 카드뉴스 제목은 원문 핵심 주제와 정확히 일치해야 합니다.\n\n[보편적 이슈 중복 방지] 질환명이나 단어가 아니라 같은 실제 사건·정책·발표·연구·조사·통계·시범사업·제도변경인지 판단하십시오. 여러 언론의 재인용은 하나의 이슈로 묶으십시오. 같은 단어라도 실제 사건이 다르면 별도 기사입니다. 각 기사에 원문 사실만으로 짧은 issue_signature를 만드십시오. 동일 이슈가 여러 개면 공식기관 원자료, 상세 기사, 고객 의료비 부담이 구체적인 기사 순으로 대표 1개만 남기십시오.\n\n절대 제외: 다른 보험사 상품홍보/가입/판매/실적/시장점유율, GA 경쟁/이직/전환/수수료, 전속채널 위기, 주가/주식, 단순 실적, 자동차/여행/펫/휴대폰보험, 연예/정치 일반/사건사고, 광고/협찬.\n\n출력은 JSON 객체 하나. 각 기사 필드: category(policy|medical|samsung_fire), source_title, core_topic, title_topic, issue_signature, title_alignment_score, title_alignment_pass, title, summary, why_it_matters, sales_tip, source, published_at, source_url. 전체 최대 14개.'''

def prompt(batch):
    rows=[]
    for x in batch: rows.append(f"\n[NEWS_ID={x['id']}] 유형={x.get('origin_type')} 공식기관={x.get('source_org_name','')} 그룹={x.get('group')} 메이저={x.get('is_major_news')} 제목={x['title']} 내용={x['description']} 출처={x['source']} 발행={x['published_at']} URL={x['source_url']}")
    return PROMPT+''.join(rows)
def parse(t):
    t=(t or '').strip();t=re.sub(r'^```(?:json)?\s*','',t);t=re.sub(r'\s*```$','',t);return json.loads(t)
def analyze(batch,no,split=True):
    for i in range(MAX_RETRIES_503+1):
        try:
            r=client.models.generate_content(model=MODEL_NAME,contents=prompt(batch));a=parse(r.text).get('articles',[])
            if not isinstance(a,list):raise ValueError('articles 배열 아님')
            print(f'배치 {no}: {len(a)}개');return a
        except Exception as e:
            m=str(e)
            if '429' in m or 'RESOURCE_EXHAUSTED' in m:return []
            if ('503' in m or 'UNAVAILABLE' in m) and i<MAX_RETRIES_503:time.sleep(RETRY_DELAY_503);continue
            if split and len(batch)>5:
                k=len(batch)//2;return analyze(batch[:k],f'{no}A',False)+analyze(batch[k:],f'{no}B',False)
            print(f'Gemini 오류 {no}: {m}');return []
    return []
def restore(a,by):
    o=by.get(clean(a.get('source_url')))
    if not o:return None
    for k in ('source_url','published_at','source','naver_url','group','source_org','source_org_name'):a[k]=o.get(k,'')
    a['source_title']=o['title'];a['origin_type']=o.get('origin_type','news');a['is_major_news']=o.get('is_major_news',False);return a

def title_check(items,by):
    if not items:return []
    q='''원문 핵심주제와 카드뉴스 제목의 일치 여부를 검수하십시오. 후반부 보조 수치/사례를 메인화하면 불일치입니다. JSON checks 배열만 반환: {"source_url":"...","pass":true,"score":0,"reason":"..."}. 65 미만 pass=false.'''
    data=[{'source_url':by[clean(a.get('source_url'))]['source_url'],'source_title':by[clean(a.get('source_url'))]['title'],'source_description':by[clean(a.get('source_url'))]['description'],'generated_title':clean(a.get('title')),'core_topic':clean(a.get('core_topic'))} for a in items if clean(a.get('source_url')) in by]
    try:r=client.models.generate_content(model=MODEL_NAME,contents=q+'\n'+json.dumps(data,ensure_ascii=False));checks={clean(x.get('source_url')):x for x in parse(r.text).get('checks',[])}
    except Exception as e: raise RuntimeError(f'제목-기사 상관관계 검수 실패: {e}')
    out=[]
    for a in items:
        c=checks.get(clean(a.get('source_url')));score=min(int(a.get('title_alignment_score',0) or 0),int(c.get('score',0))) if c else 0;ok=bool(c and c.get('pass') is True and a.get('title_alignment_pass') is True and score>=TITLE_ALIGNMENT_MIN_SCORE);a['title_alignment_score']=score;a['title_alignment_pass']=ok;a['title_alignment_reason']=clean(c.get('reason')) if c else '검수 결과 없음'
        if ok:out.append(a)
    return out

GENERIC={'오늘','이번','관련','대한','통해','예상','전망','확대','강화','지원','부담','증가','감소','문제','논란','우려','필요','가능','환자','건강','의료','질환','치료','발생','확인','정부','당국','발표','정책','연구','조사','통계','기사','보험','보장','본인','부담금','최근','내년','올해'}
TOPICS={'health_policy':['건강보험료율','건강보험요율','건강보험료','보험료율','건강보험 재정','중증 희귀','희귀질환','난치질환','중증질환'],'miscarriage':['유산','자연유산','반복유산','반복 유산','유산 경험','유산율','유산 위험','계류유산'],'noncovered':['비급여','선별급여','본인부담','본인 부담'],'caregiver':['간병비','간병 비용','간병인 비용','간병 부담','가족 간병','간병 지원'],'cancer':['암 치료비','암 의료비','암 치료','항암','방사선','표적항암','면역항암'],'cerebrovascular':['뇌혈관','뇌졸중','뇌출혈','뇌경색'],'cardiovascular':['심혈관','심근경색','심장질환']}
TOPIC_MAX={'health_policy':1,'miscarriage':1}
BURDEN=[('고액 신약',70),('신약 치료비',70),('신약',60),('비급여',55),('개인 의료비 부담',55),('고액 치료비',50),('개인 부담',45),('본인부담 증가',45),('의료비 부담',45),('치료비 부담',45),('보장 공백',40),('민영보험',35),('보험 준비',30),('보험 보장',25),('치료비',25)]
def text(a):return ' '.join(clean(a.get(k)) for k in ('source_title','title','issue_signature','core_topic','summary','why_it_matters'))
def tokens(a):return {x for x in re.sub(r'[^0-9a-z가-힣 ]',' ',text(a).lower()).split() if len(x)>=2 and x not in GENERIC}
def overlap(a,b):
    x,y=tokens(a),tokens(b);return len(x&y)/min(len(x),len(y)) if x and y else 0
def sim(a,b):return SequenceMatcher(None,re.sub(r'[^0-9a-z가-힣 ]',' ',clean(a).lower()),re.sub(r'[^0-9a-z가-힣 ]',' ',clean(b).lower())).ratio()
def topic(a):
    t=text(a)
    for k,v in TOPICS.items():
        if any(x in t for x in v):return k
    return 'other'
def same_issue(a,b):
    title=sim(a.get('source_title') or a.get('title',''),b.get('source_title') or b.get('title',''));core=sim(a.get('core_topic',''),b.get('core_topic',''));ov=overlap(a,b);sig=overlap({'issue_signature':a.get('issue_signature','')},{'issue_signature':b.get('issue_signature','')})
    na=set(re.findall(r'\d+(?:\.\d+)?%?',text(a)));nb=set(re.findall(r'\d+(?:\.\d+)?%?',text(b)));shared_num=len(na&nb);shared_ent=len(tokens(a)&tokens(b))
    if sig>=.78 or title>=.84:return True
    if core>=.86 and ov>=.55:return True
    if ov>=.78 and shared_ent>=3:return True
    if ov>=.68 and shared_num>=1 and shared_ent>=3:return True
    ta,tb=topic(a),topic(b)
    return ta==tb and ta!='other' and ((title>=.68 and ov>=.50) or (core>=.72 and ov>=.55))
def rep_score(a):
    t=text(a);return sum(p for k,p in BURDEN if k in t)+(30 if a.get('origin_type')=='official' else 0)+(10 if a.get('is_major_news') else 0)
def universal_dedup(items):
    winners=[]
    for a in sorted(items,key=rep_score,reverse=True):
        d=next((x for x in winners if same_issue(a,x)),None)
        if d:print(f"[보편 이슈 중복 제외] {clean(a.get('title'))} -> 대표: {clean(d.get('title'))}")
        else:winners.append(a)
    return winners
def category(a):
    r=clean(a.get('category')).lower().replace(' ','_').replace('-','_');aliases={'policy':'policy','policies':'policy','제도':'policy','정책':'policy','보험제도':'policy','medical':'medical','medicine':'medical','health':'medical','의료':'medical','의료비':'medical','보장':'medical','간병':'medical','samsung_fire':'samsung_fire','samsungfire':'samsung_fire','samsung':'samsung_fire','삼성화재':'samsung_fire'}
    if r in aliases:return aliases[r]
    t=text(a)
    if a.get('origin_type')=='official' and any(x in t for x in ['제도','정책','개편','개정','보험료','건강보험','보건복지','금융감독']):return 'policy'
    if '삼성화재' in t:return 'samsung_fire'
    return 'medical'
def organize(items):
    c={'policy':[],'medical':[],'samsung_fire':[]}
    for a in items:c[category(a)].append(a)
    c['policy']=sorted(c['policy'],key=lambda x:(x.get('origin_type')!='official',not x.get('is_major_news',False)))[:2]
    m=universal_dedup(c['medical']);sel=[];cnt={}
    for a in sorted(m,key=rep_score,reverse=True):
        t=topic(a);cap=TOPIC_MAX.get(t,2)
        if cnt.get(t,0)>=cap or any(same_issue(a,x) for x in sel):continue
        sel.append(a);cnt[t]=cnt.get(t,0)+1
        if len(sel)>=10:break
    c['medical']=sel;c['samsung_fire']=universal_dedup(c['samsung_fire'])[:2];return c
def sales(c):
    out=[]
    for label,k in [('상품·보장/의료비','medical'),('삼성화재 소식','samsung_fire'),('제도 동향','policy')]:
        for a in c[k]:
            if clean(a.get('sales_tip')):out.append(f"{label}: {clean(a.get('sales_tip'))}")
            if len(out)>=5:return out
    return out

def main():
    raw=prepare(load());print(f'전체 수집 뉴스: {len(raw)}개')
    def score(x):
        t=x['title']+' '+x['description'];s=(45 if x.get('origin_type')=='official' else 0)+(15 if x.get('is_major_news') else 0)+{'medical_cost':40,'caregiver':35,'product':30,'samsung_fire':25,'policy':15}.get(x.get('group'),0);s+=20 if any(z in t for z in ['의료비','치료비','본인부담','비급여','간병','암','뇌혈관','심혈관','유산']) else 0;return s
    cand=sorted([x for x in raw if not promo(x)],key=score,reverse=True)[:MAX_ANALYSIS_NEWS];print(f'AI 분석 대상: {len(cand)}개')
    by={x['source_url']:x for x in cand};an=[]
    for i in range(0,len(cand),BATCH_SIZE):an+=analyze(cand[i:i+BATCH_SIZE],i//BATCH_SIZE+1)
    items=title_check(deduplicate([x for x in (restore(a,by) for a in an) if x]),by);items=universal_dedup(items);cats=organize(items)
    out={'generated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'categories':cats,'sales_points':sales(cats),'article_count':sum(len(v) for v in cats.values())};OUTPUT_FILE.parent.mkdir(parents=True,exist_ok=True);OUTPUT_FILE.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(f"최종 기사: {out['article_count']}개")
if __name__=='__main__':main()
