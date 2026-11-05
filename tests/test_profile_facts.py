import json
from datetime import date

from test_recommend import BODIES, SCREEN

from jobpost import facts, feedback, profile

TODAY = date(2026, 10, 14)
V2 = {
    "schema": 2,
    "careers": [
        {"company": "한샘", "industry": "consumer", "start": "2016-12", "end": "2023-11",
         "roles": [{"role": "pi", "start": "2016-12", "end": "2018-03"},
                   {"role": "analyst", "start": "2018-04", "end": "2022-10"},
                   {"role": "data_eng", "start": "2022-11", "end": "2023-11"}]},
        {"company": "포스코이앤씨", "industry": "construction", "start": "2023-11", "end": "",
         "roles": [{"role": "other", "roleName": "BI 플랫폼 운영", "start": "2023-11", "end": "2025-12"}]},
    ],
    "targetRoles": ["data_eng"],
    "skills": [{"name": "SQL", "level": 4}, {"name": "Python", "level": 2}],
    "education": {"degree": "학사", "major": "건축공학", "majorGroup": "공학(기타)"},
    "english": "읽기·쓰기",
}


def test_months_and_role_years():
    assert profile.months("2026-01", "2026-09", TODAY) == 9
    assert profile.months("2026-01", "", TODAY) == 10  # 이번 달까지
    years = profile.role_years(V2, TODAY)
    assert round(years["데이터 엔지니어"], 1) == 1.1 and round(years["데이터 분석가"], 1) == 4.6
    assert "BI 플랫폼 운영" in years  # 기타는 직접 쓴 이름으로


def test_career_totals_drop_non_data_roles():
    total, data_years = profile.career_totals(V2, TODAY)
    assert round(total, 1) == 10.0 and round(data_years, 1) == 8.7  # PI 기획 16개월을 뺌


def test_rule_view_and_text():
    v = profile.rule_view(V2)
    assert v["careerStart"] == "2016-12" and v["currentRole"] == "other" and v["skills"] == ["SQL", "Python"]
    t = profile.text(V2, TODAY)
    assert "포스코이앤씨 (건설·부동산) 2023.11~현재" in t and "SQL(4 전문)" in t and "[학력] 학사 건축공학" in t


def test_facts_run_extracts_wanted_postings_once(tmp_path):
    class AI:
        model = "fake"

        def __init__(self):
            self.prompts = []

        def json(self, prompt, schema):
            self.prompts.append(prompt)
            return {"level": "시니어", "duties": ["파이프라인 구축"], "required_skills": ["Apache Spark", "Airflow"],
                    "preferred_skills": ["dbt"], "years": [], "domain_required": [], "domain_preferred": [],
                    "degree": "무관", "majors": [], "certs": [], "english": "적혀 있지 않음", "work_mode": "출근"}

    ai = AI()
    s = facts.run(tmp_path, SCREEN, BODIES, ["z:1", "z:2"], ai, "2026-10-14", max_calls=250)
    assert s == {"wanted": 2, "pending": 0, "done": 1, "calls": 1}  # 본문 없는 z:2는 건너뜀
    assert facts.load(tmp_path)["z:1"]["facts"]["level"] == "시니어"
    assert facts.run(tmp_path, SCREEN, BODIES, ["z:1"], ai, "2026-10-15")["pending"] == 0 and len(ai.prompts) == 1


def test_skill_catalog_merges_dictionary_and_extracted_names():
    rows = {"z:1": {"facts": {"required_skills": ["Apache Spark", "Great Expectations"], "preferred_skills": []}},
            "z:2": {"facts": {"required_skills": ["great expectations"], "preferred_skills": ["그런 경험이 있으신 분을 찾고 있어요 정말로요 진짜로"]}}}
    cat = {c["name"]: c["count"] for c in facts.skill_catalog({"z:1": "Spark와 Airflow"}, rows)}
    assert cat["Spark"] == 1 and cat["Airflow"] == 1  # 사전 이름으로 맞춤
    assert cat["Great Expectations"] == 2  # 사전에 없어도 두 공고 이상이면 넣는다
    assert not any(len(n) > 30 for n in cat)


