"""HTML pages for the academy account binding flow."""

from __future__ import annotations

import html


def render_login_page(*, state: str, error: str = "") -> str:
    safe_state = html.escape(state, quote=True)
    safe_error = html.escape(error, quote=True)
    error_block = f'<p class="error">{safe_error}</p>' if safe_error else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>Miho 학원 계정 연결</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      min-height: 100vh;
      margin: 0;
      padding: max(22px, env(safe-area-inset-top)) 16px max(22px, env(safe-area-inset-bottom));
      background: #f4f6f8;
      color: #15171a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(100%, 430px);
      margin: 0 auto;
      padding: 28px 22px 22px;
      background: #fff;
      border: 1px solid #dde2ea;
      border-radius: 8px;
      box-shadow: 0 10px 30px rgba(20, 28, 38, 0.08);
    }}
    .brand {{ color: #496070; font-size: 13px; font-weight: 700; margin-bottom: 8px; }}
    h1 {{ font-size: 24px; line-height: 1.2; margin: 0 0 10px; letter-spacing: 0; }}
    label {{ display: block; font-size: 14px; font-weight: 700; margin-top: 18px; }}
    input {{
      width: 100%;
      min-height: 48px;
      margin-top: 8px;
      padding: 12px 13px;
      border: 1px solid #c8ced8;
      border-radius: 6px;
      font-size: 16px;
      background: #fff;
    }}
    input:focus {{ outline: 3px solid rgba(31, 111, 235, 0.18); border-color: #1f6feb; }}
    button {{
      width: 100%;
      min-height: 50px;
      margin-top: 22px;
      padding: 13px 14px;
      border: 0;
      border-radius: 6px;
      background: #1f6feb;
      color: #fff;
      font-size: 16px;
      font-weight: 800;
    }}
    .hint {{ color: #5d6673; font-size: 14px; line-height: 1.55; margin: 0 0 6px; }}
    .error {{ color: #b42318; background: #fff1f0; border: 1px solid #ffccc7; padding: 11px; border-radius: 6px; font-size: 14px; }}
    .foot {{ margin-top: 16px; color: #7a8491; font-size: 12px; line-height: 1.45; }}
    @media (min-width: 700px) {{
      body {{ display: grid; place-items: center; padding: 32px; }}
      main {{ padding: 32px 28px 24px; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="brand">Miho Academy</div>
    <h1>Miho 학원 계정 연결</h1>
    <p class="hint">PACA/Peak 계정으로 로그인하면 디스코드에서 해당 학원 데이터만 조회할 수 있어.</p>
    {error_block}
    <form method="post" action="">
      <input type="hidden" name="state" value="{safe_state}">
      <label for="email">이메일</label>
      <input id="email" name="email" type="email" autocomplete="username" required>
      <label for="password">비밀번호</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">연결하기</button>
    </form>
    <p class="foot">비밀번호는 저장하지 않아. 로그인 성공 후 발급된 접속 토큰만 암호화해서 보관해.</p>
  </main>
</body>
</html>"""


def render_success_page(*, name: str, academy_name: str) -> str:
    safe_name = html.escape(name, quote=True)
    safe_academy = html.escape(academy_name, quote=True)
    return f"""<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>연결 완료</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f6f7f9;color:#15171a;">
  <main style="max-width:420px;margin:64px auto;padding:28px;background:white;border:1px solid #dde1e7;border-radius:8px;">
    <h1 style="font-size:22px;margin-top:0;">연결 완료</h1>
    <p>{safe_name} 계정이 {safe_academy} 학원 범위로 연결됐어.</p>
    <p style="color:#5d6673;">이 창은 닫아도 돼. 디스코드로 돌아가서 조회를 시작하면 돼.</p>
  </main>
</body>
</html>"""


def render_error_page(message: str) -> str:
    safe_message = html.escape(message, quote=True)
    return f"""<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>연결 실패</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f6f7f9;color:#15171a;padding:18px;">
  <main style="max-width:420px;margin:48px auto;padding:24px;background:white;border:1px solid #dde1e7;border-radius:8px;">
    <h1 style="font-size:22px;margin-top:0;">연결하지 못했어</h1>
    <p>{safe_message}</p>
    <p style="color:#5d6673;">디스코드에서 새 로그인 링크를 받아 다시 시도해줘.</p>
  </main>
</body>
</html>"""
