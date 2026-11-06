"""기준 목록(config/taxonomy/) 검사와, 코드로 옮기기 전 보기가 옮기기 전 설정과 같은지(2026-11-03 옮긴 시점)."""

from pathlib import Path

import pytest
import yaml

from jobpost import config, taxonomy
from jobpost.models import CompanyType

OLD = Path(__file__).parent / "fixtures" / "taxonomy_v0"


def old(name):
    return yaml.safe_load((OLD / f"{name}.yaml").read_text(encoding="utf-8"))


def test_taxonomy_is_valid():
    taxonomy.validate()


def test_job_types_view_matches_old_file():
    o, n = old("job_types"), config.load("job_types")
    strip = lambda t: {k: v for k, v in t.items() if k != "code"}  # noqa: E731
    assert [strip(t) for t in n["types"]][:13] == [
        {k: v for k, v in t.items()} for t in o["types"] if t.get("family", "data") == "data"]
    assert {t["id"] for t in n["types"]} == {t["id"] for t in o["types"]}
    assert n["legacy"] == o["legacy"]


def test_skills_view_matches_old_file():
    o, n = old("skills"), config.load("skills")
    assert n["interchangeable"] == o["interchangeable"]
    # 2026-11-06 D 점검으로 스킬·별칭을 더했다(v2). 예전 스킬과 별칭은 모두 그대로 남아 있어야 한다
    new = {i["name"]: set(i["aliases"]) for items in n["groups"].values() for i in items}
    dropped = {"랭킹"}  # 2026-11-06 정확도 시험: '인기 랭킹'이 검색으로 잡혀 뺐다(v4)
    for items in o["groups"].values():
        for i in items:
            assert set(i.get("aliases") or []) - dropped <= new[i["name"]], i["name"]


def test_profile_and_guide_views_match_old_files():
    o, n = old("profile"), config.load("profile")
    for k in ("skill_levels", "project_parts", "degrees", "major_groups", "english", "english_low", "want_levels", "roles"):
        got = n[k] if k != "roles" else [{x: v for x, v in r.items() if x != "code"} for r in n[k]]
        assert got == o[k], k
    # 업종은 2026-11-04 B로 바뀌었다(시장 기준 38개). 2026-11-06부터 id는 코드, 지난 23개 id는 legacy로 남아 이어진다
    assert {i["id"] for i in o["industries"]} <= {i["legacy"] for i in n["industries"]}
    assert all(i["id"] == i["code"] for i in n["industries"])
    assert n["version"] == 2
    og, ng = old("match_guide"), config.load("match_guide")
    assert ng["item_kinds"] == og["item_kinds"] and ng["posting_facts"] == og["posting_facts"]
    assert list(ng["fit"]) == taxonomy.names("fits")


def test_company_types_match_enum():
    assert sorted(t.value for t in CompanyType) == sorted(taxonomy.names("company_types"))


def test_profile_role_codes_exist():
    codes = {x["code"] for x in [*taxonomy.fields(), *taxonomy.job_types()]}
    for r in config.load("profile")["roles"]:
        assert r.get("code") is None or r["code"] in codes, r


def test_code_of_legacy_ids():
    assert taxonomy.code_of("data_eng") == "JT001"
    assert taxonomy.code_of("software") == taxonomy.code_of("f_sw")
    assert taxonomy.code_of("bank").startswith("IN01")
    assert taxonomy.code_of("nope") is None


def test_validate_catches_duplicate(monkeypatch):
    jobs = dict(taxonomy.raw("jobs"))
    jobs["types"] = [*jobs["types"], {**jobs["types"][0], "legacy": "dup"}]
    monkeypatch.setattr(taxonomy, "raw", lambda name: jobs if name == "jobs" else taxonomy.raw.__wrapped__(name))
    with pytest.raises(taxonomy.TaxonomyError):
        taxonomy.validate()


