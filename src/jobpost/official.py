"""공식 목록: 기업 구분(docs/collection.md '기업 구분과 그룹')의 근거가 되는 공적 자료를 받아 data/official/에 둔다.

- 공정위 대규모기업집단 소속회사(공공데이터포털 OpenAPI 15091891, 서비스 키 DATA_GO_KR_KEY 필요).
  매년 5월 1일 기준으로 지정. 응답은 XML, 소속회사마다 소속회사명·법인등록번호·사업자등록번호, 기업집단 이름(unityGrupNm)은
  기업집단코드를 주지 않고 부를 때만 온다(2026-11-03 명세).
- 공공기관 목록: 공공데이터포털 파일 3개(키 없음). 재정경제부 공공기관 지정현황(15088742, 2026년 355곳, utf-8 CSV),
  행정안전부 지방공기업 설립현황(15048282, cp949), 지방출자출연기관 설립현황(15048281, cp949). 알리오 화면 호출
  (alio.go.kr /organ/findOrganApbaList.json)은 2026-11-03 Actions에서 서버 오류라 쓰지 않는다.
- 국민연금 가입 사업장 내역(공공데이터포털 파일 15083277, 매월, CSV cp949 약 115MB). 사업장명·사업자등록번호 앞 6자리·가입자 수.
  화면에 직원 수를 보이지 않는다. DART에 없는 회사가 작은 회사인지 확인하는 데만 쓴다(회사 키 → 후보 수, 가장 큰 가입자 수).
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import re
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree

import requests

from .normalize import company_key

log = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (jobpost official-lists)"}
GROUPS_URL = "https://apis.data.go.kr/1130000/appnGroupAffiList/appnGroupAffiListApi"
NPS_PK = "15083277"
DG = "https://www.data.go.kr"


def _dir(data_dir: Path) -> Path:
    d = data_dir / "official"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _items(xml: bytes) -> tuple[list[dict[str, str]], int, str]:
    root = ElementTree.fromstring(xml)
    code = root.findtext(".//resultCode") or ""
    total = int(root.findtext(".//totalCount") or 0)
    rows = []
    for el in root.iter():
        if el.find("entrprsNm") is not None:
            rows.append({c.tag: (c.text or "").strip() for c in el})
    return rows, total, code


def fetch_groups(key: str, ym: str | None = None, session: requests.Session | None = None) -> dict[str, Any]:
    """지정 기업집단 소속회사 전부. ym(YYYYMM)을 비우면 올해 05, 없으면 작년 05."""
    s = session or requests.Session()
    key = unquote(key.strip())  # 공공데이터포털 '인코딩' 키를 넣어도 두 번 인코딩되지 않게
    today = date.today()
    tries = [ym] if ym else [f"{today.year}05", f"{today.year - 1}05"]
    for y in tries:
        out: list[dict[str, str]] = []
        page, total, code = 1, None, ""
        while True:
            r = s.get(GROUPS_URL, params={"serviceKey": key, "pageNo": page, "numOfRows": 1000, "presentnYear": y},
                      headers=UA, timeout=60)
            if r.status_code != 200 or not r.content.lstrip().startswith(b"<"):
                raise RuntimeError(f"공정위 응답 {r.status_code}: {r.text[:200]}")  # 키는 주소에만 있고 본문에는 없다
            rows, total, code = _items(r.content)
            out += rows
            if not rows or len(out) >= total:
                break
            page += 1
            time.sleep(0.5)
        if out:
            comps = [{"group": x.get("unityGrupNm", ""), "name": x.get("entrprsNm", ""),
                      "key": company_key(x.get("entrprsNm", "")), "jurirno": x.get("jurirno", ""),
                      "bizrno": x.get("bizrno", "")} for x in out]
            return {"ym": y, "fetched": today.isoformat(), "companies": comps}
        log.info("공정위 %s: 결과 없음(code %s, total %s)", y, code, total)
    raise RuntimeError("공정위 목록이 비었다")


PUBLIC_FILES = [  # (공공데이터포털 파일 번호, 목록 이름, 기관명 칸, 유형 칸)
    ("15088742", "공공기관 지정현황(재정경제부)", "기관명", "기관유형"),
    ("15048282", "지방공기업 설립현황(행정안전부)", "지방공기업명", "공기업유형"),
    ("15048281", "지방출자출연기관 설립현황(행정안전부)", "기관명", "구분"),
]


def dg_file(pk: str, session: requests.Session | None = None) -> tuple[bytes, str]:
    """공공데이터포털 파일 데이터(원본 바이트, 파일 이름). 화면의 다운로드 순서를 그대로 따른다(키 없음).
    순서: 데이터 화면에서 fn_fileDataDown(번호, 상세 번호, '', 파일 순번) → selectFileDataDownload → check-limit → fileDownload."""
    s = session or requests.Session()
    page = s.get(f"{DG}/data/{pk}/fileData.do", headers=UA, timeout=60).text
    m = re.search(rf"fn_fileDataDown\('{pk}',\s*'([^']+)',\s*'[^']*',\s*'(\d+)'", page)
    if not m:
        raise RuntimeError(f"공공데이터포털 {pk}: 파일 정보를 찾지 못했다")
    dpk, sn = m.groups()
    info = s.post(f"{DG}/tcs/dss/selectFileDataDownload.do", headers=UA, timeout=60,
                  data={"publicDataDetailPk": dpk, "publicDataPk": pk, "atchFileId": "", "fileDetailSn": sn,
                        "publicDataTyCode": "PR0051"}).json()
    fid, fsn = info["atchFileId"], info["fileDetailSn"]
    name = (info.get("fileDataRegistVO") or {}).get("orginlFileNm") or info["dataSetFileDetailInfo"].get("dataNm") or ""
    lim = s.post(f"{DG}/cmm/cmm/check-limit.json", data={"atchFileId": fid, "fileDetailSn": fsn},
                 headers=UA, timeout=60).json()
    if lim.get("needCaptcha"):
        raise RuntimeError(f"공공데이터포털 {pk}: 보안문자를 요구한다")
    r = s.get(f"{DG}/cmm/cmm/fileDownload.do", params={"atchFileId": fid, "fileDetailSn": fsn, "dataNm": pk},
              headers=UA, timeout=600)
    r.raise_for_status()
    return r.content, name


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp949", errors="replace")


def public_orgs(files: list[tuple[str, str, bytes]]) -> list[dict[str, str]]:
    """[(목록 이름, 파일 이름, 원본)] → [{name, key, type, list}]. 칸 이름으로 기관명·유형을 찾는다."""
    out = []
    for (_, label, name_col, type_col), (_, _, raw) in zip(PUBLIC_FILES, files, strict=True):
        rows = list(csv.DictReader(io.StringIO(_decode(raw))))
        for r in rows:
            name = (r.get(name_col) or "").strip()
            if name:
                out.append({"name": name, "key": company_key(name), "type": (r.get(type_col) or "").strip(),
                            "list": label})
    return out


def fetch_public(session: requests.Session | None = None) -> dict[str, Any]:
    """공공기관(공공기관운영법 지정, 매년 1월) · 지방공기업 · 지방출자출연기관 목록. 알리오 화면 호출은 Actions에서
    서버 오류라(2026-11-03) 같은 목록을 공공데이터포털 파일로 받는다."""
    files = []
    for pk, label, _, _ in PUBLIC_FILES:
        raw, fname = dg_file(pk, session)
        files.append((label, fname, raw))
    orgs = public_orgs(files)
    return {"fetched": date.today().isoformat(), "files": [f[1] for f in files], "orgs": orgs}


def nps_download(session: requests.Session | None = None) -> tuple[bytes, str]:
    """국민연금 사업장 CSV(원본 바이트)와 파일 이름."""
    return dg_file(NPS_PK, session)


def nps_index(raw: bytes) -> dict[str, list[int]]:
    """회사 키 → [후보 수, 가장 큰 가입자 수]. 등록 상태(1)인 사업장만."""
    idx: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    rd = csv.reader(io.TextIOWrapper(io.BytesIO(raw), encoding="cp949", errors="replace"))
    next(rd, None)
    for row in rd:
        if len(row) < 19 or row[3] != "1":
            continue
        try:
            n = int(row[18])
        except ValueError:
            continue
        k = company_key(row[1])
        if not k:
            continue
        v = idx[k]
        v[0] += 1
        v[1] = max(v[1], n)
    return dict(idx)


def save_nps(data_dir: Path, idx: dict[str, list[int]], source: str) -> Path:
    p = _dir(data_dir) / "nps.tsv.gz"
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write(f"# {source} {date.today().isoformat()}\n")
        for k in sorted(idx):
            f.write(f"{k}\t{idx[k][0]}\t{idx[k][1]}\n")
    return p


def load_nps(data_dir: Path) -> dict[str, tuple[int, int]]:
    p = data_dir / "official" / "nps.tsv.gz"
    if not p.exists():
        return {}
    out = {}
    with gzip.open(p, "rt", encoding="utf-8") as f:
        for line in f:
            if line.startswith("#"):
                continue
            k, c, n = line.rstrip("\n").split("\t")
            out[k] = (int(c), int(n))
    return out


def load(data_dir: Path, name: str) -> dict[str, Any]:
    p = data_dir / "official" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(data_dir: Path, name: str, obj: dict[str, Any]) -> None:
    (_dir(data_dir) / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=0), encoding="utf-8")


def run(data_dir: Path, what: list[str], key: str | None) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    s = requests.Session()
    if "groups" in what:
        try:
            if not key:
                raise RuntimeError("DATA_GO_KR_KEY 없음")
            g = fetch_groups(key, session=s)
            save(data_dir, "groups", g)
            summary["groups"] = {"ym": g["ym"], "companies": len(g["companies"]),
                                 "groups": len({c["group"] for c in g["companies"]})}
        except Exception as e:  # noqa: BLE001 - 하나가 실패해도 나머지는 받는다
            summary["groups"] = {"error": str(e)[:300]}
    if "public" in what:
        try:
            a = fetch_public(s)
            save(data_dir, "public", a)
            types: dict[str, int] = defaultdict(int)
            for o in a["orgs"]:
                types[o["type"]] += 1
            summary["public"] = {"orgs": len(a["orgs"]), "types": dict(types)}
        except Exception as e:  # noqa: BLE001
            summary["public"] = {"error": str(e)[:300]}
    if "nps" in what:
        try:
            raw, name = nps_download(s)
            idx = nps_index(raw)
            p = save_nps(data_dir, idx, name)
            summary["nps"] = {"file": name, "mb": round(len(raw) / 1e6, 1), "keys": len(idx),
                              "saved_mb": round(p.stat().st_size / 1e6, 1)}
        except Exception as e:  # noqa: BLE001
            summary["nps"] = {"error": str(e)[:300]}
    return summary
