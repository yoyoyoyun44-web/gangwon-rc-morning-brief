import getpass
import urllib.parse
import requests

REDIRECT_URI = "https://yoyoyoyun44-web.github.io/gangwon-rc-morning-brief/kakao_callback.html"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"


def main():
    client_id = input("Kakao REST API Key: ").strip()
    client_secret = getpass.getpass("Kakao Client Secret (없으면 Enter): ").strip()

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "talk_message",
    }
    auth_url = "https://kauth.kakao.com/oauth/authorize?" + urllib.parse.urlencode(params)

    print("\n1) 아래 주소를 브라우저에서 엽니다.\n")
    print(auth_url)
    print("\n2) 카카오 로그인/동의를 완료합니다.")
    print("3) callback 페이지에서 표시된 '인증 코드'를 복사해 아래에 붙여넣습니다.\n")
    code = input("Authorization code: ").strip()

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }
    if client_secret:
        data["client_secret"] = client_secret

    r = requests.post(TOKEN_URL, data=data, timeout=20)
    print("HTTP", r.status_code)
    r.raise_for_status()
    token = r.json()

    print("\n=== GitHub Secret에 등록할 값 ===")
    print("KAKAO_REFRESH_TOKEN=")
    print(token.get("refresh_token", ""))
    print("\n이 refresh token은 화면/채팅에 공유하지 말고 GitHub Secret에만 넣으세요.")


if __name__ == "__main__":
    main()
