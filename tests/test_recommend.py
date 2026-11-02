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
BODIES = {"bodies": {"z:1": {"text": "Spark, Airflow, Databricks로 데이터 파이프라인 구축\n" + "담당 업무 설명 " * 40,
                             "source": "zighang"}}}
PROFILE = {
    "schema": 2,
    "careers": [{"company": "가람건설", "industry": "construction", "start": "2016-12", "end": "", "title": "대리",
                 "roles": [{"role": "data_eng", "start": "2016-12", "end": "", "summary": "마트 설계",
                            "projects": [{"title": "메타데이터 정리", "start": "2026-01", "end": "2026-09", "part": "단독",
                                          "summary": "테이블 500여 개 → 18개", "skills": ["Databricks"]}]}]}],
    "targetRoles": ["data_eng"],
    "skills": [{"name": "Databricks", "level": 3}, {"name": "Airflow", "level": 2}, {"name": "SQL", "level": 4}],
}
FACTS = {"level": "실무자", "english": "필요 없음", "employment": "정규직", "industry": "game"}
ITEMS = [
    {"kind": "핵심 업무", "name": "파이프라인 구축", "posting": "Spark 파이프라인", "me": "마트 설계", "fit": "일부", "weight": 50},
    {"kind": "필수 스킬", "name": "Airflow", "posting": "Airflow 필수", "me": "Airflow 2단계", "fit": "충족", "weight": 30},
    {"kind": "경력 연수·직급", "name": "연차", "posting": "5년 이상", "me": "약 10년", "fit": "충족", "weight": 20},
]


class FakeDB:
    def __init__(self, old=None):
        self.rows = {"profiles": [{"user_id": "u1", "data": PROFILE, "version": 3}],
                     "settings": [{"user_id": "u1", "filters": {"company_types": ["대기업"], "job_types": ["data_eng", "analyst"]}}],
                     "matches": old or [], "match_memos": []}
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
        return {"items": ITEMS, "posting": FACTS, "reason": "Databricks 마트 경험이 맞음", "gaps": ["Spark 경험"]}


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
    assert ai_row["score_v"] == 5 and ai_row["profile_v"] == 3
    assert ai_row["parts"]["base"] == 75 and ai_row["parts"]["posting"] == FACTS and ai_row["parts"]["adjust"] == []
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


def test_sample_run_scores_only_those_postings_regardless_of_filters():
    db, ai = FakeDB(), FakeAI()
    s = recommend.run(SCREEN, BODIES, db, ai, TODAY, only={"z:3"})  # z:3은 필터에서 빠지는 공고
    assert s["rows"] == 1 and [r["posting_id"] for r in db.inserted] == ["z:3"]
    assert db.deleted == [("matches", 'user_id=eq.u1&posting_id=in.("z:3")')]  # 나머지 줄은 그대로


def test_sample_ids_come_from_config():
    ids = recommend.sample_ids()
    assert len(ids) == 100 and len(set(ids)) == 100


def test_candidates_use_client_type_for_headhunting():
    screen = {"companies": {"firm": {"name": "서치펌", "type": "그 외"}},
              "postings": [{"id": "h", "company": "firm", "title": "데이터 엔지니어", "careerMin": 7, "careerMax": None,
                            "regions": ["서울"], "jobType": "data_eng", "noise": None, "clientType": "대기업"},
                           {"id": "x", "company": "firm", "title": "데이터 엔지니어", "careerMin": 7, "careerMax": None,
                            "regions": ["서울"], "jobType": "data_eng", "noise": None}]}
    got = recommend.candidates(screen, {"company_types": ["대기업"]})
    assert [p["id"] for p in got] == ["h"]


def test_verdict_follows_score_bands():
    assert [recommend.verdict(x) for x in (100, 80, 79, 60, 59, 0)] == ["지원 추천", "지원 추천", "고려", "고려", "비추천", "비추천"]