def test_industry_from_ksic():
    assert taxonomy.industry_from_ksic("64110") == ("IN0101", "ksic")      # 은행
    assert taxonomy.industry_from_ksic("47912") == ("IN0201", "ksic")      # 무점포 소매 → 이커머스(47보다 479가 먼저)
    assert taxonomy.industry_from_ksic("58211") == ("IN0602", "ksic")      # 게임 소프트웨어
    assert taxonomy.industry_from_ksic("58221") == (None, "generic")       # 응용 소프트웨어 → 공고 정리로
    assert taxonomy.industry_from_ksic("64992") == (None, "generic")       # 지주회사(649보다 먼저)
    # 2026-11-04 리뷰에서 고친 것
    assert taxonomy.industry_from_ksic("64201") == ("IN0103", "ksic")      # 자산운용(642)
    assert taxonomy.industry_from_ksic("66202") == ("IN0104", "ksic")      # 보험 대리점(662)
    assert taxonomy.industry_from_ksic("66199") == ("IN0105", "ksic")      # 간편결제
    assert taxonomy.industry_from_ksic("20494") == ("IN0404", "ksic")      # 화약은 화학(화장품은 2042만)
    assert taxonomy.industry_from_ksic("27211") == ("IN0403", "ksic")      # 정밀·제어기기는 의료기기가 아님
    assert taxonomy.industry_from_ksic("76110") == ("IN0701", "ksic")      # 자동차 임대
    assert taxonomy.industry_from_ksic("71519") == (None, "generic")       # 회사 본부
    assert taxonomy.industry_from_ksic("47993") == ("IN0202", "ksic")      # 방문판매는 이커머스 아님
    # DART 코드가 앞자리보다 짧아 여러 업종에 걸치면 정하지 않는다
    assert taxonomy.industry_from_ksic("649") == (None, "generic")         # 지주회사 포함
    assert taxonomy.industry_from_ksic("66") == (None, "generic")
    assert taxonomy.industry_from_ksic("715") == (None, "generic")
    assert taxonomy.industry_from_ksic("6420") == ("IN0103", "ksic")
    assert taxonomy.industry_from_ksic("25200") == ("IN0405", "ksic")      # 무기·총포탄 → 방산(25 금속가공보다 먼저)
    assert taxonomy.industry_from_ksic("46510") == (None, "generic")       # 컴퓨터·SW 도매(IT 리셀러) → 회사 도메인
    assert taxonomy.industry_from_ksic(None) == (None, "none")


def test_industry_fit():
    assert taxonomy.industry_fit("IN01", {"bank"}) == 1.0          # 금융(넓게) 요구, 은행 경력
    assert taxonomy.industry_fit("IN0104", {"IN0104"}) == 1.0
    assert taxonomy.industry_fit("IN0104", {"bank"}) == 0.5        # 같은 금융
    assert taxonomy.industry_fit("IN0104", {"commerce"}) == 0.0
    assert taxonomy.industry_fit("insurance", set()) == 0.0        # 지난 id도 읽는다
    assert taxonomy.industry_name("IN01") == "금융"
    assert taxonomy.industry_name("bank") == "은행·저축"


def test_industries_in():
    def names(q):
        return [taxonomy.industry_name(c) for c in taxonomy.industries_in(q)]
    assert names("금융권 보안 규정 이해") == ["금융"]                  # 보안*는 '규정' 앞이라 안 셈
    assert names("보안 업계 경험") == ["보안"]
    assert names("기계학습 모델, 엔터프라이즈 데이터, 제약 조건") == []  # 넓은 말 오탐 없음
    assert names("병리 이미지(WSI) 분석 또는 의료 영상 처리 경험") == ["의료기기·디지털 헬스"]
    assert names("증권·은행·카드사 등 금융 환경") == ["금융"]          # 대분류가 있으면 중분류는 뺌
    assert names("물류 또는 이커머스 분야") == ["이커머스", "물류·운송"]
    assert names("공공·금융·국방 분야 구축 경험") == ["금융", "공공", "중공업·조선·방산·항공"]  # 나열 뒤의 '분야'
    assert names("공공데이터 활용 분석 경험, 보안 업무 경험, 소셜 미디어 데이터") == []       # 넓은 말 오탐 없음


def test_migrate_profile_industries():
    from jobpost import migrate
    data = {"careers": [{"industry": "bank"}, {"industry": "IN0201"}, {"industry": ""}, {"industry": "없는값"}],
            "wants": {"industriesLike": ["health", "IN0602"], "industriesAvoid": ["construction"]}}
    new, changed, unknown = migrate.industry_data(data)
    assert [c["industry"] for c in new["careers"]] == ["IN0101", "IN0201", "", "없는값"]
    assert new["wants"] == {"industriesLike": ["IN0903", "IN0602"], "industriesAvoid": ["IN0502"]}
    assert (changed, unknown) == (3, 1) and data["careers"][0]["industry"] == "bank"  # 원본은 그대로

    class DB:
        def __init__(self):
            self.updated = []

        def select(self, table, query):
            return [{"user_id": "u1", "data": data}]

        def update(self, table, query, values):
            self.updated.append(values)

    db = DB()
    assert migrate.industries(db)["values"] == 3 and not db.updated  # --apply 없이는 세기만
