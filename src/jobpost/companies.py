"""회사별 기업 구분(대기업, 공기업·공공기관, 외국계)과 그룹 이름을 정한다.

수집처가 붙인 구분을 회사 키 단위로 모아 data/companies.json에 쌓는다. 리멤버처럼 구분을 주지
않는 수집처의 공고도 같은 회사가 다른 곳에서 구분된 적이 있으면 그 구분을 쓴다.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

from . import config
from .models import CompanyType
from .normalize import clean_company

# 수집처 표기 → 공통 구분
_TYPE_MAP = {
    "대기업": CompanyType.LARGE,
    "공공기관": CompanyType.PUBLIC,
    "공기업·공공기관": CompanyType.PUBLIC,
    "외국계": CompanyType.FOREIGN,
}
# 여러 구분이 붙으면 이 순서로 고른다. 그룹 규칙에 걸리면 대기업이 우선한다
_PRIORITY = [CompanyType.PUBLIC, CompanyType.FOREIGN, CompanyType.LARGE]


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
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict] = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def update(self, company_types: dict[str, set[str]], names: dict[str, str], today: str) -> None:
        for key, types in company_types.items():
            rec = self.data.setdefault(key, {"name": names.get(key, key), "types": {}})
            for t in types:
                rec["types"][t] = today
        for key, name in names.items():
            if key in self.data and not self.data[key].get("name"):
                self.data[key]["name"] = name

    def company_type(self, key: str, name: str = "") -> CompanyType:
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
        return match_group(name or (self.data.get(key) or {}).get("name", ""))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = dict(sorted(self.data.items()))
        self.path.write_text(json.dumps(ordered, ensure_ascii=False, indent=1), encoding="utf-8")
