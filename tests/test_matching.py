from datetime import date

from jobpost import matching

TODAY = date(2026, 10, 13)
PROFILE = {"careerStart": "2016-12", "currentRole": "data_eng", "targetRoles": ["data_arch"],
           "skills": ["SQL", "python", "Databricks", "빅쿼리", "Power BI", "사내툴"]}


def test_extract_skills_uses_aliases_and_boundaries():
    text = "PySpark와 Airflow로 데이터 파이프라인 구축, BigQuery·Databricks 운영. Research 경험, R&D 조직. go to market"
    found = matching.extract_skills(text)
    assert {"Spark", "Airflow", "BigQuery", "Databricks", "ETL"} <= found
    assert "검색" not in found and "Golang" not in found


def test_canonical_skills_drops_unknown():
    assert matching.canonical_skills(PROFILE["skills"]) == {"SQL", "Python", "Databricks", "BigQuery", "Power BI"}


def test_score_parts():
    posting = {"jobType": "data_eng", "careerMin": 7, "careerMax": 15}
    s = matching.score(PROFILE, posting, {"SQL", "Python", "Spark", "Kafka"}, TODAY)
    assert s["parts"] == {"job": 40, "career": 20, "skills": 20}
    assert s["score"] == 80 and s["matched"] == ["Python", "SQL"] and s["missing"] == ["Kafka", "Spark"]


def test_interchangeable_skills_count_once():
    posting = {"jobType": "data_eng", "careerMin": 7, "careerMax": 15}
    # Snowflake·Redshift는 Databricks·BigQuery와 같은 묶음, AWS·Azure는 클라우드 묶음(나는 없음)
    s = matching.score(PROFILE, posting, {"Snowflake", "Redshift", "AWS", "Azure"}, TODAY)
    assert s["parts"]["skills"] == 10  # 2개 단위 중 1개, 분모는 최소 4
    assert s["matched"] == ["BigQuery", "Databricks"] and s["missing"] == ["AWS·Azure"]


def test_score_related_job_short_career_and_no_body():
    posting = {"jobType": "mlops", "careerMin": 12, "careerMax": None}
    s = matching.score(PROFILE, posting, None, TODAY)
    # 가까운 직무 20, 경력 2년 모자람 20-14=6, 본문 없음 20
    assert s["parts"] == {"job": 20, "career": 6, "skills": 20}


def test_career_years_matches_the_web():
    assert matching.career_years("2016-12", TODAY) == 10
    assert matching.career_years("2027-01", TODAY) is None
