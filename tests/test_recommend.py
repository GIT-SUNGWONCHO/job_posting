from datetime import date

from jobpost import recommend

TODAY = date(2026, 10, 13)
SCREEN = {
    "companies": {"a": {"name": "가나다", "type": "대기업", "group": None},
                  "b": {"name": "라마바", "type": "그 외", "group": None}},
    "postings": [
        {"id": "z:1", "company": "a", "title": "Data Engineer", "jobType": "data_eng", "careerMin": 5,
         "careerMax": None, "career": "경력 5년 이상", "regions": ["서울"], "noise": None},
        {"id": "z:2", "company": "a", "title": "Data Analyst", "jobType": "analyst", "careerMin": None,
         "careerMax": None, "career": "연차 무관", "regions": ["서울"], "noise": None},
        {"id": "z:3", "company": "b", "title": "Data Engineer", "jobType": "data_eng", "careerMin": 5,
         "careerMax": None, "career": "경력 5년 이상", "regions": ["서울"], "noise": None},
    ],
}
BODIES = {"bodies": {"z:1": {"text": "Spark, Airflow, Databricks로 데이터 파이프라인 구축", "source": "zighang"}}}
PROFILE = {"careerStart": "2016-12", "currentRole": "data_eng", "targetRoles": ["data_eng"],
           "jobs": [{"company": "비밀회사", "industry": "대형 건설사", "start": "2023-11", "end": "", "role": "데이터 플랫폼 리드"}],
           "projects": [{"title": "메타데이터 정리", "result": "테이블 500여 개 → 18개"}],
           "skills": ["Databricks", "Airflow", "SQL"]}


class FakeDB:
    def __init__(self, old=None):
        self.rows = {"profiles": [{"user_id": "u1", "data": PROFILE, "version": 3}],
                     "settings": [{"user_id": "u1", "filters": {"company_types": ["대기업"], "job_types": ["data_eng", "analyst"]}}],
                     "matches": old or []}
        self.deleted, self.inserted = [], []

    def select(self, table, query="select=*"):
        return self.rows[table]

    def delete(self, table, query):
        self.deleted.append((table, query))

    def insert(self, table, rows):
        self.inserted += rows


class FakeAI:
    model = "fake"

    def __init__(self):
        self.prompts = []

    def json(self, prompt, schema):
        self.prompts.append(prompt)
        if "Data Analyst" in prompt:  # 늘 너무 긴 답 → 두 번 묻고 버림
            return [{"i": 0, "reason": "x" * 200}]
        return [{"i": 0, "reason": "Databricks·Airflow 경험이 파이프라인 구축과 맞음"}]


def test_run_scores_filtered_postings_and_writes_reasons():
    db, ai = FakeDB(), FakeAI()
    s = recommend.run(SCREEN, BODIES, db, ai, TODAY)
    # 공고마다 한 번씩, 긴 답이 온 공고는 한 번 더 물음
    assert s == {"profiles": 1, "users": 1, "rows": 2, "reasons_new": 1, "reasons_reused": 0, "calls": 3}
    assert db.deleted == [("matches", "user_id=eq.u1")]
    by = {r["posting_id"]: r for r in db.inserted}
    assert set(by) == {"z:1", "z:2"}  # z:3은 기업 구분 필터에서 빠짐
    assert by["z:1"]["reason"].startswith("Databricks") and by["z:1"]["profile_v"] == 3
    assert by["z:2"]["reason"] is None  # 너무 긴 답은 버림
    assert by["z:1"]["score"] > by["z:2"]["score"]
    assert "비밀회사" not in ai.prompts[0] and "대형 건설사" in ai.prompts[0]


def test_run_reuses_reason_for_same_profile_version():
    old = [{"posting_id": "z:1", "reason": "지난 이유", "profile_v": 3,
            "reason_meta": {"prompt": recommend.PROMPT_VERSION, "model": "fake"}}]
    db, ai = FakeDB(old), FakeAI()
    s = recommend.run(SCREEN, BODIES, db, ai, TODAY)
    assert s["reasons_reused"] == 1
    assert {r["posting_id"]: r["reason"] for r in db.inserted}["z:1"] == "지난 이유"
