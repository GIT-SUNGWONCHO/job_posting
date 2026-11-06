"""AI 호출(Gemini). 외부 AI는 이 모듈에서만 부른다(docs/architecture.md "경계").

키는 환경 변수 GEMINI_API_KEY(GitHub Secrets)로만 받는다. 모델은 config/ai.yaml.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class AIError(RuntimeError):
    pass


def _quota(resp: requests.Response) -> str:
    """429 응답에 적힌 한도 종류와 값(예: " GenerateRequestsPerDayPerProjectPerModel-FreeTier=500").
    무료 한도가 얼마인지 실행 로그로 알 수 있게(키는 응답에 없다)."""
    try:
        details = resp.json().get("error", {}).get("details") or []
    except ValueError:
        return ""
    out = []
    for d in details:
        for v in d.get("violations") or []:
            if v.get("quotaId"):
                out.append(f"{v['quotaId']}={v.get('quotaValue', '?')}")
    return (" " + ", ".join(out)) if out else ""


def configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def api_keys() -> list[str]:
    """GEMINI_API_KEY, 그다음 GEMINI_API_KEY_2 ~ _9(있으면). 앞 키가 한도(429)에 걸리면 다음 키로 넘어간다.
    무료 한도는 키가 아니라 구글 클라우드 프로젝트마다라서, 키마다 다른 프로젝트여야 한도가 늘어난다.
    여러 키는 임시로 쓴다(2026-11-03 사용자 결정, docs/setup.md "Gemini 무료 한도")."""
    names = ["GEMINI_API_KEY", *(f"GEMINI_API_KEY_{i}" for i in range(2, 10))]
    return [os.environ[n] for n in names if os.environ.get(n)]


class Gemini:
    def __init__(self, session: requests.Session | None = None, model: str | None = None, key_index: int = 0):
        cfg = config.load("ai")
        self.model: str = model or cfg["model"]
        self.min_interval: float = cfg.get("min_interval", 4.0)
        self.session = session or requests.Session()
        self.calls = 0
        self._last = 0.0
        self.keys = api_keys()
        self.key_i = min(key_index, max(len(self.keys) - 1, 0))  # 지금 쓰는 키(한도에 걸리면 다음으로)

    def json(self, prompt: str, schema: dict[str, Any], retries: int = 3,
             images: list[tuple[str, bytes]] | None = None) -> Any:
        """지시문을 보내고 schema 형식의 JSON을 받는다. 형식이 틀리면 다시 묻는다.
        images: [(mime, bytes)] 함께 보낼 이미지(본문 읽기)."""
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for mime, data in images or []:
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}})
        last_error = ""
        attempt = 0
        while attempt < retries:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            resp = self.session.post(
                URL.format(model=self.model),
                headers={"x-goog-api-key": self.keys[self.key_i], "Content-Type": "application/json"},
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema,
                                         "temperature": 0},
                },
                timeout=120,
            )
            if resp.status_code == 429 and self.key_i + 1 < len(self.keys):
                # 이 키의 한도가 찼으면 다음 키로 바로 다시(키 이름은 남기지만 값은 남기지 않는다)
                self.key_i += 1
                log.warning("Gemini 한도(429%s): %d번째 키로 넘어감", _quota(resp), self.key_i + 1)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"{resp.status_code}{_quota(resp)}"
                if attempt < retries - 1:  # 마지막 시도 뒤에는 기다리지 않는다
                    time.sleep(20 * (attempt + 1))
                attempt += 1
                continue
            if resp.status_code != 200:
                # 응답 본문에는 키가 없지만 길이는 줄인다
                raise AIError(f"{resp.status_code} {resp.text[:200]}")
            try:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            except (KeyError, IndexError, ValueError) as e:
                last_error = f"형식 오류: {e}"
                attempt += 1
        raise AIError(last_error or "응답 없음")

    def embed(self, texts: list[str], model: str = "gemini-embedding-001") -> list[list[float]]:
        """글마다 임베딩(의미를 숫자 목록으로). 100개씩 묶어 부른다. 한도(429)면 다음 키로."""
        out: list[list[float]] = []
        for start in range(0, len(texts), 100):
            chunk = texts[start:start + 100]
            body = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t}]},
                                  "taskType": "SEMANTIC_SIMILARITY"} for t in chunk]}
            for attempt in range(4):
                wait = self.min_interval - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
                self.calls += 1
                resp = self.session.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents",
                    headers={"x-goog-api-key": self.keys[self.key_i], "Content-Type": "application/json"},
                    json=body, timeout=120)
                if resp.status_code == 429 and self.key_i + 1 < len(self.keys):
                    self.key_i += 1
                    log.warning("Gemini 임베딩 한도(429%s): %d번째 키로 넘어감", _quota(resp), self.key_i + 1)
                    continue
                if resp.status_code == 429 or resp.status_code >= 500:
                    time.sleep(20 * (attempt + 1))
                    continue
                if resp.status_code != 200:
                    raise AIError(f"{resp.status_code} {resp.text[:200]}")
                out += [e["values"] for e in resp.json()["embeddings"]]
                break
            else:
                raise AIError("임베딩 실패")
        return out

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

