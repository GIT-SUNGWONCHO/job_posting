"""AI 호출(Gemini). 외부 AI는 이 모듈에서만 부른다(docs/architecture.md "경계").

키는 환경 변수 GEMINI_API_KEY(GitHub Secrets)로만 받는다. 모델은 config/ai.yaml.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from . import config

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class AIError(RuntimeError):
    pass


def configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


class Gemini:
    def __init__(self, session: requests.Session | None = None, model: str | None = None):
        cfg = config.load("ai")
        self.model: str = model or cfg["model"]
        self.min_interval: float = cfg.get("min_interval", 4.0)
        self.session = session or requests.Session()
        self.calls = 0
        self._last = 0.0

    def json(self, prompt: str, schema: dict[str, Any], retries: int = 3) -> Any:
        """지시문을 보내고 schema 형식의 JSON을 받는다. 형식이 틀리면 다시 묻는다."""
        last_error = ""
        for attempt in range(retries):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            resp = self.session.post(
                URL.format(model=self.model),
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
                                         "temperature": 0},
                },
                timeout=120,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"{resp.status_code}"
                if attempt < retries - 1:  # 마지막 시도 뒤에는 기다리지 않는다
                    time.sleep(20 * (attempt + 1))
                continue
            if resp.status_code != 200:
                # 응답 본문에는 키가 없지만 길이는 줄인다
                raise AIError(f"{resp.status_code} {resp.text[:200]}")
            try:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except (KeyError, IndexError, ValueError) as e:
                last_error = f"형식 오류: {e}"
        raise AIError(last_error or "응답 없음")

    def grounded(self, prompt: str, retries: int = 2) -> dict[str, Any]:
        """구글 검색 근거(google_search 도구)로 답을 받는다. 문장마다 근거 웹 문서를 함께 돌려준다.
        {"text", "chunks": [{"uri", "title"}], "supports": [{"text", "chunks": [번호]}], "queries": [...]}.
        검색 도구와 JSON 형식 지정은 함께 쓸 수 없어 글로 받는다."""
        last_error = ""
        for attempt in range(retries):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            resp = self.session.post(
                URL.format(model=self.model),
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}],
                      "generationConfig": {"temperature": 0}},
                timeout=180,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                # 한도 오류 본문에 어느 한도(quotaMetric)인지 적혀 있다. 키는 들어 있지 않다
                last_error = f"{resp.status_code} {resp.text[:2000]}"
                if attempt < retries - 1:  # 마지막 시도 뒤에는 기다리지 않는다
                    time.sleep(20 * (attempt + 1))
                continue
            if resp.status_code != 200:
                raise AIError(f"{resp.status_code} {resp.text[:300]}")
            try:
                cand = resp.json()["candidates"][0]
                text = "".join(part.get("text", "") for part in cand["content"]["parts"])
            except (KeyError, IndexError, ValueError) as e:
                last_error = f"형식 오류: {e}"
                continue
            meta = cand.get("groundingMetadata") or {}
            return {
                "text": text,
                "chunks": [{"uri": (c.get("web") or {}).get("uri"), "title": (c.get("web") or {}).get("title")}
                           for c in meta.get("groundingChunks") or []],
                "supports": [{"text": (s.get("segment") or {}).get("text", ""), "chunks": s.get("groundingChunkIndices") or []}
                             for s in meta.get("groundingSupports") or []],
                "queries": meta.get("webSearchQueries") or [],
            }
        raise AIError(last_error or "응답 없음")

