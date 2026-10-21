"""텔레그램 봇(아침 알림). 텔레그램은 이 모듈에서만 부른다(docs/architecture.md "경계").

봇 토큰은 환경 변수 TELEGRAM_BOT_TOKEN(GitHub Secrets)로만 받는다. 토큰이 요청 주소에 들어가므로
요청 오류를 그대로 올리지 않고 주소를 뺀 문장으로 바꾼다(로그에 토큰이 남지 않게).

core.telegram.org/bots/api에서 확인한 것(2026-10-21, Bot API 10.3):
- 요청: https://api.telegram.org/bot<token>/METHOD, 응답 {"ok": true, "result": ...} 또는 {"ok": false, "error_code", "description"}
- sendMessage: chat_id, text(엔티티를 풀고 1~4096자), parse_mode "HTML", link_preview_options {"is_disabled": true}
- HTML: <b> <i> <a href> <blockquote expandable>(접힌 인용) 등. 태그가 아닌 <, >, &는 &lt; &gt; &amp;로 바꾼다
- reply_markup.inline_keyboard: 메시지 아래 버튼. url 버튼은 누르면 주소를 연다
- getUpdates: 봇이 받은 메시지. 받아 가지 않은 메시지는 최대 24시간만 남는다
"""

from __future__ import annotations

import os
from typing import Any

import requests

API = "https://api.telegram.org/bot{token}/{method}"
TEXT_MAX = 4096


class TelegramError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN"))


def _call(method: str, payload: dict[str, Any], session: requests.Session | None = None) -> Any:
    url = API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)
    try:
        resp = (session or requests.Session()).post(url, json=payload, timeout=30)
        body = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise TelegramError(f"텔레그램 {method} 요청 실패({type(e).__name__})") from None  # 오류 문장에 토큰 주소가 들어 있다
    if not body.get("ok"):
        raise TelegramError(f"텔레그램 {method} {body.get('error_code')} {(body.get('description') or '')[:160]}")
    return body["result"]


def send(chat_id: int | str, text: str, session: requests.Session | None = None,
         buttons: list[list[dict[str, str]]] | None = None) -> None:
    """buttons: 메시지 아래 링크 버튼 줄들([[{"text", "url"}, ...], ...])."""
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                               "link_preview_options": {"is_disabled": True}}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    _call("sendMessage", payload, session)


def bot_name(session: requests.Session | None = None) -> str:
    """토큰이 가리키는 봇의 아이디(@..._bot). 연결이 안 될 때 어느 봇인지 알려 주려고."""
    return "@" + (_call("getMe", {}, session).get("username") or "?")


def latest_chat(session: requests.Session | None = None) -> dict[str, Any] | None:
    """봇에게 가장 최근에 말을 건 대화방(/start 등). 없으면 None."""
    for update in reversed(_call("getUpdates", {"allowed_updates": ["message"]}, session) or []):
        chat = (update.get("message") or {}).get("chat")
        if chat:
            return chat
    return None
