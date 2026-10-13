"""어떤 공고를 저장할지(데이터·AI 범위), 어떤 공고가 잡음인지 판단한다."""

from __future__ import annotations

import re
from functools import cache

from . import config
from .models import Posting


@cache
def _rules() -> tuple[set[str], list[re.Pattern], list[re.Pattern]]:
    scope = config.load("collect")["scope"]
    cats = set(scope.get("categories", []))
    include = [re.compile(p) for p in scope.get("title_include", [])]
    noise = [re.compile(p) for p in scope.get("noise", [])]
    return cats, include, noise


@cache
def _overseas_regions() -> frozenset[str]:
    return frozenset(config.load("collect")["scope"].get("overseas_regions", []))


def is_overseas(p: Posting) -> bool:
    """근무지가 해외뿐인 공고. 저장은 하되 국내 목록·분석에서는 뺀다."""
    regions = _overseas_regions()
    return bool(p.regions) and all(r in regions for r in p.regions)


def in_scope(p: Posting) -> bool:
    """데이터·AI 직무 분류에 있거나 제목에 관련 말이 있으면 저장 대상."""
    cats, include, _ = _rules()
    for c in p.categories:
        if c in cats or c.split("/")[0] in cats:
            return True
    return any(r.search(p.title) for r in include)


def noise_reason(p: Posting) -> str | None:
    """명백한 잡음이면 걸린 규칙을 돌려준다."""
    _, _, noise = _rules()
    for r in noise:
        if r.search(p.title):
            return r.pattern
    return None