def test_feedback_metrics_and_report():
    labels = {"a": "good", "b": "good", "c": "bad", "d": "maybe"}
    scores = {"a": 90, "b": 50, "c": 70, "d": 60}
    m = feedback.metrics(list(labels), labels, scores.get)
    assert m == {"n": 4, "high": {"good": 1, "maybe": 0, "bad": 0}, "mid": {"good": 0, "maybe": 1, "bad": 1},
                 "low": {"good": 1, "maybe": 0, "bad": 0}}  # 구간: 80 이상 a, 60~79 c·d, 60 미만 b

    sample = [{"id": k, "company": "회사", "title": f"공고 {k}"} for k in "abcde"]
    item = {"kind": "핵심 업무", "weight": 60, "fit": "충족", "name": "파이프라인", "posting": "-", "me": "-"}
    matches = [{"user_id": "u1", "posting_id": k, "score": v, "score_v": 1, "reason_meta": {"model": "fake"},
                "parts": {"kind": "ai", "rule": 80, "verdict": "고려", "items": [item]}} for k, v in scores.items()]
    rows = [{"user_id": "u1", "posting_id": k, "label": v, "comment": None, "match_key": "g1"} for k, v in labels.items()]
    rows.append({"user_id": "u1", "posting_id": "b", "label": "good", "comment": "핵심 업무가 딱 맞음", "match_key": "g2"})
    text = "\n".join(feedback.report(sample, matches, rows))
    assert "기준 샘플 5건 중 평가 4건 ○ 2 △ 1 × 1, AI 결과 4건 (지침 v1 · fake)" in text
    assert "AI 점수: 80점 이상 1건(○ 1 △ 0 × 0), 60~79점 2건(○ 0 △ 1 × 1), 60점 미만 1건(○ 1 △ 0 × 0)" in text
    assert "미달" in text  # 60점 미만에 ○가 있다
    assert "규칙 점수: 80점 이상 4건(○ 2 △ 1 × 1)" in text  # 규칙 점수가 다 80
    assert "○ AI 50(고려) 규칙 80 | 회사 | 공고 b | 코멘트: 핵심 업무가 딱 맞음" in text  # ○인데 60 미만
    assert "[아직 평가 안 함 1건]" in text
    public = "\n".join(feedback.report(sample, matches, rows, private=False))  # 공개 로그용: 건수·지표만
    assert "AI 점수: 80점 이상 1건" in public and "[아직 평가 안 함 1건]" in public
    assert "공고 b" not in public and "코멘트" not in public and "나:" not in public
    dump = feedback.sample_dump(sample, matches, rows)
    assert len(dump) == 4 and dump[0].startswith("SMP\t") and '"score": 90' in dump[0]
    assert '"label": "good", "comment": "핵심 업무가 딱 맞음"' in dump[3]  # b(50점), 최신 평가


def test_feedback_candidates_replace_closed_sample():
    sample = [{"id": "s1", "group": "규칙 상위", "title": "샘플 1"}, {"id": "s2", "group": "직무별:data_eng", "title": "샘플 2"},
              {"id": "s3", "group": "무작위", "title": "샘플 3"}]
    open_postings = [{"id": "s1", "company": "k", "title": "샘플 1"}]  # s2·s3은 마감
    open_postings += [{"id": f"p{i}", "company": "k", "title": f"공고 {i}", "jobType": "data_eng" if i % 2 else "analyst"}
                      for i in range(6)]
    open_postings.append({"id": "same", "company": "k", "title": "샘플 2"})  # 샘플과 제목이 같은 공고는 빼다
    rows = [{"user_id": "u1", "posting_id": f"p{i}", "score": 50, "rule": 10 * i, "kind": "ai" if i < 3 else None}
            for i in range(6)]
    rows += [{"user_id": "u1", "posting_id": "s1", "score": 90, "rule": 99, "kind": "ai"},
             {"user_id": "u1", "posting_id": "same", "score": 90, "rule": 99, "kind": "ai"},
             {"user_id": "u1", "posting_id": "gone", "score": 90, "rule": 99, "kind": "ai"}]  # 화면에 없는 공고
    out = feedback.candidates(sample, open_postings, {"k": "회사"}, rows, n=4)
    assert out[0] == "== 사용자 u1: 마감된 샘플 2건, 바꿀 후보 공고 6건"
    assert [x for x in out if x.startswith("CLOSED")] == ['CLOSED\t{"id": "s2", "group": "직무별:data_eng"}',
                                                          'CLOSED\t{"id": "s3", "group": "무작위"}']
    cands = [json.loads(x.split("\t", 1)[1]) for x in out if x.startswith("CAND")]
    assert [c["id"] for c in cands if c["group"] == "규칙 상위"] == ["p5", "p4", "p3", "p2"]
    assert [c["id"] for c in cands if c["group"] == "판단 갈림"] == ["p0", "p1", "p2"]  # AI 점수가 있는 것만, 차이 큰 순
    assert {c["jobType"] for c in cands if c["group"] == "직무별:data_eng"} == {"data_eng"}
    assert all(c["company"] == "회사" for c in cands) and not any(c["id"] in {"s1", "same", "gone"} for c in cands)


