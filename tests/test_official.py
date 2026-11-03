from jobpost import official


def test_public_orgs_reads_three_lists():
    a = "기관명,기관유형,주무부처\n한국가나공사,공기업(시장형),부처\n".encode("utf-8-sig")
    b = "연번,지역,지방공기업명,공기업유형\n1,서울,서울가나공사,도시개발\n".encode("cp949")
    c = "연번,구분,기관명\n1,출연기관,서울가나재단\n".encode("cp949")
    orgs = official.public_orgs([("a", "a.csv", a), ("b", "b.csv", b), ("c", "c.csv", c)])
    assert [(o["name"], o["type"]) for o in orgs] == [("한국가나공사", "공기업(시장형)"), ("서울가나공사", "도시개발"),
                                                      ("서울가나재단", "출연기관")]
    assert orgs[1]["list"].startswith("지방공기업")
