import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote
import requests

OUT = Path('docs/index.html')
DATA = Path('data/weather.json')
API = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst'
KST = timezone(timedelta(hours=9))
REGIONS = {'춘천':(73,134),'원주':(76,122),'인제':(81,138),'양구':(78,139),'영월':(86,119),'태백':(95,119),'정선':(89,115),'평창':(84,122),'여주':(71,121),'가평':(69,133),'화천':(72,139)}

def service_key(): return unquote(os.getenv('KMA_API_KEY','').strip())
def base_datetime(now):
    slots=[2,5,8,11,14,17,20,23]; valid=[h for h in slots if h<=now.hour]
    return (now.strftime('%Y%m%d'),f'{max(valid):02d}00') if valid else ((now-timedelta(days=1)).strftime('%Y%m%d'),'2300')
def sky_text(sky,pty):
    if str(pty or '0')!='0': return {'1':'비','2':'비/눈','3':'눈','4':'소나기'}.get(str(pty),'강수')
    return {'1':'맑음','3':'구름 많음','4':'흐림'}.get(str(sky),'예보 확인 중')
def fetch_region(name,nx,ny,now,key):
    r={'name':name,'nx':nx,'ny':ny,'temp':None,'sky':'예보 확인 중','hourly':[],'error':None}
    if not key: r.update(sky='API 키 미설정',error='KMA_API_KEY missing'); return r
    bd,bt=base_datetime(now); params={'serviceKey':key,'pageNo':1,'numOfRows':1000,'dataType':'JSON','base_date':bd,'base_time':bt,'nx':nx,'ny':ny}
    try:
        p=requests.get(API,params=params,timeout=20).json(); h=p.get('response',{}).get('header',{})
        if h.get('resultCode') not in (None,'00'): raise RuntimeError(f"{h.get('resultCode')}: {h.get('resultMsg')}")
        items=p.get('response',{}).get('body',{}).get('items',{}).get('item',[]); items=[items] if isinstance(items,dict) else items; grouped={}
        for x in items:
            if x.get('fcstDate') and x.get('fcstTime'): grouped.setdefault((x['fcstDate'],x['fcstTime']),{})[x.get('category')]=x.get('fcstValue')
        today=now.strftime('%Y%m%d')
        for (date,tm),v in sorted(grouped.items()):
            if date!=today or int(tm[:2])<now.hour: continue
            r['hourly'].append({'time':f'{tm[:2]}:{tm[2:]}','temp':v.get('TMP'),'sky':sky_text(v.get('SKY'),v.get('PTY')),'pop':v.get('POP')})
            if len(r['hourly'])>=12: break
        if r['hourly']: r['temp'],r['sky']=r['hourly'][0]['temp'],r['hourly'][0]['sky']
        else: r['sky']='예보 없음'
    except Exception as e: r.update(sky='조회 오류',error=str(e)[:240])
    return r

