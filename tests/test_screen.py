import gzip
import json
from datetime import date

from jobpost import screen
from jobpost.models import Posting, Source
from jobpost.store import Store


def test_build_groups_duplicates_and_skips_overseas_and_closed(tmp_path):
    s = Store(tmp_path)
    day = date(2026, 10, 13)
    ps = [
        Posting(source=Source.ZIGHANG, source_id="a", url="https://z/a", company="(주)회사",
                title="데이터 엔지니어", career_min=5, career_max=None, regions=["서울"]),
        Posting(source=Source.REMEMBER, source_id="1", url="https://r/1", company="회사",
                title="데이터 엔지니어", description="[주요업무] " + "데이터 파이프라인 구축 " * 5),
        Posting(source=Source.ZIGHANG, source_id="b", url="https://z/b", company="외국회사",
                title="Data Engineer", regions=["해외"]),
        Posting(source=Source.SARAMIN, source_id="9", url="https://s/9", company="다른회사",
                title="데이터 분석가"),
    ]
    extra = {
        "zighang:a": {"company_key": "회사"},
        "remember:1": {"company_key": "회사", "dup_of": "zighang:a"},
        "zighang:b": {"company_key": "외국회사", "overseas": True},
        "saramin:9": {"company_key": "다른회사"},
    }
    s.ingest(day, ps, {"zighang", "remember", "saramin"}, extra)
    s.state["saramin:9"]["closed_on"] = "2026-10-13"
    s.state["remember:1"]["job_type"] = {"id": "data_eng"}  # 대표에 없으면 묶인 공고의 유형을 쓴다
    s.save()

    built, bodies = screen.build(tmp_path, today=day)
    assert [p["id"] for p in built["postings"]] == ["zighang:a"]
    p = built["postings"][0]
    assert p["career"] == "경력 5년 이상"
    assert p["jobType"] == "data_eng"
    assert p["hasBody"] and bodies["bodies"]["zighang:a"]["source"] == "remember"
    assert {"id": "data_eng", "name": "데이터 엔지니어", "short": "데이터 엔지니어", "direction": True} in built["jobTypes"]
    assert {"id": "non_data", "direction": False}.items() <= next(t for t in built["jobTypes"] if t["id"] == "non_data").items()
    assert [x["name"] for x in p["sources"]] == ["직행", "리멤버"]
    assert p["sources"][1]["url"] == "https://r/1"
    assert built["companies"]["회사"] == {"name": "회사", "type": "그 외", "group": None}
    assert built["counts"] == {"open": 1, "new": 1, "companies": 1}

    out = screen.write(built, tmp_path / "out" / "screen.json.gz")
    with gzip.open(out, "rt", encoding="utf-8") as f:
        assert json.load(f)["postings"][0]["id"] == "zighang:a"


def test_upload_sends_gzip_with_upsert(tmp_path, monkeypatch):
    from jobpost import publish

    calls = []

    class FakeResp:
        status_code = 200
        text = "{}"

    class FakeSession:
        def post(self, url, data, headers, timeout):
            calls.append((url, data, headers))
            return FakeResp()

    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co/")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "k")
    f = tmp_path / "screen.json.gz"
    f.write_bytes(b"\x1f\x8b")
    assert publish.configured()
    publish.upload(f, session=FakeSession())
    url, data, headers = calls[0]
    assert url == "https://x.supabase.co/storage/v1/object/screen/screen.json.gz"
    assert data == b"\x1f\x8b" and headers["x-upsert"] == "true"
    assert headers["apikey"] == "k" and "Authorization" not in headers


def test_body_shard_matches_the_web_hash(tmp_path):
    # web/src/lib/load.test.ts와 같은 값이어야 한다
    assert screen.body_shard("zighang:a") == "04"
    assert screen.body_shard("saramin:55277376") == "08"
    paths = screen.write_bodies({"version": 3, "date": "2026-10-13",
                                 "bodies": {"zighang:a": {"text": "x", "source": "zighang"}}}, tmp_path)
    assert len(paths) == screen.BODY_SHARDS
    with gzip.open(tmp_path / "bodies" / "04.json.gz", "rt", encoding="utf-8") as f:
        assert json.load(f)["bodies"] == {"zighang:a": {"text": "x", "source": "zighang"}}