def test_adjust_caps_only_what_the_person_cannot_do():
    facts = {**FACTS, "level": "리더·관리자", "english": "필요", "industry": "game"}
    assert recommend.adjust(95, facts, "못함", ["정규직"]) == (65, ["영어로 일하는 공고라 최대 65점"])
    assert recommend.adjust(90, {**FACTS, "employment": "인턴"}, None, ["정규직"]) == (30, ["인턴 공고라 최대 30점"])
    assert recommend.adjust(90, facts, "능통", None) == (90, [])  # 직급·업종 취향은 점수에 넣지 않는다


def test_want_tags_show_preferences_without_scoring():
    wants = {"level": "실무자", "industriesAvoid": ["game"], "industriesLike": ["bank"]}
    assert recommend.want_tags({**FACTS, "level": "리더·관리자", "industry": "game"}, wants) == ["비선호 업종 게임", "리더·관리자 공고"]
    assert recommend.want_tags({**FACTS, "industry": "bank"}, wants) == ["선호 업종 금융(은행·카드)"]
    assert recommend.want_tags(FACTS, {}) == []


def test_changing_wants_reuses_ai_and_only_readjusts():
    first = FakeDB()
    recommend.run(SCREEN, BODIES, first, FakeAI(), TODAY)
    old = [{k: r[k] for k in ("posting_id", "score", "parts", "matched", "missing", "reason", "reason_meta",
                              "profile_v", "score_v")} for r in first.inserted]
    db, ai = FakeDB(old), FakeAI()
    db.rows["profiles"] = [{"user_id": "u1", "data": {**PROFILE, "wants": {"industriesAvoid": ["game"]}}, "version": 4}]
    recommend.run(SCREEN, BODIES, db, ai, TODAY)
    assert not ai.prompts  # 원하는 조건은 AI에 보내지 않아 다시 묻지 않는다
    row = next(r for r in db.inserted if r["posting_id"] == "z:1")
    assert row["score"] == 75 and row["parts"]["adjust"] == [] and row["parts"]["wants"] == ["비선호 업종 게임"]


def test_memo_goes_into_prompt_and_changes_the_profile_hash():
    db, ai = FakeDB(), FakeAI()
    db.rows["match_memos"] = [{"user_id": "u1", "memo": {"lines": ["코드로 ETL을 직접 개발한 경험 없음"]}}]
    recommend.run(SCREEN, BODIES, db, ai, TODAY)
    assert "[매칭 메모" in ai.prompts[0] and "- 코드로 ETL을 직접 개발한 경험 없음" in ai.prompts[0]
    old = [{k: r[k] for k in ("posting_id", "score", "parts", "matched", "missing", "reason", "reason_meta",
                              "profile_v", "score_v")} for r in db.inserted]
    again, ai2 = FakeDB(old), FakeAI()  # 메모가 없어지면 같은 프로필 버전이어도 다시 매긴다
    recommend.run(SCREEN, BODIES, again, ai2, TODAY)
    assert ai2.prompts


def test_no_body_caps_score_and_body_arrival_rematches():
    assert recommend.adjust(95, FACTS, None, None, has_body=False) == (70, ["본문이 없는 공고라 최대 70점"])
    short = {"bodies": {"z:1": {"text": "마감기한 상시채용", "source": "zighang"}}}
    first = FakeDB()
    recommend.run(SCREEN, short, first, FakeAI(), TODAY)
    row = next(r for r in first.inserted if r["posting_id"] == "z:1")
    assert row["parts"]["body"] is False and row["score"] == 70
    old = [{k: r[k] for k in ("posting_id", "score", "parts", "matched", "missing", "reason", "reason_meta",
                              "profile_v", "score_v")} for r in first.inserted]
    db, ai = FakeDB(old), FakeAI()
    recommend.run(SCREEN, BODIES, db, ai, TODAY)  # 본문 읽기로 본문이 생기면 다시 묻는다
    assert ai.prompts
