import json
import html
from datetime import datetime
from pathlib import Path

INPUT_FILE = Path("data/news.json")
OUTPUT_FILE = Path("docs/index.html")

CATEGORY_INFO = {
    "policy": ("01", "제도 동향", "policy"),
    "medical": ("02", "의료비 이슈", "medical"),
    "samsung_fire": ("03", "삼성화재 소식", "samsung"),
}


def esc(value):
    return html.escape(str(value or ""), quote=True)


def format_date(value):
    value = str(value or "")
    if not value:
        return "발행일 미상"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y.%m.%d %H:%M")
    except ValueError:
        return value[:16].replace("T", " ")


def article_page(article, category_key, number):
    num, badge, css = CATEGORY_INFO[category_key]
    title = esc(article.get("title"))
    summary = esc(article.get("summary"))
    why = esc(article.get("why_it_matters"))
    tip = esc(article.get("sales_tip"))
    source = esc(article.get("source"))
    published = format_date(article.get("published_at"))
    source_url = article.get("source_url") or article.get("naver_url")
    source_url = esc(source_url)
    return f'''<section class="page article-page {css}">
  <div class="topline"><span>{num} / {number:02d}</span><span class="stamp">MORNING BRIEF</span></div>
  <div class="badge">{badge}</div>
  <h1>{title}</h1>
  <div class="meta">{published} · {source}</div>
  <div class="rule"></div>
  <p class="summary">{summary}</p>
  <div class="why"><div class="label">WHY IT MATTERS</div><div>{why}</div></div>
  <div class="tip"><div class="tip-title">오늘의 영업 Tip</div><div>{tip}</div></div>
  <a class="source" href="{source_url}" target="_blank" rel="noopener noreferrer">NAVER 원문 기사 보기 →</a>
  <div class="swipe">← 좌우로 스와이프 →</div>
</section>'''


def cover_page(date_text, counts):
    toc = "".join(
        f'<div class="toc-row"><span>{num}　{label}</span><b>{counts.get(key, 0)}건</b></div>'
        for key, (num, label, _) in CATEGORY_INFO.items()
        if counts.get(key, 0) > 0
    )
    return f'''<section class="page cover">
  <div class="cover-head"><span>GANGWON SALES DIVISION</span><span class="stamp">DAILY DOSSIER</span></div>
  <div class="cover-main">
    <div class="gold">강원영업단 RC를 위한</div>
    <h1>Morning<br><span>Brief</span></h1>
    <div class="date">{esc(date_text)}</div>
  </div>
  <div class="toc"><div class="toc-title">CONTENTS</div>{toc}</div>
  <div class="cover-foot">보험 · 의료 · 영업 인사이트　|　Swipe →</div>
</section>'''


def closing_page(points):
    if not points:
        points = ["오늘 뉴스 중 고객의 건강·의료비 걱정과 연결할 수 있는 주제를 하나 골라 대화를 시작해 보세요."]
    rows = "".join(
        f'<div class="point"><span>{i:02d}</span><p>{esc(p)}</p></div>'
        for i, p in enumerate(points[:5], 1)
    )
    return f'''<section class="page closing">
  <div class="closing-stamp">TODAY'S SALES POINT</div>
  <div class="gold">GANGWON SALES DIVISION</div>
  <h1>오늘의 영업<br><span>활용 포인트</span></h1>
  <p class="closing-sub">뉴스를 설명하는 것이 아니라, 고객의 걱정을 묻는 소재로 활용하세요.</p>
  <div class="points">{rows}</div>
  <div class="closing-message"><b>오늘 고객에게 던질 질문 하나를<br>뉴스에서 찾아보세요.</b></div>
</section>'''


def generate_html(data):
    categories = data.get("categories", {})
    # 과거 포맷(data.policy...)도 안전하게 읽을 수 있도록 보정
    if not categories and isinstance(data.get("data"), dict):
        categories = data["data"]

    date_text = datetime.now().strftime("%Y.%m.%d")
    counts = {k: len(categories.get(k) or []) for k in CATEGORY_INFO}
    pages = [cover_page(date_text, counts)]

    for category_key in ("policy", "medical", "samsung_fire"):
        articles = categories.get(category_key) or []
        # 삼성화재 뉴스가 없으면 섹션 자체를 생성하지 않음
        for i, article in enumerate(articles, 1):
            pages.append(article_page(article, category_key, i))

    pages.append(closing_page(data.get("sales_points", [])))

    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#071b3a">
