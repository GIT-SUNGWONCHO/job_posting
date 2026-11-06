from jobpost import filters, jobtypes


class FakeAI:
    model = "fake-model"

    def __init__(self, answers):
        self.answers = answers
        self.prompts = []

    def json(self, prompt, schema):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def test_classify_keeps_only_valid_answers():
    items = [("z:1", "Data Engineer", ["데이터엔지니어"], "주요업무 파이프라인 구축"), ("z:2", "AI 마케터", ["마케팅"], "")]
    ai = FakeAI([[{"i": 0, "t": "data_eng"}, {"i": 1, "t": "없는유형"}, {"i": 7, "t": "analyst"}]])
    assert jobtypes.classify(items, ai) == {"z:1": "data_eng"}
    assert "데이터 엔지니어" in ai.prompts[0] and "0\tData Engineer\t데이터엔지니어\t주요업무 파이프라인 구축" in ai.prompts[0]


def test_snippet_starts_at_duties():
    text = "회사 소개 " * 50 + "\n담당업무\nSCM 업무를   LLM·RAG 기반 서비스로 설계·개발\n지원자격 ..."
    got = jobtypes.snippet(text)
    assert got.startswith("담당업무 SCM 업무를 LLM·RAG") and len(got) <= jobtypes.SNIPPET_CHARS
    assert jobtypes.snippet("회사 소개만 있음") == "회사 소개만 있음" and jobtypes.snippet(None) == ""


def test_run_reclassifies_when_body_arrives():
    v = jobtypes.taxonomy()["version"]
    current = {"v": v, "prompt": jobtypes.PROMPT_VERSION}
    state = {
        "z:1": {"uid": "z:1", "title": "AI Solutions Engineer", "first_seen": "2026-10-29",
                "job_type": {"id": "consulting", **current, "body": False}},  # 제목만 보고 분류, 이제 본문이 있다
        "z:2": {"uid": "z:2", "title": "Data Engineer", "first_seen": "2026-10-29",
                "job_type": {"id": "data_eng", **current, "body": False}},  # 본문이 아직 없다
        "z:3": {"uid": "z:3", "title": "ML Engineer", "first_seen": "2026-10-29",
                "job_type": {"id": "ml_eng", **current, "body": True}},
    }
    details = {"z:1": {"description": "담당업무 SCM 업무를 LLM 서비스로 개발"}, "z:3": {"description": "업무 내용 모델 학습"}}
    ai = FakeAI([[{"i": 0, "t": "ai_eng"}]])
    summary = jobtypes.run(state, {}, "2026-11-03", client=ai, details=details)
    assert summary == {"pending": 0, "classified": 1, "calls": 1}
    assert state["z:1"]["job_type"]["id"] == "ai_eng" and state["z:1"]["job_type"]["body"] is True
    assert "0\tAI Solutions Engineer\t\t담당업무 SCM 업무를 LLM 서비스로 개발" in ai.prompts[0]


def test_run_records_versions_and_skips_current_closed_overseas():
    v = jobtypes.taxonomy()["version"]
    state = {
        "z:1": {"uid": "z:1", "title": "Data Engineer", "first_seen": "2026-10-13"},
        "z:2": {"uid": "z:2", "title": "ML Engineer", "first_seen": "2026-10-13",
                "job_type": {"id": "ml_eng", "v": v, "prompt": jobtypes.PROMPT_VERSION}},
        "z:3": {"uid": "z:3", "title": "Data Analyst", "first_seen": "2026-10-12", "closed_on": "2026-10-13"},
        "z:4": {"uid": "z:4", "title": "Data Engineer", "first_seen": "2026-10-13", "overseas": True},
        "z:5": {"uid": "z:5", "title": "LLM 엔지니어", "first_seen": "2026-10-12",
                "job_type": {"id": "ai_eng", "v": v - 1, "prompt": jobtypes.PROMPT_VERSION}},
    }
    ai = FakeAI([[{"i": 0, "t": "data_eng"}, {"i": 1, "t": "ai_eng"}]])
    summary = jobtypes.run(state, {"z:1": {"categories": ["데이터엔지니어"]}}, "2026-10-13", client=ai)
    assert summary == {"pending": 0, "classified": 2, "calls": 1}
    assert state["z:1"]["job_type"] == {"id": "data_eng", "v": v, "prompt": jobtypes.PROMPT_VERSION,
                                        "model": "fake-model", "on": "2026-10-13", "body": False}
    assert state["z:5"]["job_type"]["v"] == v
    assert "job_type" not in state["z:3"] and "job_type" not in state["z:4"]


