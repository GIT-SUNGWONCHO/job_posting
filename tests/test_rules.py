from datetime import date

from jobpost import dedup
from jobpost.filters import passes
from jobpost.models import CompanyType, DeadlineType, Posting, Source
from jobpost.normalize import career_text, clean_company, company_key, deadline_text
from jobpost.scope import in_scope, is_overseas, noise_reason


def test_company_names():
    assert clean_company("삼성생명보험(주)") == "삼성생명보험"
    assert clean_company("(주)에스더블유엠") == "에스더블유엠"
    assert company_key("삼성생명보험(주)") == company_key("삼성생명")
    assert company_key("주식회사 카카오페이") == company_key("카카오페이")


def test_career_and_deadline_text():
    assert career_text(1, 10) == "경력 1~10년"
    assert career_text(8, None) == "경력 8년 이상"
    assert career_text(None, 5) == "경력 5년 이하"
    assert career_text(None, None) == "연차 무관"
    assert career_text(None, 0) == "신입"
    today = date(2026, 10, 13)
    assert deadline_text(DeadlineType.DATE, date(2026, 10, 25), today) == "D-12"
    assert deadline_text(DeadlineType.DATE, today, today) == "D-day"
    assert deadline_text(DeadlineType.ALWAYS, None, today) == "상시"


def _p(title, source=Source.SARAMIN, categories=()):
    return Posting(source=source, source_id="1", url="u", company="c", title=title,
                   categories=list(categories))


def test_scope_and_noise():
    assert in_scope(_p("데이터 엔지니어 채용"))
    assert in_scope(_p("[SDF] AI 플랫폼 개발"))
    assert not in_scope(_p("Retail 매장 관리"))  # AI가 단어 안에만 있음
    assert not in_scope(_p("경영기획 담당자"))  # 사람인 분류만 걸린 공고
    assert in_scope(_p("백엔드 개발", source=Source.ZIGHANG, categories=["AI_데이터"]))
    assert noise_reason(_p("데이터센터 설비 엔지니어"))
    assert noise_reason(_p("AI 솔루션 영업 담당"))
    assert noise_reason(_p("데이터 엔지니어")) is None
    abroad = _p("Data Engineer", source=Source.ZIGHANG, categories=["AI_데이터"])
    abroad.regions = ["해외"]
    assert in_scope(abroad) and is_overseas(abroad)  # 저장은 하되 해외로 표시
    abroad.regions = ["해외", "서울"]
    assert not is_overseas(abroad)


def _item(uid, source, company, title, deadline=None):
    return dedup.Item(uid=uid, source=source, company=company, title=title, deadline=deadline)


def test_dedup_cross_source():
    items = [
        _item("zighang:a", "zighang", "삼성생명", "경력사원 채용 – 데이터 엔지니어"),
        _item("saramin:1", "saramin", "삼성생명보험(주)", "경력사원 채용(데이터 엔지니어)"),
        _item("remember:9", "remember", "카카오페이", "데이터 엔지니어 - 데이터 플랫폼"),
    ]
    rep = dedup.cluster(items)
    assert rep["zighang:a"] == rep["saramin:1"] == "zighang:a"
    assert rep["remember:9"] == "remember:9"


def test_dedup_keeps_different_teams_and_dates():
    items = [
        _item("zighang:a", "zighang", "네이버", "[검색팀] 데이터 엔지니어"),
        _item("saramin:1", "saramin", "네이버(주)", "[광고팀] 데이터 엔지니어"),
        _item("remember:1", "remember", "토스", "데이터 엔지니어", date(2026, 10, 1)),
        _item("saramin:2", "saramin", "토스", "데이터 엔지니어", date(2026, 12, 1)),
        _item("zighang:b", "zighang", "토스뱅크", "데이터 엔지니어"),
    ]
    rep = dedup.cluster(items)
    assert rep["zighang:a"] != rep["saramin:1"]
    assert rep["remember:1"] != rep["saramin:2"]
    assert rep["zighang:b"] == "zighang:b"


def test_dedup_pairs_one_to_one():
    items = [
        _item("zighang:pre", "zighang", "카카오", "LLM Research Engineer (Pre-training) (신입/경력)"),
        _item("zighang:post", "zighang", "카카오", "LLM Research Engineer (Post-training) (신입/경력)"),
        _item("saramin:pre", "saramin", "(주)카카오", "LLM Research Engineer (Pre-training) (신입/경력)"),
        _item("saramin:post", "saramin", "(주)카카오", "LLM Research Engineer (Post-training) (신입/경력)"),
    ]
    rep = dedup.cluster(items)
    assert rep["zighang:pre"] == rep["saramin:pre"]
    assert rep["zighang:post"] == rep["saramin:post"]
    assert rep["zighang:pre"] != rep["zighang:post"]


def test_dedup_zighang_copies_from_other_platforms():
    a = dedup.Item(uid="zighang:a", source="zighang", company="우아한형제들", title="데이터엔지니어링", via=None)
    b = dedup.Item(uid="zighang:b", source="zighang", company="우아한형제들", title="데이터엔지니어링", via="잡코리아")
    rep = dedup.cluster([a, b])
    assert rep["zighang:a"] == rep["zighang:b"]


def test_dedup_never_merges_same_source():
    items = [
        _item("saramin:1", "saramin", "LG CNS", "데이터 엔지니어"),
        _item("saramin:2", "saramin", "LG CNS", "데이터 엔지니어"),
    ]
    rep = dedup.cluster(items)
    assert rep["saramin:1"] == "saramin:1" and rep["saramin:2"] == "saramin:2"


FILTERS = {
    "exclude_keywords": ["데이터 입력"],
    "exclude_companies": ["현재회사"],
    "always_companies": ["○○캐피탈"],
    "company_types": ["대기업", "공기업·공공기관", "외국계"],
    "career": {"min": 7, "max": 15},
    "regions": ["서울", "경기", "원격"],
}


def _pass(**kw):
    base = dict(title="데이터 엔지니어", company="삼성생명", company_type=CompanyType.LARGE,
                career_min=5, career_max=None, regions=["서울"], filters=FILTERS)
    base.update(kw)
    return passes(**base)[0]


def test_personal_filters():
    assert _pass()
    assert not _pass(title="데이터입력 알바")
    assert not _pass(company="현재회사")
    assert not _pass(company_type=CompanyType.OTHER)
    assert _pass(company="○○캐피탈", company_type=CompanyType.OTHER)
    assert not _pass(career_min=3, career_max=6)  # 7년 미만에서 끝남
    assert not _pass(career_min=None, career_max=0)  # 신입만
    assert _pass(career_min=None, career_max=None)  # 연차 무관은 통과
    assert not _pass(regions=["부산"])
    assert _pass(regions=["부산"], title="데이터 엔지니어(재택)")
    assert _pass(regions=[])  # 지역 정보가 없으면 통과


def test_group_rules():
    from jobpost.companies import match_group

    assert match_group("NHN KCP") == "NHN"
    assert match_group("NH투자증권") == "농협"
    assert match_group("ktcloud") == "KT"
    assert match_group("삼성생명보험(주)") == "삼성"
    assert match_group("삼성제약") is None
    assert match_group("롯데이노베이트") == "롯데"
    assert match_group("롯데카드") is None
