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
PROFILE = {
    "schema": 2,
    "careers": [{"company": "가람건설", "industry": "construction", "start": "2016-12", "end": "", "title": "대리",
                 "roles": [{"role": "data_eng", "start": "2016-12", "end": "", "summary": "마트 설계",
                            "projects": [{"title": "메타데이터 정리", "start": "2026-01", "end": "2026-09", "part": "단독",
                                          "summary": "테이블 500여 개 → 18개", "skills": ["Databricks"]}]}]}],
    "targetRoles": ["data_eng"],
    "skills": [{"name": "Databricks", "level": 3}, {"name": "Airflow", "level": 2}, {"name": "SQL", "level": 4}],
}
ITEMS = [
    {"kind": "핵심 업무", "name": "파이프라인 구축", "posting": "Spark 파이프라인", "me": "마트 설계", "fit": "일부", "weight": 50},
    {"kind": "필수 스킬", "name": "Airflow", "posting": "Airflow 필수", "me": "Airflow 2단계", "fit": "충족", "weight": 30},
    {"kind": "직급·수준", "name": "연차", "posting": "5년 이상", "me": "약 10년", "fit": "충족", "weight": 20},
]


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

    def __init__(self, fail_on=""):
        self.prompts, self.fail_on = [], fail_on

    def json(self, prompt, schema):
        self.prompts.append(prompt)
        if self.fail_on and self.fail_on in prompt:
            raise RuntimeError("429")
        return {"items": ITEMS, "verdict": "고려", "reason": "Databricks 마트 경험이 맞음", "gaps": ["Spark 경험"]}


def test_score_items_recomputes_from_weights_and_fit():
    assert recommend.score_items(ITEMS) == 75  # 50×0.5 + 30 + 20
    # 가중치 합이 100이 아니어도 맞춘다
    assert recommend.score_items([{**ITEMS[1], "weight": 3}, {**ITEMS[0], "weight": 1}]) == 88


def test_run_scores_candidates_with_ai_and_keeps_basis():
    db, ai = FakeDB(), FakeAI(fail_on="Data Analyst")
    s = recommend.run(SCREEN, BODIES, db, ai, TODAY)
    assert s["ai_new"] == 1 and s["rule_only"] == 1 and s["rows"] == 2 and s["errors"] == ["429"]
    by = {r["posting_id"]: r for r in db.inserted}
    assert set(by) == {"z:1", "z:2"}  # z:3은 기업 구분 필터에서 빠짐
    ai_row = by["z:1"]
    assert ai_row["score"] == 75 and ai_row["parts"]["kind"] == "ai" and ai_row["parts"]["verdict"] == "고려"
    assert ai_row["parts"]["items"] == ITEMS and ai_row["parts"]["rule"] > 0
    assert ai_row["matched"] == ["Airflow", "연차"] and ai_row["missing"] == ["Spark 경험"]
    assert ai_row["score_v"] == 1 and ai_row["profile_v"] == 3
    assert by["z:2"]["parts"]["kind"] == "rule"  # AI가 실패하면 규칙 점수만
    # 회사명까지 보낸다
    assert "가람건설" in ai.prompts[0] and "직무별 경력: 데이터 엔지니어" in ai.prompts[0]


def test_run_reuses_ai_result_for_same_profile_guide_and_model():
    first = FakeDB()
    recommend.run(SCREEN, BODIES, first, FakeAI(), TODAY)
    old = [{k: r[k] for k in ("posting_id", "score", "parts", "matched", "missing", "reason", "reason_meta",
                              "profile_v", "score_v")} for r in first.inserted]
    db, ai = FakeDB(old), FakeAI()
    s = recommend.run(SCREEN, BODIES, db, ai, TODAY)
    assert s["ai_reused"] == 2 and s["ai_new"] == 0 and not ai.prompts


def test_two_accounts_with_the_same_profile_share_ai_results():
    db, ai = FakeDB(), FakeAI()
    db.rows["profiles"] = [{"user_id": "u1", "data": PROFILE, "version": 3}, {"user_id": "u2", "data": PROFILE, "version": 5}]
    s = recommend.run(SCREEN, BODIES, db, ai, TODAY)
    assert s["users"] == 2 and s["ai_new"] == 2 and s["ai_reused"] == 2 and len(ai.prompts) == 2
    assert {r["user_id"] for r in db.inserted} == {"u1", "u2"}


def test_reused_rows_without_hash_still_cover_the_twin_account():
    first = FakeDB()
    recommend.run(SCREEN, BODIES, first, FakeAI(), TODAY)
    old = [{**r, "reason_meta": {k: v for k, v in (r["reason_meta"] or {}).items() if k != "profile_hash"} or None}
           for r in first.inserted]  # 해시를 붙이기 전에 만든 결과
    db, ai = FakeDB(old), FakeAI()
    db.rows["profiles"].append({"user_id": "u2", "data": PROFILE, "version": 9})
    s = recommend.run(SCREEN, BODIES, db, ai, TODAY)
    assert not ai.prompts and s["ai_reused"] == 4
