import json,re
from pathlib import Path
NEWS_FILE=Path('data/raw_news.json'); BACKUP_FILE=Path('data/raw_news_before_sales_filter.json')
DROP=[
'기부','기부금','후원','성금','기탁','나눔','모금','한림화상재단','복지상','심포지엄','학술대회','학회','국제 심포지엄',
'주가','주식','투자','자본배분','지분','경영권','유상증자','목표주가','시가총액','주주','기관 매수','외국인 매수',
'의료인력','의료 인력','의료진 채용','간호인력','간호 인력','의사 부족','채용 절차','인력 확충','병원 운영','진료 공백',
'국회의원','도의원','시의원','도지사','시의회','도의회','군의회','정치','로비','청탁','고발인','후보자','법무부 장관',
'정밀의료 바이오마커','연구 협력','공동연구','파트너십','MOU','업무협약','임상시험 진행','임상 1상','임상 2상','임상 3상','임상 결과','FDA 심사','허가 신청','학회 발표','기술이전','신약개발','개발 진척','개발 착수','연구팀','연구진'
]
KEEP_VALUE=['의료비','치료비','수술비','본인부담','본인 부담','비급여','간병비','간병인','간병인지원','고액 치료','고가 치료','고액 약제','보험급여','급여 적용','환자 부담','치료 부담','경제적 부담','반복 치료','장기 치료']
def clean(v): return re.sub(r'\s+',' ',str(v or '').replace('\n',' ').replace('\r',' ').strip())
def text(n): return clean(' '.join(str(n.get(k,'')) for k in ('title','description','source','publisher'))).lower()
def classify(n):
 s=text(n); hits=[x for x in DROP if x.lower() in s]; value=any(x.lower() in s for x in KEEP_VALUE)
 if any(x in s for x in ['주가','주식','투자','자본배분','지분','경영권','유상증자','목표주가','시가총액','주주','기관 매수','외국인 매수']): return 'stock'
 if any(x in s for x in ['기부','후원','성금','기탁','나눔','모금','복지상','재단']): return 'donation'
 if any(x in s for x in ['국회의원','도의원','시의원','도지사','시의회','도의회','군의회','로비','청탁','고발인','후보자','정치']): return 'political'
 if any(x in s for x in ['의료인력','의료 인력','의료진 채용','간호인력','의사 부족','채용 절차','인력 확충','병원 운영','진료 공백']): return 'staffing'
 if any(x.lower() in s for x in DROP[20:]) and not value: return 'development_or_professional'
 return None
def main():
 if not NEWS_FILE.exists(): return
 data=json.loads(NEWS_FILE.read_text(encoding='utf-8')); BACKUP_FILE.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 if isinstance(data,list): items=data; wrapper='list'
 else:
  wrapper=next((k for k in ('items','news','articles') if isinstance(data.get(k),list)),None)
  if not wrapper: return
  items=data[wrapper]
 kept=[]; removed=[]
 for n in items:
  reason=classify(n) if isinstance(n,dict) else None
  if reason: removed.append((clean(n.get('title')),reason))
  else: kept.append(n)
 if wrapper=='list': out=kept
 else: data[wrapper]=kept; out=data
 NEWS_FILE.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(f'[사전 RC영업 필터] {len(items)}개 → {len(kept)}개 / 제거 {len(removed)}개')
 for t,r in removed[:50]: print(f'  - {r}: {t}')
if __name__=='__main__': main()
