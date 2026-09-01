```python
import os
import html
from urllib.parse import urlparse, parse_qs

from flask import Flask, request

app = Flask(__name__)

HTML = """
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>카카오 인증</title>
<style>
body {
    font-family: Arial, sans-serif;
    padding: 40px 20px;
    line-height: 1.7;
}
.box {
    max-width: 600px;
    margin: auto;
    padding: 30px;
    border: 1px solid #ddd;
    border-radius: 12px;
}
h1 {
    font-size: 24px;
}
.code {
    word-break: break-all;
    background: #f5f5f5;
    padding: 15px;
    border-radius: 8px;
    font-size: 13px;
}
</style>
</head>
<body>
<div class="box">
<h1>카카오 인증 결과</h1>
{message}
</div>
</body>
</html>
"""


@app.route("/")
def callback():
    code = request.args.get("code")

    if not code:
        error = request.args.get("error")
        description = request.args.get("error_description", "")

        message = f"""
        <p>카카오 인증코드를 받지 못했습니다.</p>
        <p>오류: {html.escape(error or "unknown")}</p>
        <p>{html.escape(description)}</p>
        """

        return HTML.format(message=message), 400

    # 인증코드는 화면에 직접 노출하지 않습니다.
    message = """
    <p><strong>카카오 인증코드가 정상적으로 전달되었습니다.</strong></p>
    <p>이제 GitHub Actions에서 인증코드를 이용해 토큰 발급을 진행할 수 있습니다.</p>
    <p>이 창은 닫으셔도 됩니다.</p>
    """

    return HTML.format(message=message)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
```

