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
    items = [("z:1", "Data Engineer", ["데이터엔지니어"]), ("z:2", "AI 마케터", ["마케팅"])]
    ai = FakeAI([[{"i": 0, "t": "data_eng"}, {"i": 1, "t": "없는유형"}, {"i": 7, "t": "analyst"}]])
    assert jobtypes.classify(items, ai) == {"z:1": "data_eng"}
    assert "데이터 엔지니어" in ai.prompts[0] and "0\tData Engineer\t데이터엔지니어" in ai.prompts[0]


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
                                        "model": "fake-model", "on": "2026-10-13"}
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
    assert not filters.passes(**args, filters=f, job_type="non_data")[0]
    assert filters.passes(**args, filters=f, job_type=None)[0]


def test_taxonomy_ids_are_unique_and_described():
    types = jobtypes.taxonomy()["types"]
    assert len({t["id"] for t in types}) == len(types)
    assert all(t["name"] and t["desc"] for t in types)