def test_run_without_key_leaves_postings_pending(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    state = {"z:1": {"uid": "z:1", "title": "Data Engineer", "first_seen": "2026-10-13"}}
    assert jobtypes.run(state, {}, "2026-10-13")["skipped"] == "GEMINI_API_KEY 없음"


def test_filter_by_job_type_lets_unclassified_through():
    from jobpost.models import CompanyType
    f = {"job_types": ["data_eng", "ai_eng"]}
    args = dict(title="t", company="c", company_type=CompanyType.LARGE, career_min=None, career_max=None, regions=[])
    assert filters.passes(**args, filters=f, job_type="data_eng")[0]
    assert not filters.passes(**args, filters=f, job_type="f_marketing")[0]
    assert filters.passes(**args, filters=f, job_type=None)[0]


def test_taxonomy_ids_are_unique_and_described():
    types = jobtypes.taxonomy()["types"]
    assert len({t["id"] for t in types}) == len(types)
    assert all(t["name"] and t["desc"] for t in types)


def test_classify_secondary_keeps_only_other_family():
    from jobpost import jobtypes

    class AI:
        def json(self, prompt, schema):
            assert "주 유형은 바꾸지 않는다" in prompt
            return [{"i": 0, "s": "analyst"}, {"i": 1, "s": "data_sci"}, {"i": 2, "s": "none"}, {"i": 3, "s": "f_marketing"}]

    items = [("a", "f_marketing", "CRM 마케팅 데이터 분석", [], ""), ("b", "data_eng", "데이터 엔지니어", [], ""),
             ("c", "analyst", "데이터 분석가", [], ""), ("d", "analyst", "CRM 분석·캠페인 운영", [], "")]
    assert jobtypes.classify_secondary(items, AI()) == {"a": "analyst", "d": "f_marketing"}


def test_secondary_only_for_other_family_and_used_by_filters():
    from jobpost import filters, jobtypes
    from jobpost.models import CompanyType

    state = {"a": {"uid": "a", "title": "CRM 마케터", "first_seen": "2026-11-02", "job_type": {"id": "f_marketing"}},
             "b": {"uid": "b", "title": "데이터 엔지니어", "first_seen": "2026-11-02", "job_type": {"id": "data_eng"}}}

    class AI:
        def json(self, prompt, schema):
            assert "\tCRM 마케터" in prompt and "\t데이터 엔지니어" not in prompt  # 그 밖 계열만 묻는다
            return [{"i": 0, "s": "analyst"}]

    out = jobtypes.run_secondary(state, {}, {}, AI(), "2026-11-02")
    assert out["found"] == 1 and jobtypes.secondary_of(state["a"]) == "analyst"
    assert jobtypes.secondary_of(state["b"]) is None
    assert not jobtypes._secondary_todo(state)  # 한 번 본 공고는 다시 묻지 않는다
    kw = dict(title="CRM 마케터", company="x", company_type=CompanyType.LARGE, career_min=None, career_max=None,
              regions=[], filters={"job_types": ["analyst"]}, job_type="f_marketing")
    assert filters.reasons(**kw) == [("job", "f_marketing")]
    assert filters.reasons(**kw, job_type2="analyst") == []


def test_filter_drops_postings_with_duties_all_outside_my_field():
    from jobpost import filters, screen
    from jobpost.models import CompanyType
    kw = dict(title="콘텐츠 마케터", company="k", company_type=CompanyType("대기업"), career_min=None, career_max=None,
              regions=[], filters={"job_types": ["data_eng", "analyst"]}, job_type="f_marketing", job_type2="analyst")
    assert filters.reasons(**kw) == []  # 공고 정리 전에는 통과
    off = screen.duty_jobs({"facts": {"duties": [{"kind": "f_marketing"}, {"kind": "f_marketing"}]}})
    assert filters.reasons(**kw, duty_jobs=off) == [("duty", "")]
    # 가까운 직무(data_sci의 related에 analyst)면 내 분야
    near = screen.duty_jobs({"facts": {"duties": [{"kind": "data_sci"}]}})
    assert "analyst" in near and filters.reasons(**kw, duty_jobs=near) == []
    assert screen.duty_jobs(None) == []
