import os
import sys
import requests

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
BRIEF_URL = "https://yoyoyoyun44-web.github.io/gangwon-rc-morning-brief/"


def refresh_access_token():
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()
    client_id = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()

    if not refresh_token or not client_id:
        raise RuntimeError("KAKAO_REFRESH_TOKEN 또는 KAKAO_REST_API_KEY가 없습니다.")

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret

    r = requests.post(TOKEN_URL, data=data, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def send_memo(access_token):
    headers = {"Authorization": f"Bearer {access_token}"}
    template = {
        "object_type": "text",
        "text": "🌅 강원영업단 RC Morning Brief\n\n오늘의 보험·의료 뉴스 카드뉴스가 준비되었습니다.\n\n👉 카드뉴스 열기",
        "link": {
            "web_url": BRIEF_URL,
            "mobile_web_url": BRIEF_URL,
        },
        "button_title": "Morning Brief 보기",
    }
    r = requests.post(
        SEND_URL,
        headers=headers,
        data={"template_object": __import__("json").dumps(template, ensure_ascii=False)},
        timeout=20,
    )
    if not r.ok:
        print(r.text, file=sys.stderr)
    r.raise_for_status()
    print("KakaoTalk 나에게 보내기 성공")


if __name__ == "__main__":
    send_memo(refresh_access_token())
