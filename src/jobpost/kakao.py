"""카카오 "나에게 보내기"(아침 알림). 카카오는 이 모듈에서만 부른다(docs/architecture.md "경계").

앱 키는 환경 변수 KAKAO_REST_KEY, KAKAO_CLIENT_SECRET(GitHub Secrets)로만 받는다.
사람마다 받은 리프레시 토큰은 Supabase kakao_links 표(서버만 읽고 씀)에 둔다. 토큰 값은 로그에 남기지 않는다.

developers.kakao.com 문서에서 확인한 것(2026-10-17):
- 인가 코드: GET https://kauth.kakao.com/oauth/authorize?response_type=code&client_id=&redirect_uri=&scope=talk_message
- 토큰 발급·갱신: POST https://kauth.kakao.com/oauth/token. REST API 키는 클라이언트 시크릿이 기본으로 켜져 있어 client_secret을 함께 보낸다
- 액세스 토큰 약 12시간(43199초), 리프레시 토큰 60일(5184000초). 갱신할 때 리프레시 토큰이 1개월 미만 남았을 때만
  새 refresh_token을 준다. 매일 갱신하고 새 값이 오면 바꿔 저장하면 끊기지 않는다
- 나에게 보내기: POST https://kapi.kakao.com/v2/api/talk/memo/default/send, template_object(JSON). 성공하면 result_code 0
- 리스트 템플릿: header_title 최대 200자, contents 2~3개(title·description 합쳐 4줄), 버튼 최대 2개.
  텍스트 템플릿: text 최대 200자
- 메시지 링크는 앱의 [제품 링크 관리] > [웹 도메인]에 등록한 도메인만 열린다
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode

import requests

AUTH = "https://kauth.kakao.com/oauth"
SEND = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class KakaoError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("KAKAO_REST_KEY"))


def _app() -> dict[str, str]:
    out = {"client_id": os.environ["KAKAO_REST_KEY"]}
    if os.environ.get("KAKAO_CLIENT_SECRET"):
        out["client_secret"] = os.environ["KAKAO_CLIENT_SECRET"]
    return out


def authorize_url(redirect_uri: str) -> str:
    return f"{AUTH}/authorize?" + urlencode({"response_type": "code", "client_id": os.environ["KAKAO_REST_KEY"],
                                              "redirect_uri": redirect_uri, "scope": "talk_message"})


def _token(data: dict[str, str], session: requests.Session) -> dict[str, Any]:
    resp = session.post(f"{AUTH}/token", data={**data, **_app()}, timeout=30)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code >= 300 or "access_token" not in body:
        # 오류 응답에는 토큰이 없다. 코드와 설명만 남긴다
        raise KakaoError(f"카카오 토큰 {resp.status_code} {body.get('error_code') or body.get('error')} "
                         f"{(body.get('error_description') or '')[:120]}")
    return body


def exchange(code: str, redirect_uri: str, session: requests.Session | None = None) -> dict[str, Any]:
    """인가 코드(한 번만 쓸 수 있음)로 토큰을 받는다."""
    return _token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
                  session or requests.Session())


def refresh(refresh_token: str, session: requests.Session | None = None) -> dict[str, Any]:
    """액세스 토큰을 새로 받는다. 응답에 refresh_token이 있으면 바뀐 것이니 저장한다."""
    return _token({"grant_type": "refresh_token", "refresh_token": refresh_token}, session or requests.Session())


def send(access_token: str, template: dict[str, Any], session: requests.Session | None = None) -> None:
    resp = (session or requests.Session()).post(
        SEND, headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)}, timeout=30)
    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code >= 300 or body.get("result_code") != 0:
        raise KakaoError(f"카카오 보내기 {resp.status_code} {body.get('code')} {(body.get('msg') or '')[:160]}")
