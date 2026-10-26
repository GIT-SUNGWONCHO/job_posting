from jobpost import ai


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class _Session:
    def __init__(self, body):
        self.body = body
        self.sent = None

    def post(self, url, headers, json, timeout):
        self.sent = json
        return _Resp(200, self.body)


def test_grounded_returns_sentences_with_their_web_sources(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    body = {"candidates": [{"content": {"parts": [{"text": "A사는 2026년 AI 조직을 만들었다. "}, {"text": "B 발표."}]},
                            "groundingMetadata": {
                                "webSearchQueries": ["A사 AI 조직"],
                                "groundingChunks": [{"web": {"uri": "https://redirect/1", "title": "news.example"}}],
                                "groundingSupports": [{"segment": {"text": "A사는 2026년 AI 조직을 만들었다."},
                                                       "groundingChunkIndices": [0]}]}}]}
    session = _Session(body)
    got = ai.Gemini(session=session, model="m").grounded("질문")
    assert session.sent["tools"] == [{"google_search": {}}] and "responseSchema" not in session.sent["generationConfig"]
    assert got["text"] == "A사는 2026년 AI 조직을 만들었다. B 발표."
    assert got["chunks"] == [{"uri": "https://redirect/1", "title": "news.example"}]
    assert got["supports"] == [{"text": "A사는 2026년 AI 조직을 만들었다.", "chunks": [0]}]
    assert got["queries"] == ["A사 AI 조직"]
