from jobpost import company_class as cc


def _c(key="가나", corp=None, basics=None, groups=None, public=None, nps=None, src="그 외"):
    return cc.classify(key, corp=corp, basics=basics, group_keys=groups or {}, public_keys=public or set(),
                       nps=nps or {}, source_type=src)


def test_sme_limit_by_industry():
    assert cc.sme_limit("62010") == 800    # 정보통신
    assert cc.sme_limit("26110") == 1000   # 전자부품
    assert cc.sme_limit("64191") == 400    # 금융
    assert cc.sme_limit(None) == 1500


def test_order_of_evidence():
    fin = {"finance": {"years": [{"revenue": 2000e8}]}, "company": {"industry_code": "62010"}}
    corp = {"corp_code": "1", "corp_name": "가나"}
    assert _c(public={"가나"}).type == "공기업·공공기관"
    assert _c(groups={"가나": "가나그룹"}, corp=corp, basics=fin).type == "대기업"
    assert _c(corp={**corp, "dart_key": "다라"}, groups={"다라": "다라그룹"}).type == "대기업"
    assert _c(corp=corp, basics=fin).type == "중견"
    small = {"finance": {"years": [{"revenue": 300e8}]}}
    assert _c(corp=corp, basics=small).type == "중소·스타트업"


def test_no_dart_uses_small_company_check():
    assert _c(nps={"가나": (1, 40)}).type == "중소·스타트업"
    assert _c(nps={"가나": (1, 900)}).type == "확인 안 됨"
    assert _c().type == "확인 안 됨"
    r = _c(src="대기업")
    assert (r.type, r.basis) == ("대기업", "수집처 표시")
