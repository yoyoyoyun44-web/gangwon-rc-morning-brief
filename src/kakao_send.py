import os
import sys
import json
import subprocess
import requests

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
BRIEF_URL = "https://yoyoyoyun44-web.github.io/gangwon-rc-morning-brief/"


def run_script(path, label):
    print(label)
    result = subprocess.run([sys.executable, path], capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{label} 실패: exit={result.returncode}")


def run_final_quality_check():
    # 1) 보험 세일즈 활용도가 낮은 연예인 기부/개인 미담/의료인력 정책 등을 먼저 제거
    run_script("src/sales_relevance_filter.py", "영업 활용도 필터 시작")

    # 2) 암·뇌혈관·심혈관·간병 보호 주제 보충
    run_script("src/topic_rescue.py", "보호 주제 보충 시작: 암·뇌혈관·심혈관·간병")

    # 3) 동일 이슈 중복 제거 + 기사별 영업 Tip 보정
    run_script("src/final_quality.py", "최종 품질검수 시작: 동일 이슈 중복 제거 + 기사별 영업 Tip 보정")

    # 4) 최종 HTML 재생성
    run_script("src/generate_html.py", "최종 HTML 재생성")

    # 5) 최종 결과를 GitHub Pages에 반영
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if status.stdout.strip():
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", "data/news.json", "docs/index.html"], check=True)
        subprocess.run(["git", "commit", "-m", "Apply final Morning Brief quality filters"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("최종 품질검수 결과 GitHub Pages 반영 완료")
    else:
        print("최종 품질검수 후 추가 변경 없음")


def refresh_access_token():
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()
    client_id = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()
    if not refresh_token:
        raise RuntimeError("KAKAO_REFRESH_TOKEN이 없습니다.")
    if not client_id:
        raise RuntimeError("KAKAO_REST_API_KEY가 없습니다.")
    data = {"grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh_token}
    if client_secret:
        data["client_secret"] = client_secret
    response = requests.post(TOKEN_URL, data=data, timeout=20)
    if not response.ok:
        print("Kakao token refresh failed:", response.text, file=sys.stderr)
    response.raise_for_status()
    result = response.json()
    access_token = result.get("access_token")
    if not access_token:
        raise RuntimeError("Kakao 응답에 access_token이 없습니다.")
    return access_token


def send_memo(access_token):
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/x-www-form-urlencoded"}
    template = {
        "object_type": "feed",
        "content": {
            "title": "🌅 강원영업단 RC Morning Brief",
            "description": "오늘의 보험·의료 뉴스 카드뉴스가 준비되었습니다.",
            "image_url": "https://dummyimage.com/800x400/071b3a/ffffff.png&text=Morning+Brief",
            "image_width": 800,
            "image_height": 400,
            "link": {"web_url": BRIEF_URL, "mobile_web_url": BRIEF_URL},
        },
        "buttons": [{"title": "Morning Brief 보기", "link": {"web_url": BRIEF_URL, "mobile_web_url": BRIEF_URL}}],
    }
    response = requests.post(SEND_URL, headers=headers, data={"template_object": json.dumps(template, ensure_ascii=False)}, timeout=20)
    if not response.ok:
        print("Kakao message send failed:", response.text, file=sys.stderr)
    response.raise_for_status()
    print("KakaoTalk 나에게 보내기 성공")
    print("Response:", response.json())


if __name__ == "__main__":
    try:
        run_final_quality_check()
        send_memo(refresh_access_token())
    except Exception as e:
        print(f"KakaoTalk 전송 실패: {e}", file=sys.stderr)
        sys.exit(1)