<title>강원영업단 RC Morning Brief</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:100%;height:100%;overflow:hidden}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Noto Sans KR","Malgun Gothic",sans-serif;background:#071b3a;color:#172033}}
.brief{{width:100vw;height:100vh;display:flex;overflow-x:auto;overflow-y:hidden;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch;scrollbar-width:none}}
.brief::-webkit-scrollbar{{display:none}}
.page{{flex:0 0 100vw;width:100vw;height:100vh;min-height:100vh;scroll-snap-align:start;overflow-y:auto;padding:32px 24px 42px;position:relative;background:#f7f8fa}}
.cover,.closing{{background:linear-gradient(145deg,#071b3a 0%,#0b2f68 58%,#13284c 100%);color:#fff;display:flex;flex-direction:column;justify-content:space-between}}
.cover-head,.topline{{display:flex;justify-content:space-between;align-items:center;font-size:10px;letter-spacing:1.5px;color:#bfc8d7}}
.stamp,.closing-stamp{{border:1px solid #d7b34b;color:#e0bd58;padding:6px 9px;font-size:9px;letter-spacing:1.3px}}
.cover-main{{margin:auto 0}}
.gold{{color:#e0bd58;font-size:13px;letter-spacing:2px;margin-bottom:14px}}
.cover h1{{font:600 clamp(48px,15vw,78px)/.92 Georgia,serif;letter-spacing:-3px}}
.cover h1 span,.closing h1 span{{color:#e0bd58}}
.date{{margin-top:22px;font-size:16px}}
.toc{{border-top:1px solid rgba(255,255,255,.2);padding-top:18px}}
.toc-title{{color:#d7b34b;font-size:10px;letter-spacing:2px;margin-bottom:8px}}
.toc-row{{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.09);font-size:13px}}
.cover-foot{{text-align:center;font-size:9px;color:#aeb8c8}}
.article-page{{display:flex;flex-direction:column}}
.article-page.policy{{border-top:6px solid #b59a45}}
.article-page.medical{{border-top:6px solid #2473a6}}
.article-page.samsung{{border-top:6px solid #0b4ea2}}
.badge{{align-self:flex-start;margin-top:28px;margin-bottom:15px;padding:6px 9px;background:#edf0f5;border-radius:4px;font-size:10px;font-weight:800}}
.article-page h1{{font-size:clamp(25px,7vw,34px);line-height:1.35;letter-spacing:-1.2px}}
.meta{{margin-top:9px;color:#8b92a0;font-size:10px}}
.rule{{height:1px;background:#d9dde5;margin:19px 0}}
.summary{{font-size:15px;line-height:1.8;color:#394153}}
.why{{margin-top:17px;padding:13px;background:#eef1f5;border-radius:8px;font-size:12px;line-height:1.65}}
.label{{font-size:9px;letter-spacing:1.5px;font-weight:800;color:#778092;margin-bottom:5px}}
.tip{{margin-top:12px;padding:15px;border:1px solid #d8c47c;background:#fffdf5;border-radius:8px;font-size:13px;line-height:1.7}}
.tip-title{{color:#9b7a17;font-weight:800;margin-bottom:5px}}
.source{{display:block;margin-top:auto;padding:13px;text-align:center;text-decoration:none;color:#fff;background:#0b2f68;border-radius:8px;font-size:12px;font-weight:700}}
.swipe{{text-align:center;color:#9aa2b1;font-size:9px;margin-top:12px;letter-spacing:1px}}
.closing-stamp{{align-self:flex-start;margin-bottom:28px}}
.closing h1{{font:600 clamp(35px,10vw,52px)/1.1 Georgia,serif;letter-spacing:-2px}}
.closing-sub{{margin-top:18px;color:#d7dfeb;font-size:13px;line-height:1.7}}
.points{{margin-top:24px}}
.point{{display:flex;gap:13px;padding:13px 0;border-bottom:1px solid rgba(255,255,255,.13)}}
.point span{{font:18px Georgia,serif;color:#d7b34b}}
.point p{{font-size:13px;line-height:1.6;color:#f0f3f8}}
.closing-message{{margin-top:auto;padding-top:24px;border-top:1px solid rgba(255,255,255,.2);font-size:14px;line-height:1.7;color:#fff}}
@media(min-width:700px){{.page{{padding-left:calc((100vw - 620px)/2);padding-right:calc((100vw - 620px)/2)}}}}
</style>
</head>
<body>
<div class="brief">{''.join(pages)}</div>
</body>
</html>'''


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"{INPUT_FILE} 파일이 없습니다.")
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(generate_html(data), encoding="utf-8")
    print("=" * 60)
    print("HTML 카드뉴스 생성 완료")
    print(f"입력: {INPUT_FILE}")
    print(f"출력: {OUTPUT_FILE}")
    print(f"제도 동향: {len(data.get('categories', {}).get('policy', []))}개")
    print(f"의료비 이슈: {len(data.get('categories', {}).get('medical', []))}개")
    print(f"삼성화재 소식: {len(data.get('categories', {}).get('samsung_fire', []))}개")
    print("삼성화재 뉴스가 0개이면 해당 섹션은 자동 생략됩니다.")
    print("=" * 60)


if __name__ == "__main__":
    main()
