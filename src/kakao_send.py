import os
import sys
import json
import requests


# ==========================================================
# Kakao API
# ==========================================================

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

# GitHub Pages Morning Brief
BRIEF_URL = "https://yoyoyoyun44-web.github.io/gangwon-rc-morning-brief/"


# ==========================================================
# Access Token 갱신
# ==========================================================

def refresh_access_token():
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "").strip()
    client_id = os.environ.get("KAKAO_REST_API_KEY", "").strip()
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET", "").strip()

    if not refresh_token:
        raise RuntimeError(
            "KAKAO_REFRESH_TOKEN이 없습니다."
        )

    if not client_id:
        raise RuntimeError(
            "KAKAO_REST_API_KEY가 없습니다."
        )

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }

    if client_secret:
        data["client_secret"] = client_secret

    response = requests.post(
        TOKEN_URL,
        data=data,
        timeout=20,
    )

    if not response.ok:
        print(
            "Kakao token refresh failed:",
            response.text,
            file=sys.stderr,
        )

    response.raise_for_status()

    result = response.json()

    access_token = result.get("access_token")

    if not access_token:
        raise RuntimeError(
            "Kakao 응답에 access_token이 없습니다."
        )

    return access_token


# ==========================================================
# KakaoTalk 나에게 보내기
# ==========================================================

def send_memo(access_token):

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    # ------------------------------------------------------
    # Feed 템플릿
    #
    # 목적:
    # 카카오톡 메시지 안에서
    # "Morning Brief 보기" 버튼을 명확하게 표시하고
    # 버튼 클릭 시 GitHub Pages로 이동
    # ------------------------------------------------------

    template = {
        "object_type": "feed",

        "content": {
            "title": "🌅 강원영업단 RC Morning Brief",

            "description": (
                "오늘의 보험·의료 뉴스 카드뉴스가 "
                "준비되었습니다."
            ),

            "image_url": (
                "https://dummyimage.com/800x400/"
                "071b3a/ffffff.png"
                "&text=Morning+Brief"
            ),

            "image_width": 800,
            "image_height": 400,

            "link": {
                "web_url": BRIEF_URL,
                "mobile_web_url": BRIEF_URL,
            },
        },

        "buttons": [
            {
                "title": "Morning Brief 보기",

                "link": {
                    "web_url": BRIEF_URL,
                    "mobile_web_url": BRIEF_URL,
                },
            }
        ],
    }

    response = requests.post(
        SEND_URL,
        headers=headers,
        data={
            "template_object": json.dumps(
                template,
                ensure_ascii=False,
            )
        },
        timeout=20,
    )

    if not response.ok:
        print(
            "Kakao message send failed:",
            response.text,
            file=sys.stderr,
        )

    response.raise_for_status()

    result = response.json()

    print("KakaoTalk 나에게 보내기 성공")
    print("Response:", result)


# ==========================================================
# 실행
# ==========================================================

if __name__ == "__main__":

    try:
        access_token = refresh_access_token()

        send_memo(access_token)

    except Exception as e:

        print(
            f"KakaoTalk 전송 실패: {e}",
            file=sys.stderr,
        )

        sys.exit(1)
