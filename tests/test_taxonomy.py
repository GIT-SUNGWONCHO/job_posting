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
    assert n["version"] == o["version"] and n["interchangeable"] == o["interchangeable"]
    # 2026-11-03 리뷰: Databricks를 데이터 처리 묶음에도 넣었다(묶음은 보기용, 판정·찾기 결과는 같다)
    got = {g: [(i["name"], i["aliases"]) for i in items if not (g == "데이터 처리" and i["name"] == "Databricks")]
           for g, items in n["groups"].items()}
    assert got == {g: [(i["name"], i.get("aliases") or []) for i in items] for g, items in o["groups"].items()}


def test_profile_and_guide_views_match_old_files():
    o, n = old("profile"), config.load("profile")
    for k in ("skill_levels", "project_parts", "degrees", "major_groups", "english", "english_low", "want_levels", "roles"):
        got = n[k] if k != "roles" else [{x: v for x, v in r.items() if x != "code"} for r in n[k]]
        assert got == o[k], k
    # 순서는 대분류로 묶여 바뀌었다(화면 순서만)
    assert sorted((i["id"], i["name"]) for i in n["industries"]) == sorted((i["id"], i["name"]) for i in o["industries"])
    assert n["version"] == o["version"]
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
