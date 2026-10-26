from jobpost import research


def _basics(name, ind, rev, op=None, basis="연결"):
    years = [{"year": 2025, "revenue": rev, "operating": op}] if rev is not None else []
    return {"company": {"name": name, "industry_code": ind}, "finance": {"basis": basis, "years": years} if years else None}


def test_competitors_are_the_biggest_peers_in_the_same_industry():
    basics = {
        "1": _basics("삼성전자(주)", "264", 300, 30),
        "2": _basics("LG전자(주)", "264", 90, 3),
        "3": _basics("작은전자(주)", "264", 1, 0),
        "4": _basics("한화비전(주)", "264", 2, None),
        "5": _basics("현대자동차(주)", "30121", 180, 10),
        "6": _basics("국민은행", "64110", None),  # 매출이 없는 회사는 비교에서 뺀다
    }
    peers = research.Peers(basics)
    got = peers.competitors("1", {"1": "삼성전자", "2": "LG전자"}, {"2": "lg전자"}, n=2)
    assert got["industry"] == "264"
    assert [(r["name"], r["key"], r["self"]) for r in got["rows"]] == [
        ("삼성전자", None, True), ("LG전자", "lg전자", False), ("한화비전", None, False)]
    assert got["rows"][0]["margin"] == 10.0 and got["rows"][2]["margin"] is None
    # 같은 업종에 다른 회사가 없으면 자기 줄만
    assert [r["self"] for r in peers.competitors("5", {}, {}, n=2)["rows"]] == [True]
    # 매출이 없는 회사도 같은 업종의 큰 회사를 본다(자기 줄은 빈칸)
    assert peers.competitors("6", {}, {}, n=2)["rows"][0]["revenue"] is None
    assert peers.competitors("x", {}, {}) is None


def test_tools_count_postings_per_tool_by_slot():
    texts = ["AWS와 Airflow, Spark로 파이프라인", "AWS, Kubernetes 운영. Tableau 대시보드", "Excel 보고서"]
    got = research.tools(texts)
    assert got["postings"] == 3
    slots = {s["name"]: [(i["skill"], i["count"]) for i in s["items"]] for s in got["slots"]}
    assert slots["클라우드"] == [("AWS", 2), ("Kubernetes", 1)]
    assert slots["데이터 플랫폼"] == [("Spark", 1), ("Airflow", 1)]  # 같은 수면 설정 순서
    assert slots["BI"] == [("Tableau", 1)] and slots["AI 도구"] == []  # Excel은 도구 칸에 없다
    assert research.tools([]) is None


def test_competitors_match_industry_codes_of_different_lengths():
    basics = {
        "kt": _basics("(주)케이티", "612", 26, 1),
        "skt": _basics("SK텔레콤(주)", "61220", 17, 1),
        "lgu": _basics("(주)LG유플러스", "61220", 15, 1, basis="별도"),
        "x": _basics("통신기타", "6", 99, 1),       # 짧은 코드(1자리)는 접두어로 맞추지 않는다
        "y": _basics("다른업종", "61310", 50, 1),   # 612로 시작하지 않는다
    }
    got = research.Peers(basics).competitors("kt", {}, {}, n=2, self_name="KT")
    assert [r["name"] for r in got["rows"]] == ["KT", "SK텔레콤", "LG유플러스"]
    assert got["rows"][2]["basis"] == "별도" and got["rows"][1]["revenueName"] == "매출액"
    # 화면 이름을 모르면 기업개황 법인명에서 법인 표기만 지운다
    assert [r["name"] for r in research.Peers(basics).competitors("skt", {}, {}, n=2)["rows"]] == ["SK텔레콤", "케이티", "LG유플러스"]


def test_tools_use_exact_product_names_not_dictionary_aliases():
    texts = [
        "EMR(전자의무기록) 데이터 분석, 임상 GCP 준수",        # 의료 문맥: AWS·GCP가 아니다
        "Redash와 Metabase로 대시보드, OpenSearch 운영",       # 비슷한 도구를 묶지 않고 이름 그대로
        "컨테이너 기반 IaC 경험, 스파크플러스 근무",             # 개념·주소는 도구가 아니다
        "GCP BigQuery와 Docker",
    ]
    got = research.tools(texts)
    found = {i["skill"]: i["count"] for s in got["slots"] for i in s["items"]}
    assert found == {"GCP": 1, "Docker": 1, "BigQuery": 1, "Redash": 1, "Metabase": 1, "OpenSearch": 1}
    assert research.tools(["엑셀 보고서"]) is None  # 찾은 도구가 없으면 모듈을 비운다