class FakeMemoAI:
    model = "fake"

    def __init__(self):
        self.prompts = []

    def json(self, prompt, schema):
        self.prompts.append(prompt)
        return {"lines": ["코드로 ETL을 직접 개발한 경험 없음", "  영어 업무   어려움 "]}


def test_memo_uses_latest_comments_only():
    rows = [{"user_id": "u1", "posting_id": "a", "label": "maybe", "comment": "예전 생각"},
            {"user_id": "u1", "posting_id": "a", "label": "bad", "comment": "elt를 코드로 날개발해 본 적 없음"},
            {"user_id": "u1", "posting_id": "b", "label": "good", "comment": None},
            {"user_id": "u2", "posting_id": "a", "label": "good", "comment": "다른 사람"}]
    got = feedback.latest_comments(rows, "u1", {"a": ("회사A", "데이터 엔지니어")})
    assert got == [{"label": "bad", "company": "회사A", "title": "데이터 엔지니어", "comment": "elt를 코드로 날개발해 본 적 없음"}]
    ai = FakeMemoAI()
    assert feedback.memo_lines(got, ["예전 메모"], ai) == ["코드로 ETL을 직접 개발한 경험 없음", "영어 업무 어려움"]
    assert "× 회사A | 데이터 엔지니어 | elt를" in ai.prompts[0] and "- 예전 메모" in ai.prompts[0]
    assert feedback.memo_lines([], ["그대로"], ai) == ["그대로"] and len(ai.prompts) == 1  # 코멘트가 없으면 AI를 부르지 않는다


def test_funnel_and_ranking_for_private_report():
    screen = {"companies": {"a": {"name": "가나다", "type": "대기업"}, "b": {"name": "작은회사", "type": "그 외"}},
              "jobTypes": [{"id": "data_eng", "name": "데이터 엔지니어"}, {"id": "software", "name": "개발"}],
              "postings": [
                  {"id": "1", "company": "a", "title": "데이터 엔지니어", "jobType": "data_eng", "careerMin": 7, "careerMax": None,
                   "regions": ["서울"], "employment": ["정규직"], "noise": None},
                  {"id": "2", "company": "b", "title": "데이터 엔지니어", "jobType": "data_eng", "careerMin": 7, "careerMax": None,
                   "regions": ["서울"], "employment": ["정규직"], "noise": None},
                  {"id": "3", "company": "a", "title": "백엔드", "jobType": "software", "careerMin": 7, "careerMax": None,
                   "regions": ["서울"], "employment": [], "noise": None},
                  {"id": "4", "company": "a", "title": "데이터 엔지니어 인턴", "jobType": "data_eng", "careerMin": None,
                   "careerMax": None, "regions": ["서울"], "employment": ["인턴직"], "noise": None},
                  {"id": "5", "company": "a", "title": "데이터 입력", "jobType": None, "careerMin": None, "careerMax": None,
                   "regions": [], "employment": [], "noise": "잡음"}]}
    f = {"job_types": ["data_eng"], "company_types": ["대기업"], "employment_types": ["정규직"]}
    lines = feedback.funnel(screen, "user-0001", f)
    assert lines[1] == ("FUNNEL\tuser-000\t열린 공고 5 → 잡음 빼고 4 → 제외 키워드 4 → 제외 회사 4 → 직무 유형 3 → "
                        "기업 구분 2 → 경력 2 → 지역 2 → 고용 형태 1")
    assert lines[2] == "JOBTYPES\tuser-000\t✔데이터 엔지니어 3, ·개발 1"
    rows = [{"user_id": "user-0001", "posting_id": "1", "score": 70, "rule": 60, "kind": "ai", "score_v": 2},
            {"user_id": "user-0001", "posting_id": "3", "score": 80, "rule": 90, "kind": "rule", "score_v": 1}]
    got = [json.loads(x.split("\t", 1)[1]) for x in feedback.ranking(screen, rows)]
    assert [(g["rule"], g["ai"]) for g in got] == [(90, None), (60, 70)]


