"""회사별 기업 구분(대기업, 공기업·공공기관, 외국계)과 그룹 이름을 정한다.

수집처가 붙인 구분을 회사 키 단위로 모아 data/companies.json에 쌓는다. 리멤버처럼 구분을 주지
않는 수집처의 공고도 같은 회사가 다른 곳에서 구분된 적이 있으면 그 구분을 쓴다.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from . import company_class, config
from .models import CompanyType
from .normalize import clean_company, company_key

# 수집처 표기 → 공통 구분
_TYPE_MAP = {
    "대기업": CompanyType.LARGE,
    "공공기관": CompanyType.PUBLIC,
    "공기업·공공기관": CompanyType.PUBLIC,
    "외국계": CompanyType.FOREIGN,
}
# 여러 구분이 붙으면 이 순서로 고른다. 그룹 규칙에 걸리면 대기업이 우선한다
_PRIORITY = [CompanyType.PUBLIC, CompanyType.FOREIGN, CompanyType.LARGE]

# 서치펌(헤드헌팅 회사) 이름. 사람인·직행은 헤드헌팅 공고를 따로 표시하지 않아 회사 이름으로 가린다(2026-11-02).
# "리서치·리써치"는 서치펌이 아니다(바이오리서치에이아이, 티엔티리써치)
_SEARCH_FIRM = re.compile(r"(?<!리)(?:써치|서치)|헤드헌|스카우트|에이치알|HR컨설팅|HR$", re.I)
# 헤드헌팅 공고 제목의 의뢰 회사 설명: "[국내 바이오 제약 대기업]", "(바이오, 대기업 계열)", "외국계 해운 IT기업"
_CLIENT_WORDS = [("외국계", CompanyType.FOREIGN), ("공기업", CompanyType.PUBLIC), ("공공기관", CompanyType.PUBLIC),
                 ("대기업", CompanyType.LARGE)]


@cache
def _named_search_firms() -> frozenset[str]:
    return frozenset(config.load("company_aliases").get("search_firms") or [])


def is_search_firm(name: str) -> bool:
    return bool(_SEARCH_FIRM.search(clean_company(name or ""))) or company_key(name or "") in _named_search_firms()


def client_from_title(title: str) -> CompanyType | None:
    """헤드헌팅 공고 제목에 적힌 의뢰 회사 구분. 없으면 None(중견·스타트업 같은 말은 '그 외'와 같아 따로 두지 않는다)."""
    return next((t for word, t in _CLIENT_WORDS if word in (title or "")), None)


_TITLE_HEAD = re.compile(r"^\s*[\[【]([^\]】]{2,40})[\]】]")
_NOT_COMPANY = re.compile(r"(그룹|계열|그룹사|자회사|공채|채용|경력|신입|인턴)$")


def subsidiary_from_title(company: str, title: str) -> str | None:
    """제목 맨 앞 [회사]가 같은 그룹의 자회사면 그 이름(공고를 자회사 화면으로 옮긴다, 2026-11-02).
    "[쿠팡로지스틱스서비스] …"를 쿠팡이 올린 경우처럼, 수집처는 모회사 이름으로 올리고 실제 고용 회사는 제목에 적는다.
    조건: 대괄호 안이 회사 키가 다르고, 모회사 키로 시작하고(쿠팡 → 쿠팡로지스틱스서비스), 같은 그룹 규칙에 맞는다.
    "[KB금융그룹 계열]"처럼 회사 이름이 아닌 말, "[한화시스템/방산]"의 / 뒤 부서는 뺀다."""
    m = _TITLE_HEAD.match(title or "")
    if not m:
        return None
    sub = re.sub(r"\([^)]*\)", "", m.group(1).split("/")[0]).strip()
    if not sub or _NOT_COMPANY.search(sub):
        return None
    parent, child = company_key(company), company_key(sub)
    if not parent or child == parent or not child.startswith(parent):
        return None
    group = match_group(company)
    return sub if group and match_group(sub) == group else None


@cache
def _group_rules() -> list[tuple[str, re.Pattern]]:
    rules = []
    for group, patterns in (config.load("groups").get("groups") or {}).items():
        for p in patterns:
            rules.append((group, re.compile(p)))
    return rules


@cache
def _not_members() -> list[re.Pattern]:
    return [re.compile(p) for p in config.load("groups").get("not_members") or []]


def match_group(name: str) -> str | None:
    """이름 규칙(config/groups.yaml)으로 정한 그룹 이름. 이름만 같은 다른 회사(not_members)는 None."""
    cleaned = clean_company(name)
    if any(p.search(cleaned) for p in _not_members()):
        return None
    for group, pattern in _group_rules():
        if pattern.search(cleaned):
            return group
    return None


def major_candidates(listed: list[list[str]]) -> list[dict[str, str | None]]:
    """주요 기업 후보: DART 상장사 목록(dart/listed.json)과 사업보고서를 낸 비상장 회사(dart/filers.json, 종목코드 "")의
    [고유번호, DART 이름, 종목코드]에서 그룹 규칙에 맞는 곳(대기업)과 config/groups.yaml major.extra에 적은 곳.
    상장사 목록에는 상장 폐지된 곳도 섞여 있어 지금 상장 여부는 기업개황으로 따로 본다."""
    cfg = config.load("groups").get("major") or {}
    skip = re.compile(cfg["skip"]) if cfg.get("skip") else None
    extra = {name: ctype for ctype, names in (cfg.get("extra") or {}).items() for name in names or []}
    out: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for code, name, stock in listed:
        if code in seen:
            continue
        seen.add(code)
        if skip and skip.search(name):
            continue
        if name in extra:
            out.append({"code": code, "name": name, "type": extra[name], "group": None, "stock": stock})
            continue
        group = match_group(name)
        if group:
            out.append({"code": code, "name": name, "type": CompanyType.LARGE.value, "group": group, "stock": stock})
    return out


def posting_type(registry: CompanyRegistry, key: str, name: str, client_type: str | None = None) -> CompanyType:
    """공고 하나의 기업 구분. 헤드헌팅 공고는 의뢰 회사 구분(수집처가 적어 준 것)을 쓴다."""
    if client_type:
        return CompanyType(client_type)
    return registry.company_type(key, name)


class CompanyRegistry:
    """수집처 표시(data/companies.json)와, 공식 목록(data/official/groups.json)이 있으면 새 기준(company_class)으로 정한
    기업 구분. 공식 목록이 없으면(처음, 시험 데이터) 수집처 표시만 쓴다."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict] = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        self._official: dict[str, Any] | None = None
        self._results: dict[str, Any] = {}

    def _evidence(self) -> dict[str, Any]:
        """새 기준에 쓰는 근거(data 폴더의 dart/, official/). 한 번만 읽는다."""
        if self._official is None:
            from . import official
            base = self.path.parent
            groups = official.load(base, "groups")
            ev: dict[str, Any] = {}
            if groups.get("companies"):
                def _j(name: str) -> dict:
                    p = base / "dart" / name
                    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
                public = official.load(base, "public")
                ev = {"groups": company_class.group_index(groups), "corps": _j("corps.json"),
                      "basics": _j("basics.json"), "nps": official.load_nps(base),
                      "public": {o["key"]: o.get("list") or "공공기관 목록" for o in public.get("orgs") or []}}
            self._official = ev
        return self._official

    def classify(self, key: str, name: str = "") -> company_class.Result | None:
        """새 기준 결과(구분·근거). 공식 목록이 없으면 None."""
        ev = self._evidence()
        if not ev:
            return None
        if key not in self._results:
            corp = dict(ev["corps"].get(key) or {})
            if corp.get("corp_name"):
                corp["dart_key"] = company_key(corp["corp_name"])
            self._results[key] = company_class.classify(
                key, corp=corp, basics=ev["basics"].get(corp.get("corp_code") or ""), group_keys=ev["groups"],
                public_keys=ev["public"], nps=ev["nps"], source_type=self.source_type(key, name).value)
        return self._results[key]

    def update(self, company_types: dict[str, set[str]], names: dict[str, str], today: str) -> None:
        for key, types in company_types.items():
            rec = self.data.setdefault(key, {"name": names.get(key, key), "types": {}})
            for t in types:
                rec["types"][t] = today
        for key, name in names.items():
            if key in self.data and not self.data[key].get("name"):
                self.data[key]["name"] = name

    def company_type(self, key: str, name: str = "") -> CompanyType:
        r = self.classify(key, name)
        return CompanyType(r.type) if r else self.source_type(key, name)

    def source_type(self, key: str, name: str = "") -> CompanyType:
        """수집처가 붙인 구분(옛 기준). 새 기준의 마지막 근거로만 쓴다."""
        raw = (self.data.get(key) or {}).get("types") or {}
        types = {_TYPE_MAP[t] for t in raw if t in _TYPE_MAP}
        if not types:
            return CompanyType.OTHER
        if CompanyType.LARGE in types and match_group(name or self.data[key].get("name", "")):
            return CompanyType.LARGE
        for t in _PRIORITY:
            if t in types:
                return t
        return CompanyType.OTHER

    def group(self, key: str, name: str = "") -> str | None:
        """대기업으로 구분된 회사만 그룹 이름을 붙인다."""
        if self.company_type(key, name) is not CompanyType.LARGE:
            return None
        named = match_group(name or (self.data.get(key) or {}).get("name", ""))  # 보통 부르는 그룹 이름(SK, CJ) 먼저
        r = self.classify(key, name)
        if not named and r and r.basis.startswith("공정위 기업집단 "):
            return r.basis.removeprefix("공정위 기업집단 ")
        return named

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = dict(sorted(self.data.items()))
        self.path.write_text(json.dumps(ordered, ensure_ascii=False, indent=1), encoding="utf-8")
