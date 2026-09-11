import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

import requests

OUT = Path("docs/index.html")
DATA = Path("data/weather.json")
API = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
KST = timezone(timedelta(hours=9))

# 기상청 5km 격자 기준 지역 중심 좌표
REGIONS = {
    "춘천": (73, 134),
    "원주": (76, 122),
    "인제": (81, 138),
    "양구": (78, 139),
    "영월": (86, 119),
    "태백": (95, 119),
    "여주": (71, 121),
    "가평": (69, 133),
    "화천": (72, 139),
}


def service_key():
    key = os.getenv("KMA_API_KEY", "").strip()
    return unquote(key) if key else ""


def base_datetime(now):
    # 단기예보 발표시각: 02, 05, 08, 11, 14, 17, 20, 23시
    candidates = [2, 5, 8, 11, 14, 17, 20, 23]
    t = now.replace(minute=0, second=0, microsecond=0)
    valid = [h for h in candidates if h <= t.hour]
    if valid:
        return now.strftime("%Y%m%d"), f"{max(valid):02d}00"
    prev = now - timedelta(days=1)
    return prev.strftime("%Y%m%d"), "2300"


def fetch_region(name, nx, ny, now, key):
    if not key:
        return {"name": name, "nx": nx, "ny": ny, "temp": None, "sky": "API 키 미설정", "hourly": [], "error": "KMA_API_KEY missing"}

    base_date, base_time = base_datetime(now)
    params = {
        "serviceKey": key,
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }
    try:
        response = requests.get(API, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        header = payload.get("response", {}).get("header", {})
        if header.get("resultCode") not in (None, "00"):
            raise RuntimeError(f"{header.get('resultCode')}: {header.get('resultMsg')}")
        items = payload.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        by_time = {}
        for item in items:
            fcst_date = item.get("fcstDate")
            fcst_time = item.get("fcstTime")
            if not fcst_date or not fcst_time:
                continue
            by_time.setdefault((fcst_date, fcst_time), {})[item.get("category")] = item.get("fcstValue")

        today = now.strftime("%Y%m%d")
        hourly = []
        for (date, tm), values in sorted(by_time.items()):
            if date != today:
                continue
            hour = int(tm[:2])
            if hour < now.hour:
                continue
            hourly.append({
                "time": f"{hour:02d}:00",
                "temp": values.get("TMP"),
                "sky": sky_text(values.get("SKY"), values.get("PTY")),
                "pty": values.get("PTY", "0"),
                "pop": values.get("POP"),
            })
            if len(hourly) >= 12:
                break

        current = hourly[0] if hourly else {}
        temp = current.get("temp")
        sky = current.get("sky") or "예보 확인 중"
        return {"name": name, "nx": nx, "ny": ny, "temp": temp, "sky": sky, "hourly": hourly, "error": None}
    except Exception as exc:
        return {"name": name, "nx": nx, "ny": ny, "temp": None, "sky": "조회 오류", "hourly": [], "error": str(exc)}


def sky_text(sky, pty):
    if pty and str(pty) != "0":
        return {"1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}.get(str(pty), "강수")
    return {"1": "맑음", "3": "구름 많음", "4": "흐림"}.get(str(sky), "예보 확인 중")


def build_html(data, now):
    raw = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    buttons = []
    for name, (nx, ny) in REGIONS.items():
        buttons.append(f'<button class="weather-pin" data-region="{name}" style="--x:{nx};--y:{ny}"><b>{name}</b><span class="weather-temp">-℃</span><small>불러오는 중</small></button>')
    section = f'''<section class="page weather-page" id="weather-page">
<div class="topline"><span>WEATHER / TODAY</span><span class="stamp">KMA FORECAST</span></div>
<div class="weather-kicker">강원·경기 주요 지역</div><h1>오늘의 날씨</h1>
<p class="weather-sub">지도에서 지역을 선택하면 오늘 시간대별 예보를 확인할 수 있습니다.</p>
<div class="weather-map"><div class="weather-map-shape"><div class="map-label">강원·경기<br><small>주요 지역 날씨</small></div></div>{''.join(buttons)}</div>
<div class="weather-detail" id="weather-detail">지역을 선택해 주세요.</div>
<div class="weather-note">기상청 단기예보 기준 · 업데이트 {now}</div>
<script>window.MORNING_WEATHER={raw};</script>
<script>(function(){{
const d=window.MORNING_WEATHER||{{}}; const box=document.getElementById('weather-detail');
function render(r){{const rows=(r.hourly||[]).map(x=>`<div class="hour-row"><b>${{x.time}}</b><span>${{x.sky}}</span><strong>${{x.temp??'-'}}℃</strong><small>강수 ${{x.pop??'-'}}%</small></div>`).join(''); box.innerHTML=`<div class="detail-title"><b>${{r.name}}</b><strong>${{r.temp??'-'}}℃</strong><span>${{r.sky}}</span></div><div class="hourly-list">${{rows||'<div>시간대별 예보가 없습니다.</div>'}}</div>`;}}
d.regions=(d.regions||[]); document.querySelectorAll('.weather-pin').forEach(b=>{{const r=d.regions.find(x=>x.name===b.dataset.region); if(!r)return; b.querySelector('.weather-temp').textContent=(r.temp??'-')+'℃'; b.querySelector('small').textContent=r.sky||'예보 확인 중'; b.addEventListener('click',()=>render(r));}});
}})();</script></section>'''
    text = OUT.read_text(encoding="utf-8") if OUT.exists() else "<div class=\"brief\"></div>"
    pattern = r'<section class="page weather-page" id="weather-page">.*?</section>'
    if re.search(pattern, text, flags=re.S):
        text = re.sub(pattern, section, text, count=1, flags=re.S)
    else:
        text = text.replace('<div class="brief">', '<div class="brief">' + section, 1)
    css = '''<style id="weather-style">.weather-page{background:#eef5fb;color:#12304d}.weather-page h1{font-size:clamp(34px,8vw,64px);margin:18px 0 8px}.weather-kicker{color:#1e6bb8;font-weight:700;margin-top:28px}.weather-sub{color:#58708a;margin-bottom:24px}.weather-map{position:relative;min-height:430px;border:1px solid #b9d5f2;border-radius:20px;background:linear-gradient(145deg,#dcecf9,#f7fbff);overflow:hidden}.weather-map-shape{position:absolute;inset:30px 25% 30px 25%;border:3px solid #8eb9df;border-radius:48% 42% 45% 38%;background:rgba(255,255,255,.5);transform:rotate(-8deg)}.map-label{position:absolute;inset:38% 0;text-align:center;color:#6d91b2;font-weight:800;font-size:20px;transform:rotate(8deg)}.map-label small{font-size:12px;font-weight:500}.weather-pin{position:absolute;left:calc(var(--x) * 1%);top:calc((145 - var(--y)) * 2.5%);transform:translate(-50%,-50%);min-width:82px;border:1px solid #8fbce2;background:#fff;border-radius:14px;padding:8px 7px;text-align:center;color:#12304d;box-shadow:0 4px 12px rgba(50,100,150,.12);cursor:pointer}.weather-pin b,.weather-pin span,.weather-pin small{display:block}.weather-pin span{font-size:21px;font-weight:800;margin:2px 0}.weather-pin small{font-size:11px;color:#58708a;white-space:nowrap}.weather-detail{margin-top:20px;padding:18px;border-radius:16px;background:#fff;border:1px solid #b9d5f2;min-height:70px}.detail-title{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}.detail-title b{font-size:24px}.detail-title strong{font-size:30px}.detail-title span{color:#58708a}.hourly-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px;margin-top:15px}.hour-row{border:1px solid #d8e7f5;border-radius:10px;padding:9px;display:grid;grid-template-columns:1fr auto;gap:3px}.hour-row span{color:#58708a}.hour-row strong{text-align:right}.hour-row small{grid-column:1/-1;color:#58708a}.weather-note{margin-top:18px;color:#58708a;font-size:12px}@media(max-width:700px){.weather-map{min-height:520px}.weather-pin{min-width:72px;font-size:12px}.weather-map-shape{inset:45px 20% 45px 20%}}@media(max-width:520px){.weather-map{min-height:560px}.weather-pin{min-width:66px;padding:7px 4px}.weather-pin span{font-size:18px}} </style>'''
    if 'id="weather-style"' in text:
        text = re.sub(r'<style id="weather-style">.*?</style>', css, text, count=1, flags=re.S)
    else:
        text = text.replace('</head>', css + '</head>', 1)
    OUT.write_text(text, encoding="utf-8")


def main():
    now = datetime.now(KST)
    key = service_key()
    regions = [fetch_region(name, nx, ny, now, key) for name, (nx, ny) in REGIONS.items()]
    data = {"updated_at": now.isoformat(), "source": "기상청 단기예보 조회서비스", "regions": regions}
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    build_html(data, now.strftime("%Y-%m-%d %H:%M KST"))
    print(json.dumps({"updated_at": data["updated_at"], "regions": [{"name": r["name"], "temp": r["temp"], "sky": r["sky"], "error": r["error"]} for r in regions]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