def test_clean_domain():
    from jobpost import facts
    text = ("주요업무\n- 보험·금융 도메인 특화 파인튜닝 전략 수립\n자격요건\n- 데이터 엔지니어링 5년\n"
            "- 금융업권 데이터 관련 법규에 대한 이해\n우대사항\n- 보험업 데이터  Domain 이해\n"
            "- 스타트업, 소규모 성장조직 경험\n- 라이브 스트리밍 서비스에 대한 관심\n- 보험, 금융, 제조 분야의 비즈니스 지식")
    got = facts.clean_domain({"company_domain": ["IN0104", "IN0101", "IN0103"], "domain_quotes": [
        "보험·금융 도메인 특화 파인튜닝 전략 수립",       # 주요업무 아래 → 버림
        "금융업권 데이터 관련 법규에 대한 이해",          # 자격요건 → 금융 필수
        "보험업 데이터 Domain 이해",                     # 공백이 달라도 본문에 있음 → 보험 우대
        "스타트업, 소규모 성장조직 경험",                 # 업종 말 없음 → unmatched
        "라이브 스트리밍 서비스에 대한 관심",              # 관심만 → 버림
        "이커머스 경험 필수",                            # 본문에 없음 → 버림
    ]}, text)
    # 금융 필수 + 보험 우대는 둘 다 남는다(필수/우대가 달라서). 제조는 AI가 빠뜨린 '보험, 금융, 제조 분야' 문장을 코드가 찾아서
    assert sorted((d["code"], d["need"]) for d in got["domain_exp"]) == [("IN01", "필수"), ("IN0104", "우대"), ("IN04", "우대")]
    assert got["domain_required"] == ["IN01"] and sorted(got["domain_preferred"]) == ["IN0104", "IN04"]
    assert got["domain_unmatched"] == ["스타트업, 소규모 성장조직 경험"]
    assert got["company_domain"] == ["IN0104", "IN0101"]
    only_pref = facts.clean_domain({"domain_quotes": []}, "우대사항\n- 보험, 금융, 제조 분야의 비즈니스 지식")
    assert [(d["code"], d["need"]) for d in only_pref["domain_exp"]] == [("IN01", "우대"), ("IN04", "우대")]


def test_facts_recompute_domain_without_ai(tmp_path):
    """업종 사전·규칙이 바뀌면 저장된 문장으로 업종 경험만 다시 계산한다(AI를 부르지 않음)."""
    import json as _json

    from jobpost import config, facts
    body = "자격요건\n- 금융 데이터 분석 경험 3년 이상\n우대사항\n- 보험업 데이터 이해"
    row = {"uid": "p:1", "prompt": facts.PROMPT_VERSION, "industries_v": config.load("profile")["version"], "body": True,
           "words": "old", "facts": {"domain_quotes": ["보험업 데이터 이해"], "company_domain": ["IN0104"]}}
    (tmp_path / facts.FILE).write_text(_json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    screen = {"postings": [{"id": "p:1", "company": "c", "title": "데이터 엔지니어"}], "companies": {"c": {"name": "가나보험"}}}
    out = facts.run(tmp_path, screen, {"bodies": {"p:1": {"text": body}}}, ["p:1"], None, "2026-11-05")
    assert out["recomputed"] == 1 and out["calls"] == 0
    got = facts.load(tmp_path)["p:1"]
    assert got["words"] == facts.words_hash()
    assert sorted((d["code"], d["need"]) for d in got["facts"]["domain_exp"]) == [("IN01", "필수"), ("IN0104", "우대")]
