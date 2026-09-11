import json, os
from datetime import datetime, timezone, timedelta
from pathlib import Path
OUT=Path('docs/index.html'); DATA=Path('data/weather.json')
REGIONS=['춘천','원주','인제','양구','영월','태백','여주','가평','화천']
def main():
 now=datetime.now(timezone(timedelta(hours=9))).isoformat()
 data={'updated_at':now,'regions':[{'name':n,'temp':None,'sky':'기상청 API 연결 필요','hourly':[]} for n in REGIONS]}
 DATA.parent.mkdir(exist_ok=True); DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 if not OUT.exists(): return
 text=OUT.read_text(encoding='utf-8')
 if 'id="weather-page"' in text: return
 cards=''.join(f'<button class="weather-pin" data-region="{n}"><b>{n}</b><span>-℃</span><small>예보 확인 중</small></button>' for n in REGIONS)
 section=f'''<section class="page weather-page" id="weather-page"><div class="topline"><span>WEATHER / TODAY</span><span class="stamp">KMA FORECAST</span></div><div class="weather-kicker">강원·경기 주요 지역</div><h1>오늘의 날씨</h1><p class="weather-sub">지역을 선택하면 시간대별 예보를 확인할 수 있습니다.</p><div class="weather-map">{cards}</div><div class="weather-detail" id="weather-detail">지역을 선택해 주세요.</div><div class="weather-note">기상청 단기예보 기준 · 업데이트 {now}</div><script>window.MORNING_WEATHER={json.dumps(data,ensure_ascii=False)};</script><script>(function(){{const d=window.MORNING_WEATHER;const box=document.getElementById('weather-detail');document.querySelectorAll('.weather-pin').forEach(b=>b.addEventListener('click',()=>{{const r=d.regions.find(x=>x.name===b.dataset.region);box.innerHTML='<b>'+r.name+'</b><br>'+r.sky+'<br>상세 시간대별 예보는 API 연결 후 표시됩니다.';}}));}})();</script></section>'''
 text=text.replace('<div class="brief">','<div class="brief">'+section,1)
 text=text.replace('</style>','''.weather-page{background:#eef5fb;color:#12304d}.weather-page h1{font-size:clamp(34px,8vw,64px);margin:18px 0 8px}.weather-kicker{color:#1e6bb8;font-weight:700;margin-top:28px}.weather-sub{color:#58708a;margin-bottom:24px}.weather-map{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.weather-pin{border:1px solid #b9d5f2;background:#fff;border-radius:16px;padding:16px 10px;text-align:left;color:#12304d}.weather-pin b,.weather-pin span,.weather-pin small{display:block}.weather-pin span{font-size:25px;font-weight:800;margin:5px 0}.weather-pin small{color:#58708a}.weather-detail{margin-top:20px;padding:18px;border-radius:16px;background:#fff;border:1px solid #b9d5f2;min-height:70px}.weather-note{margin-top:18px;color:#58708a;font-size:12px}@media(max-width:520px){.weather-map{grid-template-columns:repeat(2,minmax(0,1fr))}}\n</style>''',1)
 OUT.write_text(text,encoding='utf-8')
if __name__=='__main__': main()