def build_html(data,stamp):
    raw=json.dumps(data,ensure_ascii=False).replace('</','<\\/')
    cards=''.join(f'<button class="weather-card" data-region="{n}"><span class="weather-name">{n}</span><strong class="weather-temp">-℃</strong><small>불러오는 중</small></button>' for n in REGIONS)
    section=f'''<section class="page weather-page" id="weather-page"><div class="topline"><span>WEATHER / TODAY</span><span class="stamp">KMA FORECAST</span></div><div class="weather-kicker">강원·경기 주요 지역</div><h1>오늘의 날씨</h1><p class="weather-sub">지역별 날씨를 한눈에 확인하고, 지역을 누르면 시간대별 예보를 볼 수 있습니다.</p><div class="weather-grid">{cards}</div><div class="weather-detail" id="weather-detail">지역을 선택해 주세요.</div><div class="weather-note">기상청 단기예보 기준 · 업데이트 {stamp}</div><script>window.MORNING_WEATHER={raw};</script><script>(function(){{const d=window.MORNING_WEATHER||{{}},box=document.getElementById('weather-detail');function render(r){{const rows=(r.hourly||[]).map(x=>`<div class="hour-row"><b>${{x.time}}</b><span>${{x.sky}}</span><strong>${{x.temp??'-'}}℃</strong><small>강수 ${{x.pop??'-'}}%</small></div>`).join('');box.innerHTML=`<div class="detail-title"><b>${{r.name}}</b><strong>${{r.temp??'-'}}℃</strong><span>${{r.sky}}</span></div><div class="hourly-list">${{rows||'시간대별 예보가 없습니다.'}}</div>`;}}(d.regions||[]).forEach(r=>{{const b=document.querySelector(`[data-region="${{r.name}}"]`);if(!b)return;b.querySelector('.weather-temp').textContent=(r.temp??'-')+'℃';b.querySelector('small').textContent=r.sky||'예보 확인 중';b.addEventListener('click',()=>render(r));}});}})();</script></section>'''
    text=OUT.read_text(encoding='utf-8') if OUT.exists() else '<html><head></head><body></body></html>'; pattern=r'<section class="page weather-page" id="weather-page">.*?</section>'
    if re.search(pattern,text,re.S): text=re.sub(pattern,section,text,count=1,flags=re.S)
    else:
        old=text; text=text.replace('<div class="brief">','<div class="brief">'+section,1)
        if text==old: text=text.replace('</body>',section+'</body>',1)
    css='''<style id="weather-style">.weather-page{background:#eef5fb;color:#12304d}.weather-page h1{font-size:clamp(34px,8vw,64px);margin:18px 0 8px}.weather-kicker{color:#1e6bb8;font-weight:700;margin-top:28px}.weather-sub{color:#58708a;margin-bottom:24px}.weather-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.weather-card{min-height:105px;border:1px solid #b9d5f2;background:#fff;border-radius:16px;padding:13px 8px;text-align:center;color:#12304d;cursor:pointer;box-shadow:0 3px 10px rgba(50,100,150,.08)}.weather-card:hover{border-color:#4d98d1}.weather-name,.weather-card strong,.weather-card small{display:block}.weather-name{font-weight:800;font-size:16px}.weather-card strong{font-size:27px;margin:7px 0 3px}.weather-card small{font-size:11px;color:#58708a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.weather-detail{margin-top:20px;padding:18px;border-radius:16px;background:#fff;border:1px solid #b9d5f2;min-height:70px}.detail-title{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}.detail-title b{font-size:24px}.detail-title strong{font-size:30px}.detail-title span{color:#58708a}.hourly-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:8px;margin-top:15px}.hour-row{border:1px solid #d8e7f5;border-radius:10px;padding:9px;display:grid;grid-template-columns:1fr auto;gap:3px}.hour-row span{color:#58708a}.hour-row strong{text-align:right}.hour-row small{grid-column:1/-1;color:#58708a}.weather-note{margin-top:18px;color:#58708a;font-size:12px}@media(max-width:700px){.weather-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.weather-card{min-height:96px}.weather-name{font-size:14px}.weather-card strong{font-size:23px}}@media(max-width:420px){.weather-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>'''
    if 'id="weather-style"' in text: text=re.sub(r'<style id="weather-style">.*?</style>',css,text,count=1,flags=re.S)
    else: text=text.replace('</head>',css+'</head>',1)
    OUT.write_text(text,encoding='utf-8')

def main():
    now=datetime.now(KST); regions=[fetch_region(n,x,y,now,service_key()) for n,(x,y) in REGIONS.items()]; data={'updated_at':now.isoformat(),'source':'기상청 단기예보 조회서비스','regions':regions}
    DATA.parent.mkdir(exist_ok=True); DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); build_html(data,now.strftime('%Y-%m-%d %H:%M KST'))
    for r in regions: print(f"{r['name']}: {r.get('temp')} / {r.get('sky')} / {r.get('error')}")
if __name__=='__main__': main()
